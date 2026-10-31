#!/usr/bin/env python3
"""Copy the Proof of Walk prism share cards into the site, recompressed.

Source: the variant renders (make_variants.py), <rank>/NN.jpg, 1280x720, NN = 01-21.
Target: img/pow-share/<rank>/NN.jpg (same size, baseline->progressive JPEG, quality Q, 4:2:0, metadata stripped).
build.py then makes one static share page per card (/proof-of-walk/share/<rank>/NN/).
Usage: python3 tools/import_prism_cards.py /path/to/variants [--quality 82]
"""
import os, sys
from PIL import Image

RANKS = ('confirmed', 'genesis-block', 'grand-high-order')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
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


if __name__ == '__main__':
    main()
