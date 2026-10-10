import { resolve, type FrameRef, type FramesDecl } from '@knokin/core';

/** Inverse of `refKey`: 'n:n000' / 'e:e0001/7'. */
export function parseKey(key: string): FrameRef {
  if (key.startsWith('n:')) return { kind: 'node', node: key.slice(2) };
  const m = /^e:([^/]+)\/(\d+)$/.exec(key);
  if (!m) throw new Error(`bad frame key ${key}`);
  return { kind: 'edge', edge: m[1] as string, i: Number(m[2]) };
}

/** Cache key -> URL path (relative to the manifest), via `resolve` only. */
export function makeUrlOf(frames: FramesDecl, low: boolean): (key: string) => string {
  return (key) => resolve(frames, parseKey(key), { low });
}
