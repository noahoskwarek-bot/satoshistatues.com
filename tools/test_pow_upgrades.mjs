// Site-side checks for the 2026-11-27 Proof of Walk upgrades (PREVIEW): "Post on X" tags, walker line in
// share text, statue-page First 21 section, data-host-x. Run: node tools/test_pow_upgrades.mjs (after python3 build.py).
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const R = new URL('..', import.meta.url).pathname;
const read = p => readFileSync(R + p, 'utf8');
const statues = JSON.parse(read('statues.json')).statues;
const BAD = /\b(prizes?|win(s|ner|ners|ning)?|odds|lucky|luck|giveaway\w*|reward\w*|jackpot|worth|value|valuable|bet|chances?)\b/i;
const HOSTS = { tokyo: '@TBB_EN', 'el-zonte': '@Bitcoinbeach', lugano: '@LuganoPlanB', 'buenos-aires': '@BitcoinAR' };

function powCard() {
  const el = () => ({ appendChild() {}, setAttribute() {}, style: {} });
  const sb = { console, Promise, setTimeout, Intl, Date, Math, JSON, encodeURIComponent };
  sb.window = sb;
  sb.document = { currentScript: null, createElement: el, getElementById: () => null, head: el(), fonts: { add() {} }, querySelectorAll: () => [], addEventListener() {} };
  sb.navigator = {}; sb.location = { origin: 'https://www.satoshistatues.com', href: 'https://www.satoshistatues.com/' };
  vm.createContext(sb);
  vm.runInContext(read('proof-of-walk/card-data.js'), sb);
  vm.runInContext(read('pow-card.js'), sb);
  return sb.PowCard;
}

test('pow-card.js shareText: always @satoshistatue21, + local host only where statues.json has one', () => {
  const P = powCard();
  for (const slug of ['tokyo', 'el-zonte', 'lugano', 'buenos-aires', 'budapest', 'vienna', 'hanoi']) {
    const t = P.shareText({ rank: 'Confirmed', slug, n: 2, code: 'PW-AAAA-BBBB', earns: false });
    assert.match(t, /@satoshistatue21\b/, slug);
    if (HOSTS[slug]) assert.ok(t.endsWith(' ' + HOSTS[slug]), t);
    else assert.doesNotMatch(t.replace('@satoshistatue21', ''), /@\w/, t);
    assert.equal(t.match(/@satoshistatue21/g).length, 1);
    assert.doesNotMatch(t, BAD);
  }
});
test('pow-card.js shareText: walker line when the card carries it; never an event stamp', () => {
  const P = powCard();
  const t = P.shareText({ rank: 'Confirmed', slug: 'tokyo', n: 2, code: 'PW-AAAA-BBBB', earns: true, walker: 1, event_badge: "Bitcoin Japan '26" });
  assert.match(t, /Walker #1 in Tokyo/); assert.doesNotMatch(t, /Bitcoin Japan|🎟/); assert.match(t, /@satoshistatue21 @TBB_EN$/);
  assert.equal(P.walkerLine({ slug: 'tokyo', walker: 'x' }), '');
  assert.equal(P.xTags('hi @satoshistatue21 @tbb_en', 'tokyo'), 'hi @satoshistatue21 @tbb_en');     // no duplicates
});
test('checkin.js ciXTags: same rule, host from data-host-x', () => {
  const src = read('checkin.js'), m = src.match(/function ciXTags[\s\S]*?\n}\n/);
  const f = vm.runInNewContext('(' + m[0].replace('function ciXTags', 'function') + ')');
  assert.equal(f('I just checked in ⚡', { hostX: '@TBB_EN' }), 'I just checked in ⚡ @satoshistatue21 @TBB_EN');
  assert.equal(f('I just checked in ⚡', { hostX: '' }), 'I just checked in ⚡ @satoshistatue21');
  assert.equal(f('x @satoshistatue21', { hostX: 'not a handle!' }), 'x @satoshistatue21');
});
test('statues.json local_host_x: only the verified set, each with a source', () => {
  const got = Object.fromEntries(statues.filter(s => s.local_host_x).map(s => [s.page, s.local_host_x]));
  assert.deepEqual(got, HOSTS);
  for (const s of statues.filter(s => s.local_host_x)) assert.ok((s.local_host_x_source || '').length > 10, s.page);
});
test('built statue pages: Post on X link tags, data-host-x, First 21 section (claimable vs not installed)', () => {
  assert.equal(statues.length, 14);
  for (const s of statues) {
    const p = s.page + '/index.html'; assert.ok(existsSync(R + p), p);
    const h = read(p);
    const intent = h.match(/href="https:\/\/x\.com\/intent\/(?:post|tweet)\?text=([^"&]+)/);
    assert.ok(intent, p + ' share link');
    const text = decodeURIComponent(intent[1].replace(/&amp;/g, '&'));
    assert.match(text, /@satoshistatue21/, p);
    if (HOSTS[s.page]) { assert.ok(text.includes(HOSTS[s.page]), p); assert.match(h, new RegExp(`data-host-x="${HOSTS[s.page]}"`)); }
    else assert.doesNotMatch(h, /data-host-x="@/, p);
    assert.match(h, /class="fw"|id="first-21"/, p + ' First 21 section');
    assert.match(h, /0 \/ 21/, p);
    const checkable = ['Installed', 'Restored', 'Damaged', 'Donated'].includes(s.status);
    assert.equal(/\/api\/pow\/first21/.test(h), checkable, p + ' First 21 fetch only where check-in exists');
    const sec = h.slice(h.indexOf('First 21'), h.indexOf('First 21') + 3000);
    assert.doesNotMatch(sec, BAD, p);
  }
});
test('verify page + proof-of-walk page pass walker / event fields through', () => {
  const v = read('v/index.html'); assert.match(v, /walker_line/); assert.doesNotMatch(v, /event_badge|event stamp|🎟/i);
  const pw = read('proof-of-walk/index.html'); assert.match(pw, /walker: sc\.walker/);
  const home = read('index.html'); assert.match(home, /walker: Number\(sc\.walker\)/); assert.match(home, /local_host_x/);
});
test('build.py x_tags (python)', () => {
  const out = execFileSync('python3', ['-c', `import build,json;print(json.dumps([build.x_tags('A', {'local_host_x':'@TBB_EN'}), build.x_tags('A @satoshistatue21', {}), build.x_tags('A @tbb_en', {'local_host_x':'@TBB_EN'})]))`], { cwd: R }).toString();
  assert.deepEqual(JSON.parse(out), ['A @satoshistatue21 @TBB_EN', 'A @satoshistatue21', 'A @tbb_en @satoshistatue21']);
});
test('card front stays clean (no walker number); the back carries Walker #N (Noah 2026-11-27 8:37 AM ET)', () => {
  const src = read('pow-card.js');
  const body = name => { const i = src.indexOf('  async function ' + name + '('); const j = src.indexOf('\n  }\n', i); return src.slice(i, j); };
  const front = body('front'), back = body('back');
  assert.ok(front.length > 500 && back.length > 500);
  assert.doesNotMatch(front, /serialOf|walkerLine|badgeOf|marks\(|EVENT STAMP|WALKER #/);
  assert.doesNotMatch(src, /function marks\(|function pill\(|EVENT STAMP/);
  assert.match(back, /' · Walker #' \+ serialOf\(card\)/); assert.doesNotMatch(back, /badge|event/i);
});
test('event stamps removed everywhere (Noah 2026-11-27 8:38 AM ET: “I don’t want event stamp”)', () => {
  assert.doesNotMatch(read('events.json'), /major_badge/);
  for (const p of ['pow-card.js', 'checkin.js', 'index.html', 'build.py', 'EVENTS.md', 'v/index.html', 'proof-of-walk/index.html', 'tokyo/index.html', 'lugano/index.html'])
    assert.doesNotMatch(read(p), /major_badge|event_badge|badgeOf|MAJOR_EVENTS|events\.gen|🎟|event stamp/i, p);
});

// ---------- "Stamp your @handle" on the card reveal (PREVIEW, Noah via Matt 2026-11-27) ----------
// Browser test: the real pow-card.js mounted in headless Chrome against a tiny local server (site files + a stub
// /api/x/start). Skips if Playwright/Chrome aren't on this machine.
const PW = '/usr/local/lib/pnpm/5/.pnpm/playwright-core@1.59.1/node_modules/playwright-core';
const BAD_COPY = /\b(prizes?|win(s|ner|ners|ning)?|odds|lucky|luck|giveaway\w*|reward\w*|jackpot|worth|value|valuable|bet|chances?|earn\s+\w+\s+sats)\b/i;
async function withBrowser(fn) {
  const { createRequire } = await import('node:module'); const require = createRequire(import.meta.url);
  const http = await import('node:http'); const { chromium } = require(PW);
  const starts = [];
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    if (u.pathname === '/api/x/start') { let b = ''; req.on('data', c => b += c); req.on('end', () => { starts.push(JSON.parse(b || '{}')); res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ ok: true, url: '/__x-signin?state=test' })); }); return; }
    if (u.pathname === '/__x-signin' || u.pathname === '/__t') { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end('<!doctype html><body><div id="m"></div></body>'); return; }
    const f = R + decodeURIComponent(u.pathname).replace(/^\//, '');
    if (!existsSync(f) || f.endsWith('/')) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': f.endsWith('.js') ? 'text/javascript' : f.endsWith('.json') ? 'application/json' : f.endsWith('.woff2') ? 'font/woff2' : f.endsWith('.jpg') ? 'image/jpeg' : 'application/octet-stream' });
    res.end(readFileSync(f));
  });
  await new Promise(ok => srv.listen(0, '127.0.0.1', ok));
  const base = 'http://127.0.0.1:' + srv.address().port, br = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  try { return await fn({ br, base, starts }); } finally { await br.close(); srv.close(); }
}
async function mountCard(br, base, card, width = 390) {
  const pg = await (await br.newContext({ viewport: { width, height: 900 } })).newPage();
  await pg.goto(base + '/__t');
  await pg.evaluate(async ({ card }) => {
    localStorage.setItem('satoshiDevice.v1', 'test-device-abcdefghijklmnop'); window.SS_API = location.origin;
    const add = src => new Promise((ok, bad) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
    await add('/proof-of-walk/card-data.js'); await add('/pow-card.js');
    await window.PowCard.mount(document.getElementById('m'), card);
  }, { card });
  return pg;
}
const CARD = { rank: 'confirmed', slug: 'tokyo', n: 10, at: Date.parse('2026-11-27T01:15:00Z'), code: 'PW-HTBJ-1SVJ', earns: true, walker: 2 };
const canRun = existsSync(PW) && existsSync('/usr/bin/google-chrome');

test('Stamp your @handle: unlinked walker sees it right next to Post on X, same size, row not broken (390px + desktop)', { skip: !canRun && 'no Playwright/Chrome' }, async () => {
  await withBrowser(async ({ br, base }) => {
    for (const w of [390, 1280]) {
      const pg = await mountCard(br, base, CARD, w);
      const r = await pg.evaluate(() => {
        const box = s => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height, t: e.textContent.trim(), p: e.parentElement.className }; };
        return { x: box('[data-pc="x"]'), s: box('[data-pc="stamp"]'), save: box('[data-pc="save"]'), copy: box('[data-pc="copy"]'), share: box('[data-pc="share"]'),
          overflow: document.documentElement.scrollWidth > innerWidth, text: document.getElementById('m').innerText };
      });
      assert.ok(r.s, 'stamp button present at ' + w); assert.match(r.s.t, /Stamp your @handle/);
      assert.equal(r.s.p, r.x.p); assert.equal(r.s.p, 'pc-xrow');                          // same row container as Post on X
      assert.ok(Math.abs(r.s.y - r.x.y) < 1 && r.s.x > r.x.x && Math.abs(r.s.w - r.x.w) < 1.5 && r.s.h >= 44, JSON.stringify(r));  // right next to it, same size
      assert.ok(r.save && r.copy && r.share && Math.abs(r.save.y - r.copy.y) < 1 && r.save.y > r.x.y, 'Share / Save image / Copy link still there');
      assert.equal(r.overflow, false);
      assert.doesNotMatch(r.text, BAD_COPY);
      assert.match(r.text, /Walker #2 in Tokyo/);
    }
  });
});
test('Stamp your @handle: click uses the existing Link your X flow (POST /api/x/start) and remembers the card for the return', { skip: !canRun && 'no Playwright/Chrome' }, async () => {
  await withBrowser(async ({ br, base, starts }) => {
    const pg = await mountCard(br, base, CARD);
    await Promise.all([pg.waitForURL(/__x-signin/), pg.click('[data-pc="stamp"]')]);
    assert.deepEqual(starts, [{ device_id: 'test-device-abcdefghijklmnop' }]);
    const ss = await pg.evaluate(() => ({ r: JSON.parse(sessionStorage.getItem('satoshiXReturnCard')), m: sessionStorage.getItem('satoshiXMode') }));
    assert.equal(ss.r.slug, 'tokyo'); assert.equal(ss.m, 'link');
  });
});
test('Stamp your @handle: hidden for a linked walker (card shows @handle ✓) and on cards without a verify code', { skip: !canRun && 'no Playwright/Chrome' }, async () => {
  await withBrowser(async ({ br, base }) => {
    for (const card of [{ ...CARD, x: 'demo_walker_1' }, { ...CARD, code: '' }]) {
      const pg = await mountCard(br, base, card);
      const r = await pg.evaluate(() => ({ s: !!document.querySelector('[data-pc="stamp"]'), row: document.querySelector('[data-pc="x"]').parentElement.className,
        n: document.querySelectorAll('.pc-fb .btn').length }));
      assert.equal(r.s, false); assert.equal(r.row, 'pc-fb'); assert.equal(r.n, 3);   // the original Post on X / Save image / Copy link row
    }
  });
});
test('return path: passport page reopens the stamped card after linking; check-in reveal has no second Link your X prompt; home cards carry the linked handle', () => {
  const b = read('build.py'), pw = read('proof-of-walk/index.html'), ci = read('checkin.js'), home = read('index.html'), pc = read('pow-card.js');
  assert.match(pw, /function reopenStampedCard\(me\)/); assert.match(pw, /satoshiXReturnCard/); assert.match(pw, /else if \(reopenStampedCard\(j\.me\)\)/);
  assert.match(b, /me && me\.x && me\.x\.username/);
  assert.match(ci, /!\/pc-reveal\/\.test\(reveal\)\) html \+= xLinkPromptHtml\(\)/);
  assert.match(home, /powMe\.x\.username \? \{ x: powMe\.x\.username \}/);
  assert.match(pc, /fetch\(api \+ '\/api\/x\/start'/);
  const copy = (pc.match(/Stamp your @handle[^']*|Sign in on X to print[^']*/g) || []).join(' ');
  assert.ok(copy.length > 20); assert.doesNotMatch(copy, BAD_COPY);
});
