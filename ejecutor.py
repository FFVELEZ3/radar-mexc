"""Operación automática en MEXC con frenos de seguridad.

Flujo en cada revisión:
1. Decide el modo efectivo (papel o real) según la configuración y la evidencia.
2. Concilia las posiciones reales abiertas con MEXC (cerradas, cierre por tiempo).
3. Abre en real las señales nuevas que pasen todos los frenos.

Frenos (todos deben cumplirse antes de abrir una posición real):
- Máximo de posiciones abiertas y una sola posición por par.
- La pérdida del día y del mes, sumando lo realizado y el peor caso de lo abierto
  más la nueva operación, no puede superar los límites configurados.
- El precio no se alejó más de 0.5 ATR de la entrada calculada.
- La cantidad mínima del contrato no obliga a arriesgar más de lo configurado.
- Hay saldo disponible para el margen.
"""
import hashlib
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config as C
import salidas
from mexc_privado import ErrorMexc

TZ = ZoneInfo(C.ZONA_HORARIA)
COSTO_LADO = C.COMISION_TAKER + C.DESLIZAMIENTO


# ---------- modo ----------

def _exp(senales):
    r = [s.get("r", 0.0) for s in senales]
    return sum(r) / len(r) if r else 0.0


def decidir_modo(senales, hay_cliente):
    """Devuelve (modo_efectivo, explicación, progreso)."""
    cerradas = sorted((s for s in senales if s["estado"] != "activa" and not s.get("observacion")),
                      key=lambda s: s.get("t_cierre", ""))
    n, exp_total = len(cerradas), _exp(cerradas)
    ultimas = cerradas[-C.VENTANA_PAUSA:]
    progreso = {"cerradas": n, "necesarias": C.MIN_SENALES_PARA_REAL,
                "exp_r": round(exp_total, 3), "exp_ultimas": round(_exp(ultimas), 3)}
    if C.MODO == "apagado":
        return "apagado", "Operación automática apagada.", progreso
    if C.MODO == "simulado":
        return "simulado", "Modo simulado fijo: opera solo en papel.", progreso
    if not hay_cliente:
        return "simulado", "Faltan las claves de API de MEXC: opera en papel.", progreso
    if C.MODO == "real":
        return "real", "Modo real forzado por configuración.", progreso
    # auto
    if n < C.MIN_SENALES_PARA_REAL:
        return "simulado", (f"En prueba: {n} de {C.MIN_SENALES_PARA_REAL} señales cerradas "
                            "antes de usar dinero real."), progreso
    if exp_total <= 0:
        return "simulado", (f"El historial en papel no muestra ventaja ({exp_total:+.2f}R "
                            "por señal): sigue en papel."), progreso
    if len(ultimas) >= C.VENTANA_PAUSA and _exp(ultimas) < 0:
        return "simulado", (f"Pausa: las últimas {C.VENTANA_PAUSA} señales pierden en promedio "
                            f"({_exp(ultimas):+.2f}R). Vuelve a real cuando se recuperen."), progreso
    return "real", (f"Ventaja comprobada en papel: {n} señales, {exp_total:+.2f}R por señal."), progreso


# ---------- utilidades ----------

def _redondear(precio, tick):
    return round(round(precio / tick) * tick, 12)


def _oid(texto):
    return "rm" + hashlib.sha1(texto.encode()).hexdigest()[:20]


def _local(iso):
    return datetime.fromisoformat(iso).astimezone(TZ)


def perdidas(senales, ahora):
    """Resultado realizado hoy y este mes, y riesgo abierto, en USD (solo operaciones reales)."""
    hoy, mes = ahora.astimezone(TZ).date(), ahora.astimezone(TZ).strftime("%Y-%m")
    dia = mensual = abierto = 0.0
    for s in senales:
        real = s.get("real") or {}
        if real.get("estado") == "cerrada" and real.get("t_cierre"):
            t = _local(real["t_cierre"])
            if t.date() == hoy:
                dia += real.get("pnl", 0.0)
            if t.strftime("%Y-%m") == mes:
                mensual += real.get("pnl", 0.0)
        elif real.get("estado") == "abierta":
            abierto += real.get("riesgo_usd", C.RIESGO_POR_OPERACION_USD)
    return dia, mensual, abierto


def resumen_real(senales, ahora):
    dia, mes, abierto = perdidas(senales, ahora)
    reales = [s["real"] for s in senales if (s.get("real") or {}).get("estado") == "cerrada"]
    return {
        "hoy": round(dia, 4), "mes": round(mes, 4), "riesgo_abierto": round(abierto, 4),
        "abiertas": sum((s.get("real") or {}).get("estado") == "abierta" for s in senales),
        "cerradas": len(reales), "total": round(sum(r.get("pnl", 0.0) for r in reales), 4),
        "limite_dia": C.LIMITE_PERDIDA_DIARIA, "limite_mes": C.LIMITE_PERDIDA_MENSUAL,
        "max_posiciones": C.MAX_POSICIONES, "riesgo_usd": C.RIESGO_POR_OPERACION_USD,
        "apalancamiento": C.APALANCAMIENTO,
    }


# ---------- conciliación ----------

def conciliar(cliente, senales, precios, ahora, avisar):
    abiertas = [s for s in senales if (s.get("real") or {}).get("estado") == "abierta"]
    if not abiertas:
        return
    posiciones = cliente.posiciones()
    for s in abiertas:
        real = s["real"]
        pos = next((p for p in posiciones if p.get("symbol") == s["par"]
                    and int(p.get("positionType", 0)) == (1 if s["lado"] == 1 else 2)), None)
        if pos:
            real["position_id"] = pos.get("positionId")
            real["vol_abierto"] = float(pos.get("holdVol") or 0)
            real["liquidacion"] = float(pos.get("liquidatePrice") or 0)
            precio_ahora = precios.get(s["par"], s["entrada"])
            # Cierres parciales: el seguimiento en papel marcó TP1 / TP2 (TP3 lo cierra MEXC)
            reparto = [f for _, f in salidas.tramos(s.get("gestion", "fija"))]
            hechos = real.get("tps", 0)
            while hechos < min(s.get("tps", 0), len(reparto) - 1):
                parte = math.floor(real.get("vol", 0) * reparto[hechos] / real.get("unidad", 1)) * real.get("unidad", 1)
                parte = min(parte, real["vol_abierto"])
                if parte > 0:
                    try:
                        cliente.cerrar(s["par"], s["lado"], parte, precio_ahora, real["position_id"],
                                       _oid(f"{s['id']}|tp{hechos + 1}"))
                        real["vol_abierto"] -= parte
                        avisar(f"🎯 <b>Real</b> {s['par']}: TP{hechos + 1} — cerré {parte:g} contratos.")
                    except ErrorMexc as e:
                        avisar(f"⚠️ No pude cerrar la parte de TP{hechos + 1} en {s['par']}: {e}.")
                        break
                hechos += 1
                real["tps"] = hechos
            # Cierre total: por tiempo, o porque tras TP1 el precio volvió a la entrada
            if s["estado"] in ("tiempo", "protegida") and not real.get("cierre_enviado") and real["vol_abierto"] > 0:
                motivo = (f"por tiempo ({int(C.VELAS_MAXIMAS)} h sin tocar stop ni objetivo)"
                          if s["estado"] == "tiempo" else "en la entrada (protección tras TP1)")
                try:
                    cliente.cerrar(s["par"], s["lado"], real["vol_abierto"], precio_ahora,
                                   real["position_id"], _oid(s["id"] + "|cierre"))
                    real["cierre_enviado"] = ahora.isoformat()
                    avisar(f"🔒 Cerrando {s['par']} {motivo}.")
                except ErrorMexc as e:
                    avisar(f"⚠️ No pude cerrar {s['par']} {motivo}: {e}. Ciérrala en la app de MEXC.")
            continue
        # Ya no está abierta en MEXC: buscar el resultado
        pnl = None
        try:
            for h in cliente.posiciones_cerradas(s["par"]):
                if str(h.get("positionId")) == str(real.get("position_id")) or (
                        real.get("position_id") is None and int(h.get("state", 3)) == 3):
                    pnl = float(h.get("realised") or 0) + float(h.get("holdFee") or 0)
                    real["precio_salida"] = float(h.get("closeAvgPrice") or 0)
                    break
        except ErrorMexc:
            pass
        if pnl is None:  # sin dato de MEXC: estimación con el resultado en papel
            r = s.get("r", s.get("r_actual", -1.0))
            pnl = r * real.get("riesgo_usd", C.RIESGO_POR_OPERACION_USD)
            real["estimado"] = True
        real.update(estado="cerrada", pnl=round(pnl, 4), t_cierre=ahora.isoformat())
        avisar(f"{'✅' if pnl > 0 else '⛔'} <b>Real</b> {s['par']} cerrada en MEXC: "
               f"<b>{pnl:+.2f} USD</b>{' (estimado)' if real.get('estimado') else ''}")


# ---------- apertura ----------

def abrir_senal(cliente, s, senales, precios, ahora, avisar):
    """Intenta abrir en real una señal nueva. Devuelve True si se abrió."""
    def omitir(motivo):
        s["real"] = {"estado": "omitida", "motivo": motivo, "t": ahora.isoformat()}
        avisar(f"ℹ️ {s['par']}: señal solo en papel. {motivo}")
        return False

    abiertas = [x for x in senales if (x.get("real") or {}).get("estado") == "abierta"]
    if len(abiertas) >= C.MAX_POSICIONES:
        return omitir(f"Ya hay {len(abiertas)} posiciones reales abiertas (máximo {C.MAX_POSICIONES}).")
    if any(x["par"] == s["par"] for x in abiertas):
        return omitir("Ya hay una posición real en este par.")
    dia, mes, abierto = perdidas(senales, ahora)
    riesgo = C.RIESGO_POR_OPERACION_USD
    if dia - abierto - riesgo < -C.LIMITE_PERDIDA_DIARIA:
        return omitir(f"Límite diario: con lo perdido hoy ({dia:+.2f}) y lo abierto, "
                      f"otra pérdida superaría ${C.LIMITE_PERDIDA_DIARIA:g}.")
    if mes - abierto - riesgo < -C.LIMITE_PERDIDA_MENSUAL:
        return omitir(f"Límite mensual: con lo perdido este mes ({mes:+.2f}) y lo abierto, "
                      f"otra pérdida superaría ${C.LIMITE_PERDIDA_MENSUAL:g}.")

    precio = precios.get(s["par"]) or s["entrada"]
    if s["lado"] * (precio - s["entrada"]) > C.MAX_DISTANCIA_ATR * s["atr"]:
        return omitir("El precio ya se alejó de la entrada calculada.")
    if s["lado"] * (precio - s["stop"]) <= 0:
        return omitir("El precio ya está más allá del stop.")

    try:
        det = cliente.detalle(s["par"])
        stop = _redondear(s["stop"], det["tick"])
        objetivo = _redondear(s["objetivo"], det["tick"])
        perdida_por_contrato = (abs(precio - stop) + COSTO_LADO * (precio + stop)) * det["tam"]
        vol = math.floor(riesgo / perdida_por_contrato / det["unidad"]) * det["unidad"]
        if vol < det["min"]:
            minimo = det["min"] * perdida_por_contrato
            return omitir(f"El mínimo del contrato obligaría a arriesgar ${minimo:.2f}, "
                          f"más que tus ${riesgo:g}.")
        apal = min(int(C.APALANCAMIENTO), det["max_apal"])
        nocional = vol * det["tam"] * precio
        margen = nocional / apal
        if cliente.saldo_disponible() < margen * 1.05:
            return omitir(f"Saldo disponible insuficiente para el margen (${margen:.2f}).")
        oid = _oid(s["id"])
        cliente.abrir(s["par"], s["lado"], vol, _redondear(precio, det["tick"]), apal,
                      stop, objetivo, oid)
        ejecutada, position_id = precio, None
        try:
            o = cliente.orden_externa(s["par"], oid) or {}
            ejecutada = float(o.get("dealAvgPrice") or precio)
            position_id = o.get("positionId")
            if not position_id:
                tipo = 1 if s["lado"] == 1 else 2
                position_id = next((p.get("positionId") for p in cliente.posiciones()
                                    if p.get("symbol") == s["par"]
                                    and int(p.get("positionType", 0)) == tipo), None)
        except ErrorMexc:
            pass
        s["real"] = {"estado": "abierta", "oid": oid, "position_id": position_id,
                     "vol": vol, "unidad": det["unidad"], "tps": 0, "precio_entrada": ejecutada,
                     "stop": stop, "objetivo": objetivo, "apalancamiento": apal,
                     "nocional": round(nocional, 2), "margen": round(margen, 2),
                     "riesgo_usd": round(vol * perdida_por_contrato, 4), "t": ahora.isoformat()}
        avisar(f"🤖 <b>Orden real abierta</b> {s['par']} {'LONG' if s['lado'] == 1 else 'SHORT'}\n"
               f"{vol:g} contratos · entrada {ejecutada:g} · stop {stop:g} · objetivo {objetivo:g}\n"
               f"Margen aislado ${margen:.2f} a {apal}x · riesgo ${s['real']['riesgo_usd']:.2f}")
        return True
    except ErrorMexc as e:
        texto = str(e)
        pista = ""
        if "isolated" in texto.lower() or "unified" in texto.lower():
            pista = " Tu cuenta de futuros parece estar en modo Unificado: cámbiala a modo Simple."
        s["real"] = {"estado": "error", "motivo": texto[:200], "t": ahora.isoformat()}
        avisar(f"⚠️ MEXC rechazó la orden de {s['par']}: {texto[:200]}.{pista}")
        return False


def procesar(cliente, senales, nuevas, precios, ahora, avisar):
    """Punto de entrada. Devuelve el estado del bot para el panel."""
    modo, motivo, progreso = decidir_modo(senales, cliente is not None)
    if cliente is not None and modo != "apagado":
        try:
            conciliar(cliente, senales, precios, ahora, avisar)
        except ErrorMexc as e:
            avisar(f"⚠️ No pude revisar las posiciones en MEXC: {e}")
    if modo == "real":
        for s in nuevas:
            abrir_senal(cliente, s, senales, precios, ahora, avisar)
    return {"modo": modo, "motivo": motivo, "progreso": progreso,
            "configurado": C.MODO, "real": resumen_real(senales, ahora)}
