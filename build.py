#!/usr/bin/env python3
"""Build script for satoshistatues.com.

statues.json is the single source of truth. This script:
  * injects the statue array, JSON-LD and the crawlable link list into index.html
  * generates one static page per statue (/<page>/index.html)
  * generates /21-nodes/index.html, sitemap.xml, robots.txt and feed.xml (Atom)
  * renders the 'next statue' alert box from config.newsletter_action_url (Buttondown embed URL)

Run `python3 build.py` after editing statues.json and commit the output.
`python3 build.py --check` exits non-zero if the committed output is stale.
GitHub Pages serves the committed files as-is; there is no runtime build step.
"""
import datetime
import html
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://www.satoshistatues.com'
REPO = 'noahoskwarek-bot/satoshistatues.com'
GISCUS = dict(repoId='R_kgDOT4kDjw', category='Announcements', categoryId='DIC_kwDOT4kDj84DJD3w')
COUNTRY_ISO = {'Hungary': 'HU', 'Switzerland': 'CH', 'El Salvador': 'SV', 'Japan': 'JP', 'Vietnam': 'VN',
               'USA': 'US', 'Italy': 'IT', 'China': 'HK', 'Slovenia': 'SI', 'Austria': 'AT'}
CHECKABLE = ('Installed', 'Restored', 'Damaged')  # Damaged = still in place (counts as installed and can be stamped)
BUILD_DATE = os.environ.get('BUILD_DATE') or datetime.date.today().isoformat()
LB_API = ''  # set from statues.json config.leaderboard_api in load()

e = lambda t: html.escape(str(t), quote=True)


def load():
    with open(os.path.join(ROOT, 'statues.json'), encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('config', {})
    global LB_API
    LB_API = data['config'].get('leaderboard_api', '')
    for s in data['statues']:
        s['slug'] = slug_of(s)
    cpath = os.path.join(ROOT, 'checkins.json')
    counts = {}
    if os.path.exists(cpath):
        with open(cpath, encoding='utf-8') as f:
            counts = json.load(f).get('counts', {})
    for s in data['statues']:
        n = counts.get(s['slug'], 0)
        s['checkins'] = n if isinstance(n, int) and n > 0 else 0
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
    st = {s['slug']: {'name': s['name'], 'page': s['page'], 'lat': s['lat'], 'lng': s['lng']}
          for s in data['statues'] if s['status'] in CHECKABLE}
    path = os.path.join(WORKER_DIR, 'src', 'statues.gen.js')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('// Generated by satoshistatues.com build.py --worker from statues.json. Do not edit.\n'
                'export const STATUES = ' + json.dumps(st, ensure_ascii=False, indent=2) + ';\n')
    print(f'wrote {path} ({len(st)} stampable statues)')


def count_text(n):
    return f'👣 {n} {"person has" if n == 1 else "people have"} checked in here'


def checkin_count_html(s):
    # Baked from checkins.json; LIVE_COUNT_JS refreshes it from the leaderboard API (/api/counts).
    n = s.get('checkins', 0)
    return (f'<p class="checkin-count" data-count-slug="{e(s["slug"])}" data-base="{n}"{"" if n else " hidden"}>'
            f'{count_text(n) if n else ""}</p>')


def api_script():
    return f'<script>window.SS_API = {json.dumps(LB_API)};</script>' if LB_API else ''


LIVE_COUNT_JS = """<script>(function(){var A=window.SS_API;if(!A||!window.fetch)return;fetch(A+"/api/counts").then(function(r){return r.json()}).then(function(j){if(!j||!j.ok)return;
document.querySelectorAll("[data-count-slug]").forEach(function(el){var n=Math.max(j.counts[el.getAttribute("data-count-slug")]||0,+el.getAttribute("data-base")||0);
if(n>0){el.textContent="\\uD83D\\uDC63 "+n+(n===1?" person has":" people have")+" checked in here";el.hidden=false}});}).catch(function(){});})();</script>"""


def footer(data, extra=''):
    nostr = f' · <a href="{e(nostr_url(data))}" rel="me">Nostr</a>' if nostr_url(data) else ''
    return (f'<footer class="site"><a href="/">satoshistatues.com</a> · <a href="/21-nodes/">21 Nodes tracker</a> · '
            f'<a href="/leaderboard/">Leaderboard</a> · <a href="/feed.xml">Feed</a>{nostr}{extra} · <a href="/privacy/">Privacy</a></footer>')


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
    for fmt in ('%d %b %Y', '%b %Y'):
        try:
            return datetime.datetime.strptime(s['unveiled'], fmt)
        except (ValueError, KeyError):
            pass
    return datetime.datetime(sort_year(s['year']), 1, 1)


def img_abs(s):
    """Absolute image URL for OG/JSON-LD. Remote (hot-linked) photos fall back to the site card."""
    if s.get('img') and not s['img'].startswith('http'):
        return f"{SITE}/{s['img']}", s.get('imgW'), s.get('imgH'), True
    return f'{SITE}/og-image.jpg', 1200, 630, False


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
    if s['slug'] in ('budapest', 'lugano'):
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
    planned = [s for s in st if s['status'] not in CHECKABLE]
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
                 f"satoshistatues.com tracks {len(st)} Satoshi Nakamoto statues and Bitcoin monuments: {len(installed)} installed and "
                 f"{len(planned)} planned: " + ', '.join(f"Valentina Picozzi’s {s['city']} statue, unveiled {s['unveiled']} and awaiting a permanent public site" for s in planned) + ". "
                 f"{len(s21)} of the 21 statues in Valentina Picozzi’s “21 Nodes” series are installed so far."}},
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
.top .brand{color:#f7931a;font-weight:700;font-size:1.1rem;text-decoration:none}
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
.b-installed{background:#1a3a2a;color:#3fb950}.b-restored{background:#3a2e1a;color:#f7931a}.b-planned{background:#1a2a3a;color:#58a6ff}.b-damaged{background:#3a2a1a;color:#f0883e}
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
footer.site{border-top:1px solid #30363d;margin-top:30px;padding-top:14px;font-size:.8rem;color:#8b949e}
#comments{min-height:120px}
@media (max-width:600px){h1{font-size:1.4rem}.facts{grid-template-columns:1fr;gap:0}.facts dt{margin-top:8px}.facts dt:first-child{margin-top:0}td,th{padding:8px 6px}}
'''.strip()

FAVICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='30' fill='%23f7931a'/%3E%3Ctext x='32' y='45' font-size='38' font-weight='700' text-anchor='middle' fill='%230d1117' font-family='Arial'%3E%E2%82%BF%3C/text%3E%3C/svg%3E"


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
  <link rel="icon" href="{FAVICON}" />
  {FEED_LINK}
  {extra_ld}
  <style>{CSS}{ALERT_CSS}{VISIT_CSS}</style>
  {api_script()}
</head>
<body>
  <header class="top">
    <a class="brand" href="/">🟠 Satoshi Nakamoto Statues</a>
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
           'name': 'Satoshi Statues', 'url': SITE + '/', 'logo': SITE + '/og-image.jpg'}
    if same:
        org['sameAs'] = same
    web = {'@context': 'https://schema.org', '@type': 'WebSite', '@id': SITE + '/#website',
           'name': 'Satoshi Nakamoto Statues – Global Interactive Map', 'url': SITE + '/',
           'publisher': {'@id': SITE + '/#org'}}
    if same:
        web['sameAs'] = same
    return ld(org) + '\n  ' + ld(web)


def signup_html(data, where):
    # 'Next statue' alert box: live Buttondown form when config.newsletter_action_url is set, else a coming-soon note.
    nxt = len(data['statues']) + 1
    url = (data.get('config') or {}).get('newsletter_action_url', '').strip()
    follow = ('<span class="alert-follow"><a class="feed-link" href="/feed.xml" type="application/atom+xml">📡 RSS/Atom feed</a>'
              + (f'<a class="feed-link" href="{e(nostr_url(data))}" target="_blank" rel="noopener noreferrer me">🟣 Follow on Nostr</a>' if nostr_url(data) else '')
              + '</span>')
    title = '<p class="alert-title">🔔 Get an alert when the next statue is unveiled</p>'
    if url:
        if not url.startswith('https://'):
            raise SystemExit('config.newsletter_action_url must start with https://')
        # Buttondown embed: POST opens in a named popup/tab that first shows the public subscribe page.
        m = re.match(r'https://buttondown\.com/api/emails/embed-subscribe/([^/?#]+)', url)
        public = f'https://buttondown.com/{m.group(1)}' if m else url
        body = (f'<form class="alert-form" action="{e(url)}" method="post" target="popupwindow" '
                f'onsubmit="window.open(\'{e(public)}\', \'popupwindow\')">'
                f'<input type="hidden" name="embed" value="1" />'
                f'<label class="sr-only" for="alert-email-{where}">Email address</label>'
                f'<input id="alert-email-{where}" type="email" name="email" required autocomplete="email" inputmode="email" placeholder="you@example.com" />'
                f'<button type="submit">Notify me</button></form>'
                f'<p class="alert-fine">One email per new statue. Unsubscribe anytime.</p>{follow}')
    else:
        body = f'<p class="alert-fine">Email alerts are coming soon. Meanwhile, follow along:</p>{follow}'
    return f'<section class="alert-box" aria-label="New statue alerts">{title}{body}</section>'


def photo_subject(s):
    lab = s['label']
    if lab.startswith('Satoshi Statue '):
        return 'Photo: Satoshi statue – ' + lab[len('Satoshi Statue '):]
    return 'Photo: ' + lab


def photo_js(data):
    # Assemble the photo-submission mailto at click time; the address is never a plain string in the HTML.
    c = data.get('config', {})
    u, dom = c.get('photo_email_user'), c.get('photo_email_domain')
    if not (u and dom):
        return ''
    codes = [ord(ch) for ch in (u + '@' + dom)][::-1]
    return ('<script>(function(){var c=' + json.dumps(codes) + ';'
            'function to(){return String.fromCharCode.apply(null,c.slice().reverse())}'
            'function body(l){return "Hi,\\n\\nHere is my photo of the "+l+" (attached).\\n\\nYour name or X handle (for credit): \\nDate taken: \\n\\n'
            'By sending, you let satoshistatues.com feature your photo with credit.\\n"}'
            'document.addEventListener("click",function(ev){var a=ev.target.closest&&ev.target.closest("[data-photo-subject]");if(!a)return;'
            'ev.preventDefault();location.href="mailto:"+to()+"?subject="+encodeURIComponent(a.getAttribute("data-photo-subject"))'
            '+"&body="+encodeURIComponent(body(a.getAttribute("data-photo-label")||"statue"));},true);})();</script>')


def photo_cta(s, data):
    c = data.get('config', {})
    if not (c.get('photo_email_user') and c.get('photo_email_domain')):
        return ''
    xh = c.get('photo_x_handle')
    xbtn = (f'<a class="btn" href="https://x.com/{e(xh)}" target="_blank" rel="noopener noreferrer">Or tag @{e(xh)} on X</a>' if xh else '')
    fallback = f'{e(c["photo_email_user"])} [at] {e(c["photo_email_domain"].replace(".", " [dot] "))}'
    shout = (f'<a href="https://x.com/{e(xh)}" target="_blank" rel="noopener noreferrer">@{e(xh)}</a>' if xh else 'us')
    return (f'<section class="photo-cta" id="photo" aria-label="Share your photo">'
            f'<p class="alert-title">📸 Been here? Share your photo</p>'
            f'<p class="alert-fine">Your shot could become this statue’s featured photo, help Bitcoiners plan their visit, and get a shoutout from {shout} on X.</p>'
            f'<p class="alert-fine">Send it with your name or X handle for credit.</p>'
            f'<div class="photo-actions"><a class="btn primary" href="#photo" data-photo-subject="{e(photo_subject(s))}" data-photo-label="{e(s["label"])}">📸 Send us your photo</a>{xbtn}</div>'
            f'<noscript><p class="alert-fine">Email: {fallback} with the subject “{e(photo_subject(s))}”.</p></noscript>'
            f'<p class="alert-fine">By sending, you let satoshistatues.com feature your photo with credit.</p></section>' + photo_js(data))


def credit_html(s):
    # Optional per-statue "photo_credit": plain text, or an @handle that links to X.
    cr = (s.get('photo_credit') or '').strip()
    if not cr:
        return ''
    if re.fullmatch(r'@[A-Za-z0-9_]{1,15}', cr):
        who = f'<a href="https://x.com/{cr[1:]}" target="_blank" rel="noopener noreferrer">{e(cr)}</a>'
    else:
        who = e(cr)
    return f'<span class="photo-credit">Photo: {who}</span>'


ALERT_CSS = (
    '.alert-box{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:10px;padding:12px 14px;margin:16px 0}'
    '.alert-title{font-weight:700;color:#e6edf3;font-size:.95rem;margin:0 0 6px}'
    '.alert-form{display:flex;gap:8px;flex-wrap:wrap;max-width:520px}'
    '.alert-form input[type=email]{flex:1 1 180px;min-width:0;min-height:44px;padding:10px 12px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:16px;font-family:inherit}'
    '.alert-form input[type=email]:focus{outline:2px solid #f7931a;border-color:#f7931a}'
    '.alert-form button{min-height:44px;padding:10px 16px;border-radius:8px;border:none;background:#f7931a;color:#0d1117;font-weight:700;font-size:.92rem;cursor:pointer;font-family:inherit}'
    '.alert-fine{font-size:.8rem;color:#8b949e;margin:6px 0 0;line-height:1.45}'
    '.feed-link{color:#f7931a;font-weight:600;display:inline-block;padding:13px 0;margin:-13px 0;text-decoration:none}'
    '.feed-link:hover{text-decoration:underline}'
    '.photo-cta{background:#161b22;border:1px solid #30363d;border-left:3px solid #f7931a;border-radius:10px;padding:12px 14px;margin:16px 0}'
    '.photo-actions{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0 4px}'
    '.photo-actions .btn{max-width:100%}'
    '.photo-cta .alert-fine a,.photo-credit a{padding:15px 0;margin:-15px 0}'
    '.photo-cta .alert-fine a{color:#f7931a}'
    '.photo-credit{display:block;margin-top:2px}'
    '.checkin-count{font-size:.85rem;color:#3fb950;margin:6px 0 0}'
    '.photo-credit a{color:#8b949e}'
    '.alert-follow{display:flex;flex-wrap:wrap;gap:0 18px;margin-top:2px}'
    '.alert-follow .feed-link{padding:0;margin:0;min-height:44px;display:inline-flex;align-items:center;font-size:.85rem}'
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
        f'  <icon>{SITE}/og-image.jpg</icon>\n'
        f'{entries}</feed>\n')


def status_badge(st, label=None):
    return f'<span class="badge b-{st.lower()}">{e(label or st)}</span>'


def src_list(sources):
    return '<ol class="src">' + ''.join(
        f'<li><a href="{e(x["url"])}" target="_blank" rel="noopener noreferrer">{e(x["label"])}</a></li>' for x in sources) + '</ol>'


def statue_page(s, data):
    title = f"{s['label']} – Location, Directions & Photos"
    desc = describe(s)
    alt = f"{s['label']}, {s['place']}, {s['city']}"
    lds = ld(statue_ld(s)) + '\n  ' + ld(breadcrumb_ld([('Map', SITE + '/'), (s['label'], page_url(s))]))
    out = head(title, desc, page_url(s), f"{SITE}/{og_path(s)}", OG_W, OG_H, f"{s['label']}: {s['city']}, {s['country']} (satoshistatues.com card)", lds)
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
    else:
        acc = 'Unknown. Check locally before you go.'
    directions = f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lng']}"
    series = ''
    if s.get('series21'):
        series = (f'<div class="callout">Part of Valentina Picozzi’s <strong>21 Nodes</strong> series of Satoshi statues. '
                  f'<a href="/21-nodes/">See all 21 Nodes →</a></div>')
    others = ''.join(f'<li><a href="/{o["page"]}/">{e(o["label"])}</a></li>'
                     for o in sorted(data['statues'], key=lambda o: -sort_year(o['year'])) if o is not s)
    stamp = ('<p class="note" style="margin-top:6px;color:#8b949e">Visiting? Open it on the map and tap <strong>Check in</strong> within 150 m to stamp your Satoshi Passport and join the <a href="/leaderboard/">leaderboard</a>.</p>'
             if s['status'] in CHECKABLE else
             '<p class="note" style="margin-top:6px;color:#8b949e">Not yet installed, so it can’t be stamped in the Satoshi Passport (not counted in the total).</p>')
    giscus_attrs = {
        'data-repo': REPO, 'data-repo-id': GISCUS['repoId'], 'data-category': GISCUS['category'],
        'data-category-id': GISCUS['categoryId'], 'data-mapping': 'specific', 'data-term': f"statue-{s['slug']}",
        'data-strict': '1', 'data-reactions-enabled': '1', 'data-emit-metadata': '0', 'data-input-position': 'top',
        'data-theme': 'dark', 'data-lang': 'en', 'data-loading': 'lazy'}
    gattrs = ' '.join(f'{k}="{e(v)}"' for k, v in giscus_attrs.items())
    out += f'''  <main>
    <div class="crumbs"><a href="/">Map</a> › {e(s['label'])}</div>
    <h1>{e(s['label'])}</h1>
    <p class="sub">{e(s['place'])} · {e(s['city'])}, {e(s['country'])}</p>
    {img_html}
    <dl class="facts">
      <dt>Location</dt><dd>{e(s['place'])}, {e(s['city'])}, {e(s['country'])}</dd>
      <dt>Unveiled</dt><dd>{e(s.get('unveiled') or s['year'])}</dd>
      <dt>Year</dt><dd>{e(s['year'])}</dd>
      <dt>Artist</dt><dd>{artist}</dd>
      <dt>Type</dt><dd>{e(s['type'])}</dd>
      <dt>Status</dt><dd>{status_badge(s['status'], s.get('statusLabel'))}</dd>
      <dt>Access</dt><dd>{acc}</dd>
      <dt>Coordinates</dt><dd>{s['lat']}, {s['lng']}</dd>
    </dl>
    <div class="actions">
      <a class="btn primary" href="{directions}" target="_blank" rel="noopener noreferrer">🧭 Get Directions</a>
      <a class="btn" href="/?s={s['page']}">🗺️ Open on the map</a>
      <a class="btn" href="#comments">💬 Comments</a>
    </div>
    {series}
    <h2>About</h2>
    <p class="note">{e(s['note'])}</p>
    {stamp}
    {visit_html(s)}
    {checkin_count_html(s)}
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
    {footer(data)}
  </main>
'''
    return out + LIVE_COUNT_JS + '\n' + TAIL


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
    out = head(title, desc, canonical, SITE + '/og-image.jpg', 1200, 630, 'Satoshi statues world map', lds)
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


LB_CSS = (
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
    '.lb-ver{display:inline-block;margin-left:6px;font-size:.7rem;font-weight:700;color:#0d1117;background:#3fb950;border-radius:4px;padding:1px 6px;vertical-align:middle}'
    '.lb-feed{list-style:none;font-size:.88rem}'
    '.lb-feed li{padding:8px 0;border-bottom:1px solid #21262d}'
    '.lb-feed a{color:#f7931a}'
    '.lb-feed time{color:#8b949e;font-size:.78rem;margin-left:4px}'
    '.lb-empty{color:#8b949e;font-size:.9rem;padding:12px}'
    '.lb-nick{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}'
    '.lb-nick input{flex:1 1 160px;min-width:0;min-height:44px;padding:10px 12px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:16px;font-family:inherit}'
    '.lb-nick button{min-height:44px;padding:10px 16px;border-radius:8px;border:none;background:#f7931a;color:#0d1117;font-weight:700;font-size:.92rem;cursor:pointer;font-family:inherit}'
    '.lb-msg{font-size:.82rem;color:#f0883e;margin-top:6px;min-height:1em}'
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
  function nameHtml(e) {
    var n = esc(e.name);
    if (/^@[A-Za-z0-9_]{1,15}$/.test(e.name)) n = '<a href="https://x.com/' + e.name.slice(1) + '" target="_blank" rel="noopener noreferrer nofollow">' + n + '</a>';
    return n + (e.verified ? '<span class="lb-ver" title="Verified by satoshistatues.com">✓ verified</span>' : '');
  }
  function stampsMeta(e) {
    return e.legacy ? (e.gps + ' GPS-checked · ' + e.legacy + ' earlier, unverified') : 'all GPS-checked';
  }
  function board() {
    return fetch(A + '/api/leaderboard?limit=100').then(function (r) { return r.json(); }).then(function (j) {
      var el = document.getElementById('lb-list');
      document.getElementById('lb-total').textContent = j.total_people ? (j.total_people === 1 ? '1 person' : j.total_people + ' people') + ' so far.' : '';
      if (!j.entries.length) { el.innerHTML = '<li class="lb-empty">No check-ins yet. Visit a statue and be the first!</li>'; return; }
      el.innerHTML = j.entries.map(function (e) {
        return '<li' + (e.id === meId ? ' class="me"' : '') + '><span class="lb-rank">' + e.rank + '</span><span class="lb-who"><span class="lb-name">' + nameHtml(e) +
          (e.id === meId ? ' <span class="lb-meta">(you)</span>' : '') + '</span><span class="lb-meta">' + stampsMeta(e) + '</span></span><span class="lb-stamps">' + e.stamps +
          '<small>of ' + j.statues + '</small></span></li>';
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
    if (!dev) { box.innerHTML = 'Check in at a statue from the <a href="/">map</a> to join. Stamps are only accepted within 150 m of the statue.'; return Promise.resolve(); }
    return fetch(A + '/api/me', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: dev }) })
      .then(function (r) { return r.json(); }).then(function (j) {
        if (!j.ok) return; var m = j.me; meId = m.id;
        box.innerHTML = (m.rank ? 'You are <strong>#' + m.rank + '</strong> with <strong>' + m.stamps + '</strong> stamp' + (m.stamps === 1 ? '' : 's') + '. ' : 'No stamps on the leaderboard yet. ') +
          'Your name: <strong>' + nameHtml(m) + '</strong>' +
          '<form class="lb-nick" id="lb-nick"><input name="nick" maxlength="20" aria-label="Nickname or X handle" placeholder="Nickname or @handle" value="' + esc(m.nickname || '') + '"><button type="submit">Save name</button></form><div class="lb-msg" id="lb-msg" aria-live="polite"></div>';
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
            f'GPS-checked stamps at {n} statues, plus recent check-ins.')
    canonical = SITE + '/leaderboard/'
    lds = ld(breadcrumb_ld([('Map', SITE + '/'), ('Leaderboard', canonical)]))
    out = head(title, desc, canonical, SITE + '/og-image.jpg', 1200, 630, 'Satoshi statues world map', lds)
    out = out.replace('</style>', LB_CSS + '</style>', 1)
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › Leaderboard</div>
    <h1>🏆 Satoshi Passport Leaderboard</h1>
    <p class="sub">Who has stamped the most of the {n} installed Satoshi statues? <span id="lb-total"></span></p>
    <div class="lb-me" id="lb-me" aria-live="polite">Loading…</div>
    <noscript><p class="note">The leaderboard needs JavaScript.</p></noscript>
    <h2>Top visitors</h2>
    <ol class="lb-list" id="lb-list"><li class="lb-empty">Loading…</li></ol>
    <h2>Recent check-ins</h2>
    <ul class="lb-feed" id="lb-feed"><li class="lb-empty">Loading…</li></ul>
    <h2>How it works</h2>
    <p class="note">Open a statue on the <a href="/">map</a> and tap <strong>Check in</strong> when you are within 150 m. The server checks the distance and records the stamp; your location itself is not stored. Each device can stamp each statue once, up to 5 new stamps a day. People are ranked by unique stamps; on a tie, whoever got there first ranks higher.</p>
    <p class="note" style="margin-top:8px">Stamps collected before the leaderboard started were added from the passport saved in your browser. Their location wasn’t checked by the server, so they are labelled <em>earlier, unverified</em>. A <span class="lb-ver" style="margin-left:0">✓ verified</span> badge means we confirmed that person ourselves. GPS can be faked, so treat this as a friendly game.</p>
    <p class="note" style="margin-top:8px;font-size:.85rem;color:#8b949e">What we store and how to delete it: <a href="/privacy/">Privacy</a>.</p>
    {footer(data)}
  </main>
"""
    return out + LB_JS + '\n' + TAIL


def privacy_page(data):
    c = data.get('config', {})
    mail = f'{c.get("photo_email_user", "photos")} [at] {c.get("photo_email_domain", "satoshistatues.com").replace(".", " [dot] ")}'
    title = 'Privacy – satoshistatues.com'
    desc = 'What satoshistatues.com stores for the Satoshi Passport leaderboard and analytics, and how to have it deleted.'
    canonical = SITE + '/privacy/'
    out = head(title, desc, canonical, SITE + '/og-image.jpg', 1200, 630, 'Satoshi statues world map', '')
    out += f"""  <main>
    <div class="crumbs"><a href="/">Map</a> › Privacy</div>
    <h1>Privacy</h1>
    <p class="sub">Short version: no accounts, no locations kept, and IP addresses only as hashes for 7 days.</p>
    <h2>Satoshi Passport and leaderboard</h2>
    <ul class="src" style="font-size:.95rem;color:#e6edf3">
      <li>Your passport stamps are saved in your browser (localStorage).</li>
      <li>When you check in, your browser sends your location, a <strong>random device ID</strong> (created in your browser, not linked to your name) and the statue to our leaderboard server. The server only uses the location to check that you are within 150 m. <strong>Coordinates are not stored.</strong> We keep the statue, the time and a rough distance band such as “under 50 m”.</li>
      <li>If you add a <strong>nickname or X handle</strong>, it is shown publicly on the leaderboard and in the recent check-ins feed.</li>
      <li>The first time you use the leaderboard, stamps already in your passport are added and labelled “earlier, unverified”.</li>
      <li><strong>IP addresses</strong> are only used for rate limiting. They are stored as a salted, per-day hash and <strong>deleted after 7 days</strong>.</li>
      <li>The server runs on Cloudflare Workers with a Cloudflare D1 database.</li>
    </ul>
    <h2>Analytics</h2>
    <p class="note">We use <a href="https://www.goatcounter.com/" target="_blank" rel="noopener noreferrer">GoatCounter</a> for privacy-friendly page counts without cookies. A successful check-in also sends an anonymous “Check-in &lt;statue&gt;” event, without any location.</p>
    <h2>Deleting your data</h2>
    <p class="note">Email <strong>{e(mail)}</strong> with your leaderboard nickname (or the statue and rough time of your check-in) and we will delete your stamps and nickname. Clearing your browser data removes your local passport and device ID.</p>
    <p class="note" style="margin-top:8px;font-size:.85rem;color:#8b949e">Last updated {BUILD_DATE}.</p>
    {footer(data)}
  </main>
"""
    return out + TAIL


# ---------- Per-statue Open Graph images (1200x630, Pillow) ----------
OG_W, OG_H = 1200, 630
FONT_BOLD = os.path.join(ROOT, 'fonts', 'inter-800.woff')
FONT_REG = os.path.join(ROOT, 'fonts', 'inter-500.woff')


def og_path(s):
    return f"og/{s['page']}.jpg"


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
        left, top = (ph.width - pw) // 2, max(0, (ph.height - OG_H) // 3)
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
    if not has_photo:
        d.ellipse((860, 165, 1140, 445), fill=(58, 42, 20))
        d.text((1000, 305), '₿', font=fb(200), fill=(13, 17, 23), anchor='mm')
    fr = lambda n: ImageFont.truetype(FONT_REG, n)
    d.rectangle((0, 0, OG_W, 8), fill=(247, 147, 26))
    d.ellipse((70, 64, 142, 136), fill=(247, 147, 26))
    d.text((106, 100), '₿', font=fb(48), fill=bg, anchor='mm')
    d.text((162, 100), 'SATOSHI STATUES', font=fb(30), fill=(247, 147, 26), anchor='lm')

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
    col = {'Installed': (63, 185, 80), 'Restored': (247, 147, 26), 'Damaged': (240, 136, 62), 'Planned': (88, 166, 255)}.get(s['status'], (139, 148, 158))
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
#   nearby         list  "## Nearby (BTC Map)" bullets → [{"name", "url", "note"}]
#   sources        list  "## Sources" bullets → [{"label", "url"}]
#   public_access / free  bool, optional; only emitted in JSON-LD when `sources` is set
#   updated        "YYYY-MM-DD" date the guide was written/updated (drives the sitemap lastmod)
GUIDE_TEXT_FIELDS = ('getting_there', 'exact_spot', 'photo_tip', 'hours_access')


def has_guide(s):
    v = s.get('visit') or {}
    return any((v.get(k) or '').strip() for k in GUIDE_TEXT_FIELDS) or bool(v.get('nearby'))


def paras(t):
    return ''.join(f'<p class="note">{e(p.strip())}</p>' for p in re.split(r'\n\s*\n', t.strip()) if p.strip())


def visit_html(s):
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
    if v.get('nearby'):
        items = ''.join(
            f'<li><a href="{e(n["url"])}" target="_blank" rel="noopener noreferrer">{e(n["name"])}</a>'
            f'{" – " + e(n["note"]) if n.get("note") else ""}</li>' for n in v['nearby'] if n.get('name') and n.get('url'))
        rows.append(f'<h3>Nearby places that accept bitcoin</h3><ul class="visit-nearby">{items}</ul>'
                    f'<p class="note" style="font-size:.8rem;color:#8b949e">From <a href="https://btcmap.org/" target="_blank" rel="noopener noreferrer">BTC Map</a>. Check before you go.</p>')
    srcs = (f'<h3>Guide sources</h3>{src_list(v["sources"])}' if v.get('sources') else '')
    upd = f'<p class="note" style="font-size:.8rem;color:#8b949e;margin-top:8px">Guide updated {e(v["updated"])}.</p>' if v.get('updated') else ''
    return f'<section class="visit" id="visiting" aria-labelledby="visiting-title"><h2 id="visiting-title">🧭 Visiting</h2>{"".join(rows)}{srcs}{upd}</section>'


VISIT_CSS = ('.visit{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:4px 16px 14px;margin:22px 0;scroll-margin-top:12px}'
             '.visit h2{margin:14px 0 6px}.visit h3{font-size:.95rem;color:#f7931a;margin:14px 0 4px}'
             '.visit .note+.note{margin-top:6px}.visit-nearby{padding-left:18px;font-size:.92rem}.visit-nearby li{margin:4px 0}'
             '.visit a{display:inline-block;padding:13px 0;margin:-13px 0}.visit li{margin:8px 0}')


def page_lastmod(s):
    u = ((s.get('visit') or {}).get('updated') or '').strip()
    return max(BUILD_DATE, u) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', u) else BUILD_DATE


def sitemap(data):
    urls = [(SITE + p, BUILD_DATE) for p in ('/', '/21-nodes/', '/leaderboard/', '/privacy/')] + [(page_url(s), page_lastmod(s)) for s in data['statues']]
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


def build_index(data, text):
    statues_js = [{k: v for k, v in s.items() if k not in ('slug', 'sources', 'accessSource', 'label', 'visit')} for s in data['statues']]
    for s, src in zip(statues_js, data['statues']):
        s['label'] = src['label']
        if has_guide(src):
            s['guide'] = True
        s['photoSubject'] = photo_subject(src)
    js = '    const statues = ' + json.dumps(statues_js, ensure_ascii=False, indent=2).replace('\n', '\n    ') + ';'
    text = replace_block(text, 'STATUES', js, comment=('// ', ''))
    ldhtml, _ = home_ld(data)
    text = replace_block(text, 'JSONLD', '  ' + ldhtml)
    links = '        <ul>\n' + ''.join(
        f'          <li><a href="/{s["page"]}/">{e(s["label"])}</a></li>\n'
        for s in sorted(data['statues'], key=lambda s: -sort_year(s['year']))) + '          <li><a href="/21-nodes/">21 Nodes tracker</a></li>\n          <li><a href="/leaderboard/">🏆 Passport leaderboard</a></li>\n          <li><a href="/privacy/">Privacy</a></li>\n        </ul>'
    text = replace_block(text, 'LINKS', links)
    text = replace_block(text, 'SIGNUP', '        ' + signup_html(data, 'home'))
    text = replace_block(text, 'HEADLINKS', '  ' + FEED_LINK + '\n  <style>' + ALERT_CSS + '</style>' + ('\n  ' + api_script() if api_script() else '') + ('\n  ' + photo_js(data) if photo_js(data) else ''))
    return text


def outputs(data):
    with open(os.path.join(ROOT, 'index.html'), encoding='utf-8') as f:
        idx = f.read()
    files = {'index.html': build_index(data, idx), 'sitemap.xml': sitemap(data), 'robots.txt': ROBOTS,
             'feed.xml': feed_xml(data),
             '.nojekyll': '',
             '21-nodes/index.html': nodes_page(data),
             'leaderboard/index.html': leaderboard_page(data),
             'privacy/index.html': privacy_page(data)}
    pages = [s['page'] for s in data['statues']]
    assert len(set(pages)) == len(pages), 'duplicate page slugs'
    if nostr_json(data):
        files['.well-known/nostr.json'] = nostr_json(data)
    for s in data['statues']:
        files[f"{s['page']}/index.html"] = statue_page(s, data)
    return files


def main():
    check = '--check' in sys.argv
    if '--refresh-checkins' in sys.argv:
        refresh_checkins()
    if '--worker' in sys.argv:
        write_worker_statues(data)
        return
    data = load()
    stale = []
    for rel, content in bin_outputs(data).items():
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
