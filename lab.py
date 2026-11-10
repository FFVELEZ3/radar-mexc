"""Laboratorio de estrategias clásicas publicadas, en velas diarias y de 4 horas.

Prueba con sus reglas de entrada conocidas (sin ajustar parámetros a estos datos):
  - Tortugas / Donchian 20 (Richard Dennis): ruptura del máximo/mínimo de 20 velas.
  - Tortugas sistema 2 / Donchian 55.
  - SuperTrend (10, 3): cambio de dirección del SuperTrend.
  - Cruce de medias 50/200 ("cruce dorado").
  - Ichimoku: cierre que sale de la nube con Tenkan > Kijun.
  - MACD + EMA200: cruce del MACD a favor de la tendencia de largo plazo.
  - RSI-2 de Connors: RSI(2) < 10 sobre la SMA200 (y espejo en corto).
  - Bandas de Bollinger: vuelta adentro desde fuera de la banda, a favor de la SMA200.
Cada una se mide con las mismas salidas del radar (fija a 2R y de tendencia), stop a
1.5 ATR, comisiones de operación manual, sumando todos los pares, y separando el
70 % antiguo del 30 % reciente. Así se comparan entre sí y con las de 1 hora.
"""
import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

import config as C
from backtest import metricas, simular

RUTA = os.path.join(C.DIR_DATOS, "lab.json")
KLINE = "https://contract.mexc.com/api/v1/contract/kline/{}"
MARCOS = {"1D": ("Day1", 86400, 1500), "4H": ("Hour4", 14400, 1500),
          "5m": ("Min5", 300, 1900), "1m": ("Min1", 60, 1900)}
DIAS = {"1D": 1460, "4H": 730, "5m": 60, "1m": 14}
# Scalping: con orden a mercado se paga taker + deslizamiento; con orden límite (maker) casi nada.
# El escenario "límite" es optimista en un punto: supone que la orden se llena siempre.
COSTO_LIMITE = 0.0002   # 0.01 % maker + 0.01 % de margen por las salidas a mercado en el stop
SCALPING = ["donchian20", "supertrend", "bollinger", "rsi2", "ema9_21", "macd"]
HORAS_CACHE = 24


def velas(par, marco, dias):
    intervalo, seg, lote = MARCOS[marco]
    ahora = int(time.time())
    ini, filas = ahora - dias * 86400, []
    while ini < ahora:
        fin = min(ini + lote * seg, ahora)
        r = requests.get(KLINE.format(par), params={"interval": intervalo, "start": ini, "end": fin}, timeout=25)
        d = r.json()
        if d.get("success") and d["data"].get("time"):
            k = d["data"]
            filas += list(zip(k["time"], k["open"], k["high"], k["low"], k["close"], k["vol"]))
        ini = fin
        time.sleep(0.12)
    if not filas:
        return None
    df = pd.DataFrame(filas, columns=["t", "open", "high", "low", "close", "vol"]).drop_duplicates("t").sort_values("t")
    df = df[df["t"] + seg <= ahora]
    df.index = pd.to_datetime(df["t"], unit="s", utc=True)
    return df.drop(columns="t").astype(float)


# ---------- indicadores ----------

def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _atr(d, n=14):
    pc = d["close"].shift()
    tr = pd.concat([d["high"] - d["low"], (d["high"] - pc).abs(), (d["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _rsi(s, n):
    dlt = s.diff()
    up, dn = dlt.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-dlt.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _supertrend(d, n=10, m=3.0):
    atr = _atr(d, n)
    med = (d["high"] + d["low"]) / 2
    sup, inf = (med + m * atr).to_numpy(), (med - m * atr).to_numpy()
    c = d["close"].to_numpy()
    dir_ = np.ones(len(d))
    fs, fi = sup.copy(), inf.copy()
    for i in range(1, len(d)):
        fs[i] = sup[i] if (sup[i] < fs[i - 1] or c[i - 1] > fs[i - 1]) else fs[i - 1]
        fi[i] = inf[i] if (inf[i] > fi[i - 1] or c[i - 1] < fi[i - 1]) else fi[i - 1]
        dir_[i] = 1 if c[i] > fs[i - 1] else -1 if c[i] < fi[i - 1] else dir_[i - 1]
    return pd.Series(dir_, index=d.index)


def preparar(d):
    d = d.copy()
    d["atr"] = _atr(d)
    return d


def _senal(largo, corto):
    s = pd.Series(0, index=largo.index)
    s[largo.fillna(False)] = 1
    s[corto.fillna(False)] = -1
    return s


# ---------- estrategias (reglas publicadas, parámetros estándar) ----------

def donchian(d, n):
    c = d["close"]
    return _senal(c > d["high"].rolling(n).max().shift(), c < d["low"].rolling(n).min().shift())


def supertrend(d):
    st = _supertrend(d)
    return _senal((st == 1) & (st.shift() == -1), (st == -1) & (st.shift() == 1))


def cruce_medias(d):
    f, l = d["close"].rolling(50).mean(), d["close"].rolling(200).mean()
    return _senal((f > l) & (f.shift() <= l.shift()), (f < l) & (f.shift() >= l.shift()))


def ichimoku(d):
    h, l, c = d["high"], d["low"], d["close"]
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    a = ((tenkan + kijun) / 2).shift(26)
    b = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    techo, piso = pd.concat([a, b], axis=1).max(axis=1), pd.concat([a, b], axis=1).min(axis=1)
    return _senal((c > techo) & (c.shift() <= techo.shift()) & (tenkan > kijun),
                  (c < piso) & (c.shift() >= piso.shift()) & (tenkan < kijun))


def macd_ema200(d):
    c = d["close"]
    m = _ema(c, 12) - _ema(c, 26)
    sg = _ema(m, 9)
    e = _ema(c, 200)
    return _senal((m > sg) & (m.shift() <= sg.shift()) & (c > e), (m < sg) & (m.shift() >= sg.shift()) & (c < e))


def rsi2(d):
    c, sma = d["close"], d["close"].rolling(200).mean()
    r = _rsi(c, 2)
    return _senal((r < 10) & (c > sma), (r > 90) & (c < sma))


def bollinger(d):
    c = d["close"]
    m, s = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    sup, inf, sma = m + 2 * s, m - 2 * s, c.rolling(200).mean()
    return _senal((c.shift() < inf.shift()) & (c > inf) & (c > sma), (c.shift() > sup.shift()) & (c < sup) & (c < sma))


def ema9_21(d):
    c = d["close"]
    f, l, e = _ema(c, 9), _ema(c, 21), _ema(c, 200)
    return _senal((f > l) & (f.shift() <= l.shift()) & (c > e), (f < l) & (f.shift() >= l.shift()) & (c < e))


LAB = {
    "donchian20": ("Tortugas · Donchian 20", lambda d: donchian(d, 20)),
    "donchian55": ("Tortugas S2 · Donchian 55", lambda d: donchian(d, 55)),
    "supertrend": ("SuperTrend (10, 3)", supertrend),
    "medias": ("Cruce de medias 50/200", cruce_medias),
    "ichimoku": ("Ichimoku · salida de la nube", ichimoku),
    "macd": ("MACD + EMA200", macd_ema200),
    "rsi2": ("RSI-2 de Connors", rsi2),
    "bollinger": ("Vuelta desde Bollinger", bollinger),
    "ema9_21": ("Cruce EMA 9/21 + EMA200 (scalping)", ema9_21),
}


def _medir(clave, nombre, marco, modo, costo, datos, f):
    import salidas
    previo = salidas.COSTO_LADO
    if costo == "límite":
        salidas.COSTO_LADO = COSTO_LIMITE
    try:
        todas = []
        for par, d in datos.items():
            o = simular(d, f(d), modo)
            if len(o):
                o["par"] = par
                todas.append(o)
    finally:
        salidas.COSTO_LADO = previo
    if not todas:
        return None
    ops = pd.concat(todas)
    t = pd.DatetimeIndex(ops["entrada_t"])
    corte = t.min() + (t.max() - t.min()) * C.FRACCION_EN_MUESTRA
    mt, mi, mo = metricas(ops), metricas(ops[t < corte]), metricas(ops[t >= corte])
    por_par = ops.groupby("par")["r"].mean()
    dias = max((t.max() - t.min()).days, 1)
    return {
        "clave": clave, "nombre": nombre, "marco": marco, "gestion": modo, "costo": costo, "pares": len(datos),
        "n": mt["n"], "por_año": round(mt["n"] / dias * 365), "por_dia": round(mt["n"] / dias, 1),
        "acierto": round(mt["acierto"], 3), "exp_r": round(mt["exp_r"], 3), "t": round(mt["t"], 2),
        "exp_ins": round(mi["exp_r"], 3), "exp_oos": round(mo["exp_r"], 3), "n_oos": mo["n"],
        "t_oos": round(mo["t"], 2), "pares_positivos": int((por_par > 0).sum()), "desde": t.min().isoformat()[:10],
        "pasa": bool(mt["t"] >= 2.5 and mi["exp_r"] > 0 and mo["exp_r"] > 0 and mo["n"] >= 50 and mo["t"] >= 1.5),
    }


def correr(pares):
    resultados = []
    for marco in MARCOS:
        datos = {}
        for par in pares:
            try:
                v = velas(par, marco, DIAS[marco])
                if v is not None and len(v) >= 250:
                    datos[par] = preparar(v)
            except Exception as e:  # par sin historial suficiente o MEXC caído
                print(f"[lab] {par} {marco}: {e}")
        corto = marco in ("5m", "1m")
        for clave, (nombre, f) in LAB.items():
            if corto and clave not in SCALPING:
                continue
            for modo in ("fija", "tendencia"):
                for costo in (("mercado", "límite") if corto else ("mercado",)):
                    r = _medir(clave, nombre, marco, modo, costo, datos, f)
                    if r:
                        resultados.append(r)
    resultados.sort(key=lambda x: -x["t"])
    return resultados


def actualizar(pares, forzar=False):
    """Recalcula como mucho una vez al día (descarga varios años de velas)."""
    try:
        with open(RUTA, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = None
    ahora = datetime.now(timezone.utc)
    if prev and not forzar:
        edad = (ahora - datetime.fromisoformat(prev["generado"])).total_seconds() / 3600
        if edad < HORAS_CACHE and prev.get("version") == 2:
            return prev
    res = {"generado": ahora.isoformat(), "version": 2, "pares": pares, "resultados": correr(pares)}
    os.makedirs(os.path.dirname(RUTA), exist_ok=True)
    with open(RUTA, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    return res
