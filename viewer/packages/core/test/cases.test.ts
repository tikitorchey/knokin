import { describe, expect, it } from 'vitest';
import { frameAt, move, prefetch, type FrameRef, type MoveOpt, type Pos, type PrefetchOpt } from '../src';
import { loadGraph, readJson, toState, type StateJson } from './helpers';

const TOL = 1e-6;

function expectPos(actual: Pos, want: Pos) {
  expect(actual.at).toBe(want.at);
  if (want.at === 'node') expect(actual).toEqual(want);
  else {
    expect((actual as { edge: string }).edge).toBe(want.edge);
    expect((actual as { t: number }).t).toBeCloseTo(want.t, 6);
  }
}

describe('move cases (testdata/move_cases/move.json)', () => {
  const file = readJson<{ manifest: string; opt: MoveOpt; cases: { name: string; start: StateJson; drags: [number, number][]; expect: StateJson }[] }>('move_cases/move.json');
  const g = loadGraph(`move_cases/${file.manifest}`);
  for (const c of file.cases) {
    it(c.name, () => {
      let s = toState(c.start);
      for (const [dx, dy] of c.drags) s = move(g, s, { dx, dy }, file.opt);
      expectPos(s.pos, c.expect.pos);
      if (c.expect.heading) c.expect.heading.forEach((v, k) => expect(Math.abs(s.heading[k]! - v)).toBeLessThan(TOL));
      if (c.expect.acc) c.expect.acc.forEach((v, k) => expect(Math.abs(s.acc[k]! - v)).toBeLessThan(TOL));
    });
  }
});

describe('frameAt cases', () => {
  const file = readJson<{ manifest: string; cases: { name: string; pos: Pos; expect: FrameRef }[] }>('move_cases/frame_at.json');
  const g = loadGraph(`move_cases/${file.manifest}`);
  for (const c of file.cases) it(c.name, () => expect(frameAt(g, c.pos)).toEqual(c.expect));
});

describe('prefetch cases', () => {
  const file = readJson<{ manifest: string; opt: PrefetchOpt; cases: { name: string; start: StateJson; budget: number; expect: FrameRef[] }[] }>('move_cases/prefetch.json');
  const g = loadGraph(`move_cases/${file.manifest}`);
  for (const c of file.cases) it(c.name, () => expect(prefetch(g, toState(c.start), c.budget, file.opt)).toEqual(c.expect));
});
