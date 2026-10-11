// createImageBitmap / ImageDecoder decode time per AVIF file set (desktop headless Chromium; relative numbers only).
//   node scripts/decode-bench.mjs <baseUrl> <dir under public, e.g. truth-s-0-420> [reps]
import { createRequire } from 'node:module';
import { readdirSync } from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const [base, dir, reps = '20'] = process.argv.slice(2);
const names = readdirSync(`packages/app/public/${dir}`).filter((f) => f.endsWith('.avif'));
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.goto(base);
const r = await page.evaluate(async ({ dir, names, reps }) => {
  const blobs = await Promise.all(names.map(async (n) => (await fetch(`/${dir}/${n}`)).blob()));
  const out = {};
  const stats = (xs) => { xs.sort((a, b) => a - b); return { p50: xs[Math.floor(xs.length / 2)], p95: xs[Math.floor(xs.length * 0.95)], n: xs.length }; };
  const modes = { createImageBitmap: (b) => createImageBitmap(b), imageDecoder: async (b) => (await new ImageDecoder({ data: b.stream(), type: 'image/avif' }).decode({ frameIndex: 0 })).image };
  for (const [name, f] of Object.entries(modes)) {
    const ts = [];
    for (let i = 0; i < reps; i++) for (const b of blobs) { const t = performance.now(); const x = await f(b); ts.push(performance.now() - t); x.close(); }
    out[name] = stats(ts);
  }
  out.bytesMean = blobs.reduce((a, b) => a + b.size, 0) / blobs.length;
  return out;
}, { dir, names, reps: Number(reps) });
console.log(dir, JSON.stringify(r));
await browser.close();
