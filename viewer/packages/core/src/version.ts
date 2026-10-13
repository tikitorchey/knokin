/** Data revision `YYYY-MM-DD.N` (DD48). Compare with `compareRevision`, never as plain strings (N is numeric). */
const REVISION = /^(\d{4}-\d{2}-\d{2})\.(\d+)$/;

export function parseRevision(s: unknown): { date: string; n: number } | null {
  if (typeof s !== 'string') return null;
  const m = REVISION.exec(s);
  if (!m) return null;
  const [y, mo, d] = m[1]!.split('-').map(Number) as [number, number, number];
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  return { date: m[1]!, n: Number(m[2]) };
}

/** <0, 0, >0 like a sort comparator; null when either side is not a valid revision. */
export function compareRevision(a: unknown, b: unknown): number | null {
  const x = parseRevision(a);
  const y = parseRevision(b);
  if (!x || !y) return null;
  return x.date === y.date ? x.n - y.n : x.date < y.date ? -1 : 1;
}

/** One-line label for the viewer: `app v0.0.1 · data 2026-10-13.0`. A missing revision is shown as `-`. */
export function versionLabel(appVersion: string, meta: { revision?: unknown } | undefined): string {
  return `app v${appVersion} · data ${parseRevision(meta?.revision) ? (meta!.revision as string) : '-'}`;
}
