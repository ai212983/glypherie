// Working-preview Mono settings shared with landing capture tooling.

export type PreviewFitting = "font_hints_auto" | "font_hints_first" | "source_relative" | "upstream_mono";
export type PreviewRasterization = "free_type_mono" | "free_type_mono_terminals";
export type PreviewDropout = "off" | "simple" | "smart";

export interface PreviewPolicyInput {
  fitting?: string;
  rasterization?: string;
  diagonalFitting?: boolean;
  dropout?: string;
  includeStubs?: boolean;
  fontInstructions?: boolean;
}

export interface ResolvedPreviewPolicy {
  fitting: PreviewFitting;
  rasterization: PreviewRasterization;
  diagonal_fitting: boolean;
  hinting: "auto" | "auto_fallback";
  output_bits: 1;
  mono_threshold: 128;
  gray_gamma: 1;
  missing_glyphs: "error";
  metric_rounding: "subpixel";
  mono_raster: {
    dropout: PreviewDropout;
    include_stubs: boolean;
    font_instructions: boolean;
  };
}

export const WORKING_PREVIEW_DEFAULTS = {
  fitting: "font_hints_auto",
  rasterization: "free_type_mono_terminals",
  diagonalFitting: true,
  dropout: "smart",
  includeStubs: true,
  fontInstructions: true,
} as const;

const FITTINGS: readonly string[] = ["font_hints_auto", "font_hints_first", "source_relative", "upstream_mono"];
const RASTERIZATIONS: readonly string[] = ["free_type_mono", "free_type_mono_terminals"];
const DROPOUTS: readonly string[] = ["off", "simple", "smart"];

function fail(why: string): never {
  throw new Error(why);
}

export function resolveWorkingPreviewPolicy(input: PreviewPolicyInput = {}): ResolvedPreviewPolicy {
  const fitting = input.fitting ?? WORKING_PREVIEW_DEFAULTS.fitting;
  if (!FITTINGS.includes(fitting)) fail(`Invalid Glypherie pipeline or scan settings: unknown fitting ${JSON.stringify(fitting)}.`);
  const rasterization = input.rasterization ?? WORKING_PREVIEW_DEFAULTS.rasterization;
  if (!RASTERIZATIONS.includes(rasterization)) {
    fail(`Invalid Glypherie pipeline or scan settings: unknown rasterization ${JSON.stringify(rasterization)}.`);
  }
  const diagonalFitting = input.diagonalFitting ?? WORKING_PREVIEW_DEFAULTS.diagonalFitting;
  if (typeof diagonalFitting !== "boolean") fail("Invalid Glypherie pipeline settings: diagonal_fitting must be a boolean.");
  if (diagonalFitting && fitting !== "font_hints_auto" && fitting !== "upstream_mono") {
    fail("Diagonal fitting requires font_hints_auto or upstream_mono; use --no-diagonal-fitting");
  }
  const dropout = input.dropout ?? WORKING_PREVIEW_DEFAULTS.dropout;
  if (!DROPOUTS.includes(dropout)) fail(`Invalid Glypherie pipeline or scan settings: unknown dropout ${JSON.stringify(dropout)}.`);
  const includeStubs = input.includeStubs ?? WORKING_PREVIEW_DEFAULTS.includeStubs;
  if (typeof includeStubs !== "boolean") fail("Invalid Glypherie scan settings: include_stubs must be a boolean.");
  const fontInstructions = input.fontInstructions ?? WORKING_PREVIEW_DEFAULTS.fontInstructions;
  if (typeof fontInstructions !== "boolean") {
    fail("Invalid Glypherie scan settings: font_instructions must be a boolean.");
  }
  return {
    fitting: fitting as PreviewFitting,
    rasterization: rasterization as PreviewRasterization,
    diagonal_fitting: diagonalFitting,
    hinting: fitting === "upstream_mono" ? "auto" : "auto_fallback",
    output_bits: 1,
    mono_threshold: 128,
    gray_gamma: 1,
    missing_glyphs: "error",
    metric_rounding: "subpixel",
    mono_raster: {
      dropout: dropout as PreviewDropout,
      include_stubs: includeStubs,
      font_instructions: fontInstructions,
    },
  };
}

// Fingerprints ignore object key order but preserve array order.
export function canonicalPreviewPolicyJson(value: unknown): string {
  return JSON.stringify(canonicalize(value));
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, entry]) => [key, canonicalize(entry)] as const);
    return Object.fromEntries(entries);
  }
  return value;
}
