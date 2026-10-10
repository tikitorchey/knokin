// Run the scripted drag in headless Chromium for a list of URL-parameter variants; print + save JSON.
//   node scripts/measure.mjs <baseUrl> <out.json> [variant ...]      e.g.  "decode=imageDecoder" "cache=24&conc=2"
// Needs a server already serving the packed output (npm run dev, or `npx vite preview` after build).
// Desktop headless numbers are NOT Android numbers: they only show relative effects and catch regressions.
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE ?? 'playwright');

const [base, out, ...variants] = process.argv.slice(2);
if (!base || !out) throw new Error('usage: measure.mjs <baseUrl> <out.json> [variant ...]');
const exe = process.env.CHROMIUM ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const browser = await chromium.launch({ executablePath: exe, args: ['--enable-precise-memory-info', '--no-sandbox'] });
const results = [];
for (const v of variants.length ? variants : ['']) {
  const page = await (await browser.newContext({ viewport: { width: 900, height: 560 } })).newPage();
  const url = `${base}${base.includes('?') ? '&' : '?'}dbg=1&bench=1&tag=${encodeURIComponent(v || 'default')}${v ? '&' + v : ''}`;
  await page.goto(url);
  await page.waitForFunction(() => window.__knokinBench, null, { timeout: 120000 });
  const r = await page.evaluate(() => window.__knokinBench);
  results.push({ variant: v || 'default', ...r });
  const f = (s) => `p50 ${s.p50.toFixed(1)} p95 ${s.p95.toFixed(1)}`;
  console.log(`${(v || 'default').padEnd(36)} latency ${f(r.latency)}  fetch ${f(r.fetchMs)}  decode ${f(r.decodeMs)}  hit ${(r.hitRate * 100).toFixed(0)}%  miss ${r.counters.miss ?? 0} fail ${r.counters.fail ?? 0} heap-peak ${r.peakHeapMB?.toFixed(0)}MB`);
  await page.close();
}
await browser.close();
writeFileSync(out, JSON.stringify(results, null, 2));
