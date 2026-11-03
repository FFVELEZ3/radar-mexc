"""Cliente del API privado de futuros de MEXC (órdenes y posiciones).

Firma según la documentación oficial y la implementación de ccxt:
    Signature = HMAC-SHA256(secret, apiKey + Request-Time + parámetros)  en hexadecimal
    GET:  parámetros ordenados alfabéticamente y unidos con &
    POST: el cuerpo JSON exacto que se envía
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import requests

BASE = "https://contract.mexc.com"


class ErrorMexc(Exception):
    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo


def firma(api_key, secret, marca_tiempo, parametros):
    texto = f"{api_key}{marca_tiempo}{parametros}"
    return hmac.new(secret.encode(), texto.encode(), hashlib.sha256).hexdigest()


class ClienteMexc:
    def __init__(self, api_key, secret, sesion=None):
        self.api_key, self.secret = api_key, secret
        self.s = sesion or requests.Session()
        self._detalles = {}

    # ---------- transporte ----------
    def _privado(self, metodo, ruta, params=None):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        ts = str(int(time.time() * 1000))
        if metodo == "GET":
            cadena = urlencode(sorted(params.items()))
            url = f"{BASE}{ruta}" + (f"?{cadena}" if cadena else "")
            cuerpo = None
        else:
            cadena = json.dumps(params, separators=(",", ":"))
            url, cuerpo = f"{BASE}{ruta}", cadena
        cab = {"ApiKey": self.api_key, "Request-Time": ts, "Recv-Window": "30",
               "Signature": firma(self.api_key, self.secret, ts, cadena),
               "Content-Type": "application/json"}
        r = self.s.request(metodo, url, headers=cab, data=cuerpo, timeout=20)
        try:
            datos = r.json()
        except ValueError:
            raise ErrorMexc(f"HTTP {r.status_code}: {r.text[:200]}")
        if not datos.get("success"):
            raise ErrorMexc(f"{datos.get('message') or datos}", datos.get("code"))
        return datos.get("data")

    def _publico(self, ruta):
        r = self.s.get(f"{BASE}{ruta}", timeout=20)
        datos = r.json()
        if not datos.get("success"):
            raise ErrorMexc(str(datos)[:200], datos.get("code"))
        return datos["data"]

    # ---------- consultas ----------
    def detalle(self, simbolo):
        if simbolo not in self._detalles:
            d = self._publico(f"/api/v1/contract/detail?symbol={simbolo}")
            self._detalles[simbolo] = {
                "tam": float(d["contractSize"]), "min": float(d["minVol"]),
                "unidad": float(d.get("volUnit") or 1), "tick": float(d["priceUnit"]),
                "max_apal": int(d.get("maxLeverage") or 20),
            }
        return self._detalles[simbolo]

    def saldo_disponible(self):
        d = self._privado("GET", "/api/v1/private/account/asset/USDT")
        return float(d.get("availableBalance") or 0)

    def posiciones(self):
        return self._privado("GET", "/api/v1/private/position/open_positions") or []

    def posiciones_cerradas(self, simbolo):
        d = self._privado("GET", "/api/v1/private/position/list/history_positions",
                          {"symbol": simbolo, "page_num": 1, "page_size": 50})
        return d if isinstance(d, list) else (d or {}).get("resultList", []) or []

    def orden_externa(self, simbolo, oid):
        return self._privado("GET", f"/api/v1/private/order/external/{simbolo}/{oid}")

    # ---------- acciones ----------
    def abrir(self, simbolo, lado, vol, precio, apalancamiento, stop, objetivo, oid):
        """Orden a mercado con stop y take profit adjuntos, margen aislado."""
        return self._privado("POST", "/api/v1/private/order/submit", {
            "symbol": simbolo, "price": precio, "vol": vol,
            "leverage": int(apalancamiento), "side": 1 if lado == 1 else 3,
            "type": 5, "openType": 1, "stopLossPrice": stop, "takeProfitPrice": objetivo,
            "externalOid": oid,
        })

    def cerrar(self, simbolo, lado, vol, precio, position_id, oid):
        """Cierra a mercado una posición (cierre por tiempo)."""
        return self._privado("POST", "/api/v1/private/order/submit", {
            "symbol": simbolo, "price": precio, "vol": vol, "side": 4 if lado == 1 else 2,
            "type": 5, "openType": 1, "positionId": position_id, "externalOid": oid,
        })
