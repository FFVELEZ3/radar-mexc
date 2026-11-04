"""Pruebas del ejecutor con un MEXC simulado (no envía órdenes reales).

    python -m tests.test_ejecutor
"""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import config as C
import ejecutor
import mexc_privado
from mexc_privado import ClienteMexc, ErrorMexc

AHORA = datetime(2026, 11, 3, 20, 2, tzinfo=timezone.utc)

try:
    import pytest

    @pytest.fixture(autouse=True)
    def _ordenes_permitidas(monkeypatch):
        """Estas pruebas cubren la operación real con un MEXC falso: habilitan el permiso solo aquí."""
        monkeypatch.setattr(C, "PERMITIR_ORDENES", True)
except ImportError:  # ejecución directa sin pytest
    pass


class MexcFalso:
    def __init__(self, saldo=100.0, minimo=1):
        self.saldo, self.minimo = saldo, minimo
        self.abiertas, self.cerradas, self.ordenes, self.cierres = [], [], [], []

    def detalle(self, simbolo):
        return {"tam": 0.0001, "min": self.minimo, "unidad": 1, "tick": 0.1, "max_apal": 125}

    def saldo_disponible(self):
        return self.saldo

    def posiciones(self):
        return self.abiertas

    def posiciones_cerradas(self, simbolo):
        return self.cerradas

    def orden_externa(self, simbolo, oid):
        o = next(o for o in self.ordenes if o["oid"] == oid)
        return {"dealAvgPrice": o["precio"], "positionId": o["pid"]}

    def abrir(self, simbolo, lado, vol, precio, apal, stop, objetivo, oid):
        pid = len(self.ordenes) + 1
        self.ordenes.append(dict(simbolo=simbolo, lado=lado, vol=vol, precio=precio, apal=apal,
                                 stop=stop, objetivo=objetivo, oid=oid, pid=pid))
        self.abiertas.append({"symbol": simbolo, "positionType": 1 if lado == 1 else 2,
                              "positionId": pid, "holdVol": vol, "liquidatePrice": 1})
        return pid

    def cerrar(self, simbolo, lado, vol, precio, pid, oid):
        self.cierres.append((simbolo, vol, pid))
        self.abiertas = [p for p in self.abiertas if p["positionId"] != pid]


def senal(par="BTC_USDT", lado=1, entrada=50000.0, atr=400.0, estado="activa", r=None, t=None, n=0):
    riesgo = C.ATR_STOP * atr
    s = {"id": f"{par}|x|{n}", "par": par, "clave": "ruptura", "nombre": "Ruptura", "lado": lado,
         "entrada": entrada, "stop": entrada - lado * riesgo,
         "objetivo": entrada + lado * riesgo * C.RATIO_BENEFICIO, "riesgo": riesgo, "atr": atr,
         "estado": estado}
    if r is not None:
        s.update(r=r, t_cierre=(t or AHORA).isoformat())
    return s


def historial(n, r):
    return [senal(estado="objetivo" if r > 0 else "stop", r=r, n=i,
                  t=AHORA - timedelta(hours=n - i)) for i in range(n)]


def test_firma():
    capturado = {}

    class Sesion:
        def request(self, metodo, url, headers, data, timeout):
            capturado.update(metodo=metodo, url=url, headers=headers, data=data)

            class R:
                status_code = 200
                def json(self):
                    return {"success": True, "code": 0, "data": 123}
            return R()

    c = ClienteMexc("CLAVE", "SECRETO", Sesion(), permitir_ordenes=True)
    c.abrir("BTC_USDT", 1, 3, 50000.0, 3, 49400.0, 51200.0, "rmabc")
    h = capturado["headers"]
    esperado = hmac.new(b"SECRETO", f"CLAVE{h['Request-Time']}{capturado['data']}".encode(),
                        hashlib.sha256).hexdigest()
    assert h["Signature"] == esperado and h["ApiKey"] == "CLAVE"
    cuerpo = json.loads(capturado["data"])
    assert cuerpo["side"] == 1 and cuerpo["type"] == 5 and cuerpo["openType"] == 1
    assert cuerpo["stopLossPrice"] == 49400.0 and cuerpo["leverage"] == 3
    c._privado("GET", "/api/v1/private/position/list/history_positions",
               {"symbol": "BTC_USDT", "page_size": 50, "page_num": 1})
    assert capturado["url"].endswith("?page_num=1&page_size=50&symbol=BTC_USDT")
    print("OK firma y formato de órdenes")


def test_modo():
    C.MODO = "auto"
    assert ejecutor.decidir_modo(historial(10, 0.5), True)[0] == "simulado"
    assert ejecutor.decidir_modo(historial(30, 0.5), True)[0] == "real"
    assert ejecutor.decidir_modo(historial(30, 0.5), False)[0] == "simulado"  # sin claves
    assert ejecutor.decidir_modo(historial(40, -0.1), True)[0] == "simulado"
    mezcla = historial(30, 1.0) + [senal(estado="stop", r=-1.0, n=100 + i,
                                         t=AHORA + timedelta(minutes=i)) for i in range(20)]
    modo, motivo, _ = ejecutor.decidir_modo(mezcla, True)
    assert modo == "simulado" and "Pausa" in motivo
    C.MODO = "simulado"
    assert ejecutor.decidir_modo(historial(50, 1.0), True)[0] == "simulado"
    C.MODO = "auto"
    print("OK cambio de modo por evidencia")


def test_apertura_y_frenos():
    C.MODO, C.RIESGO_POR_OPERACION_USD = "real", 1.0
    avisos = []
    m = MexcFalso()
    s1 = senal("BTC_USDT", n=1)
    sen = [s1]
    ejecutor.procesar(m, sen, [s1], {"BTC_USDT": 50000.0}, AHORA, avisos.append)
    o = m.ordenes[0]
    perdida = (abs(o["precio"] - o["stop"]) + ejecutor.COSTO_LADO * (o["precio"] + o["stop"])) * 0.0001 * o["vol"]
    assert s1["real"]["estado"] == "abierta" and perdida <= 1.0 and o["vol"] >= 1
    assert o["apal"] == C.APALANCAMIENTO

    s2 = senal("BTC_USDT", n=2)            # mismo par: no
    sen.append(s2)
    ejecutor.procesar(m, sen, [s2], {"BTC_USDT": 50000.0}, AHORA, avisos.append)
    assert s2["real"]["estado"] == "omitida"
    s3 = senal("ETH_USDT", n=3)
    s4 = senal("SOL_USDT", n=4)            # tercera posición: excede el máximo de 2
    sen += [s3, s4]
    ejecutor.procesar(m, sen, [s3, s4], {}, AHORA, avisos.append)
    assert s3["real"]["estado"] == "abierta" and s4["real"]["estado"] == "omitida"
    print("OK apertura, tamaño y máximo de posiciones")


def test_limite_diario_y_minimo():
    C.MODO = "real"
    m = MexcFalso()
    previas = []
    for i in range(2):
        s = senal(n=50 + i, estado="stop", r=-1.0)
        s["real"] = {"estado": "cerrada", "pnl": -1.2, "t_cierre": AHORA.isoformat()}
        previas.append(s)
    nueva = senal("XRP_USDT", n=60)
    ejecutor.procesar(m, previas + [nueva], [nueva], {}, AHORA, lambda t: None)
    assert nueva["real"]["estado"] == "omitida" and "diario" in nueva["real"]["motivo"]

    m2 = MexcFalso(minimo=1000)            # el mínimo obligaría a arriesgar de más
    s = senal(n=70)
    ejecutor.procesar(m2, [s], [s], {}, AHORA, lambda t: None)
    assert s["real"]["estado"] == "omitida" and not m2.ordenes

    m3 = MexcFalso(saldo=0.5)              # sin saldo
    s = senal(n=80)
    ejecutor.procesar(m3, [s], [s], {}, AHORA, lambda t: None)
    assert s["real"]["estado"] == "omitida" and "Saldo" in s["real"]["motivo"]

    s = senal(n=90)                         # precio ya se fue
    ejecutor.procesar(MexcFalso(), [s], [s], {"BTC_USDT": 50400.0}, AHORA, lambda t: None)
    assert s["real"]["estado"] == "omitida"
    print("OK límite diario, mínimo de contrato, saldo y precio alejado")


def test_conciliacion():
    C.MODO = "real"
    m = MexcFalso()
    s = senal(n=100)
    ejecutor.procesar(m, [s], [s], {}, AHORA, lambda t: None)
    # MEXC cerró la posición por stop
    pid = m.abiertas.pop()["positionId"]
    m.cerradas = [{"positionId": pid, "state": 3, "realised": -0.97, "holdFee": -0.01,
                   "closeAvgPrice": 49400}]
    ejecutor.procesar(m, [s], [], {}, AHORA + timedelta(hours=3), lambda t: None)
    assert s["real"]["estado"] == "cerrada" and abs(s["real"]["pnl"] + 0.98) < 1e-9

    # cierre por tiempo: el papel la cerró y la real sigue abierta
    m = MexcFalso()
    s = senal(n=101)
    ejecutor.procesar(m, [s], [s], {}, AHORA, lambda t: None)
    s["estado"] = "tiempo"
    ejecutor.procesar(m, [s], [], {"BTC_USDT": 50100.0}, AHORA + timedelta(hours=48), lambda t: None)
    assert m.cierres and s["real"].get("cierre_enviado")
    print("OK conciliación con MEXC y cierre por tiempo")


def test_error_mexc():
    C.MODO = "real"

    class Rechaza(MexcFalso):
        def abrir(self, *a):
            raise ErrorMexc("isolated margin not supported in unified mode", 600)
    avisos = []
    s = senal(n=200)
    ejecutor.procesar(Rechaza(), [s], [s], {}, AHORA, avisos.append)
    assert s["real"]["estado"] == "error" and any("Simple" in a for a in avisos)
    C.MODO = "auto"
    print("OK error de MEXC informado con solución")


if __name__ == "__main__":
    C.PERMITIR_ORDENES = True
    test_firma()
    test_modo()
    test_apertura_y_frenos()
    test_limite_diario_y_minimo()
    test_conciliacion()
    test_error_mexc()
