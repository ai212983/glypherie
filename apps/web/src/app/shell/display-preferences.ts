import { DEFAULT_CANVAS_PALETTE_ID, isCanvasPaletteId, type CanvasPaletteId } from "../features/library/canvas-palettes.ts";
import { DEFAULT_PREVIEW_ZOOM, PREVIEW_ZOOM_STOPS } from "../renderer/display-scaling.ts";

export const GLOBAL_ZOOM_KEY = "font-preview.zoom.global";
export function validPreviewZoom(value: unknown): value is number {
  return typeof value === "number" && PREVIEW_ZOOM_STOPS.includes(value);
}
export function readGlobalZoom(): number {
  try {
    const current = Number(globalThis.localStorage?.getItem(GLOBAL_ZOOM_KEY));
    if (validPreviewZoom(current)) return current;
    const library: unknown = JSON.parse(globalThis.localStorage?.getItem("font-preview.library") ?? "null");
    if (library && typeof library === "object" && "zoom" in library && validPreviewZoom(library.zoom)) return library.zoom;
    const legacy = Number(globalThis.localStorage?.getItem("font-preview.zoom.specimen"));
    if (validPreviewZoom(legacy)) return legacy;
  } catch { /* storage unavailable */ }
  return DEFAULT_PREVIEW_ZOOM;
}
export function writeGlobalZoom(zoom: number): void {
  try { globalThis.localStorage?.setItem(GLOBAL_ZOOM_KEY, String(zoom)); }
  catch { /* storage unavailable */ }
}

export interface CanvasAppearance {
  palette: CanvasPaletteId;
  inverse: boolean;
}
export const GLOBAL_CANVAS_KEY = "font-preview.canvas";
export function readCanvasAppearance(): CanvasAppearance {
  const defaults: CanvasAppearance = { palette: DEFAULT_CANVAS_PALETTE_ID, inverse: false };
  try {
    const raw = globalThis.localStorage?.getItem(GLOBAL_CANVAS_KEY)
      ?? globalThis.localStorage?.getItem("font-preview.library");
    const parsed: unknown = JSON.parse(raw ?? "null");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return defaults;
    const value = parsed as Record<string, unknown>;
    return {
      palette: isCanvasPaletteId(value.palette) ? value.palette : defaults.palette,
      inverse: typeof value.inverse === "boolean" ? value.inverse : defaults.inverse,
    };
  } catch { return defaults; }
}
export function writeCanvasAppearance(canvas: CanvasAppearance): void {
  try { globalThis.localStorage?.setItem(GLOBAL_CANVAS_KEY, JSON.stringify(canvas)); }
  catch { /* storage unavailable */ }
}
