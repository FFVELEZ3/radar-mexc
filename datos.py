"""Descarga de datos públicos de futuros de MEXC (no requiere claves ni cuenta)."""
import time

import pandas as pd
import requests

BASE = "https://contract.mexc.com/api/v1/contract"
HORA = 3600
VELAS_POR_PEDIDO = 1500  # el API entrega como máximo ~2000 velas por consulta

_sesion = requests.Session()
_sesion.headers["User-Agent"] = "senales-mexc/1.0"


class ErrorDatos(Exception):
    pass


def _get(url, params=None, intentos=3):
    ultimo = None
    for i in range(intentos):
        try:
            r = _sesion.get(url, params=params, timeout=20)
            if r.status_code != 200:
                raise ErrorDatos(f"HTTP {r.status_code} en {url}: {r.text[:200]}")
            datos = r.json()
            if not datos.get("success", False):
                raise ErrorDatos(f"Respuesta sin éxito en {url}: {str(datos)[:200]}")
            return datos["data"]
        except (requests.RequestException, ValueError, ErrorDatos) as e:
            ultimo = e
            time.sleep(1.5 * (i + 1))
    raise ErrorDatos(str(ultimo))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def tickers():
    """Precio, variación 24 h, volumen y funding de todos los perpetuos USDT."""
    salida = {}
    for t in _get(f"{BASE}/ticker"):
        simbolo = t.get("symbol", "")
        if simbolo.endswith("_USDT"):
            salida[simbolo] = {
                "precio": _f(t.get("lastPrice")),
                "cambio24": _f(t.get("riseFallRate")),   # fracción, 0.012 = +1.2 %
                "volumen24": _f(t.get("amount24")),      # en USDT
                "funding": _f(t.get("fundingRate")),
            }
    return salida


def pares_top(n, excluir=(), info=None):
    """Contratos perpetuos USDT con mayor volumen negociado en 24 h (en USDT)."""
    info = info if info is not None else tickers()
    filas = [(s, v["volumen24"]) for s, v in info.items() if s not in excluir]
    filas.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in filas[:n]]


def velas_1h(simbolo, dias):
    """Velas de 1 hora cerradas, índice = hora de apertura en UTC."""
    ahora = int(time.time())
    inicio = ahora - int(dias * 86400)
    partes = []
    desde = inicio
    while desde < ahora:
        hasta = min(desde + VELAS_POR_PEDIDO * HORA, ahora)
        d = _get(f"{BASE}/kline/{simbolo}", {"interval": "Min60", "start": desde, "end": hasta})
        if d and d.get("time"):
            partes.append(pd.DataFrame({
                "time": d["time"], "open": d["open"], "high": d["high"],
                "low": d["low"], "close": d["close"], "vol": d["vol"],
            }))
        desde = hasta
        time.sleep(0.15)
    if not partes:
        raise ErrorDatos(f"Sin velas para {simbolo}")
    df = pd.concat(partes).drop_duplicates("time").sort_values("time")
    df = df[df["time"] + HORA <= ahora]  # solo velas cerradas
    df.index = pd.to_datetime(df["time"], unit="s", utc=True)
    return df[["open", "high", "low", "close", "vol"]].astype(float)
