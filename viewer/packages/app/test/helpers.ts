import type { Closable } from '../src/cache';

export interface Fake extends Closable {
  key: string;
  width: number;
  height: number;
  closed: boolean;
}

export function fake(key: string): Fake {
  const f: Fake = { key, width: 4, height: 3, closed: false, close() { f.closed = true; } };
  return f;
}

/** A load function whose promises are resolved/rejected by the test. */
export function manualLoader() {
  const pending = new Map<string, { resolve: (f: Fake) => void; reject: (e: unknown) => void; signal: AbortSignal }>();
  const started: string[] = [];
  const created: Fake[] = [];
  const load = (key: string, signal: AbortSignal) =>
    new Promise<Fake>((resolve, reject) => {
      started.push(key);
      pending.set(key, {
        resolve: (f) => { created.push(f); resolve(f); },
        reject,
        signal,
      });
    });
  const finish = async (key: string) => {
    const p = pending.get(key);
    if (!p) throw new Error(`not loading: ${key}`);
    pending.delete(key);
    p.resolve(fake(key));
    await Promise.resolve();
    await Promise.resolve();
  };
  const fail = async (key: string) => {
    const p = pending.get(key);
    if (!p) throw new Error(`not loading: ${key}`);
    pending.delete(key);
    p.reject(new Error('boom'));
    await Promise.resolve();
    await Promise.resolve();
  };
  return { load, pending, started, created, finish, fail };
}

/** Loader that resolves on the next microtasks. */
export function instantLoader() {
  const created: Fake[] = [];
  const load = async (key: string) => {
    await Promise.resolve();
    const f = fake(key);
    created.push(f);
    return f;
  };
  return { load, created };
}

export const tick = async (n = 6) => { for (let i = 0; i < n; i++) await Promise.resolve(); };
