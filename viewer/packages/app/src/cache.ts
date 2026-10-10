/**
 * Decoded-frame cache with a prioritised want-list.
 *
 * `want(items)` replaces the set of frames we care about, highest priority first. Loads start in that
 * order under a concurrency limit; queued loads that fell out of the list are dropped and in-flight ones
 * are aborted. Decoded frames beyond `maxItems` are evicted (unwanted + least recently used first, then the
 * lowest-priority wanted ones) and closed so their memory is released.
 */

export interface Closable {
  close(): void;
}

export type LoadFn<T extends Closable> = (key: string, signal: AbortSignal) => Promise<T>;

export interface CacheOpt {
  maxItems: number;
  concurrency: number;
}

interface Entry<T extends Closable> {
  key: string;
  value?: T;
  ctl?: AbortController;
  state: 'queued' | 'loading' | 'ready';
  lastUsed: number;
}

export class FrameCache<T extends Closable> {
  private entries = new Map<string, Entry<T>>();
  private wanted: string[] = [];
  private active = 0;
  private tick = 0;
  private failed = new Set<string>();
  opt: CacheOpt;

  constructor(
    private readonly load: LoadFn<T>,
    opt: CacheOpt,
    private readonly hooks: { onReady?: (key: string) => void; onFail?: (key: string, err: unknown) => void; onAbort?: (key: string) => void } = {},
  ) {
    this.opt = { ...opt };
  }

  get readyCount(): number {
    let n = 0;
    for (const e of this.entries.values()) if (e.state === 'ready') n++;
    return n;
  }

  get inFlight(): number {
    return this.active;
  }

  get wantedKeys(): readonly string[] {
    return this.wanted;
  }

  has(key: string): boolean {
    return this.entries.get(key)?.state === 'ready';
  }

  /** Returns the decoded frame and marks it recently used. */
  get(key: string): T | undefined {
    const e = this.entries.get(key);
    if (!e || e.state !== 'ready') return undefined;
    e.lastUsed = ++this.tick;
    return e.value;
  }

  want(keys: string[]): void {
    this.wanted = [...new Set(keys)];
    const wantSet = new Set(this.wanted);
    for (const [key, e] of this.entries) {
      if (wantSet.has(key)) continue;
      if (e.state === 'queued') this.entries.delete(key);
      else if (e.state === 'loading') {
        e.ctl?.abort();
        this.entries.delete(key);
        this.active--;
        this.hooks.onAbort?.(key);
      }
    }
    for (const key of this.wanted) {
      if (!this.entries.has(key) && !this.failed.has(key)) {
        this.entries.set(key, { key, state: 'queued', lastUsed: 0 });
      }
    }
    this.evict();
    this.pump();
  }

  /** Retry frames that failed earlier (e.g. after a network error). */
  clearFailures(): void {
    this.failed.clear();
  }

  private pump(): void {
    for (const key of this.wanted) {
      if (this.active >= this.opt.concurrency) return;
      const e = this.entries.get(key);
      if (!e || e.state !== 'queued') continue;
      this.start(e);
    }
  }

  private start(e: Entry<T>): void {
    e.state = 'loading';
    e.ctl = new AbortController();
    this.active++;
    const { signal } = e.ctl;
    this.load(e.key, signal).then(
      (value) => {
        if (signal.aborted || this.entries.get(e.key) !== e) {
          value.close();
          return;
        }
        this.active--;
        e.value = value;
        e.state = 'ready';
        e.lastUsed = ++this.tick;
        this.evict();
        this.hooks.onReady?.(e.key);
        this.pump();
      },
      (err: unknown) => {
        if (signal.aborted || this.entries.get(e.key) !== e) return;
        this.active--;
        this.entries.delete(e.key);
        this.failed.add(e.key);
        this.hooks.onFail?.(e.key, err);
        this.pump();
      },
    );
  }

  private evict(): void {
    let over = this.readyCount - this.opt.maxItems;
    if (over <= 0) return;
    const rank = new Map(this.wanted.map((k, i) => [k, i]));
    const ready = [...this.entries.values()].filter((e) => e.state === 'ready');
    ready.sort((a, b) => {
      const aw = rank.has(a.key), bw = rank.has(b.key);
      if (aw !== bw) return aw ? 1 : -1; // unwanted first
      if (!aw) return a.lastUsed - b.lastUsed; // then least recently used
      return (rank.get(b.key) as number) - (rank.get(a.key) as number); // then lowest priority
    });
    for (const e of ready) {
      if (over <= 0) break;
      e.value?.close();
      this.entries.delete(e.key);
      over--;
    }
  }

  dispose(): void {
    this.wanted = [];
    for (const e of this.entries.values()) {
      e.ctl?.abort();
      e.value?.close();
    }
    this.entries.clear();
    this.active = 0;
  }
}
