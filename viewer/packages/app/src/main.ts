import { parseManifest, refKey, type Manifest } from '@knokin/core';
import { FrameCache } from './cache';
import { Controller, DEFAULT_CONTROLLER_OPT, type ShowEvent } from './controller';
import { DEFAULT_LOADER_OPT, makeLoader, supportsImageDecoder, type Frame, type LoaderOpt } from './loader';
import { DEFAULT_BENCH_OPT, runBench } from './bench';
import { Metrics, formatStats } from './metrics';
import { CanvasView } from './render';
import { buildPanel, type Control } from './ui';
import { makeUrlOf } from './urls';

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

async function boot(): Promise<void> {
  const params = new URLSearchParams(location.search);
  const manifestUrl = new URL(params.get('m') ?? './manifest.json', location.href).href;
  const dbg = params.has('dbg');

  const res = await fetch(manifestUrl);
  if (!res.ok) throw new Error(`manifest: ${res.status} ${manifestUrl}`);
  const { manifest, graph } = parseManifest(await res.text());

  const metrics = new Metrics();
  // URL overrides so a run is fully described by its URL (useful on a phone: no sliders to set).
  //   decode=createImageBitmap|imageDecoder  pm=premultiply|none|default  cache=<maxItems>  conc=<n>  budget=<n>
  const num = (k: string): number | null => (params.has(k) && Number.isFinite(Number(params.get(k))) ? Number(params.get(k)) : null);
  const loaderOpt: LoaderOpt = { ...DEFAULT_LOADER_OPT };
  const decodeP = params.get('decode');
  if (decodeP === 'createImageBitmap' || decodeP === 'imageDecoder') loaderOpt.strategy = decodeP;
  const pmP = params.get('pm');
  if (pmP === 'premultiply' || pmP === 'none' || pmP === 'default') loaderOpt.premultiply = pmP;
  const view = new CanvasView($('view') as HTMLCanvasElement, manifest.image.width / manifest.image.height);
  const hasLow = Boolean(manifest.frames.nodeLow && manifest.image.low);

  let controller: Controller<Frame> | null = null;
  const cache = new FrameCache<Frame>(
    makeLoader(manifestUrl, makeUrlOf(manifest.frames, false), () => loaderOpt, metrics),
    { maxItems: num('cache') ?? 48, concurrency: num('conc') ?? 6 },
    {
      onReady: (k) => controller?.onReady(k),
      onFail: (k, e) => { metrics.inc('fail'); console.warn('load failed', k, e); },
      onAbort: () => metrics.inc('abort'),
    },
  );
  const lowCache = hasLow
    ? new FrameCache<Frame>(
        makeLoader(manifestUrl, makeUrlOf(manifest.frames, true), () => loaderOpt, new Metrics()),
        { maxItems: graph.nodes.size, concurrency: 4 },
        { onReady: (k) => controller?.onLowReady(k) },
      )
    : null;
  lowCache?.want([...graph.nodes.keys()].map((id) => refKey({ kind: 'node', node: id })));

  // Draw on the next animation frame, always the newest frame; latency = input timestamp -> drawn.
  let queued: ShowEvent<Frame> | null = null;
  const flush = () => {
    const e = queued;
    queued = null;
    if (!e) return;
    view.draw(e.bitmap);
    if (e.inputAt !== null) metrics.latency.add(performance.now() - e.inputAt);
  };
  const show = (e: ShowEvent<Frame>) => {
    if (!queued) requestAnimationFrame(flush);
    queued = e;
  };

  controller = new Controller<Frame>(graph, manifest.start.node, cache, lowCache, show, metrics, () => performance.now(), {
    ...DEFAULT_CONTROLLER_OPT,
    budget: num('budget') ?? DEFAULT_CONTROLLER_OPT.budget,
  });

  layout(view);
  addEventListener('resize', () => layout(view));
  bindPointer(view.canvas, controller);

  if (dbg) setupDebug(manifest, controller, cache, lowCache, metrics, loaderOpt, view);
}

function layout(view: CanvasView): void {
  view.resize(innerWidth, innerHeight, devicePixelRatio || 1);
}

function bindPointer(canvas: HTMLCanvasElement, c: Controller<Frame>): void {
  let last: { id: number; x: number; y: number } | null = null;
  canvas.addEventListener('pointerdown', (e) => {
    if (last) return; // single pointer only in the prototype
    last = { id: e.pointerId, x: e.clientX, y: e.clientY };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!last || e.pointerId !== last.id) return;
    const evs = typeof e.getCoalescedEvents === 'function' ? e.getCoalescedEvents() : [];
    for (const ev of evs.length ? evs : [e]) {
      c.drag(ev.clientX - last.x, ev.clientY - last.y, ev.timeStamp);
      last.x = ev.clientX;
      last.y = ev.clientY;
    }
  });
  const end = (e: PointerEvent) => {
    if (last && e.pointerId === last.id) last = null;
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
}

function setupDebug(
  manifest: Manifest, c: Controller<Frame>, cache: FrameCache<Frame>, low: FrameCache<Frame> | null,
  metrics: Metrics, loaderOpt: LoaderOpt, view: CanvasView,
): void {
  const hud = $('hud');
  const panel = $('panel');
  panel.classList.remove('hidden');
  const set = (patch: Partial<typeof c.opt>) => c.setOpt({ ...patch });
  const mv = (k: keyof typeof c.opt.move) => ({
    get: () => c.opt.move[k],
    set: (v: number) => set({ move: { ...c.opt.move, [k]: v } }),
  });
  const pf = (k: keyof typeof c.opt.prefetch) => ({
    get: () => c.opt.prefetch[k],
    set: (v: number) => set({ prefetch: { ...c.opt.prefetch, [k]: v } }),
  });
  const controls: Control[] = [
    { kind: 'range', label: 'degPerPx', min: 0.05, max: 1, step: 0.05, ...mv('degPerPx') },
    { kind: 'range', label: 'turnPx', min: 0, max: 60, step: 1, ...mv('turnPx') },
    { kind: 'range', label: 'deadZone', min: 15, max: 90, step: 5, ...mv('deadZoneDeg') },
    { kind: 'range', label: 'stickyDeg', min: 0, max: 45, step: 1, ...mv('stickyDeg') },
    { kind: 'range', label: 'budget', min: 2, max: 48, step: 1, get: () => c.opt.budget, set: (v) => set({ budget: v }) },
    { kind: 'range', label: 'fanFrames', min: 0, max: 8, step: 1, ...pf('fanFrames') },
    { kind: 'range', label: 'behind', min: 0, max: 8, step: 1, ...pf('behindFrames') },
    { kind: 'range', label: 'cacheMax', min: 4, max: 200, step: 1, get: () => cache.opt.maxItems, set: (v) => { cache.opt.maxItems = v; } },
    { kind: 'range', label: 'concurrency', min: 1, max: 16, step: 1, get: () => cache.opt.concurrency, set: (v) => { cache.opt.concurrency = v; } },
    {
      kind: 'select', label: 'decode', options: supportsImageDecoder() ? ['createImageBitmap', 'imageDecoder'] : ['createImageBitmap'],
      get: () => loaderOpt.strategy, set: (v) => { loaderOpt.strategy = v as LoaderOpt['strategy']; },
    },
    {
      kind: 'select', label: 'premultiply', options: ['premultiply', 'none', 'default'],
      get: () => loaderOpt.premultiply, set: (v) => { loaderOpt.premultiply = v as LoaderOpt['premultiply']; },
    },
    { kind: 'check', label: 'checker bg', get: () => view.checker, set: (v) => { view.checker = v; } },
  ];
  buildPanel($('controls'), controls);
  $('reset').onclick = () => c.reset(manifest.start.node);
  $('retry').onclick = () => { cache.clearFailures(); c.setOpt({}); };
  let scripted: Record<string, unknown> | null = null;
  const report = () => ({
    tag: new URLSearchParams(location.search).get('tag') ?? '',
    ua: navigator.userAgent,
    dpr: devicePixelRatio,
    screen: [innerWidth, innerHeight],
    image: [manifest.image.width, manifest.image.height],
    cores: navigator.hardwareConcurrency,
    deviceMemoryGB: (navigator as unknown as { deviceMemory?: number }).deviceMemory ?? null,
    opt: c.opt,
    cache: { maxItems: cache.opt.maxItems, concurrency: cache.opt.concurrency },
    loader: loaderOpt,
    heapMB: heapMB(),
    peakHeapMB: peakHeap,
    scripted,
    ...metrics.snapshot(),
  });
  let peakHeap = 0;
  $('bench').onclick = async () => {
    const btn = $('bench') as HTMLButtonElement;
    btn.disabled = true;
    metrics.reset();
    peakHeap = 0;
    c.reset(manifest.start.node);
    const r = await runBench(c, DEFAULT_BENCH_OPT, () => { peakHeap = Math.max(peakHeap, heapMB() ?? 0); });
    scripted = { path: DEFAULT_BENCH_OPT.path, speedPxPerSec: DEFAULT_BENCH_OPT.speedPxPerSec, wallMs: r.wallMs };
    (window as unknown as { __knokinBench: unknown }).__knokinBench = report();
    btn.disabled = false;
  };
  $('export').onclick = () => {
    const blob = new Blob([JSON.stringify(report(), null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'knokin-metrics.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  if (new URLSearchParams(location.search).has('bench')) setTimeout(() => $('bench').click(), 1500); // auto-run (automation)

  const bytes = manifest.image.width * manifest.image.height * 4;
  setInterval(() => {
    const mem = heapMB();
    hud.textContent = formatStats(metrics, {
      pos: JSON.stringify(c.state.pos),
      decoded: `${cache.readyCount} (~${((cache.readyCount * bytes) / 1048576).toFixed(0)}MB) inflight ${cache.inFlight}`,
      low: low ? low.readyCount : '-',
      heap: mem !== null ? `${mem.toFixed(0)}MB` : 'n/a',
    });
  }, 500);
}

function heapMB(): number | null {
  const mem = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
  return mem ? mem.usedJSHeapSize / 1048576 : null;
}

boot().catch((e: unknown) => {
  $('msg').textContent = String(e instanceof Error ? e.message : e);
  console.error(e);
});
