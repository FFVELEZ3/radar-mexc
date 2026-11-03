"""Genera datos de DEMOSTRACIÓN para ver el panel sin conexión a MEXC.

Simula el paso de los días hora por hora con el mismo motor real, así que las
señales, su seguimiento y el historial salen del código que corre en producción.
Los precios son inventados: el panel muestra un aviso de "Datos de demostración".

    python -m tests.demo docs/data
"""
import os
import sys

destino = sys.argv[1] if len(sys.argv) > 1 else "docs/data"
os.environ["DIR_DATOS"] = destino

import numpy as np
import pandas as pd

import datos
import main
from tests.test_motor import velas_simuladas

PARES = {  # par: (precio inicial aproximado, semilla)
    "BTC_USDT": (52000, 3), "ETH_USDT": (2400, 2), "SOL_USDT": (140, 7),
    "XRP_USDT": (0.52, 11), "DOGE_USDT": (0.11, 5), "SUI_USDT": (1.6, 13),
    "BNB_USDT": (560, 17), "PEPE_USDT": (0.0000095, 19), "LINK_USDT": (13.5, 23),
    "ADA_USDT": (0.36, 29),
}
DIAS_SIMULADOS = 10

fin = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=1)
series = {}
for p, (px, s) in PARES.items():
    v = velas_simuladas(semilla=s, inicio=px, fin=fin)
    v[["open", "high", "low", "close"]] *= px / v["close"].iloc[-1]  # termina en un precio realista
    series[p] = v
corte = {"t": fin}


def velas(par, dias):
    d = series[par]
    return d[d.index <= corte["t"]].iloc[-int(dias * 24):]


def tickers():
    out = {}
    for i, (p, d) in enumerate(series.items()):
        v = d[d.index <= corte["t"]]
        out[p] = {"precio": float(v["close"].iloc[-1]),
                  "cambio24": float(v["close"].iloc[-1] / v["close"].iloc[-25] - 1),
                  "volumen24": 5e9 / (i + 1), "funding": 0.0001 * np.sin(i)}
    return out


datos.velas_1h = velas
datos.tickers = tickers
main.telegram.enviar = lambda t: True
# MEXC simulado: permite ver cómo el bot decide entre papel y real sin enviar órdenes
from tests.test_ejecutor import MexcFalso
falso = MexcFalso(saldo=50.0)
main.crear_cliente = lambda: falso
for f in ("senales.json", "datos.json"):
    try:
        os.remove(os.path.join(destino, f))
    except OSError:
        pass

horas = pd.date_range(end=fin, periods=DIAS_SIMULADOS * 24, freq="h", tz="UTC")
for i, h in enumerate(horas):
    corte["t"] = h
    ultima = i == len(horas) - 1
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        main.ejecutar(ahora=h + pd.Timedelta(hours=1, minutes=2), demo=True)
    # el MEXC simulado ejecuta el stop o el objetivo cuando el seguimiento los detecta
    import json as _j
    for s in _j.load(open(main.RUTA_SENALES, encoding="utf-8"))["senales"]:
        real = s.get("real") or {}
        if real.get("estado") == "abierta" and s["estado"] in ("objetivo", "stop"):
            pid = real.get("position_id")
            if any(p["positionId"] == pid for p in falso.abiertas):
                falso.abiertas = [p for p in falso.abiertas if p["positionId"] != pid]
                falso.cerradas.append({"positionId": pid, "state": 3, "holdFee": 0,
                                       "realised": s["r"] * real["riesgo_usd"],
                                       "closeAvgPrice": s["salida"]})
    if i % 24 == 0:
        print(f"día {i // 24 + 1}/{DIAS_SIMULADOS}")
print("Listo:", os.path.join(destino, "datos.json"))
