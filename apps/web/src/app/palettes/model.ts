import { linearCurve, type GrayCurve } from "../domain/output-profiles/curve.ts";
import type { OutputProfile } from "../renderer/renderer-types.ts";

export interface PalettePreset {
  id: number;
  name: string;
  curve: GrayCurve;
  revision: number;
}

export const MONOCHROME_ID = 0;
export const MONOCHROME: PalettePreset = { id: MONOCHROME_ID, name: "Monochrome", curve: linearCurve(2), revision: 1 };

// Owner-held semantic edits. Index edits carry the depth the client saw so a
// stale depth after a concurrent resize fails instead of editing another
// level; whole-curve replacement carries the revision the client saw so a
// stale snapshot is rejected. Every edit reads the latest row, applies an
// existing pure curve operation, and persists inside one owner transaction.
export type PaletteEdit =
  | { kind: "rename"; name: string }
  | { kind: "setLevel"; index: number; value: number; depth: number }
  | { kind: "pinLevel"; index: number; depth: number }
  | { kind: "unpinLevel"; index: number; depth: number }
  | { kind: "resize"; count: number }
  | { kind: "replace"; curve: GrayCurve; expectedRevision: number };

export function resolvePalette(presets: readonly PalettePreset[], id?: number): PalettePreset {
  return presets.find((preset) => preset.id === id) ?? MONOCHROME;
}

// Curve length selects the output profile; depths without a dedicated
// profile keep the established 3-bit gray fallback.
export function profileForCurveLength(length: number): OutputProfile {
  return length === 2 ? "mono_1bit" : length === 4 ? "gray_2bit" : length === 16 ? "gray_4bit" : "gray_3bit";
}

export function profileForCurve(curve: GrayCurve): OutputProfile {
  return profileForCurveLength(curve.length);
}
