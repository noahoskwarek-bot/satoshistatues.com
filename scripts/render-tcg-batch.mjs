// Render locked Proof of Walk cards as TCGPrintery print-ready PNGs (1630x2220, 600 dpi, 3 mm bleed).
// Uses the same pow-card.js Canvas 2D renderer in headless Chrome. No production database is touched.
// Usage:
//   node scripts/render-tcg-batch.mjs --card '{"slug":"tokyo","rank":"confirmed","n":1,"walker":1,"x":"antonzodiak","code":"PW-XXXX-XXXX","at":"2026-11-27T01:15:00Z"}' \
//     --out-dir /workspace/foil-print-preview --prefix sample-tokyo
//   node scripts/render-tcg-batch.mjs --batch-json orders.json --out-dir ./out
// Each batch JSON item is a locked card: slug, rank, n, walker, x (handle, no @), code, at (ISO).
import http from 'node:http';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, extname, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const pw = arg('--pw', process.env.PLAYWRIGHT_CORE || '/usr/local/lib/pnpm/5/.pnpm/playwright-core@1.59.1/node_modules/playwright-core');
const { chromium } = await import(pathToFileURL(join(pw, 'index.mjs')).href);

const TYPES = { '.txt': 'text/plain', '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml',
  '.woff': 'font/woff', '.woff2': 'font/woff2' };

const srv = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname); if (p.endsWith('/')) p += 'index.html';
  const f = join(ROOT, p); if (!f.startsWith(ROOT) || !existsSync(f)) { res.writeHead(404); return res.end(); }
  const t = TYPES[extname(f)] || 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': /^text|javascript|json/.test(t) ? t + '; charset=utf-8' : t });
  res.end(readFileSync(f));
}).listen(0, '127.0.0.1');
await new Promise(r => srv.once('listening', r));
const base = `http://127.0.0.1:${srv.address().port}`;

const browser = await chromium.launch({ executablePath: arg('--chrome', '/usr/bin/google-chrome'), headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.goto(base + '/robots.txt');
await page.addScriptTag({ url: '/proof-of-walk/card-data.js' });
await page.addScriptTag({ url: '/pow-card.js' });
await page.evaluate(() => window.PowCard.load());

function parseCards() {
  const one = arg('--card', '');
  const file = arg('--batch-json', '');
  const items = [];
  if (one) items.push(JSON.parse(one));
  if (file) {
    const raw = JSON.parse(readFileSync(resolve(file), 'utf8'));
    items.push(...(Array.isArray(raw) ? raw : (raw.orders || raw.cards || [raw])));
  }
  if (!items.length) throw new Error('Pass --card JSON or --batch-json path');
  return items.map(normalize);
}
function normalize(c) {
  if (!c || !c.slug) throw new Error('card is missing slug');
  return {
    slug: c.slug,
    rank: c.rank || 'confirmed',
    n: Number(c.n || c.card || 1),
    walker: c.walker != null ? Number(c.walker) : (c.walker_number != null ? Number(c.walker_number) : undefined),
    x: c.x || c.x_handle || undefined,
    code: c.code || c.card_id || undefined,
    at: c.at || undefined,
  };
}

const outDir = resolve(arg('--out-dir', join(ROOT, 'out-tcg')));
mkdirSync(outDir, { recursive: true });
const prefixArg = arg('--prefix', '');
const cards = parseCards();
const written = [];
for (const card of cards) {
  const prefix = prefixArg || ('card-' + (card.code || (card.slug + '-' + (card.walker || 'x'))).replace(/[^A-Za-z0-9_-]+/g, '-'));
  for (const side of ['front', 'back']) {
    const buf = await page.evaluate(async ([side, card]) => {
      const blob = await window.PowCard.png(side, card, { size: 'tcg' });
      const ab = await blob.arrayBuffer();
      return Array.from(new Uint8Array(ab));
    }, [side, card]);
    const dest = join(outDir, `${prefix}-${side}-1630x2220.png`);
    writeFileSync(dest, Buffer.from(buf));
    written.push(dest);
    console.log('wrote', dest, buf.length, 'bytes');
  }
}
await browser.close(); srv.close();
console.log(`rendered ${written.length} files at 1630x2220`);
