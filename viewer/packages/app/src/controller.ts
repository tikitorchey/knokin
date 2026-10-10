/**
 * Glue between input, the pure movement functions, and the frame cache. DOM-free and clock-injected so it
 * can be tested without a browser.
 */
import {
  DEFAULT_MOVE_OPT, DEFAULT_PREFETCH_OPT, frameAt, initialState, move, prefetch, refKey,
  type FrameRef, type Graph, type MoveOpt, type PrefetchOpt, type State,
} from '@knokin/core';
import type { FrameCache, Closable } from './cache';
import type { Metrics } from './metrics';

export interface Drawable extends Closable {
  readonly width: number;
  readonly height: number;
}

export interface ControllerOpt {
  move: MoveOpt;
  prefetch: PrefetchOpt;
  /** Number of frames kept in the want-list around the current position. */
  budget: number;
}

export const DEFAULT_CONTROLLER_OPT: ControllerOpt = {
  move: DEFAULT_MOVE_OPT,
  prefetch: DEFAULT_PREFETCH_OPT,
  budget: 16,
};

export interface ShowEvent<T> {
  bitmap: T;
  key: string;
  low: boolean;
  /** Timestamp (ms) of the input that led to this frame; null when not input-driven. */
  inputAt: number | null;
}

export class Controller<T extends Drawable> {
  state: State;
  opt: ControllerOpt;
  private shownKey: string | null = null;
  private shownLow = false;
  private currentRef: FrameRef;
  private pending: { key: string; at: number } | null = null;

  constructor(
    readonly graph: Graph,
    startNode: string,
    private readonly cache: FrameCache<T>,
    private readonly lowCache: FrameCache<T> | null,
    private readonly show: (e: ShowEvent<T>) => void,
    private readonly metrics: Metrics,
    private readonly now: () => number,
    opt: Partial<ControllerOpt> = {},
  ) {
    this.opt = { ...DEFAULT_CONTROLLER_OPT, ...opt };
    this.state = initialState(startNode);
    this.currentRef = frameAt(graph, this.state.pos);
    this.refresh(null);
  }

  get currentKey(): string {
    return refKey(this.currentRef);
  }

  /** Apply one pointer movement (screen px since the previous event). `at` is the event timestamp. */
  drag(dx: number, dy: number, at: number = this.now()): void {
    this.state = move(this.graph, this.state, { dx, dy }, this.opt.move);
    this.refresh(at);
  }

  /** Jump to a node (e.g. reset). */
  reset(node: string): void {
    this.state = initialState(node);
    this.refresh(null);
  }

  /** A frame finished loading: if it is the one we are waiting for, show it. */
  onReady(key: string): void {
    if (key !== this.currentKey) return;
    const bm = this.cache.get(key);
    if (!bm) return;
    const at = this.pending?.key === key ? this.pending.at : null;
    this.pending = null;
    this.present(bm, key, false, at);
  }

  /** A low-res node image finished loading while its full image is not ready yet. */
  onLowReady(nodeKey: string): void {
    if (nodeKey !== this.currentKey || this.cache.has(nodeKey) || this.shownKey === nodeKey) return;
    const bm = this.lowCache?.get(nodeKey);
    if (bm) this.present(bm, nodeKey, true, this.pending?.at ?? null);
  }

  setOpt(opt: Partial<ControllerOpt>): void {
    this.opt = { ...this.opt, ...opt };
    this.refresh(null);
  }

  private refresh(inputAt: number | null): void {
    this.currentRef = frameAt(this.graph, this.state.pos);
    const key = this.currentKey;
    const ahead = prefetch(this.graph, this.state, this.opt.budget, this.opt.prefetch);
    this.cache.want([key, ...ahead.map(refKey)]);

    if (key === this.shownKey && !this.shownLow) return; // same full-quality frame, nothing to draw
    const bm = this.cache.get(key);
    if (bm) {
      this.metrics.inc('hit');
      this.pending = null;
      this.present(bm, key, false, inputAt);
      return;
    }
    // Not decoded yet. Count the miss once per displayed frame, and keep whatever is on screen,
    // except that a node has a low-resolution stand-in.
    if (this.pending?.key !== key) {
      this.metrics.inc('miss');
      this.pending = { key, at: inputAt ?? this.now() };
    }
    if (this.currentRef.kind === 'node' && this.lowCache && this.shownKey !== key) {
      const low = this.lowCache.get(key);
      if (low) this.present(low, key, true, this.pending.at);
    }
  }

  private present(bitmap: T, key: string, low: boolean, inputAt: number | null): void {
    this.shownKey = key;
    this.shownLow = low;
    if (low) this.metrics.inc('lowShown');
    this.show({ bitmap, key, low, inputAt });
  }
}
