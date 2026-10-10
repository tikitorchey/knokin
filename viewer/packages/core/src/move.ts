import { angleDeg, dot, edgePhi, exitDir, len, tangent } from './graph';
import type { Graph, MoveOpt, State, Vec } from './types';

const EPS = 1e-9;
const MAX_HOPS = 64;
const ZERO: Vec = [0, 0];

export function initialState(node: string): State {
  return { pos: { at: 'node', node }, heading: ZERO, acc: ZERO };
}

/**
 * Apply a drag (screen px; x right, y down) and return the new state. Pure.
 *
 * On an edge only the component along the edge tangent counts. Reaching an end node, the unused
 * part of the drag accumulates in `acc`. On a node the exit edge is chosen from `acc`:
 *  - going straight on (edge aligned with `heading`) needs no extra drag if `acc` is within
 *    stickyDeg of it, and is preferred over a better-aligned edge by up to stickyDeg;
 *  - any other exit needs |acc| >= turnPx (stickiness);
 *  - if the chosen edge is further than deadZoneDeg from `acc`, nothing happens (dead end).
 */
export function move(g: Graph, state: State, drag: { dx: number; dy: number }, opt: MoveOpt): State {
  let pos = state.pos;
  let heading = state.heading;
  let acc: Vec = state.pos.at === 'edge' ? ZERO : state.acc;
  let rem: Vec = [drag.dx, drag.dy];

  for (let hop = 0; hop < MAX_HOPS; hop++) {
    if (pos.at === 'edge') {
      if (len(rem) < EPS) break;
      const e = g.edges.get(pos.edge);
      if (!e) throw new Error(`unknown edge ${pos.edge}`);
      const { T, L } = tangent(e, edgePhi(g, e, pos.t));
      const s = dot(rem, T);
      if (Math.abs(s) < EPS) break; // perpendicular drag: ignored
      const sign = s > 0 ? 1 : -1;
      heading = [T[0] * sign, T[1] * sign];
      const last = e.frames - 1;
      const nt = pos.t + (s * opt.degPerPx) / L;
      if (nt > 0 && nt < last) {
        pos = { at: 'edge', edge: e.id, t: nt };
        break;
      }
      const endT = nt >= last ? last : 0;
      const left = Math.max(0, Math.abs(s) - (Math.abs(endT - pos.t) * L) / opt.degPerPx);
      pos = { at: 'node', node: endT === 0 ? e.from : e.to };
      acc = [T[0] * sign * left, T[1] * sign * left];
      rem = ZERO;
      continue;
    }

    // resting on a node
    acc = [acc[0] + rem[0], acc[1] + rem[1]];
    rem = ZERO;
    const accLen = len(acc);
    const inc = g.incident.get(pos.node) ?? [];
    if (inc.length === 0 || accLen < EPS) break;

    const cands = inc.map((c) => {
      const u = exitDir(g, c);
      return { c, u, fromAcc: angleDeg(acc, u), fromHeading: len(heading) < EPS ? 180 : angleDeg(heading, u) };
    });
    let best = cands[0]!;
    for (const k of cands) if (k.fromAcc < best.fromAcc - 1e-12) best = k;
    let straight = cands[0]!;
    for (const k of cands) if (k.fromHeading < straight.fromHeading - 1e-12) straight = k;
    const hasStraight = straight.fromHeading <= opt.stickyDeg;
    const chosen = hasStraight && straight.fromAcc <= best.fromAcc + opt.stickyDeg ? straight : best;
    const exempt = hasStraight && chosen === straight && straight.fromAcc <= opt.stickyDeg;

    if (!exempt && accLen < opt.turnPx) break;
    if (chosen.fromAcc > opt.deadZoneDeg) {
      if (accLen > opt.turnPx) {
        const k = opt.turnPx / accLen;
        acc = [acc[0] * k, acc[1] * k]; // keep reversing cheap
      }
      break;
    }
    pos = { at: 'edge', edge: chosen.c.edge.id, t: chosen.c.end === 'from' ? 0 : chosen.c.edge.frames - 1 };
    rem = acc;
    acc = ZERO;
  }
  return { pos, heading, acc: pos.at === 'edge' ? ZERO : acc };
}
