// Renders the combined-card static images from the same /pow-card.js the site uses (headless Chrome, Canvas 2D):
//   img/cards/og/<rank>/<page>.<ver>.jpg  1200x630 generic share images (no date, code or quote), 3 ranks x 11 statues
//   img/cards/og/card/<rank>/<page>/NN.<ver>.jpg  1200x630 per-card share images for the Worker's /c/CODE pages:
//     statue x rank at check-in x card number (3 x 11 x 21); --only-cards renders just these, --no-cards skips them
//   img/cards/sample-front.<ver>.jpg, sample-back.<ver>.jpg, sample-back-21.<ver>.jpg  600x840 explainer samples
// Usage: node tools/render_combined_cards.mjs [--chrome /usr/bin/google-chrome] [--pw /path/to/node_modules/playwright-core]
// Needs playwright-core (not a site dependency): npm i playwright-core in any folder and pass --pw. Run after build.py.
import http from 'node:http';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, extname, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const pw = arg('--pw', process.env.PLAYWRIGHT_CORE || '/workspace/cc-tools/node_modules/playwright-core');
const { chromium } = await import(pathToFileURL(join(pw, 'index.mjs')).href);
const VER = (readFileSync(join(ROOT, 'build.py'), 'utf8').match(/CARD_OG_VER = '([^']+)'/) || [])[1] || 'v1';
const TYPES = { '.txt': 'text/plain', '.html': 'text/html', '.js': 'text/javascript', '.jpg': 'image/jpeg', '.png': 'image/png', '.woff': 'font/woff', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };
const srv = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname); if (p.endsWith('/')) p += 'index.html';
  const f = join(ROOT, p); if (!f.startsWith(ROOT) || !existsSync(f)) { res.writeHead(404); return res.end(); }
  const t = TYPES[extname(f)] || 'application/octet-stream'; res.writeHead(200, { 'Content-Type': /^text|javascript/.test(t) ? t + '; charset=utf-8' : t }); res.end(readFileSync(f));
}).listen(0, '127.0.0.1');
await new Promise(r => srv.once('listening', r));
const base = `http://127.0.0.1:${srv.address().port}`;
const browser = await chromium.launch({ executablePath: arg('--chrome', '/usr/bin/google-chrome'), headless: true });
const page = await browser.newPage();
await page.goto(base + '/robots.txt');
await page.addScriptTag({ url: '/pow-card.js' });
await page.evaluate(() => window.PowCard.load());
const data = await page.evaluate(() => ({ statues: window.POW_CARD_DATA.statues, ranks: window.POW_CARD_DATA.ranks }));
const save = (rel, b64) => { const f = join(ROOT, rel); mkdirSync(dirname(f), { recursive: true }); writeFileSync(f, Buffer.from(b64, 'base64')); };
let n = 0, m = 0;
const onlyCards = process.argv.includes('--only-cards'), noCards = process.argv.includes('--no-cards');
if (!onlyCards) for (const [slug, st] of Object.entries(data.statues)) for (const [k, r] of Object.entries(data.ranks)) {
  const b64 = await page.evaluate(async ([slug, k]) => (await window.PowCard.og(document.createElement('canvas'), { slug, rank: k })).toDataURL('image/jpeg', 0.88).split(',')[1], [slug, k]);
  save(`img/cards/og/${r.share}/${st.page}.${VER}.jpg`, b64); n++;
}
if (!noCards) for (const [slug, st] of Object.entries(data.statues)) for (const [k, r] of Object.entries(data.ranks)) for (let c = 1; c <= 21; c++) {
  const b64 = await page.evaluate(async ([slug, k, c]) => (await window.PowCard.ogCard(document.createElement('canvas'), { slug, rank: k, n: c })).toDataURL('image/jpeg', 0.8).split(',')[1], [slug, k, c]);
  save(`img/cards/og/card/${r.share}/${st.page}/${String(c).padStart(2, '0')}.${VER}.jpg`, b64); m++;
}
if (onlyCards) { console.log(`wrote ${m} per-card share images (${VER})`); await browser.close(); srv.close(); process.exit(0); }
const sample = async (side, card, o) => page.evaluate(async ([side, card, o]) => {
  const c = await window.PowCard.render(document.createElement('canvas'), side, card, { size: 'portrait', ...o });
  const s = document.createElement('canvas'); s.width = 600; s.height = 840; s.getContext('2d').drawImage(c, 0, 0, 600, 840);
  return s.toDataURL('image/jpeg', 0.9).split(',')[1];
}, [side, card, o]);
const demo = { slug: 'lugano', rank: 'genesis', at: '2026-10-31T13:22:00Z', code: 'PW-7K3Q-9QX2' };
save(`img/cards/sample-front.${VER}.jpg`, await sample('front', { ...demo, n: 1 }, {}));
save(`img/cards/sample-back.${VER}.jpg`, await sample('back', { ...demo, n: 1 }, { sample: true }));
save(`img/cards/sample-back-21.${VER}.jpg`, await sample('back', { ...demo, n: 21 }, { sample: true }));
console.log(`wrote ${n} share images + ${m} per-card share images + 3 samples (${VER})`);
await browser.close(); srv.close();
