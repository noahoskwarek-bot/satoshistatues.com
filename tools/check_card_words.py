#!/usr/bin/env python3
"""Card copy word check (combined-cards spec §3.3 / §5.6 + Grant's fountain list) for the combined Proof of Walk card.

Scans the card surfaces only: /proof-of-walk/cards/, the 33 statue x rank share pages, /v/, pow-card.js and
proof-of-walk/card-data.js (visible text; CSS stripped). Fails on: jackpot, odds, bet, win, luck(y), donation/donate,
worth, resale, limited edition, chance, value, prize, pool, "your sats", "fountain balance", refill, winner, lottery,
spin(s), slot(s), casino, gamble. No exceptions.
Print copy (the "Get a print" panel in pow-card.js, card-data.js print_* fields, the print lines on the cards page and
build.py's CARD_PRINT_NOTE even while ordering is switched off) is also checked for draw, giveaway, 1,021 and random
(Noah 2026-10-31 2:26 PM ET).
Usage: python3 tools/check_card_words.py [SITE_DIR]
"""
import os, re, sys

BAD = [r'\bjackpots?\b', r'\bodds\b', r'\bbet(?:s|ting)?\b', r'\bwin(?:s|ning)?\b', r'\bluck\w*', r'\bdonat\w*', r'\bworth\b', r'\bresale\b',
       r'limited\s+edition', r'\bchances?\b', r'\bvalue\b', r'\bprizes?\b', r'\bpools?\b', r'your\s+sats', r'fountain\s+balance', r'\brefill',
       r'\bwinners?\b', r'\blotter\w*', r'\bspins?\b', r'\bslots?\b', r'\bcasinos?\b', r'\bgambl\w*']
ALLOW = []
PRINT_BAD = BAD + [r'\bdraw\w*', r'\bgiveaway\w*', r'1,?021', r'\brandom\w*']


def print_copy(root):
    """(label, text) pieces that are print copy."""
    out = []
    js = open(os.path.join(root, 'pow-card.js'), encoding='utf-8').read()
    m = re.search(r"'<section class=\"pc-print\".*?</section>'", js, re.S)
    assert m, 'print panel not found in pow-card.js'
    out.append(('pow-card.js (Get a print panel)', m.group(0)))
    data = open(os.path.join(root, 'proof-of-walk', 'card-data.js'), encoding='utf-8').read()
    out += [('card-data.js ' + k, v) for k, v in re.findall(r'"(print_\w*)":"((?:[^"\\]|\\.)*)"', data)]
    page = open(os.path.join(root, 'proof-of-walk', 'cards', 'index.html'), encoding='utf-8').read()
    out += [('cards page', p) for p in re.findall(r'<p[^>]*>[^<]*(?:<[^/p][^>]*>[^<]*</[^>]+>[^<]*)*print[^<]*.*?</p>', page, re.I | re.S)]
    bp = os.path.join(root, 'build.py')
    if os.path.exists(bp):
        m = re.search(r"CARD_PRINT_NOTE = \((.*?)\)\n", open(bp, encoding='utf-8').read(), re.S)
        if m:
            out.append(('build.py CARD_PRINT_NOTE (shown only when ordering opens)', m.group(1)))
    return out


def files(root):
    out = [os.path.join(root, p) for p in ('proof-of-walk/cards/index.html', 'v/index.html', 'pow-card.js', 'proof-of-walk/card-data.js')]
    sh = os.path.join(root, 'proof-of-walk', 'share')
    for rank in ('confirmed', 'genesis-block', 'grand-high-order'):
        for d in sorted(os.listdir(os.path.join(sh, rank))):
            if not d.isdigit() and os.path.isdir(os.path.join(sh, rank, d)):
                out.append(os.path.join(sh, rank, d, 'index.html'))
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    pat, hits, fs = re.compile('|'.join(BAD), re.I), [], files(root)
    for f in fs:
        t = open(f, encoding='utf-8').read()
        t = re.sub(r'<style>.*?</style>', '', t, flags=re.S)
        t = re.sub(r"var CSS = '.*?';", '', t)
        t = re.sub(r'(?m)^\s*//.*$', '', t)      # code comments (they quote the word list itself)
        t = re.sub(r'\.value\b', '.v', t)        # DOM/Intl property name, not copy
        for a in ALLOW:
            t = t.replace(a, '')
        for m in pat.finditer(t):
            hits.append(f'{os.path.relpath(f, root)}:{t.count(chr(10), 0, m.start()) + 1}: "{t[max(0, m.start() - 30):m.end() + 30].strip()}"')
    pp = re.compile('|'.join(PRINT_BAD), re.I)
    pieces = print_copy(root)
    for label, t in pieces:
        for m in pp.finditer(t):
            hits.append(f'{label}: "{t[max(0, m.start() - 30):m.end() + 30].strip()}"')
    if hits:
        print('card word check FAILED:\n  ' + '\n  '.join(hits)); sys.exit(1)
    print(f'card word check passed ({len(fs)} files, {len(pieces)} print-copy pieces)')


if __name__ == '__main__':
    main()
