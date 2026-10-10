export type Vec = readonly [number, number];

export interface ManifestGraphInput {
  nodes: { id: string; theta: number; phi: number }[];
  edges: { id: string; kind: string; from: string; to: string; delta: [number, number]; frames: number }[];
}

export interface GNode {
  id: string;
  theta: number;
  phi: number;
}

export interface GEdge {
  id: string;
  kind: string;
  from: string;
  to: string;
  delta: readonly [number, number];
  frames: number;
}

/** An edge as seen from one of its end nodes. */
export interface Incident {
  edge: GEdge;
  end: 'from' | 'to';
}

export interface Graph {
  nodes: Map<string, GNode>;
  edges: Map<string, GEdge>;
  incident: Map<string, Incident[]>;
}

export type Pos = { at: 'node'; node: string } | { at: 'edge'; edge: string; t: number };

/** Logical frame reference. Edge refs are interior frames only (1 <= i <= frames-2). */
export type FrameRef = { kind: 'node'; node: string } | { kind: 'edge'; edge: string; i: number };

/** Unit screen-space direction of the last motion; [0, 0] when unknown. */
export type Heading = Vec;

export interface State {
  pos: Pos;
  heading: Heading;
  /** Drag (px, screen space) accumulated while resting on a node. */
  acc: Vec;
}

export interface MoveOpt {
  /** Sensitivity: degrees of view rotation per screen pixel. */
  degPerPx: number;
  /** Drag distance needed to leave a node (stickiness). */
  turnPx: number;
  /** Largest allowed angle (deg) between the drag and the chosen edge; beyond it the position stays. */
  deadZoneDeg: number;
  /** Straight-ahead edge is preferred if within this many degrees of the best edge. */
  stickyDeg: number;
}

export const DEFAULT_MOVE_OPT: MoveOpt = { degPerPx: 0.25, turnPx: 12, deadZoneDeg: 45, stickyDeg: 15 };

export interface PrefetchOpt {
  /** Frames to prefetch on each outgoing edge when the end of the current edge is within reach. */
  fanFrames: number;
  /** Frames behind the current position to keep. */
  behindFrames: number;
}

export const DEFAULT_PREFETCH_OPT: PrefetchOpt = { fanFrames: 3, behindFrames: 2 };
