"""Seguimiento real de las señales enviadas: cuándo tocan objetivo, stop o tiempo.

Usa las mismas reglas que el backtest, para que el rendimiento real y el
histórico se puedan comparar de forma justa.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

import config as C
import salidas
from salidas import Posicion

COSTO_LADO = C.COMISION_TAKER + C.DESLIZAMIENTO


def resultado_r(s, salida):
    bruto = s["lado"] * (salida - s["entrada"])
    return (bruto - COSTO_LADO * (s["entrada"] + salida)) / s["riesgo"]


def reproducir(s, barras):
    """Recorre las velas desde la entrada con la misma gestión del backtest."""
    pos = Posicion(s["lado"], s["entrada"], s["stop"], s["riesgo"], s.get("gestion", "fija"))
    for t, b in barras.iterrows():
        if pos.vela(b["open"], b["high"], b["low"], b["close"]):
            return pos, t
    return pos, None


def actualizar(senales, velas, precios):
    """Revisa las señales activas.

    Devuelve (cerradas, eventos): las que se cerraron ahora y los objetivos parciales
    alcanzados desde la revisión anterior (para avisar "TP1 alcanzado, stop a la entrada").
    """
    cerradas, eventos = [], []
    for s in senales:
        if s["estado"] != "activa":
            continue
        d = velas.get(s["par"])
        pos = None
        if d is not None and len(d):
            barras = d[d.index >= pd.Timestamp(s["t_entrada"])]
            pos, t = reproducir(s, barras)
            antes = s.get("tps", 0)
            if pos.hechos > antes:
                for k in range(antes, pos.hechos):
                    eventos.append((s, k))
            s["tps"] = pos.hechos
            avisado = s.get("stop_avisado", s["stop"])
            # avisar para mover el stop en MEXC solo si se movió al menos 0.5R desde el último aviso
            if s.get("gestion") == "tendencia" and s["lado"] * (pos.stop - avisado) >= 0.5 * s["riesgo"]:
                eventos.append((s, "stop"))
                s["stop_avisado"] = pos.stop
            s["stop_actual"] = pos.stop
            if t is not None:
                s.update(estado=pos.motivo, salida=float(pos.salida_media),
                         r=round(pos.r(), 3), t_cierre=(t + timedelta(hours=1)).isoformat())
                cerradas.append(s)
                continue
        precio = precios.get(s["par"])
        if precio:
            s["precio_actual"] = precio
            s["r_actual"] = round(pos.r(precio) if pos else resultado_r(s, precio), 3)
    return cerradas, eventos


def rendimiento(senales):
    cerradas = [s for s in senales if s["estado"] != "activa"]
    if not cerradas:
        return {"n": 0, "acierto": 0.0, "total_r": 0.0, "exp_r": 0.0, "activas":
                sum(s["estado"] == "activa" for s in senales)}
    r = [s["r"] for s in cerradas]
    return {
        "n": len(r),
        "acierto": sum(x > 0 for x in r) / len(r),
        "total_r": round(sum(r), 3),
        "exp_r": round(sum(r) / len(r), 3),
        "activas": sum(s["estado"] == "activa" for s in senales),
    }


def nueva(r, niveles_fn, ahora=None):
    """Crea el registro de una señal a partir del resultado del análisis."""
    lado, entrada = r["ultima_senal"], r["cierre"]
    stop, objetivo, riesgo = niveles_fn(lado, entrada, r["atr"])
    modo = r["m"].get("gestion") or ("escalonada" if C.GESTION == "auto" else C.GESTION)
    objetivo = salidas.objetivos(lado, entrada, riesgo, modo)[-1]
    t_entrada = r["vela"] + timedelta(hours=1)
    return {
        "id": f"{r['par']}|{r['clave']}|{r['vela'].isoformat()}",
        "par": r["par"], "clave": r["clave"], "nombre": r["nombre"], "lado": lado,
        "entrada": entrada, "stop": stop, "objetivo": objetivo, "riesgo": riesgo,
        "atr": r["atr"], "t_entrada": t_entrada.isoformat(),
        "t_limite": (t_entrada + timedelta(hours=1)).isoformat(),
        "precio_limite": entrada + lado * C.MAX_DISTANCIA_ATR * r["atr"],
        "gestion": modo,
        "objetivos": salidas.objetivos(lado, entrada, riesgo, modo),
        "r_neto": [round(salidas.r_si_llega(lado, entrada, stop, riesgo, k, modo), 2)
                   for k in range(len(salidas.tramos(modo)))],
        "apal_max": salidas.apalancamiento_max(riesgo / entrada),
        "tps": 0, "stop_actual": stop,
        "estado": "activa", "precio_actual": entrada, "r_actual": 0.0,
        "creada": (ahora or datetime.now(timezone.utc)).isoformat(),
        "stats": {k: r["m"]["total"][k] for k in ("n", "acierto", "exp_r", "fb", "t")},
    }
