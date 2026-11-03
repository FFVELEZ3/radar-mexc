"""Seguimiento real de las señales enviadas: cuándo tocan objetivo, stop o tiempo.

Usa las mismas reglas que el backtest, para que el rendimiento real y el
histórico se puedan comparar de forma justa.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

import config as C

COSTO_LADO = C.COMISION_TAKER + C.DESLIZAMIENTO


def resultado_r(s, salida):
    bruto = s["lado"] * (salida - s["entrada"])
    return (bruto - COSTO_LADO * (s["entrada"] + salida)) / s["riesgo"]


def actualizar(senales, velas, precios):
    """Revisa las señales activas. Devuelve la lista de las que se cerraron ahora."""
    cerradas = []
    for s in senales:
        if s["estado"] != "activa":
            continue
        d = velas.get(s["par"])
        if d is not None and len(d):
            inicio = pd.Timestamp(s["t_entrada"])
            barras = d[d.index >= inicio]
            lado, stop, obj = s["lado"], s["stop"], s["objetivo"]
            for n, (t, b) in enumerate(barras.iterrows()):
                salida = motivo = None
                if lado == 1:
                    if n > 0 and b["open"] <= stop:
                        salida, motivo = b["open"], "stop"
                    elif b["low"] <= stop:
                        salida, motivo = stop, "stop"
                    elif b["high"] >= obj:
                        salida, motivo = obj, "objetivo"
                else:
                    if n > 0 and b["open"] >= stop:
                        salida, motivo = b["open"], "stop"
                    elif b["high"] >= stop:
                        salida, motivo = stop, "stop"
                    elif b["low"] <= obj:
                        salida, motivo = obj, "objetivo"
                if salida is None and n + 1 >= C.VELAS_MAXIMAS:
                    salida, motivo = b["close"], "tiempo"
                if salida is not None:
                    s.update(estado=motivo, salida=float(salida),
                             r=round(resultado_r(s, salida), 3),
                             t_cierre=(t + timedelta(hours=1)).isoformat())
                    cerradas.append(s)
                    break
        if s["estado"] == "activa":
            precio = precios.get(s["par"])
            if precio:
                s["precio_actual"] = precio
                s["r_actual"] = round(resultado_r(s, precio), 3)
    return cerradas


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
    t_entrada = r["vela"] + timedelta(hours=1)
    return {
        "id": f"{r['par']}|{r['clave']}|{r['vela'].isoformat()}",
        "par": r["par"], "clave": r["clave"], "nombre": r["nombre"], "lado": lado,
        "entrada": entrada, "stop": stop, "objetivo": objetivo, "riesgo": riesgo,
        "atr": r["atr"], "t_entrada": t_entrada.isoformat(),
        "t_limite": (t_entrada + timedelta(hours=1)).isoformat(),
        "precio_limite": entrada + lado * C.MAX_DISTANCIA_ATR * r["atr"],
        "estado": "activa", "precio_actual": entrada, "r_actual": 0.0,
        "creada": (ahora or datetime.now(timezone.utc)).isoformat(),
        "stats": {k: r["m"]["total"][k] for k in ("n", "acierto", "exp_r", "fb", "t")},
    }
