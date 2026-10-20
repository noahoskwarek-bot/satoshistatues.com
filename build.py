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
CHECKABLE = ('Installed', 'Restored')
BUILD_DATE = os.environ.get('BUILD_DATE') or datetime.date.today().isoformat()

e = lambda t: html.escape(str(t), quote=True)


def load():
    with open(os.path.join(ROOT, 'statues.json'), encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('config', {})
    for s in data['statues']:
        s['slug'] = slug_of(s)
    return data


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
        'image': image,
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
    return ld(item_list) + '\n  ' + ld(faq), faq


# ---------------------------------------------------------------- shared page chrome
CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0d1117;color:#e6edf3;line-height:1.5}
a{color:#f7931a}
.top{background:#161b22;border-bottom:1px solid #30363d;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.top .brand{color:#f7931a;font-weight:700;font-size:1.1rem;text-decoration:none}
.top nav{display:flex;gap:8px;flex-wrap:wrap}
.top nav a{color:#e6edf3;text-decoration:none;border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-size:.88rem;min-height:40px;display:inline-flex;align-items:center}
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
.b-installed{background:#1a3a2a;color:#3fb950}.b-restored{background:#3a2e1a;color:#f7931a}.b-planned{background:#1a2a3a;color:#58a6ff}
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
  <style>{CSS}{ALERT_CSS}</style>
</head>
<body>
  <header class="top">
    <a class="brand" href="/">🟠 Satoshi Nakamoto Statues</a>
    <nav><a href="/">🗺️ Map</a><a href="/21-nodes/">21 Nodes</a></nav>
  </header>
'''


TAIL = '''  <script data-goatcounter="https://satoshistatues.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body>
</html>
'''


FEED_URL = SITE + '/feed.xml'
FEED_LINK = f'<link rel="alternate" type="application/atom+xml" title="Satoshi Statues – new statues" href="{FEED_URL}" />'


def signup_html(data, where):
    # 'Next statue' alert box: live Buttondown form when config.newsletter_action_url is set, else a coming-soon note.
    nxt = len(data['statues']) + 1
    url = (data.get('config') or {}).get('newsletter_action_url', '').strip()
    feed = '<a class="feed-link" href="/feed.xml" type="application/atom+xml">📡 RSS/Atom feed</a>'
    title = f'<p class="alert-title">🔔 Get an alert when #{nxt} is unveiled</p>'
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
                f'<p class="alert-fine">One email per new statue. Unsubscribe anytime. Or follow the {feed}.</p>')
    else:
        body = f'<p class="alert-fine">Email alerts are coming soon. Follow the {feed} meanwhile.</p>'
    return f'<section class="alert-box" aria-label="New statue alerts">{title}{body}</section>'


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
                   f"Status: {s['status']}. Unveiled {s.get('unveiled') or s['year']}.")
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


def status_badge(st):
    return f'<span class="badge b-{st.lower()}">{e(st)}</span>'


def src_list(sources):
    return '<ol class="src">' + ''.join(
        f'<li><a href="{e(x["url"])}" target="_blank" rel="noopener noreferrer">{e(x["label"])}</a></li>' for x in sources) + '</ol>'


def statue_page(s, data):
    title = f"{s['label']} – Location, Directions & Photos"
    desc = describe(s)
    image, iw, ih, local = img_abs(s)
    alt = f"{s['label']}, {s['place']}, {s['city']}"
    lds = ld(statue_ld(s)) + '\n  ' + ld(breadcrumb_ld([('Map', SITE + '/'), (s['label'], page_url(s))]))
    out = head(title, desc, page_url(s), image, iw, ih, alt, lds)
    img_html = ''
    if s.get('img'):
        src = s['img'] if s['img'].startswith('http') else '/' + s['img']
        wh = f' width="{s["imgW"]}" height="{s["imgH"]}"' if s.get('imgW') else ''
        img_html = (f'<figure><img src="{e(src)}" alt="{e(alt)}"{wh} decoding="async" '
                    f'onerror="this.closest(\'figure\').remove()"><figcaption>{e(s["name"])} · {e(s["place"])}</figcaption></figure>')
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
    stamp = ('<p class="note" style="margin-top:6px;color:#8b949e">Visiting? Open it on the map and tap <strong>Check in</strong> within 200 m to stamp your Satoshi Passport.</p>'
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
      <dt>Status</dt><dd>{status_badge(s['status'])}</dd>
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
    <h2>Sources</h2>
    {src_list(s.get('sources', []))}
    <p class="note" style="font-size:.85rem;color:#8b949e;margin-top:8px">Spotted a mistake? <a href="https://github.com/{REPO}/issues/new?title={e('Correction: ' + s['name'])}" target="_blank" rel="noopener noreferrer">Suggest a correction</a>.</p>
    <h2>Other Satoshi statues</h2>
    <ul class="others">{others}</ul>
    <h2 id="comments-title">Comments</h2>
    <p class="note" style="font-size:.85rem;color:#8b949e;margin-bottom:8px">Visit reports, tips and photo links. Powered by giscus (needs a GitHub account). Same thread as on the map.</p>
    <div id="comments"><script src="https://giscus.app/client.js" {gattrs} crossorigin="anonymous" async></script></div>
    {signup_html(data, 'page')}
    <footer class="site"><a href="/">satoshistatues.com</a> · Interactive map of every known Satoshi Nakamoto statue · <a href="/21-nodes/">21 Nodes tracker</a> · <a href="/feed.xml">Feed</a></footer>
  </main>
'''
    return out + TAIL


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
        st = s['status'] if s['status'] in CHECKABLE else 'Unveiled, awaiting permanent site'
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
    <footer class="site"><a href="/">Back to the map</a> · <a href="/feed.xml">Feed</a> · <a href="/sitemap.xml">Sitemap</a></footer>
  </main>
'''
    return out + TAIL


def sitemap(data):
    urls = [SITE + '/', SITE + '/21-nodes/'] + [page_url(s) for s in data['statues']]
    body = ''.join(f'  <url><loc>{u}</loc><lastmod>{BUILD_DATE}</lastmod></url>\n' for u in urls)
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
    statues_js = [{k: v for k, v in s.items() if k not in ('slug', 'sources', 'accessSource', 'label')} for s in data['statues']]
    for s, src in zip(statues_js, data['statues']):
        s['label'] = src['label']
    js = '    const statues = ' + json.dumps(statues_js, ensure_ascii=False, indent=2).replace('\n', '\n    ') + ';'
    text = replace_block(text, 'STATUES', js, comment=('// ', ''))
    ldhtml, _ = home_ld(data)
    text = replace_block(text, 'JSONLD', '  ' + ldhtml)
    links = '        <ul>\n' + ''.join(
        f'          <li><a href="/{s["page"]}/">{e(s["label"])}</a></li>\n'
        for s in sorted(data['statues'], key=lambda s: -sort_year(s['year']))) + '          <li><a href="/21-nodes/">21 Nodes tracker</a></li>\n        </ul>'
    text = replace_block(text, 'LINKS', links)
    text = replace_block(text, 'SIGNUP', '        ' + signup_html(data, 'home'))
    text = replace_block(text, 'HEADLINKS', '  ' + FEED_LINK + '\n  <style>' + ALERT_CSS + '</style>')
    return text


def outputs(data):
    with open(os.path.join(ROOT, 'index.html'), encoding='utf-8') as f:
        idx = f.read()
    files = {'index.html': build_index(data, idx), 'sitemap.xml': sitemap(data), 'robots.txt': ROBOTS,
             'feed.xml': feed_xml(data),
             '21-nodes/index.html': nodes_page(data)}
    pages = [s['page'] for s in data['statues']]
    assert len(set(pages)) == len(pages), 'duplicate page slugs'
    for s in data['statues']:
        files[f"{s['page']}/index.html"] = statue_page(s, data)
    return files


def main():
    check = '--check' in sys.argv
    data = load()
    stale = []
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
