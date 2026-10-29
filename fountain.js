// Satoshi Fountain widget (reverse fountain: a small Lightning giveaway for verified check-ins, plus separate tips).
// Loaded only on pilot statue pages and only when fountain.json "enabled" is true, after checkin.js.
// Amounts, budget and limits all come from the API; nothing here decides who gets paid.
(function () {
  var box = document.querySelector('[data-ss-fountain]');
  if (!box || !window.fetch) return;
  var API = box.getAttribute('data-api') || window.SS_API || '';
  var slug = box.getAttribute('data-slug'), name = box.getAttribute('data-name');
  var CLAIM_KEY = 'satoshiFountainClaim.v1';
  if (!API) return;
  var state = null, done = null;
  var $ = function (sel) { return box.querySelector(sel); };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var num = function (n) { return Number(n || 0).toLocaleString('en-US'); };
  function ago(iso) {
    var s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
    if (s < 90) return 'just now';
    if (s < 5400) return Math.round(s / 60) + ' min ago';
    if (s < 129600) return Math.round(s / 3600) + ' h ago';
    return Math.round(s / 86400) + ' d ago';
  }
  function getJSON(path) { return fetch(API + path, { cache: 'no-store' }).then(function (r) { return r.json(); }); }
  function postJSON(path, body) {
    return fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { j._status = r.status; return j; }); });
  }
  function device() { return typeof window.lbDevice === 'function' ? window.lbDevice() : null; }
  function savedClaim() {
    try {
      var c = JSON.parse(sessionStorage.getItem(CLAIM_KEY) || 'null');
      return c && c.slug === slug && c.exp > Date.now() ? c : null;
    } catch (e) { return null; }
  }
  // Capture the claim token the server adds to a successful GPS check-in at this statue.
  if (typeof window.lbPost === 'function') {
    var orig = window.lbPost;
    window.lbPost = function (path, body) {
      return orig.apply(this, arguments).then(function (res) {
        try {
          var f = res && res.j && res.j.fountain;
          if (path === '/api/checkin' && f && f.claim && body && body.slug === slug) {
            sessionStorage.setItem(CLAIM_KEY, JSON.stringify({ slug: slug, claim: f.claim, exp: Date.now() + f.expires_in * 1000 - 30000 }));
            setTimeout(render, 0);
          }
        } catch (e) {}
        return res;
      });
    };
  }
  function closedText(s) {
    if (s.paused) return 'The giveaway is paused at the moment.';
    if (s.giveaway_sats_left < s.payout_sats) return 'The giveaway budget has run out. Thanks for visiting!';
    return 'Today’s giveaway limit here has been reached. Try again tomorrow.';
  }
  function renderClaim() {
    var el = $('[data-f-claim]'), s = state;
    if (done) { el.innerHTML = done; return; }
    if (!s.open) { el.innerHTML = '<p class="f-msg">' + esc(closedText(s)) + '</p>'; return; }
    var c = savedClaim();
    if (!c) {
      el.innerHTML = '<p class="f-msg">Check in above (within 150 m) to get the giveaway. No tip needed.</p>';
      return;
    }
    el.innerHTML = '<form class="f-form" data-f-form novalidate>' +
      '<p class="f-q">✅ You’re checked in. Get ' + num(s.payout_sats) + ' sats sent to a Lightning address:</p>' +
      '<input name="addr" type="email" inputmode="email" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="120" placeholder="name@wallet.com" aria-label="Lightning address">' +
      '<label><input type="checkbox" name="adult"> I’m 18 or older</label>' +
      '<label><input type="checkbox" name="terms"> I accept the <a href="/terms/" target="_blank" rel="noopener">giveaway terms</a></label>' +
      '<button class="btn primary" type="submit">⚡ Send ' + num(s.payout_sats) + ' sats</button>' +
      '<p class="f-out" aria-live="polite"></p></form>';
  }
  function renderRecent() {
    var el = $('[data-f-recent]'), items = state.recent || [];
    if (!items.length) { el.innerHTML = '<p class="f-fine">No activity here yet.</p>'; return; }
    el.innerHTML = '<ul>' + items.map(function (x) {
      return '<li>' + (x.kind === 'payout'
        ? '⚡ ' + num(x.sats) + ' giveaway sats sent to ' + esc(x.who || 'a visitor')
        : '🧡 ' + num(x.sats) + ' sats tipped') + ' <span>· ' + esc(ago(x.at)) + '</span></li>';
    }).join('') + '</ul>';
  }
  function render() {
    if (!state) return;
    $('[data-f-left]').textContent = num(state.giveaway_sats_left);
    $('[data-f-tipped]').textContent = num(state.sats_tipped);
    box.querySelectorAll('[data-f-amount]').forEach(function (n) { n.textContent = num(state.payout_sats); });
    renderClaim();
    renderRecent();
    box.hidden = false;
  }
  function load() {
    return getJSON('/api/fountain?slug=' + encodeURIComponent(slug)).then(function (j) {
      if (!j || !j.ok || !j.enabled) { box.hidden = true; return; }
      state = j; render();
    }).catch(function () { box.hidden = true; });
  }
  box.addEventListener('submit', function (ev) {
    var f = ev.target.closest('[data-f-form]');
    if (!f) return;
    ev.preventDefault();
    var out = f.querySelector('.f-out'), c = savedClaim(), btn = f.querySelector('button');
    if (!c) { renderClaim(); return; }
    if (!f.adult.checked) { out.textContent = 'Please confirm you are 18 or older.'; return; }
    if (!f.terms.checked) { out.textContent = 'Please accept the giveaway terms.'; return; }
    btn.disabled = true; out.textContent = 'Sending…';
    postJSON('/api/fountain/claim', { device_id: device(), slug: slug, claim: c.claim, lightning_address: f.addr.value, adult: true, terms: true })
      .then(function (j) {
        if (j.ok) {
          sessionStorage.removeItem(CLAIM_KEY);
          done = '<p class="f-msg ok">⚡ ' + num(j.sats) + ' sats are on the way to ' + esc(j.to) + '. Enjoy your visit!' +
            (j.mock ? ' <span class="f-fine">(test mode: no real payment)</span>' : '') + '</p>';
          renderClaim();
          load();
        } else {
          out.textContent = j.message || 'Something went wrong. Please try again.';
          if (j.error === 'payout_unconfirmed') { sessionStorage.removeItem(CLAIM_KEY); return; }
          btn.disabled = false;
          if (['claim_used', 'checkin_stale', 'checkin_required', 'address_used', 'device_used'].indexOf(j.error) >= 0 && j.error !== 'address_used') sessionStorage.removeItem(CLAIM_KEY);
        }
      }).catch(function () { btn.disabled = false; out.textContent = 'Couldn’t reach the server. Please try again.'; });
  });
  // ----- Tips (separate from the giveaway) -----
  var poll = null;
  box.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-f-tip]');
    if (b) {
      var sats = +b.getAttribute('data-f-tip'), out = $('[data-f-tipout]');
      out.innerHTML = 'Creating a Lightning invoice…';
      postJSON('/api/fountain/tip', { slug: slug, sats: sats }).then(function (j) {
        if (!j.ok) { out.textContent = j.message || 'Tips aren’t available right now.'; return; }
        out.innerHTML = '<p class="f-q">Pay ' + num(j.sats) + ' sats with any Lightning wallet:' + (j.mock ? ' <span class="f-fine">(test mode: no real payment)</span>' : '') + '</p>' +
          '<textarea readonly rows="3" aria-label="Lightning invoice">' + esc(j.invoice) + '</textarea>' +
          '<div class="f-row"><a class="btn primary" href="lightning:' + esc(j.invoice) + '">⚡ Open in wallet</a><button class="btn" type="button" data-f-copy>Copy</button></div>' +
          '<p class="f-fine" data-f-tipstate>' + (j.verifiable === false ? 'Thank you! This tip can’t be confirmed automatically, so it won’t show in the sats tipped count.' : 'Waiting for payment…') + '</p>';
        clearInterval(poll);
        if (j.verifiable === false) return;
        var n = 0;
        poll = setInterval(function () {
          if (++n > 72) { clearInterval(poll); return; }
          getJSON('/api/fountain/tip?id=' + j.tip_id).then(function (t) {
            if (t.ok && t.status === 'paid') { clearInterval(poll); out.innerHTML = '<p class="f-msg ok">Thanks for the tip! 🧡</p>'; load(); }
          }).catch(function () {});
        }, 5000);
      });
      return;
    }
    var cp = ev.target.closest('[data-f-copy]');
    if (cp) {
      var ta = box.querySelector('[data-f-tipout] textarea');
      if (ta && navigator.clipboard) navigator.clipboard.writeText(ta.value).then(function () { cp.textContent = 'Copied'; });
    }
  });
  load();
})();
