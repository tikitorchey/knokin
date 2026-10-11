/** Small measurement toolkit: rolling samples with percentiles, plus plain counters. */

export interface Summary {
  n: number;
  mean: number;
  p50: number;
  p95: number;
  max: number;
}

export class Samples {
  private buf: number[] = [];
  constructor(private readonly cap = 1000) {}

  clear(): void {
    this.buf = [];
  }

  add(v: number): void {
    this.buf.push(v);
    if (this.buf.length > this.cap) this.buf.shift();
  }

  summary(): Summary {
    const n = this.buf.length;
    if (n === 0) return { n: 0, mean: 0, p50: 0, p95: 0, max: 0 };
    const s = [...this.buf].sort((a, b) => a - b);
    const q = (p: number) => s[Math.min(n - 1, Math.floor(p * n))] as number;
    return { n, mean: s.reduce((a, b) => a + b, 0) / n, p50: q(0.5), p95: q(0.95), max: s[n - 1] as number };
  }
}

export class Metrics {
  readonly latency = new Samples(); // pointer event -> frame drawn (ms)
  readonly fetchMs = new Samples();
  readonly decodeMs = new Samples();
  readonly frameBytes = new Samples();
  readonly counters: Record<string, number> = {};

  /** Forget everything measured so far (start of a scripted run). */
  reset(): void {
    for (const s of [this.latency, this.fetchMs, this.decodeMs, this.frameBytes]) s.clear();
    for (const k of Object.keys(this.counters)) delete this.counters[k];
  }

  inc(name: string, by = 1): void {
    this.counters[name] = (this.counters[name] ?? 0) + by;
  }

  count(name: string): number {
    return this.counters[name] ?? 0;
  }

  /** Share of frame requests that were ready on time (cache hit at the moment of display). */
  hitRate(): number {
    const h = this.count('hit');
    const m = this.count('miss');
    return h + m === 0 ? 1 : h / (h + m);
  }

  snapshot(): Record<string, unknown> {
    return {
      latency: this.latency.summary(),
      fetchMs: this.fetchMs.summary(),
      decodeMs: this.decodeMs.summary(),
      frameBytes: this.frameBytes.summary(),
      counters: { ...this.counters },
      hitRate: this.hitRate(),
    };
  }
}

const f1 = (v: number) => v.toFixed(1);

export function formatStats(m: Metrics, extra: Record<string, string | number> = {}): string {
  const l = m.latency.summary();
  const d = m.decodeMs.summary();
  const f = m.fetchMs.summary();
  const b = m.frameBytes.summary();
  const lines = [
    `latency ms  p50 ${f1(l.p50)}  p95 ${f1(l.p95)}  max ${f1(l.max)}  (n=${l.n})`,
    `fetch ms    p50 ${f1(f.p50)}  p95 ${f1(f.p95)}`,
    `decode ms   p50 ${f1(d.p50)}  p95 ${f1(d.p95)}`,
    `frame KB    mean ${f1(b.mean / 1024)}  max ${f1(b.max / 1024)}`,
    `hit ${(m.hitRate() * 100).toFixed(0)}%  miss ${m.count('miss')}  fail ${m.count('fail')}  abort ${m.count('abort')}`,
  ];
  for (const [k, v] of Object.entries(extra)) lines.push(`${k} ${v}`);
  return lines.join('\n');
}
