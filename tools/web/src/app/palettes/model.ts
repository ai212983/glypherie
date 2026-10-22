import { linearCurve, type GrayCurve } from "../features/grayscale/response-curve.ts";

export interface PalettePreset {
  id: number;
  name: string;
  curve: GrayCurve;
}

export const MONOCHROME_ID = 0;
export const MONOCHROME: PalettePreset = { id: MONOCHROME_ID, name: "Monochrome", curve: linearCurve(2) };

export function resolvePalette(presets: readonly PalettePreset[], id?: number): PalettePreset {
  return presets.find((preset) => preset.id === id) ?? MONOCHROME;
}

export function validatePalette(preset: PalettePreset): void {
  if (!Number.isInteger(preset.id) || preset.id < 0 || typeof preset.name !== "string" || preset.name.length > 80
    || !Array.isArray(preset.curve) || ![2, 4, 8, 16].includes(preset.curve.length)
    || !preset.curve[0]?.pinned || !preset.curve.at(-1)?.pinned
    || preset.curve.some((level) => !Number.isFinite(level.value) || level.value < 0 || level.value > 255
      || !Number.isFinite(level.slope) || typeof level.pinned !== "boolean")) {
    throw new Error("Invalid palette preset.");
  }
}
