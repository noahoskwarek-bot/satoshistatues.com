// Satoshi Passport check-in core, shared by the home map (index.html) and every statue page (/<page>/).
// Loaded as a classic script before the page's own code, so these are page-wide globals.
// Same 150 m radius as the leaderboard server, same localStorage stamp key/format
// ({ "<slug>": { "date": "<ISO>" } }), same /api/checkin submission and GoatCounter "checkin/<slug>" event.
const CHECKIN_RADIUS_M = 150; // same radius the leaderboard server enforces
const PASSPORT_KEY = 'satoshiPassport.v1';
function fmtDate(iso) {
  try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); } catch (e) { return iso; }
}
function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000, toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1), dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
// "About N away" for a too-far check-in, rounded like the server's message (never exact metres): under 1 km to the
// nearest 50 m (under 500 m) or 100 m, never at or below the radius; 1–10 km whole km; above that 2 significant figures.
function roundedDist(m, above) {
  if (!isFinite(m) || m < 0) return 'some distance';
  if (m < 950) {
    const step = m < 475 ? 50 : 100;
    let r = Math.max(step, Math.round(m / step) * step);
    if (r <= (above || 0)) r = (Math.floor(above / step) + 1) * step;
    return r >= 1000 ? '1 km' : `${r} m`;
  }
  const km = m / 1000;
  if (km < 10) return `${Math.max(1, Math.round(km))} km`;
  const mag = Math.pow(10, Math.floor(Math.log10(km)) - 1);
  return `${(Math.round(km / mag) * mag).toLocaleString('en-US')} km`;
}
function fmtDist(m) {
  if (m < 1000) return `${Math.round(m)} m`;
  const km = m / 1000;
  return `${km < 10 ? km.toFixed(1) : Math.round(km).toLocaleString()} km`;
}
// Anonymous GoatCounter event per successful GPS check-in (no coordinates are sent).
function trackCheckin(s, tries) {
  const gc = window.goatcounter;
  if (gc && typeof gc.count === 'function') {
    try { gc.count({ path: 'checkin/' + s.slug, title: 'Check-in ' + s.name, event: true }); } catch (_) {}
  } else if ((tries || 0) < 20) {
    setTimeout(() => trackCheckin(s, (tries || 0) + 1), 500);
  }
}
const GEO_OPTS = { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 };
// ----- Location diagnostics & platform help -----
function detectPlatform() {
  const ua = navigator.userAgent || '';
  const iOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const inApp = /FBAN|FBAV|Instagram|\bLine\/|GSA\/|; wv\)|Twitter|TikTok|Snapchat/i.test(ua);
  if (inApp) {
    const m = ua.match(/FBAN|FBAV|Instagram|Line|GSA|Twitter|TikTok|Snapchat/i);
    const app = m ? ({ FBAN: 'Facebook', FBAV: 'Facebook', GSA: 'Google app' }[m[0]] || m[0]) : 'app';
    return { key: 'inapp', label: `in-app browser (${iOS ? 'iOS' : /Android/.test(ua) ? 'Android' : 'unknown OS'} · ${app})` };
  }
  if (iOS && /CriOS/.test(ua)) return { key: 'ios-chrome', label: 'iOS Chrome' };
  if (iOS && /FxiOS|EdgiOS|OPiOS/.test(ua)) return { key: 'ios-other', label: 'iOS browser (' + ua.match(/FxiOS|EdgiOS|OPiOS/)[0] + ')' };
  if (iOS && /Safari/.test(ua)) return { key: 'ios-safari', label: 'iOS Safari' };
  if (iOS) return { key: 'ios-other', label: 'iOS web view' };
  if (/Android/.test(ua) && /Chrome\//.test(ua)) return { key: 'android', label: 'Android Chrome' };
  if (/Android/.test(ua)) return { key: 'android', label: 'Android browser' };
  if (/Edg\//.test(ua)) return { key: 'desktop', label: 'desktop Edge' };
  if (/Firefox\//.test(ua)) return { key: 'desktop', label: 'desktop Firefox' };
  if (/Chrome\//.test(ua)) return { key: 'desktop', label: 'desktop Chrome' };
  if (/Safari\//.test(ua)) return { key: 'desktop', label: 'desktop Safari' };
  return { key: 'desktop', label: 'browser' };
}
async function geoPermissionState() {
  try {
    if (!navigator.permissions || !navigator.permissions.query) return 'n/a';
    const r = await Promise.race([
      navigator.permissions.query({ name: 'geolocation' }),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 1500))
    ]);
    return r.state;
  } catch (e) { return 'n/a'; }
}
function escHtml(t) {
  return String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function blockedHelp(pf) {
  switch (pf.key) {
    case 'ios-chrome': return `<ul>
      <li>iPhone <strong>Settings › Privacy &amp; Security › Location Services</strong>: on.</li>
      <li>Same screen › <strong>Chrome</strong>: <strong>While Using the App</strong>, and <strong>Precise Location</strong> on.</li>
      <li>Chrome may remember a "Don't Allow" for this site. Try an <strong>Incognito tab</strong>, or open the page in <strong>Safari</strong>.</li></ul>`;
    case 'ios-safari': return `<ul>
      <li>Tap <strong>aA</strong> in the address bar › <strong>Website Settings</strong> › <strong>Location</strong> › <strong>Allow</strong>.</li>
      <li>iPhone <strong>Settings › Apps › Safari › Location</strong>: Ask or Allow.</li>
      <li>Also check <strong>Settings › Privacy &amp; Security › Location Services</strong> is on.</li></ul>`;
    case 'ios-other': return `<ul>
      <li>iPhone <strong>Settings › Privacy &amp; Security › Location Services</strong>: on, and allowed for this browser.</li>
      <li>Or open the page in <strong>Safari</strong>.</li></ul>`;
    case 'inapp': return `<ul><li>Built-in app browsers often can't share your location. Use the menu (⋯) to <strong>open this page in Safari or Chrome</strong>.</li></ul>`;
    case 'android': return `<ul>
      <li>Tap the icon left of the address bar › <strong>Permissions › Location › Allow</strong>.</li>
      <li>Phone <strong>Settings › Location</strong>: on, and allowed for this browser.</li></ul>`;
    default: return `<ul>
      <li>Click the icon left of the address bar › <strong>Location › Allow</strong>, then reload.</li>
      <li>Make sure your computer's location services are on for this browser.</li></ul>`;
  }
}
async function geoErrorHtml(err) {
  const pf = detectPlatform();
  const perm = await geoPermissionState();
  const names = { 1: 'PERMISSION_DENIED', 2: 'POSITION_UNAVAILABLE', 3: 'TIMEOUT' };
  let main, help;
  if (err.code === 1) {
    main = pf.key === 'inapp'
      ? "This app's built-in browser blocked location access."
      : 'Location access was blocked for this site.';
    help = blockedHelp(pf);
  } else if (err.code === 3) {
    main = 'Finding your location took too long.';
    help = '<ul><li>Step outside or near a window and try again.</li><li>Check that Location Services are on.</li></ul>';
  } else {
    main = "We couldn't get your location right now.";
    help = '<ul><li>Check that Location Services are on, then try again.</li></ul>' + (pf.key === 'inapp' ? blockedHelp(pf) : '');
  }
  const diag = `Details: code ${err.code} (${names[err.code] || '?'}) · "${escHtml(err.message || '')}" · permission: ${perm} · secure: ${window.isSecureContext ? 'yes' : 'no'} · ${pf.label}`;
  return `${main}<details><summary>How to fix</summary>${help}</details><div class="geo-diag">${diag}</div>`;
}
const LB_API = window.SS_API || '';
const LB_DEVICE = 'satoshiDevice.v1', LB_NICK = 'satoshiNick.v1', LB_NICK_SKIP = 'satoshiNickSkip.v1', LB_CLAIMED = 'satoshiClaimed.v1';
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); return true; } catch (e) { return false; } }
function lbDevice() {
  let id = lsGet(LB_DEVICE);
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join(''));
    lsSet(LB_DEVICE, id);
  }
  return id;
}
async function lbPost(path, body) {
  const r = await fetch(LB_API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  let j = {};
  try { j = await r.json(); } catch (e) {}
  return { status: r.status, j };
}
function lbNickForm(intro) {
  return `<form class="lb-nick" data-lb-nick><div class="lb-nick-q">${intro}</div><div class="lb-nick-row"><input name="nick" maxlength="20" aria-label="Nickname or X handle" placeholder="Nickname or @handle" value="${escHtml(lsGet(LB_NICK) || '')}" autocomplete="nickname"><button type="submit">Save</button>${intro.includes('optional') ? '<button type="button" class="lb-skip" data-lb-skip>No thanks</button>' : ''}</div><div class="lb-nick-msg" aria-live="polite"></div></form>`;
}
// Ask the server to record the stamp. Rejections (too far, poor accuracy, rate limits) block the stamp;
// if the leaderboard can't be reached, the stamp is still saved locally.
async function lbSubmit(s, c) {
  if (!LB_API) return { html: '' };
  try {
    const { status, j } = await lbPost('/api/checkin', { device_id: lbDevice(), slug: s.slug, lat: c.latitude, lng: c.longitude, accuracy: c.accuracy });
    if (j.ok) {
      if (!j.already) s.checkins = Math.max((s.checkins || 0) + 1, 1);
      const me = j.me;
      let html = `<div class="lb-note">🏆 ${me && me.rank ? `You're <strong>#${me.rank}</strong> on the <a href="/leaderboard/">leaderboard</a> with ${me.stamps} stamp${me.stamps === 1 ? '' : 's'}.` : 'Saved to the <a href="/leaderboard/">leaderboard</a>.'}</div>`;
      if (j.pow && j.pow.me && j.pow.me.rank && j.pow.me.rank.label && !j.pow.ranked_up)
        html += `<div class="lb-note">👣 ${powStatus(j.pow.me)} on <a href="/proof-of-walk/">Proof of Walk</a></div>`;
      if (!(me && me.nickname) && !lsGet(LB_NICK_SKIP)) html += lbNickForm('Show a name or X handle on the leaderboard? (optional)');
      html += powRankUpHtml(j.pow);
      return { html };
    }
    if (status >= 400 && status < 500) return { rejected: true, html: `🏆 ${escHtml(j.message || "The check-in wasn't accepted.")}` };
    return { html: '<div class="lb-note">The leaderboard is unavailable right now, so this stamp is only in your passport.</div>' };
  } catch (e) {
    return { html: '<div class="lb-note">Couldn\'t reach the leaderboard, so this stamp is only in your passport.</div>' };
  }
}
// Proof of Walk: the Worker adds `pow` to the check-in reply only when POW_ENABLED is on. Three ranks: Confirmed (first
// stamp), Genesis Block (any 3 of the original 10), The Grand High Order (Genesis + 1 more statue anywhere).
// Progress: "N of 3 to Genesis".
// A new rank gets a short note plus the usual Share buttons (share.js) with the rank line.
function powStatus(me) {
  if (me.order) return `🏛️ <strong>Grand High Order</strong> · ${me.distinct_stamps} statues`;
  if (me.genesis) return '🧱 <strong>Genesis Block</strong> · stamp 1 more statue to join the Grand High Order';
  return `<strong>${me.genesis_progress} of ${me.genesis_at || 3} to Genesis</strong>`;
}
function powRankUpHtml(p) {
  if (!p || !p.ranked_up || !p.me || !p.me.share) return '';
  // Per-rank share page (static og:image card for crawlers; humans land on /proof-of-walk/).
  const slug = { confirmed: 'confirmed', genesis: 'genesis-block', order: 'grand-high-order' }[p.me.rank && p.me.rank.key];
  const url = location.origin + '/proof-of-walk/' + (slug ? `share/${slug}/` : '');
  const head = p.order_new
    ? `🏛️ <strong>The Grand High Order of Fellow Travelers!</strong> The Genesis Block plus 1 more statue${p.genesis_new ? ', and you mined the Genesis Block too' : ''}. It’s yours for good (<a href="/proof-of-walk/fellow-travelers/">the roll</a>).`
    : p.genesis_new
    ? `🧱 <strong>Genesis Block!</strong> ${p.me.genesis_at || 3} of the original 10 stamped (<a href="/proof-of-walk/fellow-travelers/#genesis">the roll</a>). Stamp 1 more statue, anywhere, to join the Grand High Order of Fellow Travelers.`
    : `👣 <strong>Confirmed</strong> on <a href="/proof-of-walk/">Proof of Walk</a>: ${p.me.genesis_progress} of ${p.me.genesis_at || 3} to Genesis.`;
  const share = window.SSShare ? window.SSShare.row(p.me.share, url, 'Share your rank')
    : `<div class="ci-share"><a class="btn" href="https://x.com/intent/post?text=${encodeURIComponent(p.me.share)}&url=${encodeURIComponent(url)}" target="_blank" rel="noopener noreferrer">𝕏 Share on X</a></div>`;
  return `<div class="lb-note pow-up">${head}</div>${share}`;
}
function lbNickPrompt() {
  const out = document.getElementById('geo-test-result');
  out.className = 'checkin-msg';
  out.innerHTML = lbNickForm('Your leaderboard name or X handle (2–20 letters, numbers, spaces, _ or -, or @handle):');
  const inp = out.querySelector('input'); if (inp) inp.focus();
}
document.addEventListener('submit', ev => {
  const f = ev.target.closest && ev.target.closest('[data-lb-nick]');
  if (!f) return;
  ev.preventDefault();
  const msg = f.querySelector('.lb-nick-msg'), v = f.nick.value;
  lbPost('/api/nickname', { device_id: lbDevice(), nickname: v }).then(({ j }) => {
    if (j.ok) {
      lsSet(LB_NICK, j.nickname || '');
      f.innerHTML = j.nickname ? `✓ Saved. You'll show as <strong>${escHtml(j.nickname)}</strong> on the <a href="/leaderboard/">leaderboard</a>.` : '✓ Name removed.';
    } else { msg.textContent = j.message || "Couldn't save that name."; }
  }).catch(() => { msg.textContent = "Couldn't reach the leaderboard."; });
}, true);
document.addEventListener('click', ev => {
  const b = ev.target.closest && ev.target.closest('[data-lb-skip]');
  if (!b) return;
  lsSet(LB_NICK_SKIP, '1');
  const f = b.closest('[data-lb-nick]'); if (f) f.remove();
}, true);
// ----- Check-in messages (same wording on the map and on statue pages) -----
const CHECKIN_NO_GEO = "Your browser can't share its location, so check-in isn't available here.";
function checkinOkHtml(s, saved, n, total) {
  return saved
    ? `🟠 Stamped! ${s.name} is in your passport. That's ${n} of ${total}.`
    : `🟠 You're here, but this browser won't let us save the stamp (private mode?).`;
}
function checkinTooFarHtml(s, d, accuracy) {
  const acc = accuracy && accuracy > CHECKIN_RADIUS_M ? ` (your location fix is only accurate to about ${fmtDist(accuracy)})` : '';
  return `So close… well, sort of! You're about <strong>${roundedDist(d, CHECKIN_RADIUS_M)}</strong> from ${s.name}${acc}. Get within ${CHECKIN_RADIUS_M} m to collect the stamp.`;
}
// ----- Statue page "📍 Check in here" box (build.py renders <div data-ss-checkin …>; the home page has none) -----
(function () {
  function init() {
    const box = document.querySelector('[data-ss-checkin]');
    if (!box) return;
    const d = box.dataset;
    const s = { slug: d.slug, name: d.name, city: d.city, label: d.label, page: d.page, lat: +d.lat, lng: +d.lng, checkins: +d.checkins || 0 };
    const checkable = (d.checkable || '').split(',').filter(Boolean);
    const btn = box.querySelector('[data-ss-checkin-btn]');
    const out = box.querySelector('.checkin-msg');
    const IDLE = btn.textContent;
    const load = () => { try { return JSON.parse(localStorage.getItem(PASSPORT_KEY)) || {}; } catch (e) { return {}; } };
    const visitedCount = p => checkable.filter(k => !!p[k]).length;
    const show = (cls, html) => { out.className = `checkin-msg ${cls}`; out.innerHTML = html; out.hidden = false; };
    function shareText(p) {
      const what = /^Satoshi Statue /.test(s.label || '') ? `Satoshi in ${s.city}` : `the ${s.name} in ${s.city}`;
      return `I found ${what} 🟠 ${visitedCount(p)}/${checkable.length} stamps on the Satoshi Passport @satoshistatue21`;
    }
    function shareRow(p) {
      const url = d.url;
      const more = `<div class="ci-share"><a class="btn" href="/?s=${s.page}">📤 Share card on the map</a><a class="btn" href="/#passport">🛂 My passport</a></div>`;
      // share.js (every statue page): share sheet + X with the check-in line. Older cached pages keep the X-only row.
      if (window.SSShare && d.shareName) return window.SSShare.row(`I just checked in at ${d.shareName} ⚡`, url, 'Share your check-in') + more;
      const x = `https://x.com/intent/post?text=${encodeURIComponent(shareText(p))}&url=${encodeURIComponent(url)}`;
      return `<div class="ci-share"><a class="btn" href="${x}" target="_blank" rel="noopener noreferrer">𝕏 Share on X</a><a class="btn" href="/?s=${s.page}">📤 Share card on the map</a><a class="btn" href="/#passport">🛂 My passport</a></div>`;
    }
    function collected(p) {
      btn.hidden = true;
      const st = box.querySelector('.ci-stamp');
      st.innerHTML = `✅ Stamp collected · ${fmtDate(p[s.slug].date)}`;
      st.hidden = false;
      const note = box.querySelector('.ci-note');
      if (note) note.innerHTML = 'Saved in your Satoshi Passport. <a href="/#passport">My passport</a> · <a href="/leaderboard/">Leaderboard</a>';
      box.classList.add('done');
    }
    function bumpCount() {
      const el = document.querySelector(`[data-count-slug="${s.slug}"]`);
      if (!el) return;
      const n = Math.max(s.checkins, +el.getAttribute('data-base') || 0);
      if (n > 0) { el.textContent = `👣 ${n} ${n === 1 ? 'person has' : 'people have'} checked in here`; el.hidden = false; }
    }
    const p0 = load();
    if (p0[s.slug]) collected(p0);
    btn.addEventListener('click', () => {
      if (!('geolocation' in navigator)) { show('warn', CHECKIN_NO_GEO); return; }
      btn.disabled = true; btn.textContent = '📡 Locating…';
      navigator.geolocation.getCurrentPosition(pos => {
        const { latitude, longitude, accuracy } = pos.coords;
        const dist = haversineM(latitude, longitude, s.lat, s.lng);
        if (dist <= CHECKIN_RADIUS_M) {
          btn.textContent = '🏆 Saving…';
          lbSubmit(s, pos.coords).then(r => {
            btn.disabled = false; btn.textContent = IDLE;
            if (r.rejected) { show('warn', r.html); return; }
            const p = load();  // re-read so stamps from other tabs are kept
            p[s.slug] = { date: new Date().toISOString() };
            trackCheckin(s);
            let saved;
            try { localStorage.setItem(PASSPORT_KEY, JSON.stringify(p)); saved = true; } catch (e) { saved = false; }
            if (saved) collected(p);
            bumpCount();
            show('ok', checkinOkHtml(s, saved, visitedCount(p), checkable.length) + r.html + (saved ? shareRow(p) : ''));
          });
        } else {
          btn.disabled = false; btn.textContent = IDLE;
          show('warn', checkinTooFarHtml(s, dist, accuracy));
        }
      }, err => {
        btn.disabled = false; btn.textContent = IDLE;
        geoErrorHtml(err).then(html => show('warn', html));
      }, GEO_OPTS);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
