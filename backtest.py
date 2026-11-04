"""Backtest de cada estrategia con costos reales y validación fuera de muestra.

Supuestos prudentes:
- Entrada a la apertura de la vela siguiente a la señal.
- Si en una misma vela se tocan el stop y el objetivo, se asume el stop.
- Si el precio abre más allá del stop (hueco), se sale a la apertura.
- Una sola operación abierta a la vez por par y estrategia.
- Comisión taker + deslizamiento en la entrada y en la salida.
"""
import math

import numpy as np
import pandas as pd

import config as C
from salidas import Posicion, objetivos


def niveles(lado, entrada, atr):
    """Stop, objetivo final y riesgo (distancia al stop)."""
    riesgo = C.ATR_STOP * atr
    stop = entrada - lado * riesgo
    objetivo = objetivos(lado or 1, entrada, riesgo)[-1] if lado else entrada + riesgo * C.RATIO_BENEFICIO
    return stop, objetivo, riesgo


def simular(d, senal, modo=None):
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    a = d["atr"].to_numpy()
    s = senal.to_numpy()
    idx = d.index
    ops = []
    i, n = 0, len(d)
    while i < n - 1:
        lado = s[i]
        if lado == 0 or not np.isfinite(a[i]):
            i += 1
            continue
        j = i + 1
        entrada = o[j]
        stop, _, riesgo = niveles(lado, entrada, a[i])
        pos = Posicion(int(lado), entrada, stop, riesgo, modo)
        k, cerrada = j, False
        while k < n:
            if pos.vela(o[k], h[k], l[k], c[k]):
                cerrada = True
                break
            k += 1
        if not cerrada:  # operación aún abierta al final de los datos: no se cuenta
            break
        r = pos.r()
        ops.append({
            "entrada_t": idx[j], "lado": int(lado), "entrada": entrada,
            "salida": pos.salida_media, "motivo": pos.motivo, "tps": pos.hechos,
            "r": r, "pct": r * riesgo / entrada,
        })
        i = k + 1
    return pd.DataFrame(ops)


def _wilson_inferior(aciertos, n, z=1.645):
    """Límite inferior (90 %) de la tasa de acierto: lo mínimo razonable a esperar."""
    if n == 0:
        return 0.0
    p = aciertos / n
    den = 1 + z * z / n
    centro = p + z * z / (2 * n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centro - margen) / den)


def metricas(ops):
    if ops is None or len(ops) == 0:
        return {"n": 0, "acierto": 0.0, "acierto_min": 0.0, "exp_r": 0.0,
                "fb": 0.0, "dd_r": 0.0, "total_r": 0.0, "gan_prom": 0.0, "per_prom": 0.0,
                "t": 0.0}
    r = ops["r"]
    gan, per = r[r > 0], r[r <= 0]
    curva = r.cumsum()
    dd = (curva.cummax().clip(lower=0) - curva).max()
    return {
        "n": int(len(r)),
        "acierto": float((r > 0).mean()),
        "acierto_min": _wilson_inferior(int((r > 0).sum()), len(r)),
        "exp_r": float(r.mean()),
        "fb": float(gan.sum() / -per.sum()) if per.sum() < 0 else float("inf"),
        "dd_r": float(dd),
        "total_r": float(r.sum()),
        "gan_prom": float(gan.mean()) if len(gan) else 0.0,
        "per_prom": float(per.mean()) if len(per) else 0.0,
        "t": float(r.mean() / r.std(ddof=1) * math.sqrt(len(r)))
             if len(r) > 2 and r.std(ddof=1) > 0 else 0.0,
    }


def _partir(ops, corte):
    if len(ops):
        return ops[ops["entrada_t"] < corte], ops[ops["entrada_t"] >= corte]
    return ops, ops


def evaluar(d, senal):
    """Métricas totales, en muestra (70 %) y fuera de muestra (30 %) + veredicto.

    Con GESTION="auto" se simulan las dos formas de salir (1 objetivo o 3 objetivos) y se
    elige la que mejor funcionó SOLO en el 70 % antiguo; el 30 % reciente la confirma o no.
    Así la elección no usa información del periodo con el que se valida.
    """
    corte = d.index[0] + (d.index[-1] - d.index[0]) * C.FRACCION_EN_MUESTRA
    modos = ["fija", "escalonada"] if C.GESTION == "auto" else [C.GESTION]
    sims = {k: simular(d, senal, k) for k in modos}
    def exp_ins(k):
        ins_k = _partir(sims[k], corte)[0]
        return metricas(ins_k)["exp_r"] if len(ins_k) else -9.0
    modo = max(modos, key=exp_ins)
    ops = sims[modo]
    ins, oos = _partir(ops, corte)
    m = {"total": metricas(ops), "ins": metricas(ins), "oos": metricas(oos)}
    t = m["total"]
    motivos = []
    if t["n"] < C.MIN_OPERACIONES:
        motivos.append(f"pocas operaciones ({t['n']})")
    if m["oos"]["n"] < C.MIN_OPERACIONES_OOS:
        motivos.append(f"pocas operaciones recientes ({m['oos']['n']})")
    if m["ins"]["exp_r"] <= 0:
        motivos.append("expectativa negativa en el periodo de prueba")
    if m["oos"]["exp_r"] <= 0:
        motivos.append("expectativa negativa en el periodo reciente")
    if t["fb"] < C.MIN_FACTOR_BENEFICIO:
        motivos.append(f"factor de beneficio bajo ({t['fb']:.2f})")
    if t["t"] < C.MIN_T:
        motivos.append(f"resultado no distinguible del azar (t={t['t']:.1f})")
    m["aprobada"] = not motivos
    m["motivos"] = motivos
    m["ops"] = ops
    # comparación con la otra forma de salir (informativa)
    otro = "escalonada" if modo == "fija" else "fija"
    alt = sims.get(otro)
    if alt is None:
        alt = simular(d, senal, otro)
    m["alternativa"] = {"gestion": otro, **metricas(alt)}
    m["gestion"] = modo
    if len(ops):
        m["total"]["tp"] = [float((ops["tps"] >= k).mean()) for k in (1, 2, 3)]
    return m


# ---------- efecto del horario y del día ----------
# Horas en UTC (Ecuador = UTC-5). La entrada es la apertura de la vela siguiente a la señal.
FRANJAS = [
    ("Asia (19:00–02:00 Ecuador)", lambda h, d: (h >= 0) & (h < 7)),
    ("Europa (02:00–08:00)", lambda h, d: (h >= 7) & (h < 13)),
    ("EE.UU. (08:00–16:00)", lambda h, d: (h >= 13) & (h < 21)),
    ("Tarde-noche (16:00–19:00)", lambda h, d: h >= 21),
    ("Apertura de Londres (02:00–04:00)", lambda h, d: (h >= 7) & (h < 9)),
    ("Apertura de Wall Street (08:30–10:30)", lambda h, d: (h >= 13) & (h < 16)),
    ("Lunes a viernes", lambda h, d: d < 5),
    ("Fin de semana (sáb y dom)", lambda h, d: d >= 5),
    ("Lunes", lambda h, d: d == 0),
    ("Viernes", lambda h, d: d == 4),
]


def por_horario(ops):
    """Resultado por franja horaria y día, con la mitad antigua y la reciente por separado
    para ver si el efecto se repite o fue casualidad de un periodo."""
    if ops is None or not len(ops):
        return []
    t = pd.DatetimeIndex(ops["entrada_t"]).tz_convert("UTC")
    h, d = t.hour.to_numpy(), t.dayofweek.to_numpy()
    corte = t.min() + (t.max() - t.min()) * C.FRACCION_EN_MUESTRA
    salida = []
    for nombre, f in FRANJAS:
        m = f(h, d)
        sub = ops[m]
        if not len(sub):
            continue
        tt = t[m]
        mt, mi, mo = metricas(sub), metricas(sub[tt < corte]), metricas(sub[tt >= corte])
        salida.append({"franja": nombre, "n": mt["n"], "exp_r": round(mt["exp_r"], 3), "t": round(mt["t"], 2),
                       "exp_ins": round(mi["exp_r"], 3), "exp_oos": round(mo["exp_r"], 3), "n_oos": mo["n"],
                       "consistente": bool(mt["t"] >= 2 and mi["exp_r"] > 0 and mo["exp_r"] > 0 and mo["n"] >= 15)})
    return salida
