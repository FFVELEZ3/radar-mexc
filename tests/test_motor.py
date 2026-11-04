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
    cols = ["c4", "ema50_4", "ema200_4", "ema20", "rsi", "atr", "cd", "ema50_d", "pdh", "pdl", "ema20_4", "bb_pct", "sop", "sop_toques", "res", "res_toques"]
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
    op = backtest.simular(d, senal, "fija").iloc[0]
    assert op["motivo"] == "objetivo" and op["salida"] == 103
    costo = (C.COMISION_TAKER + C.DESLIZAMIENTO) * (100 + 103)
    assert abs(op["r"] - (3 - costo) / 1.5) < 1e-9
    d2 = d.copy()
    d2.iloc[2, d2.columns.get_loc("low")] = 98
    d2.iloc[2, d2.columns.get_loc("high")] = 104
    assert backtest.simular(d2, senal).iloc[0]["motivo"] == "stop"
    # escalonada: TP1 101.5 (50 %), TP2 103 (30 %), TP3 104.5 (20 %)
    op = backtest.simular(d, senal, "escalonada").iloc[0]
    assert op["motivo"] == "objetivo" and op["tps"] == 3
    assert abs(op["salida"] - (0.5 * 101.5 + 0.3 * 103 + 0.2 * 104.5)) < 1e-9

    # el seguimiento real usa las mismas reglas que el backtest
    s = {"par": "X", "lado": 1, "entrada": 100.0, "stop": 98.5, "objetivo": 103.0,
         "riesgo": 1.5, "gestion": "escalonada", "t_entrada": idx[1].isoformat(), "estado": "activa"}
    seguimiento.actualizar([s], {"X": d}, {})
    assert s["estado"] == "objetivo" and abs(s["r"] - op["r"]) < 1e-3
    print("OK simulación y seguimiento")


def test_escalonada_protegida_y_prudencia():
    from salidas import Posicion, COSTO_LADO
    # Toca TP1 y luego vuelve a la entrada: la mitad gana 1R, el resto sale cubriendo comisiones
    p = Posicion(1, 100.0, 98.5, 1.5, "escalonada")
    # en la misma vela toca TP1 y vuelve bajo la entrada: se asume que tocó el stop protegido
    assert p.vela(100, 101.6, 99.8, 101) and p.motivo == "protegida" and 0.4 < p.r() < 0.5
    p2 = Posicion(1, 100.0, 98.5, 1.5, "escalonada")
    assert not p2.vela(100, 101.6, 100.3, 101)    # TP1 sin volver a la entrada
    assert p2.hechos == 1 and abs(p2.stop - (100 + COSTO_LADO * 200)) < 1e-9
    assert p2.vela(101, 101.2, 100.0, 100.1)       # vuelve a la entrada: cierre protegido
    assert p2.motivo == "protegida" and p2.r() > 0.4
    # Stop y TP1 en la misma vela: cuenta como stop
    p3 = Posicion(1, 100.0, 98.5, 1.5, "escalonada")
    assert p3.vela(100, 101.6, 98.0, 100) and p3.motivo == "stop" and p3.r() < -1



def test_flujo_completo():
    semillas = {"BTC_USDT": 1, "ETH_USDT": 2, "SOL_USDT": 3}
    datos.tickers = lambda: {p: {"precio": 0, "cambio24": 0.01, "volumen24": 1e9 - i,
                                 "funding": 0.0001} for i, p in enumerate(semillas)}
    datos.velas_1h = lambda par, dias: velas_simuladas(semilla=semillas[par])
    main.telegram.enviar = lambda t: True
    main.ejecutar()
    with open(main.RUTA_PANEL, encoding="utf-8") as f:
        panel = json.load(f)
    assert len(panel["pares"]) == 3 and len(panel["backtest"]) == 3 * len(ESTRATEGIAS)
    assert all(len(p["velas"]) == 336 and len(p["velas"][0]) == 6 for p in panel["pares"])
    assert all("plan" in e for p in panel["pares"] for e in p["estrategias"])
    main.ejecutar()  # una segunda corrida no duplica señales
    with open(main.RUTA_SENALES, encoding="utf-8") as f:
        ids = [s["id"] for s in json.load(f)["senales"]]
    assert len(ids) == len(set(ids))
    print("OK flujo completo")


if __name__ == "__main__":
    test_sin_mirar_al_futuro()
    test_simulacion_manual()
    test_flujo_completo()


def test_solo_lectura_bloquea_ordenes():
    import ejecutor
    from mexc_privado import ClienteMexc, ErrorMexc

    class SesionFalsa:
        def __init__(self): self.llamadas = []
        def request(self, metodo, url, **kw):
            self.llamadas.append((metodo, url))
            class R:
                status_code = 200
                def json(self_):
                    if "asset" in url:
                        return {"success": True, "data": {"availableBalance": 50, "equity": 60, "unrealized": -1.5, "positionMargin": 10}}
                    return {"success": True, "data": [{"symbol": "BTC_USDT", "positionType": 2, "holdVol": 3, "holdAvgPrice": 70000, "leverage": 5, "liquidatePrice": 80000}]}
            return R()

    ses = SesionFalsa()
    cli = ClienteMexc("k", "s", sesion=ses)              # por defecto NO permite órdenes
    for accion in (lambda: cli.abrir("BTC_USDT", 1, 1, 1, 3, 0.9, 1.1, "x"),
                   lambda: cli.cerrar("BTC_USDT", 1, 1, 1, 1, "x")):
        try:
            accion(); assert False, "debió bloquear la orden"
        except ErrorMexc as e:
            assert "solo lectura" in str(e)
    assert not any(m == "POST" for m, _ in ses.llamadas)  # nunca llegó a enviar nada
    con = ejecutor.leer_cuenta(cli)
    assert con["ok"] and con["patrimonio"] == 60 and con["posiciones"][0]["lado"] == -1
    assert C.PERMITIR_ORDENES is False
    modo, _, _ = ejecutor.decidir_modo([], True)
    assert modo in ("lectura", "simulado", "apagado")    # con claves y sin permiso, jamás "real"
    assert not any(m == "POST" for m, _ in ses.llamadas)
