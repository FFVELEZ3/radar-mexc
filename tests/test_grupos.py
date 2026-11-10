"""Auditor de grupos: lectura de formatos reales y reglas de seguimiento."""
import grupos

P = {"BTC_USDT": 70000, "ETH_USDT": 2440, "ENA_USDT": 0.19, "FIL_USDT": 1.07, "CAP_USDT": 0.095}


def test_formatos_reales():
    s, _ = grupos.parsear("NUEVA SEÑAL CAP/USDT ( LONG ) Entrada 0.09448 Target :- 0.113617 (+20.26%) "
                          "Stoploss = 0.0849117 (−10.13%) Entrada válida hasta 0.0968721.", P)
    assert s["par"] == "CAP_USDT" and s["lado"] == 1 and s["objetivos"] == [0.113617]
    s, _ = grupos.parsear("FILUSDT | LONG\nEntrada: 1.0747\nStop Loss: 1.0513\nTP1: 1.0981\nTP2: 1.1145\nTP3: 1.1332", P)
    assert s["stop"] == 1.0513 and len(s["objetivos"]) == 3
    s, _ = grupos.parsear("Nuevo SHORT en BTC Entrada1: 69.836$ Entrada2: 70.000$ SL: 70.543$ TP1: 69.121$ TP2: 68.498$", P)
    assert s["entrada"] == 69836 and s["stop"] == 70543 and s["lado"] == -1   # punto de miles
    s, _ = grupos.parsear("Nuevo LONG en ENA Entrada1: 0,1901$ TP1: 0,1932$ TP2: 0,1966$ SL: 0,1868$", P)
    assert s["entrada"] == 0.1901
    assert grupos.parsear("FILUSDT – TP1 alcanzado. SL movido a BE.", P)[0] is None
    assert grupos.parsear("LONG #ETH Entrada 2440 SL 2460 TP 2500", P)[0] is None    # stop del lado equivocado


def test_reglas_de_seguimiento():
    s = {"lado": 1, "entrada": 100, "stop": 98, "objetivos": [102, 104], "t": 0}
    tp1_entrada = grupos.simular(s, [(0, 101, 101, 99.5, 100.5), (300, 100.5, 102.5, 100, 102), (600, 102, 102, 99.9, 100)], 1000)
    assert tp1_entrada["motivo"] == "tp1_y_entrada" and 0.3 < tp1_entrada["r"] < 0.5
    todo = grupos.simular(s, [(0, 101, 101, 99.5, 100.5), (300, 100.5, 104.5, 100, 104)], 1000)
    assert todo["motivo"] == "objetivo" and 1.3 < todo["r"] < 1.5
    misma_vela = grupos.simular(s, [(0, 101, 104.5, 97, 98)], 1000)          # stop y objetivo juntos: stop
    assert misma_vela["motivo"] == "stop" and misma_vela["r"] < -1
    nunca = grupos.simular({**s, "entrada": 90, "stop": 88}, [(0, 101, 101, 99.5, 100.5)], 30 * 3600)
    assert nunca["estado"] == "no_activada"


def test_laboratorio_sin_mirar_al_futuro():
    import lab
    from tests.test_motor import velas_simuladas
    v = velas_simuladas(n=1200, semilla=5)
    base = lab.preparar(v)
    alt = v.copy()
    alt.iloc[-200:, :4] *= 1.4
    nuevo = lab.preparar(alt)
    corte = v.index[-201]
    for k, (_, f) in lab.LAB.items():
        assert (f(base).loc[:corte] == f(nuevo).loc[:corte]).all(), f"{k} usa datos futuros"
