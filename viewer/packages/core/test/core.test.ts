import { readFileSync } from 'node:fs';
import { resolve as pathResolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DEFAULT_MOVE_OPT, SchemaError, frameAt, initialState, move, parseManifest, parseRevision, compareRevision, versionLabel, prefetch, refKey, renderTemplate, resolve, totalFrames, type State } from '../src';
import { TESTDATA } from './helpers';

const read = (n: string) => readFileSync(pathResolve(TESTDATA, 'manifests', n), 'utf8');

describe('golden manifest shared with Python', () => {
  const { manifest, graph } = parseManifest(read('grid30_cross.json'));
  it('has the counts the Python tests assert', () => {
    expect(graph.nodes.size).toBe(108);
    expect(graph.edges.size).toBe(300);
    expect(totalFrames(graph)).toBe(5928);
  });
  it('resolves paths like Python does', () => {
    expect(resolve(manifest.frames, { kind: 'node', node: 'n001' })).toBe('frames/n/n001.avif');
    expect(resolve(manifest.frames, { kind: 'node', node: 'n001' }, { low: true })).toBe('frames/n-low/n001.avif');
    expect(resolve(manifest.frames, { kind: 'edge', edge: 'e0001', i: 5 })).toBe('frames/e/e0001/0005.avif');
  });
  it('every image of the graph resolves to a distinct path', () => {
    const paths = new Set<string>();
    for (const n of graph.nodes.values()) paths.add(resolve(manifest.frames, { kind: 'node', node: n.id }));
    for (const e of graph.edges.values()) for (let i = 1; i < e.frames - 1; i++) paths.add(resolve(manifest.frames, { kind: 'edge', edge: e.id, i }));
    expect(paths.size).toBe(5928);
  });
});

describe('manifest gate', () => {
  it('accepts the minimal sample', () => expect(parseManifest(read('minimal.json')).graph.edges.size).toBe(3));
  it('rejects another schema version', () => {
    const m = JSON.parse(read('minimal.json'));
    expect(() => parseManifest(JSON.stringify({ ...m, schema: 'knokin-turntable/1' }))).toThrow(SchemaError);
  });
  it('rejects another coordinate convention', () => {
    const m = JSON.parse(read('minimal.json'));
    expect(() => parseManifest(JSON.stringify({ ...m, coords: { ...m.coords, thetaDir: 'cw-from-above' } }))).toThrow(SchemaError);
  });
  it('template subset', () => {
    expect(renderTemplate('e/{edge}/{i:04d}.avif', { edge: 'e0001', i: 7 })).toBe('e/e0001/0007.avif');
    expect(() => renderTemplate('{x!r}', { x: 1 })).toThrow();
  });
});

describe('move invariants', () => {
  const { graph: g } = parseManifest(read('grid30_cross.json'));
  const snapshot = (s: State) => JSON.stringify(s);

  it('is pure: does not mutate its input and is deterministic', () => {
    const s = initialState('n024');
    const before = snapshot(s);
    const a = move(g, s, { dx: -40, dy: 5 }, DEFAULT_MOVE_OPT);
    expect(snapshot(s)).toBe(before);
    expect(snapshot(move(g, s, { dx: -40, dy: 5 }, DEFAULT_MOVE_OPT))).toBe(snapshot(a));
  });

  it('long random walks always stay on the graph and prefetch only returns valid, unique references', () => {
    let seed = 12345;
    const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32);
    let s = initialState('n024');
    for (let k = 0; k < 3000; k++) {
      s = move(g, s, { dx: (rnd() - 0.5) * 400, dy: (rnd() - 0.5) * 400 }, DEFAULT_MOVE_OPT);
      if (s.pos.at === 'edge') {
        const e = g.edges.get(s.pos.edge)!;
        expect(s.pos.t).toBeGreaterThan(0);
        expect(s.pos.t).toBeLessThan(e.frames - 1);
      } else expect(g.nodes.has(s.pos.node)).toBe(true);
      if (k % 50 === 0) {
        const refs = prefetch(g, s, 16);
        const keys = refs.map(refKey);
        expect(new Set(keys).size).toBe(keys.length);
        expect(keys).not.toContain(refKey(frameAt(g, s.pos)));
        expect(refs.length).toBeLessThanOrEqual(16);
      }
    }
  });

  it('a long straight drag around the equator never stalls at nodes', () => {
    let s = initialState('n024');
    s = move(g, s, { dx: -40, dy: 0 }, DEFAULT_MOVE_OPT); // leave the node first
    for (let k = 0; k < 12; k++) s = move(g, s, { dx: -120, dy: 0 }, DEFAULT_MOVE_OPT); // 12 x 30 frames/ 12 x 30deg = full circle
    expect(s.pos.at).toBe('edge');
    if (s.pos.at === 'edge') {
      expect(g.edges.get(s.pos.edge)!.kind).toBe('lat');
      expect(g.nodes.get(g.edges.get(s.pos.edge)!.from)!.phi).toBe(0);
    }
  });
});

describe('data revision', () => {
  it('parses and rejects', () => {
    expect(parseRevision('2026-10-13.12')).toEqual({ date: '2026-10-13', n: 12 });
    for (const bad of ['2026-10-13', '2026-13-01.0', '2026-02-30.0', 'x.0', undefined, 5]) expect(parseRevision(bad)).toBeNull();
  });
  it('compares n numerically', () => {
    expect(compareRevision('2026-10-13.9', '2026-10-13.10')).toBeLessThan(0);
    expect(compareRevision('2026-10-14.0', '2026-10-13.99')).toBeGreaterThan(0);
    expect(compareRevision('2026-10-13.1', '2026-10-13.1')).toBe(0);
    expect(compareRevision('bad', '2026-10-13.1')).toBeNull();
  });
  it('labels, with a placeholder for a manifest without revision', () => {
    expect(versionLabel('0.0.1', { revision: '2026-10-13.0' })).toBe('app v0.0.1 · data 2026-10-13.0');
    expect(versionLabel('0.0.1', undefined)).toBe('app v0.0.1 · data -');
    expect(versionLabel('0.0.1', { revision: 'junk' })).toBe('app v0.0.1 · data -');
  });
  it('a manifest with meta.revision still passes the gate', () => {
    const m = JSON.parse(read('minimal.json'));
    expect(m.meta.revision).toBe('2026-10-13.0');
    expect(parseManifest(JSON.stringify(m)).manifest.meta?.revision).toBe('2026-10-13.0');
  });
});
