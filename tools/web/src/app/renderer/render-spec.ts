// Exact WASM render-request shape (tools/wasm RenderSpec, deny_unknown_fields).
// Same mapping the legacy preview used: whole-pixel tracking for the
// candidate renderer, fractional Gray tracking otherwise, and the automatic
// Mono engine policy for candidate 1-bit unless upstream Mono is forced.
import type {
  OutputProfile,
  RendererRole,
  RenderSpec,
  RGBA,
  StemFitting,
} from "./renderer-types.js";

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
  letterSpacingPx?: number | string;
  kerning?: boolean;
  stemFitting?: StemFitting;
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
  const integer = role === "candidate" || profile !== "gray_3bit";
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
  const levels = 1 << (profile === "gray_3bit" ? 3 : 1);
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

export function toRenderSpec({
  text, sizePx, axes, profile, width, height, role,
  letterSpacingPx, kerning, stemFitting, monoThreshold, grayGamma,
  palette,
}: RenderRequestOptions): RenderSpec {
  const colors = resolveRenderColors(palette, profile);
  return {
    text,
    width: Math.min(4096, Math.max(1, Math.ceil(width))),
    height: Math.min(4096, Math.max(1, Math.ceil(height))),
    size_px: sizePx,
    axes: { ...axes },
    letter_spacing_px: normalizedSpacing(letterSpacingPx, profile, role),
    hinting: role === "candidate" && profile === "mono_1bit" && stemFitting !== "upstream_mono"
      ? "auto_fallback" : "auto",
    output_bits: profile === "gray_3bit" ? 3 : 1,
    mono_threshold: monoThreshold ?? 128,
    gray_gamma: grayGamma ?? 1.0,
    missing_glyphs: "error",
    kerning: kerning ?? true,
    metric_rounding: "subpixel",
    wrap: "word",
    align: "left",
    foreground: colors.foreground,
    background: colors.background,
    ...(colors.palette !== undefined ? { palette: colors.palette } : {}),
    renderer: role ?? "baseline",
    ...(role === "candidate" && profile === "mono_1bit" && stemFitting ? { stem_fitting: stemFitting } : {}),
  };
}
