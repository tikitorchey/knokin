import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseManifest, refKey } from '@knokin/core';
import { FrameCache } from '../src/cache';
import { Controller, type ShowEvent } from '../src/controller';
import { Metrics } from '../src/metrics';
import { instantLoader, manualLoader, tick, type Fake } from './helpers';

const here = dirname(fileURLToPath(import.meta.url));
const text = readFileSync(resolve(here, '../../../../testdata/manifests/grid30_cross.json'), 'utf8');
const { manifest, graph } = parseManifest(text);
const START = manifest.start.node;

function env(opts: { manual?: boolean; low?: boolean } = {}) {
  const full = opts.manual ? manualLoader() : null;
  const inst = opts.manual ? null : instantLoader();
  const lowL = instantLoader();
  const shows: ShowEvent<Fake>[] = [];
  const metrics = new Metrics();
  let c: Controller<Fake> | null = null;
  const cache = new FrameCache<Fake>(full ? full.load : inst!.load, { maxItems: 64, concurrency: 8 }, {
    onReady: (k) => c?.onReady(k),
  });
  const lowCache = opts.low
    ? new FrameCache<Fake>(lowL.load, { maxItems: 200, concurrency: 8 }, { onReady: (k) => c?.onLowReady(k) })
    : null;
  let clock = 0;
  c = new Controller<Fake>(graph, START, cache, lowCache, (e) => shows.push(e), metrics, () => clock);
  return { c, cache, lowCache, shows, metrics, full, setClock: (t: number) => { clock = t; } };
}

describe('Controller', () => {
  it('misses on the first frame, then shows it when it arrives', async () => {
    const e = env();
    expect(e.shows).toHaveLength(0);
    expect(e.metrics.count('miss')).toBe(1);
    await tick();
    expect(e.shows.map((s) => s.key)).toEqual([`n:${START}`]);
    expect(e.shows[0]!.low).toBe(false);
  });

  it('shows the low-res stand-in at a node until the full image is ready', async () => {
    const e = env({ manual: true, low: true });
    e.lowCache!.want([`n:${START}`]);
    await tick();
    expect(e.shows.map((s) => [s.key, s.low])).toEqual([[`n:${START}`, true]]);
    await e.full!.finish(`n:${START}`);
    expect(e.shows.map((s) => [s.key, s.low])).toEqual([[`n:${START}`, true], [`n:${START}`, false]]);
  });

  it('dragging along an edge shows successive frames and keeps a prefetched lead', async () => {
    const e = env();
    await tick();
    e.shows.length = 0;
    // From the start node (phi=0 row) drag so we travel along a latitude edge.
    for (let n = 0; n < 40; n++) {
      e.c.drag(-4, 0, n); // 4px left -> +1 deg/frame at 0.25 deg/px
      await tick();
    }
    const keys = e.shows.map((s) => s.key);
    expect(keys.length).toBeGreaterThan(10);
    expect(new Set(keys).size).toBe(keys.length); // never re-shows the same frame
    expect(e.metrics.count('hit')).toBeGreaterThan(5); // prefetch kept ahead of the drag
  });

  it('keeps the previous frame while the next one is loading, and attributes latency to the input time', async () => {
    const e = env({ manual: true });
    await e.full!.finish(`n:${START}`);
    expect(e.shows).toHaveLength(1);
    e.c.drag(-16, 0, 100); // leaves the node (turnPx=12) and travels along the edge
    const key = e.c.currentKey;
    expect(key.startsWith('e:')).toBe(true);
    expect(e.shows).toHaveLength(1); // nothing new yet: previous frame stays
    expect(e.metrics.count('miss')).toBeGreaterThanOrEqual(1);
    await e.full!.finish(key);
    expect(e.shows).toHaveLength(2);
    expect(e.shows[1]!.key).toBe(key);
    expect(e.shows[1]!.inputAt).toBe(100);
  });

  it('does not show a late frame that is no longer current', async () => {
    const e = env({ manual: true });
    await e.full!.finish(`n:${START}`);
    e.c.drag(-16, 0, 1);
    const stale = e.c.currentKey;
    e.c.drag(-40, 0, 2); // move well past it
    expect(e.c.currentKey).not.toBe(stale);
    const before = e.shows.length;
    if (e.full!.pending.has(stale)) await e.full!.finish(stale);
    expect(e.shows).toHaveLength(before);
  });

  it('changing options re-plans the want list', async () => {
    const e = env({ manual: true });
    expect(e.cache.wantedKeys[0]).toBe(`n:${START}`);
    const before = e.cache.wantedKeys.length;
    e.c.setOpt({ budget: 4 });
    expect(e.cache.wantedKeys.length).toBeLessThanOrEqual(5);
    expect(e.cache.wantedKeys.length).toBeLessThan(before);
  });

  it('reset returns to a node and shows it', async () => {
    const e = env();
    await tick();
    e.c.drag(-40, 0, 1);
    await tick();
    e.c.reset(START);
    await tick();
    expect(e.shows.at(-1)!.key).toBe(refKey({ kind: 'node', node: START }));
  });
});
