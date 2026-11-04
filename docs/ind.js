// Indicadores técnicos. Velas: [t, open, high, low, close, volumen]. Devuelven arreglos
// alineados con las velas (null donde aún no hay datos suficientes).
const IND = (() => {
  const C = (v) => v.map((x) => x[4]);
  const sma = (a, n) => a.map((_, i) => { if (i < n - 1) return null; let s = 0; for (let j = i - n + 1; j <= i; j++) s += a[j]; return s / n; });
  const ema = (a, n) => { const k = 2 / (n + 1); let e = null, c = 0; return a.map((x) => { if (x == null) return null; c++; e = e == null ? x : x * k + e * (1 - k); return c >= n ? e : null; }); };
  const rma = (a, n) => { let e = null, c = 0, s = 0; return a.map((x) => { if (x == null) return null; c++; if (c <= n) { s += x; if (c === n) e = s / n; return e; } e = (e * (n - 1) + x) / n; return e; }); };
  const tr = (v) => v.map((x, i) => { const pc = i ? v[i - 1][4] : x[4]; return Math.max(x[2] - x[3], Math.abs(x[2] - pc), Math.abs(x[3] - pc)); });
  const atr = (v, n = 14) => rma(tr(v), n);
  function rsi(v, n = 14) {
    const c = C(v), up = [null], dn = [null];
    for (let i = 1; i < c.length; i++) { const d = c[i] - c[i - 1]; up.push(Math.max(d, 0)); dn.push(Math.max(-d, 0)); }
    const u = rma(up, n), d = rma(dn, n);
    return u.map((x, i) => x == null || d[i] == null ? null : 100 - 100 / (1 + x / (d[i] || 1e-12)));
  }
  function stochRsi(v, n = 14, k = 3, d = 3) {
    const r = rsi(v, n), raw = r.map((x, i) => { if (x == null || i < 2 * n) return null; const w = r.slice(i - n + 1, i + 1); const lo = Math.min(...w), hi = Math.max(...w); return hi - lo ? (x - lo) / (hi - lo) * 100 : 50; });
    const K = sma0(raw, k), D = sma0(K, d); return { k: K, d: D };
  }
  const sma0 = (a, n) => a.map((_, i) => { if (i < n - 1) return null; const w = a.slice(i - n + 1, i + 1); return w.some((x) => x == null) ? null : w.reduce((s, x) => s + x, 0) / n; });
  function macd(v, f = 12, s = 26, g = 9) {
    const c = C(v), a = ema(c, f), b = ema(c, s), m = a.map((x, i) => x != null && b[i] != null ? x - b[i] : null), sg = ema(m, g);
    return { m, sg, h: m.map((x, i) => x != null && sg[i] != null ? x - sg[i] : null) };
  }
  function bollinger(v, n = 20, k = 2) {
    const c = C(v), m = sma(c, n);
    const sd = c.map((_, i) => { if (i < n - 1) return null; let s = 0; for (let j = i - n + 1; j <= i; j++) s += (c[j] - m[i]) ** 2; return Math.sqrt(s / n); });
    return { m, up: m.map((x, i) => x == null ? null : x + k * sd[i]), lo: m.map((x, i) => x == null ? null : x - k * sd[i]) };
  }
  function keltner(v, n = 20, k = 1.5) { const m = ema(C(v), n), a = atr(v, 10); return { m, up: m.map((x, i) => x == null || a[i] == null ? null : x + k * a[i]), lo: m.map((x, i) => x == null || a[i] == null ? null : x - k * a[i]) }; }
  function vwap(v) { let dia = null, pv = 0, q = 0; return v.map(([t, , h, l, c, vol]) => { const d = Math.floor(t / 86400); if (d !== dia) { dia = d; pv = 0; q = 0; } pv += (h + l + c) / 3 * (vol || 0); q += vol || 0; return q ? pv / q : null; }); }
  function obv(v) { let o = 0; return v.map((x, i) => { if (i) o += x[4] > v[i - 1][4] ? x[5] : x[4] < v[i - 1][4] ? -x[5] : 0; return o; }); }
  function adx(v, n = 14) {
    const p = [0], m = [0];
    for (let i = 1; i < v.length; i++) { const u = v[i][2] - v[i - 1][2], d = v[i - 1][3] - v[i][3]; p.push(u > d && u > 0 ? u : 0); m.push(d > u && d > 0 ? d : 0); }
    const a = rma(tr(v), n), P = rma(p, n), M = rma(m, n);
    const pdi = P.map((x, i) => x == null || !a[i] ? null : 100 * x / a[i]), mdi = M.map((x, i) => x == null || !a[i] ? null : 100 * x / a[i]);
    const dx = pdi.map((x, i) => x == null || mdi[i] == null ? null : 100 * Math.abs(x - mdi[i]) / ((x + mdi[i]) || 1));
    const first = dx.findIndex((x) => x != null), ad = first < 0 ? dx : dx.slice(0, first).concat(rma(dx.slice(first), n));
    return { adx: ad, pdi, mdi };
  }
  function supertrend(v, n = 10, k = 3) {
    const a = atr(v, n), out = [], dir = []; let up = null, dn = null, d = 1;
    v.forEach((x, i) => {
      if (a[i] == null) { out.push(null); dir.push(0); return; }
      const hl = (x[2] + x[3]) / 2, bu = hl - k * a[i], bd = hl + k * a[i], pc = i ? v[i - 1][4] : x[4];
      up = up == null || pc < up ? bu : Math.max(bu, up); dn = dn == null || pc > dn ? bd : Math.min(bd, dn);
      if (d === 1 && x[4] < up) d = -1; else if (d === -1 && x[4] > dn) d = 1;
      out.push(d === 1 ? up : dn); dir.push(d);
    });
    return { linea: out, dir };
  }
  function ichimoku(v) {
    const mid = (i, n) => { if (i < n - 1) return null; let h = -Infinity, l = Infinity; for (let j = i - n + 1; j <= i; j++) { h = Math.max(h, v[j][2]); l = Math.min(l, v[j][3]); } return (h + l) / 2; };
    const ten = v.map((_, i) => mid(i, 9)), kij = v.map((_, i) => mid(i, 26)), sb = v.map((_, i) => mid(i, 52));
    const sa = ten.map((x, i) => x == null || kij[i] == null ? null : (x + kij[i]) / 2);
    return { ten, kij, sa, sb, desfase: 26 };   // las nubes se dibujan 26 velas adelante
  }
  // Pivotes de giro (máximos y mínimos locales)
  function giros(v, n = 3) {
    const out = [];
    for (let i = n; i < v.length - n; i++) {
      let hi = true, lo = true;
      for (let j = i - n; j <= i + n; j++) { if (v[j][2] > v[i][2]) hi = false; if (v[j][3] < v[i][3]) lo = false; }
      if (hi) out.push({ i, t: v[i][0], p: v[i][2], tipo: "H" }); if (lo) out.push({ i, t: v[i][0], p: v[i][3], tipo: "L" });
    }
    return out;
  }
  // Zonas de soporte / resistencia: giros agrupados (0.6 ATR); banda del toque más bajo al más alto
  function zonas(v) {
    if (!v || v.length < 30) return { res: [], sop: [] };
    const a = atr(v).slice(-1)[0], tol = 0.6 * a, precio = v[v.length - 1][4], gr = [];
    giros(v, v.length > 200 ? 5 : 3).sort((x, y) => x.p - y.p).forEach((q) => { const g = gr[gr.length - 1]; if (g && q.p - g.media <= tol) { g.q.push(q); g.media = g.q.reduce((s, x) => s + x.p, 0) / g.q.length; } else gr.push({ q: [q], media: q.p }); });
    const z = gr.filter((g) => g.q.length >= 2).map((g) => {
      let lo = Math.min(...g.q.map((x) => x.p)), hi = Math.max(...g.q.map((x) => x.p));
      if (hi - lo < 0.25 * a) { const m = (hi + lo) / 2; lo = m - 0.125 * a; hi = m + 0.125 * a; }
      const n = g.q.length; return { precio: g.media, lo, hi, toques: n, t0: Math.min(...g.q.map((x) => x.t)), fuerza: n >= 4 ? "fuerte" : n === 3 ? "media" : "débil" };
    });
    return { res: z.filter((x) => x.precio > precio).sort((x, y) => x.precio - y.precio).slice(0, 3), sop: z.filter((x) => x.precio < precio).sort((x, y) => y.precio - x.precio).slice(0, 3) };
  }
  // Liquidez: máximos o mínimos iguales (stops acumulados encima / debajo) aún no barridos
  function liquidez(v) {
    if (v.length < 40) return [];
    const a = atr(v).slice(-1)[0], g = giros(v, 3), out = [];
    ["H", "L"].forEach((tipo) => {
      const xs = g.filter((x) => x.tipo === tipo);
      for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) {
        if (Math.abs(xs[i].p - xs[j].p) > 0.15 * a) continue;
        const nivel = tipo === "H" ? Math.max(xs[i].p, xs[j].p) : Math.min(xs[i].p, xs[j].p);
        const barrido = v.slice(xs[j].i + 1).some((x) => tipo === "H" ? x[2] > nivel : x[3] < nivel);
        if (!barrido && !out.some((o) => o.tipo === tipo && Math.abs(o.p - nivel) < 0.3 * a)) out.push({ tipo, p: nivel, t0: xs[i].t });
      }
    });
    return out.slice(-6);
  }
  // Order blocks: última vela contraria antes de un impulso fuerte (> 2 ATR en 3 velas), sin mitigar
  function orderBlocks(v) {
    if (v.length < 40) return [];
    const a = atr(v), out = [];
    for (let i = 20; i < v.length - 3; i++) {
      if (a[i] == null) continue;
      const mov = v[i + 3][4] - v[i][4], alcista = mov > 2 * a[i], bajista = mov < -2 * a[i];
      if (alcista && v[i][4] < v[i][1]) out.push({ tipo: "alcista", lo: v[i][3], hi: v[i][2], t0: v[i][0], i });
      if (bajista && v[i][4] > v[i][1]) out.push({ tipo: "bajista", lo: v[i][3], hi: v[i][2], t0: v[i][0], i });
    }
    return out.filter((o) => !v.slice(o.i + 4).some((x) => o.tipo === "alcista" ? x[4] < o.lo : x[4] > o.hi)).slice(-4);
  }
  // Fair value gaps: hueco entre la vela i-2 y la i, sin rellenar
  function fvg(v) {
    const out = [];
    for (let i = 2; i < v.length; i++) {
      if (v[i][3] > v[i - 2][2]) out.push({ tipo: "alcista", lo: v[i - 2][2], hi: v[i][3], t0: v[i - 1][0], i });
      if (v[i][2] < v[i - 2][3]) out.push({ tipo: "bajista", lo: v[i][2], hi: v[i - 2][3], t0: v[i - 1][0], i });
    }
    return out.filter((g) => !v.slice(g.i + 1).some((x) => g.tipo === "alcista" ? x[3] <= g.lo : x[2] >= g.hi)).slice(-5);
  }
  // Fibonacci del último gran movimiento (máximo y mínimo de las últimas n velas)
  function fibo(v, n = 120) {
    const w = v.slice(-n); if (w.length < 20) return null;
    let iH = 0, iL = 0; w.forEach((x, i) => { if (x[2] > w[iH][2]) iH = i; if (x[3] < w[iL][3]) iL = i; });
    const hi = w[iH][2], lo = w[iL][3], subida = iL < iH;   // si el mínimo fue antes, el impulso fue alcista
    const niveles = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1].map((f) => ({ f, p: subida ? hi - (hi - lo) * f : lo + (hi - lo) * f }));
    return { subida, hi, lo, niveles, t0: w[Math.min(iH, iL)][0] };
  }
  // Pivotes clásicos con la vela diaria anterior
  function pivotes(d) { if (!d) return null; const [, , h, l, c] = d, p = (h + l + c) / 3; return { P: p, R1: 2 * p - l, S1: 2 * p - h, R2: p + (h - l), S2: p - (h - l), R3: h + 2 * (p - l), S3: l - 2 * (h - p) }; }
  // Perfil de volumen del rango visible: volumen por franja de precio y punto de control (POC)
  function perfil(v, franjas = 40) {
    if (v.length < 10) return null;
    const hi = Math.max(...v.map((x) => x[2])), lo = Math.min(...v.map((x) => x[3])), paso = (hi - lo) / franjas || 1, vol = new Array(franjas).fill(0);
    v.forEach((x) => { const a = Math.floor((x[3] - lo) / paso), b = Math.min(franjas - 1, Math.floor((x[2] - lo) / paso)), n = b - a + 1; for (let k = Math.max(0, a); k <= b; k++) vol[k] += (x[5] || 0) / n; });
    const poc = vol.indexOf(Math.max(...vol)); return { lo, paso, vol, poc: lo + (poc + 0.5) * paso };
  }
  // Divergencias RSI en los últimos giros
  function divergencias(v) {
    const r = rsi(v), g = giros(v, 3), out = [];
    ["H", "L"].forEach((tipo) => { const xs = g.filter((x) => x.tipo === tipo).slice(-2); if (xs.length < 2 || r[xs[0].i] == null) return; const [a, b] = xs;
      if (tipo === "H" && b.p > a.p && r[b.i] < r[a.i]) out.push({ tipo: "bajista", t: b.t, p: b.p, txt: "Divergencia bajista RSI" });
      if (tipo === "L" && b.p < a.p && r[b.i] > r[a.i]) out.push({ tipo: "alcista", t: b.t, p: b.p, txt: "Divergencia alcista RSI" }); });
    return out;
  }
  // Lectura técnica de una temporalidad: votos de 10 indicadores → de −1 (venta fuerte) a +1 (compra fuerte)
  function lectura(v) {
    if (!v || v.length < 60) return null;
    const c = C(v), n = v.length - 1, u = c[n], votos = [];
    const vt = (nombre, x, det) => votos.push({ nombre, x, det });
    const e20 = ema(c, 20)[n], e50 = ema(c, 50)[n], e200 = ema(c, 200)[n];
    vt("Precio vs EMA20", u > e20 ? 1 : -1, e20); vt("Precio vs EMA50", u > e50 ? 1 : -1, e50);
    if (e200 != null) vt("Precio vs EMA200", u > e200 ? 1 : -1, e200);
    vt("EMA20 vs EMA50", e20 > e50 ? 1 : -1);
    const r = rsi(v)[n]; vt("RSI 14", r > 55 ? 1 : r < 45 ? -1 : 0, r);
    const m = macd(v); vt("MACD", m.h[n] > 0 ? 1 : -1, m.h[n]);
    const s = stochRsi(v); const k = s.k[n], d = s.d[n]; if (k != null && d != null) vt("Stoch RSI", k > d && k < 85 ? 1 : k < d && k > 15 ? -1 : 0, k);
    const ad = adx(v); const A = ad.adx[n]; vt("ADX / DI", A < 20 ? 0 : ad.pdi[n] > ad.mdi[n] ? 1 : -1, A);
    const st = supertrend(v); vt("Supertrend", st.dir[n], st.linea[n]);
    const ic = ichimoku(v), j = n - 26; if (j > 0 && ic.sa[j] != null && ic.sb[j] != null) { const top = Math.max(ic.sa[j], ic.sb[j]), bot = Math.min(ic.sa[j], ic.sb[j]); vt("Nube Ichimoku", u > top ? 1 : u < bot ? -1 : 0); }
    const vw = vwap(v)[n]; if (vw) vt("VWAP", u > vw ? 1 : -1, vw);
    const total = votos.reduce((a, b) => a + b.x, 0) / votos.length;
    const tx = total >= 0.5 ? "Compra fuerte" : total >= 0.15 ? "Compra" : total <= -0.5 ? "Venta fuerte" : total <= -0.15 ? "Venta" : "Neutral";
    return { votos, total, tx, compras: votos.filter((x) => x.x > 0).length, ventas: votos.filter((x) => x.x < 0).length, neutros: votos.filter((x) => !x.x).length, rsi: r, adx: A };
  }
  return { sma, ema, atr, rsi, stochRsi, macd, bollinger, keltner, vwap, obv, adx, supertrend, ichimoku, giros, zonas, liquidez, orderBlocks, fvg, fibo, pivotes, perfil, divergencias, lectura };
})();
