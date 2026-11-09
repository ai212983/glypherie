export const SCREEN_SIZE_KEY = "font-preview.screen.size";
export const SCREEN_SIZE_DEFAULT = 100;
export const SCREEN_SIZE_MIN = 50;
export const SCREEN_SIZE_MAX = 150;

export function readScreenSizePercent(): number {
  try {
    const raw = globalThis.localStorage?.getItem(SCREEN_SIZE_KEY);
    if (raw === null || raw === undefined) return SCREEN_SIZE_DEFAULT;
    const value = Number(raw);
    if (!Number.isFinite(value)) return SCREEN_SIZE_DEFAULT;
    return Math.min(SCREEN_SIZE_MAX, Math.max(SCREEN_SIZE_MIN, Math.round(value)));
  } catch {
    return SCREEN_SIZE_DEFAULT;
  }
}

export function writeScreenSizePercent(percent: number): void {
  try {
    const value = Number(percent);
    const clamped = Number.isFinite(value)
      ? Math.min(SCREEN_SIZE_MAX, Math.max(SCREEN_SIZE_MIN, Math.round(value)))
      : SCREEN_SIZE_DEFAULT;
    globalThis.localStorage?.setItem(SCREEN_SIZE_KEY, String(clamped));
  } catch {
    /* storage unavailable */
  }
}
