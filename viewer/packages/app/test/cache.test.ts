import { describe, expect, it } from 'vitest';
import { FrameCache } from '../src/cache';
import { manualLoader, tick, type Fake } from './helpers';

const mk = (maxItems = 10, concurrency = 2) => {
  const l = manualLoader();
  const events = { ready: [] as string[], fail: [] as string[], abort: [] as string[] };
  const cache = new FrameCache<Fake>(l.load, { maxItems, concurrency }, {
    onReady: (k) => events.ready.push(k),
    onFail: (k) => events.fail.push(k),
    onAbort: (k) => events.abort.push(k),
  });
  return { l, cache, events };
};

describe('FrameCache', () => {
  it('starts loads in priority order under the concurrency limit', async () => {
    const { l, cache } = mk(10, 2);
    cache.want(['a', 'b', 'c', 'd']);
    expect(l.started).toEqual(['a', 'b']);
    await l.finish('a');
    expect(l.started).toEqual(['a', 'b', 'c']);
    expect(cache.has('a')).toBe(true);
    expect(cache.get('a')?.key).toBe('a');
  });

  it('drops queued items and aborts in-flight ones that leave the want list', async () => {
    const { l, cache, events } = mk(10, 2);
    cache.want(['a', 'b', 'c']);
    const sigA = l.pending.get('a')!.signal;
    cache.want(['b', 'c']);
    expect(sigA.aborted).toBe(true);
    expect(events.abort).toEqual(['a']);
    expect(cache.inFlight).toBe(2); // b and c now fill both slots
    expect(l.started).toEqual(['a', 'b', 'c']);
  });

  it('closes a frame that finishes after it was aborted', async () => {
    const { l, cache } = mk();
    cache.want(['a']);
    const p = l.pending.get('a')!;
    cache.want([]);
    await l.finish('a');
    expect(l.created[0]!.closed).toBe(true);
    expect(cache.has('a')).toBe(false);
    expect(p.signal.aborted).toBe(true);
    expect(cache.inFlight).toBe(0);
  });

  it('re-wanting an aborted key starts a fresh load; the stale result is discarded', async () => {
    const { l, cache } = mk();
    cache.want(['a']);
    const stale = l.pending.get('a')!;
    cache.want([]);
    cache.want(['a']);
    expect(l.started).toEqual(['a', 'a']);
    stale.resolve({ key: 'stale', width: 1, height: 1, closed: false, close() { this.closed = true; } });
    await tick();
    expect(cache.has('a')).toBe(false); // the new load is still pending
    await l.finish('a');
    expect(cache.get('a')?.key).toBe('a');
  });

  it('evicts unwanted, least recently used frames first and closes them', async () => {
    const { l, cache } = mk(3, 4);
    cache.want(['a', 'b', 'c']);
    for (const k of ['a', 'b', 'c']) await l.finish(k);
    cache.get('a'); // a is now the most recently used
    cache.want(['d', 'a']); // b, c unwanted; b is the oldest
    await l.finish('d');
    expect(cache.readyCount).toBe(3);
    expect(cache.has('b')).toBe(false);
    expect(cache.has('c') && cache.has('a') && cache.has('d')).toBe(true);
    expect(l.created.find((f) => f.key === 'b')!.closed).toBe(true);
  });

  it('when everything is wanted, the lowest-priority frames go first', async () => {
    const { l, cache } = mk(2, 4);
    cache.want(['a', 'b', 'c']);
    for (const k of ['a', 'b', 'c']) await l.finish(k);
    expect(cache.has('a') && cache.has('b')).toBe(true);
    expect(cache.has('c')).toBe(false);
  });

  it('shrinking maxItems at runtime takes effect on the next want', async () => {
    const { l, cache } = mk(5, 5);
    cache.want(['a', 'b', 'c', 'd']);
    for (const k of ['a', 'b', 'c', 'd']) await l.finish(k);
    cache.opt.maxItems = 2;
    cache.want(['a', 'b', 'c', 'd']);
    expect(cache.readyCount).toBe(2);
    expect(cache.has('a') && cache.has('b')).toBe(true);
  });

  it('a failed load is reported, frees its slot, and is not retried until cleared', async () => {
    const { l, cache, events } = mk(10, 1);
    cache.want(['a', 'b']);
    await l.fail('a');
    expect(events.fail).toEqual(['a']);
    expect(l.started).toEqual(['a', 'b']);
    cache.want(['a', 'b']);
    expect(l.started).toEqual(['a', 'b']);
    cache.clearFailures();
    cache.want(['a', 'b']);
    await l.finish('b');
    expect(l.started).toEqual(['a', 'b', 'a']);
  });

  it('dispose aborts and closes everything', async () => {
    const { l, cache } = mk();
    cache.want(['a', 'b']);
    await l.finish('a');
    const sig = l.pending.get('b')!.signal;
    cache.dispose();
    expect(sig.aborted).toBe(true);
    expect(l.created[0]!.closed).toBe(true);
    expect(cache.readyCount).toBe(0);
  });
});
