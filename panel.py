"""Construye el archivo de datos que lee el panel web (docs/data/datos.json)."""
import json
import math
import os
from datetime import timedelta

import config as C
from estrategias import CONDICIONES, condiciones_actuales

VELAS_GRAFICO = 168  # 7 días de velas de 1h


def _limpio(x):
    """Convierte a tipos que JSON acepta (sin NaN ni infinito)."""
    if isinstance(x, dict):
        return {k: _limpio(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_limpio(v) for v in x]
    if isinstance(x, float):
        return round(x, 8) if math.isfinite(x) else None
    if hasattr(x, "item"):  # tipos de numpy
        return _limpio(x.item())
    return x


def _stats(m):
    return {k: v for k, v in m.items()}


def _tendencia(d):
    u = d.iloc[-1]
    if u["c4"] > u["ema200_4"] and u["ema50_4"] > u["ema200_4"]:
        return "alcista"
    if u["c4"] < u["ema200_4"] and u["ema50_4"] < u["ema200_4"]:
        return "bajista"
    return "lateral"


def resumen_par(par, d, resultados_par, info):
    u = d.iloc[-1]
    ventana = d.iloc[-VELAS_GRAFICO:]
    inicio = ventana.index[0]
    t = [int(x.timestamp()) for x in ventana.index]
    estrategias, marcas = [], []
    for r in resultados_par:
        lado, conds = condiciones_actuales(CONDICIONES[r["clave"]][1], d)
        estrategias.append({
            "clave": r["clave"], "nombre": r["nombre"], "aprobada": r["m"]["aprobada"],
            "motivos": r["m"]["motivos"], "lado": lado,
            "condiciones": conds, "cumplidas": sum(ok for _, ok in conds), "total": len(conds),
            "senal": r["ultima_senal"],
            "total_stats": _stats(r["m"]["total"]), "oos_stats": _stats(r["m"]["oos"]),
        })
        ops = r["m"]["ops"]
        if len(ops):
            for _, op in ops[ops["entrada_t"] >= inicio].iterrows():
                marcas.append({"t": int(op["entrada_t"].timestamp()) - 3600, "lado": int(op["lado"]),
                               "clave": r["clave"], "r": float(op["r"])})
    return {
        "par": par, "precio": info.get("precio") or float(u["close"]),
        "cambio24": info.get("cambio24", 0.0), "volumen24": info.get("volumen24", 0.0),
        "funding": info.get("funding", 0.0), "tendencia": _tendencia(d),
        "rsi": float(u["rsi"]), "adx": float(u["adx"]), "atr_pct": float(u["atr"] / u["close"]),
        "ultima_vela": int(d.index[-1].timestamp()),
        "velas": [[ti, float(o), float(h), float(l), float(c)] for ti, o, h, l, c in
                  zip(t, ventana["open"], ventana["high"], ventana["low"], ventana["close"])],
        "ema20": ventana["ema20"].tolist(), "ema50": ventana["ema50"].tolist(),
        "estrategias": estrategias, "marcas": marcas,
    }


def curva_aprobadas(resultados):
    ops = []
    for r in resultados:
        if r["m"]["aprobada"] and len(r["m"]["ops"]):
            ops += [(op.entrada_t, op.r) for op in r["m"]["ops"].itertuples()]
    ops.sort()
    acum, curva = 0.0, []
    for t, x in ops:
        acum += x
        curva.append([int(t.timestamp()), round(acum, 3)])
    return curva


def construir(ahora, pares, por_par, resultados, info, senales, rendimiento, errores,
              demo=False, bot=None):
    backtest = [{
        "par": r["par"], "clave": r["clave"], "nombre": r["nombre"],
        "aprobada": r["m"]["aprobada"], "motivos": r["m"]["motivos"],
        "total": _stats(r["m"]["total"]), "ins": _stats(r["m"]["ins"]),
        "oos": _stats(r["m"]["oos"]),
    } for r in resultados]
    activas = [s for s in senales if s["estado"] == "activa"]
    cerradas = sorted((s for s in senales if s["estado"] != "activa"),
                      key=lambda s: s.get("t_cierre", ""), reverse=True)[:100]
    return _limpio({
        "demo": demo,
        "generado": ahora.isoformat(),
        "proxima": (ahora + timedelta(minutes=C.INTERVALO_MIN)).isoformat(),
        "intervalo_min": C.INTERVALO_MIN,
        "config": {
            "riesgo_usd": C.RIESGO_POR_OPERACION_USD, "apalancamiento": C.APALANCAMIENTO,
            "comision": C.COMISION_TAKER, "deslizamiento": C.DESLIZAMIENTO,
            "atr_stop": C.ATR_STOP, "ratio": C.RATIO_BENEFICIO,
            "velas_max": C.VELAS_MAXIMAS, "min_t": C.MIN_T, "dias": C.DIAS_HISTORIA,
            "zona": C.ZONA_HORARIA,
        },
        "pares": [resumen_par(p, por_par[p], [r for r in resultados if r["par"] == p],
                              info.get(p, {})) for p in pares if p in por_par],
        "activas": activas, "historial": cerradas, "rendimiento": rendimiento,
        "backtest": backtest, "curva": curva_aprobadas(resultados), "errores": errores,
        "bot": bot or {},
        "reales": sorted(({"par": s["par"], "lado": s["lado"], "nombre": s["nombre"],
                           "senal": s["estado"], **s["real"]} for s in senales if s.get("real")),
                         key=lambda x: x.get("t_cierre") or x.get("t", ""), reverse=True)[:60],
    })


def guardar(ruta, contenido):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(contenido, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, ruta)
