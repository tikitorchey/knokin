import type { FrameRef } from './types';

export interface FramesDecl {
  base: string;
  node: string;
  nodeLow?: string;
  edge: string;
}

// Template subset shared with Python: {name} and {name:0Nd} only.
const PLACEHOLDER = /\{(\w+)(?::0(\d+)d)?\}/g;

export function renderTemplate(template: string, values: Record<string, string | number>): string {
  const out = template.replace(PLACEHOLDER, (_m, name: string, width?: string) => {
    const v = values[name];
    if (v === undefined) throw new Error(`missing template value: ${name}`);
    return width ? String(v).padStart(Number(width), '0') : String(v);
  });
  if (/[{}]/.test(out)) throw new Error(`unsupported template syntax: ${template}`);
  return out;
}

/** The only place that knows file naming. */
export function resolve(frames: FramesDecl, ref: FrameRef, opts: { low?: boolean } = {}): string {
  if (ref.kind === 'node') {
    const tpl = opts.low ? frames.nodeLow : frames.node;
    if (!tpl) throw new Error('frames.nodeLow is not declared');
    return frames.base + renderTemplate(tpl, { node: ref.node });
  }
  if (opts.low) throw new Error('edge frames have no low-resolution variant');
  return frames.base + renderTemplate(frames.edge, { edge: ref.edge, i: ref.i });
}
