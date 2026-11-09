export const FONT_SIZE_STOPS = [8, 10, 12, 16, 24, 32, 48, 64, 96, 128] as const;
export const FONT_SIZE_MIN = 1;
// UI entry cap; persisted domain values above this remain readable.
export const FONT_SIZE_MAX = 128;

export function isFontSize(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= FONT_SIZE_MIN && value <= FONT_SIZE_MAX;
}

// Equal spacing keeps each preset easy to reach; custom sizes sit between
// their neighboring presets without rounding the requested pixel size.
export function fontSizePosition(size: number): number {
  if (size <= FONT_SIZE_STOPS[0]) return 0;
  for (let index = 1; index < FONT_SIZE_STOPS.length; index += 1) {
    const upper = FONT_SIZE_STOPS[index]!;
    const lower = FONT_SIZE_STOPS[index - 1]!;
    if (size <= upper) return index - 1 + (size - lower) / (upper - lower);
  }
  return FONT_SIZE_STOPS.length - 1;
}
