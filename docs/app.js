// Radar MEXC · terminal. Datos del servidor (data/datos.json, cada 5 min), historial de velas
// de Binance Futures (referencia de precio, funciona desde el navegador) y flujo en vivo de MEXC.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const LS = { get(k, d) { try { const v = localStorage.getItem("radar." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem("radar." + k, JSON.stringify(v)); } catch (e) { /* sin almacenamiento */ } } };
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const dec = (p) => (!p || !isFinite(p)) ? 2 : Math.min(10, Math.max(2, 3 - Math.floor(Math.log10(Math.abs(p)))));
  const px = (p) => (p == null || !isFinite(p)) ? "–" : Number(p).toLocaleString("en-US", { minimumFractionDigits: dec(p), maximumFractionDigits: dec(p) });
  const pc = (x, d = 2) => x == null || !isFinite(x) ? "–" : (x >= 0 ? "+" : "") + (x * 100).toFixed(d) + "%";
  const R = (x) => x == null ? "–" : (x >= 0 ? "+" : "") + Number(x).toFixed(2) + "R";
  const usd = (x) => (x >= 0 ? "+" : "−") + "$" + Math.abs(x || 0).toFixed(2);
  const cls = (x) => x > 0 ? "up" : x < 0 ? "down" : "muted";
  const vol = (v) => v >= 1e9 ? (v / 1e9).toFixed(2) + " B" : v >= 1e6 ? (v / 1e6).toFixed(1) + " M" : v >= 1e3 ? (v / 1e3).toFixed(1) + " K" : (v || 0).toFixed(0);
  const base = (s) => s.replace("_USDT", "");
  let zona = "America/Guayaquil";
  const fecha = (iso) => new Intl.DateTimeFormat("es-EC", { timeZone: zona, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
  const hace = (iso) => { const m = Math.round((Date.now() - new Date(iso)) / 60000); if (m < 1) return "hace instantes"; if (m < 60) return `hace ${m} min`; const h = Math.floor(m / 60); return h < 24 ? `hace ${h} h ${m % 60} min` : `hace ${Math.floor(h / 24)} d`; };
  const ladoChip = (l) => l === 1 ? '<span class="chip long">▲ LONG</span>' : '<span class="chip short">▼ SHORT</span>';
  const check = (ok) => ok ? '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="var(--accent-soft)"/><path d="M4.8 8.2l2.1 2.1 4.3-4.6" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round"/></svg>' : '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.2" fill="none" stroke="var(--faint)" stroke-width="1.4" stroke-dasharray="2.2 2"/></svg>';
  const segs = (e) => `<div class="segs ${e.senal && e.aprobada ? "lista" : e.aprobada ? "go" : ""}">${Array.from({ length: e.total }, (_, i) => `<i class="${i < e.cumplidas ? "on" : ""}"></i>`).join("")}</div>`;
  const get = async (url, ms = 9000) => { const c = new AbortController(), t = setTimeout(() => c.abort(), ms); try { const r = await fetch(url, { signal: c.signal }); if (!r.ok) throw new Error(r.status); return await r.json(); } finally { clearTimeout(t); } };

  // ---------- estado ----------
  let D = null, U = [], sel = LS.get("sel", "BTC_USDT"), tf = LS.get("tf", "1H"), filtro = "radar", favs = LS.get("favs", []);
  let inferior = LS.get("inf", "rsi");
  const ON = Object.assign({ ema20: true, ema50: true, ema200: true, sr: true, vol: true, plan: true, liq: true, st: false, ich: false, vwap: false, bb: false, kc: false, ob: false, fvg: false, fib: false, piv: false, perfil: false, div: true, hist: true }, LS.get("ind", {}));
  const TF = {
    "1s": { seg: 1, src: "tr" }, "5s": { seg: 5, src: "tr" }, "15s": { seg: 15, src: "tr" },
    "1m": { seg: 60, bn: "1m" }, "5m": { seg: 300, bn: "5m" }, "15m": { seg: 900, bn: "15m" }, "30m": { seg: 1800, bn: "30m" },
    "1H": { seg: 3600, bn: "1h" }, "4H": { seg: 14400, bn: "4h" }, "1D": { seg: 86400, bn: "1d" }, "1S": { seg: 604800, bn: "1w" }, "1M": { seg: 2592000, bn: "1M" },
  };
  const GRUPOS = [["1s", "5s", "15s"], ["1m", "5m", "15m", "30m"], ["1H", "4H"], ["1D", "1S", "1M"]];
  const enRadar = (s) => D && D.pares.some((p) => p.par === s);
  const parD = (s) => D && D.pares.find((p) => p.par === s);
  const uni = (s) => U.find((u) => u.sym === s);

  // ---------- menú de indicadores por familias ----------
  const FAM = [
    ["Tendencia", [["ema20", "EMA 20", "Media rápida: dirección de corto plazo"], ["ema50", "EMA 50", "Tendencia intermedia"], ["ema200", "EMA 200", "La tendencia mayor: arriba = mercado alcista"], ["st", "Supertrend (10, 3)", "Cambia de color cuando gira la tendencia"], ["ich", "Ichimoku", "Tenkan, Kijun y nube 26 velas adelante"]]],
    ["Volatilidad", [["bb", "Bandas de Bollinger (20, 2)", "Precio estirado o comprimido"], ["kc", "Canal de Keltner (20, 1.5 ATR)", "Rango normal según la volatilidad"]]],
    ["Volumen", [["vol", "Volumen", "Barras de volumen por vela"], ["vwap", "VWAP diario", "Precio medio ponderado por volumen del día"], ["perfil", "Perfil de volumen + POC", "Dónde se negoció más en el rango visible"]]],
    ["Estructura", [["sr", "Soportes y resistencias", "Zonas donde el precio giró varias veces"], ["liq", "Zonas de liquidez", "Máximos o mínimos iguales: stops acumulados"], ["ob", "Order blocks", "Última vela contraria antes de un impulso fuerte"], ["fvg", "Fair value gaps", "Huecos de precio sin rellenar"], ["fib", "Fibonacci automático", "Retrocesos del último gran movimiento"], ["piv", "Pivotes diarios", "P, R1–R3 y S1–S3 de la vela diaria anterior"], ["div", "Divergencias RSI", "Precio y RSI en direcciones opuestas"]]],
    ["Radar", [["plan", "Operación posible / señal", "Entrada, stop y objetivos del servidor"], ["hist", "Entradas históricas", "Operaciones del backtest en 1H y 4H"]]],
    ["Panel inferior", [["i:rsi", "RSI 14", "Sobrecompra > 70 · sobreventa < 30"], ["i:stoch", "Stoch RSI", "Cruces de %K y %D"], ["i:macd", "MACD 12/26/9", "Impulso y cruces"], ["i:adx", "ADX / DI", "Fuerza de la tendencia (> 20 = tendencia)"], ["i:obv", "OBV", "Volumen acumulado según dirección"], ["i:atr", "ATR 14", "Volatilidad media por vela"]]],
  ];
  let famSel = 0;
  function pintarMenu() {
    $("fam").innerHTML = FAM.map(([n, ops], i) => `<button type="button" role="tab" data-i="${i}" aria-selected="${i === famSel}">${n}<i>${ops.filter(([k]) => k.startsWith("i:") ? inferior === k.slice(2) : ON[k]).length || ""}</i></button>`).join("");
    $("ops").innerHTML = FAM[famSel][1].map(([k, n, d]) => { const inf = k.startsWith("i:"); return `<label class="op"><input type="${inf ? "radio" : "checkbox"}" name="${inf ? "inf" : k}" data-k="${k}" ${(inf ? inferior === k.slice(2) : ON[k]) ? "checked" : ""}><b>${n}</b><span>${d}</span></label>`; }).join("");
    $("n-ind").textContent = Object.values(ON).filter(Boolean).length;
    $("fam").querySelectorAll("button").forEach((b) => b.onclick = () => { famSel = +b.dataset.i; pintarMenu(); });
    $("ops").querySelectorAll("input").forEach((x) => x.onchange = () => { const k = x.dataset.k; if (k.startsWith("i:")) { inferior = k.slice(2); LS.set("inf", inferior); pintarInferior(); } else { ON[k] = x.checked; LS.set("ind", ON); dibujarTodo(); } pintarMenu(); pintarIsel(); });
  }
  $("b-ind").onclick = (e) => { e.stopPropagation(); const d = $("drop"); d.hidden = !d.hidden; $("b-ind").setAttribute("aria-expanded", !d.hidden); if (!d.hidden) pintarMenu(); };
  document.addEventListener("click", (e) => { if (!$("drop").hidden && e.target.isConnected && !e.target.closest(".menu")) { $("drop").hidden = true; $("b-ind").setAttribute("aria-expanded", false); } });

  // ---------- navegación ----------
  const VISTAS = ["mercado", "senales", "estrategias", "rendimiento", "bot", "guia"];
  function ir() {
    const v = VISTAS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "mercado";
    VISTAS.forEach((x) => $("v-" + x).classList.toggle("on", x === v));
    document.querySelectorAll(".mainnav a").forEach((a) => a.dataset.v === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
    if (v === "estrategias" && D) pintarBacktest();
    if (v === "mercado" && chart) requestAnimationFrame(dibujarCapa);
    scrollTo(0, 0);
  }
  addEventListener("hashchange", ir);
  document.querySelectorAll(".sub").forEach((sub) => sub.querySelectorAll("[role=tab]").forEach((b) => b.addEventListener("click", () => {
    sub.querySelectorAll("[role=tab]").forEach((x) => { x.setAttribute("aria-selected", x === b); $(x.dataset.p).hidden = x !== b; });
    if (b.dataset.p === "e-bt") pintarBacktest(); if (b.dataset.p === "l-tec") pintarTecnico(); if (b.dataset.p === "l-der") pintarDerivados();
  })));

  // ---------- universo de activos (todos los perpetuos USDT) ----------
  async function cargarUniverso() {
    try {
      const t = await get("https://fapi.binance.com/fapi/v1/ticker/24hr");
      U = t.filter((x) => x.symbol.endsWith("USDT") && !x.symbol.includes("_")).map((x) => {
        const m = x.symbol.match(/^(1000000|1000|1M)?(.+)USDT$/), f = m[1] === "1000" ? 1000 : m[1] === "1000000" || m[1] === "1M" ? 1e6 : 1;
        return { sym: m[2] + "_USDT", bn: x.symbol, f, precio: +x.lastPrice / f, cambio: +x.priceChangePercent / 100, vol: +x.quoteVolume };
      }).sort((a, b) => b.vol - a.vol);
    } catch (e) { /* sin Binance: solo pares del radar */ }
    pintarLista();
  }
  function lista() {
    const q = $("q").value.trim().toUpperCase();
    let xs = U.slice();
    if (D) D.pares.forEach((p) => { if (!xs.some((u) => u.sym === p.par)) xs.push({ sym: p.par, bn: null, f: 1, precio: p.precio, cambio: p.cambio24, vol: p.volumen24 }); });
    if (q) return xs.filter((u) => base(u.sym).includes(q)).slice(0, 80);
    if (filtro === "radar") xs = xs.filter((u) => enRadar(u.sym));
    if (filtro === "fav") xs = xs.filter((u) => favs.includes(u.sym));
    if (filtro === "suben") xs = xs.filter((u) => u.vol > 5e6).sort((a, b) => b.cambio - a.cambio);
    if (filtro === "bajan") xs = xs.filter((u) => u.vol > 5e6).sort((a, b) => a.cambio - b.cambio);
    return xs.slice(0, 120);
  }
  function pintarLista() {
    const xs = lista();
    $("items").innerHTML = xs.map((u) => { const p = parD(u.sym), pr = vivo[u.sym] || u.precio;
      const e = p && mejor(p), tag = e && e.senal && e.aprobada ? "SEÑAL" : p ? "RADAR" : "";
      return `<button type="button" class="it" data-s="${esc(u.sym)}" aria-pressed="${u.sym === sel}"><span><b>${esc(base(u.sym))}</b>${tag ? `<span class="tag">${tag}</span>` : ""}${favs.includes(u.sym) ? ' <span class="acc">★</span>' : ""}</span><span class="num p">${px(pr)}</span><span class="s">Vol ${vol(u.vol)}</span><span class="num c ${cls(u.cambio)}">${pc(u.cambio)}</span></button>`; }).join("") || '<div class="empty">Sin resultados.</div>';
    $("items").querySelectorAll(".it").forEach((b) => b.onclick = () => elegir(b.dataset.s));
  }
  $("q").addEventListener("input", pintarLista);
  document.querySelectorAll("[data-f]").forEach((b) => b.onclick = () => { filtro = b.dataset.f; document.querySelectorAll("[data-f]").forEach((x) => x.setAttribute("aria-pressed", x === b)); pintarLista(); });
  $("b-fav").onclick = () => { favs = favs.includes(sel) ? favs.filter((x) => x !== sel) : favs.concat(sel); LS.set("favs", favs); $("b-fav").textContent = favs.includes(sel) ? "★" : "☆"; pintarLista(); };

  // ---------- velas ----------
  const cache = {}, trades = {}, vivo = {};
  async function binance(sym, intervalo, limite = 1000) {
    const u = uni(sym), cand = u ? [u] : [{ bn: base(sym) + "USDT", f: 1 }, { bn: "1000" + base(sym) + "USDT", f: 1000 }];
    for (const c of cand) {
      try { const k = await get(`https://fapi.binance.com/fapi/v1/klines?symbol=${c.bn}&interval=${intervalo}&limit=${limite}`); return k.map((x) => [x[0] / 1000, x[1] / c.f, x[2] / c.f, x[3] / c.f, x[4] / c.f, +x[7]]); } catch (e) { /* siguiente */ }
    }
    return null;
  }
  function velasTrades(s, seg) { const v = []; (trades[s] || []).forEach(([t, p, q]) => { const k = Math.floor(t / 1000 / seg) * seg, u = v[v.length - 1]; if (u && u[0] === k) { u[2] = Math.max(u[2], p); u[3] = Math.min(u[3], p); u[4] = p; u[5] += q * p; } else v.push([k, p, p, p, p, q * p]); }); return v; }
  async function obtener(s, t) {
    const c = TF[t]; if (c.src === "tr") return velasTrades(s, c.seg);
    const k = s + "|" + t; if (cache[k] && Date.now() - cache[k].t < 120000) return cache[k].v;
    let v = await binance(s, c.bn);
    if (!v && parD(s) && (t === "1H" || t === "4H")) v = t === "1H" ? parD(s).velas : agrupar(parD(s).velas, 14400);
    if (v) cache[k] = { t: Date.now(), v }; return v || [];
  }
  function agrupar(v, seg) { const g = new Map(); v.forEach(([t, o, h, l, c, q]) => { const k = Math.floor(t / seg) * seg, x = g.get(k); if (!x) g.set(k, [k, o, h, l, c, q]); else { x[2] = Math.max(x[2], h); x[3] = Math.min(x[3], l); x[4] = c; x[5] += q; } }); return [...g.values()]; }

  // cierre de vela
  function proximoCierre(t, ahora = Date.now() / 1000) {
    const s = TF[t].seg;
    if (t === "1M") { const d = new Date(ahora * 1000); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) / 1000; }
    if (t === "1S") { const lunes = 4 * 86400; return Math.floor((ahora - lunes) / 604800) * 604800 + lunes + 604800; }
    return Math.floor(ahora / s) * s + s;
  }
  const falta = (seg) => { seg = Math.max(0, Math.round(seg)); const d = Math.floor(seg / 86400), h = Math.floor(seg % 86400 / 3600), m = Math.floor(seg % 3600 / 60), s = seg % 60, z = (x) => String(x).padStart(2, "0"); return d ? `${d}d ${h}h` : h ? `${h}:${z(m)}:${z(s)}` : `${z(m)}:${z(s)}`; };

  // ---------- gráfico ----------
  let chart, sub, sC, sV, extras = [], subS = [], serie = [], token = 0, capa, ctx;
  const tema = () => ({ layout: { background: { type: "solid", color: css("--surface") }, textColor: css("--muted"), fontFamily: "IBM Plex Mono, monospace", fontSize: 11 }, grid: { vertLines: { color: css("--surface-2") }, horzLines: { color: css("--surface-2") } }, rightPriceScale: { borderColor: css("--line") }, timeScale: { borderColor: css("--line"), rightOffset: 12 }, crosshair: { mode: 0 } });
  const fmtT = (t) => new Intl.DateTimeFormat("es-EC", Object.assign({ timeZone: TF[tf].seg >= 86400 ? "UTC" : zona, day: "2-digit", month: "short" }, TF[tf].seg >= 86400 ? { year: "numeric" } : { hour: "2-digit", minute: "2-digit", hour12: false }, TF[tf].seg < 60 ? { second: "2-digit" } : {})).format(new Date(t * 1000));
  function crear() {
    if (chart) return true; if (!window.LightweightCharts) return false;
    const LC = window.LightweightCharts;
    chart = LC.createChart($("chart"), Object.assign(tema(), { autoSize: true, localization: { timeFormatter: fmtT, locale: "es-EC" } }));
    sC = chart.addCandlestickSeries({ upColor: css("--up"), downColor: css("--down"), borderVisible: false, wickUpColor: css("--up"), wickDownColor: css("--down") });
    sV = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    sub = LC.createChart($("sub"), Object.assign(tema(), { autoSize: true, localization: { timeFormatter: fmtT, locale: "es-EC" }, timeScale: { visible: false, rightOffset: 12 } }));
    let sync = false;
    chart.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (r && !sync) { sync = true; sub.timeScale().setVisibleLogicalRange(r); sync = false; } requestAnimationFrame(dibujarCapa); });
    sub.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (r && !sync) { sync = true; chart.timeScale().setVisibleLogicalRange(r); sync = false; } });
    capa = $("capa"); ctx = capa.getContext("2d");
    new ResizeObserver(() => requestAnimationFrame(dibujarCapa)).observe($("chart"));
    // escala como TradingView: al arrastrar el eje se apaga "auto"; el botón (o doble clic) la vuelve a encender
    const refrescar = () => setTimeout(() => { pintarEscala(); requestAnimationFrame(dibujarCapa); }, 30);
    ["pointerup", "wheel", "touchend"].forEach((ev) => $("chart").addEventListener(ev, refrescar, { passive: true }));
    $("chart").addEventListener("dblclick", () => accionEscala("ir"));
    $("escala").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) accionEscala(b.dataset.a); });
    document.addEventListener("keydown", (e) => { if (e.altKey && !e.ctrlKey && !e.metaKey && /^[rRlLaA]$/.test(e.key) && $("v-mercado").classList.contains("on")) { e.preventDefault(); accionEscala({ r: "ir", l: "log", a: "auto" }[e.key.toLowerCase()]); } });
    aplicarEscala();
    return true;
  }
  const ESC = { modo: LS.get("escModo", 0) };
  function aplicarEscala(auto = true) {
    chart.priceScale("right").applyOptions({ mode: ESC.modo, autoScale: auto });
    sub.priceScale("right").applyOptions({ autoScale: true });
    LS.set("escModo", ESC.modo); pintarEscala(); requestAnimationFrame(dibujarCapa);
  }
  function verUltimas() {
    const ver = TF[tf].src === "tr" ? 120 : ({ "1D": 180, "1S": 110, "1M": 80 })[tf] || 130;
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, serie.length - ver), to: serie.length + 12 });
  }
  function accionEscala(a) {
    if (!chart || !a) return;
    const auto = chart.priceScale("right").options().autoScale;
    if (a === "ir") { verUltimas(); aplicarEscala(true); }
    else if (a === "fit") { chart.timeScale().fitContent(); aplicarEscala(true); }
    else if (a === "auto") aplicarEscala(!auto);
    else if (a === "log") { ESC.modo = ESC.modo === 1 ? 0 : 1; aplicarEscala(true); }
    else if (a === "pct") { ESC.modo = ESC.modo === 2 ? 0 : 2; aplicarEscala(true); }
  }
  function pintarEscala() {
    if (!chart) return;
    const auto = chart.priceScale("right").options().autoScale, e = $("escala");
    e.innerHTML = `<button type="button" data-a="ir" title="Ir a la última vela y reajustar (doble clic en el gráfico · Alt+R)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h12M13 6l6 6-6 6"/><path d="M21 4v16"/></svg></button><button type="button" data-a="fit" title="Ver todo el historial cargado"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button><i></i><button type="button" data-a="pct" aria-pressed="${ESC.modo === 2}" title="Escala en porcentaje desde la primera vela visible">%</button><button type="button" data-a="log" aria-pressed="${ESC.modo === 1}" title="Escala logarítmica (Alt+L)">log</button><button type="button" data-a="auto" aria-pressed="${auto}" title="Escala automática: el precio se ajusta a las velas visibles (Alt+A)">auto</button>`;
    e.style.right = (chart.priceScale("right").width() + 8) + "px";
  }
  function linea(color, w = 1.5, extra = {}) { const s = chart.addLineSeries({ color, lineWidth: w, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...extra }); extras.push(s); return s; }
  const L = (arr, desfase = 0) => { const out = []; for (let i = 0; i < arr.length; i++) { if (arr[i] == null) continue; const j = i + desfase; const t = j < serie.length ? serie[j][0] : serie[serie.length - 1][0] + (j - serie.length + 1) * TF[tf].seg; out.push({ time: t, value: arr[i] }); } return out; };

  let calc = {};
  function calcular() {
    const v = serie; calc = {};
    if (v.length < 2) return;
    calc.zonas = ON.sr ? IND.zonas(v) : null; calc.liq = ON.liq ? IND.liquidez(v) : []; calc.ob = ON.ob ? IND.orderBlocks(v) : []; calc.fvg = ON.fvg ? IND.fvg(v) : [];
    calc.fib = ON.fib ? IND.fibo(v) : null; calc.ich = ON.ich ? IND.ichimoku(v) : null; calc.div = ON.div ? IND.divergencias(v) : [];
  }
  function dibujarTodo() {
    if (!chart || !serie.length) return;
    extras.forEach((s) => chart.removeSeries(s)); extras = [];
    calcular();
    const v = serie, c = v.map((x) => x[4]);
    if (ON.ema20) linea(css("--c1")).setData(L(IND.ema(c, 20)));
    if (ON.ema50) linea(css("--c2")).setData(L(IND.ema(c, 50)));
    if (ON.ema200) linea(css("--c3"), 2).setData(L(IND.ema(c, 200)));
    if (ON.vwap) linea(css("--c5"), 1.5, { lineStyle: 2 }).setData(L(IND.vwap(v)));
    if (ON.bb) { const b = IND.bollinger(v); linea(css("--c4"), 1).setData(L(b.up)); linea(css("--c4"), 1).setData(L(b.lo)); linea(css("--c4"), 1, { lineStyle: 2 }).setData(L(b.m)); }
    if (ON.kc) { const k = IND.keltner(v); linea(css("--c6"), 1).setData(L(k.up)); linea(css("--c6"), 1).setData(L(k.lo)); }
    if (ON.st) { const s = IND.supertrend(v); const up = s.linea.map((x, i) => s.dir[i] === 1 ? x : null), dn = s.linea.map((x, i) => s.dir[i] === -1 ? x : null); linea(css("--up"), 2).setData(L(up)); linea(css("--down"), 2).setData(L(dn)); }
    if (ON.ich && calc.ich) { const ic = calc.ich; linea(css("--c2"), 1).setData(L(ic.ten)); linea(css("--c6"), 1).setData(L(ic.kij)); linea(css("--up"), 1).setData(L(ic.sa, 26)); linea(css("--down"), 1).setData(L(ic.sb, 26)); }
    sV.setData(ON.vol ? v.map(([time, o, , , cc, q]) => ({ time, value: q, color: cc >= o ? css("--up-soft") : css("--down-soft") })) : []);
    marcas();
    pintarInferior(); pintarLeyenda(); dibujarCapa();
  }
  function marcas() {
    const tiempos = new Set(serie.map((x) => x[0])), seg = TF[tf].seg, m = [], p = parD(sel);
    if (ON.hist && p && (tf === "1H" || tf === "4H")) { const letra = { retroceso: "R", ruptura: "B", rebote_rsi: "S", mtf: "M", barrida: "L", compresion: "C", zona: "Z", ruptura_viernes: "V" }; p.marcas.forEach((x) => { const t = Math.floor(x.t / seg) * seg; if (tiempos.has(t)) m.push({ time: t, position: x.lado === 1 ? "belowBar" : "aboveBar", color: x.r > 0 ? css("--up") : css("--down"), shape: x.lado === 1 ? "arrowUp" : "arrowDown", text: letra[x.clave] || "" }); }); }
    if (D) D.activas.filter((a) => a.par === sel).forEach((a) => { const t = Math.floor((new Date(a.t_entrada) / 1000 - 3600) / seg) * seg; if (tiempos.has(t)) m.push({ time: t, position: a.lado === 1 ? "belowBar" : "aboveBar", color: css("--accent"), shape: "circle", text: "SEÑAL" }); });
    (calc.div || []).forEach((d) => m.push({ time: d.t, position: d.tipo === "bajista" ? "aboveBar" : "belowBar", color: d.tipo === "bajista" ? css("--down") : css("--up"), shape: "square", text: "Div" }));
    sC.setMarkers(m.sort((a, b) => a.time - b.time));
  }
  function pintarInferior() {
    if (!sub || !serie.length) return;
    subS.forEach((s) => sub.removeSeries(s)); subS = [];
    const v = serie, l = (color, w = 1.5) => { const s = sub.addLineSeries({ color, lineWidth: w, priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false }); subS.push(s); return s; };
    const nivel = (s, p) => s.createPriceLine({ price: p, color: css("--faint"), lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    if (inferior === "rsi") { const s = l(css("--c1")); s.setData(L(IND.rsi(v))); nivel(s, 70); nivel(s, 30); }
    if (inferior === "stoch") { const st = IND.stochRsi(v), s = l(css("--c2")); s.setData(L(st.k)); l(css("--c5")).setData(L(st.d)); nivel(s, 80); nivel(s, 20); }
    if (inferior === "macd") { const m = IND.macd(v), h = sub.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }); subS.push(h); h.setData(v.map((x, i) => m.h[i] == null ? { time: x[0] } : { time: x[0], value: m.h[i], color: m.h[i] >= 0 ? css("--up-soft") : css("--down-soft") })); l(css("--c2")).setData(L(m.m)); l(css("--c5")).setData(L(m.sg)); }
    if (inferior === "adx") { const a = IND.adx(v), s = l(css("--c1"), 2); s.setData(L(a.adx)); l(css("--up"), 1).setData(L(a.pdi)); l(css("--down"), 1).setData(L(a.mdi)); nivel(s, 20); }
    if (inferior === "obv") l(css("--c4")).setData(L(IND.obv(v)));
    if (inferior === "atr") l(css("--c6")).setData(L(IND.atr(v)));
    const r = chart.timeScale().getVisibleLogicalRange(); if (r) sub.timeScale().setVisibleLogicalRange(r);
  }
  const NOM_INF = { rsi: "RSI", stoch: "Stoch RSI", macd: "MACD", adx: "ADX", obv: "OBV", atr: "ATR" };
  function pintarIsel() { $("isel").innerHTML = Object.entries(NOM_INF).map(([k, n]) => `<button type="button" data-i="${k}" aria-pressed="${k === inferior}">${n}</button>`).join(""); $("isel").querySelectorAll("button").forEach((b) => b.onclick = () => { inferior = b.dataset.i; LS.set("inf", inferior); pintarIsel(); pintarInferior(); }); }
  function pintarLeyenda() {
    const it = (c, t) => `<span><i style="background:${c}"></i>${t}</span>`, l = [];
    if (ON.ema20) l.push(it("var(--c1)", "EMA20")); if (ON.ema50) l.push(it("var(--c2)", "EMA50")); if (ON.ema200) l.push(it("var(--c3)", "EMA200"));
    if (ON.st) l.push(it("var(--up)", "Supertrend")); if (ON.ich) l.push(it("var(--c6)", "Ichimoku")); if (ON.vwap) l.push(it("var(--c5)", "VWAP")); if (ON.bb) l.push(it("var(--c4)", "Bollinger")); if (ON.kc) l.push(it("var(--c6)", "Keltner"));
    if (ON.sr) l.push(it("var(--down-soft)", "Resistencia") + it("var(--up-soft)", "Soporte")); if (ON.liq) l.push(it("var(--c5)", "Liquidez")); if (ON.ob) l.push(it("var(--c2)", "Order block")); if (ON.fvg) l.push(it("var(--c7)", "FVG"));
    $("leyenda").innerHTML = l.join("");
  }

  // capa de dibujo: zonas, order blocks, FVG, liquidez, Fibonacci, pivotes, perfil, plan y cuenta regresiva
  function dibujarCapa() {
    if (!chart || !ctx || !serie.length) return;
    const r = capa.getBoundingClientRect(), dpr = devicePixelRatio || 1;
    if (capa.width !== Math.round(r.width * dpr) || capa.height !== Math.round(r.height * dpr)) { capa.width = Math.round(r.width * dpr); capa.height = Math.round(r.height * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, r.width, r.height);
    const W = r.width - chart.priceScale("right").width(), ts = chart.timeScale(), Y = (p) => sC.priceToCoordinate(p), X = (t) => { const x = ts.timeToCoordinate(t); return x == null ? 0 : Math.max(0, x); };
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W, r.height - 26); ctx.clip();
    ctx.font = "600 10px IBM Plex Mono, monospace"; ctx.textBaseline = "middle"; const usadas = [];
    const caja = (x0, p1, p2, color, alfa, borde, texto) => { const y1 = Y(Math.max(p1, p2)), y2 = Y(Math.min(p1, p2)); if (y1 == null || y2 == null) return; const h = Math.max(2, y2 - y1); ctx.globalAlpha = alfa; ctx.fillStyle = color; ctx.fillRect(x0, y1, W - x0, h); ctx.globalAlpha = .7; ctx.strokeStyle = color; ctx.lineWidth = 1; if (borde) ctx.strokeRect(x0 + .5, y1 + .5, W - x0 - 1, h - 1); ctx.globalAlpha = 1; if (texto) etiqueta(x0 + 6, y1 + h / 2, texto, color); };
    const etiqueta = (x, y, t, color, alDerecha) => { const w = ctx.measureText(t).width + 10; if (alDerecha) { x = W - w - 4; let n = 0; while (n++ < 8 && usadas.some((u) => Math.abs(u - y) < 16)) y += 16; usadas.push(y); } ctx.fillStyle = color; ctx.globalAlpha = .95; ctx.fillRect(x, y - 8, w, 16); ctx.globalAlpha = 1; ctx.fillStyle = "#fff"; ctx.fillText(t, x + 5, y + .5); };
    const recta = (p, color, t, dash = [4, 4], x0 = 0) => { const y = Y(p); if (y == null) return; ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash(dash); ctx.beginPath(); ctx.moveTo(x0, y + .5); ctx.lineTo(W, y + .5); ctx.stroke(); ctx.setLineDash([]); if (t) etiqueta(0, y, t, color, true); };
    if (ON.perfil) { const vis = ts.getVisibleLogicalRange(), w = serie.slice(Math.max(0, Math.floor(vis ? vis.from : 0)), Math.ceil(vis ? vis.to : serie.length) + 1), pf = IND.perfil(w);
      if (pf) { const mx = Math.max(...pf.vol); pf.vol.forEach((q, i) => { const y1 = Y(pf.lo + (i + 1) * pf.paso), y2 = Y(pf.lo + i * pf.paso); if (y1 == null) return; const ancho = q / mx * W * 0.22; ctx.fillStyle = css("--c7"); ctx.globalAlpha = .22; ctx.fillRect(W - ancho, y1 + 1, ancho, Math.max(1, y2 - y1 - 1)); }); ctx.globalAlpha = 1; recta(pf.poc, css("--c5"), "POC " + px(pf.poc), [2, 3]); } }
    if (ON.ich && calc.ich) { const ic = calc.ich; ctx.globalAlpha = .12; for (let i = 1; i < ic.sa.length; i++) { const a0 = ic.sa[i - 1], b0 = ic.sb[i - 1], a1 = ic.sa[i], b1 = ic.sb[i]; if ([a0, b0, a1, b1].some((x) => x == null)) continue; const t0 = i - 1 + 26, t1 = i + 26, x0 = ts.logicalToCoordinate(t0), x1 = ts.logicalToCoordinate(t1); if (x0 == null || x1 == null) continue; ctx.fillStyle = a1 >= b1 ? css("--up") : css("--down"); ctx.beginPath(); ctx.moveTo(x0, Y(a0)); ctx.lineTo(x1, Y(a1)); ctx.lineTo(x1, Y(b1)); ctx.lineTo(x0, Y(b0)); ctx.fill(); } ctx.globalAlpha = 1; }
    if (calc.zonas) { const z = calc.zonas, ocup = []; z.res.concat(z.sop).forEach((x, i) => { const esR = i < z.res.length, n = esR ? i + 1 : i - z.res.length + 1, y = Y(x.precio); const choca = y != null && ocup.some((o) => Math.abs(o - y) < 16); if (y != null && !choca) ocup.push(y); caja(X(x.t0), x.lo, x.hi, esR ? css("--down") : css("--up"), Math.min(.34, .08 + x.toques * .04), true, choca ? null : `${esR ? "R" : "S"}${n} · ${x.toques} toques · ${x.fuerza}`); }); }
    (calc.ob || []).forEach((o) => caja(X(o.t0), o.lo, o.hi, o.tipo === "alcista" ? css("--c2") : css("--c6"), .18, true, `OB ${o.tipo}`));
    (calc.fvg || []).forEach((g) => caja(X(g.t0), g.lo, g.hi, css("--c7"), .16, false, `FVG ${g.tipo}`));
    (calc.liq || []).forEach((q) => recta(q.p, css("--c5"), `Liquidez ${q.tipo === "H" ? "arriba" : "abajo"} ${px(q.p)}`, [6, 3], X(q.t0)));
    if (calc.fib) calc.fib.niveles.forEach((n) => recta(n.p, n.f === 0.618 || n.f === 0.5 ? css("--accent") : css("--c7"), `Fib ${n.f} · ${px(n.p)}`, [2, 4], X(calc.fib.t0)));
    if (ON.piv && pivDia) Object.entries(pivDia).forEach(([k, p]) => recta(p, k === "P" ? css("--accent") : k.startsWith("R") ? css("--down") : css("--up"), `${k} ${px(p)}`, [1, 3]));
    if (ON.liq && clave) [["pdh", "Máx. ayer"], ["pdl", "Mín. ayer"], ["pwh", "Máx. semana ant."], ["pwl", "Mín. semana ant."]].forEach(([k, t]) => clave[k] && TF[tf].seg < 86400 && recta(clave[k], css("--muted"), t, [1, 4]));
    // operación posible proyectada a la derecha
    const pl = ON.plan ? planDe(sel) : null;
    if (pl) { const u = serie[serie.length - 1][0], xu = ts.timeToCoordinate(u) ?? W * .8, x0 = Math.min(W - 40, xu + 8);
      const franja = (a, b, color) => { const y1 = Y(Math.max(a, b)), y2 = Y(Math.min(a, b)); if (y1 == null || y2 == null) return; ctx.fillStyle = color; ctx.globalAlpha = .16; ctx.fillRect(x0, y1, W - x0, y2 - y1); ctx.globalAlpha = 1; };
      franja(pl.entrada, pl.objetivos[pl.objetivos.length - 1], css("--up")); franja(pl.entrada, pl.stop, css("--down"));
      const lin = (p, col, t) => { const y = Y(p); if (y == null) return; ctx.strokeStyle = col; ctx.setLineDash([5, 3]); ctx.beginPath(); ctx.moveTo(x0, y + .5); ctx.lineTo(W, y + .5); ctx.stroke(); ctx.setLineDash([]); etiqueta(0, y, t, col, true); };
      pl.objetivos.forEach((o, k) => lin(o, css("--up"), pl.objetivos.length > 1 ? `TP${k + 1}${k < pl.tps ? " ✓" : ""} ${px(o)}` : `Objetivo ${px(o)}`));
      lin(pl.entrada, css("--accent"), `${pl.activa ? "Entrada" : "Entrada posible"} ${px(pl.entrada)}`); lin(pl.stop, css("--down"), `Stop ${px(pl.stop)}`);
      if (pl.tps) lin(pl.stopAct, css("--accent"), `Stop protegido ${px(pl.stopAct)}`); }
    ctx.restore();
    // cuenta regresiva bajo la etiqueta del precio
    const u = serie[serie.length - 1], y = Y(u[4]), el = $("cuenta");
    if (y != null && TF[tf].src !== "tr") { el.hidden = false; el.style.top = y + "px"; el.style.width = chart.priceScale("right").width() + "px"; el.style.background = u[4] >= u[1] ? css("--up") : css("--down"); el.textContent = falta(proximoCierre(tf) - Date.now() / 1000); } else el.hidden = true;
  }

  // ---------- plan de la operación (solo pares del radar) ----------
  const mejor = (p) => { const w = (e) => (e.senal && e.aprobada ? 3 : 0) + (e.aprobada ? 1 : 0) + e.cumplidas / e.total; return p.estrategias.slice().sort((a, b) => w(b) - w(a))[0]; };
  const estSel = {};
  const estrategia = (p) => p.estrategias.find((e) => e.clave === estSel[p.par]) || mejor(p);
  function planDe(s) {
    const p = parD(s); if (!p) return null;
    const act = D.activas.find((a) => a.par === s);
    if (act) return { activa: act, lado: act.lado, entrada: act.entrada, stop: act.stop, objetivos: act.objetivos || [act.objetivo], r_neto: act.r_neto || [], apal: act.apal_max, tps: act.tps || 0, stopAct: act.stop_actual ?? act.stop, nombre: act.nombre, tramos: (act.objetivos || []).length > 1 ? [[1, .5], [2, .3], [3, .2]] : [[2, 1]] };
    const e = estrategia(p);
    return { e, lado: e.lado, entrada: e.plan.entrada, stop: e.plan.stop, objetivos: e.plan.objetivos || [e.plan.objetivo], r_neto: e.plan.r_neto || [], apal: e.plan.apal_max, tps: 0, stopAct: e.plan.stop, nombre: e.nombre, tramos: e.plan.tramos || [] };
  }
  function pintarPlan() {
    const p = parD(sel), el = $("l-plan");
    if (!p) { el.innerHTML = `<div class="aviso">Este activo <b>no está en el radar del servidor</b> (vigila los ${D ? D.pares.length : 20} pares con más volumen de MEXC). Aquí tienes gráfico, indicadores, niveles y la <b>lectura técnica</b>, pero no hay backtest ni señales: nadie ha comprobado que una estrategia gane en este activo.</div><button class="btn" type="button" id="ir-tec">Ver resumen técnico</button>`; $("ir-tec").onclick = () => document.querySelector('[data-p="l-tec"]').click(); return; }
    const pl = planDe(sel), e = pl.e || p.estrategias.find((x) => x.nombre === pl.nombre) || mejor(p), c = D.config;
    const riesgo = Math.abs(pl.entrada - pl.stop), costo = (c.comision + c.deslizamiento) * 2 * pl.entrada, cant = c.riesgo_usd / (riesgo + costo), noc = cant * pl.entrada;
    let tit, txt, col;
    if (pl.activa) { tit = "Señal activa"; txt = `Abierta ${hace(pl.activa.creada)} · ${(pl.activa.real || {}).estado === "abierta" ? "operando en real" : "seguimiento en papel"}`; col = "var(--up)"; }
    else if (e.senal && e.aprobada) { tit = "Lista para operar"; txt = "Condiciones completas y ventaja comprobada."; col = "var(--up)"; }
    else if (e.aprobada) { tit = `En formación · faltan ${e.total - e.cumplidas}`; txt = "Tiene ventaja comprobada; avisará al completarse."; col = "var(--accent)"; }
    else { tit = "Solo referencia"; txt = "Sin ventaja estadística en este par: no se opera."; col = "var(--faint)"; }
    const t = e.total_stats, gan = e.ganadas ?? Math.round(t.n * t.acierto), faltan = e.condiciones.filter(([, ok]) => !ok).map(([x]) => x);
    const ring = (k, n) => { const rr = 19, cc = 2 * Math.PI * rr; return `<svg width="48" height="48" viewBox="0 0 48 48"><circle cx="24" cy="24" r="${rr}" fill="none" stroke="var(--surface-3)" stroke-width="5"/><circle cx="24" cy="24" r="${rr}" fill="none" stroke="${col}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${cc * (n ? k / n : 0)} ${cc}" transform="rotate(-90 24 24)"/><text x="24" y="28" text-anchor="middle" font-family="IBM Plex Mono" font-size="12" font-weight="600" fill="var(--fg)">${k}/${n}</text></svg>`; };
    const objs = pl.objetivos, rep = (k) => pl.tramos[k] ? ` · ${Math.round(pl.tramos[k][1] * 100)}%` : "";
    el.innerHTML = `
      <div><div class="label" style="margin-bottom:6px" title="La señal se decide al cierre de cada vela de 1 hora; antes filtra con la tendencia diaria y de 4 horas">Estrategia · entrada en velas de 1 h (filtros diario y 4 h)</div><div class="seg" id="estabs">${p.estrategias.map((x) => `<button type="button" data-k="${x.clave}" aria-pressed="${x.clave === e.clave && !pl.activa}">${esc(x.nombre)}</button>`).join("")}</div></div>
      <div class="veredicto">${ring(pl.activa ? e.total : e.cumplidas, e.total)}<div><b>${tit}</b><p>${txt}</p></div></div>
      ${pl.activa ? "" : `<ul class="conds"><li class="${e.cumplidas === e.total ? "ok" : ""}">${check(e.cumplidas === e.total)}<span><b>Condiciones ${e.cumplidas}/${e.total}</b>${faltan.length ? " · falta: " + faltan.map(esc).join(" · ") : ""}</span></li><li class="${e.aprobada ? "ok" : ""}">${check(e.aprobada)}<span><b>Ventaja comprobada: ${e.aprobada ? "sí" : "no"}</b> · ${t.n} ops, ganó ${gan}, ${R(t.exp_r)} por operación</span></li></ul>`}
      <div><div style="display:flex;justify-content:space-between;margin-bottom:8px">${ladoChip(pl.lado)}<span class="muted" style="font-size:12px">${objs.length > 1 ? "3 objetivos" : "1 objetivo"} · elegido por el historial</span></div>
        <div class="escalera">${objs.map((o, k) => [o, k]).reverse().map(([o, k]) => `<i style="background:var(--up);opacity:${k < pl.tps ? .4 : 1}"></i><span class="label">${objs.length > 1 ? `TP${k + 1}${rep(k)}` : "Objetivo"}${k < pl.tps ? " ✓" : ""}</span><span class="num up">${px(o)}</span>`).join("")}
          <i style="background:var(--accent)"></i><span class="label">${pl.activa ? "Entrada" : "Entrada (precio actual)"}</span><span class="num">${px(pl.entrada)}</span>
          <i style="background:var(--down)"></i><span class="label">Stop</span><span class="num down">${px(pl.stop)}</span>
          ${pl.tps ? `<i style="background:var(--accent)"></i><span class="label">Stop protegido</span><span class="num">${px(pl.stopAct)}</span>` : ""}</div></div>
      ${objs.length > 1 ? '<div class="aviso">🔒 Al tocar TP1 se cierra la mitad y el stop pasa a la entrada.</div>' : ""}
      <div class="kv">
        <div><span class="label">Tamaño para $${c.riesgo_usd}</span><span class="num">${cant.toPrecision(4)} ${esc(base(sel))}</span></div>
        <div><span class="label">Margen a ${c.apalancamiento}x</span><span class="num">$${(noc / c.apalancamiento).toFixed(2)}</span></div>
        ${pl.r_neto.map((x, k) => `<div><span class="label">${objs.length > 1 ? "Llega a TP" + (k + 1) : "Toca objetivo"} (neto)</span><span class="num ${cls(x)}">${usd(c.riesgo_usd * x)} · ${R(x)}</span></div>`).join("")}
        <div><span class="label">Toca stop</span><span class="num down">${usd(-c.riesgo_usd)} · −1R</span></div>
        <div><span class="label">Apalancamiento</span><span class="num">usa ${c.apalancamiento}x · máx ${pl.apal || "–"}x</span></div>
      </div>
      <div><div class="label" style="margin-bottom:6px">Condiciones · ${e.lado === 1 ? "LONG" : "SHORT"}</div><ul class="conds">${e.condiciones.map(([x, ok]) => `<li class="${ok ? "ok" : ""}">${check(ok)}<span>${esc(x)}</span></li>`).join("")}</ul></div>
      <div><div class="label" style="margin-bottom:6px">Si la hubieras operado el último año</div><div class="kv"><div><span class="label">Ganadas</span><span class="num up">${gan}</span></div><div><span class="label">Perdidas</span><span class="num down">${t.n - gan}</span></div><div><span class="label">Con $${c.riesgo_usd} por op.</span><span class="num ${cls(t.total_r)}">${usd(t.total_r * c.riesgo_usd)}</span></div><div><span class="label">Meses recientes</span><span class="num ${cls(e.oos_stats.exp_r)}">${R(e.oos_stats.exp_r)}/op</span></div></div>
        ${t.tp ? `<p class="muted" style="font-size:12px;margin:8px 0 0">Llegaron a TP1 ${Math.round(t.tp[0] * 100)}% · TP2 ${Math.round(t.tp[1] * 100)}% · TP3 ${Math.round(t.tp[2] * 100)}%.</p>` : ""}
        ${e.alternativa ? `<p class="muted" style="font-size:12px;margin:4px 0 0">Con ${e.alternativa.gestion === "fija" ? "1 objetivo" : "3 objetivos"} habría dado ${R(e.alternativa.exp_r)} por operación.</p>` : ""}
        ${e.aprobada ? "" : `<p class="muted" style="font-size:12px;margin:4px 0 0">No pasa el filtro: ${esc(e.motivos[0] || "")}.</p>`}</div>`;
    el.querySelectorAll("#estabs button").forEach((b) => b.onclick = () => { estSel[sel] = b.dataset.k; pintarPlan(); dibujarCapa(); });
  }

  // ---------- resumen técnico multi-temporalidad ----------
  const MTF = ["5m", "15m", "1H", "4H", "1D", "1S"];  // la tabla; el bloque "de arriba abajo" usa D, 4h, 1h y 15m
  const cls2 = (tx) => ({ "Compra fuerte": "cf", "Compra": "c", "Venta fuerte": "vf", "Venta": "v" })[tx] || "n";
  async function pintarTecnico() {
    const el = $("l-tec"), s = sel; el.innerHTML = '<span class="muted">Calculando en 6 temporalidades…</span>';
    const filas = await Promise.all(MTF.map(async (t) => ({ t, l: IND.lectura(await obtener(s, t)) })));
    if (s !== sel) return;
    const val = filas.filter((f) => f.l), conf = val.reduce((a, f) => a + f.l.total, 0) / (val.length || 1), txc = conf >= .5 ? "Compra fuerte" : conf >= .15 ? "Compra" : conf <= -.5 ? "Venta fuerte" : conf <= -.15 ? "Venta" : "Neutral";
    const act = filas.find((f) => f.t === tf) || filas.find((f) => f.l) || {};
    const aa = await arribaAbajo(s); if (s !== sel) return;
    el.innerHTML = aa + `<div><div class="label">Confluencia de 6 temporalidades</div><div style="display:flex;justify-content:space-between;align-items:baseline;margin:6px 0"><span class="lect ${cls2(txc)}" style="font-size:18px">${txc}</span><span class="num muted">${(conf * 100).toFixed(0)} / 100</span></div><div class="medidor"><b style="left:${(conf + 1) / 2 * 100}%"></b></div></div>
      <table class="mtf"><thead><tr><th>Temp.</th><th>Lectura</th><th class="r">▲ / ▼</th><th class="r">RSI</th><th class="r">Cierra en</th></tr></thead><tbody>${filas.map((f) => `<tr><td><b>${f.t}</b></td><td>${f.l ? `<span class="lect ${cls2(f.l.tx)}">${f.l.tx}</span>` : '<span class="muted">sin datos</span>'}</td><td class="r num">${f.l ? `<span class="up">${f.l.compras}</span>/<span class="down">${f.l.ventas}</span>` : "–"}</td><td class="r num">${f.l && f.l.rsi ? f.l.rsi.toFixed(0) : "–"}</td><td class="r num" data-cierre="${f.t}">${falta(proximoCierre(f.t) - Date.now() / 1000)}</td></tr>`).join("")}</tbody></table>
      ${act.l ? `<div><div class="label" style="margin-bottom:6px">Detalle en ${act.t}</div><div class="votos">${act.l.votos.map((x) => `<div><span>${x.nombre}</span><span class="${x.x > 0 ? "up" : x.x < 0 ? "down" : "muted"}">${x.x > 0 ? "▲ compra" : x.x < 0 ? "▼ venta" : "◆ neutral"}${x.det != null && isFinite(x.det) ? ` <span class="muted num">${x.det > 1000 || x.det < 1 ? px(x.det) : x.det.toFixed(1)}</span>` : ""}</span></div>`).join("")}</div></div>` : ""}
      <div class="aviso">Es una <b>lectura técnica</b> (10 indicadores votan) como la de los analistas, no una señal: el backtest del radar muestra que estas lecturas solas no ganan tras comisiones. Úsala para no operar contra la tendencia mayor.</div>`;
  }

  // análisis de arriba abajo: diario y 4h dan la dirección, 1h el contexto y 15m la entrada fina
  function dirTF(v) {
    if (!v || v.length < 60) return null;
    const c = v.map((x) => x[4]), n = c.length - 1, e20 = IND.ema(c, 20)[n], e50 = IND.ema(c, 50)[n], u = c[n];
    return u > e50 && e20 > e50 ? 1 : u < e50 && e20 < e50 ? -1 : 0;
  }
  async function arribaAbajo(s) {
    const [vD, v4, v1, v15] = await Promise.all(["1D", "4H", "1H", "15m"].map((t) => obtener(s, t)));
    const d = [["Diario", dirTF(vD)], ["4h", dirTF(v4)], ["1h", dirTF(v1)], ["15m", dirTF(v15)]];
    const ico = (x) => x === 1 ? '<span class="up">▲ alcista</span>' : x === -1 ? '<span class="down">▼ bajista</span>' : '<span class="muted">◆ lateral</span>';
    const sesgo = d[0][1] && d[0][1] === d[1][1] ? d[0][1] : 0;
    let plan = "";
    if (!sesgo) plan = `<div class="aviso">El diario y el 4h <b>no apuntan al mismo lado</b>: no hay sesgo claro. Lo profesional aquí es esperar.</div>`;
    else if (v15 && v15.length > 60 && v1 && v1.length > 60) {
      const z15 = IND.zonas(v15), z1 = IND.zonas(v1), u = v15[v15.length - 1][4], a15 = IND.atr(v15).slice(-1)[0];
      const zona = sesgo === 1 ? z15.sop[0] : z15.res[0], meta = sesgo === 1 ? z1.res[0] : z1.sop[0];
      const alineado = d[2][1] === sesgo;
      if (zona) {
        const entrada = sesgo === 1 ? zona.hi : zona.lo, stop = sesgo === 1 ? zona.lo - 0.5 * a15 : zona.hi + 0.5 * a15;
        const obj = meta ? meta.precio : entrada + sesgo * 2 * Math.abs(entrada - stop), rr = Math.abs(obj - entrada) / Math.abs(entrada - stop);
        plan = `<div class="aviso"><b>Sesgo ${sesgo === 1 ? "LONG" : "SHORT"}</b> (diario y 4h de acuerdo)${alineado ? " y el 1h acompaña." : ", pero el 1h todavía va en contra: espera a que gire."}<br>
          Zona de entrada en 15m: <b class="num">${px(zona.lo)} – ${px(zona.hi)}</b> (${zona.toques} toques, ${pc((entrada - u) / u)} del precio)<br>
          Invalidación: <b class="num">${px(stop)}</b> · objetivo ${meta ? "en la " + (sesgo === 1 ? "resistencia" : "zona de soporte") + " de 1h" : "a 2R"}: <b class="num">${px(obj)}</b> · R:R ${rr.toFixed(1)}<br>
          <span class="muted">Plan táctico sin backtest: úsalo para afinar la entrada de una señal del radar, no como señal por sí solo.${rr < 1.5 ? " Con este R:R no compensa." : ""}</span></div>`;
      } else plan = `<div class="aviso"><b>Sesgo ${sesgo === 1 ? "LONG" : "SHORT"}</b>, pero no hay una zona clara en 15m a favor: espera un retroceso.</div>`;
    }
    return `<div><div class="label" style="margin-bottom:6px">De arriba abajo</div><div class="votos">${d.map(([n, x]) => `<div><span>${n}</span>${x == null ? '<span class="muted">sin datos</span>' : ico(x)}</div>`).join("")}</div></div>${plan}`;
  }

  // ---------- niveles ----------
  let pivDia = null, clave = null;
  async function cargarClave(s) {
    pivDia = null; clave = null;
    const [d, w] = await Promise.all([binance(s, "1d", 3), binance(s, "1w", 3)]);
    if (s !== sel) return;
    const dd = d && d.length >= 2 ? d[d.length - 2] : null, ww = w && w.length >= 2 ? w[w.length - 2] : null;
    pivDia = IND.pivotes(dd); clave = { pdh: dd && dd[2], pdl: dd && dd[3], pwh: ww && ww[2], pwl: ww && ww[3] };
    dibujarCapa(); pintarNiveles();
  }
  function pintarNiveles() {
    const v = serie, u = v.length ? v[v.length - 1][4] : null, z = IND.zonas(v), fila = (tag, colorTag, p, extra) => `<div><span class="chip ${colorTag}">${tag}</span><span class="num">${px(p)}</span><span class="muted num">${u ? pc((p - u) / u) : ""}${extra ? " · " + extra : ""}</span></div>`;
    const lq = IND.liquidez(v), ob = IND.orderBlocks(v), fv = IND.fvg(v), fb = IND.fibo(v);
    $("l-niv").innerHTML = `<div><div class="label" style="margin-bottom:6px">Soportes y resistencias (${tf})</div><div class="nivlist">${z.res.slice().reverse().map((x, i, a) => fila("R" + (a.length - i), "short", x.precio, `${x.toques} toques · ${x.fuerza}`)).join("")}${u ? fila("Precio", "accent", u) : ""}${z.sop.map((x, i) => fila("S" + (i + 1), "long", x.precio, `${x.toques} toques · ${x.fuerza}`)).join("")}</div></div>
      ${lq.length ? `<div><div class="label" style="margin-bottom:6px">Liquidez sin barrer</div><div class="nivlist">${lq.map((q) => fila(q.tipo === "H" ? "Arriba" : "Abajo", "accent", q.p, "máximos/mínimos iguales")).join("")}</div></div>` : ""}
      ${ob.length ? `<div><div class="label" style="margin-bottom:6px">Order blocks sin mitigar</div><div class="nivlist">${ob.map((o) => fila(o.tipo === "alcista" ? "OB ▲" : "OB ▼", o.tipo === "alcista" ? "long" : "short", (o.lo + o.hi) / 2, `${px(o.lo)}–${px(o.hi)}`)).join("")}</div></div>` : ""}
      ${fv.length ? `<div><div class="label" style="margin-bottom:6px">Fair value gaps abiertos</div><div class="nivlist">${fv.map((g) => fila(g.tipo === "alcista" ? "FVG ▲" : "FVG ▼", "", (g.lo + g.hi) / 2, `${px(g.lo)}–${px(g.hi)}`)).join("")}</div></div>` : ""}
      ${fb ? `<div><div class="label" style="margin-bottom:6px">Fibonacci · impulso ${fb.subida ? "alcista" : "bajista"}</div><div class="nivlist">${fb.niveles.map((n) => fila(String(n.f), n.f === 0.618 || n.f === 0.5 ? "accent" : "", n.p)).join("")}</div></div>` : ""}
      ${pivDia ? `<div><div class="label" style="margin-bottom:6px">Pivotes diarios</div><div class="nivlist">${["R3", "R2", "R1", "P", "S1", "S2", "S3"].map((k) => fila(k, k[0] === "R" ? "short" : k[0] === "S" ? "long" : "accent", pivDia[k])).join("")}</div></div>` : ""}
      ${clave && clave.pdh ? `<div><div class="label" style="margin-bottom:6px">Día y semana anteriores</div><div class="nivlist">${fila("Máx. D", "", clave.pdh)}${fila("Mín. D", "", clave.pdl)}${clave.pwh ? fila("Máx. S", "", clave.pwh) + fila("Mín. S", "", clave.pwl) : ""}</div></div>` : ""}`;
  }

  // ---------- derivados ----------
  async function pintarDerivados() {
    const el = $("l-der"), s = sel, u = uni(s); if (!u) { el.innerHTML = '<span class="muted">Sin datos de derivados para este activo.</span>'; return; }
    el.innerHTML = '<span class="muted">Consultando…</span>';
    const q = (url) => get(url).catch(() => null), b = u.bn;
    const [pi, oi, oih, ls, top, tk, fg] = await Promise.all([q(`https://fapi.binance.com/fapi/v1/premiumIndex?symbol=${b}`), q(`https://fapi.binance.com/fapi/v1/openInterest?symbol=${b}`), q(`https://fapi.binance.com/futures/data/openInterestHist?symbol=${b}&period=1h&limit=25`), q(`https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=${b}&period=1h&limit=1`), q(`https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=${b}&period=1h&limit=1`), q(`https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=${b}&period=1h&limit=6`), q("https://api.alternative.me/fng/?limit=1")]);
    if (s !== sel) return;
    const fr = pi ? +pi.lastFundingRate : null, pdM = parD(s), oiN = oi ? +oi.openInterest * (vivo[s] || u.precio) * u.f : null;
    const oiCh = oih && oih.length > 1 ? +oih[oih.length - 1].sumOpenInterestValue / +oih[0].sumOpenInterestValue - 1 : null;
    const lsr = ls && ls[0] ? +ls[0].longShortRatio : null, tpr = top && top[0] ? +top[0].longShortRatio : null, tkr = tk && tk.length ? tk.reduce((a, x) => a + +x.buySellRatio, 0) / tk.length : null, f = fg && fg.data ? fg.data[0] : null;
    const caja = (t, v, s2) => `<div><span class="label">${t}</span><span class="num" style="font-size:16px">${v}</span><span class="muted" style="font-size:12px">${s2}</span></div>`;
    el.innerHTML = `<div class="kv">
      ${caja("Funding (8h)", fr != null ? `<span class="${cls(-fr)}">${(fr * 100).toFixed(4)}%</span>` : (pdM ? (pdM.funding * 100).toFixed(4) + "%" : "–"), fr == null ? "" : fr > .0003 ? "Longs pagando caro: mercado sobrecargado al alza" : fr < -.0001 ? "Shorts pagando: posible rebote por cierre de cortos" : "Neutral")}
      ${caja("Próximo funding", pi ? falta(pi.nextFundingTime / 1000 - Date.now() / 1000) : "–", "")}
      ${caja("Interés abierto", oiN ? "$" + vol(oiN) : "–", oiCh != null ? `${pc(oiCh)} en 24 h · ${oiCh > .03 ? "entra dinero nuevo" : oiCh < -.03 ? "se cierran posiciones" : "estable"}` : "")}
      ${caja("Long/short cuentas", lsr ? lsr.toFixed(2) : "–", lsr ? `${(lsr / (1 + lsr) * 100).toFixed(0)}% en largo${lsr > 2 ? " · mucha gente long: riesgo de barrida abajo" : lsr < .8 ? " · mucha gente short: riesgo de barrida arriba" : ""}` : "")}
      ${caja("Top traders L/S", tpr ? tpr.toFixed(2) : "–", "posiciones de las cuentas grandes")}
      ${caja("Compras/ventas agresivas", tkr ? tkr.toFixed(2) : "–", tkr ? (tkr > 1.05 ? "dominan compradores (6 h)" : tkr < .95 ? "dominan vendedores (6 h)" : "equilibrado") : "")}
      ${caja("Miedo y codicia", f ? f.value : "–", f ? { "Extreme Fear": "Miedo extremo", "Fear": "Miedo", "Neutral": "Neutral", "Greed": "Codicia", "Extreme Greed": "Codicia extrema" }[f.value_classification] || f.value_classification : "")}
      </div><div class="aviso">Datos de Binance Futures (el mayor mercado de perpetuos) como referencia del posicionamiento. Cuando casi todos están del mismo lado, el precio suele ir a barrer sus stops antes de seguir.</div>`;
  }

  // ---------- flujo (MEXC en vivo) ----------
  function pintarFlujo() {
    const tr = trades[sel] || [], ahora = Date.now(), ult = tr.filter((x) => ahora - x[0] <= 60000);
    let c = 0, v = 0; ult.forEach((x) => { if (x[3] === 1) c += x[2] * x[1]; else v += x[2] * x[1]; }); const tot = c + v || 1;
    const tam = tr.slice(-300).map((x) => x[2]).sort((a, b) => a - b), grande = tam[Math.floor(tam.length * .95)] || Infinity;
    $("l-flujo").innerHTML = `<div><div class="label">Presión compradora vs vendedora · 60 s</div><div class="barra" style="height:10px;margin:8px 0 4px"><i style="width:${c / tot * 100}%;background:var(--up)"></i><i style="width:${v / tot * 100}%;background:var(--down)"></i></div><div style="display:flex;justify-content:space-between;font-size:12px"><span class="up">Compras ${Math.round(c / tot * 100)}%</span><span class="muted">${(ult.length / 60).toFixed(1)} ops/s</span><span class="down">Ventas ${Math.round(v / tot * 100)}%</span></div></div>
      <div><div class="label" style="margin-bottom:6px">Operaciones en MEXC · resaltadas las más grandes</div><div class="tape">${tr.slice(-50).reverse().map(([t, p, q, l]) => `<div class="${l === 1 ? "b" : "s"} ${q >= grande ? "big" : ""}"><span class="num muted">${new Intl.DateTimeFormat("es-EC", { timeZone: zona, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(t))}</span><span class="num">${px(p)}</span><span class="num">${q.toLocaleString("en-US")}</span></div>`).join("") || `<span class="muted">${wsOk ? "Esperando operaciones…" : "Conectando con MEXC…"}</span>`}</div></div>`;
  }

  // ---------- cabecera ----------
  function pintarCabecera() {
    const u = uni(sel), p = parD(sel), pr = vivo[sel] || (u && u.precio) || (p && p.precio), ch = u ? u.cambio : p && p.cambio24, l = serie.length > 60 ? IND.lectura(serie) : null;
    const a = serie.length > 20 ? IND.atr(serie).slice(-1)[0] / serie[serie.length - 1][4] : null;
    $("chead").innerHTML = `<div class="tit"><b>${esc(base(sel))}</b><small>/USDT perpetuo${p ? " · en el radar" : ""}</small></div>
      <div class="px num">${px(pr)} <span class="${cls(ch)}" style="font-size:14px">${pc(ch)}</span></div>
      <div class="st"><span class="label">Vol. 24h</span><span class="num">$${vol(u ? u.vol : p && p.volumen24)}</span></div>
      <div class="st"><span class="label">ATR ${tf}</span><span class="num">${a ? (a * 100).toFixed(2) + "%" : "–"}</span></div>
      <div class="st"><span class="label">Lectura ${tf}</span><span class="lect ${l ? cls2(l.tx) : "n"}">${l ? l.tx : "–"}</span></div>
      <div class="st"><span class="label">Cierre vela ${tf}</span><span class="num" id="cierre-h">${TF[tf].src === "tr" ? "–" : falta(proximoCierre(tf) - Date.now() / 1000)}</span></div>`;
    $("b-fav").textContent = favs.includes(sel) ? "★" : "☆";
  }
  function pintarTfs() {
    $("tfs").innerHTML = GRUPOS.map((g) => g.map((t) => `<button type="button" data-tf="${t}" aria-pressed="${t === tf}">${t}</button>`).join("")).join('<span class="sep"></span>');
    $("tfs").querySelectorAll("button").forEach((b) => b.onclick = () => { tf = b.dataset.tf; LS.set("tf", tf); pintarTfs(); pintarGrafico(); });
  }
  async function pintarGrafico() {
    if (!crear()) { $("nota").textContent = "No se pudo cargar la librería de gráficos."; return; }
    const mio = ++token, v = await obtener(sel, tf); if (mio !== token) return;
    serie = v.slice();
    const d = dec(serie.length ? serie[serie.length - 1][4] : 1);
    sC.applyOptions({ priceFormat: { type: "price", precision: d, minMove: Math.pow(10, -d) } });
    chart.timeScale().applyOptions({ secondsVisible: TF[tf].seg < 60, timeVisible: TF[tf].seg < 86400 });
    sC.setData(serie.map(([time, open, high, low, close]) => ({ time, open, high, low, close })));
    dibujarTodo();
    verUltimas(); aplicarEscala(true);
    pintarCabecera(); pintarNiveles();
    $("nota").innerHTML = TF[tf].src === "tr" ? `Velas de ${tf} armadas con cada operación de MEXC desde que abriste el panel (${(trades[sel] || []).length} recibidas).` : `Velas de Binance Futures como referencia de precio (la diferencia con MEXC es mínima); se actualizan cada 3 s. ${parD(sel) ? "Las señales del radar se calculan en 1H con datos de MEXC." : "Activo fuera del radar: solo análisis técnico."}`;
    if (!$("l-tec").hidden) pintarTecnico();
  }
  // vela en curso: cada 3 s desde Binance
  setInterval(async () => {
    if (!chart || TF[tf].src === "tr" || !serie.length || document.hidden || !$("v-mercado").classList.contains("on")) return;
    const t0 = tf, s0 = sel, k = await binance(sel, TF[tf].bn, 2); if (!k || t0 !== tf || s0 !== sel) return;
    let nueva = false;
    k.forEach((b) => { const u = serie[serie.length - 1]; if (u[0] === b[0]) serie[serie.length - 1] = b; else if (b[0] > u[0]) { serie.push(b); nueva = true; } else return; sC.update({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }); if (ON.vol) sV.update({ time: b[0], value: b[5], color: b[4] >= b[1] ? css("--up-soft") : css("--down-soft") }); });
    if (!vivo[sel]) vivo[sel] = serie[serie.length - 1][4];
    cache[sel + "|" + tf] = { t: Date.now(), v: serie };
    if (nueva) { dibujarTodo(); pintarNiveles(); } else { pintarInferior(); dibujarCapa(); }
    pintarCabecera();
  }, 3000);
  setInterval(() => { if (!$("v-mercado").classList.contains("on")) return; dibujarCapa(); const h = $("cierre-h"); if (h && TF[tf].src !== "tr") h.textContent = falta(proximoCierre(tf) - Date.now() / 1000); document.querySelectorAll("[data-cierre]").forEach((x) => x.textContent = falta(proximoCierre(x.dataset.cierre) - Date.now() / 1000)); }, 1000);

  // ---------- MEXC en vivo (precio, operaciones) ----------
  let ws, wsOk = false, wsSym = null;
  function suscribir() {
    if (!ws || ws.readyState !== 1) return;
    if (wsSym && wsSym !== sel) ws.send(JSON.stringify({ method: "unsub.deal", param: { symbol: wsSym } }));
    wsSym = sel; ws.send(JSON.stringify({ method: "sub.deal", param: { symbol: sel } })); ws.send(JSON.stringify({ method: "sub.ticker", param: { symbol: sel } }));
  }
  function conectar() {
    if (ws && ws.readyState <= 1) return;
    try { ws = new WebSocket("wss://contract.mexc.com/edge"); } catch (e) { return; }
    let ping;
    ws.onopen = () => { wsOk = true; (D ? D.pares : []).forEach((p) => ws.send(JSON.stringify({ method: "sub.ticker", param: { symbol: p.par } }))); wsSym = null; suscribir(); ping = setInterval(() => ws.readyState === 1 && ws.send('{"method":"ping"}'), 15000); pintarEstado(); };
    ws.onmessage = (m) => {
      let j; try { j = JSON.parse(m.data); } catch (e) { return; }
      if (j.channel === "push.ticker" && j.data) { vivo[j.data.symbol] = +j.data.lastPrice; }
      else if (j.channel === "push.deal" && j.data) { const s = j.symbol || sel, tr = trades[s] || (trades[s] = []); (Array.isArray(j.data) ? j.data : [j.data]).forEach((d) => tr.push([d.t, +d.p, +d.v, d.T])); if (tr.length > 20000) tr.splice(0, tr.length - 20000);
        if (s === sel && TF[tf].src === "tr") { const v = velasTrades(s, TF[tf].seg); if (!serie.length || v.length - serie.length > 1) pintarGrafico(); else { const b = v[v.length - 1]; if (serie.length && serie[serie.length - 1][0] === b[0]) serie[serie.length - 1] = b; else serie.push(b); sC.update({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }); } } }
    };
    ws.onclose = () => { wsOk = false; clearInterval(ping); pintarEstado(); setTimeout(conectar, 5000); };
  }
  setInterval(() => { if (!$("l-flujo").hidden) pintarFlujo(); }, 1500);
  setInterval(() => { if ($("v-mercado").classList.contains("on")) pintarLista(); }, 5000);

  function elegir(s) {
    sel = s; LS.set("sel", s); pintarLista(); pintarPlan(); pintarGrafico(); suscribir(); cargarClave(s);
    if (!$("l-der").hidden) pintarDerivados(); if (!$("l-flujo").hidden) pintarFlujo();
    if (innerWidth < 900) $("chead").scrollIntoView({ block: "start" });
  }

  // ---------- secciones con datos del servidor ----------
  function pintarEstado() {
    if (!D) return; const min = (Date.now() - new Date(D.generado)) / 60000, tipo = min < D.intervalo_min * 3 ? "" : min < 45 ? "warn" : "bad";
    $("status").innerHTML = `<span class="dot ${tipo}"></span><span>Análisis ${hace(D.generado)}${wsOk ? " · en vivo" : ""}</span>`;
  }
  function tarjeta(s, obs) {
    const p = vivo[s.par] || s.precio_actual, r = s.tps ? s.r_actual : s.r_actual, objs = s.objetivos || [s.objetivo];
    return `<button class="sig ${s.lado === 1 ? "" : "short"} ${obs ? "obs" : ""}" type="button" data-s="${esc(s.par)}"><div class="fila"><b style="font-size:16px">${esc(base(s.par))}</b>${ladoChip(s.lado)}${obs ? (s.candidata ? '<span class="chip accent">CANDIDATA</span>' : '<span class="chip">OBSERVACIÓN</span>') : (s.real || {}).estado === "abierta" ? '<span class="chip accent">REAL</span>' : '<span class="chip">PAPEL</span>'}${(s.contrarias || []).length ? '<span class="chip short">⚠ contraria</span>' : ""}<span class="when">${hace(s.creada)}</span></div>
      <div class="muted" style="font-size:12.5px">${esc(s.nombre)} · ${objs.length > 1 ? `TP ${s.tps || 0}/${objs.length}` : "1 objetivo"}</div>
      <div class="niv"><div><span class="label">${s.tps ? "Stop prot." : "Stop"}</span><span class="num ${s.tps ? "" : "down"}">${px(s.tps ? s.stop_actual : s.stop)}</span></div><div><span class="label">Entrada</span><span class="num">${px(s.entrada)}</span></div><div><span class="label">${objs.length > 1 ? "Siguiente TP" : "Objetivo"}</span><span class="num up">${px(objs[Math.min(s.tps || 0, objs.length - 1)])}</span></div></div>
      <div class="fila"><span class="muted num">Precio ${px(p)}</span><span class="num ${cls(r)}" style="margin-left:auto;font-weight:600">${R(r)}</span></div></button>`;
  }
  function pintarSenales() {
    const act = D.activas, obs = D.observando || [];
    $("nb-sen").hidden = !act.length; $("nb-sen").textContent = act.length;
    // Próximas: setups a los que les falta una sola condición (con o sin ventaja, siempre etiquetados)
    const prox = D.pares.flatMap((p) => p.estrategias.filter((e) => e.lado && e.total - e.cumplidas === 1 && !e.senal).map((e) => ({ p, e, falta: (e.condiciones.find((c) => !c[1]) || [""])[0] })))
      .sort((a, b) => (b.e.aprobada - a.e.aprobada) || (b.e.total_stats.exp_r - a.e.total_stats.exp_r));
    const tProx = prox.length ? `<div class="label" style="margin:16px 0 8px">Próximas posibles · les falta 1 condición al cierre de la vela de 1 hora</div><div class="panel scroll-x"><table class="t"><thead><tr><th>Par</th><th>Lado</th><th>Estrategia</th><th>Falta</th><th class="r">Historial</th><th>Ventaja</th></tr></thead><tbody>${prox.map(({ p, e, falta }) => `<tr data-par="${esc(p.par)}" style="cursor:pointer"><td><b>${esc(base(p.par))}</b></td><td>${ladoChip(e.lado)}</td><td>${esc(e.nombre)}</td><td style="white-space:normal;min-width:160px">${esc(falta)}</td><td class="num r ${cls(e.total_stats.exp_r)}">${R(e.total_stats.exp_r)}</td><td>${e.aprobada ? '<span class="chip long">sí · se avisa</span>' : '<span class="chip">no · solo estudio</span>'}</td></tr>`).join("")}</tbody></table></div>` : "";
    $("s-act").innerHTML = (act.length ? `<div class="tarjetas">${act.map((s) => tarjeta(s)).join("")}</div>`
      : `<div class="panel empty"><b>No hay señales con ventaja ahora.</b><span>Solo se avisan por Telegram las estrategias que ganaron con comisiones en un año de datos. Hoy ninguna lo logra, así que el radar no te manda nada para no hacerte perder. Abajo ves lo que el radar está mirando: ${obs.length} setups en observación (seguidos en papel) y ${prox.length} a punto de formarse. <b>Son solo para estudio, no para operar.</b></span></div>`)
      + (obs.some((s) => s.candidata) ? `<div class="label" style="margin:16px 0 8px">🟡 Candidatas · en validación (se avisan por Telegram)</div><div class="tarjetas">${obs.filter((s) => s.candidata).map((s) => tarjeta(s, true)).join("")}</div>` : "") + (!act.length && obs.some((s) => !s.candidata) ? `<div class="label" style="margin:16px 0 8px">En observación ahora · solo estudio</div><div class="tarjetas">${obs.filter((s) => !s.candidata).map((s) => tarjeta(s, true)).join("")}</div>` : "") + tProx;
    $("s-act").querySelectorAll("tr[data-par]").forEach((tr) => tr.onclick = () => { location.hash = "#mercado"; elegir(tr.dataset.par); });
    $("s-obs").innerHTML = obs.length ? `<div class="tarjetas">${obs.map((s) => tarjeta(s, true)).join("")}</div>` : '<div class="panel empty"><b>Nada en observación.</b></div>';
    const h = D.historial, tx = { objetivo: ["Todos los TP", "long"], stop: ["Stop", "short"], tiempo: ["Tiempo", ""], protegida: ["TP1 + protegida", "long"] };
    $("s-cer").innerHTML = h.length ? `<div class="panel scroll-x"><table class="t"><thead><tr><th>Cierre</th><th>Par</th><th>Lado</th><th>Tipo</th><th>Estrategia</th><th class="r">Entrada</th><th class="r">Salida</th><th>Resultado</th><th class="r">R</th></tr></thead><tbody>${h.map((s) => `<tr><td class="num">${fecha(s.t_cierre)}</td><td><b>${esc(base(s.par))}</b></td><td>${ladoChip(s.lado)}</td><td>${s.observacion ? '<span class="chip">Obs.</span>' : '<span class="chip accent">Señal</span>'}</td><td>${esc(s.nombre)}</td><td class="num r">${px(s.entrada)}</td><td class="num r">${px(s.salida)}</td><td><span class="chip ${(tx[s.estado] || [])[1] || ""}">${(tx[s.estado] || [s.estado])[0]}</span></td><td class="num r ${cls(s.r)}"><b>${R(s.r)}</b></td></tr>`).join("")}</tbody></table></div>` : '<div class="panel empty"><b>Todavía no hay operaciones cerradas.</b></div>';
    document.querySelectorAll("#v-senales .sig").forEach((b) => b.onclick = () => { location.hash = "mercado"; elegir(b.dataset.s); });
  }
  function pintarMatriz() {
    const claves = D.pares[0] ? D.pares[0].estrategias.map((e) => [e.clave, e.nombre]) : [];
    $("e-mx").innerHTML = `<div class="panel scroll-x"><table class="t matriz"><thead><tr><th>Par</th><th>Tendencia 4h</th>${claves.map(([, n]) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>${D.pares.map((p) => `<tr><td><b>${esc(base(p.par))}</b></td><td><span class="${p.tendencia === "alcista" ? "up" : p.tendencia === "bajista" ? "down" : "muted"}">${p.tendencia}</span></td>${p.estrategias.map((e) => `<td><button class="celda" type="button" data-s="${esc(p.par)}" data-k="${e.clave}"><span style="display:flex;justify-content:space-between"><span>${e.lado === 1 ? "▲ long" : "▼ short"} · ${e.cumplidas}/${e.total}</span><b style="color:${e.senal && e.aprobada ? "var(--up)" : e.aprobada ? "var(--accent)" : "var(--faint)"}">${e.senal && e.aprobada ? "SEÑAL" : e.aprobada ? "con ventaja" : "sin ventaja"}</b></span>${segs(e)}</button></td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    $("e-mx").querySelectorAll(".celda").forEach((b) => b.onclick = () => { estSel[b.dataset.s] = b.dataset.k; location.hash = "mercado"; elegir(b.dataset.s); });
    pintarHorarios();
    $("e-ges").innerHTML = `<div class="panel scroll-x"><table class="t"><thead><tr><th>Par</th><th>Estrategia</th><th>Gestión elegida</th><th class="r">Esperanza elegida</th><th class="r">La otra</th><th class="r">Llegan a TP1</th></tr></thead><tbody>${D.pares.flatMap((p) => p.estrategias.map((e) => `<tr><td><b>${esc(base(p.par))}</b></td><td>${esc(e.nombre)}</td><td><span class="chip ${e.gestion === "fija" ? "" : "accent"}">${e.gestion === "fija" ? "1 objetivo (2R)" : "3 objetivos"}</span></td><td class="num r ${cls(e.total_stats.exp_r)}">${R(e.total_stats.exp_r)}</td><td class="num r ${cls(e.alternativa && e.alternativa.exp_r)}">${e.alternativa ? R(e.alternativa.exp_r) : "–"}</td><td class="num r">${e.total_stats.tp ? Math.round(e.total_stats.tp[0] * 100) + "%" : "–"}</td></tr>`)).join("")}</tbody></table></div><p class="muted" style="font-size:12.5px">La gestión se elige con el 70 % más antiguo del año; el 30 % reciente sirve para confirmarla. Así no se escoge mirando el resultado final.</p>`;
  }
  let eqChart, eqS, orden = "exp";
  function pintarBacktest() {
    if (!D) return; const ap = D.backtest.filter((b) => b.aprobada), totR = D.curva.length ? D.curva[D.curva.length - 1][1] : 0, c = D.config;
    $("bt-sum").innerHTML = `<div class="panel kpi"><span class="label">Historial</span><span class="v">${c.dias} d</span><span class="s">velas de 1 hora de MEXC</span></div><div class="panel kpi"><span class="label">Aprobadas</span><span class="v">${ap.length}<span class="muted" style="font-size:.6em"> / ${D.backtest.length}</span></span><span class="s">pasan el filtro estadístico</span></div><div class="panel kpi"><span class="label">Costos</span><span class="v">${((c.comision + c.deslizamiento) * 200).toFixed(2)}%</span><span class="s">ida y vuelta por operación</span></div><div class="panel kpi"><span class="label">Total aprobadas</span><span class="v ${cls(totR)}">${R(totR)}</span><span class="s">suma del último año</span></div>`;
    const f = D.backtest.slice().sort((a, b) => orden === "exp" ? b.total.exp_r - a.total.exp_r : orden === "t" ? b.total.t - a.total.t : b.total.n - a.total.n);
    const th = (k, t) => `<th class="r"><button class="btn" style="padding:1px 6px;font-size:11px" data-o="${k}" type="button">${t}${orden === k ? " ↓" : ""}</button></th>`;
    $("bt-tab").innerHTML = `<table class="t"><thead><tr><th>Par</th><th>Estrategia</th>${th("n", "Ops")}<th class="r">Acierto</th>${th("exp", "Esperanza")}<th class="r">FB</th>${th("t", "t")}<th class="r">Reciente</th><th>Estado</th></tr></thead><tbody>${f.map((b) => `<tr><td><b>${esc(base(b.par))}</b></td><td>${esc(b.nombre)}</td><td class="num r">${b.total.n}</td><td class="num r">${Math.round(b.total.acierto * 100)}%</td><td class="num r ${cls(b.total.exp_r)}">${R(b.total.exp_r)}</td><td class="num r">${b.total.fb == null ? "∞" : b.total.fb.toFixed(2)}</td><td class="num r">${b.total.t.toFixed(1)}</td><td class="num r ${cls(b.oos.exp_r)}">${b.oos.n} · ${R(b.oos.exp_r)}</td><td style="white-space:normal;min-width:200px">${b.aprobada ? '<span class="chip long">aprobada</span>' : b.candidata ? '<span class="chip accent">candidata · se avisa</span>' : `<span class="muted" style="font-size:12px">${esc(b.motivos.join(" · "))}</span>`}</td></tr>`).join("")}</tbody></table>`;
    $("bt-tab").querySelectorAll("[data-o]").forEach((b) => b.onclick = () => { orden = b.dataset.o; pintarBacktest(); });
    if (!window.LightweightCharts || $("e-bt").hidden || !$("v-estrategias").classList.contains("on")) return;
    if (!eqChart) { eqChart = LightweightCharts.createChart($("equity"), Object.assign(tema(), { autoSize: true, handleScroll: false, handleScale: false, localization: { priceFormatter: (v) => v.toFixed(1) + "R" } })); eqS = eqChart.addBaselineSeries({ baseValue: { type: "price", price: 0 }, lineWidth: 2, priceLineVisible: false }); }
    const m = new Map(); D.curva.forEach(([t, v]) => m.set(t, v)); eqS.setData([...m].map(([time, value]) => ({ time, value }))); eqChart.timeScale().fitContent();
  }
  function pintarGrupos() {
    const G = D.grupos;
    const ayuda = `<p class="muted" style="font-size:12.5px;margin:10px 0 0">Reenvía a <b>@radar_freddy_bot</b> cada señal en cuanto la publique el grupo. El radar la sigue con velas de 5 minutos de MEXC y las mismas reglas para todos: se activa al tocar la entrada (si no la toca en 24 h no cuenta), 50 % en el TP1 y el resto con stop en la entrada hasta el último objetivo, comisiones incluidas. Así se mide a cada grupo con todas sus señales, no solo con las que publica como ganadas.</p>`;
    if (!G || !G.senales || !G.senales.length) { $("r-grupos").innerHTML = `<div class="panel empty"><b>Aún no hay señales de grupos.</b><span>Reenvía una señal a tu bot y aparecerá aquí en el siguiente análisis (5 minutos).</span></div>${ayuda}`; return; }
    const est = { pendiente: ["Esperando entrada", ""], abierta: ["Abierta", "accent"], cerrada: ["Cerrada", ""], no_activada: ["No se activó", ""], sin_datos: ["Sin datos MEXC", ""] };
    const mot = { stop: "Stop", objetivo: "Todos los TP", tp1_y_entrada: "TP1 + entrada", tiempo: "Tiempo" };
    $("r-grupos").innerHTML = `<div class="panel scroll-x"><table class="t"><thead><tr><th>Grupo</th><th class="r">Total</th><th class="r">Por señal</th><th class="r">Cerradas</th><th class="r">Ganadas</th><th class="r">Perdidas</th><th class="r">Abiertas</th><th class="r">Recibidas</th></tr></thead><tbody>${G.resumen.map((g) => `<tr><td><b>${esc(g.grupo)}</b></td><td class="num r ${cls(g.total_r)}"><b>${R(g.total_r)}</b></td><td class="num r ${cls(g.exp_r)}">${g.exp_r == null ? "–" : R(g.exp_r)}</td><td class="num r">${g.cerradas}</td><td class="num r">${g.ganadas}</td><td class="num r">${g.perdidas}</td><td class="num r">${g.abiertas}</td><td class="num r">${g.recibidas}</td></tr>`).join("")}</tbody></table></div>
      <div class="label" style="margin:16px 0 8px">Últimas señales recibidas</div>
      <div class="panel scroll-x"><table class="t"><thead><tr><th>Fecha</th><th>Grupo</th><th>Par</th><th>Lado</th><th class="r">Entrada</th><th class="r">Stop</th><th>Estado</th><th class="r">R</th></tr></thead><tbody>${G.senales.map((s) => `<tr><td class="num">${fecha(new Date(s.t * 1000).toISOString())}</td><td>${esc(s.grupo)}</td><td><b>${esc(base(s.par))}</b></td><td>${ladoChip(s.lado)}</td><td class="num r">${px(s.entrada)}</td><td class="num r">${px(s.stop)}</td><td><span class="chip ${(est[s.estado] || [])[1] || ""}">${s.estado === "cerrada" ? mot[s.motivo] || "Cerrada" : (est[s.estado] || [s.estado])[0]}${s.tp1 && s.estado === "abierta" ? " · TP1" : ""}</span></td><td class="num r ${cls(s.r ?? s.r_actual)}">${s.r != null ? R(s.r) : s.r_actual != null ? R(s.r_actual) : "–"}</td></tr>`).join("")}</tbody></table></div>${ayuda}`;
  }
  function pintarRendimiento() {
    const rd = D.rendimiento, ro = D.rendimiento_obs || {}, ap = D.backtest.filter((b) => b.aprobada).length, t = { alcista: 0, bajista: 0, lateral: 0 }; D.pares.forEach((p) => t[p.tendencia]++);
    $("kpis").innerHTML = `<div class="panel kpi"><span class="label">Señales activas</span><span class="v">${D.activas.length}</span><span class="s">${(D.observando || []).length} en observación</span></div>
      <div class="panel kpi"><span class="label">Resultado señales</span><span class="v ${cls(rd.total_r)}">${rd.n ? R(rd.total_r) : "–"}</span><span class="s">${rd.n ? `${rd.n} cerradas · ${Math.round(rd.acierto * 100)}% acierto` : "aún sin cerradas"}</span></div>
      <div class="panel kpi"><span class="label">Estrategias con ventaja</span><span class="v">${ap}<span class="muted" style="font-size:.6em"> / ${D.backtest.length}</span></span><span class="s">hoy</span></div>
      <div class="panel kpi"><span class="label">Tendencia 4h del radar</span><span class="v" style="font-size:18px"><span class="up">${t.alcista}▲</span> <span class="down">${t.bajista}▼</span> <span class="muted">${t.lateral}◆</span></span><span class="s">${D.pares.length} pares vigilados</span></div>`;
    const bloque = (x, lista) => `<div class="kpis"><div class="panel kpi"><span class="label">Cerradas</span><span class="v">${x.n || 0}</span></div><div class="panel kpi"><span class="label">Acierto</span><span class="v">${x.n ? Math.round(x.acierto * 100) + "%" : "–"}</span></div><div class="panel kpi"><span class="label">Total</span><span class="v ${cls(x.total_r)}">${x.n ? R(x.total_r) : "–"}</span><span class="s">${x.n ? usd(x.total_r * D.config.riesgo_usd) + " con $" + D.config.riesgo_usd + " por operación" : ""}</span></div><div class="panel kpi"><span class="label">Por operación</span><span class="v ${cls(x.exp_r)}">${x.n ? R(x.exp_r) : "–"}</span></div></div>${lista.length ? "" : '<div class="panel empty"><b>Sin operaciones cerradas todavía.</b></div>'}`;
    $("r-papel").innerHTML = bloque(rd, D.historial.filter((s) => !s.observacion)); $("r-obs").innerHTML = bloque(ro, D.historial.filter((s) => s.observacion));
    const rs = D.reales || [], est = { abierta: ["Abierta", "accent"], cerrada: ["Cerrada", ""], omitida: ["No abierta", ""], error: ["Error", "short"] };
    pintarGrupos();
    $("r-real").innerHTML = rs.length ? `<div class="panel scroll-x"><table class="t"><thead><tr><th>Fecha</th><th>Par</th><th>Lado</th><th>Estado</th><th class="r">Contratos</th><th class="r">Entrada</th><th class="r">Resultado</th><th>Detalle</th></tr></thead><tbody>${rs.map((x) => `<tr><td class="num">${fecha(x.t_cierre || x.t)}</td><td><b>${esc(base(x.par))}</b></td><td>${ladoChip(x.lado)}</td><td><span class="chip ${(est[x.estado] || [])[1] || ""}">${(est[x.estado] || [x.estado])[0]}</span></td><td class="num r">${x.vol ?? "–"}</td><td class="num r">${x.precio_entrada ? px(x.precio_entrada) : "–"}</td><td class="num r ${cls(x.pnl)}">${x.pnl != null ? usd(x.pnl) : "–"}</td><td class="muted" style="white-space:normal;min-width:200px">${esc(x.motivo || "")}</td></tr>`).join("")}</tbody></table></div>` : `<div class="panel empty"><b>Aún no hay operaciones con dinero real.</b><span>${esc((D.bot || {}).motivo || "")}</span></div>`;
  }
  function pintarHorarios() {
    const H = D.horarios || {}, nom = {}; D.backtest.forEach((b) => { nom[b.clave] = b.nombre; });
    const cols = ["todas", ...Object.keys(H).filter((k) => k !== "todas")];
    const filas = (H.todas || []).map((x) => x.franja);
    if (!filas.length) { $("e-hor").innerHTML = '<div class="panel empty"><b>Aún sin datos.</b><span>Se calcula con el próximo análisis.</span></div>'; return; }
    const celda = (k, f) => { const x = (H[k] || []).find((y) => y.franja === f); if (!x) return '<td class="num r muted">–</td>';
      return `<td class="num r ${cls(x.exp_r)}" title="${x.n} operaciones · t=${x.t} · antes ${R(x.exp_ins)} · reciente ${R(x.exp_oos)} (${x.n_oos})">${x.consistente ? "<b>" : ""}${R(x.exp_r)}${x.consistente ? " ✓</b>" : ""}<br><small class="muted">${x.n} ops</small></td>`; };
    const buenos = cols.flatMap((k) => (H[k] || []).filter((x) => x.consistente).map((x) => `${k === "todas" ? "Todas las estrategias" : nom[k] || k} en ${x.franja.toLowerCase()} (${R(x.exp_r)}, ${x.n} ops)`));
    $("e-hor").innerHTML = `<div class="panel" style="padding:12px 14px;margin-bottom:12px"><b>${buenos.length ? "Franjas con ventaja que se repite en ambos periodos:" : "Ninguna franja horaria ni día convierte una estrategia en ganadora de forma consistente."}</b>${buenos.length ? `<ul style="margin:6px 0 0 18px">${buenos.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}<p class="muted" style="margin:6px 0 0;font-size:12.5px">Resultado medio por operación según la hora de entrada (hora de Ecuador), sumando los 20 pares durante un año con comisiones. ✓ = positivo en la parte antigua y en la reciente, y distinguible del azar (t ≥ 2). Toca o pasa el cursor por una celda para ver el detalle.</p></div>
      <div class="panel scroll-x"><table class="t"><thead><tr><th>Franja</th>${cols.map((k) => `<th class="r">${esc(k === "todas" ? "Todas" : nom[k] || k)}</th>`).join("")}</tr></thead><tbody>${filas.map((f) => `<tr><td style="white-space:normal;min-width:150px">${esc(f)}</td>${cols.map((k) => celda(k, f)).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  function pintarBot() {
    const b = D.bot || {}, r = b.real || {}, pg = b.progreso || {};
    if (!b.modo) { $("bot").innerHTML = '<div class="panel empty">Sin datos del bot todavía.</div>'; return; }
    const et = { real: ["REAL", "operando con dinero real"], simulado: ["PAPEL", "sin dinero real"], lectura: ["SOLO LECTURA", "conectado a MEXC, sin enviar órdenes"], apagado: ["APAGADO", "sin operar"] }[b.modo] || [b.modo, ""];
    const cx = b.conexion, cuenta = !cx ? `<div class="panel kpi"><span class="label">Cuenta MEXC</span><span class="v muted">Sin conectar</span><span class="s">faltan las claves de API</span></div>`
      : !cx.ok ? `<div class="panel kpi"><span class="label">Cuenta MEXC</span><span class="v neg">Error</span><span class="s">${esc(cx.error || "")}</span></div>`
      : `<div class="panel kpi"><span class="label">Cuenta MEXC · ${b.ordenes ? "puede operar" : "solo lectura"}</span><span class="v">${cx.patrimonio.toFixed(2)} <span class="muted" style="font-size:.55em">USDT</span></span><span class="s">disponible ${cx.disponible.toFixed(2)} · no realizado <span class="${cls(cx.no_realizado)}">${usd(cx.no_realizado)}</span></span></div>`;
    $("bot-nota").textContent = b.configurado === "auto" ? "Pasa a dinero real solo cuando hay evidencia suficiente." : "Modo fijado: " + b.configurado;
    $("bot").innerHTML = `<div class="panel kpi"><span class="label">Modo</span><span class="v">${et[0]}</span><span class="s">${et[1]}</span></div>${cuenta}
      <div class="panel kpi"><span class="label">Progreso hacia real</span><span class="v">${pg.cerradas || 0}<span class="muted" style="font-size:.6em"> / ${pg.necesarias || 30}</span></span><div class="barra"><i style="width:${Math.min(1, (pg.cerradas || 0) / (pg.necesarias || 30)) * 100}%;background:var(--accent)"></i></div><span class="s">señales cerradas · ${R(pg.exp_r)} por op.</span></div>
      <div class="panel kpi"><span class="label">Hoy (real)</span><span class="v ${cls(r.hoy)}">${usd(r.hoy)}</span><span class="s">freno a −$${r.limite_dia}</span></div>
      <div class="panel kpi"><span class="label">Este mes (real)</span><span class="v ${cls(r.mes)}">${usd(r.mes)}</span><span class="s">freno a −$${r.limite_mes}</span></div>
      <div class="panel kpi"><span class="label">Posiciones reales</span><span class="v">${r.abiertas ?? 0}<span class="muted" style="font-size:.6em"> / ${r.max_posiciones ?? "–"}</span></span><span class="s">$${r.riesgo_usd} de riesgo · ${r.apalancamiento}x aislado</span></div>`;
    $("frenos").innerHTML = `<p style="margin:0 0 8px"><b>${esc(b.motivo || "")}</b></p><p class="muted" style="margin:0">El bot sigue en papel cada señal con ventaja. Solo usa dinero real cuando acumula ${pg.necesarias || 30} señales cerradas con resultado positivo, y se detiene si las últimas 20 pierden, si pierdes $${r.limite_dia} en el día o $${r.limite_mes} en el mes. Al tocar TP1 cierra la mitad; si el precio vuelve a la entrada, cierra el resto.</p>${cx && cx.ok && cx.posiciones.length ? `<div class="label" style="margin-top:14px">Tus posiciones abiertas en MEXC</div><div class="scroll-x"><table class="t"><thead><tr><th>Par</th><th>Lado</th><th class="r">Contratos</th><th class="r">Entrada</th><th class="r">Apal.</th><th class="r">Liquidación</th></tr></thead><tbody>${cx.posiciones.map((p) => `<tr><td><b>${esc(base(p.par || ""))}</b></td><td>${ladoChip(p.lado)}</td><td class="num r">${p.vol}</td><td class="num r">${px(p.entrada)}</td><td class="num r">${p.apal}x</td><td class="num r">${p.liquidacion ? px(p.liquidacion) : "–"}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
  }
  function pintarGuia() {
    const c = D ? D.config : {};
    $("g-como").innerHTML = `<p>Cada ${D ? D.intervalo_min : 5} minutos un servidor gratuito (GitHub) descarga de MEXC un año de velas de 1 hora de los ${D ? D.pares.length : 20} pares con más volumen, prueba tres estrategias con comisiones reales y publica todo aquí.</p>
      <h3>Dos filtros antes de avisarte</h3><p><b>1. Condiciones del mercado</b>: la estrategia debe cumplir todas sus condiciones en la última vela cerrada. <b>2. Ventaja comprobada</b>: en el último año debe ganar en el 70 % antiguo y en el 30 % reciente, con al menos 30 operaciones y un resultado que no se explique por azar (t ≥ ${c.min_t || 2}).</p>
      <h3>1 o 3 objetivos</h3><p>Cada estrategia prueba las dos formas de salir: un objetivo a 2R, o tres objetivos (TP1 1R cierra 50 % y el stop pasa a la entrada; TP2 2R cierra 30 %; TP3 3R el resto). Se queda con la que mejor funcionó en el 70 % antiguo.</p>
      <h3>Mercado</h3><p>El gráfico usa velas de Binance Futures para cualquier activo y temporalidad (de 1 minuto a 1 mes), y operaciones de MEXC en vivo para las velas de segundos y el flujo. El buscador incluye todos los perpetuos en USDT.</p>`;
    $("g-ind").innerHTML = `<dl>${FAM.flatMap(([, ops]) => ops).map(([, n, d]) => `<dt>${n}</dt><dd>${d}</dd>`).join("")}<dt>Lectura técnica</dt><dd>10 indicadores votan compra, venta o neutral en cada temporalidad; la confluencia es el promedio de 6 temporalidades.</dd><dt>Derivados</dt><dd>Funding, interés abierto, relación long/short y agresividad de compradores en Binance; índice de miedo y codicia.</dd></dl>`;
    $("g-riesgo").innerHTML = `<p>Arriesgas $${c.riesgo_usd || 1} por operación con ${c.apalancamiento || 3}x en margen aislado. 1R es lo que pierdes si toca el stop.</p><p>Las comisiones de API (${c.comision ? (c.comision * 100).toFixed(2) : "0.08"}% por lado más deslizamiento) se comen gran parte del beneficio en temporalidades cortas: por eso el radar no da señales de scalping.</p><p>Si ninguna estrategia tiene ventaja, el radar no te avisará nada. Es a propósito: no operar también protege tu dinero. Esto no es asesoría financiera.</p>`;
  }
  function pintarTodo() {
    zona = D.config.zona || zona; $("demo").hidden = !D.demo;
    pintarEstado(); pintarSenales(); pintarMatriz(); pintarRendimiento(); pintarBot(); pintarGuia(); pintarLista(); pintarPlan();
    if ($("v-estrategias").classList.contains("on")) pintarBacktest();
  }
  async function cargar() {
    try { const n = await get("data/datos.json?t=" + Date.now()); if (!D || n.generado !== D.generado) { const prim = !D; D = n; pintarTodo(); if (prim) { conectar(); dibujarCapa(); } } else pintarEstado(); }
    catch (e) { if (!D) $("status").innerHTML = '<span class="dot bad"></span><span>Sin datos del servidor</span>'; }
  }
  new MutationObserver(() => location.reload()).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  // ---------- inicio ----------
  if (!TF[tf]) tf = "1H";
  pintarTfs(); pintarIsel(); pintarLeyenda(); ir(); pintarGuia(); $("n-ind").textContent = Object.values(ON).filter(Boolean).length;
  cargar().then(() => { cargarUniverso(); pintarGrafico(); cargarClave(sel); conectar(); });
  setInterval(cargar, 60000); setInterval(pintarEstado, 30000); setInterval(cargarUniverso, 60000);
})();
