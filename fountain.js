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
  // Payout rules come from the API: fixed (payout_sats) or a server-drawn amount (payout_min–payout_max + bonus_sats).
  function isRange(s) { return s.payout_mode !== 'fixed' && s.payout_max > 0; }
  function minPay(s) { return isRange(s) ? 1 : s.payout_sats; }
  function howMuch(s) {
    return isRange(s) ? num(s.payout_min) + '–' + num(s.payout_max) + ' sats' + (s.bonus_sats ? ', or the rare Lucky ' + num(s.bonus_sats) + ' bonus' : '')
      : 'a fixed ' + num(s.payout_sats) + ' sats';
  }
  var FREE = '<p class="f-free">Free to play. No purchase or tip necessary. A tip won’t improve your odds. 18+. <a href="/rules/">Official Rules</a></p>';
  function closedText(s) {
    if (s.paused) return 'The giveaway is paused at the moment.';
    if (s.giveaway_sats_left < minPay(s)) return 'The giveaway budget has run out. Thanks for visiting!';
    return 'Today’s giveaway limit here has been reached. Try again tomorrow.';
  }
  function renderClaim() {
    var el = $('[data-f-claim]'), s = state;
    if (done) { if (el.getAttribute('data-done') !== '1') { el.innerHTML = done; el.setAttribute('data-done', '1'); } return; }
    if (!s.open) { el.innerHTML = '<p class="f-msg">' + esc(closedText(s)) + '</p>'; return; }
    var c = savedClaim();
    if (!c) {
      el.innerHTML = '<p class="f-msg">Check in above (within 150 m) to get the giveaway. No tip needed.</p>';
      return;
    }
    var range = isRange(s);
    el.innerHTML = '<form class="f-form" data-f-form novalidate>' +
      '<p class="f-q">✅ You’re checked in. ' + (range ? 'Get ' + esc(howMuch(s)) + ' sent to a Lightning address:'
        : 'Get ' + num(s.payout_sats) + ' sats sent to a Lightning address:') + '</p>' +
      '<input name="addr" type="email" inputmode="email" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="120" placeholder="name@wallet.com" aria-label="Lightning address">' +
      '<label><input type="checkbox" name="adult"> I’m 18 or older</label>' +
      '<label><input type="checkbox" name="terms"> I accept the <a href="/terms/" target="_blank" rel="noopener">giveaway terms</a></label>' +
      '<button class="btn primary" type="submit">' + (range ? '⚡ Send the sats' : '⚡ Send ' + num(s.payout_sats) + ' sats') + '</button>' +
      (range ? FREE : '') +
      '<p class="f-out" aria-live="polite"></p></form>';
  }
  function renderRecent() {
    var el = $('[data-f-recent]'), items = (state.recent || []).filter(function (x) { return x.kind === 'payout'; });
    if (!items.length) { el.innerHTML = '<p class="f-fine">No activity here yet.</p>'; return; }
    el.innerHTML = '<ul>' + items.map(function (x) {
      return '<li>' + (x.kind === 'payout'
        ? (x.bonus ? '⚡ Lucky ' + num(x.sats) + '! ' + num(x.sats) + ' sats sent to ' : '⚡ ' + num(x.sats) + ' giveaway sats sent to ') + esc(x.who || 'a visitor')
        : '🧡 ' + num(x.sats) + ' sats tipped') + ' <span>· ' + esc(ago(x.at)) + '</span></li>';
    }).join('') + '</ul>';
  }
  function render() {
    if (!state) return;
    $('[data-f-left]').textContent = num(state.giveaway_sats_left);
    var hm = $('[data-f-howmuch]'); if (hm && (isRange(state) || state.payout_sats > 0)) hm.textContent = howMuch(state);
    // No tip pitch right after a claim: the support section stays hidden while the success screen shows.
    var sup = $('[data-f-support]'); if (sup) sup.hidden = !!done;
    renderClaim();
    renderRecent();
    var first = box.hidden;
    box.hidden = false;
    // Home-map callouts link to #giveaway; the box is hidden until the API answers, so scroll once it appears.
    if (first && location.hash === '#giveaway') box.scrollIntoView({ block: 'start' });
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
          if (j.payout_mode && j.payout_mode !== 'fixed') {
            done = successHtml(j);
            renderClaim(); render();
            roll($('[data-f-claim] .f-got'), j);
            load();
            return;
          }
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
  // ----- Success screen (server-drawn amounts) -----
  // The amount was already drawn and paid by the server (j.sats). The odometer is decoration only: it rolls each digit
  // and stops on that number. prefers-reduced-motion shows the final amount at once.
  var reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  function successHtml(j) {
    var lucky = !!j.bonus, digits = String(j.sats).split('');
    var odo = '<span class="f-odo" aria-hidden="true">' + digits.map(function (d, i) {
      var cyc = reduce ? 0 : digits.length - i, strip = '';
      for (var k = 0; k < cyc * 10 + (+d) + 1; k++) strip += '<span>' + (k % 10) + '</span>';
      var stop = cyc * 10 + (+d);
      return '<span class="d"><span class="s" data-stop="' + stop + '" style="transform:translateY(-' + stop + 'em)">' + strip + '</span></span>';
    }).join('') + '</span><span class="f-odo-unit" aria-hidden="true">sats</span>';
    var head = lucky ? 'Lucky ' + num(j.sats) + '! You got ' + num(j.sats) + ' sats!' : 'You got ' + num(j.sats) + ' sats!';
    // With motion, the headline (and the Lucky tag + glow) appear when the counter lands, not before.
    var later = reduce ? '' : ' style="visibility:hidden"';
    return '<div class="f-msg ok f-got' + (lucky && reduce ? ' f-lucky' : '') + '" role="status">' +
      (lucky ? '<div class="f-lucky-tag" data-f-land aria-hidden="true"' + later + '>⚡ Lucky ' + num(j.sats) + '!</div><br>' : '') +
      odo + '<p class="f-big" data-f-land' + later + '>' + esc(head) + '</p>' +
      '<p class="f-sub">On the way to ' + esc(j.to) + '. Enjoy your visit!' +
      (j.reduced ? ' That was the last of the giveaway sats for now.' : '') +
      (j.mock ? ' <span class="f-fine">(test mode: no real payment)</span>' : '') + '</p></div>';
  }
  function roll(card, j) {
    if (!card) return;
    var strips = card.querySelectorAll('.f-odo .s');
    strips.forEach(function (s) { s.style.transform = 'translateY(-' + (+s.getAttribute('data-stop')) + 'em)'; });
    if (reduce) return;
    // Start from 0 on every digit, then let the CSS transition (1.5 s) roll to the stop.
    strips.forEach(function (s) { s.style.transition = 'none'; s.style.transform = 'translateY(0)'; });
    void card.offsetHeight;
    strips.forEach(function (s) { s.style.transition = ''; s.style.transform = 'translateY(-' + (+s.getAttribute('data-stop')) + 'em)'; });
    setTimeout(function () {
      card.querySelectorAll('[data-f-land]').forEach(function (n) { n.style.visibility = ''; });
      if (j.bonus) { card.classList.add('f-lucky'); confetti(card); }
    }, 1500);
  }
  function confetti(card) {
    var colors = ['#f7931a', '#ffd28a', '#3fb950', '#e6edf3', '#58a6ff'];
    for (var i = 0; i < 28; i++) {
      var a = (i / 28) * Math.PI * 2, r = 90 + (i % 4) * 25, p = document.createElement('span');
      p.className = 'f-conf';
      p.style.background = colors[i % colors.length];
      p.style.setProperty('--x', Math.round(Math.cos(a) * r * 1.4) + 'px');
      p.style.setProperty('--y', Math.round(Math.sin(a) * r * 0.8) + 'px');
      p.style.setProperty('--r', (i % 2 ? '' : '-') + (180 + i * 17) + 'deg');
      p.style.setProperty('--dl', (i % 5) * 40 + 'ms');
      card.appendChild(p);
    }
    setTimeout(function () { card.querySelectorAll('.f-conf').forEach(function (n) { n.remove(); }); }, 2000);
  }
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
          '<p class="f-fine" data-f-tipstate>' + (j.verifiable === false ? 'Thank you! This tip can’t be confirmed automatically.' : 'Waiting for payment…') + '</p>';
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
