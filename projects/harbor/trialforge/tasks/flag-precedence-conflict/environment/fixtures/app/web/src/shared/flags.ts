// Browser-side flag accessors. The bundle is served the merged layer set the
// server resolved, so the ordering rule in /data/flags/README.md already
// applies by the time this runs. A key the server could not resolve is absent
// from the payload and falls through to the caller's fallback.

declare const __FLAGS__: Record<string, boolean | number>;

export function isEnabled(name: string, fallback = false): boolean {
  const value = __FLAGS__[name];
  return value === undefined ? fallback : Boolean(value);
}

export function getNumber(name: string, fallback: number): number {
  const value = __FLAGS__[name];
  return typeof value === "number" ? value : fallback;
}
