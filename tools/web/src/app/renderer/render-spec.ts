// Exact WASM render-request shape (tools/wasm RenderSpec, deny_unknown_fields).
// Same mapping the legacy preview used: whole-pixel tracking for the
// candidate renderer and the separated pipeline, fractional Gray tracking
// otherwise, and the automatic Mono engine policy for candidate 1-bit unless
// upstream Mono is forced.
import type {
  MonoDropout,
  MonoRaster,
  OutputProfile,
  RendererRole,
  Rasterization,
  RenderSpec,
  RGBA,
  StemFitting,
} from "./renderer-types.js";
import { WORKING_PREVIEW_DEFAULTS, resolveWorkingPreviewPolicy } from "./preview-policy.ts";

export { WORKING_PREVIEW_DEFAULTS } from "./preview-policy.ts";

export function profileBits(profile: OutputProfile): number {
  return profile === "mono_1bit" ? 1 : profile === "gray_2bit" ? 2 : profile === "gray_4bit" ? 4 : 3;
}

export const TEXT_DEFAULT = "Pack my box with five dozen liquor jugs.";
export const MAX_TEXT_LENGTH = 8192;
const INK: [number, number, number, number] = [36, 40, 43, 255];
const PAPER: [number, number, number, number] = [255, 255, 255, 255];

export interface RenderRequestOptions {
  text: string;
  sizePx: number;
  axes: Record<string, number>;
  profile: OutputProfile;
  width: number;
  height: number;
  role?: RendererRole;
  rasterization?: Rasterization;
  letterSpacingPx?: number | string;
  kerning?: boolean;
  stemFitting?: StemFitting;
  diagonalFitting?: boolean;
  monoRaster?: MonoRaster;
  monoThreshold?: number;
  grayGamma?: number;
  palette?: readonly RGBA[];
}

// Logical render width for a display box at integer zoom: the native request
// shrinks so integer magnification fills the box.
export function logicalBounds(display: number, zoom: number): number {
  return Math.min(4096, Math.max(1, Math.ceil(display / zoom)));
}

export function normalizedSpacing(
  value: number | string | undefined,
  profile: OutputProfile,
  role?: RendererRole,
): number {
  const number = Number(value);
  const clamped = Number.isFinite(number) ? Math.min(4, Math.max(-2, number)) : 0;
  const integer = role === "candidate" || profile === "mono_1bit";
  return integer ? Math.sign(clamped) * Math.floor(Math.abs(clamped) + 0.5) : clamped;
}

export interface ResolvedRenderColors {
  foreground: [number, number, number, number];
  background: [number, number, number, number];
  palette?: [number, number, number, number][];
}

function normalizeChannel(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 255 ? value : null;
}

function normalizeColor(value: unknown): [number, number, number, number] | null {
  if (!Array.isArray(value) || value.length !== 4) return null;
  const r = normalizeChannel(value[0]);
  const g = normalizeChannel(value[1]);
  const b = normalizeChannel(value[2]);
  const a = normalizeChannel(value[3]);
  if (r === null || g === null || b === null || a === null) return null;
  return [r, g, b, a];
}

// Palette-only color contract (tools/generator surface palette_map): a full
// palette holds exactly 2^bits entries and applies verbatim — entry 0 is
// the paper (zero coverage leaves it untouched) and every nonzero entry
// applies directly with its own RGBA, uneven differences included, with no
// extra coverage alpha. An omitted palette renders the established default
// (ink over paper) with no native palette, so default bytes never change.
// Anything else is rejected.
export function resolveRenderColors(
  palette: readonly RGBA[] | undefined,
  profile: OutputProfile,
): ResolvedRenderColors {
  if (palette === undefined) return { foreground: [...INK], background: [...PAPER] };
  if (!Array.isArray(palette)) throw new Error("Invalid palette: expected an array of RGBA colors.");
  const levels = 1 << profileBits(profile);
  if (palette.length !== levels) {
    throw new Error(`Invalid palette: expected exactly ${levels} entries for profile ${profile}, got ${palette.length}.`);
  }
  const entries: [number, number, number, number][] = [];
  for (const entry of palette) {
    const color = normalizeColor(entry);
    if (!color) throw new Error("Invalid palette color: expected [r, g, b, a] with byte channels 0..255.");
    entries.push(color);
  }
  // The native background is entry 0 (cloned, never aliased); the foreground
  // stays the default ink and applies only when no native palette is sent.
  return { foreground: [...INK], background: [...(entries[0] ?? PAPER)], palette: entries };
}

const MONO_DROPOUTS: readonly MonoDropout[] = ["off", "simple", "smart"];

export const DEFAULT_MONO_RASTER: MonoRaster = { dropout: "smart", includeStubs: false, fontInstructions: false };
// Font scan instructions take precedence over these fallback scan settings.
export const PREVIEW_MONO_RASTER: MonoRaster = {
  dropout: WORKING_PREVIEW_DEFAULTS.dropout,
  includeStubs: WORKING_PREVIEW_DEFAULTS.includeStubs,
  fontInstructions: WORKING_PREVIEW_DEFAULTS.fontInstructions,
};

// Manual scan-converter settings, restricted to candidate Mono like stem
// fitting: other roles/profiles omit them so the native path keeps coverage.
export function resolveMonoRaster(
  value: MonoRaster | undefined,
): { dropout: MonoDropout; include_stubs: boolean; font_instructions: boolean } | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Invalid mono raster settings: expected { dropout, includeStubs, fontInstructions }.");
  }
  const dropout = value.dropout === undefined ? "smart" : value.dropout;
  if (!MONO_DROPOUTS.includes(dropout as MonoDropout)) {
    throw new Error(`Invalid mono raster dropout: expected one of ${MONO_DROPOUTS.join(", ")}.`);
  }
  const includeStubs = value.includeStubs === undefined ? false : value.includeStubs;
  if (typeof includeStubs !== "boolean") {
    throw new Error("Invalid mono raster stubs flag: expected a boolean.");
  }
  const fontInstructions = value.fontInstructions === undefined ? false : value.fontInstructions;
  if (typeof fontInstructions !== "boolean") {
    throw new Error("Invalid mono raster font-instructions flag: expected a boolean.");
  }
  return { dropout: dropout as MonoDropout, include_stubs: includeStubs, font_instructions: fontInstructions };
}

export function toRenderSpec({
  text, sizePx, axes, profile, width, height, role, rasterization,
  letterSpacingPx, kerning, stemFitting, diagonalFitting, monoRaster, monoThreshold, grayGamma,
  palette,
}: RenderRequestOptions): RenderSpec {
  const colors = resolveRenderColors(palette, profile);
  const separated = rasterization !== undefined;
  const effectiveRole = separated ? "candidate" : role;
  const previewPolicy = separated && profile === "mono_1bit"
    ? resolveWorkingPreviewPolicy({
      fitting: stemFitting === "upstream_mono" ? "upstream_mono"
        : stemFitting === "font_hints_first" ? "font_hints_auto" : undefined,
      // URL omission preserves the historical diagonal-off preference.
      diagonalFitting: diagonalFitting ?? false,
    })
    : null;
  const scan = effectiveRole === "candidate" && profile === "mono_1bit"
    ? previewPolicy !== null
      ? { ...previewPolicy.mono_raster }
      : resolveMonoRaster(monoRaster)
    : undefined;
  return {
    text,
    width: Math.min(4096, Math.max(1, Math.ceil(width))),
    height: Math.min(4096, Math.max(1, Math.ceil(height))),
    size_px: sizePx,
    axes: { ...axes },
    letter_spacing_px: normalizedSpacing(letterSpacingPx, profile, effectiveRole),
    hinting: previewPolicy?.hinting
      ?? (effectiveRole === "candidate" && profile === "mono_1bit" && stemFitting !== "upstream_mono"
        ? "auto_fallback" : "auto"),
    output_bits: previewPolicy?.output_bits ?? profileBits(profile),
    mono_threshold: monoThreshold ?? previewPolicy?.mono_threshold ?? 128,
    gray_gamma: grayGamma ?? previewPolicy?.gray_gamma ?? 1.0,
    missing_glyphs: previewPolicy?.missing_glyphs ?? "error",
    kerning: kerning ?? true,
    metric_rounding: previewPolicy?.metric_rounding ?? "subpixel",
    wrap: "word",
    align: "left",
    foreground: colors.foreground,
    background: colors.background,
    ...(colors.palette !== undefined ? { palette: colors.palette } : {}),
    ...(!separated ? { renderer: role ?? "baseline" } : {}),
    ...(separated ? { pipeline: {
      fitting: previewPolicy !== null ? previewPolicy.fitting : "upstream_mono",
      rasterization: previewPolicy !== null ? previewPolicy.rasterization : "coverage",
      ...(previewPolicy?.diagonal_fitting ? { diagonal_fitting: true as const } : {}),
    } } : {}),
    ...(!separated && role === "candidate" && profile === "mono_1bit" && stemFitting ? { stem_fitting: stemFitting } : {}),
    ...(scan !== undefined ? { mono_raster: scan } : {}),
  };
}
