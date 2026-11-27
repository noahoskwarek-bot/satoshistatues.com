#!/usr/bin/env python3
"""Sanity-check the shared site header after a build. Run from the repo root."""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Import constants without running main. build.py only runs main under __name__ == '__main__'.
import build

failed = []

def check(cond, msg):
    if not cond:
        failed.append(msg)

SHOP_ON = build.SHOP_LINK_ENABLED is True   # live since 2026-11-27 (Noah: "Go live with everything")

# Walk generated HTML (skip redirect stubs and the private test page if any)
skip = {'passport/index.html', 'fellow-travelers/index.html'}
headers = 0
shop_visible = 0
for p in ROOT.rglob('index.html'):
    rel = str(p.relative_to(ROOT))
    if '/.git/' in '/' + rel or rel in skip:
        continue
    t = p.read_text(encoding='utf-8', errors='replace')
    if 'data-ss-nav' not in t:
        # redirect / embed / test pages may omit the full nav
        if '<header class="top"' in t and 'data-ss-nav' not in t:
            # test statue page is brand-only; that's ok
            if 'Private test page' in t:
                continue
            failed.append(f'{rel}: has .top header but no data-ss-nav')
        continue
    headers += 1
    check('ss-nav-toggle' in t, f'{rel}: missing hamburger')
    check('ss-more-btn' in t, f'{rel}: missing More button')
    check('aria-controls="ss-nav-panel"' in t, f'{rel}: hamburger missing aria-controls')
    check('aria-expanded="false"' in t, f'{rel}: missing aria-expanded')
    check('/ss-nav.js' in t, f'{rel}: missing ss-nav.js')
    check('Proof of Walk' in t, f'{rel}: missing Proof of Walk link')
    check('>Timeline<' in t or '>Timeline</a>' in t, f'{rel}: missing Timeline link')
    check('Before you arrive' in t, f'{rel}: missing Before you arrive link')
    check('href="/shop/"' in t, f'{rel}: Shop link missing from markup')
    # Shop must be hidden while the flag is off
    shops = re.findall(r'<a href="/shop/"[^>]*>', t)
    check(shops, f'{rel}: no Shop <a>')
    for tag in shops:
        if 'hidden' not in tag:
            shop_visible += 1
        if SHOP_ON:
            check('hidden' not in tag, f'{rel}: Shop link is hidden but SHOP_LINK_ENABLED is True: {tag}')
        else:
            check('hidden' in tag, f'{rel}: Shop link is not hidden: {tag}')
    # Forbidden copy (Grant) in the header itself
    m = re.search(r'<header class="top"[^>]*>.*?</header>', t, re.S)
    if m:
        h = m.group(0).lower()
        for w in ('odds', 'luck', ' win', 'bet', 'worth', 'value', 'prize', 'limited edition', 'valuable', 'resale'):
            # "win" is too short / may match "rewind"; require word-ish
            if w.strip() in ('win', 'bet') and not re.search(r'\b' + w.strip() + r'\b', h):
                continue
            if w in h:
                failed.append(f'{rel}: header contains banned word {w!r}')

check(headers >= 50, f'expected many generated headers, found {headers}')
if SHOP_ON:
    check(shop_visible >= 2 * headers, f'Shop visible in {shop_visible} links, expected desktop + phone menu on all {headers} pages')
else:
    check(shop_visible == 0, f'Shop visible on {shop_visible} pages')

# Home keeps Passport + tip toggle id (JS and load_home_tip depend on them)
home = (ROOT / 'index.html').read_text(encoding='utf-8')
check('id="passport-btn"' in home, 'home: passport-btn id missing')
check('id="tip-toggle"' in home, 'home: tip-toggle id missing')
check('id="tip-box"' in home, 'home: tip-box missing')
check('BUILD:HEADER:BEGIN' in home, 'home: BUILD:HEADER markers missing')

# Statue pages keep the tip CTA
vienna = (ROOT / 'vienna/index.html').read_text(encoding='utf-8')
check('id="tip-toggle"' in vienna, 'vienna: tip-toggle missing')
check('₿ Tip' in vienna, 'vienna: Tip label missing')

print(f'checked {headers} pages with the shared header (Shop {"visible" if SHOP_ON else "hidden"}, {shop_visible} visible Shop links)')
if failed:
    print('FAIL:')
    for f in failed:
        print(' -', f)
    sys.exit(1)
print('ok')
