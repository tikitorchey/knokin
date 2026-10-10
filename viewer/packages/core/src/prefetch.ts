import { angleDeg, edgePhi, exitDir, len, tangent } from './graph';
import { frameAt, frameRef, refKey } from './frameAt';
import { DEFAULT_PREFETCH_OPT, type FrameRef, type Graph, type PrefetchOpt, type State } from './types';

/**
 * References worth loading next, highest priority first, at most `budget`, current frame excluded.
 * On an edge: (1) frames ahead (at most ceil(budget/2)), including the end node if reached;
 * (2) once at that node, the first `fanFrames` frames of every other incident edge, round-robin by
 * rank, edges ordered by alignment with the heading; (3) `behindFrames` frames behind.
 * On a node: all incident edges round-robin until the budget is spent.
 */
export function prefetch(g: Graph, state: State, budget: number, opt: PrefetchOpt = DEFAULT_PREFETCH_OPT): FrameRef[] {
  const out: FrameRef[] = [];
  if (budget <= 0) return out;
  const seen = new Set<string>([refKey(frameAt(g, state.pos))]);
  const push = (r: FrameRef) => {
    const k = refKey(r);
    if (out.length < budget && !seen.has(k)) {
      seen.add(k);
      out.push(r);
    }
  };
  const hasHeading = len(state.heading) > 1e-9;

  const fan = (node: string, skipEdge: string | null, depth: number) => {
    const ordered = (g.incident.get(node) ?? [])
      .filter((c) => c.edge.id !== skipEdge)
      .map((c) => ({ c, a: hasHeading ? angleDeg(state.heading, exitDir(g, c)) : 0 }))
      .sort((x, y) => x.a - y.a || (x.c.edge.id < y.c.edge.id ? -1 : x.c.edge.id > y.c.edge.id ? 1 : x.c.end === 'from' ? -1 : 1));
    const maxRank = Math.min(depth, Math.max(0, ...ordered.map(({ c }) => c.edge.frames - 1)));
    for (let rank = 1; rank <= maxRank && out.length < budget; rank++) {
      for (const { c } of ordered) {
        const i = c.end === 'from' ? rank : c.edge.frames - 1 - rank;
        if (rank <= c.edge.frames - 1) push(frameRef(g, c.edge.id, i));
      }
    }
  };

  if (state.pos.at === 'node') {
    fan(state.pos.node, null, Number.MAX_SAFE_INTEGER);
    return out;
  }

  const e = g.edges.get(state.pos.edge)!;
  const { T } = tangent(e, edgePhi(g, e, state.pos.t));
  const dir = hasHeading && state.heading[0] * T[0] + state.heading[1] * T[1] < 0 ? -1 : 1;
  const i0 = Math.round(state.pos.t);
  const aheadMax = Math.ceil(budget / 2);
  let reachedNode: string | null = null;
  for (let k = 1; k <= aheadMax; k++) {
    const i = i0 + dir * k;
    push(frameRef(g, e.id, i));
    if (i <= 0 || i >= e.frames - 1) {
      reachedNode = i <= 0 ? e.from : e.to;
      break;
    }
  }
  if (reachedNode) fan(reachedNode, e.id, opt.fanFrames);
  for (let k = 1; k <= opt.behindFrames; k++) push(frameRef(g, e.id, i0 - dir * k));
  return out;
}

