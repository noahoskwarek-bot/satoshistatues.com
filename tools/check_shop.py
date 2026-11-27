#!/usr/bin/env python3
"""Hidden /shop/ page checks (PREVIEW). Run: python3 tools/check_shop.py [--worker /workspace/lb-tee]
- /shop/ is noindex, not in sitemap.xml, not linked from any other page (unlisted)
- Grant's copy rules on the page, its script and (with --worker) the Worker catalog
- no statue imagery referenced from the shop page (mockup only)
- print files are 3600x4800 RGBA at ~300 DPI (Printful printfile 1: 1800x2400 @150 DPI = 12x16 in, same 3:4)
"""
import re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
BAD = re.compile(r"\b(odds|luck\w*|win(s|ning|ners?)?|bet(s|ting)?|worth\w*|value\w*|valuable|prizes?|limited\s+edition|resale|resell\w*|jackpots?|giveaway\w*|rewards?|lotter\w*|gambl\w*|chances?)\b", re.I)
fails = []
def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

page = (ROOT / 'shop/index.html').read_text()
js = (ROOT / 'shop/shop.js').read_text()
strip_js = lambda t: re.sub(r'^\s*//.*$', '', t, flags=re.M)
sys.path.insert(0, str(ROOT))
import build
LIVE = build.SHOP_LINK_ENABLED is True
print('mode:', 'LIVE (indexed, linked, in sitemap)' if LIVE else 'HIDDEN (noindex, unlinked)')
sm = (ROOT / 'sitemap.xml').read_text()
linked = [str(p.relative_to(ROOT)) for p in ROOT.rglob('*.html') if 'shop' not in p.parts and '.git' not in p.parts and re.search(r'href="(https://www\.satoshistatues\.com)?/shop/"(?![^>]*hidden)', p.read_text(errors='ignore'))]
if LIVE:
    check('content="index, follow"' in page and 'noindex' not in page, 'shop/index.html is index, follow')
    check('rel="canonical" href="https://www.satoshistatues.com/shop/"' in page, 'canonical is /shop/')
    check('<loc>https://www.satoshistatues.com/shop/</loc>' in sm, 'in sitemap.xml')
    check('index.html' in linked and len(linked) >= 50, f'Shop linked (visible) from {len(linked)} pages incl. home')
    check('data-ss-nav' in page, 'shop page uses the shared site header')
else:
    check('content="noindex, nofollow"' in page, 'shop/index.html is noindex, nofollow')
    check('rel="canonical"' not in page and 'og:' not in page, 'no canonical / og tags that advertise the page')
    check('/shop' not in sm, 'not in sitemap.xml')
    check(not linked, 'no other page links to /shop/ ' + (str(linked) if linked else ''))
check('/shop/shop.js' in page, 'page loads /shop/shop.js')
main_html = re.search(r'<main.*?</main>', page, re.S).group(0) if '<main' in page else page
og = re.findall(r'og:image" content="([^"]+)"', page)
check(all('/shop/img/' in u for u in og), f'og:image is the shop mockup {og}')
def visible(s):
    s = re.sub(r'<(script|style)\b.*?</\1>', ' ', s, flags=re.S)
    s = re.sub(r'<!--.*?-->', ' ', s, flags=re.S)
    return re.sub(r'<[^>]+>', ' ', s)
for name, text in [('page text', visible(main_html if '<main' in page else page)), ('shop.js strings', ' '.join(m.group(0) for m in re.finditer(r'"[^"\n]*"|\'[^\'\n]*\'', strip_js(js))))]:
    text = re.sub(r'\bvalue=', ' ', text)   # HTML attribute, not copy
    m = BAD.search(text); check(not m, f'{name}: no restricted wording' + (f' (found "{m.group(0)}")' if m else ''))
imgs = re.findall(r'(?:src|href)="([^"]+\.(?:jpg|jpeg|png|webp|svg))"', main_html + js)
check(not any(re.search(r'satoshi-[a-z]|statue|photo', i) for i in imgs), 'no statue imagery on the shop page ' + str(imgs))
if '--worker' in sys.argv:
    w = pathlib.Path(sys.argv[sys.argv.index('--worker') + 1])
    cat = strip_js((w / 'src/shop-catalog.js').read_text())
    strings = ' '.join(m.group(0) for m in re.finditer(r"'[^'\n]*'", cat))
    m = BAD.search(strings); check(not m, 'worker catalog strings: no restricted wording' + (f' (found "{m.group(0)}")' if m else ''))
    for rel in re.findall(r"(/shop/[^']+\.(?:png|jpg))", cat):
        check((ROOT / rel.lstrip('/')).exists(), f'catalog file exists on the site: {rel}')
try:
    from PIL import Image
    for f in sorted((ROOT / 'shop/files').glob('*.png')):
        im = Image.open(f); dpi = im.info.get('dpi', (0, 0))[0]
        check(im.size == (3600, 4800) and im.mode == 'RGBA' and abs(dpi - 300) < 1, f'{f.name}: {im.size} {im.mode} {dpi:.1f} DPI')
except ImportError:
    print('skip image checks (no Pillow)')
print('\n' + ('PASS' if not fails else f'{len(fails)} FAILED'))
sys.exit(1 if fails else 0)
