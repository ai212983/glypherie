import type { OutputProfile, RGBA } from "../renderer/renderer-types.ts";
import { curveLevels } from "../features/grayscale/response-curve.ts";
import { canvasPaletteById, type CanvasPaletteId } from "../features/library/canvas-palettes.ts";
import type { PalettePreset } from "./model.ts";

export function paletteProfile(preset: PalettePreset): OutputProfile {
  return preset.curve.length === 2 ? "mono_1bit" : preset.curve.length === 4 ? "gray_2bit"
    : preset.curve.length === 16 ? "gray_4bit" : "gray_3bit";
}

export function presetColors(preset: PalettePreset, appearance: CanvasPaletteId, inverse: boolean): readonly RGBA[] {
  const base = canvasPaletteById(appearance);
  const paper = inverse ? base.ink : base.paper;
  const ink = inverse ? base.paper : base.ink;
  return curveLevels(preset.curve).map((gray): RGBA => [
    Math.round(ink[0] + (paper[0] - ink[0]) * gray / 255),
    Math.round(ink[1] + (paper[1] - ink[1]) * gray / 255),
    Math.round(ink[2] + (paper[2] - ink[2]) * gray / 255), 255,
  ]);
}
