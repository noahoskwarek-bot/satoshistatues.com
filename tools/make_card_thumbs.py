#!/usr/bin/env python3
"""Passport card-grid thumbnails: img/cards/art/<page>.jpg (1200x1600) -> img/cards/art/thumb/<page>.jpg (240x320, q78).
Run by hand after adding or changing card art; the files are committed (GitHub Pages has no image pipeline)."""
import os, sys
from PIL import Image
root = sys.argv[1] if len(sys.argv) > 1 else '.'
src = os.path.join(root, 'img', 'cards', 'art'); dst = os.path.join(src, 'thumb'); os.makedirs(dst, exist_ok=True)
for f in sorted(os.listdir(src)):
    if not f.endswith('.jpg'):
        continue
    im = Image.open(os.path.join(src, f)).convert('RGB'); im.thumbnail((240, 320), Image.LANCZOS)
    im.save(os.path.join(dst, f), 'JPEG', quality=78, optimize=True, progressive=True)
    print('thumb', f, im.size, os.path.getsize(os.path.join(dst, f)))
