#!/usr/bin/env python3
"""Copy the Proof of Walk prism share cards into the site, recompressed.

Source: the variant renders (make_variants.py), <rank>/NN.jpg, 1280x720, NN = 01-21.
Target: img/pow-share/<rank>/NN.jpg (same size, baseline->progressive JPEG, quality Q, 4:2:0, metadata stripped).
build.py then makes one static share page per card (/proof-of-walk/share/<rank>/NN/).
Also writes the 640x360 thumbnails used by /proof-of-walk/cards/: img/pow-share/thumbs/confirmed/NN.jpg (the gallery set)
and img/pow-share/thumbs/<rank>.jpg (the three base rank cards). Thumbnails only: python3 tools/import_prism_cards.py --thumbs
Usage: python3 tools/import_prism_cards.py /path/to/variants [--quality 82]
"""
import os, sys
from PIL import Image

RANKS = ('confirmed', 'genesis-block', 'grand-high-order')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


THUMB_RANK, THUMB = 'confirmed', (640, 360)


def thumbs(q=78):
    out = os.path.join(ROOT, 'img', 'pow-share', 'thumbs')
    os.makedirs(os.path.join(out, THUMB_RANK), exist_ok=True)
    jobs = [(os.path.join(ROOT, 'img', 'pow-share', THUMB_RANK, f'{n:02d}.jpg'), os.path.join(out, THUMB_RANK, f'{n:02d}.jpg')) for n in range(1, 22)]
    jobs += [(os.path.join(ROOT, 'img', 'pow-share', f'{r}.jpg'), os.path.join(out, f'{r}.jpg')) for r in RANKS]
    tot = 0
    for a, b in jobs:
        Image.open(a).convert('RGB').resize(THUMB, Image.LANCZOS).save(b, 'JPEG', quality=q, optimize=True, progressive=True)
        tot += os.path.getsize(b)
    print(f'{len(jobs)} thumbnails: {tot/1e3:.0f} KB')


def main():
    if '--thumbs' in sys.argv:
        return thumbs()
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    q = int(sys.argv[sys.argv.index('--quality') + 1]) if '--quality' in sys.argv else 82
    src = args[0]
    tot_in = tot_out = 0
    for r in RANKS:
        os.makedirs(os.path.join(ROOT, 'img', 'pow-share', r), exist_ok=True)
        for n in range(1, 22):
            a = os.path.join(src, r, f'{n:02d}.jpg'); b = os.path.join(ROOT, 'img', 'pow-share', r, f'{n:02d}.jpg')
            im = Image.open(a).convert('RGB')
            assert im.size == (1280, 720), (a, im.size)
            im.save(b, 'JPEG', quality=q, optimize=True, progressive=True, subsampling='4:2:0')
            tot_in += os.path.getsize(a); tot_out += os.path.getsize(b)
    print(f'63 cards: {tot_in/1e6:.2f} MB -> {tot_out/1e6:.2f} MB (quality {q})')
    thumbs()


if __name__ == '__main__':
    main()
