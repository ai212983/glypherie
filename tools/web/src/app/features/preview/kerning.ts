// cspell:words unkeyed
// Pure kerning-display helpers. Same rules as the legacy preview:
// printable-ASCII scope, signed 26.6 adjustments, substring/codepoint filter.
export interface KerningPairView {
  left: number;
  right: number;
  adjustment_26_6: number;
}

// Cache identity for one font at one size/axes coordinate. The font id is
// part of the key: two fonts may share every coordinate while having
// different source tables, so an unkeyed cache would serve stale pairs.
export function kerningQueryKey(fontId: string, sizePx: number, axes: Record<string, number>): string {
  return `${fontId} ${kerningCacheKey(sizePx, axes)}`;
}

export function kerningCacheKey(sizePx: number, axes: Record<string, number>): string {
  const entries = Object.entries(axes ?? {})
    .filter(([, value]) => Number.isFinite(value))
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return JSON.stringify({ sizePx, axes: entries });
}

export function formatKerningAdjustment(adjustment266: number): string {
  const px = adjustment266 / 64;
  const text = (px > 0 ? "+" : "") + String(px);
  return `${text} px`;
}

export function pairCodepoints(left: number, right: number): string {
  const hex = (cp: number): string => `U+${cp.toString(16).toUpperCase().padStart(4, "0")}`;
  return `${hex(left)} ${hex(right)}`;
}

export function filterKerningPairs(pairs: KerningPairView[], query: string): KerningPairView[] {
  const text = (query ?? "").trim();
  if (!text) return pairs;
  const upper = text.toUpperCase();
  return pairs.filter((pair) => {
    const chars = String.fromCodePoint(pair.left, pair.right);
    return chars.includes(text)
      || chars.toUpperCase().includes(upper)
      || pairCodepoints(pair.left, pair.right).includes(upper);
  });
}
