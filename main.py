"""Radar de futuros MEXC: análisis, panel web y alertas por Telegram.

Uso:
    python main.py            # análisis completo: actualiza el panel y envía alertas
    python main.py prueba     # envía un mensaje de prueba a Telegram
    python main.py backtest   # solo muestra el reporte de backtest
"""
import json
import math
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config as C
import datos
import ejecutor
import panel
from mexc_privado import ClienteMexc
import salidas
import seguimiento
import telegram
from backtest import evaluar, niveles
from estrategias import ESTRATEGIAS
from indicadores import preparar

TZ = ZoneInfo(C.ZONA_HORARIA)
RUTA_SENALES = os.path.join(C.DIR_DATOS, "senales.json")
RUTA_PANEL = os.path.join(C.DIR_DATOS, "datos.json")


# ---------- utilidades ----------

def precio(p):
    if not p or not math.isfinite(p):
        return "-"
    dec = min(10, max(2, 3 - int(math.floor(math.log10(abs(p))))))
    return f"{p:,.{dec}f}"


def hora_local(ts):
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return ts.astimezone(TZ).strftime("%d/%m %H:%M")


def pct(x):
    return f"{x * 100:.0f}%"


def url_panel():
    if os.getenv("URL_PANEL"):
        return os.getenv("URL_PANEL")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if "/" in repo:
        usuario, nombre = repo.split("/", 1)
        return f"https://{usuario.lower()}.github.io/{nombre}/"
    return ""


def crear_cliente():
    clave, secreto = os.getenv("MEXC_API_KEY", "").strip(), os.getenv("MEXC_API_SECRET", "").strip()
    return ClienteMexc(clave, secreto) if clave and secreto else None


def cargar_estado():
    try:
        with open(RUTA_SENALES, encoding="utf-8") as f:
            e = json.load(f)
            e.setdefault("senales", [])
            e.setdefault("resumen", "")
            return e
    except (OSError, ValueError):
        return {"senales": [], "resumen": ""}


# ---------- análisis ----------

def analizar(info, pares, extra=()):
    """Analiza los pares top y descarga velas de los pares con señales activas."""
    resultados, errores, por_par = [], [], {}
    for par in list(pares) + [p for p in extra if p not in pares]:
        try:
            d = preparar(datos.velas_1h(par, C.DIAS_HISTORIA))
        except Exception as e:  # un par con problemas no detiene a los demás
            errores.append(f"{par}: {e}")
            continue
        por_par[par] = d
        if par not in pares:
            continue
        for clave, (nombre, funcion) in ESTRATEGIAS.items():
            senal = funcion(d).fillna(0)
            resultados.append({
                "par": par, "clave": clave, "nombre": nombre, "m": evaluar(d, senal),
                "ultima_senal": int(senal.iloc[-1]), "vela": d.index[-1],
                "cierre": float(d["close"].iloc[-1]), "atr": float(d["atr"].iloc[-1]),
                "dias": (d.index[-1] - d.index[0]).days,
            })
    return resultados, errores, por_par


# ---------- mensajes ----------

def mensaje_senal(s, r, modo="simulado"):
    lado, entrada = s["lado"], s["entrada"]
    etiqueta = {"real": "🤖 El bot intentará abrirla en real (aviso aparte).",
                "simulado": "📝 En papel: el bot la sigue sin dinero real.",
                "apagado": "Bot apagado: solo aviso."}.get(modo, "")
    t, oos = r["m"]["total"], r["m"]["oos"]
    dist = s["riesgo"] / entrada
    costo = (C.COMISION_TAKER + C.DESLIZAMIENTO) * 2 * entrada
    cantidad = C.RIESGO_POR_OPERACION_USD / (s["riesgo"] + costo)
    nocional = cantidad * entrada
    moneda = s["par"].split("_")[0]
    objs, netos = s.get("objetivos") or [s["objetivo"]], s.get("r_neto") or []
    reparto = [f for _, f in salidas.tramos(s.get("gestion", "fija"))]
    lineas = [
        f"{'🟢 LONG' if lado == 1 else '🔴 SHORT'} <b>{s['par']}</b> · 1h",
        f"Estrategia: {s['nombre']}",
        etiqueta,
        "",
        f"📍 Entrada: <b>{precio(entrada)}</b> (a mercado)",
        f"   No entres si el precio ya pasó {precio(s['precio_limite'])}",
    ]
    for k, o in enumerate(objs):
        neto = f" · neto {netos[k]:+.2f}R" if k < len(netos) else ""
        cierra = f" · cierra {reparto[k] * 100:.0f}%" if len(objs) > 1 else ""
        lineas.append(f"🎯 TP{k + 1}: <b>{precio(o)}</b> ({lado * (o - entrada) / entrada * 100:+.2f}%){cierra}{neto}")
    lineas.append(f"🛑 Stop loss: <b>{precio(s['stop'])}</b> ({-dist * 100:+.2f}%) · −1R + comisiones")
    if len(objs) > 1:
        lineas.append("🔒 Al tocar TP1 el stop pasa a la entrada: desde ahí ya no puedes perder.")
    lineas += [
        f"⏱ Se cierra sola a las {int(C.VELAS_MAXIMAS)} h si no toca ni stop ni "
        f"{'TP' + str(len(objs)) if len(objs) > 1 else 'el objetivo'}",
        f"📐 Gestión elegida por el historial: {'3 objetivos' if len(objs) > 1 else '1 objetivo'}",
        "",
        f"💵 Para arriesgar ${C.RIESGO_POR_OPERACION_USD:g}: {cantidad:.6g} {moneda} "
        f"(nocional ${nocional:,.0f}, margen ${nocional / C.APALANCAMIENTO:,.0f} "
        f"a {int(C.APALANCAMIENTO)}x)",
        f"⚙️ Apalancamiento: usa {int(C.APALANCAMIENTO)}x. Máximo técnico {s.get('apal_max', '?')}x "
        "(más arriba, la liquidación llega antes que el stop). Margen aislado.",
    ]
    if dist >= 0.8 / C.APALANCAMIENTO:
        lineas.append("⚠️ La liquidación quedaría cerca del stop. Baja el apalancamiento.")
    tp = t.get("tp")
    lineas += [
        "",
        f"<b>Historial</b> ({r['dias']} días, con comisiones):",
        f"{t['n']} operaciones · acierto {pct(t['acierto'])} (mínimo probable {pct(t['acierto_min'])})",
    ]
    if tp and len(objs) > 1:
        lineas.append(f"Llegaron a TP1 {pct(tp[0])} · TP2 {pct(tp[1])} · TP3 {pct(tp[2])}")
    lineas += [
        f"Expectativa <b>{t['exp_r']:+.2f}R</b> · factor de beneficio {t['fb']:.2f} · t={t['t']:.1f}",
        f"Periodo reciente: {oos['n']} ops, {oos['exp_r']:+.2f}R · caída máxima {t['dd_r']:.1f}R",
        f"Válida para entrar hasta las {hora_local(s['t_limite'])}.",
    ]
    if url_panel():
        lineas.append(f'<a href="{url_panel()}">Abrir panel</a>')
    return "\n".join(lineas)


def mensaje_tp(s, k):
    lado = "LONG" if s["lado"] == 1 else "SHORT"
    objs = s.get("objetivos") or [s["objetivo"]]
    extra = " Stop movido a la entrada: la operación ya no puede perder." if k == 0 and len(objs) > 1 else ""
    falta = f" Siguiente: TP{k + 2} {precio(objs[k + 1])}." if k + 1 < len(objs) else ""
    return (f"🎯 <b>{s['par']}</b> {lado} alcanzó <b>TP{k + 1}</b> ({precio(objs[k])}).{extra}{falta}")


def mensaje_cierre(s):
    icono = {"objetivo": "✅", "stop": "⛔", "tiempo": "⏱", "protegida": "🔒"}.get(s["estado"], "•")
    texto = {"objetivo": "alcanzó todos los objetivos", "stop": "tocó el stop",
             "tiempo": "se cerró por tiempo",
             "protegida": f"cerró en la entrada después de TP{s.get('tps', 1)}"}.get(s["estado"], s["estado"])
    lado = "LONG" if s["lado"] == 1 else "SHORT"
    usd = s["r"] * C.RIESGO_POR_OPERACION_USD
    return (f"{icono} <b>{s['par']}</b> {lado} {texto}\n"
            f"{s['nombre']} · salida media {precio(s['salida'])}\n"
            f"Resultado: <b>{s['r']:+.2f}R</b> (≈ ${usd:+.2f} con tu riesgo por operación)")


def mensaje_contraria(s, r):
    nuevo = "LONG" if r["ultima_senal"] == 1 else "SHORT"
    return (f"⚠️ <b>Señal contraria</b> en {s['par']}\n"
            f"Tienes un {'LONG' if s['lado'] == 1 else 'SHORT'} activo ({s['nombre']}) y ahora "
            f"«{r['nombre']}» marca {nuevo}{'' if r['m']['aprobada'] else ' (sin ventaja comprobada)'}.\n"
            f"Resultado actual {s.get('r_actual', 0):+.2f}R. Revisa el panel; si ya tocó TP1 el stop está en la entrada.")


def mensaje_resumen(resultados, rend, errores):
    aprobadas = sorted((r for r in resultados if r["m"]["aprobada"]),
                       key=lambda r: r["m"]["total"]["exp_r"], reverse=True)
    lineas = [f"📊 <b>Resumen diario</b> · {len(resultados)} combinaciones evaluadas"]
    if rend["n"]:
        lineas.append(f"Señales cerradas: {rend['n']} · acierto {pct(rend['acierto'])} · "
                      f"total {rend['total_r']:+.2f}R")
    if aprobadas:
        lineas.append("Con ventaja comprobada hoy:")
        for r in aprobadas:
            t = r["m"]["total"]
            lineas.append(f"• {r['par']} · {r['nombre']}: {t['exp_r']:+.2f}R, t={t['t']:.1f}")
    else:
        lineas.append("Ninguna combinación pasa hoy el filtro: no habrá señales.")
    if errores:
        lineas.append(f"Pares con error de datos: {len(errores)}")
    if url_panel():
        lineas.append(f'<a href="{url_panel()}">Abrir panel</a>')
    return "\n".join(lineas)


def reporte_markdown(resultados):
    filas = ["| Par | Estrategia | Ops | Acierto | Exp. R | FB | t | Reciente | Estado |",
             "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in sorted(resultados, key=lambda r: r["m"]["total"]["exp_r"], reverse=True):
        t, o = r["m"]["total"], r["m"]["oos"]
        estado = "✅ aprobada" if r["m"]["aprobada"] else "❌ " + "; ".join(r["m"]["motivos"])
        fb = "∞" if t["fb"] == float("inf") else f"{t['fb']:.2f}"
        filas.append(f"| {r['par']} | {r['nombre']} | {t['n']} | {pct(t['acierto'])} | "
                     f"{t['exp_r']:+.2f} | {fb} | {t['t']:.1f} | {o['n']} / {o['exp_r']:+.2f} | {estado} |")
    return "\n".join(filas)


# ---------- flujos ----------

def ejecutar(solo_reporte=False, ahora=None, demo=False):
    ahora = ahora or datetime.now(timezone.utc)
    info = datos.tickers()
    pares = datos.pares_top(C.NUM_PARES, C.EXCLUIR, info)
    estado = cargar_estado()
    senales = estado["senales"]
    activas_pares = {s["par"] for s in senales if s["estado"] == "activa"}
    resultados, errores, por_par = analizar(info, pares, activas_pares)

    reporte = (f"## Backtest {ahora.astimezone(TZ):%d/%m/%Y %H:%M}\n\n"
               f"Pares: {', '.join(pares)}\n\n{reporte_markdown(resultados)}")
    if errores:
        reporte += "\n\n**Errores de datos:**\n" + "\n".join(f"- {e}" for e in errores)
    print(reporte)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(reporte + "\n")
    if solo_reporte:
        return

    if not resultados:
        telegram.enviar("⚠️ No se pudieron descargar datos de MEXC en esta revisión.\n"
                        + "\n".join(errores[:5]))
        return

    # 1. Seguimiento de señales abiertas
    precios = {p: v["precio"] for p, v in info.items()}
    cerradas_ahora, eventos = seguimiento.actualizar(senales, por_par, precios)
    for s, k in eventos:
        if not s.get("observacion") and s["id"] not in {c["id"] for c in cerradas_ahora}:
            telegram.enviar(mensaje_tp(s, k))
    for s in cerradas_ahora:
        if not s.get("observacion"):
            telegram.enviar(mensaje_cierre(s))

    # 2. Señales nuevas (solo combinaciones aprobadas y vela recién cerrada)
    cliente = crear_cliente()
    modo_previo = ejecutor.decidir_modo(senales, cliente is not None)[0]
    nuevas = []
    ids = {s["id"] for s in senales}
    abiertas = {(s["par"], s["clave"]) for s in senales if s["estado"] == "activa"}
    for r in resultados:
        if r["ultima_senal"] == 0:
            continue
        # señal contraria: otra estrategia apunta al lado opuesto de una señal activa
        if ahora - (r["vela"] + timedelta(hours=1)) <= timedelta(minutes=90):
            for a in senales:
                if (a["estado"] == "activa" and not a.get("observacion") and a["par"] == r["par"]
                        and a["lado"] == -r["ultima_senal"]):
                    marca = f"{r['clave']}|{r['vela'].isoformat()}"
                    if marca not in a.setdefault("contrarias", []):
                        a["contrarias"].append(marca)
                        telegram.enviar(mensaje_contraria(a, r))
        observacion = not r["m"]["aprobada"]  # sin ventaja: se sigue en papel, sin aviso ni dinero
        if (r["par"], r["clave"]) in abiertas:
            continue  # igual que el backtest: una operación a la vez por par y estrategia
        if ahora - (r["vela"] + timedelta(hours=1)) > timedelta(minutes=90):
            continue
        s = seguimiento.nueva(r, niveles, ahora)
        if s["id"] in ids:
            continue
        s["precio_actual"] = precios.get(r["par"], s["entrada"])
        s["r_actual"] = round(seguimiento.resultado_r(s, s["precio_actual"]), 3)
        s["observacion"] = observacion
        senales.append(s)
        ids.add(s["id"])
        if not observacion:
            nuevas.append(s)
            telegram.enviar(mensaje_senal(s, r, modo_previo))

    # 3. Operación automática (papel o real, con frenos)
    bot = ejecutor.procesar(cliente, senales, nuevas, precios, ahora, telegram.enviar)
    if bot["modo"] != estado.get("modo_bot"):
        if estado.get("modo_bot"):
            telegram.enviar(f"🔁 Modo del bot: <b>{bot['modo'].upper()}</b>. {bot['motivo']}")
        estado["modo_bot"] = bot["modo"]

    # 4. Resumen diario
    rend = seguimiento.rendimiento([s for s in senales if not s.get("observacion")])
    rend_obs = seguimiento.rendimiento([s for s in senales if s.get("observacion")])
    local = ahora.astimezone(TZ)
    if local.hour == C.HORA_RESUMEN and estado.get("resumen") != local.strftime("%Y-%m-%d"):
        if telegram.enviar(mensaje_resumen(resultados, rend, errores)):
            estado["resumen"] = local.strftime("%Y-%m-%d")

    # 5. Guardar estado y datos del panel
    cerradas = [s for s in senales if s["estado"] != "activa"][-800:]
    estado["senales"] = cerradas + [s for s in senales if s["estado"] == "activa"]
    panel.guardar(RUTA_SENALES, panel._limpio(estado))
    panel.guardar(RUTA_PANEL, panel.construir(
        ahora, pares, por_par, resultados, info, estado["senales"], rend, errores, demo, bot, rend_obs))
    print(f"Panel actualizado. Activas: {rend['activas']} · cerradas: {rend['n']}")


def prueba():
    ok = telegram.enviar("✅ Conexión correcta. Aquí recibirás las señales del radar de "
                         "futuros MEXC y el resultado de cada una.")
    pares = datos.pares_top(C.NUM_PARES, C.EXCLUIR)
    print("Telegram:", "OK" if ok else "FALLÓ")
    print("Pares vigilados:", ", ".join(pares))
    texto = "Pares vigilados ahora: " + ", ".join(pares)
    if url_panel():
        texto += f'\n<a href="{url_panel()}">Abrir panel</a>'
    telegram.enviar(texto)


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "senales"
    try:
        if modo == "prueba":
            prueba()
        elif modo == "backtest":
            ejecutar(solo_reporte=True)
        else:
            ejecutar()
    except Exception as e:
        traceback.print_exc()
        # avisar como máximo una vez cada 3 horas para no llenar el chat
        est = cargar_estado()
        ultimo = est.get("ultimo_error", "")
        ahora = datetime.now(timezone.utc)
        if not ultimo or ahora - datetime.fromisoformat(ultimo) > timedelta(hours=3):
            telegram.enviar(f"⚠️ El radar falló en esta revisión: {e}\n"
                            "Volverá a intentarlo en 15 minutos.")
            est["ultimo_error"] = ahora.isoformat()
            panel.guardar(RUTA_SENALES, panel._limpio(est))
        sys.exit(1)
