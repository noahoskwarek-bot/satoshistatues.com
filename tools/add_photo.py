#!/usr/bin/env python3
"""Add an approved visitor photo to a statue page.

    python3 tools/add_photo.py INPUT.jpg SLUG --credit "Nickname" --month 2026-10 [--dry-run]

* Applies the camera orientation, resizes to at most 1600 px on the long edge (plus a 640 px "-sm" thumbnail)
  and saves compressed JPEG (quality 82, progressive).
* Strips ALL metadata (EXIF incl. GPS, XMP, IPTC, ICC, comments) by re-encoding only the pixels, then re-opens the
  output and refuses to continue if any EXIF/GPS/XMP/IPTC/comment data remains.
* Writes photos/<slug>/<slug>-<month>-<n>.jpg, adds {"slug", "file", "credit", "month", "approved": true, "w", "h"} to
  photos.json, and moves statues.json last_confirmed to the photo month (source visitor_photo) only if the photo is
  newer. build.py also derives this from the newest approved photo, so the two always agree.
Then run: python3 build.py && python3 build.py --check
"""
import argparse
import json
import os
import re
import sys

from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_EDGE, THUMB_EDGE, QUALITY = 1600, 640, 82


def load_json(path):
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    return json.loads(txt), txt.endswith('\n')


def save_json(path, data, nl):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + ('\n' if nl else ''))


def clean_copy(img, edge):
    img = ImageOps.exif_transpose(img)  # bake in orientation before the EXIF goes
    if img.mode not in ('RGB', 'L'):
        bg = Image.new('RGB', img.size, (13, 17, 23))
        img = img.convert('RGBA')
        bg.paste(img, mask=img.split()[-1])
        img = bg
    img = img.convert('RGB')
    img.thumbnail((edge, edge), Image.LANCZOS)
    out = Image.new('RGB', img.size)  # fresh image: pixels only, no .info / metadata carried over
    out.paste(img)
    return out


def save_clean(img, path):
    img.save(path, 'JPEG', quality=QUALITY, optimize=True, progressive=True, exif=b'', icc_profile=None)


def verify_clean(path):
    with Image.open(path) as im:
        exif = im.getexif()
        problems = []
        if len(exif):
            problems.append(f'EXIF tags: {list(exif.keys())[:10]}')
        if exif.get_ifd(0x8825):
            problems.append('GPS IFD present')
        for k in ('exif', 'xmp', 'XML:com.adobe.xmp', 'photoshop', 'icc_profile', 'comment', 'gps'):
            if im.info.get(k):
                problems.append(f'info[{k}]')
        if getattr(im, 'applist', None):
            bad = [m for m, _ in im.applist if m not in ('APP0',)]
            if bad:
                problems.append(f'segments {bad}')
    raw = open(path, 'rb').read()
    for marker in (b'Exif\x00\x00', b'http://ns.adobe.com/xap', b'Photoshop 3.0', b'ICC_PROFILE'):
        if marker in raw:
            problems.append(f'bytes {marker!r}')
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('slug')
    ap.add_argument('--credit', default='Anonymous', help='nickname shown under the photo (default Anonymous)')
    ap.add_argument('--month', required=True, help='month the photo was taken, YYYY-MM')
    ap.add_argument('--root', default=ROOT, help=argparse.SUPPRESS)  # for tests on a copy of the repo
    ap.add_argument('--dry-run', action='store_true', help='process and verify the image only; write nothing')
    a = ap.parse_args()
    root = a.root
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', a.month):
        sys.exit('--month must be YYYY-MM')
    credit = re.sub(r'\s+', ' ', a.credit).strip()[:40] or 'Anonymous'
    statues, s_nl = load_json(os.path.join(root, 'statues.json'))
    st = next((s for s in statues['statues'] if s['page'] == a.slug), None)
    if not st:
        sys.exit(f'unknown slug {a.slug!r}; use one of: ' + ', '.join(s['page'] for s in statues['statues']))
    ppath = os.path.join(root, 'photos.json')
    photos, p_nl = load_json(ppath) if os.path.exists(ppath) else ({'photos': []}, True)

    d = os.path.join(root, 'photos', a.slug)
    n = 1
    while os.path.exists(os.path.join(d, f'{a.slug}-{a.month}-{n}.jpg')) or any(
            p['file'] == f'{a.slug}-{a.month}-{n}.jpg' and p['slug'] == a.slug for p in photos['photos']):
        n += 1
    name = f'{a.slug}-{a.month}-{n}'
    with Image.open(a.input) as src:
        src.load()
        full, thumb = clean_copy(src, MAX_EDGE), clean_copy(src, THUMB_EDGE)
    tmpdir = d if not a.dry_run else '/tmp'
    os.makedirs(tmpdir, exist_ok=True)
    fpath, tpath = os.path.join(tmpdir, name + '.jpg'), os.path.join(tmpdir, name + '-sm.jpg')
    save_clean(full, fpath)
    save_clean(thumb, tpath)
    for pth in (fpath, tpath):
        probs = verify_clean(pth)
        if probs:
            os.remove(fpath); os.remove(tpath)
            sys.exit(f'metadata still present in {pth}: {probs}; nothing was added')
    print(f'ok: {fpath} {full.size[0]}x{full.size[1]} {os.path.getsize(fpath)//1024} KB, thumb {thumb.size[0]}x{thumb.size[1]}, no EXIF/GPS/XMP')
    if a.dry_run:
        os.remove(fpath); os.remove(tpath)
        print('dry run: nothing written')
        return
    photos['photos'].append({'slug': a.slug, 'file': name + '.jpg', 'credit': credit, 'month': a.month,
                             'approved': True, 'w': full.size[0], 'h': full.size[1]})
    save_json(ppath, photos, p_nl)
    print('added to photos.json')
    if (st.get('last_confirmed') or '') <= a.month:
        st['last_confirmed'], st['last_confirmed_source'] = a.month, 'visitor_photo'
        st['last_confirmed_url'] = f'/{a.slug}/#visitor-photos'
        st.pop('last_confirmed_kind', None)
        save_json(os.path.join(root, 'statues.json'), statues, s_nl)
        print(f'statues.json: {a.slug} last_confirmed → {a.month} (visitor_photo)')
    else:
        print(f'statues.json unchanged: last_confirmed {st["last_confirmed"]} is newer than {a.month}')
    print('next: python3 build.py && python3 build.py --check')


if __name__ == '__main__':
    main()
