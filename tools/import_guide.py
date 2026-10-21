#!/usr/bin/env python3
"""Import trip-guide markdown files into statues.json `visit` objects (format: see GUIDES.md).

Usage: python3 tools/import_guide.py GUIDE.md [GUIDE.md ...]
Each file's name (without .md) must match a statue's `page` in statues.json.
Then run: BUILD_DATE=YYYY-MM-DD python3 build.py && python3 build.py --check
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECTIONS = {
    'getting there': 'getting_there', 'exact spot': 'exact_spot', 'photo tip': 'photo_tip',
    'hours & access': 'hours_access', 'nearby bitcoin places': 'nearby', 'nearby (btc map)': 'nearby',
    'sources': 'sources',
}
SKIP = ('intro and faq',)  # trailing optional section, not imported


def parse(md):
    visit = {}
    fm = re.match(r'---\n(.*?)\n---\n', md, re.S)
    if fm:
        for line in fm.group(1).splitlines():
            k, _, v = line.partition(':')
            k, v = k.strip(), v.strip()
            if k == 'updated':
                visit['updated'] = v
            elif k in ('public_access', 'free'):
                visit[k] = {'true': True, 'false': False}[v.lower()]
        md = md[fm.end():]
    cur, buf, out = None, [], {}
    for line in md.splitlines() + ['## __end__']:
        m = re.match(r'##\s+(.*)', line)
        if m:
            if cur:
                out[cur] = '\n'.join(buf).strip()
            title = m.group(1).strip().lower()
            if title.startswith(SKIP) or title == '__end__':
                cur = None
                if title != '__end__':
                    break
                continue
            if title not in SECTIONS:
                raise SystemExit(f'unknown section: {m.group(1)!r}')
            cur, buf = SECTIONS[title], []
        elif cur:
            buf.append(line)
    if cur:
        out[cur] = '\n'.join(buf).strip()
    for k in ('getting_there', 'exact_spot', 'photo_tip', 'hours_access'):
        if out.get(k):
            visit[k] = re.sub(r'\n{3,}', '\n\n', out[k])
    if 'nearby' in out:
        items, notes = [], []
        for p in re.split(r'\n\s*\n', out['nearby']):
            p = ' '.join(p.split())
            if not p:
                continue
            md_link = re.match(r'-\s*\[(.+?)\]\((\S+?)\)\s*(?:[–-]\s*(.*))?$', p)
            parts = [x.strip() for x in p.split(' | ')]
            if md_link:
                items.append({'name': md_link.group(1), 'url': md_link.group(2), 'note': md_link.group(3) or ''})
            elif len(parts) >= 2 and parts[1].startswith('http'):
                items.append({'name': parts[0], 'url': parts[1], 'note': ' | '.join(parts[2:])})
            else:
                notes.append(p)
        for it in items:
            if not it['note']:
                del it['note']
        if items:
            visit['nearby'] = items
        # free-text notes in that section are ignored: the BTC Map list is automatic (merchants.json, see GUIDES.md)
    if 'sources' in out:
        srcs = []
        for p in out['sources'].splitlines():
            p = p.strip()
            if not p:
                continue
            md_link = re.match(r'-\s*\[(.+?)\]\((\S+?)\)$', p)
            if md_link:
                srcs.append({'label': md_link.group(1), 'url': md_link.group(2)})
                continue
            label, sep, url = p.rpartition(' | ')
            if not sep or not url.startswith('http'):
                raise SystemExit(f'bad source line: {p!r}')
            srcs.append({'label': label.strip(), 'url': url.strip()})
        visit['sources'] = srcs
    order = ['updated', 'getting_there', 'exact_spot', 'photo_tip', 'hours_access', 'nearby', 'nearby_note', 'sources', 'public_access', 'free']
    return {k: visit[k] for k in order if k in visit}


def main(paths):
    p = os.path.join(HERE, 'statues.json')
    data = json.load(open(p, encoding='utf-8'))
    by_page = {s['page']: s for s in data['statues']}
    for path in paths:
        slug = os.path.splitext(os.path.basename(path))[0]
        if slug not in by_page:
            raise SystemExit(f'{path}: no statue with page {slug!r}')
        by_page[slug]['visit'] = parse(open(path, encoding='utf-8').read())
        v = by_page[slug]['visit']
        print(f'{slug}: {", ".join(k for k in v)} ({len(v.get("nearby", []))} nearby, {len(v.get("sources", []))} sources)')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main(sys.argv[1:])
