import type { FrameRef, Graph, Pos } from './types';

/** Reference for frame i of an edge; endpoints are the shared node images. */
export function frameRef(g: Graph, edgeId: string, i: number): FrameRef {
  const e = g.edges.get(edgeId);
  if (!e) throw new Error(`unknown edge ${edgeId}`);
  if (i <= 0) return { kind: 'node', node: e.from };
  if (i >= e.frames - 1) return { kind: 'node', node: e.to };
  return { kind: 'edge', edge: e.id, i };
}

/** Nearest integer frame (halves round up). No cross-fade: a plain switch. */
export function frameAt(g: Graph, pos: Pos): FrameRef {
  if (pos.at === 'node') return { kind: 'node', node: pos.node };
  return frameRef(g, pos.edge, Math.round(pos.t));
}

export function refKey(r: FrameRef): string {
  return r.kind === 'node' ? `n:${r.node}` : `e:${r.edge}/${r.i}`;
}
