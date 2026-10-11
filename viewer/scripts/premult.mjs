// Quantify the three createImageBitmap premultiplyAlpha modes against a ground-truth composite.
//   node scripts/premult.mjs <baseUrl> <truthDir> <out.json>
// truthDir (from python/tools/make_premult_truth.py) holds, per sample: <name>.avif (the packed frame) and
// <name>.white.png / <name>.gray.png (straight-alpha composite in sRGB space = the intended on-screen result).
import { createRequire } from 'node:module';
import { readdirSync, writeFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const [base, dir, out] = process.argv.slice(2);
const exe = process.env.CHROMIUM ?? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const names = readdirSync(dir).filter((f) => f.endsWith('.avif')).map((f) => f.slice(0, -5));
const browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.goto(base);
const res = await page.evaluate(async ({ names, dir }) => {
  const load = async (u) => (await fetch(u)).blob();
  const px = (bm, bg, w, h) => {
    const c = new OffscreenCanvas(w, h);
    const g = c.getContext('2d');
    g.fillStyle = bg; g.fillRect(0, 0, w, h); g.drawImage(bm, 0, 0);
    return g.getImageData(0, 0, w, h).data;
  };
  const out = {};
  for (const sample of names) {
    const blob = await load(`${dir}/${sample}.avif`);
    const truth = { white: await createImageBitmap(await load(`${dir}/${sample}.white.png`)), gray: await createImageBitmap(await load(`${dir}/${sample}.gray.png`)) };
    const mask = await createImageBitmap(await load(`${dir}/${sample}.edge.png`));
    const w = truth.white.width, h = truth.white.height;
    const m = px(mask, '#000', w, h);
    const modes = ['premultiply', 'none', 'default'];
    const variants = modes.map((pm) => ({ name: 'bitmap:' + pm, make: () => createImageBitmap(blob, { premultiplyAlpha: pm }) }));
    if (typeof ImageDecoder === 'function') variants.push({ name: 'imageDecoder', make: async () => (await new ImageDecoder({ data: blob.stream(), type: 'image/avif' }).decode({ frameIndex: 0 })).image });
    for (const v of variants) {
      const bm = await v.make();
      for (const [bgName, bg] of [['white', '#fff'], ['gray', '#808080']]) {
        const a = px(bm, bg, w, h), t = px(truth[bgName], '#000', w, h);
        let se = 0, n = 0, seE = 0, nE = 0, max = 0;
        for (let i = 0; i < a.length; i += 4) for (let k = 0; k < 3; k++) {
          const d = a[i + k] - t[i + k]; se += d * d; n++; if (Math.abs(d) > max) max = Math.abs(d);
          if (m[i] > 127) { seE += d * d; nE++; }
        }
        (out[v.name] ??= {})[`${sample}/${bgName}`] = { mse: se / n, mseEdge: nE ? seE / nE : null, maxErr: max };
      }
      bm.close?.();
    }
  }
  return out;
}, { names, dir: `/${dir.split('/').pop()}` });
writeFileSync(out, JSON.stringify(res, null, 2));
const psnr = (mse) => (mse == null ? '  n/a' : (10 * Math.log10(255 * 255 / Math.max(mse, 1e-9))).toFixed(1));
for (const [variant, o] of Object.entries(res)) {
  const ents = Object.entries(o);
  const avg = (key, f) => { const xs = ents.filter(([k]) => k.endsWith(f)).map(([, v]) => v[key]).filter((x) => x != null); return xs.reduce((a, b) => a + b, 0) / xs.length; };
  console.log(`${variant.padEnd(22)} PSNR white ${psnr(avg('mse', 'white'))}  gray ${psnr(avg('mse', 'gray'))}  | edge band white ${psnr(avg('mseEdge', 'white'))}  gray ${psnr(avg('mseEdge', 'gray'))}  | max err ${Math.max(...ents.map(([, v]) => v.maxErr))}`);
}
await browser.close();
