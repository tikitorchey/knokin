import type { GEdge, Graph, Incident, ManifestGraphInput, Vec } from './types';

export function buildGraph(m: ManifestGraphInput): Graph {
  const nodes = new Map(m.nodes.map((n) => [n.id, { ...n }]));
  const edges = new Map<string, GEdge>(m.edges.map((e) => [e.id, { ...e }]));
  const incident = new Map<string, Incident[]>([...nodes.keys()].map((id) => [id, []]));
  for (const e of edges.values()) {
    if (!nodes.has(e.from) || !nodes.has(e.to)) throw new Error(`edge ${e.id}: unknown endpoint`);
    if (e.frames < 2) throw new Error(`edge ${e.id}: frames must be >= 2`);
    incident.get(e.from)!.push({ edge: e, end: 'from' });
    incident.get(e.to)!.push({ edge: e, end: 'to' });
  }
  for (const list of incident.values()) {
    list.sort((a, b) => (a.edge.id < b.edge.id ? -1 : a.edge.id > b.edge.id ? 1 : a.end === 'from' ? -1 : 1));
  }
  return { nodes, edges, incident };
}

export function totalFrames(g: Graph): number {
  let n = g.nodes.size;
  for (const e of g.edges.values()) n += e.frames - 2;
  return n;
}

const rad = (d: number) => (d * Math.PI) / 180;

export function edgePhi(g: Graph, e: GEdge, t: number): number {
  return g.nodes.get(e.from)!.phi + (e.delta[1] * t) / (e.frames - 1);
}

export function unit(v: Vec): Vec {
  const l = Math.hypot(v[0], v[1]);
  return l === 0 ? [0, 0] : [v[0] / l, v[1] / l];
}

export const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1];
export const len = (a: Vec) => Math.hypot(a[0], a[1]);

/** Angle between two non-zero vectors in degrees, [0, 180]. */
export function angleDeg(a: Vec, b: Vec): number {
  const c = dot(a, b) / (len(a) * len(b));
  return (Math.acos(Math.max(-1, Math.min(1, c))) * 180) / Math.PI;
}

/** Screen direction of an angle-space step (dTheta, dPhi) at elevation phi.
 *  Dragging right decreases theta; dragging down increases phi; theta is shortened by cos(phi). */
export function screenVec(dTheta: number, dPhi: number, phiDeg: number): Vec {
  return [-dTheta * Math.cos(rad(phiDeg)), dPhi];
}

/** Unit screen tangent of an edge (towards increasing t) at elevation phi, and degrees per frame there. */
export function tangent(e: GEdge, phiDeg: number): { T: Vec; L: number } {
  const v = screenVec(e.delta[0], e.delta[1], phiDeg);
  return { T: unit(v), L: len(v) / (e.frames - 1) };
}

/** Unit screen direction in which an incident edge leaves its end node. */
export function exitDir(g: Graph, inc: Incident): Vec {
  const sign = inc.end === 'from' ? 1 : -1;
  const n = g.nodes.get(inc.end === 'from' ? inc.edge.from : inc.edge.to)!;
  return unit(screenVec(sign * inc.edge.delta[0], sign * inc.edge.delta[1], n.phi));
}
