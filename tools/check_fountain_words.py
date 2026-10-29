#!/usr/bin/env python3
"""Banned-wording check for the Satoshi Fountain (reverse fountain) legal review.

Fails (exit 1) if any banned word appears in the built site output or in the Worker source strings.
Usage: python3 tools/check_fountain_words.py [SITE_DIR] [--worker /workspace/leaderboard/src]
Banned: pool, "your sats", "fountain balance", refill, donation(s), winner(s), jackpot(s), lottery, spin(s), slot(s),
casino(s), gamble/gambling (Grant's review of the random-amount giveaway).
Strict giveaway-copy check (only the giveaway UI itself, since the wider site legitimately says "Donated" statue and
"random device ID"): also donate/donated, win/winning, prize, random, lottery, jackpot, "free money", tip-to-unlock.
Scanned: fountain.js, the home-map giveaway callout block in index.html, each statue page's fountain section, and
the terms page and the Official Rules page (CSS stripped).
Two pre-existing, unrelated statue-history sentences (Vienna and Hong Kong pages describe the statues' own
donation history) are allow-listed by exact phrase; any other hit fails.
"""
import os, re, sys

BANNED = [r'\bpools?\b', r'your\s+sats', r'fountain\s+balance', r'\brefill', r'\bdonations?\b', r'\bwinners?\b',
          r'\bjackpots?\b', r'\blotter(?:y|ies)\b', r'\bspins?\b', r'\bslots?\b', r'\bcasinos?\b', r'\bgambl\w*']
ALLOW = ['Extra donations fund maintenance', 'in a donation ceremony', 'since the donation']
EXTS = ('.html', '.xml', '.js', '.mjs', '.json', '.txt', '.toml', '.sql')
SKIP_DIRS = {'.git', 'node_modules', '.wrangler', 'tools', 'test'}
SKIP_FILES = {'statues.json', 'merchants.json', 'lodging.json', 'photos.json', 'events.json', 'checkins.json'}  # sources, not built pages


def scan(root, skip_files=SKIP_FILES):
    hits = []
    pat = re.compile('|'.join(BANNED), re.I)
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(EXTS) or fn in skip_files:
                continue
            path = os.path.join(d, fn)
            text = open(path, encoding='utf-8', errors='replace').read()
            for a in ALLOW:
                text = text.replace(a, '')
            for m in pat.finditer(text):
                line = text.count('\n', 0, m.start()) + 1
                hits.append(f'{os.path.relpath(path, root)}:{line}: "{text[max(0, m.start() - 30):m.end() + 30].strip()}"')
    return hits


STRICT = BANNED + [r'\bdonat\w*', r'\bwin(?:s|ning|ners?)?\b', r'\bprizes?\b', r'\brandom\w*', r'\blotter\w*',
                   r'\bjackpots?\b', r'free\s+money', r'tip[\s-]+to[\s-]+unlock', r'\bprize\s+pool', r'\bspins?\b', r'\bslots?\b',
                   r'\bcasinos?\b', r'\bgambl\w*', r'\bbet(?:s|ting)?\b']
# The Official Rules must state the method plainly (Grant's draft), so these exact factual phrases are allowed there only.
RULES_ALLOW = ['receives a random amount from', 'cryptographic random number generator']


def giveaway_copy(root):
    """(label, text) pieces that are giveaway copy. Missing pieces are skipped (fountain off = nothing to scan)."""
    out = []
    read = lambda rel: open(os.path.join(root, rel), encoding='utf-8', errors='replace').read() if os.path.exists(os.path.join(root, rel)) else ''
    nostyle = lambda t: re.sub(r'<style>.*?</style>', '', t, flags=re.S)
    if read('fountain.js'):
        out.append(('fountain.js', read('fountain.js')))
    m = re.search(r'<style>\.gw-badge.*?</script>', read('index.html'), re.S)
    if m:
        out.append(('index.html (giveaway callouts)', m.group(0)))
    if read('rules/index.html'):
        t = nostyle(read('rules/index.html'))
        for a in RULES_ALLOW:
            t = t.replace(a, '')
        out.append(('rules/index.html', t))
    if read('terms/index.html'):
        out.append(('terms/index.html', nostyle(read('terms/index.html'))))
    for d in sorted(os.listdir(root)):
        m = re.search(r'<section class="fountain".*?</section>', read(os.path.join(d, 'index.html')), re.S) if os.path.isdir(os.path.join(root, d)) else None
        if m:
            out.append((f'{d}/index.html (fountain section)', nostyle(m.group(0))))
    return out


def scan_strict(root):
    pat = re.compile('|'.join(STRICT), re.I)
    hits = []
    for label, text in giveaway_copy(root):
        for m in pat.finditer(text):
            hits.append(f'{label}: "{text[max(0, m.start() - 30):m.end() + 30].strip()}"')
    return hits


def main():
    args = sys.argv[1:]
    worker = None
    if '--worker' in args:
        i = args.index('--worker'); worker = args[i + 1]; del args[i:i + 2]
    site = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hits = scan(site) + ['strict ' + h for h in scan_strict(site)]
    if worker:
        hits += ['worker/' + h for h in scan(worker, set())]
    if hits:
        print('banned wording found:'); print('\n'.join(hits)); sys.exit(1)
    print(f'banned-word check passed: {site}' + (f' + {worker}' if worker else ''))


if __name__ == '__main__':
    main()
