"""Pruebas con datos simulados (no necesitan internet).

Ejecutar desde la carpeta del proyecto:  python -m tests.test_motor
"""
import json
import os
import tempfile

os.environ.setdefault("DIR_DATOS", tempfile.mkdtemp())

import numpy as np
import pandas as pd

import backtest
import config as C
import datos
import main
import seguimiento
from estrategias import ESTRATEGIAS
from indicadores import preparar


def velas_simuladas(n=8760, semilla=1, inicio=30000.0, fin=None):
    rng = np.random.default_rng(semilla)
    deriva = np.repeat(rng.normal(0, 0.0006, n // 500 + 1), 500)[:n]  # regímenes de tendencia
    ret = deriva + rng.normal(0, 0.006, n)
    close = inicio * np.exp(np.cumsum(ret))
    open_ = np.r_[inicio, close[:-1]]
    rango = np.abs(rng.normal(0, 0.004, n)) * close
    high = np.maximum(open_, close) + rango
    low = np.minimum(open_, close) - rango
    fin = fin or pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=1)
    idx = pd.date_range(end=fin, periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "vol": 1.0}, index=idx)


def test_sin_mirar_al_futuro():
    df = velas_simuladas()
    base = preparar(df)
    alterado = df.copy()
    alterado.iloc[-300:, :4] *= 1.5  # cambiar el futuro no debe cambiar el pasado
    nuevo = preparar(alterado)
    corte = df.index[-301]
    for clave, (_, f) in ESTRATEGIAS.items():
        assert (f(base).loc[:corte] == f(nuevo).loc[:corte]).all(), f"{clave} usa datos futuros"
    cols = ["c4", "ema50_4", "ema200_4", "ema20", "rsi", "atr"]
    pd.testing.assert_frame_equal(base.loc[:corte, cols], nuevo.loc[:corte, cols])
    print("OK sin mirar al futuro")


def test_simulacion_manual():
    idx = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
    d = pd.DataFrame({
        "open":  [100, 100, 101, 102, 104],
        "high":  [101, 101, 102, 104.5, 105],
        "low":   [99, 99.5, 100.5, 101.5, 103],
        "close": [100, 101, 102, 104, 104.5],
        "atr":   [1.0] * 5,
    }, index=idx)
    senal = pd.Series([1, 0, 0, 0, 0], index=idx)
    op = backtest.simular(d, senal).iloc[0]
    assert op["motivo"] == "objetivo" and op["salida"] == 103
    costo = (C.COMISION_TAKER + C.DESLIZAMIENTO) * (100 + 103)
    assert abs(op["r"] - (3 - costo) / 1.5) < 1e-9
    d2 = d.copy()
    d2.iloc[2, d2.columns.get_loc("low")] = 98
    d2.iloc[2, d2.columns.get_loc("high")] = 104
    assert backtest.simular(d2, senal).iloc[0]["motivo"] == "stop"

    # el seguimiento real usa las mismas reglas que el backtest
    s = {"par": "X", "lado": 1, "entrada": 100.0, "stop": 98.5, "objetivo": 103.0,
         "riesgo": 1.5, "t_entrada": idx[1].isoformat(), "estado": "activa"}
    seguimiento.actualizar([s], {"X": d}, {})
    assert s["estado"] == "objetivo" and abs(s["r"] - op["r"]) < 1e-3
    print("OK simulación y seguimiento")


def test_flujo_completo():
    semillas = {"BTC_USDT": 1, "ETH_USDT": 2, "SOL_USDT": 3}
    datos.tickers = lambda: {p: {"precio": 0, "cambio24": 0.01, "volumen24": 1e9 - i,
                                 "funding": 0.0001} for i, p in enumerate(semillas)}
    datos.velas_1h = lambda par, dias: velas_simuladas(semilla=semillas[par])
    main.telegram.enviar = lambda t: True
    main.ejecutar()
    with open(main.RUTA_PANEL, encoding="utf-8") as f:
        panel = json.load(f)
    assert len(panel["pares"]) == 3 and len(panel["backtest"]) == 9
    assert all(len(p["velas"]) == 168 for p in panel["pares"])
    main.ejecutar()  # una segunda corrida no duplica señales
    with open(main.RUTA_SENALES, encoding="utf-8") as f:
        ids = [s["id"] for s in json.load(f)["senales"]]
    assert len(ids) == len(set(ids))
    print("OK flujo completo")


if __name__ == "__main__":
    test_sin_mirar_al_futuro()
    test_simulacion_manual()
    test_flujo_completo()
