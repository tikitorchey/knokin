import { describe, expect, it } from 'vitest';
import { Metrics, Samples, formatStats } from '../src/metrics';
import { parseKey, makeUrlOf } from '../src/urls';

describe('Samples', () => {
  it('summarises percentiles and rolls over', () => {
    const s = new Samples(100);
    for (let i = 1; i <= 100; i++) s.add(i);
    const x = s.summary();
    expect(x.n).toBe(100);
    expect(x.p50).toBe(51);
    expect(x.p95).toBe(96);
    expect(x.max).toBe(100);
    s.add(1000);
    expect(s.summary().n).toBe(100);
    expect(s.summary().max).toBe(1000);
  });
  it('is zeroed when empty', () => {
    expect(new Samples().summary()).toEqual({ n: 0, mean: 0, p50: 0, p95: 0, max: 0 });
  });
});

describe('Metrics', () => {
  it('hit rate and stats text', () => {
    const m = new Metrics();
    expect(m.hitRate()).toBe(1);
    m.inc('hit', 3);
    m.inc('miss');
    m.latency.add(12);
    expect(m.hitRate()).toBe(0.75);
    const text = formatStats(m, { pos: 'x' });
    expect(text).toContain('hit 75%');
    expect(text).toContain('pos x');
  });
});

describe('urls', () => {
  it('parseKey inverts refKey formats', () => {
    expect(parseKey('n:n000')).toEqual({ kind: 'node', node: 'n000' });
    expect(parseKey('e:e0001/7')).toEqual({ kind: 'edge', edge: 'e0001', i: 7 });
    expect(() => parseKey('x')).toThrow();
  });
  it('resolves only through the manifest templates', () => {
    const frames = { base: 'frames/', node: 'n/{node}.avif', nodeLow: 'n-low/{node}.avif', edge: 'e/{edge}/{i:04d}.avif' };
    expect(makeUrlOf(frames, false)('e:e0001/7')).toBe('frames/e/e0001/0007.avif');
    expect(makeUrlOf(frames, true)('n:n000')).toBe('frames/n-low/n000.avif');
  });
});
