"""Estrategias en velas de 1h con filtro de tendencia en 4h.

Cada estrategia se define como una lista de condiciones para LONG y otra para
SHORT. La señal aparece cuando se cumplen todas; el panel muestra cuántas se
cumplen en cada momento. La señal se evalúa al cierre de la vela y la entrada
es al precio de apertura de la vela siguiente (orden a mercado).
"""
import numpy as np
import pandas as pd


def _alcista_4h(d):
    return (d["c4"] > d["ema200_4"]) & (d["ema50_4"] > d["ema200_4"])


def _bajista_4h(d):
    return (d["c4"] < d["ema200_4"]) & (d["ema50_4"] < d["ema200_4"])


def cond_retroceso(d):
    largo = {
        "Tendencia 4h alcista": _alcista_4h(d),
        "EMA20 sobre EMA50 en 1h": d["ema20"] > d["ema50"],
        "Retrocedió a la EMA20": d["low"].rolling(3).min() <= d["ema20"],
        "Cierra sobre el máximo previo": (d["close"] > d["high"].shift()) & (d["close"] > d["ema20"]),
        "RSI entre 45 y 70": d["rsi"].between(45, 70),
    }
    corto = {
        "Tendencia 4h bajista": _bajista_4h(d),
        "EMA20 bajo EMA50 en 1h": d["ema20"] < d["ema50"],
        "Rebotó a la EMA20": d["high"].rolling(3).max() >= d["ema20"],
        "Cierra bajo el mínimo previo": (d["close"] < d["low"].shift()) & (d["close"] < d["ema20"]),
        "RSI entre 30 y 55": d["rsi"].between(30, 55),
    }
    return largo, corto


def cond_ruptura(d):
    largo = {
        "Precio 4h sobre su EMA50": d["c4"] > d["ema50_4"],
        "Cierra sobre el máximo de 20 velas": d["close"] > d["max20"],
        "Tendencia con fuerza (ADX > 20)": d["adx"] > 20,
    }
    corto = {
        "Precio 4h bajo su EMA50": d["c4"] < d["ema50_4"],
        "Cierra bajo el mínimo de 20 velas": d["close"] < d["min20"],
        "Tendencia con fuerza (ADX > 20)": d["adx"] > 20,
    }
    return largo, corto


def cond_rebote_rsi(d):
    previo = d["rsi"].shift()
    largo = {
        "Tendencia 4h alcista": _alcista_4h(d),
        "RSI venía en sobreventa (< 35)": previo < 35,
        "RSI cruza 35 al alza": d["rsi"] >= 35,
    }
    corto = {
        "Tendencia 4h bajista": _bajista_4h(d),
        "RSI venía en sobrecompra (> 65)": previo > 65,
        "RSI cruza 65 a la baja": d["rsi"] <= 65,
    }
    return largo, corto


def _todas(conds):
    return pd.concat([s.fillna(False).astype(bool) for s in conds.values()], axis=1).all(axis=1)


def senal_desde(cond_fn):
    def senal(d):
        largo, corto = cond_fn(d)
        l, c = _todas(largo), _todas(corto)
        return pd.Series(np.where(l, 1, np.where(c, -1, 0)), index=d.index)
    return senal


def condiciones_actuales(cond_fn, d):
    """Condiciones en la última vela: elige el lado (long/short) más avanzado."""
    largo, corto = cond_fn(d)
    l = [(k, bool(v.fillna(False).iloc[-1])) for k, v in largo.items()]
    c = [(k, bool(v.fillna(False).iloc[-1])) for k, v in corto.items()]
    nl, nc = sum(ok for _, ok in l), sum(ok for _, ok in c)
    if nl > nc or (nl == nc and d["c4"].iloc[-1] >= d["ema50_4"].iloc[-1]):
        return 1, l
    return -1, c


CONDICIONES = {
    "retroceso": ("Retroceso en tendencia", cond_retroceso),
    "ruptura": ("Ruptura de rango", cond_ruptura),
    "rebote_rsi": ("Rebote de RSI", cond_rebote_rsi),
}

ESTRATEGIAS = {k: (n, senal_desde(f)) for k, (n, f) in CONDICIONES.items()}
