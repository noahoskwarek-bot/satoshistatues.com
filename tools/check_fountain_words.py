#!/usr/bin/env python3
"""Banned-wording check for the Satoshi Fountain (reverse fountain) legal review.

Fails (exit 1) if any banned word appears in the built site output or in the Worker source strings.
Usage: python3 tools/check_fountain_words.py [SITE_DIR] [--worker /workspace/leaderboard/src]
Banned: pool, "your sats", "fountain balance", refill, donation(s), winner(s).
Two pre-existing, unrelated statue-history sentences (Vienna and Hong Kong pages describe the statues' own
donation history) are allow-listed by exact phrase; any other hit fails.
"""
import os, re, sys

BANNED = [r'\bpools?\b', r'your\s+sats', r'fountain\s+balance', r'\brefill', r'\bdonations?\b', r'\bwinners?\b']
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


def main():
    args = sys.argv[1:]
    worker = None
    if '--worker' in args:
        i = args.index('--worker'); worker = args[i + 1]; del args[i:i + 2]
    site = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hits = scan(site)
    if worker:
        hits += ['worker/' + h for h in scan(worker, set())]
    if hits:
        print('banned wording found:'); print('\n'.join(hits)); sys.exit(1)
    print(f'banned-word check passed: {site}' + (f' + {worker}' if worker else ''))


if __name__ == '__main__':
    main()
