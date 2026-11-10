import { curveLevels, type GrayCurve } from "../../domain/output-profiles/curve.ts";
import { canvasPaletteById, libraryFrame, type CanvasPaletteId } from "../library/canvas-palettes.ts";
import type { RGBA } from "../../renderer/renderer-types.ts";

// Scene label palette: the same curve plus paper/ink mapping the FontEditor
// preview uses (palettes/render.ts presetColors), except level 0 stays fully
// transparent so stacked labels compose instead of hiding each other.
export function sceneLabelPalette(curve: GrayCurve, appearance: CanvasPaletteId, inverse: boolean): RGBA[] {
  const base = canvasPaletteById(appearance);
  const paper = inverse ? base.ink : base.paper;
  const ink = inverse ? base.paper : base.ink;
  return curveLevels(curve).map((gray, index): RGBA => [
    Math.round(ink[0] + ((paper[0] - ink[0]) * gray) / 255),
    Math.round(ink[1] + ((paper[1] - ink[1]) * gray) / 255),
    Math.round(ink[2] + ((paper[2] - ink[2]) * gray) / 255),
    index === 0 ? 0 : 255,
  ]);
}

export function scenePaperCss(appearance: CanvasPaletteId, inverse: boolean): string {
  return libraryFrame(appearance, inverse).paperCss;
}
