// Proof of Walk combined card (statue + rank + quote), design 2. Hand-written; the single renderer for every
// surface: the card reveal right after a check-in (checkin.js), "Your cards" on /proof-of-walk/, the print files and
// the generic share images (tools/render_combined_cards.mjs runs this same file in headless Chrome).
// Data: /proof-of-walk/card-data.js (built by build.py from statues.json + the 21 sayings). QR: /vendor/qrcode.js
// (MIT, Kazuhiko Arase). Fonts: Inter (site), IBM Plex Serif Medium Italic + IBM Plex Mono (OFL), all self-hosted.
// Layout: 1000 x 1400 units (5:7 = the 2.5 x 3.5 in trim). Print: 1650 x 2250 px = trim 1500 x 2100 at 600 dpi plus
// 1/8 in (75 px) bleed per side; all text and the QR stay inside the 1/8 in safe zone (50 units in from the trim).
// Card copy rules (spec §3.3 / Grant): no odds, luck, win, bet, worth, value, prize, "limited edition"; the card and
// the share text never mention the giveaway, tips or sats.
(function () {
  'use strict';
  var W = 1000, H = 1400, ORANGE = '#f7931a';
  var RANKS = { confirmed: 'confirmed', 'genesis-block': 'genesis', genesis: 'genesis', order: 'order', 'grand-high-order': 'order' };
  var V = (document.currentScript && (document.currentScript.src.split('?')[1] || '')) || '';
  var loaded = null, artCache = {};
  function D() { return window.POW_CARD_DATA; }
  function script(src) {
    return new Promise(function (ok, bad) { var s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
  }
  function font(fam, url, desc) { try { var f = new FontFace(fam, 'url(' + url + ')', desc); document.fonts.add(f); return f.load().catch(function () {}); } catch (e) { return Promise.resolve(); } }
  var CSS = '.pc{display:block;margin:12px 0}.pc-rank{text-align:center;font-size:.95rem;color:#e6edf3;margin:0 0 8px}.pc-rank strong{color:#f7931a}.pc-stage{max-width:420px;margin:0 auto}.pc-face{display:block;width:100%;height:auto;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.45)}.pc-face[hidden]{display:none}.pc-flip{display:flex;justify-content:center;gap:0;margin:10px auto 4px;width:max-content;border:1px solid #30363d;border-radius:999px;overflow:hidden}.pc-flip button{min-height:40px;padding:6px 18px;border:0;background:#161b22;color:#c9d1d9;font:600 .88rem inherit;font-family:inherit;cursor:pointer}.pc-flip button[aria-pressed=true]{background:#f7931a;color:#0d1117}.pc-share{max-width:420px;margin:10px auto 0;display:grid;gap:8px}.pc-main{width:100%;min-height:48px;font-size:1rem}.pc-fb{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.pc-fb .btn{justify-content:center;text-align:center;min-height:44px;font-size:.84rem;padding:8px 6px}.pc-hint{font-size:.78rem;color:#8b949e;margin:0;text-align:center}.pc-toast{display:block;color:#3fb950;font-weight:600;min-height:1em}.pc button.btn{font-family:inherit;cursor:pointer}.pc .btn.primary{background:#f7931a;color:#0d1117;border-color:#f7931a}.pc-print{max-width:420px;margin:14px auto 0;background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px 14px}.pc-print h3{font-size:1rem;color:#e6edf3;margin:0 0 4px}.pc-sub{font-size:.84rem;color:#c9d1d9;margin:0 0 8px}.pc-row{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:6px 0}.pc-row .btn{justify-content:center;text-align:center;min-height:44px;font-size:.84rem}.pc-row .pc-soon{grid-column:1/-1;opacity:.55;cursor:not-allowed;border-style:dashed}.pc-fine{font-size:.74rem;color:#8b949e;margin:6px 0 0}';
  function load() {
    if (loaded) return loaded;
    if (!document.getElementById('pc-css')) { var st = document.createElement('style'); st.id = 'pc-css'; st.textContent = CSS; document.head.appendChild(st); }
    loaded = Promise.all([
      window.POW_CARD_DATA ? 0 : script('/proof-of-walk/card-data.js' + (V ? '?' + V : '')),
      window.qrcode ? 0 : script('/vendor/qrcode.js'),
      font('PCInter', '/fonts/inter-500.woff', { weight: '500' }), font('PCInter', '/fonts/inter-800.woff', { weight: '800' }),
      font('PCSerif', '/fonts/plex-serif-500i.woff2', { style: 'italic', weight: '500' }),
      font('PCMono', '/fonts/plex-mono-500.woff2', { weight: '500' }), font('PCMono', '/fonts/plex-mono-600.woff2', { weight: '600' }),
    ]);
    return loaded;
  }
  function art(page) {
    if (!artCache[page]) artCache[page] = new Promise(function (ok) {
      var im = new Image(); im.decoding = 'async'; im.onload = function () { ok(im); }; im.onerror = function () { ok(null); };
      im.src = '/img/cards/art/' + page + '.jpg';
    });
    return artCache[page];
  }
  // ---------- data helpers ----------
  function rankKey(r) { return RANKS[r] || 'confirmed'; }
  function siteOrigin() { return /(^|\.)satoshistatues\.com$/.test(location.hostname) || location.protocol === 'file:' ? D().site : location.origin; }
  function verifyUrl(code) { return siteOrigin() + '/v/?c=' + encodeURIComponent(code); }
  function shareUrl(card) { var st = D().statues[card.slug]; return siteOrigin() + '/proof-of-walk/share/' + D().ranks[rankKey(card.rank)].share + '/' + st.page + '/'; }
  function shareText(card) {
    var st = D().statues[card.slug], k = rankKey(card.rank);
    var verb = { confirmed: 'got my first Proof of Walk stamp', genesis: 'earned Genesis Block', order: 'reached Grand High Order' }[k];
    return 'I walked to ' + st.phrase + ' and ' + verb + ' 🟧 #ProofOfWalk #Bitcoin satoshistatues.com';
  }
  function fileName(card) { return 'proof-of-walk-' + D().statues[card.slug].page + '-' + D().ranks[rankKey(card.rank)].share + '.png'; }
  var TZ_ABBR = { 'Europe/': { 'GMT+1': 'CET', 'GMT+2': 'CEST' }, 'Asia/Tokyo': { 'GMT+9': 'JST' }, 'Asia/Ho_Chi_Minh': { 'GMT+7': 'ICT' },
    'Asia/Hong_Kong': { 'GMT+8': 'HKT' }, 'America/New_York': { 'GMT-5': 'EST', 'GMT-4': 'EDT' }, 'America/El_Salvador': { 'GMT-6': 'CST' },
    'America/Argentina/Buenos_Aires': { 'GMT-3': 'ART' } };
  // Statue-local date/time (spec §2.10): { day: "31", mon: "Oct", year: "2026", hm: "14:22", tz: "CET" }
  function localParts(iso, tz) {
    var d = new Date(iso), o = {};
    try {
      new Intl.DateTimeFormat('en-GB', { timeZone: tz, day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
        .formatToParts(d).forEach(function (p) { o[p.type] = p.value; });
    } catch (e) { tz = 'UTC'; return localParts(iso, 'UTC'); }
    var off = 'UTC';
    try { off = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'shortOffset' }).formatToParts(d).filter(function (p) { return p.type === 'timeZoneName'; })[0].value; } catch (e) {}
    var key = Object.keys(TZ_ABBR).filter(function (k) { return tz === k || (k.slice(-1) === '/' && tz.indexOf(k) === 0); })[0];
    var ab = key && TZ_ABBR[key][off] || off;
    return { day: o.day, mon: (o.month || '').replace('.', '').slice(0, 3), year: o.year, hm: o.hour + ':' + o.minute, tz: ab };
  }
  // ---------- drawing helpers ----------
  function rr(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }
  function f(c, w, size, fam) { c.font = (fam === 'PCSerif' ? 'italic ' : '') + w + ' ' + size + 'px ' + fam + ', ' + (fam === 'PCMono' ? 'ui-monospace, Menlo, monospace' : fam === 'PCSerif' ? 'Georgia, serif' : 'Inter, system-ui, sans-serif'); }
  function spaced(c, text, x, y, sp, align) {   // letter-spaced text (canvas letterSpacing isn't everywhere yet)
    var ws = text.split('').map(function (ch) { return c.measureText(ch).width; });
    var tw = ws.reduce(function (a, b) { return a + b; }, 0) + sp * (text.length - 1);
    var sx = align === 'center' ? x - tw / 2 : align === 'right' ? x - tw : x, ta = c.textAlign; c.textAlign = 'left';
    text.split('').forEach(function (ch, i) { c.fillText(ch, sx, y); sx += ws[i] + sp; }); c.textAlign = ta; return tw;
  }
  function fit(c, text, maxW, size, w, fam, min) { for (; size > (min || 10); size -= 2) { f(c, w, size, fam); if (c.measureText(text).width <= maxW) break; } return size; }
  function wrap(c, text, maxW) {
    var words = String(text).split(' '), lines = [], cur = '';
    words.forEach(function (wd) { var t = cur ? cur + ' ' + wd : wd; if (c.measureText(t).width <= maxW || !cur) cur = t; else { lines.push(cur); cur = wd; } });
    if (cur) lines.push(cur); return lines;
  }
  function rng(seed) { var s = seed >>> 0 || 1; return function () { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
  function hsl(h, s, l, a) { return 'hsla(' + Math.round(h * 360) + ',' + s + '%,' + l + '%,' + (a == null ? 1 : a) + ')'; }
  var RAINBOW = ['#ff4d4d', '#ffb84d', '#f9ff4d', '#4dff88', '#4dc3ff', '#a64dff', '#ff4dd2'];
  function rainbow(c, x0, y0, x1, y1, a) { var g = c.createLinearGradient(x0, y0, x1, y1); RAINBOW.concat(RAINBOW[0]).forEach(function (col, i, arr) { g.addColorStop(i / (arr.length - 1), col); }); return g; }
  // Tier finish (spec §3.3): border fill + what goes over the art.
  function tierOf(n) { return n === 21 ? 'Legendary' : n === 20 ? 'Ultra rare' : n >= 17 ? 'Rare' : n >= 11 ? 'Uncommon' : 'Common'; }
  function borderFill(c, card, x, y, w, h) {
    var q = card.n ? D().quotes[card.n - 1] : null, t = card.n ? tierOf(card.n) : 'Generic', hue = q ? q.hue : 0.08, g;
    if (t === 'Generic') { g = c.createLinearGradient(x, y, x + w, y + h); g.addColorStop(0, '#6b3d0a'); g.addColorStop(.5, '#f2a541'); g.addColorStop(1, '#6b3d0a'); return g; }
    if (t === 'Common') { g = c.createLinearGradient(x, y, x + w, y + h); [[0, 28], [.22, 62], [.4, 36], [.6, 70], [.8, 34], [1, 58]].forEach(function (s) { g.addColorStop(s[0], hsl(hue, 38, s[1])); }); return g; }
    if (t === 'Uncommon') { g = c.createLinearGradient(x, y, x + w, y + h); g.addColorStop(0, hsl(hue, 65, 32)); g.addColorStop(.45, hsl(hue + .12, 80, 74)); g.addColorStop(.7, hsl(hue, 60, 42)); g.addColorStop(1, hsl(hue + .2, 70, 70)); return g; }
    return rainbow(c, x, y, x + w, y + h);
  }
  function sparkles(c, n, x, y, w, h, count) {
    var r = rng(n * 977 + 13); c.save(); c.fillStyle = '#fff';
    for (var i = 0; i < count; i++) {
      var sx = x + r() * w, sy = y + r() * h, s = 4 + r() * 10; c.globalAlpha = .5 + r() * .5;
      c.beginPath(); c.moveTo(sx, sy - s); c.lineTo(sx + s * .22, sy - s * .22); c.lineTo(sx + s, sy); c.lineTo(sx + s * .22, sy + s * .22);
      c.lineTo(sx, sy + s); c.lineTo(sx - s * .22, sy + s * .22); c.lineTo(sx - s, sy); c.lineTo(sx - s * .22, sy - s * .22); c.closePath(); c.fill();
    }
    c.restore();
  }
  function holo(c, card, x, y, w, h) {   // overlay on the art window
    var t = card.n ? tierOf(card.n) : 'Generic'; if (t === 'Generic' || t === 'Common') return;
    c.save(); c.globalCompositeOperation = 'screen';
    if (t === 'Uncommon') { var g = c.createLinearGradient(x, y + h * .2, x + w, y + h * .7); g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(.48, 'rgba(255,255,255,0)'); g.addColorStop(.52, 'rgba(255,255,255,.28)'); g.addColorStop(.56, 'rgba(255,255,255,0)'); g.addColorStop(1, 'rgba(255,255,255,0)'); c.fillStyle = g; c.fillRect(x, y, w, h); }
    else {
      var a = t === 'Rare' ? .11 : t === 'Ultra rare' ? .15 : .19, bands = t === 'Rare' ? 3 : 5;
      for (var i = 0; i < bands; i++) { c.globalAlpha = a; var ox = x - w + (i / bands) * w * 2.4; c.fillStyle = rainbow(c, ox, y, ox + w * .9, y + h); c.beginPath(); c.moveTo(ox, y); c.lineTo(ox + w * .35, y); c.lineTo(ox + w * .95, y + h); c.lineTo(ox + w * .6, y + h); c.closePath(); c.fill(); }
    }
    c.restore();
    if (t === 'Ultra rare') sparkles(c, card.n, x, y, w, h * .55, 14);
    if (t === 'Legendary') sparkles(c, card.n, x, y, w, h * .6, 24);
  }
  function frame(c, card, print) {
    // outer foil border (to the bleed edge on print) + dark panel + orange circuit frame
    c.fillStyle = borderFill(c, card, 0, 0, W, H);
    if (print) c.fillRect(-50, -50, W + 100, H + 100); else { rr(c, 0, 0, W, H, 36); c.fill(); }
    var t = card.n ? tierOf(card.n) : 'Generic';
    if (t === 'Ultra rare' || t === 'Legendary') {   // ripples
      c.save(); c.globalAlpha = .35; c.strokeStyle = '#fff'; c.lineWidth = 1.5;
      for (var i = -H; i < W + H; i += 22) { c.beginPath(); c.moveTo(i, 0); c.lineTo(i - H * .6, H); c.stroke(); }
      c.restore();
    }
    c.fillStyle = '#101217'; rr(c, 18, 18, W - 36, H - 36, 24); c.fill();
    if (t === 'Legendary') { c.strokeStyle = rainbow(c, W, 0, 0, H); c.lineWidth = 8; rr(c, 30, 30, W - 60, H - 60, 20); c.stroke();
      c.strokeStyle = '#e8c35a'; c.lineWidth = 3; rr(c, 42, 42, W - 84, H - 84, 16); c.stroke(); }
    c.strokeStyle = 'rgba(247,147,26,.85)'; c.lineWidth = 2.5;
    var m = t === 'Legendary' ? 54 : 44; rr(c, m, m, W - 2 * m, H - 2 * m, 14); c.stroke();
    c.lineWidth = 2; [[m + 14, m + 14, 1, 1], [W - m - 14, m + 14, -1, 1], [m + 14, H - m - 14, 1, -1], [W - m - 14, H - m - 14, -1, -1]].forEach(function (p) {
      c.beginPath(); c.moveTo(p[0], p[1] + p[3] * 70); c.lineTo(p[0], p[1]); c.lineTo(p[0] + p[2] * 70, p[1]); c.stroke();
      c.beginPath(); c.arc(p[0] + p[2] * 70, p[1], 4, 0, 7); c.fillStyle = ORANGE; c.fill();
    });
  }
  function pinGlyph(c, x, y, s) {
    c.save(); c.fillStyle = ORANGE; c.beginPath(); c.arc(x, y, s, Math.PI * .8, Math.PI * 2.2); c.lineTo(x, y + s * 1.7); c.closePath(); c.fill();
    c.fillStyle = '#fff'; f(c, 800, s * 1.15, 'PCInter'); c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('₿', x, y + 2); c.restore();
  }
  function shield(c, k, x, y, w, h) {
    var col = { confirmed: ['#4d74ad', '#26405f'], genesis: ['#3f8a4c', '#1d4a26'], order: ['#7a45ad', '#3a1a57'] }[k];
    var label = D().ranks[k].badge.split(' ');
    c.save(); c.shadowColor = 'rgba(0,0,0,.55)'; c.shadowBlur = 18; c.shadowOffsetY = 6;
    c.beginPath(); c.moveTo(x, y + 18); c.quadraticCurveTo(x + w / 2, y - 10, x + w, y + 18); c.lineTo(x + w, y + h * .58); c.quadraticCurveTo(x + w, y + h * .86, x + w / 2, y + h); c.quadraticCurveTo(x, y + h * .86, x, y + h * .58); c.closePath();
    var g = c.createLinearGradient(x, y, x, y + h); g.addColorStop(0, col[0]); g.addColorStop(1, col[1]); c.fillStyle = g; c.fill(); c.restore();
    c.save(); c.strokeStyle = '#e0a94a'; c.lineWidth = 5; c.stroke(); c.lineWidth = 1.5; c.strokeStyle = 'rgba(255,230,170,.6)';
    c.beginPath(); c.moveTo(x + 10, y + 26); c.quadraticCurveTo(x + w / 2, y + 2, x + w - 10, y + 26); c.stroke(); c.restore();
    var cx = x + w / 2; c.save(); c.fillStyle = '#fff'; c.strokeStyle = '#fff';
    if (k === 'genesis') { c.lineWidth = 13; c.lineCap = 'round'; c.lineJoin = 'round'; c.beginPath(); c.moveTo(cx - 34, y + 62); c.lineTo(cx - 8, y + 88); c.lineTo(cx + 38, y + 38); c.stroke(); }
    if (k === 'confirmed') { [[-20, 0], [18, -14]].forEach(function (p) { c.beginPath(); c.ellipse(cx + p[0], y + 72 + p[1], 12, 20, 0, 0, 7); c.fill(); [-8, -1, 6].forEach(function (t, i) { c.beginPath(); c.arc(cx + p[0] + t, y + 46 + p[1] - (i === 1 ? 4 : 0), 4.5, 0, 7); c.fill(); }); }); }
    if (k === 'order') { c.fillStyle = '#f2cc60'; c.beginPath(); c.moveTo(cx - 44, y + 52); c.lineTo(cx, y + 30); c.lineTo(cx + 44, y + 52); c.closePath(); c.fill(); [-32, -11, 10, 31].forEach(function (t) { c.fillRect(cx + t - 5, y + 56, 10, 34); }); c.fillRect(cx - 46, y + 92, 92, 8); }
    c.restore();
    c.fillStyle = '#fff'; c.textAlign = 'center'; c.textBaseline = 'alphabetic';
    var ty = y + 138, sz = label.length > 2 ? 26 : 30;
    label.forEach(function (wd, i) { fit(c, wd, w - 34, sz, 800, 'PCInter', 16); c.fillText(wd, cx, ty + i * (sz + 4)); });
    if (k === 'genesis') { c.fillStyle = '#e8763a'; for (var r = 0; r < 2; r++) for (var i = 0; i < 3 - r; i++) c.fillRect(cx - 34 + r * 12 + i * 24, y + h - 56 - r * 13, 21, 10); }
  }
  function seal(c, cx, cy, r) {
    c.save(); c.shadowColor = 'rgba(0,0,0,.55)'; c.shadowBlur = 18; c.shadowOffsetY = 6;
    var g = c.createRadialGradient(cx - r * .3, cy - r * .3, r * .1, cx, cy, r); g.addColorStop(0, '#f6d27a'); g.addColorStop(.7, '#c98a2c'); g.addColorStop(1, '#8a5a17');
    c.fillStyle = g; c.beginPath(); c.arc(cx, cy, r, 0, 7); c.fill(); c.restore();
    c.strokeStyle = '#5a3a0c'; c.lineWidth = 3; c.beginPath(); c.arc(cx, cy, r - 8, 0, 7); c.stroke(); c.beginPath(); c.arc(cx, cy, r * .52, 0, 7); c.stroke();
    c.fillStyle = '#3d2706'; f(c, 800, r * .2, 'PCInter'); c.textBaseline = 'middle';
    function arcText(text, start, end, rad, inv) {
      var n = text.length, step = (end - start) / (n - 1);
      for (var i = 0; i < n; i++) { var a = start + step * i; c.save(); c.translate(cx + Math.cos(a) * rad, cy + Math.sin(a) * rad); c.rotate(a + (inv ? -Math.PI / 2 : Math.PI / 2)); c.textAlign = 'center'; c.fillText(text[i], 0, 0); c.restore(); }
    }
    arcText('GPS VERIFIED', Math.PI * 1.2, Math.PI * 1.8, r * .73, false);
    arcText('PROOF OF WALK', Math.PI * .83, Math.PI * .17, r * .73, true);
    c.fillStyle = '#3d2706'; c.beginPath(); c.arc(cx, cy - r * .1, r * .26, Math.PI * .8, Math.PI * 2.2); c.lineTo(cx, cy + r * .36); c.closePath(); c.fill();
    c.strokeStyle = '#f6d27a'; c.lineWidth = r * .07; c.lineCap = 'round'; c.beginPath(); c.moveTo(cx - r * .12, cy - r * .1); c.lineTo(cx - r * .02, cy); c.lineTo(cx + r * .14, cy - r * .2); c.stroke();
  }
  // ---------- the two sides ----------
  async function front(c, card, o) {
    var d = D(), st = d.statues[card.slug], k = rankKey(card.rank), im = await art(st.page);
    frame(c, card, o.print);
    pinGlyph(c, W / 2, 86, 22);
    c.fillStyle = ORANGE; f(c, 800, 28, 'PCInter'); c.textBaseline = 'alphabetic'; spaced(c, 'SATOSHI STATUES', W / 2, 160, 7, 'center');
    c.fillStyle = '#f5f1e6'; var sz = fit(c, st.title, 820, 128, 800, 'PCInter', 60); c.textAlign = 'center'; c.fillText(st.title, W / 2, 160 + sz * .95 + 8);
    f(c, 500, 34, 'PCInter'); fit(c, st.subtitle, 640, 34, 500, 'PCInter', 22); c.fillStyle = '#e6edf3'; var sw = c.measureText(st.subtitle).width; c.fillText(st.subtitle, W / 2, 340);
    c.strokeStyle = 'rgba(247,147,26,.8)'; c.lineWidth = 2; [-1, 1].forEach(function (s) { c.beginPath(); c.moveTo(W / 2 + s * (sw / 2 + 22), 328); c.lineTo(W / 2 + s * (sw / 2 + 110), 328); c.stroke(); c.beginPath(); c.arc(W / 2 + s * (sw / 2 + 22), 328, 4, 0, 7); c.fillStyle = ORANGE; c.fill(); });
    var ax = 70, ay = 372, aw = 860, ah = 868;
    c.save(); rr(c, ax, ay, aw, ah, 18); c.clip();
    if (im) { var s = Math.max(aw / im.naturalWidth, ah / im.naturalHeight), iw = im.naturalWidth * s, ih = im.naturalHeight * s; c.drawImage(im, ax + (aw - iw) / 2, ay + ah - ih, iw, ih); }
    else { var gg = c.createLinearGradient(0, ay, 0, ay + ah); gg.addColorStop(0, '#3a2a4a'); gg.addColorStop(1, '#0d1117'); c.fillStyle = gg; c.fillRect(ax, ay, aw, ah); }
    holo(c, card, ax, ay, aw, ah);
    var sh = c.createLinearGradient(0, ay + ah * .62, 0, ay + ah); sh.addColorStop(0, 'rgba(10,12,16,0)'); sh.addColorStop(1, 'rgba(10,12,16,.55)'); c.fillStyle = sh; c.fillRect(ax, ay, aw, ah);
    c.restore();
    c.strokeStyle = 'rgba(247,147,26,.9)'; c.lineWidth = 3; rr(c, ax, ay, aw, ah, 18); c.stroke();
    shield(c, k, 92, 1004, 196, 248);
    seal(c, 812, 1128, 112);
    c.textAlign = 'center'; c.fillStyle = '#e6edf3'; f(c, 500, 28, 'PCInter');
    if (card.at && !o.generic) { var p = localParts(card.at, st.tz); spaced(c, 'CHECKED IN ' + p.day + ' ' + p.mon.toUpperCase() + ' ' + p.year, W / 2, 1290, 3, 'center'); }
    else spaced(c, 'A REAL WALK TO A REAL STATUE', W / 2, 1290, 3, 'center');
    c.fillStyle = ORANGE; f(c, 800, 32, 'PCInter'); c.fillText('satoshistatues.com', W / 2, 1338);
  }
  async function back(c, card, o) {
    var d = D(), st = d.statues[card.slug], q = d.quotes[(card.n || 1) - 1], t = tierOf(card.n || 1);
    frame(c, card, o.print);
    c.textAlign = 'center'; c.textBaseline = 'alphabetic'; c.fillStyle = ORANGE; f(c, 800, 30, 'PCInter'); var hw = spaced(c, 'PROOF OF WALK', W / 2, 118, 6, 'center');
    c.strokeStyle = 'rgba(247,147,26,.8)'; c.lineWidth = 2; [-1, 1].forEach(function (s) { c.beginPath(); c.moveTo(W / 2 + s * (hw / 2 + 24), 108); c.lineTo(W / 2 + s * (hw / 2 + 150), 108); c.stroke(); });
    // quote: auto-size into the 170..490 box; card 21 in monospace like the raw coinbase text
    var mono = card.n === 21, fam = mono ? 'PCMono' : 'PCSerif', wgt = mono ? 600 : 500, size = mono ? 50 : 72, lines, lh;
    for (; size >= 26; size -= 2) { f(c, wgt, size, fam); lines = wrap(c, mono ? q.q : '“' + q.q + '”', 790); lh = size * 1.22; if (lines.length * lh <= 310) break; }
    c.fillStyle = mono ? '#ffdf80' : '#f2ead8'; var y0 = 170 + (310 - lines.length * lh) / 2 + size * .9;
    lines.forEach(function (l, i) { c.fillText(l, W / 2, y0 + i * lh); });
    c.fillStyle = ORANGE; fit(c, '— ' + q.by, 800, 28, 500, 'PCInter', 18); c.fillText('— ' + q.by, W / 2, 536);
    // card-number box: NN / 21 · TIER + diamonds
    var nn = (card.n < 10 ? '0' : '') + card.n, dia = { Common: 1, Uncommon: 2, Rare: 3, 'Ultra rare': 4, Legendary: 5 }[t];
    f(c, 600, 26, 'PCMono'); var label = nn + ' / 21 · ' + t.toUpperCase(), lw = c.measureText(label).width, bw = lw + 40 + dia * 26 + 24;
    c.strokeStyle = 'rgba(247,147,26,.7)'; c.lineWidth = 2; rr(c, W / 2 - bw / 2, 566, bw, 54, 27); c.stroke();
    c.fillStyle = '#f5f1e6'; c.textAlign = 'left'; c.fillText(label, W / 2 - bw / 2 + 22, 602);
    c.fillStyle = t === 'Common' ? hsl(q.hue, 55, 62) : rainbow(c, 0, 0, W, 0);
    for (var i = 0; i < dia; i++) { var dx = W / 2 - bw / 2 + 22 + lw + 26 + i * 26, dy = 593; c.beginPath(); c.moveTo(dx, dy - 10); c.lineTo(dx + 9, dy); c.lineTo(dx, dy + 10); c.lineTo(dx - 9, dy); c.closePath(); c.fill(); }
    // GPS-verified check-in box
    c.textAlign = 'center'; c.strokeStyle = 'rgba(247,147,26,.9)'; c.lineWidth = 2.5; rr(c, 150, 648, 700, 206, 18); c.fillStyle = 'rgba(0,0,0,.35)'; c.fill(); c.stroke();
    c.fillStyle = ORANGE; f(c, 800, 26, 'PCInter'); spaced(c, 'GPS-VERIFIED CHECK-IN', W / 2, 694, 4, 'center');
    c.fillStyle = '#f5f1e6'; fit(c, st.label, 640, 32, 500, 'PCMono', 20); c.fillText(st.label, W / 2, 744);
    var p = card.at ? localParts(card.at, st.tz) : null;
    f(c, 500, 30, 'PCMono'); c.fillText(p ? p.day + ' ' + p.mon + ' ' + p.year + ' · ' + p.hm + ' ' + p.tz : 'Date shown on your card', W / 2, 790);
    fit(c, 'Verify code: ' + (card.code || 'PW-XXXX-XXXX'), 640, 30, 500, 'PCMono', 18); c.fillText('Verify code: ' + (card.code || 'PW-XXXX-XXXX'), W / 2, 834);
    // QR (EC level M, 4-module quiet zone) on a light tile: 300 units = 450 px on the print file
    var qx = 350, qy = 878, qs = 300; c.fillStyle = '#f5f1e6'; rr(c, qx, qy, qs, qs, 14); c.fill();
    if (window.qrcode) {
      var qr = window.qrcode(0, 'M'); qr.addData(verifyUrl(card.code || 'PW-XXXX-XXXX')); qr.make();
      var n = qr.getModuleCount(), m = qs / (n + 8); c.fillStyle = '#101217';
      for (var r = 0; r < n; r++) for (var col = 0; col < n; col++) if (qr.isDark(r, col)) c.fillRect(qx + (col + 4) * m, qy + (r + 4) * m, m + .3, m + .3);
    }
    c.fillStyle = '#e6edf3'; f(c, 500, 26, 'PCInter'); c.fillText('Scan to verify this stamp', W / 2, 1214);
    c.fillStyle = '#9aa3ad'; f(c, 500, 19, 'PCInter'); wrap(c, d.credit, 820).forEach(function (l, i) { c.fillText(l, W / 2, 1258 + i * 26); });
    if (o.sample) { c.save(); c.translate(W / 2, H / 2); c.rotate(-.5); c.fillStyle = 'rgba(247,147,26,.18)'; f(c, 800, 150, 'PCInter'); c.fillText('SAMPLE', 0, 50); c.restore(); }
  }
  // Render one side. size: 'portrait' (1000x1400), 'hd' (2000x2800), 'print' (1650x2250, bleed), or a number (width).
  async function render(canvas, side, card, o) {
    o = o || {}; await load();
    var print = o.size === 'print', scale = print ? 1.5 : o.size === 'hd' ? 2 : typeof o.size === 'number' ? o.size / W : 1;
    canvas.width = print ? 1650 : Math.round(W * scale); canvas.height = print ? 2250 : Math.round(H * scale);
    var c = canvas.getContext('2d'); c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, canvas.width, canvas.height);
    if (print) c.translate(75, 75); c.scale(scale, scale);
    await (side === 'back' ? back : front)(c, card, { print: print, generic: o.generic, sample: o.sample });
    return canvas;
  }
  function blob(canvas) { return new Promise(function (ok) { canvas.toBlob(ok, 'image/png'); }); }
  async function png(side, card, o) { return blob(await render(document.createElement('canvas'), side, card, o)); }
  // Generic share image (1200x630): the card front (no date, no code, no quote) over the blurred art.
  async function og(canvas, card) {
    await load(); var d = D(), st = d.statues[card.slug], k = rankKey(card.rank), im = await art(st.page);
    canvas.width = 1200; canvas.height = 630; var c = canvas.getContext('2d');
    c.fillStyle = '#0d1117'; c.fillRect(0, 0, 1200, 630);
    if (im) { c.save(); c.filter = 'blur(26px) brightness(.45)'; c.drawImage(im, -60, -400, 1320, 1760); c.restore(); }
    var fc = await render(document.createElement('canvas'), 'front', { slug: card.slug, rank: card.rank }, { size: 430, generic: true });
    c.save(); c.shadowColor = 'rgba(0,0,0,.6)'; c.shadowBlur = 30; c.drawImage(fc, 64, 14, 430, 602); c.restore();
    c.textAlign = 'left'; c.textBaseline = 'alphabetic'; c.fillStyle = ORANGE; f(c, 800, 24, 'PCInter'); spaced(c, 'PROOF OF WALK', 548, 150, 5);
    c.fillStyle = '#fff'; var t1 = d.ranks[k].label; fit(c, t1, 600, 64, 800, 'PCInter', 36); c.fillText(t1, 546, 228);
    var t2 = 'at ' + st.og_place; fit(c, t2, 600, 40, 800, 'PCInter', 26); c.fillStyle = '#f2cc60'; c.fillText(t2, 548, 284);
    c.fillStyle = '#e6edf3'; f(c, 500, 30, 'PCInter'); wrap(c, 'A real walk to a real statue, verified by GPS.', 590).forEach(function (l, i) { c.fillText(l, 548, 352 + i * 40); });
    c.fillStyle = '#c9d1d9'; f(c, 500, 26, 'PCInter'); wrap(c, 'Start your Proof of Walk passport. Free, no sign-up.', 590).forEach(function (l, i) { c.fillText(l, 548, 446 + i * 36); });
    c.fillStyle = ORANGE; f(c, 800, 34, 'PCInter'); c.fillText('satoshistatues.com', 548, 570);
    return canvas;
  }
  // ---------- UI: card view with flip, Share (Web Share API Level 2 + fallbacks) and Get a print ----------
  var esc = function (t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (ch) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]; }); };
  var IOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  function toast(el, msg) { var t = el.querySelector('.pc-toast'); if (!t) return; t.textContent = msg; clearTimeout(t._t); t._t = setTimeout(function () { t.textContent = ''; }, 2200); }
  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return false; });
    var ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.top = '-1000px'; document.body.appendChild(ta); ta.select();
    var ok = false; try { ok = document.execCommand('copy'); } catch (e) {} ta.remove(); return Promise.resolve(ok);
  }
  function analytics(method) { try { if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path: 'pow-share-' + method, title: 'Proof of Walk share: ' + method, event: true }); } catch (e) {} }
  async function mount(el, card, opt) {
    opt = opt || {}; await load(); var d = D(); if (!d.statues[card.slug]) { el.hidden = true; return; }
    var k = rankKey(card.rank), url = shareUrl(card), text = shareText(card), name = fileName(card);
    el.classList.add('pc');
    el.innerHTML = '<p class="pc-rank">' + d.ranks[k].emoji + ' <strong>' + esc(d.ranks[k].label) + ' ✓</strong> · ' + esc(d.statues[card.slug].label) + '</p><div class="pc-stage"><canvas class="pc-face" data-side="front" role="img" aria-label="Your ' + esc(d.ranks[k].label) + ' card, front: ' + esc(d.statues[card.slug].label) + '"></canvas>' +
      '<canvas class="pc-face" data-side="back" hidden role="img" aria-label="Your card, back: card ' + card.n + ' of 21, verify code ' + esc(card.code || '') + '"></canvas></div>' +
      '<div class="pc-flip" role="group" aria-label="Card side"><button type="button" data-flip="front" aria-pressed="true">Front</button><button type="button" data-flip="back" aria-pressed="false">Back</button></div>' +
      '<div class="pc-share"><button class="btn primary pc-main" type="button" data-pc="share">📤 Share</button>' +
      '<div class="pc-fb"><a class="btn" data-pc="x" href="' + esc('https://x.com/intent/post?text=' + encodeURIComponent(text) + '&url=' + encodeURIComponent(url)) + '" target="_blank" rel="noopener noreferrer">𝕏 Post on X</a>' +
      '<a class="btn" data-pc="save" href="#" download="' + esc(name) + '">⬇️ Save image</a><button class="btn" type="button" data-pc="copy">🔗 Copy link</button></div>' +
      '<p class="pc-hint">Your card shows your check-in date and verify code. <span class="pc-toast" role="status" aria-live="polite"></span></p></div>' +
      '<section class="pc-print" aria-labelledby="pc-print-h-' + k + '"><h3 id="pc-print-h-' + k + '">🖨️ Get a print</h3>' +
      '<p class="pc-sub">Print it yourself: print-ready files for the front and back, 1650 × 2250 px each (2.5 × 3.5 in card at 600 dpi, with 1/8 in bleed on every side). Trim to 2.5 × 3.5 in.</p>' +
      '<div class="pc-row"><button class="btn" type="button" data-print="front">⬇️ Front (print PNG)</button><button class="btn" type="button" data-print="back">⬇️ Back (print PNG)</button></div>' +
      '<div class="pc-row"><button class="btn pc-soon" type="button" disabled aria-disabled="true">Order a printed card, coming soon</button></div>' +
      '<p class="pc-fine">' + esc(d.print_note) + '</p><p class="pc-fine">' + esc(d.not_affiliated) + '</p></section>';
    var faces = el.querySelectorAll('.pc-face');
    await Promise.all([render(faces[0], 'front', card, { size: 'portrait' }), render(faces[1], 'back', card, { size: 'portrait' })]);
    el.querySelectorAll('[data-flip]').forEach(function (b) {
      b.addEventListener('click', function () { var s = b.getAttribute('data-flip'); faces[0].hidden = s !== 'front'; faces[1].hidden = s !== 'back';
        el.querySelectorAll('[data-flip]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); }); });
    });
    // Pre-render the PNG now so navigator.share runs inside the tap's user activation (iOS drops it after a slow fetch).
    var fileBlob = await blob(faces[0]), file = null, blobUrl = URL.createObjectURL(fileBlob);
    try { file = new File([fileBlob], name, { type: 'image/png' }); } catch (e) {}
    var save = el.querySelector('[data-pc="save"]'); save.href = blobUrl;
    save.addEventListener('click', function (ev) { analytics('save'); if (IOS) { ev.preventDefault(); var w = window.open(blobUrl, '_blank'); if (!w) location.href = blobUrl; toast(el, 'Press and hold the image to save it.'); } });
    el.querySelector('[data-pc="x"]').addEventListener('click', function () { analytics('x-intent'); });
    el.querySelector('[data-pc="copy"]').addEventListener('click', function () { analytics('copy'); copy(url).then(function (ok) { toast(el, ok ? 'Link copied' : url); }); });
    el.querySelector('[data-pc="share"]').addEventListener('click', function () {
      var p = null;
      try {
        if (file && navigator.canShare && navigator.canShare({ files: [file] })) { p = navigator.share({ files: [file], text: text + ' ' + url, title: 'Proof of Walk' }).then(function () { analytics('shared-file'); }); }
        else if (navigator.share) { p = navigator.share({ text: text, url: url, title: 'Proof of Walk' }).then(function () { analytics('shared-link'); }); }
      } catch (e) { p = Promise.reject(e); }
      if (!p) { el.classList.add('pc-nofile'); toast(el, 'Sharing isn’t available in this browser. Use the buttons below.'); return; }
      p.catch(function (e) { if (!e || e.name !== 'AbortError') { el.classList.add('pc-nofile'); toast(el, 'Use the buttons below to share.'); } });
    });
    el.querySelectorAll('[data-print]').forEach(function (b) {
      b.addEventListener('click', async function () {
        var side = b.getAttribute('data-print'), idle = b.textContent; b.disabled = true; b.textContent = 'Preparing…';
        var bl = await png(side, card, { size: 'print' }), u = URL.createObjectURL(bl), a = document.createElement('a');
        a.href = u; a.download = name.replace('.png', '-' + side + '-print-1650x2250.png'); document.body.appendChild(a);
        if (IOS) window.open(u, '_blank'); else a.click(); a.remove(); b.disabled = false; b.textContent = idle; analytics('print-' + side);
      });
    });
    return el;
  }
  window.PowCard = { load: load, render: render, png: png, og: og, mount: mount, shareUrl: shareUrl, shareText: shareText, localParts: localParts, rankKey: rankKey };
})();
