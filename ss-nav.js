/* Site header: mobile panel + desktop More. No dependencies. */
(function () {
  var header = document.querySelector('[data-ss-nav]');
  if (!header) return;

  var toggle = header.querySelector('.ss-nav-toggle');
  var panel = document.getElementById('ss-nav-panel');
  var backdrop = document.getElementById('ss-nav-backdrop');
  var moreBtn = header.querySelector('.ss-more-btn');
  var moreMenu = document.getElementById('ss-more-menu');
  var lastFocus = null;

  function mobile() {
    return window.matchMedia('(max-width: 1199px)').matches;
  }

  function pathOf(href) {
    try {
      var u = new URL(href, location.origin);
      var p = u.pathname;
      if (p.length > 1 && !p.endsWith('/')) p += '/';
      return p;
    } catch (e) {
      return href;
    }
  }

  function markCurrent() {
    var here = pathOf(location.pathname);
    header.querySelectorAll('a[href]').forEach(function (a) {
      if (a.hasAttribute('hidden')) return;
      var href = a.getAttribute('href');
      if (!href || href.charAt(0) !== '/') return;
      var p = pathOf(href);
      var on = (p === '/' ? here === '/' : here === p || here.indexOf(p) === 0);
      if (on) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
  }

  function focusables(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')
    ).filter(function (el) {
      return el.offsetParent !== null && !el.hasAttribute('hidden') && !el.closest('[hidden]');
    });
  }

  function closeMore() {
    if (!moreBtn || !moreMenu) return;
    moreMenu.hidden = true;
    moreBtn.setAttribute('aria-expanded', 'false');
  }

  function openMore() {
    if (!moreBtn || !moreMenu || mobile()) return;
    moreMenu.hidden = false;
    moreBtn.setAttribute('aria-expanded', 'true');
  }

  function closePanel(restore) {
    if (!panel || !toggle) return;
    var wasOpen = !panel.hidden;
    panel.hidden = true;
    if (backdrop) backdrop.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Open menu');
    document.body.classList.remove('ss-nav-open');
    if (restore !== false && wasOpen && lastFocus) {
      lastFocus.focus();
    }
  }

  function openPanel() {
    if (!panel || !toggle || !mobile()) return;
    lastFocus = document.activeElement;
    closeMore();
    header.style.setProperty('--ss-header-h', Math.ceil(header.getBoundingClientRect().height) + 'px');
    panel.hidden = false;
    if (backdrop) backdrop.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Close menu');
    document.body.classList.add('ss-nav-open');
    var items = focusables(panel);
    if (items.length) items[0].focus();
  }

  function togglePanel() {
    if (panel.hidden) openPanel();
    else closePanel();
  }

  function toggleMore() {
    if (!moreMenu) return;
    if (moreMenu.hidden) openMore();
    else closeMore();
  }

  if (toggle) {
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      togglePanel();
    });
  }
  if (moreBtn) {
    moreBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      toggleMore();
    });
  }
  if (backdrop) {
    backdrop.addEventListener('click', function () { closePanel(); });
  }

  document.addEventListener('click', function (e) {
    if (moreMenu && !moreMenu.hidden && moreBtn && !header.querySelector('.ss-more').contains(e.target)) {
      closeMore();
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (!panel.hidden) {
        e.preventDefault();
        closePanel();
        return;
      }
      if (moreMenu && !moreMenu.hidden) {
        e.preventDefault();
        closeMore();
        moreBtn.focus();
      }
      return;
    }
    if (e.key !== 'Tab') return;
    if (panel.hidden || !mobile()) return;
    var set = [toggle].concat(focusables(panel)).filter(Boolean);
    if (!set.length) return;
    var first = set[0], last = set[set.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  });

  window.addEventListener('resize', function () {
    if (!mobile()) closePanel(false);
    else closeMore();
  });

  var passport = document.getElementById('passport-btn');
  if (passport) {
    passport.addEventListener('click', function () { closePanel(false); });
  }

  markCurrent();
})();
