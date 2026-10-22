import { toRenderSpec } from "../../renderer/render-spec.ts";
import type { PlaydateExportRequest } from "../../renderer/renderer-types.ts";
import type { VariantSettings } from "../../variants/model.ts";

export const PLAYDATE_ASCII = Array.from({ length: 95 }, (_, i) => String.fromCodePoint(i + 32)).join("");

export function playdateRequest(settings: VariantSettings, characters: string): PlaydateExportRequest {
  if (settings.profile !== "mono_1bit") throw new Error("Select Monochrome output to export for Playdate.");
  const spec = toRenderSpec({
    text: "", width: 1, height: 1, sizePx: settings.sizePx, axes: settings.axes,
    profile: settings.profile, rasterization: "free_type_mono", stemFitting: settings.stemFitting,
    diagonalFitting: settings.diagonalFitting,
    letterSpacingPx: settings.letterSpacingPx, kerning: settings.kerning,
  });
  const { size_px, axes, hinting, output_bits, mono_threshold, gray_gamma, missing_glyphs,
    kerning, metric_rounding, mono_raster } = spec;
  return {
    config: { size_px, axes, hinting, output_bits, mono_threshold, gray_gamma, missing_glyphs,
      kerning, metric_rounding, mono_raster, characters },
    pipeline: spec.pipeline!,
    letter_spacing_px: spec.letter_spacing_px,
  };
}

export function playdateFileName(name: string, sizePx: number): string {
  const stem = name.replace(/[^\p{L}\p{N}_-]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "font";
  return `${stem}-${sizePx}px.fnt`;
}
