/**
 * Scripted drag path for repeatable on-device measurements: one tap runs the same sequence on every phone, so
 * numbers (latency, hit rate, decode time, heap) can be compared across settings. Not a model of real use: it only
 * makes runs comparable. The controller is driven exactly like the pointer handler (drag(dx, dy, timeStamp)).
 */
import type { Controller } from './controller';
import type { Drawable } from './controller';

export interface Leg {
  /** Unit screen direction of the drag. */
  dir: [number, number];
  seconds: number;
}

/** Equator sweep, a turn onto a meridian, a diagonal, a reversal. (screen: x right, y down) */
export const DEFAULT_PATH: Leg[] = [
  { dir: [1, 0], seconds: 4 },
  { dir: [0, 1], seconds: 2 },
  { dir: [1, 1], seconds: 2 },
  { dir: [-1, 0], seconds: 4 },
  { dir: [0, -1], seconds: 3 },
  { dir: [-1, -1], seconds: 2 },
  { dir: [1, 0], seconds: 3 },
];

export interface BenchOpt {
  /** Finger speed in CSS px / s. */
  speedPxPerSec: number;
  path: Leg[];
}

export const DEFAULT_BENCH_OPT: BenchOpt = { speedPxPerSec: 400, path: DEFAULT_PATH };

/** Resolves when the path has been played. `tick` is called on every animation frame (for HUD updates etc.). */
export function runBench<T extends Drawable>(c: Controller<T>, opt: BenchOpt, tick?: () => void): Promise<{ wallMs: number }> {
  return new Promise((resolve) => {
    const t0 = performance.now();
    let last = t0;
    let leg = 0;
    let legStart = t0;
    const step = (now: number) => {
      const cur = opt.path[leg];
      if (!cur) return resolve({ wallMs: now - t0 });
      const dt = Math.min(now - last, 100) / 1000; // a stalled tab must not turn into one huge drag
      last = now;
      const n = Math.hypot(cur.dir[0], cur.dir[1]) || 1;
      const px = opt.speedPxPerSec * dt;
      c.drag((cur.dir[0] / n) * px, (cur.dir[1] / n) * px, now);
      tick?.();
      if (now - legStart >= cur.seconds * 1000) {
        leg++;
        legStart = now;
      }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}
