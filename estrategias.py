"""Estrategias en velas de 1h con filtros de temporalidades mayores (4h y diario).

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


def _dia_entrada(d):
    """Día (UTC, 0 = lunes) en que se entra: la apertura de la vela siguiente a la señal."""
    return pd.Series((d.index + pd.Timedelta(hours=1)).dayofweek, index=d.index)


def _entre_semana(d):
    # Medido en un año y 20 pares: las rupturas en sábado y domingo pierden ~-0.32R por operación
    # en la parte antigua y en la reciente (poco volumen, rupturas falsas).
    return _dia_entrada(d) < 5


def cond_ruptura(d):
    largo = {
        "Entre semana (sin rupturas en fin de semana)": _entre_semana(d),
        "Precio 4h sobre su EMA50": d["c4"] > d["ema50_4"],
        "Cierra sobre el máximo de 20 velas": d["close"] > d["max20"],
        "Tendencia con fuerza (ADX > 20)": d["adx"] > 20,
    }
    corto = {
        "Entre semana (sin rupturas en fin de semana)": _entre_semana(d),
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


def _diario_alcista(d):
    return (d["cd"] > d["ema50_d"]) & (d["ema20_d"] > d["ema50_d"])


def _diario_bajista(d):
    return (d["cd"] < d["ema50_d"]) & (d["ema20_d"] < d["ema50_d"])


def cond_mtf(d):
    """Análisis de arriba abajo: diario y 4h marcan la dirección, 1h da la entrada."""
    toca50 = d["low"].rolling(5).min() <= d["ema50"] + 0.3 * d["atr"]
    toca50c = d["high"].rolling(5).max() >= d["ema50"] - 0.3 * d["atr"]
    largo = {
        "Diario alcista (precio y EMA20 sobre EMA50)": _diario_alcista(d),
        "4h alcista (sobre su EMA20 y EMA50)": (d["c4"] > d["ema20_4"]) & (d["ema20_4"] > d["ema50_4"]),
        "1h retrocedió hasta la EMA50": toca50,
        "RSI 1h recupera 50": (d["rsi"].shift() < 50) & (d["rsi"] >= 50),
        "Cierra sobre la EMA20 de 1h": d["close"] > d["ema20"],
    }
    corto = {
        "Diario bajista (precio y EMA20 bajo EMA50)": _diario_bajista(d),
        "4h bajista (bajo su EMA20 y EMA50)": (d["c4"] < d["ema20_4"]) & (d["ema20_4"] < d["ema50_4"]),
        "1h rebotó hasta la EMA50": toca50c,
        "RSI 1h pierde 50": (d["rsi"].shift() > 50) & (d["rsi"] <= 50),
        "Cierra bajo la EMA20 de 1h": d["close"] < d["ema20"],
    }
    return largo, corto


def cond_barrida(d):
    """Barrida de liquidez: el precio perfora el mínimo (máximo) del día anterior y vuelve."""
    rango = (d["high"] - d["low"]).replace(0, np.nan)
    largo = {
        "4h no bajista (sobre su EMA200)": d["c4"] > d["ema200_4"],
        "Perforó el mínimo de ayer": d["low"] < d["pdl"],
        "Cerró de vuelta sobre el mínimo de ayer": d["close"] > d["pdl"],
        "Cierre en la mitad alta de la vela": (d["close"] - d["low"]) / rango > 0.6,
    }
    corto = {
        "4h no alcista (bajo su EMA200)": d["c4"] < d["ema200_4"],
        "Perforó el máximo de ayer": d["high"] > d["pdh"],
        "Cerró de vuelta bajo el máximo de ayer": d["close"] < d["pdh"],
        "Cierre en la mitad baja de la vela": (d["high"] - d["close"]) / rango > 0.6,
    }
    return largo, corto


def cond_compresion(d):
    """Compresión de volatilidad (bandas de Bollinger estrechas) y ruptura con volumen."""
    estrecha = d["bb_pct"].rolling(6).min() < 0.15
    volumen = d["vol"] > 1.5 * d["vol_media"]
    largo = {
        "Entre semana (sin rupturas en fin de semana)": _entre_semana(d),
        "Diario no bajista": ~_diario_bajista(d),
        "Bandas muy estrechas hace poco": estrecha,
        "Cierra sobre la banda superior": d["close"] > d["bb_sup"],
        "Volumen 1.5x sobre su media": volumen,
    }
    corto = {
        "Entre semana (sin rupturas en fin de semana)": _entre_semana(d),
        "Diario no alcista": ~_diario_alcista(d),
        "Bandas muy estrechas hace poco": estrecha,
        "Cierra bajo la banda inferior": d["close"] < d["bb_inf"],
        "Volumen 1.5x sobre su media": volumen,
    }
    return largo, corto


def cond_zona(d):
    """Rebote en soporte/resistencia: zona con 2+ toques en 10 días, vela de rechazo y RSI agotado."""
    rango = (d["high"] - d["low"]).replace(0, np.nan)
    largo = {
        "Soporte con 2+ toques (10 días)": d["sop_toques"] >= 2,
        "Tocó el soporte": d["low"] <= d["sop"] + 0.25 * d["atr"],
        "Cerró sobre el soporte (no lo rompió)": d["close"] > d["sop"],
        "Vela de rechazo (cierre en la mitad alta)": (d["close"] - d["low"]) / rango > 0.6,
        "RSI agotado (< 40 en las últimas 3 velas)": d["rsi"].rolling(3).min() < 40,
    }
    corto = {
        "Resistencia con 2+ toques (10 días)": d["res_toques"] >= 2,
        "Tocó la resistencia": d["high"] >= d["res"] - 0.25 * d["atr"],
        "Cerró bajo la resistencia (no la rompió)": d["close"] < d["res"],
        "Vela de rechazo (cierre en la mitad baja)": (d["high"] - d["close"]) / rango > 0.6,
        "RSI agotado (> 60 en las últimas 3 velas)": d["rsi"].rolling(3).max() > 60,
    }
    return largo, corto


def cond_ruptura_viernes(d):
    """Candidata: la ruptura de rango solo los viernes (UTC). En el análisis por día ganó
    +0.19R en 556 operaciones, positiva en la parte antigua y en la reciente del año.
    Se valida igual que las demás; mientras no pase los filtros, solo se observa."""
    largo, corto = cond_ruptura(d)
    viernes = _dia_entrada(d) == 4
    largo = {"Es viernes": viernes, **{k: v for k, v in largo.items() if not k.startswith("Entre semana")}}
    corto = {"Es viernes": viernes, **{k: v for k, v in corto.items() if not k.startswith("Entre semana")}}
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
    "mtf": ("Arriba-abajo (D → 4h → 1h)", cond_mtf),
    "barrida": ("Barrida de liquidez", cond_barrida),
    "compresion": ("Compresión y ruptura", cond_compresion),
    "zona": ("Rebote en soporte/resistencia", cond_zona),
    "ruptura_viernes": ("Ruptura de rango · viernes", cond_ruptura_viernes),
}

ESTRATEGIAS = {k: (n, senal_desde(f)) for k, (n, f) in CONDICIONES.items()}
