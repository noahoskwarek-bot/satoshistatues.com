// Share buttons for statue pages: a phone share sheet (navigator.share, with a copy-link fallback) and Share on X.
// Hand-written, loaded on every statue page. Same X intent and copy logic as the home page (index.html xIntent/copyText).
// Static buttons come from build.py; checkin.js and fountain.js add a share prompt with SSShare.row(text, url, label).
// Share text never includes tip amounts or Lightning addresses.
(function () {
  var esc = function (t) { return String(t).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  function xIntent(text, url) { return 'https://x.com/intent/post?text=' + encodeURIComponent(text) + '&url=' + encodeURIComponent(url); }
  function legacyCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', '');
    ta.style.position = 'fixed'; ta.style.top = '-1000px';
    document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, text.length);
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) {}
    ta.remove();
    return ok;
  }
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return legacyCopy(text); });
    }
    return Promise.resolve(legacyCopy(text));
  }
  function row(text, url, label) {
    return '<div class="ss-share" role="group" aria-label="' + esc(label || 'Share') + '">' +
      (label ? '<span class="ss-share-q">' + esc(label) + '</span>' : '') +
      '<button class="btn" type="button" data-ss-share data-text="' + esc(text) + '" data-url="' + esc(url) + '" aria-label="Share with your phone’s share sheet, or copy the link">📤 Share</button>' +
      '<a class="btn" href="' + esc(xIntent(text, url)) + '" target="_blank" rel="noopener noreferrer" aria-label="Share on X (opens in a new tab)">𝕏 Share on X</a>' +
      '<span class="ss-share-ok" role="status" aria-live="polite"></span></div>';
  }
  function copied(b, ok, text) {
    var live = b.parentNode && b.parentNode.querySelector('.ss-share-ok');
    if (!ok) { window.prompt('Copy this link:', text); return; }
    var idle = b.getAttribute('data-idle') || b.innerHTML;
    b.setAttribute('data-idle', idle);
    b.innerHTML = '✓ Link copied';
    if (live) live.textContent = 'Link copied';
    clearTimeout(b._t);
    b._t = setTimeout(function () { b.innerHTML = idle; if (live) live.textContent = ''; }, 2000);
  }
  // Keep this synchronous up to navigator.share() so iOS (Safari and Chrome) keeps the tap's user activation.
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('[data-ss-share]');
    if (!b) return;
    ev.preventDefault();
    var text = b.getAttribute('data-text') || document.title, url = b.getAttribute('data-url') || location.href;
    var fallback = function () { copyText(url).then(function (ok) { copied(b, ok, url); }); };
    if (navigator.share) {
      navigator.share({ title: document.title, text: text, url: url })
        .catch(function (e) { if (!e || e.name !== 'AbortError') fallback(); });
      return;
    }
    fallback();
  });
  window.SSShare = { row: row, xIntent: xIntent, copyText: copyText };
})();
