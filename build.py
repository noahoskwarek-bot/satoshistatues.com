#!/usr/bin/env python3
"""Build script for satoshistatues.com.

statues.json is the single source of truth. This script:
  * injects the statue array, JSON-LD and the crawlable link list into index.html
  * generates one static page per statue (/<page>/index.html)
  * generates /21-nodes/index.html, sitemap.xml, robots.txt and feed.xml (Atom)
  * generates /embed/ (map-only iframe page, noindex) and the 'Embed this map' snippet box on the home page
  * renders 'Upcoming Bitcoin events nearby' on statue pages from events.json (see EVENTS.md)
  * renders 'The story' (statue.story) and the BTC Map 'Nearby places' list from merchants.json (see GUIDES.md)
  * renders 'Stay nearby (accepts bitcoin)' from lodging.json (statue pages + toggleable map layer; see GUIDES.md)
  * renders the 'Follow us on X' line (signup_html) on the home page, statue pages and 21 Nodes

Run `python3 build.py` after editing statues.json and commit the output.
`python3 build.py --check` exits non-zero if the committed output is stale.
`python3 build.py --no-bin` skips the binary OG images (used by the weekly merchants workflow).
Refresh merchants.json + lodging.json with `python3 tools/fetch_merchants.py` (needs network; builds themselves stay offline).
GitHub Pages serves the committed files as-is; there is no runtime build step.
"""
import datetime
import html
import json
import os
import re
import sys
import unicodedata
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://www.satoshistatues.com'
REPO = 'noahoskwarek-bot/satoshistatues.com'
GISCUS = dict(repoId='R_kgDOT4kDjw', category='Announcements', categoryId='DIC_kwDOT4kDj84DJD3w')
COUNTRY_ISO = {'Hungary': 'HU', 'Switzerland': 'CH', 'El Salvador': 'SV', 'Japan': 'JP', 'Vietnam': 'VN',
               'USA': 'US', 'Italy': 'IT', 'China': 'HK', 'Slovenia': 'SI', 'Austria': 'AT', 'Argentina': 'AR'}
CHECKABLE = ('Installed', 'Restored', 'Damaged', 'Donated')  # Damaged = still in place; Donated = unveiled + donated, pin at the
# unveiling venue (Hong Kong). All of these count in the passport total and can be stamped.
# Any other status (Planned, Unveiled, ...) is listed with a page and pin but can't be stamped and isn't counted.
# 'Unveiled' = unveiled at a known spot but public visiting isn't confirmed yet; statue.stamp_note / stamp_short explain why.
BUILD_DATE = os.environ.get('BUILD_DATE') or datetime.date.today().isoformat()
# Site-wide preview image; ?v= busts X/Facebook/iMessage caches when it changes (cards1: 'Collect cards', Noah 5:08 PM ET).
OG_IMAGE = SITE + '/og-image.jpg?v=cards1'
LB_API = ''  # set from statues.json config.leaderboard_api in load()
POW_ON = False  # config.proof_of_walk.enabled, set in load()

e = lambda t: html.escape(str(t), quote=True)


def load():
    with open(os.path.join(ROOT, 'statues.json'), encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('config', {})
    global LB_API, POW_ON
    LB_API = data['config'].get('leaderboard_api', '')
    POW_ON = bool(pow_cfg(data))
    for s in data['statues']:
        s['slug'] = slug_of(s)
    if POW_ON:
        assert 1 <= pow_genesis_required(data) <= 10 and pow_order_extra(data) >= 1, 'proof_of_walk.genesis_required must be 1-10, order_extra 1+'
        gs = pow_genesis_set(data)
        assert len(gs) == 10 and len(set(gs)) == 10, 'proof_of_walk.genesis_set must be the fixed original 10'
        for s in gs:
            assert any(x['slug'] == s and x['status'] in CHECKABLE for x in data['statues']), f'proof_of_walk.genesis_set: unknown or unstampable statue {s}'
    cpath = os.path.join(ROOT, 'checkins.json')
    counts = {}
    if os.path.exists(cpath):
        with open(cpath, encoding='utf-8') as f:
            counts = json.load(f).get('counts', {})
    for s in data['statues']:
        n = counts.get(s['slug'], 0)
        s['checkins'] = n if isinstance(n, int) and n > 0 else 0
    ppath = os.path.join(ROOT, 'photos.json')
    data['photos'] = {}
    if os.path.exists(ppath):
        with open(ppath, encoding='utf-8') as f:
            plist = json.load(f).get('photos', [])
        for ph in plist:
            # only approved entries whose file exists are published (see PHOTOS.md)
            if ph.get('approved') is True and os.path.exists(os.path.join(ROOT, 'photos', ph['slug'], ph['file'])):
                data['photos'].setdefault(ph['slug'], []).append(ph)
        for v in data['photos'].values():
            v.sort(key=lambda ph: ph.get('month', ''), reverse=True)
    mpath = os.path.join(ROOT, 'merchants.json')
    data['merchants'] = {}
    if os.path.exists(mpath):
        with open(mpath, encoding='utf-8') as f:
            data['merchants'] = json.load(f)
    data['fountain'] = load_fountain()
    lpath = os.path.join(ROOT, 'lodging.json')
    data['lodging'] = {}
    if os.path.exists(lpath):
        with open(lpath, encoding='utf-8') as f:
            data['lodging'] = json.load(f)
    return data


GC_SITE = 'https://satoshistatues.goatcounter.com'
GC_TOKEN_FILES = ('/home/box/.secrets/goatcounter_token', '/home/box/secrets/goatcounter-token')


def gc_token():
    tok = os.environ.get('GOATCOUNTER_TOKEN', '').strip()
    for p in GC_TOKEN_FILES:
        if tok:
            break
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                tok = f.read().strip()
    if not tok:
        raise SystemExit('no GoatCounter token: set GOATCOUNTER_TOKEN or create ' + ' or '.join(GC_TOKEN_FILES))
    return tok


def checkin_counts(hits):
    """Sum GoatCounter event rows "checkin/<slug>" per slug (count = unique visitors)."""
    counts = {}
    for h in hits:
        p = (h.get('path') or '').lstrip('/')
        if h.get('event') and p.startswith('checkin/') and len(p) > len('checkin/'):
            slug = p[len('checkin/'):]
            counts[slug] = counts.get(slug, 0) + int(h.get('count') or 0)
    return counts


def gc_hits(tok, start='2024-01-01'):
    """All rows of /api/v0/stats/hits. Plain YYYY-MM-DD dates; end is tomorrow (UTC) so today is included.
    Any HTTP/network error or unexpected reply aborts the refresh (checkins.json is left untouched)."""
    import urllib.request, urllib.parse, urllib.error
    end = (datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=1)).isoformat()
    rows, seen = [], []
    for _ in range(50):
        q = {'start': start, 'end': end, 'limit': 100}
        if seen:
            q['exclude_paths'] = ','.join(map(str, seen))
        req = urllib.request.Request(GC_SITE + '/api/v0/stats/hits?' + urllib.parse.urlencode(q),
                                     headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)
        except urllib.error.HTTPError as ex:
            raise SystemExit(f'GoatCounter API error {ex.code} {ex.reason}: {ex.read()[:200].decode("utf-8", "replace")}')
        except (urllib.error.URLError, TimeoutError, ValueError) as ex:
            raise SystemExit(f'GoatCounter API request failed: {ex}')
        if not isinstance(res, dict) or not isinstance(res.get('hits'), list):
            raise SystemExit('GoatCounter API: unexpected reply (no "hits" list)')
        rows += res['hits']
        seen += [h.get('path_id') for h in res['hits']]
        if not res.get('more') or not res['hits']:
            return rows, start, end
    raise SystemExit('GoatCounter API: too many pages')


def refresh_checkins():
    """Fetch per-statue check-in counts (GoatCounter events "checkin/<slug>") into checkins.json.
    The read-only token is only used here at build time and is never written into the site."""
    rows, start, end = gc_hits(gc_token())
    counts = checkin_counts(rows)
    pages = sum(1 for h in rows if not h.get('event'))
    events = sum(1 for h in rows if h.get('event'))
    print(f'GoatCounter {start}..{end}: {len(rows)} rows ({pages} pages, {events} events)')
    out = {'_comment': 'Generated by `python3 build.py --refresh-checkins` from GoatCounter events checkin/<slug> '
                       '(unique visitors). Edit by re-running, not by hand.',
           'updated': datetime.datetime.now(datetime.timezone.utc).date().isoformat(), 'counts': dict(sorted(counts.items()))}
    with open(os.path.join(ROOT, 'checkins.json'), 'w', encoding='utf-8') as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print('checkins.json:', out['counts'] or 'no check-in events yet')


WORKER_DIR = os.environ.get('LEADERBOARD_DIR', '/workspace/leaderboard')


def write_worker_statues(data):
    """Statue coordinates for the leaderboard Worker's server-side distance check (stampable statues only)."""
    # label/city/country/tz: the combined card's verify lookup (/api/pow/verify) shows the statue label and the date in
    # the statue's own time zone (statues.json "tz", IANA).
    st = {s['slug']: {'name': s['name'], 'page': s['page'], 'lat': s['lat'], 'lng': s['lng'],
                      'label': s['label'], 'city': s['city'], 'country': s['country'], 'tz': s.get('tz') or 'UTC'}
          for s in data['statues'] if s['status'] in CHECKABLE}
    path = os.path.join(WORKER_DIR, 'src', 'statues.gen.js')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Proof of Walk rank config (config.proof_of_walk), read by the Worker's src/pow.js: Genesis = genesis_required of
    # genesis_set; Grand High Order = Genesis + order_extra more statues, kept for good unless order_keep = false.
    pg = {'set': sorted(pow_genesis_set(data)), 'required': pow_genesis_required(data)}
    po = {'extra': pow_order_extra(data), 'keep': pow_order_keep(data)}
    with open(path, 'w', encoding='utf-8') as f:
        f.write('// Generated by satoshistatues.com build.py --worker from statues.json. Do not edit.\n'
                'export const STATUES = ' + json.dumps(st, ensure_ascii=False, indent=2) + ';\n'
                'export const POW_GENESIS = ' + json.dumps(pg) + ';\n'
                'export const POW_ORDER = ' + json.dumps(po) + ';\n')
    print(f'wrote {path} ({len(st)} stampable statues)')


def count_text(n):
    return f'👣 {n} {"person has" if n == 1 else "people have"} checked in here'


def checkin_count_html(s):
    # Baked from checkins.json; LIVE_COUNT_JS refreshes it from the leaderboard API (/api/counts).
    n = s.get('checkins', 0)
    return (f'<p class="checkin-count" data-count-slug="{e(s["slug"])}" data-base="{n}"{"" if n else " hidden"}>'
            f'{count_text(n) if n else ""}</p>')


# ---------- Satoshi Fountain (reverse fountain: Lightning giveaway for verified check-ins) ----------
# Switched by fountain.json "enabled" (default false). When off, every helper below returns '' / adds nothing, so the
# build is byte-identical to one without this feature. Amounts, budget and limits live in the Worker, not here.
FOUNTAIN_DEFAULTS = {'enabled': False, 'api': '', 'statues': [], 'claim_minutes': 21, 'address_retention_days': 90,
                     'tip_presets': [1000, 5000, 21000]}


def load_fountain():
    cfg = dict(FOUNTAIN_DEFAULTS)
    path = os.environ.get('FOUNTAIN_CONFIG') or os.path.join(ROOT, 'fountain.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            cfg.update({k: v for k, v in json.load(f).items() if not k.startswith('_')})
    cfg['enabled'] = cfg.get('enabled') is True
    return cfg


def payout_info(data):
    """Payout rules from fountain.json "payout" (mirrors the Worker vars). Exact odds and mean via Fraction."""
    from fractions import Fraction
    p = (data.get('fountain') or {}).get('payout') or {}
    fixed = int(p.get('fixed_sats', 21))
    if p.get('mode') != 'random':
        return {'mode': 'fixed', 'sats': fixed}
    tiers = [(int(a), int(b), int(w)) for a, b, w in p['tiers']]
    bonus, bw = int(p.get('bonus_sats', 0)), int(p.get('bonus_weight', 0))
    assert tiers and all(1 <= a <= b and w > 0 for a, b, w in tiers) and bw >= 0, 'bad fountain.json payout tiers'
    total = sum(w for _, _, w in tiers) + bw
    mean = (sum(Fraction(w * (a + b), 2) for a, b, w in tiers) + bw * bonus) / total
    odds = Fraction(total, bw) if bw else None
    fmt = lambda f: str(f.numerator) if f.denominator == 1 else f'{float(f):.2f}'
    return {'mode': 'random', 'min': min(a for a, _, _ in tiers), 'max': max(b for _, b, _ in tiers), 'bonus': bonus if bw else 0,
            'odds': fmt(odds) if odds else '', 'mean': fmt(mean), 'tiers': tiers, 'total': total, 'bonus_weight': bw,
            'cap_sats_day': int(p.get('cap_sats_day', 240))}


def payout_phrase(data):
    """Static amount phrase for the widget and terms (the widget refines it from /api/fountain)."""
    pi = payout_info(data)
    if pi['mode'] == 'fixed':
        return f"a fixed {pi['sats']} sats"
    return f"{pi['min']:,}–{pi['max']:,} sats" + (f", or the rare Lucky {pi['bonus']:,} bonus" if pi['bonus'] else '')


def odds_line(data):
    """One-line odds disclosure (2026-10-29) for the statue giveaway box and the Official Rules. '' in fixed mode."""
    pi = payout_info(data)
    if pi['mode'] == 'fixed':
        return ''
    return (f"Each verified check-in reveals {pi['min']:,}–{pi['max']:,} sats" +
            (f" or, about 1 in {pi['odds']} times, a Lucky {pi['bonus']:,} sats" if pi['bonus'] else '') +
            ", while the giveaway budget and daily limits last.")


def fountain_on(data, s=None):
    f = data.get('fountain') or {}
    return bool(f.get('enabled')) and (s is None or (s['slug'] in f.get('statues', []) and s['status'] in CHECKABLE))


FOUNTAIN_CSS = ('.fountain{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:10px;padding:12px 14px;margin:14px 0}'
                '.fountain h2{margin:0 0 4px;font-size:1.05rem;color:#f7931a}.fountain p{font-size:.9rem;line-height:1.45}'
                '.f-stats{display:grid;grid-template-columns:1fr;max-width:220px;gap:8px;margin:10px 0}'
                '.f-stat{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:8px 10px;font-size:.8rem;color:#8b949e}'
                '.f-stat b{display:block;font-size:1.25rem;color:#e6edf3}'
                '.f-msg{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:9px 11px;margin-top:8px}.f-msg.ok{border-color:#3fb950;color:#3fb950}'
                '.f-form{display:grid;gap:8px;margin-top:8px;background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:10px 11px}'
                '.f-form input[name=addr]{font:inherit;font-size:16px;padding:10px;border-radius:8px;border:1px solid #30363d;background:#161b22;color:#e6edf3;min-height:44px;width:100%}'
                '.f-form label{display:flex;gap:8px;align-items:center;font-size:.9rem;min-height:32px}.f-form input[type=checkbox]{width:20px;height:20px;accent-color:#f7931a}'
                '.f-form button{width:100%;border:0;cursor:pointer;font:inherit;font-weight:700}.f-form button:disabled{opacity:.6}'
                '.f-out{color:#f0883e;font-size:.88rem;min-height:1em}.f-q{font-weight:600}'
                '.f-fine{font-size:.8rem;color:#8b949e}.f-row{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}'
                '.f-row button.btn{cursor:pointer;font:inherit;font-weight:700}'
                '.fountain h3{font-size:.95rem;margin:14px 0 4px}'
                '.fountain textarea{width:100%;font:.75rem ui-monospace,Menlo,Consolas,monospace;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:8px;word-break:break-all}'
                '.f-recent ul{list-style:none;font-size:.85rem}.f-recent li{padding:4px 0;border-bottom:1px solid #21262d}.f-recent li span{color:#8b949e}'
                '.f-free{font-size:.78rem;color:#8b949e;line-height:1.4;margin:0}.f-free a{color:#f7931a}'
                '.f-got{position:relative;text-align:center;padding:16px 12px 14px;overflow:hidden}'
                '.f-got .f-big{font-size:1.15rem;font-weight:800;color:#e6edf3;margin:0}'
                '.f-odo{display:inline-flex;font-variant-numeric:tabular-nums;font-size:2.6rem;font-weight:800;line-height:1;height:1em;overflow:hidden;color:#f7931a;vertical-align:bottom}'
                '.f-odo .d{display:block;height:1em;overflow:hidden}.f-odo .s{display:flex;flex-direction:column;transition:transform 1.5s cubic-bezier(.15,.75,.25,1)}'
                '.f-odo .s span{display:block;height:1em;line-height:1em}.f-odo-unit{font-size:1.1rem;font-weight:700;color:#f7931a;margin-left:6px}'
                '.f-got .f-sub{font-size:.85rem;color:#8b949e;margin:8px 0 0}'
                '.f-got.f-lucky{border-color:#f7931a;box-shadow:0 0 0 1px #f7931a,0 0 22px rgba(247,147,26,.55);animation:f-glow 1.6s ease-in-out 2}'
                '.f-lucky-tag{display:inline-block;font-weight:800;color:#0d1117;background:#f7931a;border-radius:999px;padding:3px 12px;margin-bottom:8px;font-size:.9rem}'
                '@keyframes f-glow{50%{box-shadow:0 0 0 2px #ffd28a,0 0 40px rgba(247,147,26,.85)}}'
                '.f-conf{position:absolute;left:50%;top:45%;width:8px;height:12px;border-radius:2px;opacity:0;pointer-events:none;'
                'animation:f-burst 1.3s cubic-bezier(.2,.7,.3,1) forwards;animation-delay:var(--dl)}'
                '@keyframes f-burst{0%{opacity:1;transform:translate(-50%,-50%) rotate(0)}100%{opacity:0;transform:translate(calc(-50% + var(--x)),calc(-50% + var(--y))) rotate(var(--r))}}'
                '@media (prefers-reduced-motion:reduce){.f-odo .s{transition:none}.f-got.f-lucky{animation:none}.f-conf{display:none}}'
                '.fountain[hidden],.fountain [hidden]{display:none!important}')


# Shown under the claim box (and so under the address form after the reveal) on every giveaway page.
WALLETS_LINE = ('<p class="f-fine f-wallets">Works with Wallet of Satoshi, Strike, Phoenix, Primal and most Lightning wallets. '
                'Cash App can’t receive these payouts.</p>')


def fountain_box(s, data):
    if not fountain_on(data, s):
        return ''
    f = data['fountain']
    api = f.get('api') or LB_API
    return (f'\n    <style>{FOUNTAIN_CSS}</style><section class="fountain" id="giveaway" data-ss-fountain data-slug="{e(s["slug"])}" data-name="{e(s["name"])}" data-share-name="{e(share_name(s))}" data-url="{e(page_url(s))}" data-api="{e(api)}" hidden>'
            f'<h2>⛲ Satoshi Fountain</h2>'
            f'<p>A small Lightning giveaway for visitors who check in at this statue, while the giveaway budget lasts.</p>'
            + (f'<p class="f-fine f-odds">{e(odds_line(data))}</p>' if odds_line(data) else '') +
            f'<div class="f-stats"><div class="f-stat"><b data-f-left>–</b>giveaway sats left</div></div>'
            f'<p class="f-fine">Check in here to get <span data-f-howmuch>{e(payout_phrase(data))}</span> sent to a Lightning address. '
            f'One per Lightning address per statue. 18+ only. No tip needed, and tipping never changes the giveaway. '
            f'The giveaway can stop at any time. {rules_links(data)}</p>'
            f'<div data-f-claim></div>{WALLETS_LINE}'
            f'<h3>Recent activity</h3><div class="f-recent" data-f-recent></div>'
            f'</section>')


def rules_on(data):
    return fountain_on(data) and payout_info(data)['mode'] == 'random'


def rules_links(data):
    return ('<a href="/rules/">Official Rules</a> · <a href="/terms/">Giveaway terms</a>' if rules_on(data)
            else '<a href="/terms/">Giveaway terms</a>')


def fountain_script(s, data):
    if not fountain_on(data, s):
        return ''
    import hashlib
    with open(os.path.join(ROOT, 'fountain.js'), 'rb') as f:
        v = hashlib.sha256(f.read()).hexdigest()[:10]
    return f'<script src="/fountain.js?v={v}"></script>\n'


# Home-page map callouts for giveaway statues (popup / mobile detail sheet + a small badge on the sidebar card).
# Only emitted when fountain.json is enabled, and only statues listed there get s.giveaway in the map data.
# Static first: a neutral label without an amount. Then /api/fountain?slug= refines it (amount from the Worker's
# PAYOUT_SATS, "paused", or hidden when the budget is out). Any API failure keeps the neutral label, never an error.
GIVEAWAY_HOME_CSS = ('.gw-badge{display:inline-block;font-size:.7rem;padding:2px 7px;border-radius:4px;margin-top:7px;font-weight:600;'
                     'background:rgba(247,147,26,.12);border:1px solid rgba(247,147,26,.45);color:#f7931a;line-height:1.35}'
                     '.gw-badge.gw-paused{background:#21262d;border-color:#30363d;color:#8b949e}.gw-badge[hidden],.gw-pop[hidden]{display:none!important}'
                     '.gw-pop{background:#0d1117;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:8px;padding:8px 10px;margin:8px 0 10px;font-size:.82rem;line-height:1.45;color:#e6edf3}'
                     '.gw-pop b{color:#f7931a}.gw-pop.gw-paused{border-left-color:#8b949e}.gw-pop.gw-paused b{color:#8b949e}'
                     '.gw-pop .gw-links{margin-top:4px;font-size:.78rem}.gw-pop a{color:#f7931a;font-weight:600;text-decoration:none}.gw-pop a:hover{text-decoration:underline}'
                     '.gw-pop .gw-links .gw-terms{color:#8b949e;font-weight:400}'
                     '@media (max-width:768px){.gw-pop{font-size:.88rem;padding:10px 12px 0}.gw-pop .gw-links{margin-top:0}.gw-pop a{display:inline-flex;align-items:center;min-height:44px}}')

GIVEAWAY_HOME_JS = r'''(function () {
  var API = window.SS_API || '', SLUGS = __SLUGS__, state = {};
  var num = function (n) { return Number(n || 0).toLocaleString('en-US'); };
  function info(slug) {
    var j = state[slug];
    if (!j) return { kind: 'static' };
    var range = j.payout_mode !== 'fixed' && j.payout_max > 0;
    var min = range ? 1 : j.payout_sats;
    if (!j.enabled || !(min > 0) || j.giveaway_sats_left < min) return { kind: 'off' };
    if (j.paused) return { kind: 'paused' };
    return { kind: j.open ? 'open' : 'limit', sats: range ? 0 : j.payout_sats,
      range: range ? num(j.payout_min) + '–' + num(j.payout_max) + ' sats' : '', bonus: range && j.bonus_sats ? num(j.bonus_sats) : '' };
  }
  function badgeText(i) {
    if (i.kind === 'paused') return '⚡ Giveaway paused';
    return i.sats ? '⚡ ' + num(i.sats) + '-sat giveaway' : '⚡ Sats giveaway';
  }
  function popText(i) {
    if (i.kind === 'paused') return '<b>⚡ Sats giveaway:</b> paused at the moment.';
    var amt = i.range ? i.range : i.sats ? num(i.sats) + ' sats' : __NEUTRAL__;
    var bonus = i.range ? i.bonus : i.sats ? '' : __NEUTRAL_BONUS__;
    return '<b>⚡ Sats giveaway:</b> ' + amt + ' per verified check-in' + (bonus ? ', with a rare ' + bonus + ' bonus' : '') + ', while the giveaway budget lasts.' +
      (i.kind === 'limit' ? ' Today’s limit here has been reached. Try again tomorrow.' : '');
  }
  function fill(el, slug, pop) {
    var i = info(slug);
    el.hidden = i.kind === 'off';
    el.classList.toggle('gw-paused', i.kind === 'paused');
    if (!pop) { el.textContent = badgeText(i); return; }
    el.querySelector('[data-gw-text]').innerHTML = popText(i);
  }
  window.giveawayBadgeHtml = function (s) {
    var i = info(s.slug);
    return '<span class="gw-badge' + (i.kind === 'paused' ? ' gw-paused' : '') + '" data-gw-badge="' + s.slug + '"' + (i.kind === 'off' ? ' hidden' : '') + '>' + badgeText(i) + '</span>';
  };
  window.giveawayPopupHtml = function (s) {
    var i = info(s.slug);
    return '<div class="gw-pop' + (i.kind === 'paused' ? ' gw-paused' : '') + '" data-gw-pop="' + s.slug + '"' + (i.kind === 'off' ? ' hidden' : '') + '>' +
      '<div data-gw-text>' + popText(i) + '</div>' +
      '<div class="gw-links"><a href="/' + encodeURIComponent(s.page) + '/#giveaway">See how it works ›</a> <span class="gw-terms">· 18+ · <a class="gw-terms" href="__RULES_HREF__">__RULES_LABEL__</a></span></div></div>';
  };
  window.giveawayOpen = function (slug) { var k = info(slug).kind; return k !== 'off' && k !== 'paused'; };
  function apply(slug) {
    var W = window.SS_CI_WHAT, ok = window.giveawayOpen(slug);
    if (W) document.querySelectorAll('[data-ci-what="' + slug + '"]').forEach(function (el) { el.textContent = ok ? W.pay : W.free; });
    document.querySelectorAll('[data-gw-badge="' + slug + '"]').forEach(function (el) { fill(el, slug, false); });
    document.querySelectorAll('[data-gw-pop="' + slug + '"]').forEach(function (el) { fill(el, slug, true); });
  }
  function load() {
    if (!API || !window.fetch) return;
    SLUGS.forEach(function (slug) {
      fetch(API + '/api/fountain?slug=' + encodeURIComponent(slug)).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { if (j && j.ok && typeof j.enabled === 'boolean') { state[slug] = j; apply(slug); } })
        .catch(function () {});
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load); else load();
})();'''


def giveaway_home_head(data):
    if not fountain_on(data):
        return ''
    slugs = [s['slug'] for s in data['statues'] if fountain_on(data, s)]
    if not slugs:
        return ''
    pi = payout_info(data)
    rnd = pi['mode'] == 'random'
    neutral = f"'{pi['min']}–{pi['max']} sats'" if rnd else "'a small, fixed amount of sats'"
    js = (GIVEAWAY_HOME_JS.replace('__SLUGS__', json.dumps(slugs)).replace('__NEUTRAL_BONUS__', f"'{pi['bonus']:,}'" if rnd and pi['bonus'] else "''")
          .replace('__NEUTRAL__', neutral)
          .replace('__RULES_HREF__', '/rules/' if rules_on(data) else '/terms/').replace('__RULES_LABEL__', 'Rules' if rules_on(data) else 'Terms'))
    return f'\n  <style>{GIVEAWAY_HOME_CSS}</style>\n  <script>{js}</script>'


def fountain_footer_link(data):
    return ' · <a href="/terms/">Terms</a>' if fountain_on(data) else ''


def fountain_names(data):
    return ', '.join(o['name'] for o in data['statues'] if o['slug'] in data['fountain'].get('statues', []))


def fountain_privacy_html(data):
    if not fountain_on(data):
        return ''
    f = data['fountain']
    return f'''    <h2>Satoshi Fountain giveaway and tips</h2>
    <ul class="src" style="font-size:.95rem;color:#e6edf3">
      <li>The giveaway runs at selected statues ({e(fountain_names(data))}). It only uses data when you take part.</li>
      <li>A GPS check-in at one of these statues creates a <strong>single-use code</strong> that is valid for {int(f.get('claim_minutes', 21))} minutes. We store a hash of the code, your hashed device ID, the statue and the time, and delete it after 1 day.</li>
      <li>{PRIVACY_CLAIM_BULLET}</li>
      <li>No address is ever shown publicly. The statue’s recent activity list shows “a visitor”.</li>
      <li>Your <strong>IP address</strong> is used for daily limits as a salted, per-day hash and deleted after 7 days.</li>
      <li>Tips are sent from your own wallet straight to our Bitcoin tip address (the same one as on the map’s home page). We don’t store anything about tips.</li>
      <li>To send a payout, our server asks the wallet service behind your Lightning address for an invoice, and our Lightning payment provider pays it.</li>
    </ul>
    <p class="note">See the <a href="/terms/">terms</a>.</p>
'''


def terms_page(data):
    title = 'Terms – satoshistatues.com'
    desc = 'Terms for visiting statues, the Satoshi Fountain Lightning giveaway and tips on satoshistatues.com.'
    canonical = SITE + '/terms/'
    out = head(title, desc, canonical, OG_IMAGE, 1200, 630, 'Satoshi statues world map', '')
    li = lambda items: '<ul class="src" style="font-size:.95rem;color:#e6edf3">' + ''.join(f'<li>{x}</li>' for x in items) + '</ul>'
    visiting = li(['Obey local laws and any rules at the site.',
                   'Don’t trespass. Only visit statues from public places or during opening hours, and respect private property.',
                   'Visiting statues, checking in and using this site are at your own risk. We don’t guarantee access, safety or that a statue is still there.'])
    giveaway = li([f'The Satoshi Fountain is a small, optional giveaway run by SatoshiStatues.com at selected statues ({e(fountain_names(data))}).',
                   ('A GPS check-in verified by our server at one of these statues lets you get a <strong>fixed amount</strong> of sats sent to a Lightning address. The amount is shown on the statue page and is the same for everyone.'
                    if not rules_on(data) else
                    f'A GPS check-in verified by our server at one of these statues lets you get sats sent to a Lightning address. Our server draws the amount when your check-in is verified and shows it before you enter an address: {e(payout_phrase(data))}. It is reserved for you for {int(data["fountain"].get("claim_minutes", 21))} minutes, and released if you don’t claim it in that time. The exact odds are in the <a href="/rules/">Official Rules</a>, which also apply.'),
                   'It is funded only from a giveaway budget set by SatoshiStatues.com and runs <strong>while the giveaway budget lasts</strong>. Daily limits apply per statue, per network and overall.',
                   'One payout per Lightning address per statue, and one per passport per statue.',
                   'No purchase or tip is needed. Tipping never affects the giveaway.',
                   'You must be <strong>18 or older</strong> to take part.',
                   'The giveaway can change, pause or stop at any time without notice. Nobody is entitled to a payout.',
                   'We may refuse or cancel payouts that look like abuse, for example faked locations, many devices or many addresses.',
                   'Payouts are sent over Lightning and can’t be reversed. Check your Lightning address before you send it.',
                   'Where the giveaway isn’t allowed, it doesn’t apply. You are responsible for any taxes that apply to you.'])
    tips = li(['Tips are voluntary payments to SatoshiStatues.com that help keep the map running.',
               'Tips are not tax-deductible, are not refundable and don’t buy any goods, services or rights.',
               'Tips are kept separate from the giveaway and are never added to the giveaway budget.'])
    out += f'''  <main>
    <div class="crumbs"><a href="/">Map</a> › Terms</div>
    <h1>Terms</h1>
    <p class="sub">Plain terms for visiting statues, the Satoshi Fountain giveaway and tips.</p>
    <h2>Visiting statues</h2>
    {visiting}
    <h2>Satoshi Fountain giveaway</h2>
    {giveaway}
    <h2>Tips</h2>
    {tips}
    <h2>Linking your X account</h2>
    <p class="note">Linking your X account is optional. {e(X_DISCLAIMER)}</p>
    <h2>Privacy</h2>
    <p class="note">What we store and for how long: <a href="/privacy/">Privacy</a>.</p>{'<p class="note">Giveaway amounts and odds: <a href="/rules/">Official Rules</a>.</p>' if rules_on(data) else ''}
    <p class="note" style="margin-top:8px;font-size:.85rem;color:#8b949e">Last updated {BUILD_DATE}.</p>
    {footer(data)}
  </main>
'''
    return out + TAIL


def rules_page(data):
    """Official Rules for the giveaway in random-amount mode (numbers from fountain.json payout)."""
    pi = payout_info(data)
    title = 'Official Rules: Satoshi Fountain giveaway – satoshistatues.com'
    desc = 'Official Rules for the Satoshi Fountain Lightning giveaway on satoshistatues.com: eligibility, amounts, odds and limits.'
    out = head(title, desc, SITE + '/rules/', OG_IMAGE, 1200, 630, 'Satoshi statues world map', '')
    li = lambda items: '<ul class="src" style="font-size:.95rem;color:#e6edf3">' + ''.join(f'<li>{x}</li>' for x in items) + '</ul>'
    pct = lambda w: f'{100 * w / pi["total"]:.1f}%'.replace('.0%', '%')
    rows = ''.join(f'<tr><td>{a:,}–{b:,} sats (each amount in this range equally likely)</td><td>{w} in {pi["total"]:,} ({pct(w)})</td></tr>' for a, b, w in pi['tiers'])
    if pi['bonus']:
        rows = f'<tr><td>{pi["bonus"]:,} sats (Lucky {pi["bonus"]:,})</td><td>1 in {pi["odds"]} ({pct(pi["bonus_weight"])})</td></tr>' + rows
    table = ('<table style="width:100%;border-collapse:collapse;font-size:.9rem;margin:8px 0" class="rules-odds">'
             '<thead><tr><th style="text-align:left">Amount per valid check-in</th><th style="text-align:left">Odds</th></tr></thead>'
             f'<tbody>{rows}</tbody></table>')
    out += f'''  <style>.rules-odds td,.rules-odds th{{border-bottom:1px solid #30363d;padding:6px 4px;vertical-align:top}}.rules-odds th{{color:#8b949e;font-weight:600}}</style>
  <main>
    <div class="crumbs"><a href="/">Map</a> › Official Rules</div>
    <h1>Official Rules: Satoshi Fountain giveaway</h1>
    <p class="sub">No purchase or tip necessary. A tip won’t improve your odds. 18+. Void where prohibited.</p>
    <h2>1. Sponsor</h2>
    {li(['SatoshiStatues.com (the “Sponsor”).', f'Questions: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>'])}
    <h2>2. Eligibility</h2>
    {li(['Open to people <strong>18 or older</strong> where permitted by law. Void where prohibited or restricted.'])}
    <h2>3. How to take part</h2>
    {li([f'Complete a check-in at a participating statue ({e(fountain_names(data))}) that our server verifies (GPS, within 150 m). Our server then draws your amount and shows it to you right away. To receive it, enter a Lightning address within the claim time shown ({int(data["fountain"].get("claim_minutes", 21))} minutes).',
         '<strong>No purchase or tip is necessary.</strong> Tips never affect taking part, the odds or the amount.',
         'One payout per Lightning address per statue and one per passport (device) per statue. Daily limits apply per statue, per network and overall.'])}
    <h2>4. Amounts and odds</h2>
    {li([e(odds_line(data)), f'Each valid check-in receives a random amount from {pi["min"]:,} to {pi["max"]:,} sats' + (f', or a rare {pi["bonus"]:,}-sat bonus' if pi['bonus'] else '') + '. Our server picks the amount with a cryptographic random number generator. Nothing you do on the page changes it.',
         (f'The odds of the {pi["bonus"]:,}-sat bonus are <strong>1 in {pi["odds"]}</strong> per valid check-in. ' if pi['bonus'] else '') + f'The average amount is <strong>{pi["mean"]} sats</strong>.',
         f'The amount is drawn once per passport (device) per statue per day, at check-in. It is reserved for you during the claim time ({int(data["fountain"].get("claim_minutes", 21))} minutes) and counts against the giveaway budget and daily limits while it is reserved. If it isn’t claimed in time, it is released back to the giveaway budget. Checking in again the same day shows the same amount; it doesn’t draw a new one.',
         'The total giveaway budget is set by the Sponsor, and the giveaway sats left are shown on each participating statue page.',
         f'If the amount drawn is more than what is left of the giveaway budget, or of the daily limit of {pi["cap_sats_day"]:,} sats across all statues, you are shown and can claim what is left instead' + (f', so a Lucky {pi["bonus"]:,} draw may not be paid in full' if pi['bonus'] else '') + '. If nothing is left, you are told before you enter a Lightning address.'])}
    {table}
    <h2>5. Period</h2>
    {li(['From the start of the giveaway until the giveaway budget runs out or the Sponsor ends it, whichever comes first.'])}
    <h2>6. Payment</h2>
    {li(['Paid in sats over Lightning only, to the Lightning address you enter. No cash or other alternative. Not transferable.',
         'Lightning payments can’t be reversed. Check your Lightning address before you send it.',
         'Recipients are responsible for any taxes that apply to them.'])}
    <h2>7. Changes and disqualification</h2>
    {li(['The Sponsor may end, pause or change the giveaway at any time.',
         'The Sponsor may refuse or cancel payouts and disqualify anyone for fraud, spoofed or faked location, automation, multiple devices or addresses, or other abuse.'])}
    <h2>8. Safety</h2>
    {li(['Taking part is at your own risk. Obey local laws and any rules at the site.',
         'Don’t trespass. Only visit statues from public places or during opening hours, and respect private property.'])}
    <h2>9. Data</h2>
    <p class="note">What we store and for how long: <a href="/privacy/">Privacy</a>. See also the <a href="/terms/">Terms</a>.</p>
    <p class="note" style="margin-top:8px;font-size:.85rem;color:#8b949e">Last updated {BUILD_DATE}.</p>
    {footer(data)}
  </main>
'''
    return out + TAIL


def checkin_script():
    # Shared check-in core (checkin.js, hand-written): loaded by the home map and every statue page.
    # ?v= is a content hash so browsers pick up changes right after a deploy.
    import hashlib
    with open(os.path.join(ROOT, 'checkin.js'), 'rb') as f:
        v = hashlib.sha256(f.read()).hexdigest()[:10]
    return f'<script src="/checkin.js?v={v}"></script>'


def share_script():
    # Share buttons (share.js, hand-written): loaded on every statue page. ?v= is a content hash like checkin.js.
    import hashlib
    with open(os.path.join(ROOT, 'share.js'), 'rb') as f:
        v = hashlib.sha256(f.read()).hexdigest()[:10]
    return f'<script src="/share.js?v={v}"></script>'


def share_name(s):
    """'the Lugano Satoshi statue' for share text; other monuments keep their own name ('the Miami Bitcoin Bull')."""
    return f"the {s['city']} Satoshi statue" if s['label'].startswith('Satoshi Statue ') else f"the {s['label']}"


SHARE_CSS = ('.ss-share{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:10px 0}'
             '.ss-share .btn{font-size:.85rem;color:#e6edf3;cursor:pointer;font-family:inherit}'
             '.ss-share-q{flex-basis:100%;font-size:.85rem;font-weight:600;color:#c9d1d9}'
             '.ss-share-ok{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}'
             '.f-msg.ok .ss-share-q,.checkin-msg.ok .ss-share-q{color:#e6edf3}')


def share_box(s):
    """Static share row for a statue page (works without JS: the X link is a plain link; share.js adds the share sheet)."""
    text = f"Check out {share_name(s)} 🟠 Location, directions and photos"
    url = page_url(s)
    x = f"https://x.com/intent/post?text={urllib.parse.quote(text, safe='')}&url={urllib.parse.quote(url, safe='')}"
    return (f'<style>{SHARE_CSS}</style><div class="ss-share" role="group" aria-label="Share this statue">'
            f'<span class="ss-share-q">Share this statue</span>'
            f'<button class="btn" type="button" data-ss-share data-text="{e(text)}" data-url="{e(url)}" '
            f'aria-label="Share with your phone’s share sheet, or copy the link">📤 Share</button>'
            f'<a class="btn" href="{e(x)}" target="_blank" rel="noopener noreferrer" aria-label="Share on X (opens in a new tab)">Share on X</a>'
            f'<span class="ss-share-ok" role="status" aria-live="polite"></span></div>')


def api_script():
    if not LB_API:
        return ''
    return (f'<script>window.SS_API = {json.dumps(LB_API)};' + ('window.SS_POW = true;' if POW_ON else '')
            + (f'window.SS_POWCARD = {json.dumps(POW_CARD_JS_URL)};' if POW_ON and POW_CARD_JS_URL else '') + '</script>')


POW_CARD_JS_URL = ''   # set in main() once statues.json is loaded (content-hashed /pow-card.js?v=…)


LIVE_COUNT_JS = """<script>(function(){var A=window.SS_API;if(!A||!window.fetch)return;fetch(A+"/api/counts").then(function(r){return r.json()}).then(function(j){if(!j||!j.ok)return;
document.querySelectorAll("[data-count-slug]").forEach(function(el){var n=Math.max(j.counts[el.getAttribute("data-count-slug")]||0,+el.getAttribute("data-base")||0);
if(n>0){el.textContent="\\uD83D\\uDC63 "+n+(n===1?" person has":" people have")+" checked in here";el.hidden=false}});}).catch(function(){});})();</script>"""


def footer(data, extra=''):
    nostr = f' · <a href="{e(nostr_url(data))}" rel="me">Nostr</a>' if nostr_url(data) else ''
    return (f'<footer class="site"><a href="/">satoshistatues.com</a> · <a href="/21-nodes/">21 Nodes tracker</a> · '
            f'<a href="/leaderboard/">Leaderboard</a> · <a href="/feed.xml">Feed</a>{nostr}{extra}{fountain_footer_link(data)} · <a href="/privacy/">Privacy</a>'
            f'{support_line()}</footer>')


def support_line():
    # 'Questions? support@…' on its own small line at the bottom of every page's footer (home: BUILD:SUPPORT block).
    return (f'<span class="support-line">Questions? <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></span>'
            f'<span class="support-line x-disc" id="x-disclaimer">{e(X_DISCLAIMER)}</span>')


# Footer + terms disclaimer for the blue ✓ "Verified" badge (Noah 2026-11-01 11:36 AM ET; text as given, typographic quotes).
X_DISCLAIMER = ('SatoshiStatues.com is not affiliated with or endorsed by X Corp. ‘Verified’ means the walker signed in with that X account. '
                'It is not X’s own verification badge.')
PRIVACY_UPDATED = '2026-11-02'   # xrecover preview: X-only recovery, no stored Lightning addresses (for Grant); independent of BUILD_DATE


def slug_of(s):
    """Same as slugOf() in index.html: used for passport stamps and giscus terms."""
    if s.get('id'):
        return s['id']
    t = unicodedata.normalize('NFD', s['name'].lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return re.sub(r'^-|-$', '', re.sub(r'[^a-z0-9]+', '-', t))


def sort_year(y):
    m = re.findall(r'\d{4}', str(y))
    return max(map(int, m)) if m else 0


def unveil_key(s):
    # first date in the string: '16 Sep 2021', 'Apr 2025', '6–9 Apr 2022', '~1 Feb 2025 (San Salvador); Apr 2025 (El Zonte)'
    m = re.search(r'(?:(\d{1,2})(?:[–-]\d{1,2})? )?([A-Z][a-z]{2}) (\d{4})', s.get('unveiled') or '')
    if m:
        try:
            return datetime.datetime.strptime(f"{m.group(1) or 1} {m.group(2)} {m.group(3)}", '%d %b %Y')
        except ValueError:
            pass
    return datetime.datetime(sort_year(s['year']), 1, 1)


def img_abs(s):
    """Absolute image URL for OG/JSON-LD. Remote (hot-linked) photos fall back to the site card."""
    if s.get('img') and not s['img'].startswith('http'):
        return f"{SITE}/{s['img']}", s.get('imgW'), s.get('imgH'), True
    return OG_IMAGE, 1200, 630, False


def creators(s):
    if s.get('creatorVerified') is False:
        return []
    names = re.sub(r'\s*\(.*?\)', '', s['artist'])
    return [{'@type': 'Person', 'name': n.strip()} for n in re.split(r'\s*&\s*|\s+and\s+', names) if n.strip()]


def page_url(s):
    return f"{SITE}/{s['page']}/"


def describe(s):
    t = (f"{s['label']} in {s['city']}, {s['country']} ({s['place']}). Photo, exact location, "
         f"directions, artist ({re.sub(r' *[(].*?[)]', '', s['artist'])}), status and visitor access.")
    return t if len(t) <= 200 else t[:197].rsplit(' ', 1)[0] + '…'


def ld(obj):
    return '<script type="application/ld+json">\n' + json.dumps(obj, ensure_ascii=False, indent=1).replace('</', '<\\/') + '\n</script>'


def statue_ld(s):
    img, *_ = img_abs(s)
    image = s['img'] if s.get('img', '').startswith('http') else img
    o = {
        '@context': 'https://schema.org',
        '@type': ['TouristAttraction', 'Sculpture'],
        'name': s['label'],
        'description': s['note'],
        'url': page_url(s),
        'image': ({'@type': 'ImageObject', 'url': image, 'creditText': s['photo_credit'].strip()}
                  if (s.get('photo_credit') or '').strip() else image),
        'geo': {'@type': 'GeoCoordinates', 'latitude': s['lat'], 'longitude': s['lng']},
        'address': {'@type': 'PostalAddress', 'streetAddress': s['place'], 'addressLocality': s['city'],
                    'addressCountry': COUNTRY_ISO.get(s['country'], s['country'])},
        'hasMap': f"https://www.google.com/maps/search/?api=1&query={s['lat']},{s['lng']}",
    }
    c = creators(s)
    if c:
        o['creator'] = c if len(c) > 1 else c[0]
    if s['slug'] == 'budapest':  # official site: free, 24/7
        o['isAccessibleForFree'] = True
    v = s.get('visit') or {}
    if v.get('sources'):  # only claim access facts that the guide cites
        if isinstance(v.get('public_access'), bool):
            o['publicAccess'] = v['public_access']
        if isinstance(v.get('free'), bool):
            o['isAccessibleForFree'] = v['free']
    return o


def breadcrumb_ld(items):
    return {'@context': 'https://schema.org', '@type': 'BreadcrumbList',
            'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': u}
                                for i, (n, u) in enumerate(items)]}


def nodes21(data):
    series = sorted([s for s in data['statues'] if s.get('series21')], key=unveil_key)
    installed = [s for s in series if s['status'] in CHECKABLE]
    return series, installed


def home_ld(data):
    st = data['statues']
    installed = [s for s in st if s['status'] in CHECKABLE]
    planned = [s for s in st if s['status'] not in CHECKABLE and s['status'] == 'Planned']
    unlisted = [s for s in st if s['status'] not in CHECKABLE and s['status'] != 'Planned']
    newest = max(installed, key=unveil_key)
    series, s21 = nodes21(data)
    others = [s for s in st if not s.get('series21')]
    def short(s):
        nm = s['city'] if s['label'].startswith('Satoshi Statue') else 'the ' + s['label']
        art = re.sub(r' *[(].*?[)]', '', s['artist'])
        return f"{nm} ({art})" if s.get('creatorVerified') is not False else nm
    parts = [short(s) for s in sorted(others, key=unveil_key)]
    other_txt = ', '.join(parts[:-1]) + ' and ' + parts[-1] if len(parts) > 1 else ''.join(parts)
    items = sorted(st, key=lambda s: -sort_year(s['year']))
    item_list = {
        '@context': 'https://schema.org', '@type': 'ItemList',
        'name': 'Satoshi Nakamoto statues and Bitcoin monuments around the world',
        'numberOfItems': len(items),
        'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'url': page_url(s), 'name': s['label']}
                            for i, s in enumerate(items)],
    }
    faq = {
        '@context': 'https://schema.org', '@type': 'FAQPage',
        'mainEntity': [
            {'@type': 'Question', 'name': 'How many Satoshi statues are there?',
             'acceptedAnswer': {'@type': 'Answer', 'text':
                 f"satoshistatues.com tracks {len(st)} Satoshi Nakamoto statues and Bitcoin monuments: {len(installed)} on the Satoshi Passport and "
                 f"{len(planned)} planned: " + ', '.join(f"Valentina Picozzi’s {s['city']} statue, unveiled {s['unveiled']} and awaiting a permanent public site" for s in planned) +
                 (f", plus {len(unlisted)} unveiled but not on the passport yet: " + ', '.join(f"the {s['label']}, unveiled {s['unveiled']} (public visiting hours not published yet)" for s in unlisted) if unlisted else '') + ". "
                 f"{len(s21)} of the 21 statues in Valentina Picozzi’s “21 Nodes” series are on the passport so far."}},
            {'@type': 'Question', 'name': 'Where is the newest Satoshi statue?',
             'acceptedAnswer': {'@type': 'Answer', 'text':
                 f"The newest installed statue is in {newest['city']}, {newest['country']}, at {newest['place']}. "
                 f"It was unveiled on {newest['unveiled']}. The next confirmed node is Prague: its statue is funded and the location is being negotiated with the city."}},
            {'@type': 'Question', 'name': 'Who makes the Satoshi statues?',
             'acceptedAnswer': {'@type': 'Answer', 'text':
                 f"Most are by Italian artist Valentina Picozzi (Satoshi Gallery): the “disappearing” stainless-steel Satoshi of her “21 Nodes” series, "
                 f"unveiled so far in {', '.join(s['city'] for s in series[:-1])} and {series[-1]['city']}. The other monuments on the map are separate works: {other_txt}."}},
        ],
    }
    return site_ld(data) + '\n  ' + ld(item_list) + '\n  ' + ld(faq), faq


# ---------------------------------------------------------------- shared page chrome
CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0d1117;color:#e6edf3;line-height:1.5}
a{color:#f7931a}
.top{background:#161b22;border-bottom:1px solid #30363d;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.top .brand{display:inline-flex;align-items:center;gap:12px;text-decoration:none;border-radius:6px;min-width:0}
.top .brand:focus-visible{outline:2px solid #f7931a;outline-offset:3px}
.brand-logo{display:block;height:44px;width:auto}
.top .tagline{color:#8b949e;font-size:.85rem;padding-left:12px;border-left:1px solid #30363d;line-height:1.3}
.top nav{display:flex;gap:8px;flex-wrap:wrap}
.top nav a{color:#e6edf3;text-decoration:none;border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-size:.88rem;min-height:44px;display:inline-flex;align-items:center}
.top nav a:hover{border-color:#f7931a;color:#f7931a}
main{max-width:860px;margin:0 auto;padding:18px 16px calc(40px + env(safe-area-inset-bottom,0px))}
.crumbs{font-size:.8rem;color:#8b949e;margin-bottom:10px}
.crumbs a{color:#8b949e}
h1{color:#f7931a;font-size:1.7rem;line-height:1.25;margin-bottom:4px}
.sub{color:#8b949e;margin-bottom:16px}
h2{font-size:1.1rem;margin:26px 0 10px;color:#e6edf3}
figure{margin:0 0 16px}
figure img{width:100%;height:auto;max-height:70vh;object-fit:contain;background:#161b22;border:1px solid #30363d;border-radius:10px;display:block}
figcaption{font-size:.75rem;color:#8b949e;margin-top:4px}
.facts{display:grid;grid-template-columns:max-content 1fr;gap:6px 14px;background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px;font-size:.92rem}
.facts dt{color:#8b949e}
.badge{display:inline-block;font-size:.75rem;padding:2px 8px;border-radius:4px;font-weight:600}
.b-installed{background:#1a3a2a;color:#3fb950}.b-restored{background:#3a2e1a;color:#f7931a}.b-planned,.b-unveiled{background:#1a2a3a;color:#58a6ff}.b-damaged{background:#3a2a1a;color:#f0883e}.b-donated{background:#2a1f3a;color:#bc8cff}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 16px;border-radius:8px;font-weight:700;text-decoration:none;font-size:.92rem;border:1px solid #30363d;color:#e6edf3;background:#21262d}
.btn.primary{background:#f7931a;border-color:#f7931a;color:#0d1117}
.btn:hover{border-color:#f7931a}
.note{font-size:.95rem}
.src{font-size:.85rem;color:#8b949e;padding-left:18px}
.src li{margin:3px 0}
.others{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px}
.others a{display:flex;min-height:44px;align-items:center;padding:6px 10px;border:1px solid #30363d;border-radius:8px;text-decoration:none;color:#e6edf3;font-size:.88rem;background:#161b22}
.others a:hover{border-color:#f7931a;color:#f7931a}
.callout{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:8px;padding:10px 14px;font-size:.9rem;margin:14px 0}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid #30363d;vertical-align:top}
th{color:#8b949e;font-weight:600;font-size:.8rem}
.tbl{overflow-x:auto;border:1px solid #30363d;border-radius:10px;background:#161b22}
.big{font-size:3rem;font-weight:800;line-height:1}.big small{font-size:1.4rem;color:#8b949e}
.bar{height:10px;background:#21262d;border-radius:5px;overflow:hidden;margin:10px 0 4px;max-width:420px}.bar span{display:block;height:100%;background:linear-gradient(90deg,#f7931a,#ffb347)}
footer.site{border-top:1px solid #30363d;margin-top:30px;padding-top:14px;font-size:.8rem;color:#8b949e}.support-line{display:block;margin-top:6px;font-size:.8rem;color:#8b949e}
#comments{min-height:120px}
@media (max-width:600px){.brand-logo{height:36px}.top .tagline{font-size:.72rem;padding-left:10px}.top nav{width:100%}h1{font-size:1.4rem}.facts{grid-template-columns:1fr;gap:0}.facts dt{margin-top:8px}.facts dt:first-child{margin-top:0}td,th{padding:8px 6px}}
'''.strip()

ICON_LINKS = ('<link rel="icon" href="/favicon.ico" sizes="32x32" />\n'
              '  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />\n'
              '  <link rel="apple-touch-icon" href="/apple-touch-icon.png" />')
LOGO_IMG = '<img class="brand-logo" src="/brand/logo-lockup.svg" width="310" height="88" alt="Satoshi Nakamoto Statues" />'


def head(title, desc, canonical, image, iw, ih, img_alt, extra_ld):
    dims = f'\n  <meta property="og:image:width" content="{iw}" />\n  <meta property="og:image:height" content="{ih}" />' if iw else ''
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <script>if (location.protocol === "http:" && !/^(localhost|127\\.)/.test(location.hostname)) location.replace("https:" + location.href.slice(5));</script>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <title>{e(title)}</title>
  <meta name="description" content="{e(desc)}" />
  <meta name="robots" content="index, follow" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="{canonical}" />
  <meta property="og:title" content="{e(title)}" />
  <meta property="og:description" content="{e(desc)}" />
  <meta property="og:image" content="{image}" />{dims}
  <meta property="og:image:alt" content="{e(img_alt)}" />
  <meta property="og:site_name" content="Satoshi Statues" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{e(title)}" />
  <meta name="twitter:description" content="{e(desc)}" />
  <meta name="twitter:image" content="{image}" />
  <meta name="twitter:image:alt" content="{e(img_alt)}" />
  <meta name="theme-color" content="#0d1117" />
  {ICON_LINKS}
  {FEED_LINK}
  {extra_ld}
  <style>{CSS}{ALERT_CSS}{STORY_CSS}{VISIT_CSS}{EVENTS_CSS}{GALLERY_CSS}</style>
  {api_script()}
</head>
<body>
  <header class="top">
    <a class="brand" href="/" title="Satoshi Nakamoto Statues: map home">{LOGO_IMG}<span class="tagline">Every Satoshi statue on Earth</span></a>
    <nav><a href="/">🗺️ Map</a><a href="/21-nodes/">21 Nodes</a><a href="/leaderboard/">🏆 Leaderboard</a></nav>
  </header>
'''


TAIL = '''  <script data-goatcounter="https://satoshistatues.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body>
</html>
'''


FEED_URL = SITE + '/feed.xml'
FEED_LINK = f'<link rel="alternate" type="application/atom+xml" title="Satoshi Statues – new statues" href="{FEED_URL}" />'


def nostr_url(data):
    npub = (data.get('config') or {}).get('nostr_npub', '').strip()
    return f'https://njump.me/{npub}' if npub else ''


def nostr_json(data):
    hexkey = (data.get('config') or {}).get('nostr_hex', '').strip().lower()
    if not hexkey:
        return None
    if not re.fullmatch(r'[0-9a-f]{64}', hexkey):
        raise SystemExit('config.nostr_hex must be 64 lowercase hex chars')
    return json.dumps({'names': {'_': hexkey}}, separators=(',', ':'))


def site_ld(data):
    same = [u for u in [nostr_url(data)] if u]
    npub = (data.get('config') or {}).get('nostr_npub', '').strip()
    if npub:
        same.append(f'nostr:{npub}')
    xh = (data.get('config') or {}).get('photo_x_handle', '').strip().lstrip('@')
    if xh:
        same.append(f'https://x.com/{xh}')
    org = {'@context': 'https://schema.org', '@type': 'Organization', '@id': SITE + '/#org',
           'name': 'Satoshi Statues', 'url': SITE + '/', 'logo': SITE + '/brand/icon-512.png'}
    if same:
        org['sameAs'] = same
    web = {'@context': 'https://schema.org', '@type': 'WebSite', '@id': SITE + '/#website',
           'name': 'Satoshi Nakamoto Statues – Global Interactive Map', 'url': SITE + '/',
           'publisher': {'@id': SITE + '/#org'}}
    if same:
        web['sameAs'] = same
    return ld(org) + '\n  ' + ld(web)


FOLLOW_X_URL = 'https://x.com/satoshistatue21'


def signup_html(data, where):
    # No email sign-up: one line pointing people to X for new statues and events.
    return (f'<section class="alert-box follow-x" aria-label="Follow us on X"><p class="alert-fine" style="margin:0">'
            f'<a href="{FOLLOW_X_URL}" target="_blank" rel="noopener">Follow us on X</a> to stay up to date on new statues and events.</p></section>')


# Visitor photos: we don't collect them by email. One short line asks people to post their own photo and tag us.
SOCIAL_TAGS = [('X', '@satoshistatue21', 'https://x.com/satoshistatue21'),
               ('Instagram', '@satoshi.statues', 'https://www.instagram.com/satoshi.statues/'),
               ('TikTok', '@satoshistatues', 'https://www.tiktok.com/@satoshistatues')]
SOCIAL_LINE = ('📸 Snap a photo? Post it and tag us: '
               + ', '.join(f'<a href="{u}" target="_blank" rel="noopener noreferrer">{h}</a> on {n}' for n, h, u in SOCIAL_TAGS)
               + ', #SatoshiStatues.')


def photo_cta(s, data):
    return f'<section class="photo-cta" id="photo" aria-label="Post your photo"><p class="alert-fine" style="margin:0">{SOCIAL_LINE}</p></section>'


def credit_html(s):
    # Optional per-statue "photo_credit": plain text, or an @handle that links to X
    # (to the source post when "photo_source" is set).
    cr = (s.get('photo_credit') or '').strip()
    if not cr:
        return ''
    src = (s.get('photo_source') or '').strip()  # optional: URL of the post the photo comes from
    if src:
        who = f'<a href="{e(src)}" target="_blank" rel="noopener noreferrer">{e(cr)}</a>'
    elif re.fullmatch(r'@[A-Za-z0-9_]{1,15}', cr):
        who = f'<a href="https://x.com/{cr[1:]}" target="_blank" rel="noopener noreferrer">{e(cr)}</a>'
    else:
        who = e(cr)
    return f'<span class="photo-credit">Photo: {who}</span>'


ALERT_CSS = (
    '.alert-box{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:10px;padding:12px 14px;margin:16px 0}'
    '.alert-fine{font-size:.8rem;color:#8b949e;margin:6px 0 0;line-height:1.45}'
    '.photo-cta{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:10px;padding:12px 14px;margin:16px 0}'
    '.photo-actions{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0 4px}'
    '.photo-actions .btn{max-width:100%}'
    '.photo-cta .alert-fine a,.photo-credit a{padding:15px 0;margin:-15px 0}'
    '.photo-cta .alert-fine a{color:#f7931a}'
    '.follow-x .alert-fine a{color:#f7931a;font-weight:600}'
    '.photo-credit{display:block;margin-top:2px}'
    '.checkin-count{font-size:.85rem;color:#3fb950;margin:6px 0 0}'
    '.photo-credit a{color:#8b949e}'
    '.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}'
)


def feed_xml(data):
    # Atom feed: one entry per statue, newest unveiling first.
    items = sorted(data['statues'], key=unveil_key, reverse=True)
    ts = lambda s: unveil_key(s).strftime('%Y-%m-%dT00:00:00Z')
    x = lambda t: html.escape(str(t), quote=False)
    entries = ''
    for s in items:
        artist = re.sub(r' *[(].*?[)]', '', s['artist'])
        if s.get('creatorVerified') is False:
            artist += ' (credit unverified)'
        summary = (f"{s['city']}, {s['country']} · {s['place']}. Artist: {artist}. "
                   f"Status: {s.get('statusLabel') or s['status']}. Unveiled {s.get('unveiled') or s['year']}.")
        entries += (
            '  <entry>\n'
            f"    <title>{x(s['label'])} ({x(s['city'])}, {x(s['country'])})</title>\n"
            f'    <link rel="alternate" type="text/html" href="{page_url(s)}" />\n'
            f'    <id>{page_url(s)}</id>\n'
            f'    <published>{ts(s)}</published>\n'
            f'    <updated>{ts(s)}</updated>\n'
            f'    <author><name>{x(artist)}</name></author>\n'
            f"    <category term=\"{x(s['status'])}\" />\n"
            f'    <summary>{x(summary)}</summary>\n'
            '  </entry>\n')
    updated = max(unveil_key(s) for s in items).strftime('%Y-%m-%dT00:00:00Z')
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        '  <title>Satoshi Statues – new Satoshi Nakamoto statues</title>\n'
        '  <subtitle>Every known Satoshi Nakamoto statue and Bitcoin monument, newest first.</subtitle>\n'
        f'  <link rel="self" type="application/atom+xml" href="{FEED_URL}" />\n'
        f'  <link rel="alternate" type="text/html" href="{SITE}/" />\n'
        f'  <id>{SITE}/</id>\n'
        f'  <updated>{updated}</updated>\n'
        f'  <author><name>satoshistatues.com</name><uri>{SITE}/</uri></author>\n'
        f'  <icon>{SITE}/brand/icon-512.png</icon>\n'
        f'{entries}</feed>\n')


def status_badge(st, label=None):
    return f'<span class="badge b-{st.lower()}">{e(label or st)}</span>'


def src_list(sources):
    return '<ol class="src">' + ''.join(
        f'<li><a href="{e(x["url"])}" target="_blank" rel="noopener noreferrer">{e(x["label"])}</a></li>' for x in sources) + '</ol>'


APPROX_HTML = ' <span class="approx" style="color:#d29922">(📍 Approximate location)</span>'


def pin_sub(s):
    # statue.pin_note (str, optional) explains what the pin marks, e.g. 'Pin: unveiling location (20 Apr 2026)'
    if (s.get('pin_note') or '').strip():
        return ' · 📍 ' + e(s['pin_note'].strip())
    return ' · 📍 Approximate location' if s.get('pin_approx') else ''


def pin_html(s):
    if (s.get('pin_note') or '').strip():
        return f' <span class="approx" style="color:#d29922">(📍 {e(s["pin_note"].strip())})</span>'
    return APPROX_HTML if s.get('pin_approx') else ''


# ---------- Last confirmed line, status alert, visitor photos (see PHOTOS.md) ----------
# statues.json → statue.last_confirmed (YYYY-MM), last_confirmed_source (visitor_photo | gps_checkin | report),
# last_confirmed_url, optional last_confirmed_kind ('reported' = say "Last reported", not "standing"),
# alert (null or {type, title, text, date YYYY-MM-DD, source_url, source_label}).
# photos.json → {"photos": [{slug, file, credit, month YYYY-MM, approved}]}, images in /photos/<slug>/.
# The newest approved photo overrides last_confirmed when it is newer (source visitor_photo).
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
CONFIRM_SOURCES = {'visitor_photo': 'Visitor photo', 'gps_checkin': 'GPS-verified check-in', 'report': 'News/official report'}


def fmt_month(m):
    y, mo = m.split('-')[:2]
    return f'{MONTHS[int(mo) - 1]} {y}'


def fmt_day(d):
    y, mo, dd = d.split('-')
    return f'{int(dd)} {MONTHS[int(mo) - 1]} {y}'


def statue_photos(s, data):
    return data.get('photos', {}).get(s['slug'], [])


def photo_url(ph, small=False):
    f = ph['file']
    if small:
        sm = re.sub(r'\.jpe?g$', '', f, flags=re.I) + '-sm.jpg'
        if os.path.exists(os.path.join(ROOT, 'photos', ph['slug'], sm)):
            f = sm
    return f"/photos/{ph['slug']}/{f}"


def last_confirmed(s, data):
    """(month, source, url, kind) or None. The newest approved visitor photo wins when it is newer."""
    lc = None
    if re.fullmatch(r'\d{4}-\d{2}', s.get('last_confirmed') or ''):
        lc = (s['last_confirmed'], s.get('last_confirmed_source') or 'report', s.get('last_confirmed_url') or '',
              s.get('last_confirmed_kind') or 'standing')
    phs = statue_photos(s, data)
    if phs and re.fullmatch(r'\d{4}-\d{2}', phs[0].get('month') or '') and (not lc or phs[0]['month'] >= lc[0]):
        lc = (phs[0]['month'], 'visitor_photo', '#visitor-photos', 'standing')
    return lc


def confirmed_html(s, data):
    badge = (' <a class="pv-badge" href="#visitor-photos">📸 Photo-verified</a>' if statue_photos(s, data) else '')
    lc = last_confirmed(s, data)
    if not lc:
        return f'<p class="confirmed">Not yet confirmed by a visitor · <a href="#photo">Post a photo</a>{badge}</p>'
    month, src, url, kind = lc
    lead = 'Last reported' if kind == 'reported' else 'Last confirmed standing'
    lab = e(CONFIRM_SOURCES.get(src, CONFIRM_SOURCES['report']))
    if url:
        ext = '' if url.startswith('#') or url.startswith('/') else ' target="_blank" rel="noopener noreferrer"'
        lab = f'<a href="{e(url)}"{ext}>{lab}</a>'
    return f'<p class="confirmed">{lead}: <strong>{fmt_month(month)}</strong> · {lab}{badge}</p>'


ALERT_ICONS = {'damaged': '⚠️', 'donated': 'ℹ️', 'not_installed': '🚧', 'moved': '📍', 'removed': '⚠️'}


def alert_html(s):
    a = s.get('alert')
    if not a or not (a.get('text') or '').strip():
        return ''
    t = (a.get('type') or 'notice').lower()
    src = ''
    if a.get('source_url'):
        src = (f' <a href="{e(a["source_url"])}" target="_blank" rel="noopener noreferrer">Source: {e(a.get("source_label") or "report")}</a>')
    date = f'<span class="sa-date">{fmt_day(a["date"])}</span> · ' if re.fullmatch(r'\d{4}-\d{2}-\d{2}', a.get('date') or '') else ''
    return (f'<div class="status-alert sa-{e(t)}" role="note"><p class="sa-title">{ALERT_ICONS.get(t, "ℹ️")} {e(a.get("title") or t.replace("_", " ").capitalize())}</p>'
            f'<p class="sa-text">{date}{e(a["text"].strip())}{src}</p></div>')


GALLERY_JS = ('<script>(function(){var d=document.getElementById("pv-dialog");if(!d||!d.showModal)return;var im=d.querySelector("img"),cap=d.querySelector("p");'
              'document.addEventListener("click",function(ev){var a=ev.target.closest&&ev.target.closest("[data-pv-full]");'
              'if(a){ev.preventDefault();im.src=a.getAttribute("data-pv-full");im.alt=a.getAttribute("data-pv-alt")||"";cap.textContent=a.getAttribute("data-pv-cap")||"";d.showModal();return}'
              'if(ev.target===d||ev.target.closest("[data-pv-close]")){d.close()}});'
              'd.addEventListener("close",function(){im.removeAttribute("src")});})();</script>')


def gallery_html(s, data):
    # Rendered only when the statue has approved photos; otherwise nothing at all (the photo CTA box below asks for photos).
    phs = statue_photos(s, data)
    if not phs:
        return ''
    items = []
    for ph in phs:
        cr = (ph.get('credit') or '').strip() or 'Anonymous'
        cap = f'{cr} · {fmt_month(ph["month"])}' if ph.get('month') else cr
        alt = f'Visitor photo of the {s["label"]} by {cr}'
        wh = f' width="{ph["w"]}" height="{ph["h"]}"' if ph.get('w') else ''
        items.append(f'<li><a href="{photo_url(ph)}" data-pv-full="{photo_url(ph)}" data-pv-alt="{e(alt)}" data-pv-cap="{e(cap)}">'
                     f'<img src="{photo_url(ph, True)}" alt="{e(alt)}"{wh} loading="lazy" decoding="async"></a>'
                     f'<span class="vp-cap">{e(cap)}</span></li>')
    return (f'<section class="gallery" id="visitor-photos" aria-labelledby="vp-title"><h2 id="vp-title">📸 Visitor photos</h2>'
            f'<ul class="vp-grid">{"".join(items)}</ul>'
            f'<dialog id="pv-dialog" aria-label="Photo"><button type="button" class="pv-close" data-pv-close aria-label="Close">✕</button>'
            f'<img alt=""><p></p></dialog></section>' + GALLERY_JS)


GALLERY_CSS = ('.confirmed{font-size:.88rem;color:#8b949e;margin:-8px 0 14px;line-height:1.6}.confirmed strong{color:#e6edf3}'
               '.confirmed a{color:#f7931a}'
               '.pv-badge{display:inline-flex;align-items:center;gap:4px;margin-left:6px;font-size:.75rem;font-weight:700;color:#3fb950!important;'
               'border:1px solid #3fb950;border-radius:999px;padding:1px 8px;text-decoration:none;vertical-align:1px}'
               '.status-alert{border:1px solid #30363d;border-left:4px solid #f0883e;background:#2a1d12;border-radius:10px;padding:12px 14px;margin:0 0 16px}'
               '.status-alert.sa-donated{border-left-color:#bc8cff;background:#1f1830}.status-alert.sa-not_installed{border-left-color:#58a6ff;background:#121f30}'
               '.sa-title{font-weight:700;font-size:.95rem;margin:0 0 4px;color:#e6edf3}.sa-text{font-size:.88rem;line-height:1.5;margin:0}'
               '.sa-date{font-weight:700}.sa-text a{display:inline-block;padding:4px 0;color:#f7931a}'
               '.gallery{margin:22px 0;scroll-margin-top:12px}'
               '.vp-grid{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}'
               '.vp-grid a{display:block;border-radius:8px;overflow:hidden;border:1px solid #30363d;background:#161b22}'
               '.vp-grid img{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:cover}'
               '.vp-cap{display:block;font-size:.75rem;color:#8b949e;margin-top:3px}'
               '#pv-dialog{border:0;padding:0;background:transparent;max-width:100vw;max-height:100vh;margin:auto;color:#e6edf3}'
               '#pv-dialog::backdrop{background:rgba(0,0,0,.88)}'
               '#pv-dialog img{display:block;max-width:96vw;max-height:84vh;width:auto;height:auto;border-radius:8px;margin:0 auto}'
               '#pv-dialog p{text-align:center;font-size:.85rem;color:#c9d1d9;margin-top:6px}'
               '.pv-close{position:fixed;top:calc(10px + env(safe-area-inset-top,0px));right:10px;width:44px;height:44px;border-radius:50%;border:1px solid #30363d;'
               'background:#21262d;color:#e6edf3;font-size:1.1rem;cursor:pointer}')


# ---------- "The story" (optional per statue; see GUIDES.md) ----------
# statues.json → statue.story: [{"label": "Artist", "text": "…", "reported": true?, "sources": [{"label", "url"}]}]
# Only sourced facts. `reported: true` marks partly confirmed items (shown with a 'Reported' tag).
def story_html(s):
    items = [x for x in (s.get('story') or []) if (x.get('text') or '').strip()]
    if not items:
        return ''
    rows = []
    for x in items:
        cites = ''.join(f' <a class="cite" href="{e(c["url"])}" target="_blank" rel="noopener noreferrer">{e(c["label"])}</a>'
                        for c in x.get('sources', []) if c.get('url'))
        tag = '<span class="rep">Reported</span> ' if x.get('reported') else ''
        rows.append(f'<dt>{e(x["label"])}</dt><dd>{tag}{e(x["text"].strip())}'
                    f'{f"<span class=cites>Sources:{cites}</span>" if cites else ""}</dd>')
    return (f'<section class="story" id="story" aria-labelledby="story-title"><h2 id="story-title">📖 The story</h2>'
            f'<dl>{"".join(rows)}</dl>'
            f'<p class="note" style="font-size:.8rem;color:#8b949e;margin-top:8px">Only facts we could source. Items tagged “Reported” are not fully confirmed.</p></section>')


STORY_CSS = ('.story{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:4px 16px 14px;margin:22px 0;scroll-margin-top:12px}'
             '.story h2{margin:14px 0 6px}.story dt{font-size:.95rem;color:#f7931a;font-weight:700;margin:14px 0 4px}'
             '.story dd{margin:0;font-size:.95rem;line-height:1.55}.story .cites{display:block;font-size:.8rem;color:#8b949e;margin-top:4px}'
             '.story .cite{margin-right:6px;display:inline-block;padding:6px 0}'
             '.story .rep{display:inline-block;font-size:.7rem;font-weight:700;color:#d29922;border:1px solid #d29922;border-radius:4px;padding:0 5px;margin-right:2px;vertical-align:1px}')


CHECKIN_CSS = ('.checkin-box{background:#161b22;border:1px solid #30363d;border-left:3px solid #3fb950;border-radius:10px;padding:12px 14px;margin:14px 0}'
               '.ci-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px}'
               '.btn.ci-btn{background:#238636;border-color:#238636;color:#fff;font-size:1rem}.btn.ci-btn:hover{background:#2ea043;border-color:#2ea043}.btn.ci-btn:disabled{opacity:.7;cursor:wait}'
               '.ci-stamp{display:inline-flex;align-items:center;min-height:44px;padding:0 12px;border:2px dashed #3fb950;border-radius:8px;color:#3fb950;font-weight:700;transform:rotate(-1deg)}'
               '.ci-map{color:#8b949e;font-size:.88rem;display:inline-flex;align-items:center;min-height:44px}.ci-map:hover{color:#f7931a}'
               '.ci-what{font-size:.92rem;color:#e6edf3;margin:8px 0 0;line-height:1.45}'
               '.ci-note{font-size:.85rem;color:#8b949e;margin:8px 0 0;line-height:1.45}.ci-note a{color:#f7931a}'
               '.checkin-msg{margin-top:10px;font-size:.88rem;line-height:1.45;color:#e6edf3;background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:9px 11px}'
               '.checkin-msg.ok{border-color:#3fb950;color:#3fb950}.checkin-msg.warn{border-color:#f7931a}'
               '.checkin-msg details{margin-top:6px}.checkin-msg summary{cursor:pointer;color:#f7931a;font-weight:600}.checkin-msg ul{margin:6px 0 0 18px;padding:0}.checkin-msg li{margin:3px 0}'
               '.checkin-msg a{color:#f7931a}.geo-diag{margin-top:6px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.7rem;color:#8b949e;word-break:break-word}'
               '.lb-note{margin-top:6px}.lb-nick{margin-top:8px}.lb-nick-q{font-size:.82rem;color:#c9d1d9;margin-bottom:6px}.lb-nick-row{display:flex;gap:6px;flex-wrap:wrap}'
               '.lb-nick input{flex:1 1 150px;min-width:0;min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:16px;font-family:inherit}'
               '.lb-nick button{min-height:44px;padding:8px 14px;border-radius:8px;border:none;background:#f7931a;color:#0d1117;font-weight:700;font-family:inherit;cursor:pointer}'
               '.lb-nick button.lb-skip{background:#21262d;color:#c9d1d9;border:1px solid #30363d;font-weight:600}.lb-nick-msg{font-size:.8rem;color:#f0883e;margin-top:4px}'
               '.ci-share{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.ci-share .btn{color:#e6edf3;font-size:.85rem}'
               '.checkin-box [hidden]{display:none!important}')


# One short line under every check-in button saying what the walker gets (Noah via Matt, 2026-11-03).
# Paying vs. not comes from fountain.json (fountain_on), never a hard-coded list. Sats need a Lightning address and
# only last while the giveaway budget/limits do (fountain.js claim form + Worker issueClaim), so the paying line says so.
# fountain.js / the home map switch a paying line to the non-paying one when the Worker says the giveaway is off or paused.
def ci_what(kind):
    card = 'Proof of Walk card' if POW_ON else 'card'
    return {'pay': f'Check in to get your {card}, add this statue to your passport and claim free sats with a Lightning address while the giveaway lasts. No sign-up needed.',
            'free': f'Check in to get your {card} and add this statue to your passport. No sign-up needed.',
            'near': f'Check in at the nearest statue to get its {card} and add it to your passport. No sign-up needed.',
            'near_pay': ' At giveaway statues you can also claim free sats.'}[kind]


def ci_what_script(data):
    # Home map copy (popup "Check in" + passport "Check in here"): same strings as the statue pages.
    d = {'pay': ci_what('pay'), 'free': ci_what('free'), 'near': ci_what('near') + (ci_what('near_pay') if fountain_on(data) else '')}
    return f'<script>window.SS_CI_WHAT = {json.dumps(d, ensure_ascii=False)};</script>'


def checkin_box(s, data):
    # One-tap passport stamp on the statue page (logic in checkin.js, shared with the home map).
    # Only statues the map lets you stamp (CHECKABLE) get it; others keep the "not yet installed" note.
    if s['status'] not in CHECKABLE:
        return ''
    stampable = ','.join(o['slug'] for o in data['statues'] if o['status'] in CHECKABLE)
    attrs = {'data-slug': s['slug'], 'data-name': s['name'], 'data-label': s['label'], 'data-city': s['city'],
             'data-page': s['page'], 'data-url': page_url(s), 'data-share-name': share_name(s), 'data-lat': s['lat'], 'data-lng': s['lng'],
             'data-checkins': s.get('checkins', 0), 'data-checkable': stampable}
    a = ' '.join(f'{k}="{e(str(v))}"' for k, v in attrs.items())
    return (f'\n    <style>{CHECKIN_CSS}</style><div class="checkin-box" data-ss-checkin {a}>'
            f'<div class="ci-row"><button class="btn ci-btn" type="button" data-ss-checkin-btn>📍 Check in here</button>'
            f'<span class="ci-stamp" hidden></span>'
            f'<a class="ci-map" href="/?s={s["page"]}">🗺️ Open on the map</a></div>'
            + (f'<p class="ci-what" data-ci-what data-free="{e(ci_what("free"))}">{e(ci_what("pay"))}</p>' if fountain_on(data, s)
               else f'<p class="ci-what" data-ci-what>{e(ci_what("free"))}</p>') +
            f'<p class="ci-note">At the statue? Tap within 150 m. '
            f'Your location is only checked, never stored. <a href="/leaderboard/">Leaderboard</a>'
            + (' · <a href="/proof-of-walk/">Proof of Walk</a>' if POW_ON else '') + '</p>'
            f'<div class="checkin-msg" aria-live="polite" hidden></div></div>')


def statue_page(s, data):
    title = f"{s['label']} – Location, Directions & Photos"
    desc = describe(s)
    alt = f"{s['label']}, {s['place']}, {s['city']}"
    lds = ld(statue_ld(s)) + '\n  ' + ld(breadcrumb_ld([('Map', SITE + '/'), (s['label'], page_url(s))]))
    out = head(title, desc, page_url(s), f"{SITE}/{og_path(s)}", OG_W, OG_H, f"{s['label']}: {s['city']}, {s['country']} (satoshistatues.com card)", lds)
    nav_end = '<a href="/leaderboard/">🏆 Leaderboard</a></nav>'
    assert out.count(nav_end) == 1 and HOME_TIP['button']
    out = out.replace(nav_end, nav_end[:-len('</nav>')] + HOME_TIP['button'] + '</nav>')  # same '₿ Tip' as the home header
    img_html = ''
    if s.get('img'):
        src = s['img'] if s['img'].startswith('http') else '/' + s['img']
        wh = f' width="{s["imgW"]}" height="{s["imgH"]}"' if s.get('imgW') else ''
        img_html = (f'<figure><img src="{e(src)}" alt="{e(alt)}"{wh} decoding="async" '
                    f'onerror="this.closest(\'figure\').remove()"><figcaption>{e(s["name"])} · {e(s["place"])}{credit_html(s)}</figcaption></figure>')
    artist = f'<a href="{e(s["artistUrl"])}" target="_blank" rel="noopener noreferrer">{e(s["artist"])}</a>' if s.get('artistUrl') else e(s['artist'])
    if s.get('creatorVerified') is False:
        artist += ' <span style="color:#8b949e">(credit not independently verified)</span>'
    if s.get('access'):
        acc = e(s['access'])
        if s.get('accessSource'):
            acc += f' <a href="{e(s["accessSource"]["url"])}" target="_blank" rel="noopener noreferrer">Source: {e(s["accessSource"]["label"])}</a>'
    elif ((s.get('visit') or {}).get('hours_access') or '').strip():
        # no short `access` line: summarise the guide's sourced Hours & access instead of saying 'Unknown'
        first = re.split(r'\n\s*\n', s['visit']['hours_access'].strip())[0]
        acc = e(first) + ' <a href="#visiting">More in Visiting ↓</a>'
    else:
        acc = 'Unknown. Check locally before you go.'
    directions = f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lng']}"
    series = ''
    if s.get('series21'):
        series = (f'<div class="callout">Part of Valentina Picozzi’s <strong>21 Nodes</strong> series of Satoshi statues. '
                  f'<a href="/21-nodes/">See all 21 Nodes →</a></div>')
    others = ''.join(f'<li><a href="/{o["page"]}/">{e(o["label"])}</a></li>'
                     for o in sorted(data['statues'], key=lambda o: -sort_year(o['year'])) if o is not s)
    # stampable statues get the check-in box (with its own "Open on the map" link) near the top instead
    map_btn = '' if s['status'] in CHECKABLE else f'\n      <a class="btn" href="/?s={s["page"]}">🗺️ Open on the map</a>'
    stamp = ('' if s['status'] in CHECKABLE else
             f'\n    <p class="note" style="margin-top:6px;color:#8b949e">{e(s.get("stamp_note") or "Not yet installed, so there’s no card to collect yet (not counted in the total).")}</p>')
    giscus_attrs = {
        'data-repo': REPO, 'data-repo-id': GISCUS['repoId'], 'data-category': GISCUS['category'],
        'data-category-id': GISCUS['categoryId'], 'data-mapping': 'specific', 'data-term': f"statue-{s['slug']}",
        'data-strict': '1', 'data-reactions-enabled': '1', 'data-emit-metadata': '0', 'data-input-position': 'top',
        'data-theme': 'dark', 'data-lang': 'en', 'data-loading': 'lazy'}
    gattrs = ' '.join(f'{k}="{e(v)}"' for k, v in giscus_attrs.items())
    out += f'''  <main>
    <div class="crumbs"><a href="/">Map</a> › {e(s['label'])}</div>
    <h1>{e(s['label'])}</h1>
    <p class="sub">{e(s['place'])} · {e(s['city'])}, {e(s['country'])}{pin_sub(s)}</p>
    {confirmed_html(s, data)}
    {alert_html(s)}{checkin_box(s, data)}{fountain_box(s, data)}
    {img_html}
    <dl class="facts">
      <dt>Location</dt><dd>{e(s['place'])}, {e(s['city'])}, {e(s['country'])}</dd>
      <dt>Unveiled</dt><dd>{e(s.get('unveiled') or s['year'])}</dd>
      <dt>Year</dt><dd>{e(s['year'])}</dd>
      <dt>Artist</dt><dd>{artist}</dd>
      <dt>Type</dt><dd>{e(s['type'])}</dd>
      <dt>Status</dt><dd>{status_badge(s['status'], s.get('statusLabel'))}</dd>
      <dt>Access</dt><dd>{acc}</dd>
      <dt>Coordinates</dt><dd>{s['lat']}, {s['lng']}{pin_html(s)}</dd>
    </dl>
    <div class="actions">
      <a class="btn primary" href="{directions}" target="_blank" rel="noopener noreferrer">🧭 Get Directions</a>{map_btn}
      <a class="btn" href="#comments">💬 Comments</a>
    </div>
    {share_box(s)}
    {series}
    <h2>About</h2>
    <p class="note">{e(s['note'])}</p>{stamp}
    {story_html(s)}
    {visit_html(s, data)}
    {events_html(s, data)}
    {gallery_html(s, data)}{checkin_count_html(s)}
    {photo_cta(s, data)}
    <h2>Sources</h2>
    {src_list(s.get('sources', []))}
    <p class="note" style="font-size:.85rem;color:#8b949e;margin-top:8px">Spotted a mistake? <a href="https://github.com/{REPO}/issues/new?title={e('Correction: ' + s['name'])}" target="_blank" rel="noopener noreferrer">Suggest a correction</a>.</p>
    <h2>Other Satoshi statues</h2>
    <ul class="others">{others}</ul>
    <h2 id="comments-title">Comments</h2>
    <p class="note" style="font-size:.85rem;color:#8b949e;margin-bottom:8px">Visit reports, tips and photo links. Powered by giscus (needs a GitHub account). Same thread as on the map.</p>
    <div id="comments"><script src="https://giscus.app/client.js" {gattrs} crossorigin="anonymous" async></script></div>
    {signup_html(data, 'page')}
    {HOME_TIP['html']}
    {footer(data)}
  </main>
'''
    return out + share_script() + '\n' + (checkin_script() + '\n' if s['status'] in CHECKABLE else '') + fountain_script(s, data) + LIVE_COUNT_JS + '\n' + TAIL


def nodes_page(data):
    series, installed = nodes21(data)
    n = len(installed)
    title = f'21 Nodes Tracker – {n} of 21 Satoshi Statues Installed'
    desc = (f'Tracker for Valentina Picozzi’s “21 Nodes” series of Satoshi Nakamoto statues: {n} of 21 installed, '
            f'with locations, years, status, upcoming nodes like Prague, and sources.')
    canonical = SITE + '/21-nodes/'
    item_list = {'@context': 'https://schema.org', '@type': 'ItemList', 'name': '21 Nodes – Satoshi statues by Valentina Picozzi',
                 'numberOfItems': len(series),
                 'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'url': page_url(s), 'name': s['label']} for i, s in enumerate(series)]}
    lds = ld(item_list) + '\n  ' + ld(breadcrumb_ld([('Map', SITE + '/'), ('21 Nodes', canonical)]))
    out = head(title, desc, canonical, OG_IMAGE, 1200, 630, 'Satoshi statues world map', lds)
    rows = ''
    for i, s in enumerate(series, 1):
        cites = ' '.join(f'<a href="{e(x["url"])}" target="_blank" rel="noopener noreferrer">[{j}]</a>' for j, x in enumerate(s.get('sources', []), 1))
        st = (s.get('statusLabel') or s['status']) if s['status'] in CHECKABLE else 'Unveiled, awaiting permanent site'
        cls = 'planned' if s['status'] not in CHECKABLE else s['status'].lower()
        rows += (f'<tr><td>{i}</td><td><a href="/{s["page"]}/">{e(s["city"])}</a><br><span style="color:#8b949e;font-size:.8rem">{e(s["country"])}</span></td>'
                 f'<td>{e(s.get("unveiled") or s["year"])}</td><td><span class="badge b-{cls}">{e(st)}</span></td><td>{cites}</td></tr>')
    up = ''
    for u in data.get('upcoming21', []):
        cites = ' '.join(f'<a href="{e(x["url"])}" target="_blank" rel="noopener noreferrer">[{j}]</a>' for j, x in enumerate(u['sources'], 1))
        up += (f'<tr><td><strong>{e(u["city"])}</strong><br><span style="color:#8b949e;font-size:.8rem">{e(u["country"])}</span></td>'
               f'<td><span class="badge b-planned">{e(u["status"])}</span></td><td>{e(u["summary"])} {cites}</td></tr>')
    pct = round(100 * n / 21, 1)
    unveiled_not_installed = [s for s in series if s['status'] not in CHECKABLE]
    out += f'''  <main>
    <div class="crumbs"><a href="/">Map</a> › 21 Nodes</div>
    <h1>21 Nodes: Valentina Picozzi’s Satoshi statues</h1>
    <p class="sub">“21 Nodes” is the Satoshi Gallery project by Italian artist Valentina Picozzi to place 21 identical “disappearing” Satoshi Nakamoto statues around the world, one for each million of Bitcoin’s 21 million coin cap. <a href="https://bitcoin-austria.at/satoshi-statue/" target="_blank" rel="noopener noreferrer">[Bitcoin Austria]</a> <a href="https://www.tokenpost.com/news/technology/32422" target="_blank" rel="noopener noreferrer">[TokenPost]</a></p>
    <div class="big">{n} <small>of 21 installed</small></div>
    <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="21" aria-valuenow="{n}"><span style="width:{pct}%"></span></div>
    <p class="sub">{len(series)} unveiled so far{f" ({', '.join(s['city'] for s in unveiled_not_installed)} is still waiting for a permanent public site)" if unveiled_not_installed else ''}. Last updated {BUILD_DATE}.</p>
    <h2>Nodes unveiled</h2>
    <div class="tbl"><table>
      <thead><tr><th>#</th><th>City</th><th>Unveiled</th><th>Status</th><th>Sources</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <h2>Confirmed upcoming</h2>
    <div class="tbl"><table>
      <thead><tr><th>City</th><th>Status</th><th>Details</th></tr></thead>
      <tbody>{up}</tbody>
    </table></div>
    <h2>About the count</h2>
    <p class="note">Bitcoin Austria’s 21 Nodes page lists six nodes: New York, El Zonte, Lugano, Vienna, Hanoi and Tokyo <a href="https://bitcoin-austria.at/satoshi-statue/" target="_blank" rel="noopener noreferrer">[source]</a>. Miami (unveiled November 2025 as the series’ fifth statue <a href="https://en.cryptonomist.ch/2025/11/12/satoshi-statue-miami/" target="_blank" rel="noopener noreferrer">[source]</a>) and Hong Kong (a Valentina Picozzi statue unveiled in April 2026, described as the next of the same limited edition after Switzerland, El Zonte, Tokyo, Hanoi, Miami and the NYSE <a href="https://www.microbit.ai/en/news/press-releases/microbit-hashkey-group-hong-kong-unveils-its-first-satoshi-nakamoto-statue-at-web3-festival/" target="_blank" rel="noopener noreferrer">[source]</a>) are included from press reports. We count a node as installed once it stands at a public site, so Miami is not counted yet. Sources disagree on the numbering of the early statues. Budapest (2021), Fornelli and the other monuments on the map are separate works and not part of 21 Nodes.</p>
    <p class="note" style="font-size:.85rem;color:#8b949e;margin-top:10px">Know of a new node? <a href="https://github.com/{REPO}/issues/new?title=New%2021%20Nodes%20statue" target="_blank" rel="noopener noreferrer">Tell us</a> with a source link.</p>
    {signup_html(data, 'nodes')}
    {footer(data, ' · <a href="/sitemap.xml">Sitemap</a>')}
  </main>
'''
    return out + TAIL


# 'About the cards' link (Noah 2026-11-01 7:43 AM ET): a subtle outlined pill so it is easier to spot, on every page that links
# to /proof-of-walk/cards/ (home passport, /proof-of-walk/, fellow-travelers grid, /v/, card share pages).
CARDS_LINK_CSS = ('a.cards-link,a.cards-link:visited{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:6px 14px;margin:4px 0;'
                  'border:1px solid rgba(247,147,26,.55);border-radius:999px;background:rgba(247,147,26,.07);color:#f7931a;'
                  'font-weight:600;font-size:.86rem;line-height:1.2;text-decoration:none;white-space:nowrap}'
                  'a.cards-link:hover,a.cards-link:focus-visible{border-color:#f7931a;background:rgba(247,147,26,.15);color:#f7931a;text-decoration:none}'
                  '.cg-more{text-align:center;margin:10px 0 0}') + (
    # "Link your X" (PREVIEW, Noah 2026-11-01 11:04 AM ET via Matt): verified-handle check, "unverified" tag, Link box.
    # Badge (Noah 2026-11-01 11:36 AM ET, "Just Verified with a checkmark"): a plain blue ✓ character, never X's badge shape.
    # Tap or hover shows what it means (<details> popover, no JS needed, works on iPhone).
    '.xv{color:#1d9bf0;font-weight:900;margin-left:4px;cursor:pointer;list-style:none;display:inline}'
    '.xv::-webkit-details-marker{display:none}.xv::marker{content:""}'
    '.xvd{display:inline;position:relative}'
    '.xvd .xtip{position:absolute;z-index:20;left:-40px;top:1.6em;width:230px;background:#161b22;border:1px solid #1d9bf0;border-radius:8px;padding:8px 10px;font-size:.8rem;font-weight:400;line-height:1.35;color:#e6edf3;box-shadow:0 6px 18px rgba(0,0,0,.5);white-space:normal;text-align:left}'
    '.xvd .xtip a{color:#58a6ff}'
    '.xu{display:inline-block;margin-left:6px;font-size:.68rem;font-weight:600;color:#8b949e;border:1px dashed #484f58;border-radius:999px;padding:0 7px;vertical-align:middle;white-space:nowrap}'
    '.xlink{background:#0d1117;border:1px solid #30363d;border-left:3px solid #1d9bf0;border-radius:10px;padding:12px 14px;margin:12px 0;font-size:.92rem;scroll-margin-top:12px}'
    '.xlink.on{border-left-color:#3fb950}.xlink p{margin:4px 0 8px}'
    '.x-btn{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:8px 18px;border-radius:999px;border:0;background:#e7e9ea;color:#0d1117;font-weight:700;font-size:.95rem;font-family:inherit;cursor:pointer}'
    '.x-note{background:#1f1a0d;border:1px solid #6e5a1e;border-radius:8px;padding:8px 10px;margin:8px 0;font-size:.86rem;color:#f2cc60}'
    '.x-note strong{color:#ffdf80}'
)


LB_CSS = CARDS_LINK_CSS + (
    '.lb-me{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:10px;padding:12px 14px;margin:14px 0;font-size:.92rem}'
    '.lb-list{list-style:none;border:1px solid #30363d;border-radius:10px;background:#161b22;overflow:hidden}'
    '.lb-list li{display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid #30363d;min-height:52px}'
    '.lb-list li:last-child{border-bottom:none}'
    '.lb-list li.me{background:#1f2a1a}'
    '.lb-rank{flex:0 0 2.2em;font-weight:800;color:#f7931a;font-size:1.05rem;text-align:center}'
    '.lb-who{flex:1 1 auto;min-width:0;display:flex;flex-direction:column}'
    '.lb-name{font-weight:700;overflow-wrap:anywhere}'
    '.lb-name a{color:#e6edf3}'
    '.lb-meta{font-size:.78rem;color:#8b949e;font-weight:400}'
    '.lb-stamps{flex:0 0 auto;text-align:right;font-weight:800;font-size:1.15rem}'
    '.lb-stamps small{display:block;font-size:.7rem;font-weight:400;color:#8b949e}'
    '.lb-feed{list-style:none;font-size:.88rem}'
    '.lb-feed li{padding:8px 0;border-bottom:1px solid #21262d}'
    '.lb-feed a{color:#f7931a}'
    '.lb-feed time{color:#8b949e;font-size:.78rem;margin-left:4px}'
    '.lb-empty{color:#8b949e;font-size:.9rem;padding:12px}'
    '.lb-nick{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}'
    '.lb-nick input{flex:1 1 160px;min-width:0;min-height:44px;padding:10px 12px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:16px;font-family:inherit}'
    '.lb-nick button{min-height:44px;padding:10px 16px;border-radius:8px;border:none;background:#f7931a;color:#0d1117;font-weight:700;font-size:.92rem;cursor:pointer;font-family:inherit}'
    '.lb-msg{font-size:.82rem;color:#f0883e;margin-top:6px;min-height:1em}'
    # Proof of Walk rank pill (same look as the home passport pill .pp-rank, sized for a list row)
    '.lb-pill{display:inline-block;margin-left:6px;font-size:.72rem;font-weight:600;color:#c9d1d9;border:1px solid #30363d;border-radius:999px;padding:1px 8px;vertical-align:middle;white-space:nowrap;text-decoration:none}'
    '.lb-pill strong{color:#f7931a;font-weight:800}'
    '.lb-pill.gen{background:#1f1a0d;border-color:#6e5a1e;color:#f2cc60}.lb-pill.gen strong{color:#ffdf80}'
    'a.lb-pill:hover{border-color:#f7931a}'
    # Top card tier pill (Noah 2026-11-01 8:00 AM ET via Matt; replaces the green "verified" tag): the walker's highest
    # card tier, same names and foil colors as the tier chips on /proof-of-walk/cards/ (POW_CARDS_CSS .t-*).
    '.lb-tier{display:inline-block;margin-left:6px;font-size:.68rem;font-weight:700;color:#0d1117;border-radius:999px;padding:1px 7px;vertical-align:middle;white-space:nowrap;text-decoration:none;background:var(--f)}'
    '.lb-tier.t-common{--f:linear-gradient(135deg,#8a5a2b,#e8b07a 45%,#7a4a1f)}'
    '.lb-tier.t-uncommon{--f:linear-gradient(135deg,#1f6f8b,#7fe3f0 40%,#2a9d8f 70%,#9be7c4)}'
    '.lb-tier.t-rare{--f:linear-gradient(135deg,#ff6b6b,#ffd93d,#6bff95,#4dd2ff)}'
    '.lb-tier.t-ultra{--f:linear-gradient(135deg,#ff4d4d,#ffb84d,#f9ff4d,#4dff88,#4dc3ff,#a64dff,#ff4dd2)}'
    '.lb-tier.t-genesis{--f:conic-gradient(from 0deg,#ff4d4d,#ffb84d,#f9ff4d,#4dff88,#4dc3ff,#a64dff,#ff4dd2,#ff4d4d)}'
    '.lb-name a.lb-tier,.lb-me a.lb-tier{color:#0d1117}a.lb-tier:hover{outline:1px solid #f7931a}'
)

LB_JS = r"""<script>
(function () {
  var A = window.SS_API, DEV = 'satoshiDevice.v1', NICK = 'satoshiNick.v1';
  var esc = function (t) { return String(t).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  var get = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var set = function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} };
  var dev = get(DEV), meId = null;
  function ago(iso) {
    var s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
    if (s < 90) return 'just now'; if (s < 5400) return Math.round(s / 60) + ' min ago';
    if (s < 129600) return Math.round(s / 3600) + ' h ago';
    return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }
  // "Link your X" (PREVIEW): e.x_linked = handle proven with X sign-in (link + blue check); e.name_unverified = an older
  // typed "@" nickname (plain text + "unverified" tag, no link). Everyone else: the nickname as before.
  var XV = '<details class="xvd"><summary class="xv" title="Signed in with this X account. Not X’s verification badge." aria-label="Verified">✓</summary><span class="xtip" role="note"><strong>Verified:</strong> Signed in with this X account. Not X’s verification badge. <a href="#x-disclaimer">More</a></span></details>';   // blue ✓ Verified with its tap/hover note
  function nameHtml(e) {
    var n = esc(e.name);
    if (e.x_linked && /^@[A-Za-z0-9_]{1,15}$/.test(e.name)) return '<a href="https://x.com/' + e.name.slice(1) + '" target="_blank" rel="noopener noreferrer nofollow">' + n + '</a>' + XV;
    if (e.name_unverified) return n + '<span class="xu" title="Typed name, not checked with X">unverified</span>';
    return n;
  }
  // Top card tier pill from the Worker (entry.top_tier; null = no cards = no pill). Same classes as POW_CARD_CLASS.
  var TIER_CLASS = { 'Common': 't-common', 'Uncommon': 't-uncommon', 'Rare': 't-rare', 'Ultra rare': 't-ultra', 'Legendary': 't-genesis' };
  function tierPill(t) {
    if (!t || !TIER_CLASS[t]) return '';
    return '<a class="lb-tier ' + TIER_CLASS[t] + '" href="/proof-of-walk/cards/" title="Top card collected: ' + esc(t) + '">' + esc(t) + '</a>';
  }
  // Proof of Walk rank pill from the Worker (entry.pow; null = no GPS stamps = no pill).
  function pill(p) {
    if (!p || !p.label) return '';
    if (p.order) return '<a class="lb-pill gen" href="/proof-of-walk/fellow-travelers/" title="Proof of Walk: The Grand High Order of Fellow Travelers">🏛️ <strong>Grand High Order</strong></a>';
    return p.genesis
      ? '<a class="lb-pill gen" href="/proof-of-walk/" title="Proof of Walk: Genesis Block">🧱 <strong>Genesis Block</strong></a>'
      : '<a class="lb-pill" href="/proof-of-walk/" title="Proof of Walk: Confirmed">👣 <strong>' + (p.progress == null ? esc(p.label) : p.progress + ' of ' + (p.genesis_at || 3) + ' cards to Genesis') + '</strong></a>';
  }
  function stampsMeta(e) {
    return e.legacy ? '' : 'all GPS-checked';
  }
  function board() {
    return fetch(A + '/api/leaderboard?limit=100').then(function (r) { return r.json(); }).then(function (j) {
      var el = document.getElementById('lb-list');
      document.getElementById('lb-total').textContent = j.total_people ? (j.total_people === 1 ? '1 person' : j.total_people + ' people') + ' so far.' : '';
      if (!j.entries.length) { el.innerHTML = '<li class="lb-empty">No check-ins yet. Visit a statue and be the first!</li>'; return; }
      el.innerHTML = j.entries.map(function (e) {
        return '<li' + (e.id === meId ? ' class="me"' : '') + '><span class="lb-rank">' + e.rank + '</span><span class="lb-who"><span class="lb-name">' + nameHtml(e) + pill(e.pow) + tierPill(e.top_tier) +
          (e.id === meId ? ' <span class="lb-meta">(you)</span>' : '') + '</span><span class="lb-meta">' + stampsMeta(e) + '</span></span><span class="lb-stamps">' + e.gps +
          '<small>card' + (e.gps === 1 ? '' : 's') + ' of ' + j.statues + '</small></span></li>';
      }).join('');
    }).catch(function () { document.getElementById('lb-list').innerHTML = '<li class="lb-empty">The leaderboard could not be loaded. Please try again later.</li>'; });
  }
  function feed() {
    return fetch(A + '/api/recent?limit=20').then(function (r) { return r.json(); }).then(function (j) {
      var el = document.getElementById('lb-feed');
      el.innerHTML = j.items.length ? j.items.map(function (i) {
        return '<li><span class="lb-name">' + nameHtml(i) + '</span> checked in at ' + (i.page ? '<a href="/' + i.page + '/">' + esc(i.statue) + '</a>' : esc(i.statue)) +
          ' <time datetime="' + esc(i.at) + '">' + ago(i.at) + '</time></li>';
      }).join('') : '<li class="lb-empty">No check-ins yet.</li>';
    }).catch(function () {});
  }
  function me() {
    var box = document.getElementById('lb-me');
    if (!dev) { box.innerHTML = 'Check in at a statue from the <a href="/">map</a> to join. Cards are only collected within 150 m of the statue.'; return Promise.resolve(); }
    return fetch(A + '/api/me', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: dev }) })
      .then(function (r) { return r.json(); }).then(function (j) {
        if (!j.ok) return; var m = j.me; meId = m.id;
        box.innerHTML = (m.rank ? 'You are <strong>#' + m.rank + '</strong> with <strong>' + m.gps + '</strong> GPS-verified card' + (m.gps === 1 ? '' : 's') +
          pill(m.pow) + tierPill(m.top_tier) + '. ' + (m.pow && m.pow.genesis && !m.pow.order ? 'Collect 1 more card to join the Grand High Order. ' : '') : 'No cards on the leaderboard yet. ') +
          'Your name: <strong>' + nameHtml(m) + '</strong>' +
          (m.x ? '<p class="lb-meta" style="margin-top:6px">Linked to X. Manage it on <a href="/proof-of-walk/#xlink">your passport</a>.</p>'
            : (m.name_released ? '<p class="x-note">Your old name <strong>' + esc(m.name_released) + '</strong> now belongs to the owner of that X account, who linked it. Pick a new nickname, or link your X.</p>' : '') +
              (m.name_unverified ? '<p class="x-note">Your name isn’t checked with X, so it shows as “unverified”. <a href="/proof-of-walk/#xlink">Link your X</a> to show it with a check.</p>' : '') +
              '<form class="lb-nick" id="lb-nick"><input name="nick" maxlength="20" aria-label="Nickname" placeholder="Nickname" value="' + esc(m.nickname || '') + '"><button type="submit">Save name</button></form><div class="lb-msg" id="lb-msg" aria-live="polite"></div>' +
              '<p class="lb-meta" style="margin-top:6px">Want your @handle here with a blue ✓ Verified? <a href="/proof-of-walk/#xlink">Link your X</a> (optional).</p>');
        if (!document.getElementById('lb-nick')) return;
        document.getElementById('lb-nick').addEventListener('submit', function (ev) {
          ev.preventDefault();
          var v = this.nick.value, msg = document.getElementById('lb-msg');
          fetch(A + '/api/nickname', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: dev, nickname: v }) })
            .then(function (r) { return r.json(); }).then(function (k) {
              if (k.ok) { set(NICK, k.nickname || ''); me().then(board).then(function () { var mm = document.getElementById('lb-msg'); if (mm) { mm.style.color = '#3fb950'; mm.textContent = 'Saved.'; } }); feed(); }
              else { msg.style.color = ''; msg.textContent = k.message || 'Could not save that name.'; }
            }).catch(function () { msg.textContent = 'Could not reach the leaderboard.'; });
        });
      }).catch(function () {});
  }
  if (!A) return;
  me().then(board); feed();
})();
</script>"""


def leaderboard_page(data):
    n = sum(1 for s in data['statues'] if s['status'] in CHECKABLE)
    title = 'Satoshi Passport Leaderboard – Who Has Visited the Most Satoshi Statues?'
    desc = (f'Leaderboard of visitors who checked in at Satoshi Nakamoto statues with the Satoshi Passport: '
            f'GPS-checked cards from {n} statues, plus recent check-ins.')
    canonical = SITE + '/leaderboard/'
    lds = ld(breadcrumb_ld([('Map', SITE + '/'), ('Leaderboard', canonical)]))
    out = head(title, desc, canonical, OG_IMAGE, 1200, 630, 'Satoshi statues world map', lds)
    out = out.replace('</style>', LB_CSS + '</style>', 1)
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › Leaderboard</div>
    <h1>🏆 Satoshi Passport Leaderboard</h1>
    <p class="sub">Who has collected the most cards from the {n} installed Satoshi statues? <span id="lb-total"></span></p>{pow_lb_link(data) if POW_ON else ''}
    <div class="lb-me" id="lb-me" aria-live="polite">Loading…</div>
    <noscript><p class="note">The leaderboard needs JavaScript.</p></noscript>
    <h2>Top visitors</h2>
    <ol class="lb-list" id="lb-list"><li class="lb-empty">Loading…</li></ol>
    <h2>Recent check-ins</h2>
    <ul class="lb-feed" id="lb-feed"><li class="lb-empty">Loading…</li></ul>
    <h2>How it works</h2>
    <p class="note">Open a statue on the <a href="/">map</a> and tap <strong>Check in here</strong> when you are within 150 m. The server checks the distance and records your card; your location itself is not stored. Each device can collect each statue’s card once, up to 5 new cards in 24 hours. People are ranked by GPS-verified cards; on a tie, whoever got there first ranks higher.</p>
    <p class="note" style="margin-top:8px">GPS can be faked, so treat this as a friendly game.</p>
    <p class="note" style="margin-top:8px;font-size:.85rem;color:#8b949e">What we store and how to delete it: <a href="/privacy/">Privacy</a>.</p>
    {footer(data)}
  </main>
"""
    return out + LB_JS + '\n' + TAIL


# ---------- Proof of Walk (passport ranks) ----------
# statues.json config.proof_of_walk = {"enabled": true, "preview": false, "genesis_set": [the original 10 slugs],
# "genesis_required": 3, "order_extra": 1, "order_keep": true}. Pages: /proof-of-walk/ (pitch, your rank, 3 ranks,
# leaderboard) and /proof-of-walk/fellow-travelers/ (the rolls). Data comes from the Worker's /api/pow/* (POW_ENABLED);
# `build.py --worker` copies the rank config into the Worker's src/statues.gen.js, so both sides always agree.
# Three ranks (Noah, 2026-10-30 12:35 ET), mirroring the Worker's src/pow.js:
#   Confirmed = first GPS-verified stamp · Genesis Block = any 3 of the original 10 · The Grand High Order of Fellow
#   Travelers = Genesis + 1 more stamp at any statue (4+ statues), kept for good; members ranked by total statues
#   stamped, ties to whoever got there first. Progress: "N of 3 to Genesis".
GENESIS_TITLE = 'Genesis Block'
ORDER_NAME = 'The Grand High Order of Fellow Travelers'


SUPPORT_EMAIL = 'support@satoshistatues.com'  # Zoho Mail support mailbox


def pow_cfg(data):
    c = data['config'].get('proof_of_walk') or {}
    return c if c.get('enabled') else None


def pow_genesis_set(data):
    # The fixed original 10.
    c = pow_cfg(data) or {}
    return list(c.get('genesis_set') or [])


def pow_genesis_required(data):
    return int((pow_cfg(data) or {}).get('genesis_required') or 3)


def pow_order_extra(data):
    return int((pow_cfg(data) or {}).get('order_extra') or 1)


def pow_order_keep(data):
    return (pow_cfg(data) or {}).get('order_keep', True) is not False


def pow_names(slugs, data):
    names = [x['city'] if x['label'].startswith('Satoshi Statue') else x['label'] for x in data['statues'] if x['slug'] in slugs]
    return ', '.join(names[:-1]) + ' and ' + names[-1] if len(names) > 1 else ''.join(names)


def pow_genesis_rule(data):
    return f'any {pow_genesis_required(data)} of the original 10 statues: {pow_names(pow_genesis_set(data), data)}'


def pow_order_rule(data):
    x = pow_order_extra(data)
    return f'the Genesis Block plus {x} more statue{"" if x == 1 else "s"}, anywhere on the map ({pow_genesis_required(data) + x} or more in all)'


def pow_keep_text(data):
    return 'Once earned, it’s yours for good.' if pow_order_keep(data) else ''


def pow_lb_link(data):
    return (f'\n    <p class="note">👣 Pills show each walker’s Proof of Walk rank (GPS-verified cards only): “N of {pow_genesis_required(data)} cards to Genesis”, then '
            f'🧱 Genesis Block ({pow_genesis_required(data)} of the original 10), then 🏛️ Grand High Order (Genesis + {pow_order_extra(data)} more). '
            '<a href="/proof-of-walk/">How ranks work →</a></p>'
            '\n    <p class="note">✨ The colored pill shows the rarest city card each walker has collected, from Common up to Legendary. '
            '<a class="cards-link" href="/proof-of-walk/cards/">About the cards →</a></p>')


def pow_head(data, title, desc, canonical, lds):
    out = head(title, desc, canonical, OG_IMAGE, 1200, 630, 'Satoshi statues world map', lds)
    if pow_cfg(data).get('preview'):
        out = out.replace('<meta name="robots" content="index, follow" />', '<meta name="robots" content="noindex, nofollow" />', 1)
    return out.replace('</style>', LB_CSS + SHARE_CSS + POW_CSS + '</style>', 1)




# Passport card grid (passport-cards preview): one card per counted statue, shared by the home passport modal and
# /proof-of-walk/. Collected = face-up art thumbnail (img/cards/art/thumb/, tools/make_card_thumbs.py); not yet = dimmed + 🔒.
CARD_GRID_CSS = CARDS_LINK_CSS + (
    '.cg-line{margin:0 0 10px;font-size:.92rem;color:#e6edf3;text-align:center}.cg-line strong{color:#f7931a}'
    '.cg-grid{list-style:none;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0;padding:0}'
    '@media(min-width:560px){.cg-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}'
    '.cg-tile{position:relative;display:block;width:100%;aspect-ratio:5/7;padding:0;border-radius:10px;overflow:hidden;cursor:pointer;font-family:inherit;'
    'background:#0d1117;border:2px solid #30363d;color:#e6edf3;text-align:center}'
    '.cg-tile:active{transform:scale(.97)}'
    '.cg-art{position:absolute;inset:0;background-size:cover;background-position:center bottom}'
    '.cg-tile.got{border-color:#f2a541;box-shadow:0 4px 14px rgba(0,0,0,.45),0 0 0 1px rgba(247,147,26,.35)}'
    '.cg-tile.locked{border-style:dashed;border-color:#3d444d}'
    '.cg-tile.locked .cg-art{filter:grayscale(1) brightness(.32) blur(1.5px)}'
    '.cg-tile.soon{border-color:#1f3a5f}.cg-tile.soon .cg-art{filter:grayscale(.6) brightness(.4)}'
    '.cg-cap{position:absolute;left:0;right:0;bottom:0;padding:16px 4px 6px;background:linear-gradient(rgba(10,12,16,0),rgba(10,12,16,.92) 45%)}'
    '.cg-name{display:block;font-size:.8rem;font-weight:800;line-height:1.15;overflow-wrap:anywhere}'
    '.cg-date{display:block;font-size:.66rem;color:#f2cc60;font-weight:600;margin-top:2px}'
    '.cg-tile.locked .cg-name{color:#8b949e}.cg-tile.locked .cg-date,.cg-tile.soon .cg-date{color:#6e7681}'
    '.cg-lock{position:absolute;top:34%;left:0;right:0;font-size:1.5rem;opacity:.8}'
    '.cg-badge{position:absolute;top:5px;right:5px;min-width:26px;height:26px;border-radius:13px;background:rgba(13,17,23,.85);border:1px solid #f2a541;font-size:.8rem;line-height:24px;padding:0 4px}'
    '.cg-tile.just{animation:cgIn .6s cubic-bezier(.2,1.6,.4,1)}@keyframes cgIn{0%{transform:scale(1.25) rotate(-6deg);opacity:0}100%{transform:none;opacity:1}}'
    '.cg-view{margin:14px 0 4px;padding:10px 0 0;border-top:1px solid #21262d}.cg-view[hidden]{display:none}'
    '.cg-view-bar{display:flex;justify-content:space-between;gap:8px;max-width:420px;margin:0 auto 4px}'
    '.cg-view-bar button,.cg-view-bar a{min-height:40px;padding:6px 12px;border-radius:999px;border:1px solid #30363d;background:#21262d;color:#e6edf3;font:600 .84rem inherit;font-family:inherit;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}'
    '.cg-hint{font-size:.78rem;color:#8b949e;text-align:center;margin:8px 0 0}'
    # tier finish on the thumbnail (same tiers as pow-card.js): number + tier chip, border by tier
    '.cg-no{position:absolute;top:5px;left:5px;height:22px;border-radius:11px;background:rgba(13,17,23,.85);border:1px solid #f2a541;font:700 .66rem/20px ui-monospace,Menlo,monospace;padding:0 6px;color:#f5f1e6}'
    '.cg-tier{display:block;font-size:.6rem;font-weight:700;letter-spacing:.02em;color:#c9d1d9;margin-top:1px}'
    '.cg-tile.t1{border:3px solid #b98a3e}'
    '.cg-tile.t2{border:3px solid transparent;background:linear-gradient(#0d1117,#0d1117) padding-box,linear-gradient(135deg,#2f6b55,#9ff0c8 45%,#2f6b55 70%,#9fd8f0) border-box}'
    '.cg-tile.t3,.cg-tile.t4,.cg-tile.t5{border:3px solid transparent;background:linear-gradient(#0d1117,#0d1117) padding-box,linear-gradient(135deg,#ff4d4d,#ffb84d,#f9ff4d,#4dff88,#4dc3ff,#a64dff,#ff4dd2) border-box}'
    '.cg-tile.t3 .cg-art::after,.cg-tile.t4 .cg-art::after,.cg-tile.t5 .cg-art::after{content:"";position:absolute;inset:0;mix-blend-mode:screen;opacity:.22;background:linear-gradient(115deg,transparent 30%,#ff4dd2 42%,#4dc3ff 50%,#f9ff4d 58%,transparent 70%)}'
    '.cg-tile.t5{box-shadow:0 0 0 2px #e8c35a,0 4px 16px rgba(232,195,90,.45)}'
)

POW_CSS = CARD_GRID_CSS + (
    '.pow-card{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:10px;padding:14px;margin:14px 0}'
    '.pow-rank{font-size:1.35rem;font-weight:800;color:#f7931a;margin:2px 0 4px}'
    '.pow-sub{font-size:.88rem;color:#8b949e;margin:0 0 8px}'
    '.pow-pips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}'
    '.pow-pip{width:26px;height:26px;border-radius:50%;border:2px solid #30363d;background:#0d1117;display:inline-flex;align-items:center;justify-content:center;font-size:.7rem;color:#8b949e}'
    '.pow-pip.on{background:#f7931a;border-color:#f7931a;color:#0d1117;font-weight:800}'
    '.pow-code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:1.05rem;font-weight:700;letter-spacing:.04em;color:#ffdf80;background:#0d1117;border:1px dashed #6e5a1e;border-radius:8px;padding:10px 12px;margin:6px 0;word-break:break-all;user-select:all}'
    '.pow-codebox{background:#1f1a0d;border:1px solid #6e5a1e;border-radius:8px;padding:10px 12px;margin:10px 0;font-size:.86rem;color:#e6edf3}'
    '.pow-codebox button,.pow-ghost{min-height:40px;padding:8px 14px;border-radius:8px;border:1px solid #30363d;background:#21262d;color:#e6edf3;font-weight:600;font-size:.86rem;cursor:pointer;font-family:inherit}'
    '.pow-recover{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:10px 14px;margin:10px 0}'
    '.pow-recover summary{cursor:pointer;font-weight:700;color:#e6edf3;font-size:.92rem;min-height:32px;display:flex;align-items:center}'
    '.pow-recover[open] summary{margin-bottom:6px}'
    '.x-confirm{border-color:#e3b341!important;margin:0 0 14px}.x-confirm p{margin:6px 0}'
    '.pow-key{font-size:.84rem;color:#c9d1d9;margin:8px 0 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center}'
    '.pow-genesis{background:#1f1a0d;border:1px solid #6e5a1e;border-radius:8px;padding:10px 12px;margin:10px 0;color:#f2cc60;font-size:.9rem}'
    '.pow-genesis strong{color:#ffdf80}'
    '.pow-form{display:grid;gap:8px;margin-top:10px}'
    '.pow-form label{font-size:.82rem;color:#c9d1d9}'
    '.pow-form input{min-height:44px;padding:10px 12px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:16px;font-family:inherit;width:100%;box-sizing:border-box}'
    '.pow-form button{min-height:44px;padding:10px 16px;border-radius:8px;border:none;background:#f7931a;color:#0d1117;font-weight:700;font-size:.92rem;cursor:pointer;font-family:inherit;justify-self:start}'
    '.pow-fine{font-size:.78rem;color:#8b949e;margin:2px 0 0}'
    '.pow-ranks{list-style:none;padding:0;margin:6px 0}.pow-ranks li{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #30363d;font-size:.95rem}.pow-ranks li>span{font-size:1.2rem;width:1.6em;text-align:center}.pow-ranks .pow-fine{font-size:.84rem;color:#c9d1d9}'
    '.pow-badge{display:inline-block;margin-left:6px;font-size:.7rem;font-weight:800;color:#0d1117;background:#e3b341;border-radius:4px;padding:1px 6px;vertical-align:middle}'
    '.pow-preview{display:inline-block;font-size:.72rem;font-weight:700;color:#58a6ff;border:1px solid #1f3a5f;border-radius:4px;padding:1px 6px;margin-left:6px;vertical-align:middle}'
    '.pow-roll li .lb-rank{color:#e3b341}'
    '.pow-cards-h{font-size:1rem;color:#e6edf3;margin:14px 0 6px;text-align:center}'
    '.pow-tabs{display:flex;flex-wrap:wrap;justify-content:center;gap:6px;margin:0 0 6px}'
    '.pow-tabs button{min-height:40px;padding:6px 12px;border-radius:999px;border:1px solid #30363d;background:#21262d;color:#e6edf3;font:600 .84rem inherit;font-family:inherit;cursor:pointer}'
    '.pow-tabs button[aria-selected=true]{background:#f7931a;color:#0d1117;border-color:#f7931a}'
)


def pow_ranks_html(data):
    rows = [('👣', 'Confirmed', 'Your first GPS-verified card.'),
            ('🧱', GENESIS_TITLE, f'Collect cards from {pow_genesis_rule(data)}.'),
            ('🏛️', ORDER_NAME, f'{pow_order_rule(data)[0].upper() + pow_order_rule(data)[1:]}. {pow_keep_text(data)} Members are ranked by total cards collected. <a href="/proof-of-walk/fellow-travelers/">The roll →</a>')]
    return '<ol class="pow-ranks">' + ''.join(f'<li><span>{i}</span><div><strong>{e(t)}</strong><br><span class="pow-fine">{d}</span></div></li>' for i, t, d in rows) + '</ol>'


POW_JS = r"""<script src="/share.js"></script>
<script>
(function () {
  var A = window.SS_API, DEV = 'satoshiDevice.v1', NICK = 'satoshiNick.v1', PAGE = document.body.getAttribute('data-pow') || 'main';
  var URL_POW = location.origin + '/proof-of-walk/';
  var SHARE_SLUG = { confirmed: 'confirmed', genesis: 'genesis-block', order: 'grand-high-order' };
  // me.card = this walker's prism card for the current rank ({ rank: slug, n: 1-21 }, from the Worker); else the base card.
  var cardOf = function (me) { var k = me && me.rank && SHARE_SLUG[me.rank.key], c = me && me.card, n = c ? Number(c.n) : 0;
    return k && c && c.rank === k && n >= 1 && n <= 21 && n === Math.floor(n) ? { slug: k, nn: (n < 10 ? '0' : '') + n, tier: (String(c.tier || '') === '1 of 121' ? 'Legendary' : String(c.tier || '')) } : null; };
  var shareUrl = function (me) { var k = me && me.rank && SHARE_SLUG[me.rank.key], c = cardOf(me);
    return c ? URL_POW + 'share/' + c.slug + '/' + c.nn + '/' : k ? URL_POW + 'share/' + k + '/' : URL_POW; };
  // me.cards[rank] with a verify code + earning stamp = the combined card (design 2); else the older card above.
  var RANK_UI = { confirmed: '👣 Confirmed', genesis: '🧱 Genesis Block', order: '🏛️ Grand High Order' };
  var comboCards = function (me) {
    var out = ['confirmed', 'genesis', 'order'].filter(function (k) { var c = me && me.cards && me.cards[k]; return c && c.code && c.earned && c.earned.slug; })
      .map(function (k) { var c = me.cards[k]; return { rank: k, slug: c.earned.slug, n: Number(c.n), at: c.earned.at, code: c.code }; });
    var cur = me && me.rank && me.rank.key; out.current = out.some(function (c) { return c.rank === cur; }) ? cur : (out[0] && out[0].rank);
    return out;
  };
  var withPowCard = function (fn) {
    if (window.PowCard) return fn(window.PowCard);
    var s = document.createElement('script'); s.src = window.SS_POWCARD || '/pow-card.js'; s.onload = function () { if (window.PowCard) fn(window.PowCard); }; document.head.appendChild(s);
  };
  var esc = function (t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  // Top card tier pill (same as LB_JS tierPill; Noah 2026-11-01 8:18 AM ET via Matt): m.top_tier from /api/pow/order; null = no cards = no pill.
  var TIER_CLASS = { 'Common': 't-common', 'Uncommon': 't-uncommon', 'Rare': 't-rare', 'Ultra rare': 't-ultra', 'Legendary': 't-genesis' };
  function tierPill(t) {
    if (!t || !TIER_CLASS[t]) return '';
    return '<a class="lb-tier ' + TIER_CLASS[t] + '" href="/proof-of-walk/cards/" title="Top card collected: ' + esc(t) + '">' + esc(t) + '</a>';
  }
  // "Link your X" (PREVIEW): verified check / "unverified" tag on names (same as LB_JS nameHtml).
  var XV = '<details class="xvd"><summary class="xv" title="Signed in with this X account. Not X’s verification badge." aria-label="Verified">✓</summary><span class="xtip" role="note"><strong>Verified:</strong> Signed in with this X account. Not X’s verification badge. <a href="#x-disclaimer">More</a></span></details>';   // blue ✓ Verified with its tap/hover note
  function nameHtml(e) {
    var n = esc(e.name);
    if (e.x_linked && /^@[A-Za-z0-9_]{1,15}$/.test(e.name)) return '<a href="https://x.com/' + e.name.slice(1) + '" target="_blank" rel="noopener noreferrer nofollow" style="color:inherit">' + n + '</a>' + XV;
    if (e.name_unverified) return n + '<span class="xu" title="Typed name, not checked with X">unverified</span>';
    return n;
  }
  var get = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var set = function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} };
  var $ = function (id) { return document.getElementById(id); };
  var post = function (p, b) { return fetch(A + p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(function (r) { return r.json(); }); };
  var getj = function (p) { return fetch(A + p).then(function (r) { return r.json(); }); };
  var MAP = JSON.parse(document.body.getAttribute('data-pow-map') || '[]');
  var off = function (el) { if (el) el.innerHTML = '<p class="pow-sub">Proof of Walk isn’t switched on yet.</p>'; };
  if (!A || !window.fetch) { off($('pow-me')); off($('pow-list')); off($('pow-roll')); return; }
  function pips(me) {
    var have = {}; (me.slugs || []).forEach(function (s) { have[s] = 1; });
    var set = me.genesis_set, list = set ? MAP.filter(function (m) { return set.indexOf(m.slug) >= 0; }) : MAP;
    return '<div class="pow-pips" aria-label="' + (me.progress_text || '') + '">' + list.map(function (m) {
      return '<span class="' + (have[m.slug] ? 'pow-pip on' : 'pow-pip') + '" title="' + esc(m.name) + (have[m.slug] ? ' ✓' : '') + '">' + (have[m.slug] ? '✓' : '') + '</span>';
    }).join('') + '</div>';
  }
  // Passport card grid: one card per counted statue. Collected (a GPS-verified check-in on the Worker) = face-up.
  // Every check-in is a full card (me.stamp_cards: rank as of that check-in, quote, verify code); the check-in that
  // earned a rank is that rank's card. Without stamp_cards (table not there yet) only the rank cards open.
  var RANK_EMOJI = { confirmed: '👣', genesis: '🧱', order: '🏛️' };
  var cardFor = function (me, slug) {
    var sc = me && me.stamp_cards && me.stamp_cards[slug];
    if (sc && sc.code) return { rank: sc.rank, slug: slug, n: Number(sc.n), at: sc.at, code: sc.code, earns: !!sc.earns };
    var rk = comboCards(me).filter(function (c) { return c.slug === slug; })[0];
    if (rk) return rk;
    var st = (me && me.stamped || []).filter(function (x) { return x.slug === slug; })[0];
    return st ? { pending: true, slug: slug, at: st.at } : null;
  };
  var TIER = function (n) { return n === 21 ? ['Legendary', 5] : n === 20 ? ['Ultra rare', 4] : n >= 17 ? ['Rare', 3] : n >= 11 ? ['Uncommon', 2] : ['Common', 1]; };
  var fmtDay = function (iso) { try { return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }); } catch (e) { return ''; } };
  function cardsLine(me) {
    var gN = (me && me.genesis_at) || 3, n = (me && me.distinct_stamps) || 0;
    if (me && me.order) return '🗺️ <strong>Cards collected: ' + n + '</strong> · 🏛️ Grand High Order ✓';
    if (me && me.genesis) return '🗺️ <strong>Cards collected: ' + n + '</strong> · 🧱 Genesis Block ✓ · ' + (me.order_needed || 1) + ' more card' + ((me.order_needed || 1) === 1 ? '' : 's') + ' for the Grand High Order';
    var p = (me && me.genesis_progress) || 0;
    return '🗺️ <strong>Cards collected: ' + p + ' of ' + gN + ' to Genesis</strong>' + (n > p ? ' · ' + n + ' cards in all' : '') + '<br><span class="pow-fine">Any ' + gN + ' of the original 10 statues</span>';
  }
  function gridHtml(me) {
    return '<ul class="cg-grid" aria-label="Your Satoshi Passport cards">' + MAP.map(function (m) {
      var c = me ? cardFor(me, m.slug) : null, page = m.page || m.slug, nm = esc(m.short || m.name);
      var art = '<span class="cg-art" style="background-image:url(/img/cards/art/thumb/' + esc(page) + '.jpg)"></span>';
      if (!c) return '<li><button class="cg-tile locked" type="button" data-cg-locked="' + esc(page) + '" aria-label="' + esc(m.name) + ': not collected yet">' + art +
        '<span class="cg-lock" aria-hidden="true">🔒</span><span class="cg-cap"><span class="cg-name">' + nm + '</span><span class="cg-date">Not yet</span></span></button></li>';
      var n = Number(c.n) || 0, t = n ? TIER(n) : null, nn = n ? (n < 10 ? '0' : '') + n : '';
      return '<li><button class="cg-tile got' + (t ? ' t' + t[1] : '') + '" type="button" data-cg="' + esc(m.slug) + '" aria-label="' + esc(m.name) + ': card ' + (n ? nn + ' of 21, ' + t[0] + ', ' : '') + 'collected ' + esc(fmtDay(c.at)) + (c.rank ? ', ' + esc(RANK_UI[c.rank].replace(/^\S+\s/, '')) : '') + '. Tap to open">' + art +
        (n ? '<span class="cg-no" aria-hidden="true">' + nn + '/21</span>' : '') + (c.rank ? '<span class="cg-badge" aria-hidden="true">' + RANK_EMOJI[c.rank] + '</span>' : '') +
        '<span class="cg-cap"><span class="cg-name">' + nm + '</span>' + (t ? '<span class="cg-tier">' + '◆'.repeat(t[1]) + ' ' + t[0] + '</span>' : '') + '<span class="cg-date">' + esc(fmtDay(c.at)) + '</span></span></button></li>';
    }).join('') + '</ul><div id="pow-combo" class="cg-view" aria-live="polite" hidden></div>' +
      '<p class="cg-hint">Tap a card to flip it, share it or print it.</p><p class="cg-more"><a class="cards-link" href="/proof-of-walk/cards/">About the cards</a></p>';
  }
  function wireGrid(el, me) {
    el.querySelectorAll('[data-cg]').forEach(function (b) { b.addEventListener('click', function () {
      var c = cardFor(me, b.getAttribute('data-cg')), box = $('pow-combo'); if (!c || !box) return;
      box.hidden = false; box.innerHTML = '<p class="pow-sub">Loading your card…</p>';
      if (c.pending) { box.innerHTML = '<p class="pow-sub">This card is still being made. Reload the page in a moment.</p>'; return; }
      if (me && me.x && me.x.username) c.x = me.x.username;   // linked X handle on the card (Link your X)
      withPowCard(function (P) { var holder = document.createElement('div'); box.innerHTML = '<div class="cg-view-bar"><button type="button" data-cg-close>✕ Close card</button><a href="/' + esc((MAP.filter(function (m) { return m.slug === c.slug; })[0] || {}).page || '') + '/">Statue page →</a></div>'; box.appendChild(holder);
        box.querySelector('[data-cg-close]').addEventListener('click', function () { box.hidden = true; box.innerHTML = ''; b.focus(); });
        P.mount(holder, c).then(function () { box.scrollIntoView({ block: 'start', behavior: 'smooth' }); }); });
    }); });
    el.querySelectorAll('[data-cg-locked]').forEach(function (b) { b.addEventListener('click', function () { location.href = '/' + b.getAttribute('data-cg-locked') + '/'; }); });
  }
  function renderMe(me) {
    var el = $('pow-me'); if (!el) return;
    var gN = me.genesis_at || 3;
    var h = '<div class="pow-sub">Your Satoshi Passport rank' + (me.x ? ' · <strong>@' + esc(me.x.username) + '</strong>' + XV : me.nickname ? ' · <strong>' + esc(me.nickname) + '</strong>' + (me.nick_unverified ? '<span class="xu">unverified</span>' : '') : '') + '</div>' +
      (me.moved_away && !me.stamps ? '<div class="pow-rank" id="pow-moved">Your passport moved to another device</div>' +
        '<p class="pow-fine">On ' + esc(fmtDay(me.moved_away)) + ' it was moved to another phone or browser by signing in with X. To bring it back here, tap “Lost your phone?” below and sign in with the same X account. ' +
        'Or check in at a statue to start a new passport on this device.</p>'
      : '<div class="pow-rank">' + esc(me.rank.label || 'No rank yet') + '</div>');
    if (me.order) h += '<div class="pow-genesis">🏛️ <strong>The Grand High Order of Fellow Travelers</strong> · since ' + esc((me.order_since || '').slice(0, 10)) +
      '<br><span class="pow-fine">' + me.distinct_stamps + ' cards collected</span></div>';
    if (me.genesis) h += '<div class="pow-genesis">🧱 <strong>Genesis Block</strong> · mined ' + esc((me.joined_at || '').slice(0, 10)) +
      (!me.order ? '<br><span class="pow-fine">Collect ' + (me.order_needed || 1) + ' more card' + ((me.order_needed || 1) === 1 ? '' : 's') + ', at any statue on the map, to join the Grand High Order.</span>' : '') + '</div>';
    var card = cardOf(me), combo = comboCards(me);
    // passport-cards preview: the card grid replaces the Genesis pips and the per-rank "Your cards" tabs.
    h += '<h3 class="pow-cards-h">Your passport cards</h3><p class="cg-line">' + cardsLine(me) + '</p>' + gridHtml(me);
    h += xBox(me);
    h += '<form class="pow-form" id="pow-form"><label for="pow-nick">Passport nickname (shown on the leaderboard' + (me.x ? ' if you unlink X' : '') + ')</label>' +
      '<input id="pow-nick" name="nick" maxlength="20" autocomplete="nickname" placeholder="Nickname" value="' + esc(me.nickname || get(NICK) || '') + '">' +
      '<button type="submit">Save</button><div class="lb-msg" id="pow-msg" aria-live="polite"></div></form>';
    el.innerHTML = h;
    wireGrid(el, me); wireX(me); renderRecover(me);
    $('pow-form').addEventListener('submit', function (ev) {
      ev.preventDefault();
      var body = { device_id: dev, nickname: $('pow-nick').value };   // no Lightning address: the passport never stores one
      post('/api/pow/profile', body).then(function (j) {
        if (j.ok) { set(NICK, j.me.nickname || ''); renderMe(j.me); $('pow-msg').textContent = 'Saved.'; loadList(); }
        else $('pow-msg').textContent = j.message || 'Couldn’t save that.';
      }).catch(function () { $('pow-msg').textContent = 'Couldn’t reach the server.'; });
    });
  }
  var dev = get(DEV);
  // ---------- "Link your X" (PREVIEW, Noah 2026-11-01 11:04 AM ET via Matt) ----------
  // Optional. X's own sign-in page proves the account; the Worker reads only the @handle (+ X user id), never posts, and
  // keeps no X login. Coming back from X: ?xt=<one-time token> is confirmed from this device (POST /api/x/finish).
  var xNote = '', xNoteOk = true;
  // xrecover: X is the only way to move a passport. No password, no recovery code, no Lightning address.
  var XHOME = '<p class="pow-fine pow-home" id="pow-home"><strong>Your passport lives on this device. No password.</strong> ';
  function xBox(me) {
    var note = xNote ? '<div class="lb-msg" id="x-msg" aria-live="polite" style="color:' + (xNoteOk ? '#3fb950' : '#e3b341') + '">' + xNote + '</div>' : '<div class="lb-msg" id="x-msg" aria-live="polite"></div>';
    if (me.x) return '<div class="xlink on" id="xlink">✅ Verified: <strong>@' + esc(me.x.username) + '</strong>' + XV + ' <span class="pow-fine">· linked ' + esc(fmtDay(me.x.linked_at)) + '</span>' +
      '<p class="pow-fine">Your cards, card pages and the leaderboards show this handle with a blue ✓ Verified. It means you signed in with this X account; it isn’t X’s own verification badge.</p>' +
      XHOME + 'New phone? Open this page there, tap “Lost your phone?” and sign in as @' + esc(me.x.username) + '. Your passport moves over and leaves this device.</p>' +
      '<button class="pow-ghost" type="button" id="x-relink">Refresh handle</button> <button class="pow-ghost" type="button" id="x-unlink">Unlink X</button>' + note + '</div>';
    return '<div class="xlink" id="xlink">' +
      (me.name_released ? '<p class="x-note">Your old name <strong>' + esc(me.name_released) + '</strong> now belongs to the owner of that X account, who linked it, so it was removed. Pick a new nickname below, or link your X.</p>' : '') +
      (me.nick_unverified ? '<p class="x-note">Your name <strong>' + esc(me.nickname) + '</strong> isn’t checked with X, so it shows as “unverified”. Link your X to show it with a blue ✓ Verified.</p>' : '') +
      XHOME + 'Link your X to move it to a new phone.</p>' +
      '<strong>Link your X</strong> <span class="pow-fine">(optional)</span>' +
      '<p class="pow-fine">Show your @handle on your cards and the leaderboard with a blue ✓ Verified. You sign in on X, and we only read your handle. We never post or send messages, and we don’t keep your X login.</p>' +
      '<button class="x-btn" type="button" id="x-link">Link your X</button>' + note + '</div>';
  }
  var XMODE = 'satoshiXMode';
  function xStart(btn, mode, msgId) {
    var label = btn ? btn.textContent : '', msg = function (s) { if ($(msgId || 'x-msg')) $(msgId || 'x-msg').textContent = s; };
    if (btn) { btn.disabled = true; btn.textContent = 'Opening X…'; }
    try { sessionStorage.setItem(XMODE, mode || 'link'); } catch (e) {}
    post('/api/x/start', { device_id: dev }).then(function (j) {
      if (j.ok && j.url) { location.href = j.url; return; }
      if (btn) { btn.disabled = false; btn.textContent = label; }
      msg(j.message || 'Couldn’t open X. Please try again.');
    }).catch(function () { msg('Couldn’t reach the server.'); if (btn) { btn.disabled = false; btn.textContent = label; } });
  }
  function wireX(me) {
    xNote = '';
    if ($('x-link')) $('x-link').addEventListener('click', function () { xStart(this); });
    if ($('x-relink')) $('x-relink').addEventListener('click', function () { xStart(this); });
    if ($('x-unlink')) $('x-unlink').addEventListener('click', function () {
      if (!confirm('Unlink your X account? Your cards stay; the @handle and check are removed from them.')) return;
      post('/api/x/unlink', { device_id: dev }).then(function (j) { if (j.ok) { xNote = 'X unlinked. Your cards no longer show a handle.'; loadMe(); loadList(); } });
    });
  }
  // back from X: finish on this device, then clean the address bar
  var XQ = new URLSearchParams(location.search), XMSG = { cancelled: 'No problem. Nothing was linked.', error: 'X sign-in didn’t work. Please try again.', expired: 'That sign-in took too long. Please try again.' };
  function xReturn() {
    var t = XQ.get('xt'), x = XQ.get('x');
    if (!t && !x) return Promise.resolve();
    try { history.replaceState(null, '', location.pathname + '#xlink'); } catch (e) {}
    if (x && XMSG[x]) { xNote = XMSG[x]; return Promise.resolve(); }
    var mode = 'link'; try { mode = sessionStorage.getItem(XMODE) || 'link'; sessionStorage.removeItem(XMODE); } catch (e) {}
    if (!dev) return Promise.resolve();
    return xFinish({ device_id: dev, token: t, mode: mode });
  }
  // A move always asks first (the Worker returns needs_confirm and changes nothing until confirm: true).
  var xPending = null;
  function xFinish(body) {
    return post('/api/x/finish', body).then(function (j) {
      xNoteOk = !!j.ok;
      if (j.ok && j.needs_confirm) { xPending = { body: body, j: j }; xNote = ''; return; }
      xPending = null;
      if (j.ok && j.cancelled) { xNote = 'Nothing was moved. Your passport stays where it was.'; xNoteOk = true; return; }
      if (j.ok && j.restored) {
        // the passport moved here: mirror its cards into this browser's local passport (same as the home map's)
        var p = {}; try { p = JSON.parse(get('satoshiPassport.v1')) || {}; } catch (e) {}
        ((j.me && j.me.stamped) || []).forEach(function (s) { if (!p[s.slug]) p[s.slug] = { date: s.at }; });
        set('satoshiPassport.v1', JSON.stringify(p)); set('satoshiClaimed.v1', '1'); if (j.me && j.me.nickname) set(NICK, j.me.nickname);
        var n = (j.me && j.me.stamps) || 0;
        xNote = '✅ Passport restored: you now have ' + n + ' card' + (n === 1 ? '' : 's') + ' on this device. Signed in as @' + esc(j.x.username) + '. Your other device no longer has it.';
      } else xNote = j.ok ? '✅ Verified: @' + esc(j.x.username) + '.' : esc(j.message || 'Couldn’t link X. Please try again.');
    }).catch(function () { xNoteOk = false; xNote = 'Couldn’t reach the server.'; });
  }
  function cardsN(n) { return n + ' card' + (n === 1 ? '' : 's'); }
  function showConfirm() {
    var el = $('pow-me'); if (!el || !xPending) return;
    var j = xPending.j, h = '<div class="xlink x-confirm" id="x-confirm" role="alertdialog" aria-labelledby="x-confirm-h">' +
      '<p id="x-confirm-h"><strong>This moves your passport to this device. Your other device will lose it.</strong></p>' +
      '<p class="pow-fine">The passport linked to @' + esc(j.x.username) + ' has ' + cardsN(j.passport_cards) + '.</p>';
    if (j.here_cards) h += '<p class="pow-fine"><strong>This device already has ' + cardsN(j.here_cards) + ' of its own.</strong> They will be merged into the restored passport, so you keep all of them: ' +
      'after the move this device has ' + cardsN(j.after_cards) + '.' + (j.shared_cards ? ' ' + (j.shared_cards === 1 ? '1 statue is on both; for it, the restored passport’s card is kept.' : j.shared_cards + ' statues are on both; for those, the restored passport’s cards are kept.') : '') + '</p>';
    if (j.nickname_replaced) h += '<p class="pow-fine">Your passport’s nickname “' + esc(j.nickname_kept) + '” replaces “' + esc(j.nickname_replaced) + '” on this device.</p>';
    h += '<button class="x-btn" type="button" id="x-confirm-yes">Move my passport here</button> <button class="pow-ghost" type="button" id="x-confirm-no">Cancel</button>' +
      '<div class="lb-msg" id="x-confirm-msg" aria-live="polite"></div></div>';
    el.insertAdjacentHTML('afterbegin', h);
    var go = function (extra) {
      $('x-confirm-yes').disabled = $('x-confirm-no').disabled = true; $('x-confirm-msg').textContent = extra.confirm ? 'Moving…' : '';
      var b = {}; for (var k in xPending.body) b[k] = xPending.body[k]; for (var k2 in extra) b[k2] = extra[k2];
      xFinish(b).then(function () { loadMe(); loadList(); loadRoll(); });
    };
    $('x-confirm-yes').addEventListener('click', function () { go({ confirm: true }); });
    $('x-confirm-no').addEventListener('click', function () { go({ cancel: true }); });
    $('x-confirm').scrollIntoView({ block: 'start' });
  }
  // "Lost your phone?": sign in with X on this device. If that X account is linked to a passport, the whole passport
  // moves here and the old device loses it. Hidden once this device's passport is linked to X.
  function renderRecover(me) {
    var el = $('pow-recover'); if (!el) return;
    if (me && me.x) { el.innerHTML = ''; return; }
    el.innerHTML = '<details class="pow-recover" id="pow-lost"' + (location.hash === '#recover' ? ' open' : '') + '><summary>Lost your phone? Sign in with X to restore your passport</summary>' +
      '<p class="pow-fine">If you linked your X on your old phone, sign in with the same X account here. Your cards, rank and nickname move to this device, and the old device loses them. ' +
      'No password and no code. Nothing is paid.</p>' +
      '<button class="x-btn" type="button" id="x-restore">Sign in with X</button><div class="lb-msg" id="pow-rmsg" aria-live="polite"></div>' +
      '<p class="pow-fine">Never linked your X? We can’t move that passport. Trouble? Email <a href="mailto:__SUPPORT__">__SUPPORT__</a></p></details>';
    $('x-restore').addEventListener('click', function () {
      if (!dev) { dev = (crypto.randomUUID ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16)), function (b) { return b.toString(16).padStart(2, '0'); }).join('')); set(DEV, dev); }
      xStart(this, 'restore', 'pow-rmsg');
    });
  }
  function loadMe() {
    var el = $('pow-me'); if (!el) return;
    if (!dev) { renderRecover(null); if (xNote && $('pow-rmsg')) $('pow-rmsg').textContent = xNote; el.innerHTML = '<div class="pow-rank">No rank yet</div><p class="pow-sub">Check in at a statue (within 150 m) to collect your first card. Open a statue on the <a href="/">map</a> or its page and tap <strong>Check in here</strong>.</p>' +
      '<h3 class="pow-cards-h">Your passport cards</h3><p class="cg-line">' + cardsLine(null) + '</p>' + gridHtml(null); wireGrid(el, null); return; }
    post('/api/pow/me', { device_id: dev }).then(function (j) { if (j.ok) { renderMe(j.me); if (xPending) showConfirm(); else if (location.hash === '#xlink' && $('xlink')) $('xlink').scrollIntoView({ block: 'center' }); } else off(el); }).catch(function () { off(el); });
  }
  function loadList() {
    var el = $('pow-list'); if (!el) return;
    getj('/api/pow/leaderboard?limit=5').then(function (j) {
      if (!j.ok) return off(el);
      if ($('pow-total')) $('pow-total').textContent = j.total_walkers + (j.total_walkers === 1 ? ' walker' : ' walkers') + ' so far.';
      el.innerHTML = j.entries.length ? j.entries.map(function (x) {
        return '<li><span class="lb-rank">' + x.position + '</span><span class="lb-who"><span class="lb-name">' + nameHtml(x) + 
          '</span><span class="lb-meta">' + (x.order ? '🏛️ Grand High Order' : x.genesis ? '🧱 Genesis Block' : x.progress + ' of ' + (j.genesis_at || 3) + ' cards to Genesis') + '</span></span><span class="lb-stamps">' + x.stamps + '<small>card' + (x.stamps === 1 ? '' : 's') + '</small></span></li>';
      }).join('') : '<li class="lb-empty">No walkers yet. Be the first.</li>';
    }).catch(function () { off(el); });
  }
  function loadRoll() {
    var el = $('pow-roll'), ge = $('pow-genesis-roll'); if (!el) return;
    var day = function (d) { return esc(new Date(d + 'T12:00:00Z').toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })); };
    getj('/api/pow/order').then(function (j) {
      if (!j.ok) { off(el); off(ge); return; }
      el.innerHTML = j.members.length ? j.members.map(function (m) {
        return '<li><span class="lb-rank">' + m.number + '</span><span class="lb-who"><span class="lb-name">' + nameHtml(m) + tierPill(m.top_tier) + '</span><span class="lb-meta">Since ' +
          day(m.since) + '</span></span><span class="lb-stamps">' + m.stamps + '<small>card' + (m.stamps === 1 ? '' : 's') + '</small></span></li>';
      }).join('') : '<li class="lb-empty">No members yet. Mine the Genesis Block, then collect 1 more card to join.</li>';
      if (ge) ge.innerHTML = (j.genesis || []).length ? j.genesis.map(function (m) {
        return '<li><span class="lb-rank">' + m.number + '</span><span class="lb-who"><span class="lb-name">' + nameHtml(m) + tierPill(m.top_tier) + '</span><span class="lb-meta">Mined ' +
          day(m.joined) + '</span></span><span class="lb-stamps">' + m.stamps + '<small>card' + (m.stamps === 1 ? '' : 's') + '</small></span></li>';
      }).join('') : '<li class="lb-empty">No miners yet. Collect cards from any ' + (j.genesis_at || 3) + ' of the original 10 to mine the Genesis Block.</li>';
    }).catch(function () { off(el); off(ge); });
  }
  xReturn().then(loadMe); loadList(); loadRoll();
})();
</script>"""

POW_JS = POW_JS.replace('__SUPPORT__', SUPPORT_EMAIL)

def pow_map_attr(data):
    m = [{'slug': s['slug'], 'name': s['name'], 'short': pow_names([s['slug']], data), 'page': s['page']} for s in data['statues'] if s['status'] in CHECKABLE]
    return e(json.dumps(m, ensure_ascii=False))


def pow_body_tag(out, data, page):
    return out.replace('<body>', f'<body data-pow="{page}" data-pow-map="{pow_map_attr(data)}">', 1)


def pow_page(data):
    canonical = SITE + '/proof-of-walk/'
    title = 'Proof of Walk – Satoshi Passport Ranks'
    pitch = f'Walk to Satoshi statues and collect each city’s card. Collect any {pow_genesis_required(data)} of the original 10 to mine the Genesis Block.'
    desc = f'{pitch} Three ranks: Confirmed, Genesis Block and {ORDER_NAME}.'
    lds = ld(breadcrumb_ld([('Map', SITE + '/'), ('Proof of Walk', canonical)]))
    out = pow_body_tag(pow_head(data, title, desc, canonical, lds), data, 'main')
    pv = '<span class="pow-preview">Preview</span>' if pow_cfg(data).get('preview') else ''
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › Proof of Walk</div>
    <h1>👣 Proof of Walk{pv}</h1>
    <p class="sub">{e(pitch)}</p>
    <div class="pow-card" id="pow-me" aria-live="polite">Loading…</div>
    <p class="note pow-cards-link" style="font-size:.9rem">🗺️ Every statue you walk to is a card in your passport: that statue, your rank at the time, one of 21 Bitcoin quotes and a verify code.<br><a class="cards-link" href="/proof-of-walk/cards/">See the cards →</a></p>
    <div id="pow-recover"></div>
    <noscript><p class="note">Proof of Walk needs JavaScript.</p></noscript>
    <h2>Ranks</h2>
    {pow_ranks_html(data)}
    <h2>Proof of Walk leaderboard</h2>
    <p class="sub" id="pow-total"></p>
    <ol class="lb-list" id="pow-list"><li class="lb-empty">Loading…</li></ol>
    <p class="note" style="margin-top:8px"><a href="/leaderboard/">See full leaderboard →</a></p>
    <h2>How it works</h2>
    <p class="note">Tap <strong>Check in here</strong> on a statue page or the <a href="/">map</a> within 150 m. Each GPS-verified check-in is that statue’s card in your passport, one per statue. Ranks are just for fun: free, and not linked to tips or the giveaway. <a href="/privacy/">Privacy</a>.</p>
    {footer(data)}
  </main>
"""
    return out + api_script() + POW_JS + '\n' + TAIL


def pow_roll_page(data):
    canonical = SITE + '/proof-of-walk/fellow-travelers/'
    title = f'{ORDER_NAME} – Proof of Walk'
    desc = f'Members’ roll of {ORDER_NAME} ({pow_order_rule(data)}), plus the Genesis Block miners.'
    lds = ld(breadcrumb_ld([('Map', SITE + '/'), ('Proof of Walk', SITE + '/proof-of-walk/'), ('Fellow Travelers', canonical)]))
    out = pow_body_tag(pow_head(data, title, desc, canonical, lds), data, 'roll')
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › <a href="/proof-of-walk/">Proof of Walk</a> › Fellow Travelers</div>
    <h1>🏛️ {e(ORDER_NAME)}</h1>
    <p class="sub">The members’ roll: walkers with {e(pow_order_rule(data))}. {e(pow_keep_text(data))}</p>
    <p class="note">Ranked by total cards collected; on a tie, whoever got there first ranks higher.</p>
    <p class="note">✨ The colored pill shows the rarest city card each walker has collected, from Common up to Legendary. <a class="cards-link" href="/proof-of-walk/cards/">About the cards →</a></p>
    <ol class="lb-list pow-roll" id="pow-roll"><li class="lb-empty">Loading…</li></ol>
    <h2 id="genesis">🧱 {e(GENESIS_TITLE)}</h2>
    <p class="note">Walkers who collected cards from {e(pow_genesis_rule(data))}.</p>
    <ol class="lb-list pow-roll" id="pow-genesis-roll"><li class="lb-empty">Loading…</li></ol>
    <p class="note" style="margin-top:10px"><a href="/proof-of-walk/">← Proof of Walk ranks and leaderboard</a></p>
    {footer(data)}
  </main>
"""
    return out + api_script() + POW_JS + '\n' + TAIL


# Per-rank share pages (/proof-of-walk/share/<slug>/): static HTML whose og:image / twitter:image is that rank's card
# (img/pow-share/<slug>.jpg, 1200x675), so X, iMessage, Slack and Facebook show the rank card without running JS.
# noindex, not in the sitemap (robots.txt still allows fetching), canonical -> /proof-of-walk/; humans are sent on to
# /proof-of-walk/ by JS (crawlers don't run it, so they keep this page's tags). "Share your rank" (POW_JS and checkin.js)
# picks the URL from me.rank.key. No nickname or other user data ever goes in these URLs or images.
POW_SHARE = {  # rank.key from the Worker -> (slug, emoji, title, description, image alt)
    'confirmed': ('confirmed', '👣', 'Confirmed on Proof of Walk',
                  'I stamped my first Satoshi statue. Walk to a Satoshi statue, tap “Check in here” and get your passport stamped. No signup, no cost.',
                  'Proof of Walk: Confirmed. I stamped my first Satoshi statue.'),
    'genesis': ('genesis-block', '🧱', 'I mined the Genesis Block on Proof of Walk',
                'GENESIS_RULE. Walk to Satoshi statues around the world and get your passport stamped. No signup, no cost.',
                'Proof of Walk: Genesis Block card.'),
    'order': ('grand-high-order', '🏛️', 'I joined the Grand High Order of Fellow Travelers',
              'ORDER_RULE. Walk to Satoshi statues around the world and get your passport stamped. No signup, no cost.',
              'Proof of Walk: Grand High Order of Fellow Travelers card. I joined the Grand High Order.'),
}


def pow_share_url(key):
    return f'{SITE}/proof-of-walk/share/{POW_SHARE[key][0]}/'


# Launch rank share pages /proof-of-walk/share/<rank>/ and the 63 old prism links /proof-of-walk/share/<rank>/NN/ (Noah
# 2026-10-31 5:08 PM ET, city-free): titles like "Confirmed on Proof of Walk", og/twitter tags to match, a city-free rank
# image (img/cards/og/rank/<rank>.<ver>.jpg, PowCard.ogRank) and humans are sent on to /proof-of-walk/ (meta refresh +
# location.replace + canonical, noindex). The statue pages /proof-of-walk/share/<rank>/<statue>/ stay as they are.
def pow_rank_rule(data, key):
    return {'confirmed': 'Your first GPS-verified card at any Satoshi statue.',
            'genesis': f'Cards from any {pow_genesis_required(data)} of the original 10 Satoshi statues.',
            'order': f'The Genesis Block plus {pow_order_extra(data)} more statue{"" if pow_order_extra(data) == 1 else "s"}, anywhere on the map.'}[key]


def card_og_rank_img(rank_slug):
    return f'img/cards/og/rank/{rank_slug}.{CARD_OG_VER}.jpg'


def old_share_redirect_page(data, key):
    rs, label, _, emoji = POW_RANKS[key]
    target = SITE + '/proof-of-walk/'
    url = f'{SITE}/proof-of-walk/share/{rs}/'
    title = f'{label} on Proof of Walk'
    desc = f'{pow_rank_rule(data, key)} A real walk to a real statue, verified by GPS. Start your Proof of Walk passport.'
    img = f'{SITE}/{card_og_rank_img(rs)}'
    alt = f'Proof of Walk {label}: {pow_rank_rule(data, key)}'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{e(title)} · Satoshi Statues</title>
  <meta name="description" content="{e(desc)}" />
  <meta name="robots" content="noindex, follow" />
  <link rel="canonical" href="{target}" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="{url}" />
  <meta property="og:title" content="{e(title)}" />
  <meta property="og:description" content="{e(desc)}" />
  <meta property="og:image" content="{img}" />
  <meta property="og:image:type" content="image/jpeg" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta property="og:image:alt" content="{e(alt)}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{e(title)}" />
  <meta name="twitter:description" content="{e(desc)}" />
  <meta name="twitter:image" content="{img}" />
  <meta name="twitter:image:alt" content="{e(alt)}" />
  <meta http-equiv="refresh" content="0; url={target}" />
  <script>location.replace("{target}");</script>
</head>
<body>
  <p>{emoji} {e(title)}. <a href="{target}">See Proof of Walk ranks →</a></p>
</body>
</html>
'''


def old_share_redirects(data):
    out = {}
    for k, v in POW_RANKS.items():
        out[f'proof-of-walk/share/{v[0]}/index.html'] = old_share_redirect_page(data, k)
        for n in range(1, 22):
            out[f'proof-of-walk/share/{v[0]}/{n:02d}/index.html'] = old_share_redirect_page(data, k)
    return out


# Prism cards (variants of the three rank cards): 21 cards per rank, img/pow-share/<slug>/NN.jpg (1280x720, imported by
# tools/import_prism_cards.py). The Worker draws one per walker per rank the first time the rank is earned (crypto RNG,
# weights 7/6/4/2/1 of 121; card 21 is a plain 1-in-121 draw, not linked to the giveaway) and returns it as me.card {rank, n}. Social crawlers don't run JS, so each card
# gets its own static page /proof-of-walk/share/<slug>/NN/ with that card as og:image / twitter:image: same rules as the
# base share pages (noindex, not in the sitemap, canonical /proof-of-walk/, humans redirected). Quotes stay in the
# images, not in page copy. Pages are only made for cards whose image exists, so a missing image keeps the base page.
POW_CARD_TIERS = {**{n: 'Common' for n in range(1, 11)}, **{n: 'Uncommon' for n in range(11, 17)},
                  **{n: 'Rare' for n in range(17, 20)}, 20: 'Ultra rare', 21: 'Legendary'}


def pow_card_img(slug, n):
    return f'img/pow-share/{slug}/{n:02d}.jpg'


# Card text for /proof-of-walk/cards/ (from the card set's sayings.json; notes from the cards-page draft).
# n: (quote or None, attribution, plain-English note, source link or None). A None quote is shown only in the card image.
# Card 13 swapped to the code-vs-words quote (Noah 2026-10-31 08:40 ET).
POW_CARD_TEXT = {
    1: ('Not your keys, not your coins.', 'Bitcoin saying', 'A popular Bitcoin saying. If someone else holds the keys to your bitcoin, they control it.', None),
    2: ("Don't trust, verify.", 'Bitcoin saying', 'A Bitcoin motto. Bitcoin lets anyone check the rules for themselves instead of trusting someone.', None),
    3: ('Stay humble, stack sats.', 'Bitcoin saying', 'A friendly Bitcoin saying: stay modest and keep saving a few sats (small pieces of a bitcoin).', None),
    4: ('Tick tock, next block.', 'Bitcoin saying', 'A Bitcoin saying. A new block is added to Bitcoin about every 10 minutes, like a clock.', None),
    5: ('I AM HODLING', 'GameKyuubi, BitcoinTalk, Dec 18 2013', '“HODL” began as a typo in a BitcoinTalk forum post titled “I AM HODLING” on Dec 18, 2013. It now means holding on.', 'https://bitcointalk.org/index.php?topic=375643.0'),
    6: ('Vires in numeris. (Strength in numbers.)', 'Bitcoin motto', 'Latin for “strength in numbers”, an early Bitcoin motto.', None),
    7: ('Fix the money, fix the world.', 'Bitcoin saying', 'A Bitcoin saying: the idea that better money makes a better world.', None),
    8: ('Writing a description for this thing for general audiences is bloody hard.', 'Satoshi Nakamoto, BitcoinTalk, Jul 5 2010', 'Satoshi Nakamoto on the BitcoinTalk forum, July 5, 2010, on how hard Bitcoin is to explain.', 'https://satoshi.nakamotoinstitute.org/posts/bitcointalk/167/'),
    9: ('…an electronic payment system based on cryptographic proof instead of trust…', 'Bitcoin whitepaper, 2008', 'From section 1 of the Bitcoin whitepaper (2008).', 'https://bitcoin.org/bitcoin.pdf'),
    10: ('We have proposed a system for electronic transactions without relying on trust.', 'Bitcoin whitepaper, 2008', 'The first line of the Bitcoin whitepaper’s conclusion (2008).', 'https://bitcoin.org/bitcoin.pdf'),
    11: ('Proof-of-work is essentially one-CPU-one-vote.', 'Bitcoin whitepaper, 2008', 'From section 4 of the Bitcoin whitepaper (2008). Proof of Walk is our walking version of proof-of-work.', 'https://bitcoin.org/bitcoin.pdf'),
    12: ('It might make sense just to get some in case it catches on.', 'Satoshi Nakamoto, Cryptography list, Jan 16 2009', 'Satoshi Nakamoto on the Cryptography mailing list, January 16, 2009, a week after Bitcoin launched.', 'https://satoshi.nakamotoinstitute.org/emails/cryptography/17/'),
    13: ("I'm better with code than with words though.", 'Satoshi Nakamoto, Cryptography mailing list, Nov 14 2008', 'Satoshi Nakamoto on the Cryptography mailing list, November 14, 2008, two weeks after sharing the whitepaper.', 'https://satoshi.nakamotoinstitute.org/emails/cryptography/12/'),
    14: ("If you don't believe me or don't get it, I don't have time to try to convince you, sorry.", 'Satoshi Nakamoto, BitcoinTalk, Jul 29 2010', 'Satoshi Nakamoto on the BitcoinTalk forum, July 29, 2010.', 'https://bitcointalk.org/index.php?topic=532.msg6306#msg6306'),
    15: ("The root problem with conventional currency is all the trust that's required to make it work.", 'Satoshi Nakamoto, P2P Foundation, Feb 11 2009', 'Satoshi Nakamoto introducing Bitcoin on the P2P Foundation forum, February 11, 2009.', 'https://satoshi.nakamotoinstitute.org/posts/p2pfoundation/1/'),
    16: ('…gain a new territory of freedom for several years.', 'Satoshi Nakamoto, Cryptography list, Nov 6 2008', 'Satoshi Nakamoto on the Cryptography mailing list, November 6, 2008.', 'https://satoshi.nakamotoinstitute.org/emails/cryptography/4/'),
    17: ('Total circulation will be 21,000,000 coins.', 'Satoshi Nakamoto, Bitcoin v0.1 release, Jan 8 2009', 'Satoshi Nakamoto announcing Bitcoin v0.1, January 8, 2009: the 21 million limit, in Satoshi’s words.', 'https://satoshi.nakamotoinstitute.org/emails/cryptography/16/'),
    18: ('Bitcoin: A Peer-to-Peer Electronic Cash System', 'Satoshi Nakamoto, whitepaper title, Oct 31 2008', 'The title of the Bitcoin whitepaper, published October 31, 2008.', 'https://bitcoin.org/bitcoin.pdf'),
    19: ('Running bitcoin', 'Hal Finney (@halfin), Jan 10 2009', 'Hal Finney’s tweet on January 10, 2009, the first known tweet about Bitcoin. Hal was one of the first people to run it.', 'https://x.com/halfin/status/1110302988'),
    20: ("I've been working on a new electronic cash system that's fully peer-to-peer, with no trusted third party.", 'Satoshi Nakamoto, Cryptography list, Oct 31 2008', 'The first words Satoshi Nakamoto used to introduce Bitcoin, on the Cryptography mailing list, October 31, 2008.', 'https://satoshi.nakamotoinstitute.org/emails/cryptography/1/'),
    21: ('The Times 03/Jan/2009 Chancellor on brink of second bailout for banks', 'Genesis block coinbase, Block 0, Jan 3 2009', 'The newspaper headline Satoshi put inside the very first Bitcoin block (block 0) on January 3, 2009. It is still there today.', 'https://mempool.space/block/000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f'),
}

POW_CARD_UNITS = {'Common': 7, 'Uncommon': 6, 'Rare': 4, 'Ultra rare': 2, 'Legendary': 1}   # per card, out of 121 (= the Worker's cards.js)
POW_CARD_CLASS = {'Common': 't-common', 'Uncommon': 't-uncommon', 'Rare': 't-rare', 'Ultra rare': 't-ultra', 'Legendary': 't-genesis'}
POW_CARDS_RANK = 'confirmed'   # the gallery shows the Confirmed set (same 21 sayings and frames on every rank)
POW_CARDS_CSS = '.strip{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:6px 0 16px}\n.strip img,.rank img,.gen img{display:block;width:100%;height:auto;border-radius:8px;border:1px solid #30363d;background:#161b22}\n.strip figcaption{font-size:.75rem;color:#8b949e;margin-top:4px;text-align:center}\n.ranks{list-style:none;display:grid;gap:12px}\n.rank{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr);gap:14px;align-items:center;background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px}\n.rank h3{font-size:1.05rem;color:#f7931a;margin-bottom:2px}.rank p{font-size:.92rem;color:#c9d1d9}\n.rank .step{display:inline-block;font-size:.72rem;font-weight:700;color:#8b949e;letter-spacing:.04em;text-transform:uppercase}\n.tiers{list-style:none;border:1px solid #30363d;border-radius:10px;background:#161b22;overflow:hidden}\n.tiers li{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px;border-bottom:1px solid #30363d}\n.tiers li:last-child{border-bottom:0}\n.sw{width:52px;height:34px;border-radius:6px;border:1px solid #30363d}\n.tiers strong{display:block}.tiers .desc{font-size:.85rem;color:#8b949e}\n.tiers .pct{font-weight:800;font-size:1.05rem;text-align:right;white-space:nowrap}.tiers .pct small{display:block;font-size:.7rem;font-weight:400;color:#8b949e}\n.tier{display:inline-block;font-size:.72rem;font-weight:700;border-radius:4px;padding:1px 7px;color:#0d1117}\n.t-common{--f:linear-gradient(135deg,#8a5a2b,#e8b07a 45%,#7a4a1f)}\n.t-uncommon{--f:linear-gradient(135deg,#1f6f8b,#7fe3f0 40%,#2a9d8f 70%,#9be7c4)}\n.t-rare{--f:linear-gradient(135deg,#ff6b6b,#ffd93d,#6bff95,#4dd2ff)}\n.t-ultra{--f:linear-gradient(135deg,#ff4d4d,#ffb84d,#f9ff4d,#4dff88,#4dc3ff,#a64dff,#ff4dd2)}\n.t-genesis{--f:conic-gradient(from 0deg,#ff4d4d,#ffb84d,#f9ff4d,#4dff88,#4dc3ff,#a64dff,#ff4dd2,#ff4d4d)}\n.sw,.tier{background:var(--f)}\n.gen{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:14px;align-items:center;background:#1f1a0d;border:1px solid #6e5a1e;border-radius:10px;padding:14px;margin:10px 0}\n.gen h3{color:#ffdf80;font-size:1.05rem;margin-bottom:6px}.gen p{font-size:.92rem;color:#e6edf3}.gen p+p{margin-top:8px}\n.gen code{display:block;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88rem;color:#ffdf80;background:#0d1117;border:1px dashed #6e5a1e;border-radius:8px;padding:8px 10px;margin:8px 0;overflow-wrap:anywhere}\n.grid{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}\n.cc{all:unset;text-decoration:none;color:inherit;box-sizing:border-box;display:flex;flex-direction:column;width:100%;height:100%;cursor:pointer;background:#161b22;border:1px solid #30363d;border-radius:10px;overflow:hidden}\n.cc:hover,.cc:focus-visible{border-color:#f7931a;outline:none}\n.cc img{display:block;width:100%;height:auto;aspect-ratio:16/9}\n.cc-meta{display:flex;justify-content:space-between;align-items:center;padding:8px 10px 2px}\n.cc-no{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:700;font-size:.85rem;color:#e6edf3}\n.cc-q{display:block;padding:2px 10px 10px;font-size:.85rem;color:#c9d1d9;font-style:italic}\n#cd{border:1px solid #30363d;border-radius:12px;padding:0;background:#161b22;color:#e6edf3;width:min(720px,94vw);max-height:92vh;margin:auto}\n#cd::backdrop{background:rgba(0,0,0,.85)}\n#cd img{display:block;width:100%;height:auto}\n#cd .cd-body{padding:12px 16px 16px}\n#cd .q{font-size:1.05rem;font-style:italic;margin:8px 0 4px}\n#cd .by{font-size:.85rem;color:#8b949e}\n#cd .n{font-size:.92rem;margin-top:10px}\n#cd .cd-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}\n#cd .cd-bar{display:flex;justify-content:space-between;align-items:center;padding:4px 6px 4px 16px;font-size:.85rem;color:#8b949e;border-bottom:1px solid #30363d}\n#cd .cd-close{width:44px;height:44px;border-radius:50%;border:1px solid #30363d;background:#21262d;color:#e6edf3;font-size:1.1rem;cursor:pointer}\n.share-list{list-style:none;display:grid;gap:8px;margin:10px 0}\n.share-list a{display:flex;align-items:center;gap:10px;min-height:44px;padding:8px 12px;border:1px solid #30363d;border-radius:8px;background:#161b22;color:#e6edf3;text-decoration:none;font-size:.92rem}\n.share-list a:hover{border-color:#f7931a;color:#f7931a}\n@media (max-width:600px){.brand-logo{height:36px}.top .tagline{font-size:.72rem;padding-left:10px}.top nav{width:100%}h1{font-size:1.4rem}\n.rank,.gen{grid-template-columns:1fr}.strip{gap:6px}.tiers li{grid-template-columns:40px minmax(0,1fr) auto;gap:10px}.sw{width:40px;height:28px}.grid{grid-template-columns:1fr 1fr;gap:8px}.cc-q{font-size:.8rem}}\n@media (max-width:360px){.grid{grid-template-columns:1fr}}'


def pow_card_thumb(slug, n):
    return f'img/pow-share/thumbs/{slug}/{n:02d}.jpg'


def pow_cards_odds_html():
    assert sum(POW_CARD_UNITS[POW_CARD_TIERS[n]] for n in range(1, 22)) == 121
    desc = {'Common': 'Brushed-metal foil frame, a different color on every card.',
            'Uncommon': 'Two-tone foil with a soft streak of light across the art.',
            'Rare': 'Prism foil frame and holographic bands over the art.',
            'Ultra rare': 'Full rainbow foil with ripples and sparkles.',
            'Legendary': 'Double rainbow frame, full holographic shine, sparkles.'}
    rows = []
    for t, u in POW_CARD_UNITS.items():
        ns = [n for n in range(1, 22) if POW_CARD_TIERS[n] == t]
        span = f'Card {ns[0]:02d}' if len(ns) == 1 else f'Cards {ns[0]:02d}–{ns[-1]:02d}'
        tot = u * len(ns)
        each = '' if len(ns) == 1 else f' Each card: {u} in 121.'
        pct = f'{tot / 121 * 100:.1f}%<small>{tot} in 121</small>'
        rows.append(f'<li class="{POW_CARD_CLASS[t]}"><span class="sw"></span><span><strong>{e(t)}</strong><span class="desc">{span}. {desc[t]}{each}</span></span><span class="pct">{pct}</span></li>')
    return '<ul class="tiers">' + ''.join(rows) + '</ul>'


def pow_cards_gallery_html():
    out = []
    for n in range(1, 22):
        q, by, note, link = POW_CARD_TEXT[n]
        t = POW_CARD_TIERS[n]
        qtxt = q if q else 'The saying is shown on the card.'
        alt = f'Card {n:02d} of 21, {t}' + (f': {q}' if q else '')
        out.append(f'<li><a class="cc {POW_CARD_CLASS[t]}" href="/{pow_card_img(POW_CARDS_RANK, n)}" data-n="{n:02d}" data-tier="{e(t)}" '
                   f'data-quote="{e(q or "")}" data-by="{e(by)}" data-note="{e(note)}" data-link="{e(link or "")}">'
                   f'<img src="/{pow_card_thumb(POW_CARDS_RANK, n)}" width="640" height="360" loading="lazy" decoding="async" alt="{e(alt)}">'
                   f'<span class="cc-meta"><span class="cc-no">No. {n:02d}</span><span class="tier {POW_CARD_CLASS[t]}">{e(t)}</span></span>'
                   f'<span class="cc-q">{e(qtxt)}</span></a></li>')
    return '\n'.join(out)


POW_CARDS_JS = r"""<script>
(function(){
  var d=document.getElementById('cd'),$=function(i){return document.getElementById(i)};
  if(!d||!d.showModal)return;   // no <dialog>: the card links open the full image
  document.querySelectorAll('.cc').forEach(function(b){
    b.addEventListener('click',function(ev){
      ev.preventDefault();
      var n=b.dataset.n,t=b.className.replace('cc ','');
      $('cd-img').src=b.getAttribute('href');$('cd-img').alt=b.querySelector('img').alt;
      $('cd-no').textContent='No. '+n+' / 21';$('cd-tier').textContent=b.dataset.tier;$('cd-tier').className='tier '+t;
      $('cd-q').textContent=b.dataset.quote;$('cd-q').hidden=!b.dataset.quote;
      $('cd-by').textContent='— '+b.dataset.by;$('cd-note').textContent=b.dataset.note;
      var l=$('cd-link');if(b.dataset.link){l.href=b.dataset.link;l.parentNode.hidden=false}else{l.parentNode.hidden=true}
      d.showModal();
    });
  });
  d.querySelector('.cd-close').addEventListener('click',function(){d.close()});
  d.addEventListener('click',function(e){if(e.target===d)d.close()});
})();
</script>"""


# ---------- Combined statue + rank card (design 2; spec combined-cards/spec.md, Noah 2026-10-31 1:31 PM ET) ----------
# One card per rank: the front shows the statue whose GPS stamp earned the rank (art panel img/cards/art/<page>.jpg,
# original city scene with a generic hooded figure, no statue likeness), the rank badge and a GPS-verified seal with the
# statue-local check-in date; the back shows the drawn quote (same 21 sayings, tiers and weights; card 21 Legendary,
# about 1 in 121, not linked to the giveaway), the check-in box, a verify code PW-XXXX-XXXX and a QR to /v/?c=CODE.
# Rendering is client-side (pow-card.js, hand-written, Canvas 2D); this block builds its data file, the verify page,
# the 33 generic share pages (statue x rank, no date/code/quote) and the cards explainer. Share images (1200x630) and
# the explainer's sample images are rendered by tools/render_combined_cards.mjs from the same pow-card.js.
POW_RANKS = {  # rank key -> (share slug, label, badge text, emoji)
    'confirmed': ('confirmed', 'Confirmed', 'CONFIRMED', '👣'),
    'genesis': ('genesis-block', 'Genesis Block', 'GENESIS BLOCK', '🧱'),
    'order': ('grand-high-order', 'Grand High Order', 'GRAND HIGH ORDER', '🏛️'),
}
CARD_CREDIT = ('Quotes attributed as shown. Headline from The Times, 3 Jan 2009, as embedded in Bitcoin’s genesis block. '
               'Not affiliated with or endorsed by The Times, any statue artist, owner or city.')   # approved D1
CARD_NOT_AFFILIATED = 'Not affiliated with or endorsed by The Times, any statue artist, owner or city.'
# Print ordering (spec §5.7) is not open yet. Until CARD_PRINT_ORDERING_OPEN is True the price/disclosure line below is
# not emitted anywhere (not in card-data.js, not in any HTML). Print copy never uses draw, luck/lucky, chance, odds or
# giveaway wording (Noah 2026-10-31 2:26 PM ET); tools/check_card_words.py checks this constant and the print panel.
# The wording below is a shortened version of Grant's §5.6 line; have Grant re-check it before switching the flag on.
CARD_PRINT_ORDERING_OPEN = False
CARD_PRINT_NOTE = ('Ordering a printed card is optional and doesn’t change your rank or your card. '
                   'Printed cards cost the same at every tier and are just for fun.')
# Exact line from Noah/Grant (2026-10-31 4:50 PM ET), shown under the tier % column on /proof-of-walk/cards/.
CARD_RARITY_NOTE = "Rarity shows how often a design is drawn. It isn't a measure of value, and cards can't be bought, sold or traded here."
CARD_OG_VER = 'v1'   # bump when the share images change, so X/Facebook/LinkedIn re-scrape
CARD_SAYINGS = os.path.join(ROOT, 'tools', 'pow_sayings.json')   # copy of rank-cards/variants/sayings.json


def card_statues(data):
    return [s for s in data['statues'] if s['status'] in CHECKABLE and os.path.exists(os.path.join(ROOT, 'img', 'cards', 'art', s['page'] + '.jpg'))]


def card_phrase(s):
    # Share text / share-page title: true for every statue (Kranj is a Bitcoin "B" monument, Miami's is the Bitcoin Bull,
    # Buenos Aires is the "Satoshi Monument" glass cube).
    return {'kranj': 'the Bitcoin monument in Kranj', 'miami-bull': 'the Bitcoin Bull in Miami',
            'buenos-aires': 'the Satoshi monument in Buenos Aires'}.get(s['page'], f"the Satoshi statue in {s['city']}")


def card_quotes():
    with open(CARD_SAYINGS, encoding='utf-8') as f:
        q = json.load(f)
    assert [x['n'] for x in q] == list(range(1, 22))
    m = {'common': 'Common', 'uncommon': 'Uncommon', 'rare': 'Rare', 'ultra': 'Ultra rare', 'genesis': 'Legendary'}
    for x in q:
        assert m[x['tier']] == POW_CARD_TIERS[x['n']], x   # same tiers as the Worker's cards.js and the cards page
    return q


def card_og_img(rank_slug, page):
    return f'img/cards/og/{rank_slug}/{page}.{CARD_OG_VER}.jpg'


def card_page_base():
    # Per-card share pages are served by the Worker (/c/PW-XXXX-XXXX): GitHub Pages is static, and link previews need
    # each card's own og:/twitter: tags in the HTML (crawlers don't run JS). pow-card.js appends the verify code.
    return LB_API.rstrip('/') + '/c/'


def card_og_card_img(rank_slug, page, n):
    # Per-card share image: statue x rank at check-in x card number (tools/render_combined_cards.mjs).
    return f'img/cards/og/card/{rank_slug}/{page}/{n:02d}.{CARD_OG_VER}.jpg'


def write_worker_cardshare(data):
    """Card text for the Worker's per-card share pages (src/cardshare.gen.js): same statues, quotes and ranks as
    card-data.js, plus where the share images live. Written by build.py --worker."""
    st = {s['slug']: {'page': s['page'], 'label': s['label'], 'city': s['city'], 'country': s['country'],
                      'tz': s.get('tz') or 'UTC', 'phrase': card_phrase(s)} for s in card_statues(data)}
    d = {'site': SITE, 'og_ver': CARD_OG_VER, 'og_path': 'img/cards/og/card/{rank}/{page}/{nn}.' + CARD_OG_VER + '.jpg',
         'statues': st, 'quotes': [{'n': x['n'], 'q': x['quote'], 'by': x['by']} for x in card_quotes()],
         'ranks': {k: {'share': v[0], 'label': v[1], 'emoji': v[3]} for k, v in POW_RANKS.items()},
         'not_affiliated': CARD_NOT_AFFILIATED}
    path = os.path.join(WORKER_DIR, 'src', 'cardshare.gen.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('// Generated by satoshistatues.com build.py --worker from statues.json + tools/pow_sayings.json. Do not edit.\n'
                'export const CARD_SHARE = ' + json.dumps(d, ensure_ascii=False, indent=1) + ';\n')
    print(f'wrote {path} ({len(st)} card statues)')


def card_data_js(data):
    st = {s['slug']: {'page': s['page'], 'title': s['city'].upper(), 'subtitle': f"{s['city']}, {s['country']}", 'label': s['label'],
                      'tz': s.get('tz') or 'UTC', 'phrase': card_phrase(s), 'og_place': card_phrase(s)} for s in card_statues(data)}
    d = {'site': SITE, 'statues': st,
         'quotes': [{'n': x['n'], 'q': x['quote'], 'by': x['by'], 'hue': x['hue']} for x in card_quotes()],
         'ranks': {k: {'share': v[0], 'label': v[1], 'badge': v[2], 'emoji': v[3], 'rule': pow_rank_rule(data, k)} for k, v in POW_RANKS.items()},
         'credit': CARD_CREDIT, 'not_affiliated': CARD_NOT_AFFILIATED, 'card_page': card_page_base()}
    if CARD_PRINT_ORDERING_OPEN:
        d['print_note'] = CARD_PRINT_NOTE
    return ('// Generated by build.py from statues.json + tools/pow_sayings.json. Do not edit. Read by /pow-card.js.\n'
            'window.POW_CARD_DATA = ' + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';\n')


def pow_card_js_url(data):
    import hashlib
    h = hashlib.sha256(open(os.path.join(ROOT, 'pow-card.js'), 'rb').read() + card_data_js(data).encode()).hexdigest()[:10]
    return f'/pow-card.js?v={h}'


def card_share_url(key, s):
    return f"{SITE}/proof-of-walk/share/{POW_RANKS[key][0]}/{s['page']}/"


def card_share_page(data, key, s):
    rs, label, _, emoji = POW_RANKS[key]
    title = f'{label} at {card_phrase(s)}'
    desc = 'A real walk to a real statue, verified by GPS. Start your Proof of Walk passport.'
    url, img = card_share_url(key, s), f'{SITE}/{card_og_img(rs, s["page"])}'
    alt = f'Proof of Walk {label} card for {s["label"]}, {s["city"]}, {s["country"]}: a city scene with the rank badge and a GPS-verified seal.'
    out = head(title, desc, url, img, 1200, 630, alt, '')
    out = out.replace('<meta name="robots" content="index, follow" />', '<meta name="robots" content="noindex, follow" />', 1)
    out = out.replace('<meta property="og:image:width"', '<meta property="og:image:type" content="image/jpeg" />\n  <meta property="og:image:width"', 1)
    rule = {'confirmed': 'a first GPS-verified card at any Satoshi statue',
            'genesis': f'GPS-verified cards from any {pow_genesis_required(data)} of the original 10 statues',
            'order': f'the Genesis Block plus {pow_order_extra(data)} more statue, anywhere on the map'}[key]
    out = out.replace('</style>', '.cs-hero{display:block;width:100%;height:auto;border-radius:12px;border:1px solid #30363d;margin:6px 0 12px}'
                      '.cs-go{display:grid;gap:8px;margin:12px 0}.cs-go .btn{min-height:52px;font-size:1rem}'
                      '.cs-steps{margin:8px 0 0 1.2em;color:#c9d1d9;font-size:.95rem}.cs-steps li{margin:4px 0}'
                      '.cs-tags{color:#58a6ff;font-size:.9rem;margin-top:10px}' + CARDS_LINK_CSS + '</style>', 1)
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › <a href="/proof-of-walk/">Proof of Walk</a> › {e(label)}</div>
    <h1>{emoji} {e(label)} ✓</h1>
    <p class="sub">at {e(s['label'])} · {e(s['city'])}, {e(s['country'])}</p>
    <img class="cs-hero" src="/{card_og_img(rs, s['page'])}" width="1200" height="630" alt="{e(alt)}" />
    <p class="note">Someone walked to {e(card_phrase(s))} and earned <strong>{e(label)}</strong> on Proof of Walk: {e(rule)}. Every check-in is checked by GPS on the spot.</p>
    <div class="cs-go"><a class="btn primary" href="/">📍 Find a statue near you</a><a class="btn" href="/proof-of-walk/">👣 Start your passport</a></div>
    <h2>How it works</h2>
    <ol class="cs-steps">
      <li>Walk to any Satoshi statue on the <a href="/">map</a>.</li>
      <li>Tap <strong>Check in here</strong> within 150 m. Your phone’s GPS confirms you’re there.</li>
      <li>Earn ranks (Confirmed, Genesis Block, Grand High Order), each with its own card of the statue you walked to.</li>
    </ol>
    <p class="note">Free, no sign-up, no app. <a href="/{s['page']}/">About {e(s['label'])} →</a></p>
    <p><a class="cards-link" href="/proof-of-walk/cards/">About the cards →</a></p>
    <p class="cs-tags">#ProofOfWalk #Bitcoin</p>
    {footer(data)}
  </main>
"""
    return out + TAIL


def card_share_pages(data):
    return {f"proof-of-walk/share/{POW_RANKS[k][0]}/{s['page']}/index.html": card_share_page(data, k, s)
            for k in POW_RANKS for s in card_statues(data)}


VERIFY_JS = r"""<script>
(function () {
  var A = window.SS_API, $ = function (i) { return document.getElementById(i); };
  var RS = { confirmed: ['confirmed', '👣'], genesis: ['genesis-block', '🧱'], order: ['grand-high-order', '🏛️'] };
  var esc = function (t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  var code = (new URLSearchParams(location.search).get('c') || '').trim().slice(0, 20);
  $('v-code').value = code;
  function show(html, cls) { var el = $('v-out'); el.className = 'v-out ' + (cls || ''); el.innerHTML = html; }
  if (!code) { show('<p>Type the code from the back of a card (it looks like <strong>PW-7K3Q-9QX2</strong>), or scan the card’s QR code.</p>'); return; }
  if (!A || !window.fetch) { show('<p>Verification needs JavaScript and a connection.</p>'); return; }
  show('<p>Checking…</p>');
  fetch(A + '/api/pow/verify?code=' + encodeURIComponent(code)).then(function (r) { return r.json(); }).then(function (j) {
    if (!j || !j.ok) { show('<p class="v-no">❌ We couldn’t find that code. Check the letters and numbers on the back of the card and try again.</p>', 'bad'); return; }
    var rk = RS[j.rank_key] || RS.confirmed;
    var xh = j.x_username && /^[A-Za-z0-9_]{1,15}$/.test(j.x_username) ? j.x_username : '';
    var XV = '<details class="xvd"><summary class="xv" title="Signed in with this X account. Not X’s verification badge." aria-label="Verified">✓</summary><span class="xtip" role="note"><strong>Verified:</strong> Signed in with this X account. Not X’s verification badge. <a href="#x-disclaimer">More</a></span></details>';
    show('<p class="v-ok">✅ GPS-verified check-in</p><p class="v-line"><strong>' + esc(j.statue.label) + '</strong> · ' + esc(j.date) + ' · ' + rk[1] + ' ' + esc(j.rank) + '</p>' +
      (xh ? '<div class="v-line v-x">X account verified by sign-in: <a href="https://x.com/' + xh + '" target="_blank" rel="noopener noreferrer nofollow"><strong>@' + esc(xh) + '</strong></a>' + XV + '</div>' : '') +
      '<img class="v-img" src="/img/cards/og/' + rk[0] + '/' + encodeURIComponent(j.statue.page) + '.__OGV__.jpg" width="1200" height="630" alt="' + esc(j.rank) + ' card for ' + esc(j.statue.label) + '">' +
      '<p class="note">This card was issued by satoshistatues.com for a real check-in within 150 m of the statue.</p>' +
      '<p class="note"><a href="/' + encodeURIComponent(j.statue.page) + '/">About ' + esc(j.statue.label) + ' →</a></p>', 'good');
  }).catch(function () { show('<p>Couldn’t reach the server. Try again in a moment.</p>', 'bad'); });
})();
</script>"""


def verify_page(data):
    canonical = SITE + '/v/'
    title = 'Verify a Proof of Walk card – satoshistatues.com'
    desc = 'Check that a Proof of Walk card is a real, GPS-verified check-in at a Satoshi statue.'
    out = head(title, desc, canonical, OG_IMAGE, 1200, 630, 'Satoshi statues world map', '')
    out = out.replace('<meta name="robots" content="index, follow" />', '<meta name="robots" content="noindex, nofollow" />', 1)
    out = out.replace('</style>', '.v-out{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;margin:12px 0}'
                      '.v-out.good{border-left:3px solid #3fb950}.v-out.bad{border-left:3px solid #f85149}.v-ok{font-size:1.25rem;font-weight:800;color:#3fb950;margin:0 0 4px}'
                      '.v-line{font-size:1.02rem;margin:0 0 10px}.v-img{display:block;width:100%;height:auto;border-radius:10px;margin:8px 0}'
                      '.v-form{display:flex;gap:8px;margin:10px 0}.v-form input{flex:1;min-height:44px;padding:10px 12px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font:600 16px ui-monospace,Menlo,monospace;text-transform:uppercase}'
                      '.v-form button{min-height:44px;padding:10px 16px;border-radius:8px;border:none;background:#f7931a;color:#0d1117;font-weight:700;font-family:inherit;cursor:pointer}' + CARDS_LINK_CSS + '</style>', 1)
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › <a href="/proof-of-walk/">Proof of Walk</a> › Verify</div>
    <h1>✅ Verify a Proof of Walk card</h1>
    <p class="sub">Every card carries a code. It shows the statue, the date and the rank, plus the walker’s @handle if they linked their X account.</p>
    <div id="v-out" class="v-out" aria-live="polite"><p>Loading…</p></div>
    <form class="v-form" method="get" action="/v/"><label class="sr-only" for="v-code" style="position:absolute;left:-9999px">Verify code</label>
      <input id="v-code" name="c" maxlength="20" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="PW-XXXX-XXXX"><button type="submit">Check</button></form>
    <p class="note">No nicknames, exact times or locations are shown here. <a href="/privacy/">Privacy</a></p>
    <p><a class="cards-link" href="/proof-of-walk/cards/">About the cards</a></p>
    {footer(data)}
  </main>
"""
    return out + VERIFY_JS.replace('__OGV__', CARD_OG_VER) + '\n' + TAIL


def pow_cards_tiers_html():
    # Tier table: % and "N in 121 cards" (spec §5.6); no odds/chance wording.
    assert sum(POW_CARD_UNITS[POW_CARD_TIERS[n]] for n in range(1, 22)) == 121
    desc = {'Common': 'Brushed-metal frame, a different color on every card.',
            'Uncommon': 'Two-tone foil frame with a soft streak of light across the art.',
            'Rare': 'Prism frame with holographic bands over the art.',
            'Ultra rare': 'Full rainbow frame with ripples, stronger shine and sparkles.',
            'Legendary': 'Double rainbow frame, gold inner frame, full holographic shine, sparkles, and the quote set like raw block data.'}
    rows = []
    for t, u in POW_CARD_UNITS.items():
        ns = [n for n in range(1, 22) if POW_CARD_TIERS[n] == t]
        span = f'Card {ns[0]:02d}' if len(ns) == 1 else f'Cards {ns[0]:02d}–{ns[-1]:02d}'
        tot = u * len(ns)
        each = '' if len(ns) == 1 else f' Each one: {u} in 121 cards.'
        pct = f'{tot / 121 * 100:.1f}%<small>{tot} in 121</small>'
        rows.append(f'<li class="{POW_CARD_CLASS[t]}"><span class="sw"></span><span><strong>{e(t)}</strong><span class="desc">{span}. {desc[t]}{each}</span></span><span class="pct">{pct}</span></li>')
    return '<ul class="tiers">' + ''.join(rows) + '</ul>'


def pow_cards_quotes_html():
    out = []
    for x in card_quotes():
        n = x['n']; t = POW_CARD_TIERS[n]
        _, by, note, link = POW_CARD_TEXT[n]
        src = f' <a href="{e(link)}" target="_blank" rel="noopener">Source ↗</a>' if link else ''
        q = f'<code>{e(x["quote"])}</code>' if n == 21 else f'“{e(x["quote"])}”'
        out.append(f'<li class="qq"><details><summary><span class="cc-no">{n:02d}</span><span class="tier {POW_CARD_CLASS[t]}">{e(t)}</span>'
                   f'<span class="qq-q">{q}</span><span class="qq-by">— {e(x["by"])}</span></summary><p class="qq-n">{e(note)}{src}</p></details></li>')
    return '\n'.join(out)


COMBO_CARDS_CSS = ('.duo{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0 6px}.duo figure{margin:0}.duo img{display:block;width:100%;height:auto;border-radius:12px;border:1px solid #30363d}'
                   '.duo figcaption{font-size:.8rem;color:#8b949e;margin-top:6px}.duo figcaption strong{color:#e6edf3}'
                   '.qlist{list-style:none;display:grid;gap:6px}.qq details{background:#161b22;border:1px solid #30363d;border-radius:8px}'
                   '.qq summary{cursor:pointer;display:grid;grid-template-columns:auto auto 1fr;gap:4px 8px;align-items:center;padding:10px 12px;list-style:none}'
                   '.qq summary::-webkit-details-marker{display:none}.qq-q{grid-column:1/-1;font-style:italic;color:#e6edf3;font-size:.95rem}'
                   '.qq-q code{font-style:normal;font-family:ui-monospace,Menlo,monospace;color:#ffdf80;font-size:.85rem;overflow-wrap:anywhere}'
                   '.qq-by{grid-column:1/-1;font-size:.8rem;color:#f7931a}.qq-n{padding:0 12px 10px;font-size:.85rem;color:#c9d1d9}'
                   '.credit{font-size:.8rem;color:#8b949e;border-top:1px solid #30363d;padding-top:10px;margin-top:14px}')


def pow_cards_page(data):
    canonical = SITE + '/proof-of-walk/cards/'
    title = 'Proof of Walk cards: your statue, your rank, your quote'
    desc = ('Every Proof of Walk rank comes with a card: the Satoshi statue you walked to, your rank, a GPS-verified seal and one of '
            '21 Bitcoin quotes. See how the cards work.')
    lds = ld(breadcrumb_ld([('Map', SITE + '/'), ('Proof of Walk', SITE + '/proof-of-walk/'), ('Cards', canonical)]))
    out = head(title, desc, canonical, f'{SITE}/{card_og_img("genesis-block", "lugano")}', 1200, 630,
               'Proof of Walk Genesis Block card for Satoshi Statue Lugano', lds)
    if pow_cfg(data).get('preview'):
        out = out.replace('<meta name="robots" content="index, follow" />', '<meta name="robots" content="noindex, nofollow" />', 1)
    out = out.replace('</style>', POW_CARDS_CSS + COMBO_CARDS_CSS + '</style>', 1)
    g, o = pow_genesis_required(data), pow_order_extra(data)
    ex = [s for s in card_statues(data) if s['page'] in ('lugano', 'tokyo', 'el-zonte')]
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › <a href="/proof-of-walk/">Proof of Walk</a> › Cards</div>
    <h1>🗺️ Proof of Walk cards</h1>
    <p class="sub">Your statue, your rank, your quote.</p>
    <p class="note">Every statue you walk to is a card in your passport, and the check-in that earns a rank becomes that rank’s card. The front shows the Satoshi statue you walked to, your rank and a GPS-verified seal with the date. The back carries one of <strong>21 Bitcoin quotes</strong>, the details of your check-in and a code anyone can scan to verify it.</p>
    <div class="duo">
      <figure><img src="/img/cards/sample-front.{CARD_OG_VER}.jpg" width="600" height="840" alt="Sample card front: LUGANO, Lugano, Switzerland, a lakeside scene with a hooded walker, the Genesis Block badge and the GPS verified seal, checked in 31 Oct 2026"><figcaption><strong>Front.</strong> The statue whose check-in earned the rank, the rank badge, the GPS-verified seal and the check-in date.</figcaption></figure>
      <figure><img src="/img/cards/sample-back.{CARD_OG_VER}.jpg" width="600" height="840" alt="Sample card back: the quote Not your keys, not your coins, card 01 of 21 Common, the GPS-verified check-in box with a verify code, and a QR code"><figcaption><strong>Back.</strong> Your quote and its card number, the GPS-verified check-in (statue, local date and time) and the verify code with its QR.</figcaption></figure>
    </div>

    <h2>How it works</h2>
    <ol class="ranks">
      <li class="rank" style="grid-template-columns:1fr"><div><span class="step">Rank 1</span><h3>👣 Confirmed ✓</h3><p>Your first GPS-verified card at any Satoshi statue. Your card shows that statue.</p></div></li>
      <li class="rank" style="grid-template-columns:1fr"><div><span class="step">Rank 2</span><h3>🧱 Genesis Block ✓</h3><p>Collect cards from any {g} of the original 10 statues. Your card shows the statue that completed it.</p></div></li>
      <li class="rank" style="grid-template-columns:1fr"><div><span class="step">Rank 3</span><h3>🏛️ Grand High Order ✓</h3><p>The Genesis Block plus {o} more statue{'' if o == 1 else 's'}, anywhere on the map. Your card shows the statue that got you there.</p></div></li>
    </ol>
    <p class="note" style="margin-top:10px">Every GPS-verified check-in is a card in your passport, one per statue: that statue, your rank at the time, a quote and its own verify code. The check-in that earns a rank is that rank’s card, and each rank is earned at a different statue. Once you have a card, it’s yours and it never changes.</p>

    <h2>21 quotes and how rare they are</h2>
    <p class="note" style="margin-bottom:10px">Your quote is picked when you collect the card. The frame and shine show its tier.</p>
    {pow_cards_tiers_html()}
    <p class="note" style="margin-top:8px;font-size:.85rem;color:#8b949e">Percentages are out of 121 cards. The diamonds next to the card number show the tier: one for Common, up to five for Legendary.</p>
    <p class="note rarity-note" style="margin-top:4px;font-size:.85rem;color:#8b949e">{e(CARD_RARITY_NOTE)}</p>

    <h2>The Legendary Genesis card</h2>
    <div class="gen">
      <img src="/img/cards/sample-back-21.{CARD_OG_VER}.jpg" width="600" height="840" loading="lazy" alt="Sample card back 21 of 21, Legendary: The Times 03/Jan/2009 Chancellor on brink of second bailout for banks">
      <div>
        <h3>Card No. 21 · Legendary</h3>
        <p>About 1 in 121 cards is the Legendary Genesis card, at any statue and any rank.</p>
        <p>Cards are just for fun: free, and not linked to tips or the giveaway.</p>
      </div>
    </div>
    <p class="note">Its quote is the newspaper headline Satoshi Nakamoto wrote into Bitcoin’s very first block, block 0, on January 3, 2009:</p>
    <div class="gen" style="display:block;padding:10px 14px"><code>The Times 03/Jan/2009 Chancellor on brink of second bailout for banks</code></div>
    <p class="note">It shows when Bitcoin started and why: a new kind of money, launched while banks were being bailed out. Those words are still in block 0 today, and every Bitcoin block since builds on it.</p>

    <h2>All 21 quotes</h2>
    <p class="note" style="margin-bottom:10px">Tap a quote to see where it comes from.</p>
    <ul class="qlist">
{pow_cards_quotes_html()}
    </ul>

    <h2>Verify a card</h2>
    <p class="note">Every card has a verify code like <strong>PW-7K3Q-9QX2</strong> and a QR code. Scan it, or type it on the <a href="/v/">verify page</a>: it shows only the statue, the date and the rank. No name, no exact time, no location.</p>

    <h2>Show yours off</h2>
    <p class="note">Right after a check-in that earns a rank, tap <strong>Share</strong> under your card to post it, or save the image. The link you share goes to a page for that statue and rank, for example
      {', '.join(f'<a href="/proof-of-walk/share/genesis-block/{s["page"]}/">Genesis Block at {e(s["city"])}</a>' for s in ex)}.</p>
    <p class="note">You can also download print-ready files of your card (front and back) from your card on the <a href="/proof-of-walk/">Proof of Walk</a> page. Ordering a printed card is coming soon.</p>
    <div class="actions"><a class="btn primary" href="/proof-of-walk/">👣 Proof of Walk</a><a class="btn" href="/leaderboard/">🏆 Leaderboard</a><a class="btn" href="/">🗺️ Find a statue</a></div>
    <p class="credit">{e(CARD_CREDIT)} Card art is original illustration; the hooded walker is a generic figure, not any statue or person.</p>
    {footer(data)}
  </main>
"""
    return out + TAIL


def pow_privacy_html(data):
    if not pow_cfg(data):
        return ''
    return (f'\n      <li><strong>Proof of Walk</strong> ranks are worked out from your GPS-verified cards. If you mine the Genesis Block ({pow_genesis_required(data)} of the original 10), '
            'your nickname (or “Anonymous #…”) and the date are listed on the Fellow Travelers page.</li>'
            '\n      <li>' + PRIVACY_PASSPORT_BULLET + '</li>'
            '\n      <li>Each <strong>Proof of Walk card</strong> (one per GPS-verified check-in) carries a random verify code (it isn’t linked to your device ID) and a QR code. Anyone who scans or types it sees only the statue, the date and the rank '
            '(plus your @handle with a blue ✓ Verified, only if you linked X): no nickname, no exact time, no location and no other cards. Shared and printed cards show your check-in date, time and verify code, because they’re on the card. '
            'Cards are drawn on your device’s screen; print files (including your @handle, if linked) are made in your browser and aren’t sent to anyone. Verify lookups are counted per network (as a salted hash, kept 1 day).</li>'
            + X_PRIVACY_HTML)


# xrecover privacy bullets: Grant's exact text (2026-11-02). Do not reword without Grant.
PRIVACY_PASSPORT_BULLET = "Your passport lives on this device. There's no password and no recovery code, and we don't ask for or keep a Lightning address for your passport. To move your passport to a new phone, <strong>link your X</strong> (below), then on the new phone tap “Lost your phone?” and sign in with the same X account. Your cards, rank and nickname move to the new device, and the old device no longer has them. When your passport moves, we keep a hashed ID of the old device and the time of the move for 30 days, so that device can tell you your passport moved. Anyone who can sign in to your X account can move your passport this way, so keep your X account secure. If you haven't linked X, your passport can't be restored after you clear your browser data or lose your phone. Restores are counted per network and per X account (as salted hashes, kept 1 day)."
PRIVACY_CLAIM_BULLET = "If you claim the giveaway, the <strong>Lightning address</strong> you enter is used once, to send that payout, and is <strong>not stored</strong>: not in our database, not in our logs, and not in a shortened or masked form. To send the payout, it goes to the wallet service behind your address and to our Lightning payment provider (see below). We keep the statue, the amount, the payout status, the time and a salted hash of the address, so each address can be used only once per statue, as our Terms and Official Rules say. The hash isn't your address and is never shown; we use it only to check for repeat claims, and we delete these hashes when the giveaway ends. Lightning addresses stored from earlier claims were deleted on 2026-11-02."

# "Link your X" privacy text (PREVIEW, Noah 2026-11-01 11:04 AM ET via Matt). For Grant's (legal) review before go-live.
X_PRIVACY_HTML = (
    '\n      <li><strong>Link your X (optional).</strong> Linking is optional, and you can undo it at any time by unlinking. '
    'If you tap “Link your X”, you sign in on X’s own page. Signing in happens on X, and X’s own privacy policy applies there. '
    'X then tells us your X user ID and @handle. We store only those two and the date you linked them, with your passport. '
    'We ask X only for permission to read your profile (“users.read” and “tweet.read”, which X requires for reading your handle). '
    'We never post, like, follow or send messages for you, and we don’t keep your X login: the one-time access key X gives us is used once to read your handle, '
    'then we ask X to cancel it, and it is never saved.</li>'
    '\n      <li>An unfinished X sign-in expires after 10 minutes and is deleted within 20 minutes.</li>'
    '\n      <li>Once linked, your @handle is shown publicly with a blue ✓ “Verified” on your cards (including saved, shared and printed card images), your card pages, '
    'the verify page for your cards, the leaderboards and the Fellow Travelers page. “Verified” means you signed in with that X account; it is not X’s own verification badge. '
    'One X account can be linked to one passport at a time; signing in with it on another device moves your whole passport there. If your handle changes on X, tap “Refresh handle”.</li>'
    '\n      <li>To unlink, tap <strong>Unlink X</strong> on your <a href="/proof-of-walk/#xlink">passport</a>, or email us (below). '
    'Unlinking deletes your X user ID, handle and link date from our server, along with any unfinished sign-in. '
    'Your cards stay; the handle and ✓ are removed from them and from your card pages, the verify page and the leaderboards. '
    'Card images you already saved, shared or printed can’t be changed, and apps or sites where you shared a card link may show their own saved preview for a while. '
    'Backups are covered under <a href="#deleting">Deleting your data</a>. '
    'You can also remove our access in X: Settings › Security and account access › Apps and sessions › Connected apps.</li>'
    '\n      <li>Nicknames can’t start with “@” any more. An older “@” nickname is shown as “unverified” and is removed if the owner of that X account links it; '
    'the note telling you so is deleted after 30 days.</li>')


def privacy_page(data):
    c = data.get('config', {})
    title = 'Privacy – satoshistatues.com'
    desc = 'What satoshistatues.com stores for the Satoshi Passport leaderboard and analytics, and how to have it deleted.'
    canonical = SITE + '/privacy/'
    out = head(title, desc, canonical, OG_IMAGE, 1200, 630, 'Satoshi statues world map', '')
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › Privacy</div>
    <h1>Privacy</h1>
    <p class="sub">Short version: no accounts, no locations kept, IP addresses only as hashes for 7 days. If you choose to link X, we keep your X user ID and @handle.</p>
    <h2>Satoshi Passport and leaderboard</h2>
    <ul class="src" style="font-size:.95rem;color:#e6edf3">
      <li>Your passport cards are saved in your browser (localStorage).</li>
      <li>When you check in, your browser sends your location, a <strong>random device ID</strong> (created in your browser, not linked to your name) and the statue to our leaderboard server. The server only uses the location to check that you are within 150 m. <strong>Coordinates are not stored.</strong> We keep the statue, the time and a rough distance band such as “under 50 m”.</li>
      <li>If you add a <strong>nickname</strong>, it is shown publicly on the leaderboard and in the recent check-ins feed.</li>
      <li>The first time you use the leaderboard, cards already in your passport are added to it.</li>{pow_privacy_html(data)}
      <li><strong>IP addresses</strong> are only used for rate limiting. They are stored as a salted, per-day hash and <strong>deleted after 7 days</strong>.</li>
      <li>The server runs on Cloudflare Workers with a Cloudflare D1 database.</li>
    </ul>
    <h2>Analytics</h2>
    <p class="note">We use <a href="https://www.goatcounter.com/" target="_blank" rel="noopener noreferrer">GoatCounter</a> for privacy-friendly page counts without cookies. A successful check-in also sends an anonymous “Check-in &lt;statue&gt;” event, without any location.</p>
{fountain_privacy_html(data)}    <h2 id="deleting">Deleting your data</h2>
    <p class="note">Email <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a> with your leaderboard nickname (or the statue and rough time of your check-in) and we will delete your cards, nickname and your linked X account. Clearing your browser data removes your local passport and device ID.</p>
    <p class="note">Our database host keeps rolling backups for up to 30 days. Data you delete, including an unlinked X account, can remain in a backup until it rolls off, and we don’t restore deleted data to the site.</p>
    <p class="note" style="margin-top:8px;font-size:.85rem;color:#8b949e">Last updated {PRIVACY_UPDATED}.</p>
    {footer(data)}
  </main>
"""
    return out + TAIL


# ---------- Per-statue Open Graph images (1200x630, Pillow) ----------
OG_W, OG_H = 1200, 630
FONT_BOLD = os.path.join(ROOT, 'fonts', 'inter-800.woff')
FONT_REG = os.path.join(ROOT, 'fonts', 'inter-500.woff')


def og_path(s):
    # optional og_ver (e.g. "v2") gives the share image a new file name so X/Facebook recrawl it instead of reusing a cached card
    v = s.get('og_ver')
    return f"og/{s['page']}-{v}.jpg" if v else f"og/{s['page']}.jpg"


def og_image(s):
    """Branded share card; uses the statue photo only when it is a local file (never hot-linked images)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    import io
    bg = (13, 17, 23)
    im = Image.new('RGB', (OG_W, OG_H), bg)
    glow = Image.new('L', (OG_W, OG_H), 0)
    ImageDraw.Draw(glow).ellipse((-260, -300, 520, 380), fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    im = Image.composite(Image.new('RGB', (OG_W, OG_H), (247, 147, 26)), im, glow)
    text_w = 760  # without a photo the right side holds a large coin
    has_photo = False
    if s.get('img') and not s['img'].startswith('http') and os.path.exists(os.path.join(ROOT, s['img'])):
        pw = 520
        ph = Image.open(os.path.join(ROOT, s['img'])).convert('RGB')
        scale = max(pw / ph.width, OG_H / ph.height)
        ph = ph.resize((round(ph.width * scale), round(ph.height * scale)), Image.LANCZOS)
        fx = float(s.get('imgFocusX', 0.5))  # optional: horizontal centre of the subject (0-1) for the share-card crop
        left = min(max(0, round(ph.width * fx - pw / 2)), ph.width - pw)
        top = max(0, (ph.height - OG_H) // 3)
        ph = ph.crop((left, top, left + pw, top + OG_H))
        mask = Image.new('L', (pw, OG_H), 255)
        md = ImageDraw.Draw(mask)
        for x in range(120):
            md.line([(x, 0), (x, OG_H)], fill=round(255 * x / 120))
        im.paste(ph, (OG_W - pw, 0), mask)
        text_w = OG_W - pw - 110
        has_photo = True
    d = ImageDraw.Draw(im)
    fb = lambda n: ImageFont.truetype(FONT_BOLD, n)
    pin = Image.open(os.path.join(ROOT, 'brand', 'pin-512.png')).convert('RGBA')  # from tools/make_brand.py
    if not has_photo:
        big = pin.resize((round(pin.width * 300 / pin.height), 300), Image.LANCZOS)
        big.putalpha(big.getchannel('A').point(lambda a: a * 0.35))
        im.paste(big, (1000 - big.width // 2, 158), big)
    fr = lambda n: ImageFont.truetype(FONT_REG, n)
    d.rectangle((0, 0, OG_W, 8), fill=(247, 147, 26))
    mark = pin.resize((round(pin.width * 80 / pin.height), 80), Image.LANCZOS)
    im.paste(mark, (70, 60), mark)
    d.text((70 + mark.width + 16, 100), 'SATOSHI', font=fb(32), fill=(255, 255, 255), anchor='lm')
    d.text((70 + mark.width + 16 + d.textlength('SATOSHI ', font=fb(32)), 100), 'STATUES', font=fb(32), fill=(247, 147, 26), anchor='lm')

    def wrap(text, font, width, max_lines):
        words, lines, cur = text.split(), [], ''
        for w in words:
            t = (cur + ' ' + w).strip()
            if d.textlength(t, font=font) <= width or not cur:
                cur = t
            else:
                lines.append(cur); cur = w
        lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            while d.textlength(lines[-1] + '…', font=font) > width and ' ' in lines[-1]:
                lines[-1] = lines[-1].rsplit(' ', 1)[0]
            lines[-1] += '…'
        return lines

    limit = OG_H - 172
    for size in range(72, 43, -4):
        lines = wrap(s['label'], fb(size), text_w, 3)
        for pl in (2, 1):
            place = wrap(s['place'], fr(28), text_w, pl)
            hgt = len(lines) * round(size * 1.15) + 14 + 46 + len(place) * 36
            if 180 + hgt <= limit:
                break
        if 180 + hgt <= limit:
            break
    y = 180 + max(0, (limit - 180 - hgt) // 2)
    for l in lines:
        d.text((70, y), l, font=fb(size), fill=(230, 237, 243))
        y += round(size * 1.15)
    y += 14
    for l in wrap(f"{s['city']}, {s['country']}", fr(36), text_w, 1):
        d.text((70, y), l, font=fr(36), fill=(201, 209, 217)); y += 46
    for l in place:
        d.text((70, y), l, font=fr(28), fill=(139, 148, 158)); y += 36
    st = s.get('statusLabel') or s['status']
    col = {'Installed': (63, 185, 80), 'Restored': (247, 147, 26), 'Damaged': (240, 136, 62), 'Donated': (188, 140, 255), 'Planned': (88, 166, 255), 'Unveiled': (88, 166, 255)}.get(s['status'], (139, 148, 158))
    st = st if d.textlength(st, font=fb(24)) <= text_w - 40 else s['status']
    bw = d.textlength(st, font=fb(24)) + 32
    d.rounded_rectangle((70, OG_H - 150, 70 + bw, OG_H - 108), radius=8, outline=col, width=3)
    d.text((86, OG_H - 129), st, font=fb(24), fill=col, anchor='lm')
    d.text((70, OG_H - 62), 'satoshistatues.com', font=fb(34), fill=(247, 147, 26), anchor='ls')
    tag, tx = '· map, directions & Satoshi Passport', 70 + d.textlength('satoshistatues.com', font=fb(34)) + 18
    if tx + d.textlength(tag, font=fr(24)) <= 70 + text_w + 40:
        d.text((tx, OG_H - 64), tag, font=fr(24), fill=(139, 148, 158), anchor='ls')
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=84, optimize=True, progressive=True)
    return buf.getvalue()


def bin_outputs(data):
    return {og_path(s): og_image(s) for s in data['statues']}


# ---------- "Visiting" trip guide (optional per statue; see GUIDES.md) ----------
# statues.json → statue.visit:
#   getting_there  str   "## Getting there" section of the guide markdown
#   exact_spot     str   "## Exact spot"
#   photo_tip      str   "## Photo tip"
#   hours_access   str   "## Hours & access" (omit to reuse the statue's `access` + `accessSource`)
#   nearby         list  optional hand-curated notes for BTC Map places → [{"name", "url", "note"}]; the list itself comes
#                        from merchants.json (tools/fetch_merchants.py). Same place → note appended; others listed after.
#   merchants      false  hide the BTC Map list (statue not installed yet)
#   sources        list  "## Sources" lines "Label | URL" → [{"label", "url"}]
# Import with: python3 tools/import_guide.py <page>.md
# statue.pin_approx (bool, optional): coordinates are approximate → "Approximate location" on card + page
#   public_access / free  bool, optional; only emitted in JSON-LD when `sources` is set
#   updated        "YYYY-MM-DD" date the guide was written/updated (drives the sitemap lastmod)
GUIDE_TEXT_FIELDS = ('getting_there', 'exact_spot', 'photo_tip', 'hours_access')


def has_guide(s):
    v = s.get('visit') or {}
    return any((v.get(k) or '').strip() for k in GUIDE_TEXT_FIELDS) or bool(v.get('nearby'))


def paras(t):
    return ''.join(f'<p class="note">{e(p.strip())}</p>' for p in re.split(r'\n\s*\n', t.strip()) if p.strip())


def btcmap_map_url(s):
    return f"https://btcmap.org/map#16/{s['lat']}/{s['lng']}"


PLACE_TYPES = {  # BTC Map icon → readable type; unknown or ambiguous icons (e.g. 'home', 'business') show no type
    'restaurant': 'restaurant', 'lunch_dining': 'restaurant', 'local_pizza': 'pizzeria', 'local_cafe': 'café',
    'bakery_dining': 'bakery', 'local_bar': 'bar', 'sports_bar': 'pub', 'nightlife': 'bar', 'liquor': 'drinks shop',
    'hotel': 'hotel', 'bed': 'accommodation', 'storefront': 'shop', 'shopping_cart': 'shop', 'local_grocery_store': 'grocery',
    'checkroom': 'clothing', 'diamond': 'jeweller', 'content_cut': 'hair & beauty', 'spa': 'spa', 'local_florist': 'florist',
    'fitness_center': 'fitness', 'medical_services': 'health', 'local_pharmacy': 'pharmacy', 'school': 'school',
    'directions_car': 'car services', 'currency_exchange': 'exchange', 'local_gas_station': 'fuel', 'computer': 'computers',
    'phone_iphone': 'phones', 'sports_tennis': 'sports', 'pets': 'pets', 'museum': 'museum', 'beach_access': 'beach'}


def place_type(icon):
    return PLACE_TYPES.get(icon or '', '')


def fmt_km(k):
    return f'{round(k * 1000 / 10) * 10:.0f} m' if k < 1 else f'{k:.1f} km'


def merchants_html(s, data):
    """BTC Map list from merchants.json: up to 5 within 1 km; else nearest 3 within 5 km; else 'none listed yet'.
    Hand-curated visit.nearby entries for the same BTC Map place only contribute their note; others are listed after."""
    v = s.get('visit') or {}
    if v.get('merchants') is False:
        return ('<h3>Nearby places that accept bitcoin</h3><p class="note">Nearby places will be listed once the statue has a '
                'permanent site.</p>')
    m = (data.get('merchants') or {}).get('places', {}).get(s['page'])
    if not m:
        return ''
    curated = {re.sub(r'.*/merchant/', '', n['url']): n for n in v.get('nearby', []) if n.get('url')}
    near = m['nearest']
    if m['within_1km']:
        show, scope = [x for x in near if x['km'] <= 1][:5], ''
    elif m['within_5km']:
        show, scope = near[:3], '<p class="note">None within 1 km. The nearest within 5 km:</p>'
    else:
        show, scope = [], ''
    fetched = (data.get('merchants') or {}).get('fetched') or ''
    out = '<h3>Nearby places that accept bitcoin</h3>'
    if m['within_1km'] > 5:
        out += f'<p class="note merch-count"><strong>{m["within_1km"]} places</strong> within 1 km on BTC Map. The nearest 5:</p>'
    out += scope
    if show:
        items = []
        for x in show:
            bits = [b for b in (place_type(x.get('icon')), fmt_km(x['km'])) if b]
            ver = (f'last verified {datetime.date.fromisoformat(x["verified_at"]).strftime("%b %Y")}'
                   if x.get('verified_at') else 'not verified on BTC Map')
            cn = curated.pop(str(x['id']), {}).get('note')
            items.append(f'<li><a href="https://btcmap.org/merchant/{x["id"]}" target="_blank" rel="noopener noreferrer">{e(x["name"])}</a>'
                         f' – {e(", ".join(bits))} <span class="ver">· {ver}</span>{" – " + e(cn) if cn else ""}</li>')
        out += f'<ul class="visit-nearby">{"".join(items)}</ul>'
    else:
        out += (f'<p class="note">None listed within 5 km on BTC Map yet. <a href="{btcmap_map_url(s)}" target="_blank" rel="noopener noreferrer">See the BTC Map map</a> '
                f'or <a href="https://btcmap.org/add-location" target="_blank" rel="noopener noreferrer">add a place to BTC Map</a>.</p>')
    extra = [n for n in curated.values() if n.get('name')]
    if extra:
        out += '<p class="note">Also noted in our guide:</p><ul class="visit-nearby">' + ''.join(
            f'<li><a href="{e(n["url"])}" target="_blank" rel="noopener noreferrer">{e(n["name"])}</a>{" – " + e(n["note"]) if n.get("note") else ""}</li>'
            for n in extra) + '</ul>'
    out += (f'<p class="note" style="font-size:.8rem;color:#8b949e">From <a href="https://btcmap.org/" target="_blank" rel="noopener noreferrer">BTC Map</a>'
            f'{" (checked " + e(fetched) + ")" if fetched else ""}; straight-line distances from the map pin, ATMs and unnamed listings left out. Check before you go.</p>')
    return out


# ---------- Stay nearby (accepts bitcoin): lodging.json (tools/fetch_merchants.py) ----------
# Thresholds live in statues.json config.lodging: radius_mi (main radius, miles), fallback_km (labelled fallback),
# max_items (per statue). Distances are shown miles first, then km. Never hand-edit lodging.json.
STAY_TYPES = {'hotel': 'hotel', 'hostel': 'hostel', 'guest_house': 'guesthouse', 'motel': 'motel',
              'apartment': 'apartment', 'chalet': 'holiday home'}
MI = 1.609344


def lodging_cfg(data):
    c = (data.get('config') or {}).get('lodging') or {}
    return float(c.get('radius_mi', 5)), float(c.get('fallback_km', 25)), int(c.get('max_items', 5))


def fmt_mi(mi):
    return f'{mi:.1f} mi' if mi < 100 else f'{mi:.0f} mi'


def fmt_mi_km(k):
    return f'{fmt_mi(k / MI)} ({fmt_km(k)})'


def fmt_num(x):
    return f'{x:g}'


def statue_stays(s, data):
    """(rows, fallback?) for a statue: up to max_items within radius_mi, else up to max_items within fallback_km."""
    radius_mi, fallback_km, n = lodging_cfg(data)
    L = ((data.get('lodging') or {}).get('stays') or {}).get(s['page'])
    if not L:
        return [], False
    near = [x for x in L['nearest'] if x['km'] <= radius_mi * MI][:n]
    if near:
        return near, False
    return [x for x in L['nearest'] if x['km'] <= fallback_km][:n], True


def stay_link(x):
    return x.get('website') or f'https://btcmap.org/merchant/{x["id"]}'


def lodging_html(s, data):
    v = s.get('visit') or {}
    head = '<h3 id="stay">Stay nearby (accepts bitcoin)</h3>'
    if v.get('merchants') is False:
        return head + '<p class="note">Places to stay will be listed once the statue has a permanent site.</p>'
    if not (data.get('lodging') or {}).get('stays'):
        return ''
    radius_mi, fallback_km, n = lodging_cfg(data)
    L = data['lodging']['stays'].get(s['page']) or {}
    rows, fallback = statue_stays(s, data)
    rad = f'{fmt_num(radius_mi)} mi ({fmt_num(round(radius_mi * MI))} km)'
    if not rows:
        return (head + f'<p class="note">No bitcoin-accepting places to stay listed within {fmt_mi(fallback_km / MI)} ({fmt_num(fallback_km)} km) '
                f'on <a href="{btcmap_map_url(s)}" target="_blank" rel="noopener noreferrer">BTC Map</a> yet.</p>')
    out = head
    if fallback:
        out += (f'<p class="note">None within {rad}. Nearest bitcoin stay{"s" if len(rows) > 1 else ""}, '
                f'{fmt_mi_km(rows[0]["km"])} away:</p>')
    elif L.get('within_radius', 0) > n:
        out += f'<p class="note merch-count"><strong>{L["within_radius"]} places to stay</strong> within {rad} on BTC Map. The nearest {n}:</p>'
    items = []
    for x in rows:
        bits = [b for b in (STAY_TYPES.get(x.get('type'), ''), fmt_mi_km(x['km'])) if b]
        ver = (f'last verified {datetime.date.fromisoformat(x["verified_at"]).strftime("%b %Y")}'
               if x.get('verified_at') else 'not verified on BTC Map')
        bm = (f' · <a href="https://btcmap.org/merchant/{x["id"]}" target="_blank" rel="noopener noreferrer">BTC Map</a>'
              if x.get('website') else '')
        items.append(f'<li><a href="{e(stay_link(x))}" target="_blank" rel="noopener noreferrer">{e(x["name"])}</a>'
                     f' – {e(", ".join(bits))} <span class="ver">· {ver}{bm}</span></li>')
    out += f'<ul class="visit-nearby">{"".join(items)}</ul>'
    fetched = data['lodging'].get('fetched') or ''
    out += ('<p class="note stay-warn">Confirm with the place that it still takes bitcoin before you book.</p>'
            f'<p class="note" style="font-size:.8rem;color:#8b949e">Hotels, hostels, guesthouses and rentals from '
            f'<a href="https://btcmap.org/" target="_blank" rel="noopener noreferrer">BTC Map</a>'
            f'{" (checked " + e(fetched) + ")" if fetched else ""}; straight-line distances from the map pin. No paid or affiliate links.</p>')
    return out


def visit_html(s, data=None):
    if not has_guide(s):
        return ''
    v = s['visit']
    rows = []
    for key, label in (('getting_there', 'Getting there'), ('exact_spot', 'Exact spot'), ('photo_tip', 'Photo tip')):
        if (v.get(key) or '').strip():
            rows.append(f'<h3>{label}</h3>{paras(v[key])}')
    if (v.get('hours_access') or '').strip():
        rows.append(f'<h3>Hours &amp; access</h3>{paras(v["hours_access"])}')
    elif s.get('access'):
        src = (f' <a href="{e(s["accessSource"]["url"])}" target="_blank" rel="noopener noreferrer">Source: {e(s["accessSource"]["label"])}</a>'
               if s.get('accessSource') else '')
        rows.append(f'<h3>Hours &amp; access</h3><p class="note">{e(s["access"])}{src}</p>')
    mh = merchants_html(s, data or {})
    if mh:
        rows.append(mh)
    lh = lodging_html(s, data or {})
    if lh:
        rows.append(lh)
    srcs = (f'<h3>Guide sources</h3>{src_list(v["sources"])}' if v.get('sources') else '')
    upd = f'<p class="note" style="font-size:.8rem;color:#8b949e;margin-top:8px">Guide updated {e(v["updated"])}.</p>' if v.get('updated') else ''
    return f'<section class="visit" id="visiting" aria-labelledby="visiting-title"><h2 id="visiting-title">🧭 Visiting</h2>{"".join(rows)}{srcs}{upd}</section>'


VISIT_CSS = ('.visit{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:4px 16px 14px;margin:22px 0;scroll-margin-top:12px}'
             '.visit h2{margin:14px 0 6px}.visit h3{font-size:.95rem;color:#f7931a;margin:14px 0 4px}'
             '.visit .note+.note{margin-top:6px}.visit-nearby{padding-left:18px;font-size:.92rem}.visit-nearby li{margin:4px 0}'
             '.stay-warn{font-size:.85rem;color:#e3b341}'
             '.visit a{display:inline-block;padding:13px 0;margin:-13px 0}.visit li{margin:8px 0}.visit .ver{color:#8b949e;font-size:.85em}')


# ---------- Upcoming Bitcoin events nearby (events.json → statue pages) ----------
# events.json: {"events": [{name, start_date, end_date?, city, country, lat?, lng?, url, statue, source_url, verified}]}
# Only events confirmed on their official site. Past events are dropped at build time (end date < BUILD_DATE) and
# hidden again client-side (EVENTS_JS) so a page built earlier never shows a finished event between rebuilds.
# No upcoming events for a statue → no section at all. Format documented in EVENTS.md.
EVENT_RADIUS_KM = 300
_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def km_between(a_lat, a_lng, b_lat, b_lng):
    import math
    p = math.radians
    h = (math.sin(p(b_lat - a_lat) / 2) ** 2
         + math.cos(p(a_lat)) * math.cos(p(b_lat)) * math.sin(p(b_lng - a_lng) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def load_events(data):
    path = os.path.join(ROOT, 'events.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        evs = json.load(f).get('events', [])
    by_page = {s['page']: s for s in data['statues']}
    out = []
    for ev in evs:
        for k in ('name', 'start_date', 'city', 'country', 'url', 'statue', 'source_url', 'verified'):
            assert ev.get(k), f"events.json: {ev.get('name', '?')} missing {k}"
        for k in ('start_date', 'end_date', 'verified'):
            if ev.get(k):
                datetime.date.fromisoformat(ev[k])  # raises on a bad date
        ev = dict(ev, end_date=ev.get('end_date') or ev['start_date'])
        assert ev['end_date'] >= ev['start_date'], f"events.json: {ev['name']} ends before it starts"
        s = by_page.get(ev['statue'])
        assert s, f"events.json: {ev['name']} → unknown statue {ev['statue']}"
        ev['km'] = None
        if ev.get('lat') is not None and ev.get('lng') is not None:
            ev['km'] = km_between(ev['lat'], ev['lng'], s['lat'], s['lng'])
            assert ev['km'] <= EVENT_RADIUS_KM, f"events.json: {ev['name']} is {ev['km']:.0f} km from {s['page']} (> {EVENT_RADIUS_KM})"
        out.append(ev)
    return out


def fmt_range(a, b):
    a, b = datetime.date.fromisoformat(a), datetime.date.fromisoformat(b)
    if a == b:
        return f'{_MON[a.month - 1]} {a.day}, {a.year}'
    if (a.year, a.month) == (b.year, b.month):
        return f'{_MON[a.month - 1]} {a.day}–{b.day}, {a.year}'
    if a.year == b.year:
        return f'{_MON[a.month - 1]} {a.day} – {_MON[b.month - 1]} {b.day}, {a.year}'
    return f'{_MON[a.month - 1]} {a.day}, {a.year} – {_MON[b.month - 1]} {b.day}, {b.year}'


def statue_events(s, data):
    return sorted((ev for ev in data.get('events', []) if ev['statue'] == s['page'] and ev['end_date'] >= BUILD_DATE),
                  key=lambda ev: (ev['start_date'], ev['name']))


def event_ld(ev):
    obj = {'@context': 'https://schema.org', '@type': 'Event', 'name': ev['name'],
           'startDate': ev['start_date'], 'endDate': ev['end_date'], 'url': ev['url'],
           'eventAttendanceMode': 'https://schema.org/OfflineEventAttendanceMode',
           'location': {'@type': 'Place', 'name': ev['city'],
                        'address': {'@type': 'PostalAddress', 'addressLocality': ev['city'], 'addressCountry': ev['country']}}}
    return ld(obj)


def events_html(s, data):
    evs = statue_events(s, data)
    if not evs:
        return ''
    items = []
    for ev in evs:
        far = f' · about {round(ev["km"] / 10) * 10:.0f} km away' if ev.get('km') and ev['km'] >= 25 else ''
        items.append(f'<li data-end="{e(ev["end_date"])}"><a href="{e(ev["url"])}" target="_blank" rel="noopener noreferrer">{e(ev["name"])}</a>'
                     f'<span class="ev-meta">{e(fmt_range(ev["start_date"], ev["end_date"]))} · {e(ev["city"])}, {e(ev["country"])}{far}</span></li>')
    lds = ''.join(event_ld(ev) for ev in evs)
    return (f'<section class="events" id="events" aria-labelledby="events-title"><h2 id="events-title">📅 Upcoming Bitcoin events nearby</h2>'
            f'<ul class="ev-list">{"".join(items)}</ul>'
            f'<p class="note ev-fine">Dates are from each event’s official website. Check there for the latest details before you travel.</p></section>'
            f'{lds}{EVENTS_JS}')


# hide events whose end date has passed (visitor's local date), and the whole section if none are left
EVENTS_JS = ('<script>(function(){var d=new Date(),t=d.getFullYear()+"-"+("0"+(d.getMonth()+1)).slice(-2)+"-"+("0"+d.getDate()).slice(-2),'
             'x=document.getElementById("events");if(!x)return;x.querySelectorAll("li[data-end]").forEach(function(l){if(l.getAttribute("data-end")<t)l.remove()});'
             'if(!x.querySelector("li[data-end]"))x.remove()})();</script>')

EVENTS_CSS = ('.events{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:4px 16px 12px;margin:22px 0;scroll-margin-top:12px}'
              '.events h2{margin:14px 0 6px}.ev-list{list-style:none;padding:0;margin:0}'
              '.ev-list li{padding:10px 0;border-top:1px solid #21262d}.ev-list li:first-child{border-top:0}'
              '.ev-list a{font-weight:600;display:inline-block;padding:4px 0}.ev-meta{display:block;color:#8b949e;font-size:.9rem}'
              '.ev-fine{font-size:.82rem;color:#8b949e;margin-top:6px}')


def social_meta(url, title, desc, alt='Satoshi statues world map'):
    """Open Graph + Twitter tags for pages that don't use head() (embed, printable passport): site og-image.jpg."""
    img = OG_IMAGE
    return f'''<meta property="og:type" content="website" />
  <meta property="og:url" content="{url}" />
  <meta property="og:title" content="{e(title)}" />
  <meta property="og:description" content="{e(desc)}" />
  <meta property="og:image" content="{img}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta property="og:image:alt" content="{e(alt)}" />
  <meta property="og:site_name" content="Satoshi Statues" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{e(title)}" />
  <meta name="twitter:description" content="{e(desc)}" />
  <meta name="twitter:image" content="{img}" />
  <meta name="twitter:image:alt" content="{e(alt)}" />'''


# ---------- Embeddable map (/embed/) ----------
# Map-only page for iframes on blogs and meetup sites. Kept deliberately light: Leaflet + markercluster,
# no passport/check-in/giscus/share-card/font code. noindex, canonical → home, not in the sitemap.
# Optional ?statue=<page> focuses one statue and opens its popup.
EMBED_URL = SITE + '/embed/'
EMBED_TITLE = 'Map of Satoshi Nakamoto statues around the world'
EMBED_SNIPPET = (
    '<div style="width:100%;height:450px;max-width:100%;border-radius:12px;overflow:hidden">\n'
    f'  <iframe src="{EMBED_URL}" title="{EMBED_TITLE}" loading="lazy" allowfullscreen'
    ' style="display:block;width:100%;height:100%;border:0"></iframe>\n'
    '</div>')

EMBED_CSS = '''
html,body{margin:0;height:100%;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
#map{position:absolute;inset:0;background:#0d1117}
.btc-pin{display:flex;align-items:center;justify-content:center}
.m,.c{border-radius:50%;display:flex;align-items:center;justify-content:center;color:#0d1117;line-height:1;background:#f7931a}
.m{width:28px;height:28px;border:2px solid #fff;font-weight:700;font-size:15px;box-shadow:0 0 10px rgba(247,147,26,.6)}
.c{width:36px;height:36px;border:3px solid rgba(255,255,255,.9);box-shadow:0 0 0 5px rgba(247,147,26,.35),0 0 12px rgba(247,147,26,.7);font-weight:800;font-size:14px}
.leaflet-popup-content-wrapper{background:#161b22;color:#e6edf3;border-radius:10px}
.leaflet-popup-tip{background:#161b22}
.leaflet-popup-content{margin:12px 14px;font-size:.85rem;line-height:1.45}
.leaflet-popup-content h3{margin:0 0 3px;color:#f7931a;font-size:1rem}
.leaflet-container a.leaflet-popup-close-button{color:#8b949e}
.loc{color:#8b949e;margin-bottom:8px}
.st{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:600;background:#1a3a2a;color:#3fb950}
.st.Restored{background:#3a2e1a;color:#f7931a}.st.Planned,.st.Unveiled{background:#1a2a3a;color:#58a6ff}
.st.Removed{background:#3a1a1a;color:#f85149}.st.Damaged{background:#3a2a1a;color:#f0883e}.st.Donated{background:#2a1f3a;color:#bc8cff}
.go{display:inline-block;margin-top:10px;background:#f7931a;color:#0d1117!important;padding:6px 12px;border-radius:6px;font-weight:600;text-decoration:none}
.credit{position:absolute;top:10px;right:10px;z-index:1000;display:flex;align-items:center;gap:6px;background:rgba(13,17,23,.88);border:1px solid #30363d;color:#e6edf3;text-decoration:none;font-size:12px;font-weight:600;padding:5px 9px 5px 7px;border-radius:999px}
.credit:hover{border-color:#f7931a}.credit img{display:block}
.leaflet-control-attribution{background:rgba(13,17,23,.75)!important;color:#8b949e}.leaflet-control-attribution a{color:#8b949e}
.leaflet-bar a{background:#161b22;color:#e6edf3;border-bottom-color:#30363d}.leaflet-bar a:hover{background:#21262d}
'''.strip()

EMBED_JS = r'''
(function () {
  var esc = function (t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  var map = L.map('map', { zoomSnap: 0.25, minZoom: 0.5, scrollWheelZoom: false, worldCopyJump: true });
  map.once('focus', function () { map.scrollWheelZoom.enable(); });
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri', maxZoom: 16, detectRetina: true }).addTo(map);
  var icon = L.divIcon({ className: 'btc-pin', html: '<div class="m">₿</div>', iconSize: [44, 44], iconAnchor: [22, 22], popupAnchor: [0, -16] });
  var group = L.markerClusterGroup({ maxClusterRadius: 40, showCoverageOnHover: false, spiderfyOnMaxZoom: true,
    iconCreateFunction: function (c) { return L.divIcon({ className: 'btc-pin', html: '<div class="c">' + c.getChildCount() + '</div>', iconSize: [44, 44], iconAnchor: [22, 22] }); } }).addTo(map);
  var bySlug = {}, all = [];
  STATUES.forEach(function (s) {
    var html = '<h3>' + esc(s.n) + '</h3><div class="loc">' + esc(s.loc) + (s.a ? ' · approximate pin' : '') + '</div>' +
      '<span class="st ' + esc(s.s) + '">' + esc(s.sl || s.s) + '</span><br>' +
      '<a class="go" href="' + SITE + '/' + encodeURIComponent(s.p) + '/" target="_blank" rel="noopener">Photos &amp; details ↗</a>';
    var m = L.marker([s.lat, s.lng], { icon: icon, title: s.n, alt: s.n }).bindPopup(html, { maxWidth: 260, autoPanPaddingTopLeft: [14, 56], autoPanPaddingBottomRight: [14, 30] });
    group.addLayer(m); bySlug[s.p] = m; all.push(m);
  });
  var small = Math.min(innerWidth, innerHeight) < 500;
  map.fitBounds(L.featureGroup(all).getBounds(), { padding: small ? [34, 34] : [48, 48], animate: false });
  var want = (location.search.match(/[?&]statue=([a-z0-9-]+)/) || [])[1];
  if (want && bySlug[want]) group.zoomToShowLayer(bySlug[want], function () { bySlug[want].openPopup(); });
})();
'''.strip()


def embed_page(data):
    pts = []
    for s in data['statues']:
        p = {'n': s['label'], 'loc': ', '.join(x for x in (s.get('place'), s['city'], s['country']) if x),
             'lat': s['lat'], 'lng': s['lng'], 's': s['status'], 'p': s['page']}
        if s.get('statusLabel'):
            p['sl'] = s['statusLabel']
        if s.get('pin_approx'):
            p['a'] = 1
        pts.append(p)
    pts_js = json.dumps(pts, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Satoshi Nakamoto Statues: embeddable map</title>
  <meta name="description" content="Interactive map of Satoshi Nakamoto statues around the world, for embedding on other websites." />
  <meta name="robots" content="noindex, follow" />
  <link rel="canonical" href="{SITE}/" />
  {social_meta(EMBED_URL, 'Satoshi Nakamoto Statues: embeddable map', 'Interactive map of Satoshi Nakamoto statues around the world, for embedding on other websites.')}
  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  <link rel="preconnect" href="https://server.arcgisonline.com" crossorigin>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
  <style>{EMBED_CSS}</style>
</head>
<body>
  <div id="map" role="region" aria-label="{EMBED_TITLE}"></div>
  <a class="credit" href="{SITE}/" target="_blank" rel="noopener"><img src="/brand/pin.svg" width="13" height="18" alt="" />satoshistatues.com</a>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <script>var SITE = "{SITE}", STATUES = {pts_js};
{EMBED_JS}</script>
  <script data-goatcounter="https://satoshistatues.goatcounter.com/count" data-goatcounter-settings='{{"path": "/embed/", "allow_frame": true}}' async src="//gc.zgo.at/count.js"></script>
</body>
</html>
'''


def embed_box_html():
    snippet = e(EMBED_SNIPPET)
    return f'''        <details class="embed-box" id="embed-box">
          <summary>🧩 Embed this map</summary>
          <p class="embed-help">Add this map to your blog or meetup site. Copy the code and paste it into an HTML block.</p>
          <label class="sr-only" for="embed-code">Embed code</label>
          <textarea id="embed-code" class="embed-code" readonly rows="6" spellcheck="false" onfocus="this.select()">{snippet}</textarea>
          <div class="embed-actions">
            <button class="tip-btn tip-primary" type="button" id="embed-copy" onclick="copyEmbed()">Copy code</button>
            <a class="tip-btn" href="/embed/" target="_blank" rel="noopener">Open preview ↗</a>
          </div>
          <div class="embed-preview" id="embed-preview" aria-hidden="true"></div>
        </details>'''


# ---------- /passport/print/ → /proof-of-walk/ (redirect page) ----------
# The printable stamp passport (02ed73d) was retired (Noah 2026-10-31 4:52 PM ET): every GPS check-in is now a full
# Proof of Walk card, so the old URL sends people to /proof-of-walk/. GitHub Pages has no server redirects: same
# pattern as the share redirects (meta refresh + location.replace + canonical, noindex), not in the sitemap.
# Card print files (pow-card.js "Get a print") are separate and stay.
PASSPORT_PRINT_TARGET = SITE + '/proof-of-walk/'


def passport_print_redirect_page():
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Proof of Walk · Satoshi Statues</title>
  <meta name="robots" content="noindex, follow" />
  <link rel="canonical" href="{PASSPORT_PRINT_TARGET}" />
  <meta http-equiv="refresh" content="0; url={PASSPORT_PRINT_TARGET}" />
  <script>location.replace("{PASSPORT_PRINT_TARGET}");</script>
</head>
<body>
  <p>Your Satoshi Passport is now a set of Proof of Walk cards. <a href="{PASSPORT_PRINT_TARGET}">Go to Proof of Walk →</a></p>
</body>
</html>
'''


def page_lastmod(s):
    u = ((s.get('visit') or {}).get('updated') or '').strip()
    return max(BUILD_DATE, u) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', u) else BUILD_DATE


def sitemap(data):
    urls = [(SITE + p, BUILD_DATE) for p in ('/', '/21-nodes/', '/leaderboard/', '/privacy/') + (('/terms/',) if fountain_on(data) else ()) + (('/rules/',) if rules_on(data) else ()) + (('/proof-of-walk/', '/proof-of-walk/fellow-travelers/', '/proof-of-walk/cards/') if pow_cfg(data) and not pow_cfg(data).get('preview') else ())] + [(page_url(s), page_lastmod(s)) for s in data['statues']]
    body = ''.join(f'  <url><loc>{u}</loc><lastmod>{m}</lastmod></url>\n' for u, m in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n'


ROBOTS = f'User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n'


def replace_block(text, name, content, comment=('<!-- ', ' -->')):
    # Replace everything between the BEGIN and END marker lines (markers keep their own line + indent).
    a, _ = comment
    begin_re = re.escape(a + f'BUILD:{name}:BEGIN')
    end_re = re.escape(a + f'BUILD:{name}:END')
    pat = re.compile(rf'([ \t]*)({begin_re}[^\n]*)\n.*?[ \t]*({end_re}[^\n]*)', re.S)
    if not pat.search(text):
        raise SystemExit(f'marker {name} not found in index.html')
    return pat.sub(lambda m: f'{m.group(1)}{m.group(2)}\n{content.rstrip()}\n{m.group(1)}{m.group(3)}', text, count=1)


# "📍 Nearby Statues" only suggests statues standing at a known spot (see GUIDES.md). Derived, never hand-set:
# not eligible when status is one of NOT_AT_SPOT_STATUSES or the alert type is one of NOT_AT_SPOT_ALERTS.
NOT_AT_SPOT_STATUSES = ('Planned', 'Donated', 'Removed')
NOT_AT_SPOT_ALERTS = ('not_installed', 'location_unknown', 'removed')


def nearby_eligible(s):
    return s['status'] not in NOT_AT_SPOT_STATUSES and ((s.get('alert') or {}).get('type') or '') not in NOT_AT_SPOT_ALERTS


def map_stays(data):
    """Places to stay shown on statue pages, for the home map's toggleable 'Stays' layer (deduplicated by BTC Map id).
    Never stampable: they are not statues and are not in the statues array, passport or leaderboard."""
    seen, out = set(), []
    for s in data['statues']:
        if (s.get('visit') or {}).get('merchants') is False:
            continue
        for x in statue_stays(s, data)[0]:
            if x['id'] in seen or x.get('lat') is None:
                continue
            seen.add(x['id'])
            out.append({'n': x['name'], 't': STAY_TYPES.get(x.get('type'), ''), 'lat': x['lat'], 'lng': x['lng'],
                        'u': stay_link(x), 'b': x['id'], 'v': x.get('verified_at') or '', 'p': s['page'],
                        's': s['name'], 'd': fmt_mi_km(x['km'])})
    return out


def build_index(data, text):
    statues_js = [{k: v for k, v in s.items() if k not in ('slug', 'sources', 'accessSource', 'label', 'visit', 'story')} for s in data['statues']]
    for s, src in zip(statues_js, data['statues']):
        s['label'] = src['label']
        if has_guide(src):
            s['guide'] = True
        s['nearby_eligible'] = nearby_eligible(src)
        if fountain_on(data, src):
            s['giveaway'] = True
    js = '    const statues = ' + json.dumps(statues_js, ensure_ascii=False, indent=2).replace('\n', '\n    ') + ';'
    text = replace_block(text, 'STATUES', js, comment=('// ', ''))
    text = replace_block(text, 'STAYS', '    const stays = ' + json.dumps(map_stays(data), ensure_ascii=False) + ';', comment=('// ', ''))
    ldhtml, _ = home_ld(data)
    text = replace_block(text, 'JSONLD', '  ' + ldhtml)
    links = '        <ul>\n' + ''.join(
        f'          <li><a href="/{s["page"]}/">{e(s["label"])}</a></li>\n'
        for s in sorted(data['statues'], key=lambda s: -sort_year(s['year']))) + '          <li><a href="/21-nodes/">21 Nodes tracker</a></li>\n          <li><a href="/leaderboard/">🏆 Leaderboard</a></li>\n          <li><a href="/privacy/">Privacy</a></li>\n        </ul>'
    text = replace_block(text, 'LINKS', links)
    text = replace_block(text, 'SIGNUP', '        ' + signup_html(data, 'home'))
    text = replace_block(text, 'EMBED', embed_box_html())
    text = replace_block(text, 'SUPPORT', '        <p class="support-p">' + support_line() + '</p>')
    text = replace_block(text, 'HEADLINKS', '  ' + FEED_LINK + '\n  <style>' + ALERT_CSS + CARD_GRID_CSS + '</style>' + ('\n  ' + api_script() if api_script() else '') + '\n  ' + ci_what_script(data) + '\n  ' + checkin_script() + giveaway_home_head(data))
    return text

# ---------- Temporary hidden test statue (fountain.json "test_page") ----------
# A private page for one live end-to-end giveaway test. Not a statue: not in statues.json, so it is not on the map,
# sitemap, feed, passport, leaderboard, statue lists or embeds; noindex/nofollow; reachable only by its direct URL.
# The test spot's location lives only in the Worker's D1 (fountain_test_statue); the page never has it, so the
# distance check is done by the server alone. Check-ins here are not recorded and do not stamp the passport.
# Remove: delete "test_page" from fountain.json, `git rm -r <slug>/`, rebuild. See FOUNTAIN.md.
def test_page_cfg(data):
    t = (data.get('fountain') or {}).get('test_page') or {}
    slug = t.get('slug') if isinstance(t, dict) else None
    if not fountain_on(data) or not slug:
        return None
    assert re.fullmatch(r'test-[a-z0-9-]+', slug), 'test_page.slug must start with test-'
    assert slug not in [o['page'] for o in data['statues']], 'test_page.slug clashes with a statue page'
    return {'slug': slug, 'name': t.get('name') or 'Test statue', 'radius_m': int(t.get('radius_m') or 150)}


TEST_PAGE_CSS = ('.tp{max-width:640px;margin:0 auto;padding:16px}.tp h1{font-size:1.4rem;margin:8px 0}'
                 '.tp .tp-note{background:#161b22;border:1px solid #30363d;border-left:3px solid #8b949e;border-radius:10px;padding:10px 12px;font-size:.88rem;color:#c9d1d9;line-height:1.45}'
                 '.tp .tp-ci{margin:14px 0}.tp .tp-ci button{width:100%;min-height:48px;font:inherit;font-weight:700;cursor:pointer;border:0}'
                 '.tp .checkin-msg{margin-top:8px;background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:9px 11px;font-size:.9rem}'
                 '.tp .checkin-msg.ok{border-color:#3fb950;color:#3fb950}.tp .checkin-msg.warn{border-color:#f0883e}'
                 '.tp .checkin-msg[hidden]{display:none}.tp .geo-diag{font-size:.75rem;color:#8b949e;margin-top:6px}')

TEST_PAGE_JS = """<script>(function () {
  var box = document.querySelector('[data-tp-checkin]'); if (!box) return;
  var btn = box.querySelector('button'), out = box.querySelector('.checkin-msg'), slug = box.getAttribute('data-slug'), IDLE = btn.textContent;
  function show(cls, html) { out.className = 'checkin-msg ' + cls; out.innerHTML = html; out.hidden = false; }
  if (!navigator.geolocation || !window.SS_API) { show('warn', 'Location or the check-in server isn’t available in this browser.'); btn.disabled = true; return; }
  btn.addEventListener('click', function () {
    btn.disabled = true; btn.textContent = '📍 Finding your location…'; out.hidden = true;
    navigator.geolocation.getCurrentPosition(function (pos) {
      btn.textContent = 'Checking…';
      var c = pos.coords;
      // window.lbPost is wrapped by fountain.js, which stores the claim token from a passed check-in.
      window.lbPost('/api/checkin', { device_id: window.lbDevice(), slug: slug, lat: c.latitude, lng: c.longitude, accuracy: c.accuracy }).then(function (r) {
        btn.disabled = false; btn.textContent = IDLE;
        var j = r.j || {};
        if (j.ok && j.fountain && j.fountain.state === 'drawn') show('ok', '✅ Checked in at the test spot. Your amount is below.');
        else if (j.ok && j.fountain) show('ok', '✅ Checked in at the test spot.');
        else if (j.ok) show('warn', 'Checked in, but the giveaway isn’t running here right now.');
        else show('warn', escHtml(j.message || 'The check-in wasn’t accepted.'));
      }).catch(function () { btn.disabled = false; btn.textContent = IDLE; show('warn', 'Couldn’t reach the check-in server. Try again.'); });
    }, function (err) {
      btn.disabled = false; btn.textContent = IDLE;
      geoErrorHtml(err).then(function (h) { show('warn', h); });
    }, GEO_OPTS);
  });
})();</script>"""


def test_fountain_box(t, data):
    """The same giveaway box as the real statues (amount copy, rules link, odometer/Lucky 210 success screen and share
    prompt from fountain.js), without the tip section (tips aren't offered here). The share prompt links to the home
    page, not to this hidden page."""
    api = data['fountain'].get('api') or LB_API
    return (f'<style>{FOUNTAIN_CSS}{SHARE_CSS}</style><section class="fountain" id="giveaway" data-ss-fountain data-slug="{e(t["slug"])}" data-name="{e(t["name"])}" '
            f'data-share-name="the Satoshi Statues test spot" data-url="{SITE}/" data-api="{e(api)}" data-radius="{int(t["radius_m"])}" hidden>'
            f'<h2>⛲ Satoshi Fountain (test)</h2>'
            f'<p>A private test of the Lightning giveaway, while the test budget lasts.</p>'
            f'<div class="f-stats"><div class="f-stat"><b data-f-left>–</b>test sats left</div></div>'
            f'<p class="f-fine">Check in at the test spot to get <span data-f-howmuch>{e(payout_phrase(data))}</span> sent to a Lightning address. '
            f'One per Lightning address. 18+ only. The test can stop at any time. {rules_links(data)}</p>'
            f'<div data-f-claim></div>{WALLETS_LINE}'
            f'<h3>Recent activity</h3><div class="f-recent" data-f-recent></div>'
            f'</section>')


def test_statue_page(t, data):
    import hashlib
    with open(os.path.join(ROOT, 'fountain.js'), 'rb') as f:
        fv = hashlib.sha256(f.read()).hexdigest()[:10]
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <title>{e(t["name"])} · Satoshi Statues</title>
  <meta name="robots" content="noindex, nofollow, noarchive" />
  <meta name="googlebot" content="noindex, nofollow" />
  <meta name="referrer" content="no-referrer" />
  <meta name="theme-color" content="#0d1117" />
  {ICON_LINKS}
  <style>{CSS}{TEST_PAGE_CSS}</style>
  {api_script()}
</head>
<body>
  <header class="top">
    <a class="brand" href="/" title="Satoshi Nakamoto Statues: map home">{LOGO_IMG}<span class="tagline">Every Satoshi statue on Earth</span></a>
  </header>
  <main class="tp">
    <h1>🧪 {e(t["name"])}</h1>
    <p class="tp-note">Private test page for the giveaway. This isn’t a real statue: it isn’t on the map, and checking in here doesn’t add a card to your passport or appear on the leaderboard.</p>
    <div class="tp-ci" data-tp-checkin data-slug="{e(t["slug"])}">
      <button class="btn primary" type="button">📍 Check in at the test spot</button>
      <div class="checkin-msg" aria-live="polite" hidden></div>
    </div>
    {test_fountain_box(t, data)}
  </main>
  {share_script()}
  {checkin_script()}
  <script src="/fountain.js?v={fv}"></script>
  {TEST_PAGE_JS}
</body>
</html>
'''


# ---------- /passport/ → home page passport (redirect page) ----------
# Nothing links to /passport/; it used to 404. GitHub Pages has no server redirects, so this is a meta refresh +
# location.replace page. /#passport opens the passport modal on the home page (see openFromLocation in index.html).
PASSPORT_TARGET = SITE + '/#passport'


def passport_redirect_page():
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Satoshi Passport · Satoshi Statues</title>
  <meta name="robots" content="noindex, follow" />
  <link rel="canonical" href="{SITE}/" />
  <meta http-equiv="refresh" content="0; url={PASSPORT_TARGET}" />
  <script>location.replace("{PASSPORT_TARGET}");</script>
</head>
<body>
  <p>The Satoshi Passport is on the <a href="{PASSPORT_TARGET}">home page</a>.</p>
</body>
</html>
'''


# ---------- /fellow-travelers/ → /proof-of-walk/fellow-travelers/ (redirect page) ----------
# Short link for the Grand High Order roll. Same static pattern as /passport/: meta refresh + location.replace,
# canonical → target, noindex, not in the sitemap. Built only when Proof of Walk is on (same as the roll page).
FELLOW_TARGET = SITE + '/proof-of-walk/fellow-travelers/'


def fellow_travelers_redirect_page():
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Fellow Travelers · Satoshi Statues</title>
  <meta name="robots" content="noindex, follow" />
  <link rel="canonical" href="{FELLOW_TARGET}" />
  <meta http-equiv="refresh" content="0; url={FELLOW_TARGET}" />
  <script>location.replace("{FELLOW_TARGET}");</script>
</head>
<body>
  <p>The Fellow Travelers roll has moved to <a href="{FELLOW_TARGET}">Proof of Walk</a>.</p>
</body>
</html>
'''


# ---------- "Tip the map" box on statue pages ----------
# Statue pages reuse the home page's tip box verbatim (same Bitcoin address, QR image and buttons), taken from the
# <section class="tip-box"> in index.html, so both always point at the same tip wallet. Tips are never offered inside
# the giveaway widget (legal: keep tipping out of the claim flow); the box sits at the bottom of the page, and the
# home header's '₿ Tip' button is added to the statue page's top nav (it scrolls to the box).
HOME_TIP = {'html': '', 'button': ''}
TIP_CSS = ('.tip-box{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:10px;padding:12px 14px;'
           'margin:16px 0;font-size:.82rem;color:#8b949e;line-height:1.45;scroll-margin-top:12px;transition:box-shadow .3s}'
           '.tip-box .tip-title{font-weight:700;color:#e6edf3;font-size:.95rem;margin:0 0 6px}'
           '.tip-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}'
           '.tip-btn{background:#21262d;border:1px solid #30363d;color:#e6edf3;padding:5px 10px;border-radius:6px;font-size:.78rem;'
           'cursor:pointer;text-decoration:none;font-family:inherit;min-height:44px;display:inline-flex;align-items:center;justify-content:center}'
           '.tip-btn:hover{border-color:#f7931a}.tip-primary{background:#f7931a;border-color:#f7931a;color:#0d1117;font-weight:600}'
           '.tip-qr{display:none;margin-top:8px;border-radius:6px;background:#fff}.tip-qr.show{display:block}'
           '.btc-address{display:inline-block;margin-top:6px;background:#0d1117;border:1px solid #30363d;color:#f7931a;padding:6px 10px;'
           'border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:.78rem;word-break:break-all;'
           'cursor:pointer;user-select:all}.btc-address:hover{border-color:#f7931a}'
           '.tip-box.flash{box-shadow:0 0 0 2px #f7931a}.top nav .tip-toggle{padding:8px 14px;font-size:.85rem}')


def load_home_tip(idx):
    m = re.search(r'<section class="tip-box" id="tip-box".*?</section>', idx, re.S)
    if not m:
        raise SystemExit('tip-box section not found in index.html')
    sec = m.group(0)
    addr = re.search(r'<div class="btc-address"[^>]*>\s*([a-zA-Z0-9]+)\s*</div>', sec)
    if not addr or f'bitcoin:{addr.group(1)}' not in sec:
        raise SystemExit('tip-box address not found in index.html')
    # The home header's '₿ Tip' button (same markup/classes); on statue pages it sits in the top nav and jumps to the box.
    btn = re.search(r'<button class="tip-btn tip-primary tip-toggle" id="tip-toggle"[^>]*>.*?</button>', idx, re.S)
    if not btn:
        raise SystemExit('tip-toggle button not found in index.html')
    HOME_TIP['button'] = btn.group(0)
    sec = sec.replace('src="btc-tip-qr.png"', 'src="/btc-tip-qr.png"')  # statue pages live one folder down
    a = json.dumps(addr.group(1))
    js = ('<script>function copyTipAddress(){var a=' + a + ',b=document.getElementById("tip-copy");'
          'var done=function(){b.textContent="Copied ✓";setTimeout(function(){b.textContent="Copy"},2000)};'
          'if(navigator.clipboard)navigator.clipboard.writeText(a).then(done,function(){prompt("Copy this address:",a)});'
          'else prompt("Copy this address:",a)}'
          'function showTip(){var b=document.getElementById("tip-box");if(!b)return;b.scrollIntoView({behavior:"smooth",block:"center"});'
          'b.classList.add("flash");setTimeout(function(){b.classList.remove("flash")},1600)}'
          '(function(){var el=document.querySelector(".tip-box .btc-address");if(el)el.addEventListener("click",function(){'
          'var r=document.createRange();r.selectNodeContents(this);var s=window.getSelection();s.removeAllRanges();s.addRange(r)})})();</script>')
    HOME_TIP['html'] = f'<style>{TIP_CSS}</style>\n    {sec}\n    {js}'


def outputs(data):
    with open(os.path.join(ROOT, 'index.html'), encoding='utf-8') as f:
        idx = f.read()
    load_home_tip(idx)
    files = {'index.html': build_index(data, idx), 'sitemap.xml': sitemap(data), 'robots.txt': ROBOTS,
             'feed.xml': feed_xml(data),
             '.nojekyll': '',
             '21-nodes/index.html': nodes_page(data),
             'leaderboard/index.html': leaderboard_page(data),
             'privacy/index.html': privacy_page(data),
             'embed/index.html': embed_page(data),
             'passport/print/index.html': passport_print_redirect_page(),
             'passport/index.html': passport_redirect_page()}
    pages = [s['page'] for s in data['statues']]
    assert len(set(pages)) == len(pages), 'duplicate page slugs'
    if nostr_json(data):
        files['.well-known/nostr.json'] = nostr_json(data)
    if fountain_on(data):
        files['terms/index.html'] = terms_page(data)
    tp = test_page_cfg(data)
    if tp:
        files[f"{tp['slug']}/index.html"] = test_statue_page(tp, data)
    if rules_on(data):
        files['rules/index.html'] = rules_page(data)
    if pow_cfg(data):
        files['proof-of-walk/index.html'] = pow_page(data)
        files['proof-of-walk/fellow-travelers/index.html'] = pow_roll_page(data)
        files['fellow-travelers/index.html'] = fellow_travelers_redirect_page()
        files['proof-of-walk/cards/index.html'] = pow_cards_page(data)
        files['proof-of-walk/card-data.js'] = card_data_js(data)
        files.update(card_share_pages(data))
        files.update(old_share_redirects(data))
        files['v/index.html'] = verify_page(data)
    for s in data['statues']:
        files[f"{s['page']}/index.html"] = statue_page(s, data)
    return files


def main():
    check = '--check' in sys.argv
    if '--refresh-checkins' in sys.argv:
        refresh_checkins()
    data = load()
    data['events'] = load_events(data)
    global POW_CARD_JS_URL
    POW_CARD_JS_URL = pow_card_js_url(data) if os.path.exists(os.path.join(ROOT, 'pow-card.js')) else ''
    if '--worker' in sys.argv:
        write_worker_statues(data)
        write_worker_cardshare(data)
        return
    stale = []
    for rel, content in ({} if '--no-bin' in sys.argv else bin_outputs(data)).items():
        path = os.path.join(ROOT, rel)
        old = open(path, 'rb').read() if os.path.exists(path) else None
        if old != content:
            if check:
                stale.append(rel)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(content)
            print('wrote', rel)
    for rel, content in outputs(data).items():
        path = os.path.join(ROOT, rel)
        old = open(path, encoding='utf-8').read() if os.path.exists(path) else None
        # ignore build-date-only differences in --check mode
        norm = lambda t: re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', t or '')
        if check:
            if norm(old) != norm(content):
                stale.append(rel)
            continue
        if old != content:
            os.makedirs(os.path.dirname(path) or ROOT, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print('wrote', rel)
    if check:
        if stale:
            print('stale (run python3 build.py):', ', '.join(stale))
            sys.exit(1)
        print('up to date')


if __name__ == '__main__':
    main()
