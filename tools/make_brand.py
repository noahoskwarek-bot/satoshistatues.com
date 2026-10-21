#!/usr/bin/env python3
"""Generate the satoshistatues.com logo files from the hand-written pin path below.

  python3 tools/make_brand.py          # writes brand/*.svg, favicons, apple-touch-icon, brand/pin-512.png, brand/icon-512.png
  python3 tools/make_brand.py --og     # also rebuilds /og-image.jpg (main share image) from brand/og-photos.jpg

The wordmark is converted to outlines from the self-hosted Inter ExtraBold (fonts/inter-800.woff),
so the SVGs need no web font. Needs fontTools, Pillow and cairosvg (only for the PNG/ICO renders).
Run `python3 build.py` afterwards: the per-statue OG images use brand/pin-512.png.
"""
import io
import os
import sys

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORANGE, WHITE, DARK = '#F7931A', '#FFFFFF', '#0D1117'

# Map pin with a hooded Satoshi cut out of it (negative space), drawn on a 100 x 140 grid.
# Subpaths: pin outline, hood opening, left and right shoulder cuts (ends lie on the outline); evenodd = holes.
PIN_W, PIN_H = 100, 140
PIN_D = ('M50 138C45 126 6 84 6 50a44 44 0 0 1 88 0c0 34-39 76-44 88Z'
         'M31 44Q50 32 69 44Q74 48 72 55Q64 76 50 94Q36 76 28 55Q26 48 31 44Z'
         'M11.12 73.8Q19.69 62.59 29.5 62L29.5 66.5Q21.89 66.8 13.36 79.14Z'
         'M88.88 73.8Q80.31 62.59 70.5 62L70.5 66.5Q78.11 66.8 86.64 79.14Z')
# Favicon variant: same outline and hood, wider shoulder cuts so they survive at 16-32 px.
PIN_D_SMALL = ('M50 138C45 126 6 84 6 50a44 44 0 0 1 88 0c0 34-39 76-44 88Z'
               'M30 43Q50 30 70 43Q76 48 73 56Q65 77 50 96Q35 77 27 56Q24 48 30 43Z'
               'M10.6 72.4Q19 60.5 28.5 60L29 68Q21.5 68.5 14.2 81.6Z'
               'M89.4 72.4Q81 60.5 71.5 60L71 68Q78.5 68.5 85.8 81.6Z')


def f(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


def word_path(font, text, x, baseline, cap, tracking):
    """Outline `text` at cap height `cap` (px) starting at x; returns (path d, advance width)."""
    gs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = cap / font['OS/2'].sCapHeight
    pen = SVGPathPen(gs, ntos=f)
    cx = x
    for i, ch in enumerate(text):
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, cx, baseline)))
        cx += gs[g].width * scale + (tracking if i < len(text) - 1 else 0)
    return pen.getCommands(), cx - x


def lockup_svg(font, title='Satoshi Nakamoto Statues', ink=None):
    # Pin 88 px tall at the left; SATOSHI (white) over STATUES (orange, tracked out), like the concept.
    ph = 88.0
    s = ph / PIN_H
    pw = PIN_W * s
    tx = pw + 16
    cap1, cap2 = 36.0, 24.0
    top = 13.0
    d1, w1 = word_path(font, 'SATOSHI', tx, top + cap1, cap1, 1.5)
    # fit STATUES to ~80% of the SATOSHI width by tracking
    _, w2_0 = word_path(font, 'STATUES', tx, 0, cap2, 0)
    track2 = max(2.0, (w1 * 0.80 - w2_0) / 6)
    d2, w2 = word_path(font, 'STATUES', tx, top + cap1 + 12 + cap2, cap2, track2)
    W = round(tx + max(w1, w2) + 2)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {round(ph)}" width="{W}" height="{round(ph)}" role="img" aria-labelledby="t">
  <title id="t">{title}</title>
  <path fill="{ORANGE}" fill-rule="evenodd" transform="scale({f(s)})" d="{PIN_D}"/>
  <path fill="{ink or WHITE}" d="{d1}"/>
  <path fill="{ORANGE}" d="{d2}"/>
</svg>
''', W, round(ph)


def pin_svg(d=PIN_D, title='Satoshi Statues'):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {PIN_W} {PIN_H}" width="{PIN_W}" height="{PIN_H}" role="img" aria-labelledby="t">
  <title id="t">{title}</title>
  <path fill="{ORANGE}" fill-rule="evenodd" d="{d}"/>
</svg>
'''


def icon_svg(size=64, pad=0.08, d=PIN_D_SMALL, radius=0.22):
    """Orange pin on a dark rounded square (favicon / app icon)."""
    h = size * (1 - 2 * pad)
    s = h / PIN_H
    x = (size - PIN_W * s) / 2
    y = size * pad
    r = f' rx="{f(size * radius)}"' if radius else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <rect width="{size}" height="{size}"{r} fill="{DARK}"/>
  <path fill="{ORANGE}" fill-rule="evenodd" transform="translate({f(x)} {f(y)}) scale({f(s)})" d="{d}"/>
</svg>
'''


def png(svg, w, h=None, bg=None):
    import cairosvg
    from PIL import Image
    b = cairosvg.svg2png(bytestring=svg.encode(), output_width=w, output_height=h, background_color=bg)
    return Image.open(io.BytesIO(b)).convert('RGBA')


def write(rel, data):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    mode = 'wb' if isinstance(data, bytes) else 'w'
    with open(p, mode, **({} if mode == 'wb' else {'encoding': 'utf-8'})) as fh:
        fh.write(data)
    print('wrote', rel)


def save_png(img, rel):
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    write(rel, buf.getvalue())


def og_main(font):
    """Main share image (1200x630): lockup + headline on the left, statue photo collage on the right."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W, H = 1200, 630
    bg = (13, 17, 23)
    im = Image.new('RGB', (W, H), bg)
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-260, -300, 520, 380), fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    im = Image.composite(Image.new('RGB', (W, H), (247, 147, 26)), im, glow)
    photos = Image.open(os.path.join(ROOT, 'brand', 'og-photos.jpg')).convert('RGB')
    fade = Image.new('L', photos.size, 255)
    fd = ImageDraw.Draw(fade)
    for x in range(48):  # blend the collage's own background into the glow
        fd.line([(x, 0), (x, H)], fill=round(255 * x / 48))
    im.paste(photos, (W - photos.width, 0), fade)
    svg, lw, lh = lockup_svg(font)
    logo = png(svg, round(lw * 1.25))
    im.paste(logo, (70, 70), logo)
    d = ImageDraw.Draw(im)
    fb = ImageFont.truetype(os.path.join(ROOT, 'fonts', 'inter-800.woff'), 58)
    fr = ImageFont.truetype(os.path.join(ROOT, 'fonts', 'inter-500.woff'), 30)
    y = 236
    for line in ('Satoshi Nakamoto', 'Statues'):
        d.text((70, y), line, font=fb, fill=(230, 237, 243)); y += 70
    y += 18
    for line in ('Every Satoshi statue on Earth, on one', 'world map. Collect stamps in your', 'Satoshi Passport.'):
        d.text((70, y), line, font=fr, fill=(201, 209, 217)); y += 40
    d.rectangle((0, 0, W, 8), fill=(247, 147, 26))
    d.text((70, H - 62), 'satoshistatues.com', font=ImageFont.truetype(os.path.join(ROOT, 'fonts', 'inter-800.woff'), 34),
           fill=(247, 147, 26), anchor='ls')
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=86, optimize=True, progressive=True)
    write('og-image.jpg', buf.getvalue())


def main():
    font = TTFont(os.path.join(ROOT, 'fonts', 'inter-800.woff'))
    lock, lw, lh = lockup_svg(font)
    write('brand/logo-lockup.svg', lock)
    # dark-ink variant for light backgrounds (printable passport)
    write('brand/logo-lockup-light.svg', lockup_svg(font, ink='#0D1117')[0])
    write('brand/pin.svg', pin_svg())
    fav = icon_svg(64)
    write('favicon.svg', fav)
    write('brand/favicon.svg', fav)
    from PIL import Image
    save_png(png(icon_svg(32), 32), 'favicon-32.png')
    ico = png(icon_svg(48), 48)
    buf = io.BytesIO()
    ico.save(buf, 'ICO', sizes=[(16, 16), (32, 32), (48, 48)])
    write('favicon.ico', buf.getvalue())
    # iOS rounds the corners itself: full-bleed dark square, pin a bit smaller
    save_png(png(icon_svg(180, pad=0.14, d=PIN_D, radius=0), 180).convert('RGB'), 'apple-touch-icon.png')
    save_png(png(pin_svg(), 512 * PIN_W // PIN_H, 512), 'brand/pin-512.png')
    save_png(png(icon_svg(512, pad=0.12, d=PIN_D, radius=0), 512).convert('RGB'), 'brand/icon-512.png')  # JSON-LD logo, feed icon
    save_png(png(lock, lw * 4), 'brand/logo-lockup.png')
    if '--og' in sys.argv:
        og_main(font)


if __name__ == '__main__':
    main()
