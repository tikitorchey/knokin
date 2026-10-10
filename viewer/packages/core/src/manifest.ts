import { buildGraph } from './graph';
import type { FramesDecl } from './resolve';
import type { Graph, ManifestGraphInput } from './types';

export const SCHEMA = 'knokin-turntable/0';

export const COORDS = {
  unit: 'deg',
  up: '+Z',
  thetaZero: 'camera-at -Y',
  thetaDir: 'ccw-from-above',
  phiDir: 'up-positive',
} as const;

export interface Manifest extends ManifestGraphInput {
  schema: string;
  coords: Record<string, string>;
  camera: Record<string, unknown>;
  image: { width: number; height: number; alpha: string; colorSpace: string; low?: { width: number; height: number } };
  frames: FramesDecl;
  start: { node: string };
}

export class SchemaError extends Error {}

/** Parse and gate a manifest: refuses a different schema version or coordinate convention. */
export function parseManifest(text: string): { manifest: Manifest; graph: Graph } {
  const m = JSON.parse(text) as Manifest;
  if (m.schema !== SCHEMA) throw new SchemaError(`unsupported schema ${JSON.stringify(m.schema)}; expected ${SCHEMA}`);
  for (const [k, v] of Object.entries(COORDS)) {
    if (m.coords?.[k] !== v) throw new SchemaError(`coords.${k} differs from the supported convention`);
  }
  const graph = buildGraph(m);
  if (!graph.nodes.has(m.start?.node)) throw new SchemaError(`start node ${m.start?.node} not found`);
  return { manifest: m, graph };
}
