import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve as pathResolve } from 'node:path';
import { buildGraph, parseManifest, type Graph, type Pos, type State } from '../src';

const here = dirname(fileURLToPath(import.meta.url));
export const TESTDATA = pathResolve(here, '../../../../testdata');

export function readJson<T>(rel: string): T {
  return JSON.parse(readFileSync(pathResolve(TESTDATA, rel), 'utf8')) as T;
}

export function loadGraph(manifestRel: string): Graph {
  return parseManifest(readFileSync(pathResolve(TESTDATA, manifestRel), 'utf8')).graph;
}

export { buildGraph };

export interface StateJson {
  pos: Pos;
  heading?: [number, number];
  acc?: [number, number];
}

export const toState = (s: StateJson): State => ({ pos: s.pos, heading: s.heading ?? [0, 0], acc: s.acc ?? [0, 0] });
