"""Cartera de tendencia diaria: entradas reales en velas de 1 día.

Usa las cinco estrategias de seguimiento de tendencia que en el laboratorio salieron
positivas en el periodo antiguo y en el reciente (hasta 4 años, 20 pares):
Ichimoku, cruce 50/200, Donchian 55, Donchian 20 y SuperTrend (10, 3).

- Señal al cierre de la vela diaria (00:00 UTC = 19:00 Ecuador); entrada a la apertura
  de la vela siguiente, es decir, al precio de ese momento.
- Una sola posición por par a la vez (si varias estrategias coinciden, un solo aviso).
- Salida de tendencia del radar: stop inicial a 1.5 ATR diario; al ganar 1R pasa a la
  entrada; desde 2R persigue al precio a 2R del máximo de las velas diarias cerradas;
  objetivo de seguridad a 6R; hasta 120 días.
- El stop se recalcula una vez al día con velas cerradas (igual que en el backtest) y se
  vigila durante el día: si el precio lo toca, la operación se cierra en el stop.
"""
import json
import os
from datetime import datetime, timezone

import config as C
import lab
from backtest import niveles
from salidas import Posicion, stop_protegido

RUTA = os.path.join(C.DIR_DATOS, "diario.json")
ESTRATEGIAS = ["ichimoku", "medias", "donchian55", "donchian20", "supertrend"]
DIA = 86400


def cargar():
    try:
        with open(RUTA, encoding="utf-8") as f:
            e = json.load(f)
    except (OSError, ValueError):
        e = {}
    e.setdefault("senales", [])
    e.setdefault("ultimo_dia", None)
    return e


def guardar(e):
    os.makedirs(os.path.dirname(RUTA), exist_ok=True)
    tmp = RUTA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, RUTA)


def _lado_txt(l):
    return "LONG" if l == 1 else "SHORT"


def _r(lado, entrada, salida, riesgo):
    return (lado * (salida - entrada) - (C.COMISION_TAKER + C.DESLIZAMIENTO) * (entrada + salida)) / riesgo


def recorrer(s, d, ahora_ts):
    """Recalcula la posición con las velas diarias cerradas desde la entrada y vigila la vela en curso."""
    ent_t = datetime.fromisoformat(s["t_entrada"])
    cerr = d[(d.index >= ent_t) & (d.index.map(lambda x: x.timestamp()) + DIA <= ahora_ts)]
    pos = Posicion(s["lado"], s["entrada"], s["stop"], s["riesgo"], "tendencia")
    for t, v in cerr.iterrows():
        if pos.vela(v["open"], v["high"], v["low"], v["close"]):
            return {"estado": "cerrada", "motivo": pos.motivo, "r": round(pos.r(), 3), "salida": pos.salida_media,
                    "t_cierre": (t + (d.index[1] - d.index[0])).isoformat()}
    # stop que rige hoy: el que dejaron las velas cerradas (y el movimiento de la última)
    if len(cerr):
        avance = s["lado"] * (pos.extremo - s["entrada"])
        mejor = max if s["lado"] == 1 else min
        if avance >= s["riesgo"]:
            pos.stop = mejor(pos.stop, stop_protegido(s["lado"], s["entrada"]))
        if avance >= 2 * s["riesgo"]:
            pos.stop = mejor(pos.stop, pos.extremo - s["lado"] * 2 * s["riesgo"])
    hoy = d[d.index.map(lambda x: x.timestamp()) + DIA > ahora_ts]
    if len(hoy):
        v = hoy.iloc[-1]
        toca = v["low"] <= pos.stop if s["lado"] == 1 else v["high"] >= pos.stop
        if toca and datetime.fromtimestamp(ahora_ts, timezone.utc) >= ent_t:
            r = _r(s["lado"], s["entrada"], pos.stop, s["riesgo"])
            motivo = "stop" if s["lado"] * (pos.stop - s["stop"]) <= 0 else "seguimiento"
            return {"estado": "cerrada", "motivo": motivo, "r": round(r, 3), "salida": pos.stop,
                    "t_cierre": datetime.fromtimestamp(ahora_ts, timezone.utc).isoformat()}
        actual = v["close"]
    else:
        actual = cerr["close"].iloc[-1] if len(cerr) else s["entrada"]
    return {"estado": "activa", "stop_actual": pos.stop, "precio_actual": actual,
            "r_actual": round(_r(s["lado"], s["entrada"], actual, s["riesgo"]), 3)}


def procesar(pares, ahora, enviar, precio_fmt):
    e = cargar()
    ahora_ts = ahora.timestamp()
    hoy = datetime.fromtimestamp(ahora_ts - ahora_ts % DIA, timezone.utc)
    cache = {}

    def velas(par):
        if par not in cache:
            v = lab.velas(par, "1D", 420)
            cache[par] = lab.preparar(v) if v is not None else None
        return cache[par]

    # 1. Seguimiento de las abiertas (cada vuelta)
    for s in e["senales"]:
        if s["estado"] != "activa":
            continue
        try:
            d = velas(s["par"])
        except Exception as err:
            print(f"[diario] {s['par']}: {err}")
            continue
        if d is None:
            continue
        s.update(recorrer(s, d, ahora_ts))
        if s["estado"] == "cerrada":
            txt = {"stop": "tocó el stop", "seguimiento": "salió por el stop dinámico", "objetivo": "llegó al objetivo de 6R",
                   "tiempo": "se cerró por tiempo", "protegida": "salió protegida"}.get(s["motivo"], s["motivo"])
            enviar(f"{'✅' if s['r'] > 0 else '⛔'} <b>Tendencia diaria · {s['par']} {_lado_txt(s['lado'])}</b> {txt}: "
                   f"<b>{s['r']:+.2f}R</b> (entrada {precio_fmt(s['entrada'])}, salida {precio_fmt(s['salida'])}).")
        elif s["lado"] * (s["stop_actual"] - s.get("stop_avisado", s["stop"])) >= 0.5 * s["riesgo"]:
            s["stop_avisado"] = s["stop_actual"]
            seguro = s["lado"] * (s["stop_actual"] - s["entrada"]) >= 0
            enviar(f"🔁 <b>Tendencia diaria · {s['par']} {_lado_txt(s['lado'])}</b>: mueve el stop a "
                   f"<b>{precio_fmt(s['stop_actual'])}</b>.{' Ya no puede perder.' if seguro else ''}\n"
                   f"Precio {precio_fmt(s['precio_actual'])} · va {s['r_actual']:+.2f}R.")

    # 2. Señales nuevas: una vez por día, en la primera vuelta tras el cierre diario
    clave_dia = hoy.date().isoformat()
    if e["ultimo_dia"] != clave_dia and ahora_ts - hoy.timestamp() < 6 * 3600:
        abiertas = {s["par"] for s in e["senales"] if s["estado"] == "activa"}
        nuevas = 0
        for par in pares:
            if par in abiertas:
                continue
            try:
                d = velas(par)
            except Exception as err:
                print(f"[diario] {par}: {err}")
                continue
            if d is None or len(d) < 230:
                continue
            cerr = d[d.index.map(lambda x: x.timestamp()) + DIA <= ahora_ts]
            if not len(cerr) or cerr.index[-1].timestamp() + DIA != hoy.timestamp():
                continue
            quienes, lado = [], 0
            for k in ESTRATEGIAS:
                sv = int(lab.LAB[k][1](cerr).iloc[-1])
                if sv and (lado == 0 or sv == lado):
                    lado = sv
                    quienes.append(lab.LAB[k][0])
            if not lado:
                continue
            atr = float(cerr["atr"].iloc[-1])
            hoy_v = d[d.index.map(lambda x: x.timestamp()) + DIA > ahora_ts]
            entrada = float(hoy_v["open"].iloc[-1]) if len(hoy_v) else float(cerr["close"].iloc[-1])
            stop, _, riesgo = niveles(lado, entrada, atr)
            s = {"id": f"{par}|{clave_dia}", "par": par, "lado": lado, "estrategias": quienes,
                 "t_entrada": hoy.isoformat(), "entrada": entrada, "stop": stop, "riesgo": riesgo,
                 "objetivo": entrada + lado * 6 * riesgo, "estado": "activa", "stop_actual": stop}
            e["senales"].append(s)
            nuevas += 1
            pct = riesgo / entrada * 100
            enviar(f"🎯 <b>ENTRADA · TENDENCIA DIARIA · {par} {_lado_txt(lado)}</b>\n"
                   f"Por: {', '.join(quienes)}\n\n"
                   f"Entrada ≈ {precio_fmt(entrada)}\nStop {precio_fmt(stop)} ({pct:.1f} %)\n"
                   f"Objetivo de seguridad {precio_fmt(s['objetivo'])} (6R)\n\n"
                   "🔁 Sin objetivo cercano: al ganar 1R el stop pasa a la entrada y desde 2R sigue al precio. "
                   "Te aviso cuando debas moverlo (como mucho una vez al día).\n"
                   f"Apalancamiento máximo prudente: {max(1, int(30 / pct))}x. Arriesga poco: ganan ~4 de cada 10, "
                   "las ganadoras pagan varias pérdidas.\n"
                   "Base: estrategias de tendencia diaria positivas en 4 años de 20 pares, en el periodo antiguo y en el reciente.")
        e["ultimo_dia"] = clave_dia
        print(f"[diario] {clave_dia}: {nuevas} entradas nuevas")
    guardar(e)
    cerradas = [s for s in e["senales"] if s["estado"] == "cerrada"]
    return {"activas": [s for s in e["senales"] if s["estado"] == "activa"],
            "cerradas": sorted(cerradas, key=lambda s: s.get("t_cierre", ""), reverse=True)[:50],
            "resumen": {"cerradas": len(cerradas), "ganadas": sum(1 for s in cerradas if s["r"] > 0),
                        "total_r": round(sum(s["r"] for s in cerradas), 2)}}
