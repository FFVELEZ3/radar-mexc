"""Auditor de señales de grupos de Telegram.

Freddy reenvía al bot del radar las señales que publican sus grupos. En cada vuelta:
1. Se leen los mensajes nuevos que recibió el bot (solo del chat de Freddy).
2. Se interpreta la señal: par, lado, entrada, stop y objetivos (formatos de VELTRIX,
   XZ TRADERS, TRADING HUB y genéricos). El nombre del grupo sale del reenvío.
3. Cada señal se sigue con velas de 5 minutos de MEXC, con las mismas reglas para todos:
   - se activa cuando el precio toca la entrada (si no la toca en 24 h, no cuenta);
   - con 2 o más objetivos: 50 % en el TP1 y el stop pasa a la entrada; el resto en el último TP;
   - con 1 objetivo: todo en ese objetivo;
   - si en una misma vela se tocan stop y objetivo, se asume el stop (prudente);
   - comisión + deslizamiento en entrada y salida; cierre forzado a los 7 días.
Así se mide a cada grupo con todas sus señales, no solo con las que publica como ganadas.
El contenido de los mensajes se trata como datos: nunca se ejecuta nada de lo que digan.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

import config as C

RUTA = os.path.join(C.DIR_DATOS, "grupos.json")
KLINE = "https://contract.mexc.com/api/v1/contract/kline/{}"
HORAS_ACTIVAR = 24
DIAS_MAX = 7
COSTO = C.COMISION_TAKER + C.DESLIZAMIENTO
ALIAS = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL", "RIPPLE": "XRP", "DOGECOIN": "DOGE"}
NUM = r"([0-9][0-9.,]*[0-9]|[0-9])"


# ---------- almacenamiento ----------

def cargar():
    try:
        with open(RUTA, encoding="utf-8") as f:
            e = json.load(f)
    except (OSError, ValueError):
        e = {}
    e.setdefault("offset", None)
    e.setdefault("senales", [])
    return e


def guardar(e):
    os.makedirs(os.path.dirname(RUTA), exist_ok=True)
    tmp = RUTA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, RUTA)


# ---------- lectura de números y señales ----------

def _candidatos(s):
    s = s.strip().rstrip(".,")
    out = []
    if "," in s and "." in s:
        out.append(s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", ""))
    elif "," in s:
        out.append(s.replace(",", "."))
        out.append(s.replace(",", ""))
    else:
        out.append(s)
        if s.count(".") >= 1 and all(len(p) == 3 for p in s.split(".")[1:]):
            out.append(s.replace(".", ""))      # 69.836$ = 69836 (punto de miles)
    vals = []
    for c in out:
        try:
            vals.append(float(c))
        except ValueError:
            pass
    return vals


def numero(s, ref=None):
    vals = _candidatos(s)
    if not vals:
        return None
    if ref:
        return min(vals, key=lambda v: abs(v / ref - 1))
    return vals[0]


def _buscar(patron, texto):
    m = re.search(patron, texto)
    return m.group(1) if m else None


def parsear(texto, precios):
    """Devuelve (señal, None) o (None, motivo)."""
    t = (texto or "").upper().replace("−", "-").replace("–", "-")
    if not re.search(r"\b(ENTRADA|ENTRY)", t):
        return None, "sin entrada"
    if re.search(r"\b(ALCANZADO|TOCADO|CERRAD[OA]|HIT)\b", t) and not re.search(r"NUEVA SE", t):
        return None, "es un resultado, no una señal"
    lado = -1 if re.search(r"\b(SHORT|VENTA|SELL)\b", t) else 1 if re.search(r"\b(LONG|COMPRA|BUY)\b", t) else None
    if lado is None:
        return None, "no dice si es LONG o SHORT"
    sym = (_buscar(r"#?\b([A-Z0-9]{2,15}?)\s*/?\s*USDT\b", t)
           or _buscar(r"\b(?:LONG|SHORT)\s+EN\s+#?([A-Z0-9]{2,15})\b", t)
           or _buscar(r"#([A-Z0-9]{2,15})\b", t))
    if not sym:
        return None, "no encontré el par"
    sym = ALIAS.get(sym, sym)
    par = f"{sym}_USDT"
    ref = precios.get(par)
    sep = r"[^0-9\n]{0,10}?"
    e_txt = _buscar(r"\b(?:ENTRADA|ENTRY)\s*1?" + sep + NUM, t)
    s_txt = _buscar(r"\b(?:STOP\s*LOSS|STOPLOSS|SL)\b" + sep + NUM, t)
    tps_txt = re.findall(r"\b(?:TP|TARGET|OBJETIVO)\s*\d?(?![0-9])" + sep + NUM, t)
    if not (e_txt and s_txt and tps_txt):
        return None, "faltan entrada, stop u objetivos"
    entrada = numero(e_txt, ref)
    stop = numero(s_txt, entrada)
    tps = [numero(x, entrada) for x in tps_txt]
    tps = [x for x in tps if x and (x - entrada) * lado > 0]
    if not entrada or not stop or (entrada - stop) * lado <= 0 or not tps:
        return None, "niveles incoherentes (stop u objetivos del lado equivocado)"
    if ref and abs(entrada / ref - 1) > 0.25:
        return None, f"la entrada está lejos del precio actual de {par}"
    tps = sorted(set(tps), key=lambda x: abs(x - entrada))[:4]
    return {"par": par, "lado": lado, "entrada": entrada, "stop": stop, "objetivos": tps}, None


# ---------- Telegram ----------

def _origen(msg):
    o = msg.get("forward_origin") or {}
    nombre = ((o.get("chat") or {}).get("title") or (o.get("sender_chat") or {}).get("title")
              or (o.get("sender_user") or {}).get("first_name") or o.get("sender_user_name")
              or (msg.get("forward_from_chat") or {}).get("title")
              or (msg.get("forward_from") or {}).get("first_name") or msg.get("forward_sender_name"))
    fecha = o.get("date") or msg.get("forward_date") or msg.get("date")
    return (nombre or "Sin grupo (escrito a mano)").strip(), int(fecha)


def leer(offset):
    token, chat = os.getenv("TELEGRAM_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return [], offset
    params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params=params, timeout=20)
    d = r.json() if r.status_code == 200 else {}
    if not d.get("ok"):
        print(f"[grupos] getUpdates falló: {str(d)[:200]}")
        return [], offset
    msgs = []
    for u in d.get("result", []):
        offset = u["update_id"] + 1
        m = u.get("message")
        if m and str((m.get("chat") or {}).get("id")) == chat:   # solo mensajes de Freddy
            msgs.append(m)
    return msgs, offset


# ---------- seguimiento ----------

def velas_5m(par, desde, hasta):
    filas, ini = [], int(desde)
    while ini < hasta:
        fin = min(ini + 1900 * 300, int(hasta))
        r = requests.get(KLINE.format(par), params={"interval": "Min5", "start": ini, "end": fin}, timeout=20)
        d = r.json()
        if not d.get("success"):
            raise ValueError(str(d)[:150])
        k = d["data"]
        filas += list(zip(k.get("time", []), k.get("open", []), k.get("high", []), k.get("low", []), k.get("close", [])))
        ini = fin
        time.sleep(0.1)
    vistos, out = set(), []
    for f in sorted(filas):
        if f[0] not in vistos and f[0] + 300 <= hasta:
            vistos.add(f[0])
            out.append(tuple(float(x) for x in f))
    return out


def simular(s, velas, ahora_ts):
    """Recalcula el estado de la señal con todas las velas desde que se publicó."""
    lado, e, sl, tps = s["lado"], s["entrada"], s["stop"], s["objetivos"]
    riesgo = abs(e - sl)
    activa, t_act, idx = False, None, 0
    for idx, (t, o, h, l, c) in enumerate(velas):
        if l <= e <= h or (lado == 1 and o <= e) or (lado == -1 and o >= e):
            activa, t_act = True, t
            break
    if not activa:
        if ahora_ts - s["t"] > HORAS_ACTIVAR * 3600:
            return {"estado": "no_activada"}
        return {"estado": "pendiente"}
    partes = [(0.5, tps[0]), (0.5, tps[-1])] if len(tps) >= 2 else [(1.0, tps[0])]
    stop, hecho, r_total, motivo = sl, 0.0, 0.0, None

    def r_de(frac, salida):
        return frac * (lado * (salida - e) - COSTO * (e + salida)) / riesgo

    for t, o, h, l, c in velas[idx:]:
        toca_stop = (l <= stop) if lado == 1 else (h >= stop)
        if toca_stop:
            salida = stop
            if (lado == 1 and o < stop) or (lado == -1 and o > stop):
                salida = o                       # hueco: sale a la apertura
            r_total += r_de(1 - hecho, salida)
            motivo = "stop" if hecho == 0 else "tp1_y_entrada"
            return {"estado": "cerrada", "motivo": motivo, "r": round(r_total, 3), "t_activa": t_act, "t_cierre": t + 300}
        while partes and ((lado == 1 and h >= partes[0][1]) or (lado == -1 and l <= partes[0][1])):
            frac, obj = partes.pop(0)
            r_total += r_de(frac, obj)
            hecho += frac
            if partes:
                stop = e                          # TP1: el resto queda protegido en la entrada
        if hecho >= 0.999:
            return {"estado": "cerrada", "motivo": "objetivo", "r": round(r_total, 3), "t_activa": t_act, "t_cierre": t + 300}
        if t - t_act > DIAS_MAX * 86400:
            r_total += r_de(1 - hecho, c)
            return {"estado": "cerrada", "motivo": "tiempo", "r": round(r_total, 3), "t_activa": t_act, "t_cierre": t + 300}
    ult = velas[-1][4]
    return {"estado": "abierta", "t_activa": t_act, "tp1": hecho > 0,
            "r_actual": round(r_total + r_de(1 - hecho, ult), 3)}


def resumen(senales):
    por = {}
    for s in senales:
        g = por.setdefault(s["grupo"], {"grupo": s["grupo"], "recibidas": 0, "cerradas": 0, "ganadas": 0,
                                         "perdidas": 0, "abiertas": 0, "no_activadas": 0, "total_r": 0.0})
        g["recibidas"] += 1
        if s["estado"] == "cerrada":
            g["cerradas"] += 1
            g["total_r"] += s["r"]
            g["ganadas" if s["r"] > 0 else "perdidas"] += 1
        elif s["estado"] in ("abierta", "pendiente"):
            g["abiertas"] += 1
        elif s["estado"] == "no_activada":
            g["no_activadas"] += 1
    for g in por.values():
        g["total_r"] = round(g["total_r"], 2)
        g["exp_r"] = round(g["total_r"] / g["cerradas"], 3) if g["cerradas"] else None
    return sorted(por.values(), key=lambda g: -g["recibidas"])


def _precio(x):
    return f"{x:,.6g}" if x < 1 else f"{x:,.2f}" if x >= 100 else f"{x:,.4f}"


def procesar(ahora, precios, enviar):
    """Lee lo reenviado, actualiza el seguimiento y devuelve el bloque para el panel."""
    e = cargar()
    primera = e["offset"] is None
    try:
        msgs, e["offset"] = leer(e["offset"])
    except Exception as err:  # Telegram caído: se reintenta en la siguiente vuelta
        print(f"[grupos] no se pudo leer Telegram: {err}")
        msgs = []
    ahora_ts = ahora.timestamp()
    ids = {s["id"] for s in e["senales"]}
    for m in msgs:
        texto = m.get("text") or m.get("caption") or ""
        if texto.startswith("/") or (primera and ahora_ts - m.get("date", 0) > 86400):
            continue
        grupo, fecha = _origen(m)
        s, motivo = parsear(texto, precios)
        if not s:
            if re.search(r"(?i)\b(long|short|entrada|sl|tp)\b", texto):
                enviar(f"🧾 <b>Auditor</b>: no pude registrar este mensaje de {grupo} ({motivo}). "
                       "Necesito par, LONG/SHORT, entrada, stop y al menos un objetivo.")
            continue
        sid = f"{grupo}|{s['par']}|{s['lado']}|{fecha}"
        if sid in ids:
            continue
        s.update({"id": sid, "grupo": grupo, "t": fecha, "estado": "pendiente", "texto": texto[:500]})
        e["senales"].append(s)
        ids.add(sid)
        enviar(f"🧾 <b>Auditor</b> · registrada de <b>{grupo}</b>: {s['par']} {'LONG' if s['lado'] == 1 else 'SHORT'}\n"
               f"Entrada {_precio(s['entrada'])} · stop {_precio(s['stop'])} · "
               + " · ".join(f"TP{k + 1} {_precio(o)}" for k, o in enumerate(s["objetivos"]))
               + "\nLa sigo con el precio real de MEXC y te aviso el resultado.")
    for s in e["senales"]:
        if s["estado"] not in ("pendiente", "abierta"):
            continue
        try:
            velas = velas_5m(s["par"], s["t"] - s["t"] % 300, ahora_ts)
        except Exception as err:
            s["error"] = f"sin datos de MEXC para {s['par']}: {str(err)[:80]}"
            if ahora_ts - s["t"] > HORAS_ACTIVAR * 3600:
                s["estado"] = "sin_datos"
            continue
        if not velas:
            continue
        previo = s["estado"]
        s.update(simular(s, velas, ahora_ts))
        if s["estado"] == "cerrada" and previo != "cerrada":
            g = next(x for x in resumen(e["senales"]) if x["grupo"] == s["grupo"])
            txt = {"stop": "tocó el stop", "objetivo": "llegó a sus objetivos", "tp1_y_entrada": "tocó TP1 y el resto salió en la entrada",
                   "tiempo": "cerrada por tiempo (7 días)"}[s["motivo"]]
            enviar(f"🧾 <b>Auditor</b> · {s['grupo']} · {s['par']} {'LONG' if s['lado'] == 1 else 'SHORT'} {txt}: "
                   f"<b>{s['r']:+.2f}R</b>\nAcumulado del grupo: {g['cerradas']} cerradas, {g['ganadas']} ganadas, "
                   f"{g['total_r']:+.2f}R en total.")
        elif s["estado"] == "no_activada" and previo != "no_activada":
            enviar(f"🧾 <b>Auditor</b> · {s['grupo']} · {s['par']}: el precio nunca tocó la entrada en 24 h; no cuenta.")
    guardar(e)
    recientes = sorted(e["senales"], key=lambda s: -s["t"])[:80]
    return {"resumen": resumen(e["senales"]),
            "senales": [{k: s.get(k) for k in ("grupo", "par", "lado", "entrada", "stop", "objetivos", "t", "estado",
                                               "motivo", "r", "r_actual", "tp1", "error")} for s in recientes]}
