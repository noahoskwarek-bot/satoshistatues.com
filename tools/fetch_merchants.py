#!/usr/bin/env python3
"""Refresh merchants.json and lodging.json: places (and places to stay) that accept bitcoin near each statue, from the BTC Map API.

    python3 tools/fetch_merchants.py          # fetch both, rewrite each file only if a list changed
    python3 tools/fetch_merchants.py --force  # also bump the 'fetched' dates when nothing changed

Lodging ("Stay nearby"): one bulk call to /v4/places with the osm:tourism field; keeps OSM tourism=hotel, hostel,
guest_house, motel, apartment and chalet (camp/caravan sites, alpine huts and attractions are left out), named only.
Radius/limit come from statues.json config.lodging (radius_mi, fallback_km, max_items); see GUIDES.md.

The API's radius_km is a loose box, so every distance is re-checked here with haversine.
ATMs and unnamed entries are dropped. build.py reads merchants.json (offline) and decides what to show:
up to 5 places within 1 km; else the nearest 3 within 5 km; else 'none listed yet' with BTC Map links.
If a statue's fetch fails, its previous cached entry is kept, so a BTC Map outage never empties a page.
"""
import datetime
import json
import math
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'merchants.json')
LODGING_OUT = os.path.join(ROOT, 'lodging.json')
API = 'https://api.btcmap.org/v4/places/search/?lat={lat}&lon={lng}&radius_km={r}'
QUERY_KM = 6        # ask a bit wider than 5 km, then filter exactly
KEEP = 5            # nearest places stored per statue
ATM_ICONS = {'local_atm', 'atm'}
LODGING_API = ('https://api.btcmap.org/v4/places?fields=id,lat,lon,name,osm:tourism,verified_at,website')
LODGING_TYPES = ('hotel', 'hostel', 'guest_house', 'motel', 'apartment', 'chalet')
# booking aggregators / tracking parameters: never shown as the link (BTC Map listing is used instead)
NO_LINK_HOSTS = re.compile(r'(^|\.)(booking\.com|airbnb\.[a-z.]+|expedia\.[a-z.]+|hotels\.com|agoda\.com|trivago\.[a-z.]+|'
                           r'tripadvisor\.[a-z.]+|vrbo\.com|hostelworld\.com|kayak\.[a-z.]+)$', re.I)
TRACKING = re.compile(r'[?&](aff|affiliate|aid|ref|refid|utm_[a-z]+|partner|clickref)=', re.I)
UA = 'satoshistatues.com build (https://www.satoshistatues.com)'
# Link check for lodging websites (see check_site): browser-like UA so bot filters treat us like a visitor
LINK_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
           'Chrome/130.0 Safari/537.36')
LINK_TIMEOUT = 10
DOH = 'https://dns.google/resolve?name={host}&type=A'
# Parked / placeholder pages, matched conservatively: strong parking phrases anywhere in the first 64 KB,
# 'coming soon' style phrases only in the <title>, or a redirect to a domain-parking / for-sale host.
PARKED_BODY = re.compile(r'this domain (?:name )?(?:is|may be) (?:parked|for sale)|domain (?:is )?for sale|buy this domain|'
                         r'parked free|domain parking|parkingcrew|sedoparking|bodis\.com|'
                         r'website is being created here|new customer website is being created|'
                         r'future home of something quite cool|web ?site coming soon', re.I)
PARKED_TITLE = re.compile(r'coming soon|under construction|website is being created|default web site page|'
                          r'domain (?:is )?for sale|parked domain|account suspended', re.I)
PARKED_HOSTS = re.compile(r'(^|\.)(sedo\.com|dan\.com|afternic\.com|hugedomains\.com|parkingcrew\.net|bodis\.com|'
                          r'undeveloped\.com|sav\.com)$', re.I)


def km(a_lat, a_lng, b_lat, b_lng):
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def is_atm(p):
    return (p.get('icon') or '') in ATM_ICONS or re.search(r'\bATM\b', p.get('name') or '') is not None


def named(p):
    n = (p.get('name') or '').strip()
    return n and n.lower() not in ('unnamed', 'unknown')


def fetch(lat, lng):
    req = urllib.request.Request(API.format(lat=lat, lng=lng, r=QUERY_KM), headers={'User-Agent': UA, 'Accept': 'application/json'})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as ex:  # network hiccup: retry, then give up for this statue
            last = ex
            time.sleep(2 + attempt * 3)
    raise last


def summarize(s, places):
    rows = []
    for p in places:
        if is_atm(p) or not named(p) or p.get('lat') is None or p.get('lon') is None:
            continue
        d = km(s['lat'], s['lng'], p['lat'], p['lon'])
        if d <= 5:
            rows.append({'id': p['id'], 'name': p['name'].strip(), 'icon': p.get('icon') or '',
                         'km': round(d, 3), 'verified_at': (p.get('verified_at') or '')[:10] or None})
    rows.sort(key=lambda x: (x['km'], x['id']))
    return {'lat': s['lat'], 'lng': s['lng'],
            'within_1km': sum(1 for x in rows if x['km'] <= 1),
            'within_5km': len(rows),
            'nearest': rows[:KEEP]}


def clean_site(u):
    import urllib.parse
    u = (u or '').strip()
    if not re.match(r'https?://', u, re.I):
        return None
    host = (urllib.parse.urlsplit(u).hostname or '').lower()
    if not host or NO_LINK_HOSTS.search(host) or TRACKING.search(u):
        return None
    return u


def _nxdomain(host):
    """True only for a clear DNS failure: NXDOMAIN from Google DNS-over-HTTPS (works behind resolving proxies);
    if DoH can't be reached, a local 'name not known' resolver error. Anything else counts as resolvable."""
    import socket
    import urllib.parse
    try:
        req = urllib.request.Request(DOH.format(host=urllib.parse.quote(host)), headers={'User-Agent': UA, 'Accept': 'application/dns-json'})
        with urllib.request.urlopen(req, timeout=LINK_TIMEOUT) as r:
            return json.load(r).get('Status') == 3
    except Exception:
        pass
    try:
        socket.getaddrinfo(host, 443)
        return False
    except socket.gaierror as ex:
        return ex.errno in (getattr(socket, 'EAI_NONAME', -2), getattr(socket, 'EAI_NODATA', -5))
    except Exception:
        return False


def _probe(url):
    """('dead'|'alive'|'unknown', reason). HEAD first, GET if HEAD fails or isn't 2xx; redirects followed.
    404/410 and parked pages are dead; 403/429/5xx/other HTTP answers are alive; network errors are unknown."""
    import urllib.error
    import urllib.parse
    hdrs = {'User-Agent': LINK_UA, 'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8', 'Accept-Language': 'en,de;q=0.8'}
    status = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs, method='HEAD'), timeout=LINK_TIMEOUT) as r:
            status = r.status
    except urllib.error.HTTPError as ex:
        status = ex.code
    except Exception:
        status = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=LINK_TIMEOUT) as r:
            final = (urllib.parse.urlsplit(r.geturl()).hostname or '').lower()
            if PARKED_HOSTS.search(final):
                return 'dead', f'redirects to parking host {final}'
            body = r.read(65536).decode('utf-8', 'replace') if 'html' in (r.headers.get('Content-Type') or 'html') else ''
    except urllib.error.HTTPError as ex:
        if ex.code in (404, 410):
            return 'dead', f'HTTP {ex.code}'
        return 'alive', f'HTTP {ex.code}'
    except Exception as ex:
        if status in (404, 410):
            return 'dead', f'HTTP {status} (HEAD; GET failed)'
        if status is not None:
            return 'alive', f'HTTP {status} (HEAD; GET failed)'
        return 'unknown', type(ex).__name__
    m = re.search(r'<title[^>]*>(.*?)</title>', body, re.I | re.S)
    title = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    if PARKED_BODY.search(body) or (title and PARKED_TITLE.search(title)):
        return 'dead', f'placeholder page ({title[:60] or "parking text"})'
    return 'alive', 'OK'


_LINKS = {}


def check_site(url):
    """Is a lodging website worth linking? Returns (keep, reason). Dead = 404/410, NXDOMAIN or a parked/placeholder page.
    403, 429, 5xx and timeouts are kept (bot protection or a slow server is not a dead site). An http:// link that can't
    be reached at all is also tried over https://, and that answer is used when it is a clear one."""
    import urllib.parse
    if url in _LINKS:
        return _LINKS[url]
    host = (urllib.parse.urlsplit(url).hostname or '').lower()
    if _nxdomain(host):
        res = (False, 'DNS: no such domain')
    else:
        state, why = _probe(url)
        if state == 'unknown' and url.lower().startswith('http://'):
            state2, why2 = _probe('https://' + url[7:])
            if state2 != 'unknown':
                state, why = state2, why2 + ' (via https)'
        res = (state != 'dead', why)
    _LINKS[url] = res
    return res


def lodging_config(cfg):
    c = cfg.get('lodging') or {}
    return float(c.get('radius_mi', 5)) * 1.609344, float(c.get('fallback_km', 25)), int(c.get('max_items', 5))


DROPPED = []


def fetch_lodging(statues, cfg):
    radius_km, fallback_km, keep = lodging_config(cfg)
    hide = set((cfg.get('lodging') or {}).get('hide_websites') or [])  # dead links confirmed by hand
    req = urllib.request.Request(LODGING_API, headers={'User-Agent': UA, 'Accept': 'application/json'})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                allp = json.load(r)
            break
        except Exception as ex:
            last = ex
            time.sleep(2 + attempt * 3)
    else:
        raise last
    stays = [p for p in allp if p.get('osm:tourism') in LODGING_TYPES and named(p)
             and p.get('lat') is not None and p.get('lon') is not None]
    out = {}
    for s in statues:
        rows = []
        for p in stays:
            d = km(s['lat'], s['lng'], p['lat'], p['lon'])
            if d <= fallback_km:
                row = {'id': p['id'], 'name': p['name'].strip(), 'type': p['osm:tourism'], 'km': round(d, 3),
                       'verified_at': (p.get('verified_at') or '')[:10] or None, 'lat': round(p['lat'], 6), 'lng': round(p['lon'], 6)}
                site = clean_site(p.get('website'))
                if site:
                    row['website'] = site
                rows.append(row)
        rows.sort(key=lambda x: (x['km'], x['id']))
        for row in rows[:keep]:  # only the stored ones are checked (cached per URL across statues)
            if row.get('website'):
                ok, why = ((False, 'listed in config.lodging.hide_websites') if row['website'] in hide
                           else check_site(row['website']))
                if not ok:
                    DROPPED.append((s['page'], row['name'], row['website'], why))
                    del row['website']  # build.py and the map fall back to the BTC Map listing
        out[s['page']] = {'within_radius': sum(1 for x in rows if x['km'] <= radius_km),
                          'within_fallback': len(rows), 'nearest': rows[:keep]}
    return out


def refresh_lodging(statues, cfg):
    old = {}
    if os.path.exists(LODGING_OUT):
        with open(LODGING_OUT, encoding='utf-8') as f:
            old = json.load(f)
    try:
        new = fetch_lodging(statues, cfg)
    except Exception as ex:  # BTC Map outage: keep the cached file as-is
        print(f'WARN lodging: {ex}; keeping lodging.json', file=sys.stderr)
        return
    radius_km, fallback_km, keep = lodging_config(cfg)
    for page, name, url, why in DROPPED:
        print(f'lodging link dropped: {page}: {name}: {url} ({why})')
    changed = new != old.get('stays')
    if not changed and '--force' not in sys.argv:
        print('lodging.json unchanged')
        return
    out = {'_comment': 'Generated by tools/fetch_merchants.py from the BTC Map API: OSM tourism=' + '/'.join(LODGING_TYPES)
                       + ', named only, haversine km from the statue pin, nearest ' + str(keep) + ' within ' + str(fallback_km)
                       + ' km. Booking-site and tracking links dropped; dead websites (404/410, no such domain, parked/placeholder page) '
                       'dropped by a link check, so those stays link to BTC Map. Do not edit by hand.',
           'source': 'https://api.btcmap.org/v4/places',
           'fetched': datetime.date.today().isoformat(),
           'stays': new}
    with open(LODGING_OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write('\n')
    for k, v in new.items():
        print(f'{k:15s} stays: {v["within_radius"]:3d} within {radius_km:.2f} km, {v["within_fallback"]:3d} within {fallback_km:g} km')


def main():
    with open(os.path.join(ROOT, 'statues.json'), encoding='utf-8') as f:
        sj = json.load(f)
    statues = sj['statues']
    refresh_lodging(statues, sj.get('config') or {})
    old = {}
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            old = json.load(f)
    new_places, failed = {}, []
    for s in statues:
        try:
            new_places[s['page']] = summarize(s, fetch(s['lat'], s['lng']))
        except Exception as ex:
            failed.append(s['page'])
            print(f'WARN {s["page"]}: {ex}; keeping cached entry', file=sys.stderr)
            if s['page'] in old.get('places', {}):
                new_places[s['page']] = old['places'][s['page']]
        time.sleep(0.5)
    changed = new_places != old.get('places')
    if not changed and '--force' not in sys.argv:
        print('merchants.json unchanged')
        return
    out = {'_comment': 'Generated by tools/fetch_merchants.py from the BTC Map API (ATMs and unnamed places removed, '
                       'haversine distances in km from the statue pin). Do not edit by hand.',
           'source': 'https://api.btcmap.org/v4/places/search/',
           'fetched': datetime.date.today().isoformat() if changed or '--force' in sys.argv else old.get('fetched'),
           'places': new_places}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write('\n')
    for k, v in new_places.items():
        print(f'{k:15s} 1km={v["within_1km"]:4d} 5km={v["within_5km"]:4d}')
    if failed:
        print('failed (cached kept):', ', '.join(failed), file=sys.stderr)


if __name__ == '__main__':
    main()
