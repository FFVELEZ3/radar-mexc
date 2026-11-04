"""Indicadores técnicos (mismas fórmulas que TradingView: medias de Wilder)."""
import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _wilder(s, n):
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close, n=14):
    delta = close.diff()
    ganancia = _wilder(delta.clip(lower=0), n)
    perdida = _wilder(-delta.clip(upper=0), n)
    rs = ganancia / perdida.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def atr(df, n=14):
    prev = df["close"].shift()
    rango = pd.concat([
        df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()
    ], axis=1).max(axis=1)
    return _wilder(rango, n)


def adx(df, n=14):
    sube = df["high"].diff()
    baja = -df["low"].diff()
    dm_mas = np.where((sube > baja) & (sube > 0), sube, 0.0)
    dm_menos = np.where((baja > sube) & (baja > 0), baja, 0.0)
    rango = atr(df, n)
    di_mas = 100 * _wilder(pd.Series(dm_mas, index=df.index), n) / rango
    di_menos = 100 * _wilder(pd.Series(dm_menos, index=df.index), n) / rango
    dx = 100 * (di_mas - di_menos).abs() / (di_mas + di_menos).replace(0, np.nan)
    return _wilder(dx.fillna(0), n)


def tendencia_4h(df1h):
    """Tendencia en 4h, alineada al 1h sin mirar al futuro.

    Una vela de 4h solo se usa cuando ya cerró: su valor queda disponible
    desde la hora de cierre de esa vela.
    """
    agg = df1h.resample("4h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "vol": "count"})
    agg = agg[agg["vol"] == 4]  # solo bloques completos de 4 velas
    t = pd.DataFrame(index=agg.index + pd.Timedelta(hours=4))  # disponible al cierre
    t["c4"] = agg["close"].values
    t["ema50_4"] = ema(agg["close"], 50).values
    t["ema200_4"] = ema(agg["close"], 200).values
    cierre_1h = df1h.index + pd.Timedelta(hours=1)
    alineado = pd.merge_asof(
        pd.DataFrame({"k": cierre_1h}), t.reset_index(names="k"),
        on="k", direction="backward")
    alineado.index = df1h.index
    return alineado[["c4", "ema50_4", "ema200_4"]]


def _alinear(df1h, t, cols):
    cierre_1h = df1h.index + pd.Timedelta(hours=1)
    al = pd.merge_asof(pd.DataFrame({"k": cierre_1h}), t.reset_index(names="k"),
                       on="k", direction="backward")
    al.index = df1h.index
    return al[cols]


def marco_diario(df1h):
    """Velas diarias (UTC) alineadas al 1h sin mirar al futuro: cada día se usa cuando ya cerró."""
    agg = df1h.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "vol": "count"})
    agg = agg[agg["vol"] >= 23]
    t = pd.DataFrame(index=agg.index + pd.Timedelta(days=1))
    t["cd"] = agg["close"].values
    t["ema20_d"] = ema(agg["close"], 20).values
    t["ema50_d"] = ema(agg["close"], 50).values
    t["pdh"] = agg["high"].values     # máximo del día anterior
    t["pdl"] = agg["low"].values      # mínimo del día anterior
    return _alinear(df1h, t, ["cd", "ema20_d", "ema50_d", "pdh", "pdl"])


def marco_4h_extra(df1h):
    agg = df1h.resample("4h", label="left", closed="left").agg(
        {"close": "last", "vol": "count"})
    agg = agg[agg["vol"] == 4]
    t = pd.DataFrame(index=agg.index + pd.Timedelta(hours=4))
    t["ema20_4"] = ema(agg["close"], 20).values
    t["rsi4"] = rsi(agg["close"]).values
    return _alinear(df1h, t, ["ema20_4", "rsi4"])


def preparar(df):
    df = df.copy()
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["rsi"] = rsi(df["close"])
    df["atr"] = atr(df)
    df["adx"] = adx(df)
    df["max20"] = df["high"].rolling(20).max().shift()
    df["min20"] = df["low"].rolling(20).min().shift()
    df = df.join(tendencia_4h(df))
    df = df.join(marco_4h_extra(df)).join(marco_diario(df))
    media = df["close"].rolling(20).mean()
    desv = df["close"].rolling(20).std(ddof=0)
    df["bb_sup"], df["bb_inf"] = media + 2 * desv, media - 2 * desv
    df["bb_ancho"] = (4 * desv / media)
    df["bb_pct"] = df["bb_ancho"].rolling(120).rank(pct=True)
    df["vol_media"] = df["vol"].rolling(20).mean().shift()
    return df
