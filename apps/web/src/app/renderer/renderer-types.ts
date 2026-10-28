// Typed boundary for the staged wasm-bindgen renderer (crates/wasm). The
// generated font_wasm.d.ts types render specs as `any`; this declaration
// gives the browser code the exact shape the Rust side serializes
// (crates/wasm/src/lib.rs RenderSpec). Only the surface the interactive
// renderer uses is declared. Type-only module: imports of it are erased at
// compile time.

import type { FontMetadata } from "../fonts/storage.js";
import type { RenderPixels } from "./client.js";

/** Scan conversion, independent of fitting and bitmap layout. */
export type Rasterization = "free_type_mono" | "coverage";

export interface RenderPipeline {
  fitting: StemFitting | "source_relative" | "font_hints_auto";
  rasterization: Rasterization | "free_type_mono_terminals";
  // Opt-in native diagonal-width fitting; absent unless mono 1-bit opted in.
  diagonal_fitting?: boolean;
}

/** Historical bundled pipeline identity; new requests select explicit stages. */
export type RendererRole = "baseline" | "reference" | "candidate";

/** Candidate 1-bit stem-fitting strategies (`stem_fitting`). */
export type StemFitting = "font_hints_first" | "upstream_mono";

/** Manual monochrome dropout correction (`mono_raster.dropout`). */
export type MonoDropout = "off" | "simple" | "smart";

/** Manual monochrome scan-converter settings (`mono_raster`). */
export interface MonoRaster {
  dropout: MonoDropout;
  includeStubs: boolean;
  fontInstructions: boolean;
}

/** Published output profiles distinguished by the interactive controls. */
export type OutputProfile = "mono_1bit" | "gray_2bit" | "gray_3bit" | "gray_4bit";

/**
 * RGBA color with byte channels 0..255. Readonly inputs are accepted;
 * request mapping always clones into fresh mutable tuples.
 */
export type RGBA = readonly [number, number, number, number];

/**
 * Exact request object for Font.render. The Rust side rejects unknown
 * fields, so this is the complete accepted shape; only `text`, `width`
 * and `height` lack serde defaults and must always be sent.
 */
export interface RenderSpec {
  text: string;
  width: number;
  height: number;
  size_px: number;
  axes: Record<string, number>;
  hinting: "none" | "auto" | "interpreter" | "auto_fallback";
  output_bits: number;
  mono_threshold: number;
  gray_gamma: number;
  missing_glyphs: "error" | "skip";
  kerning: boolean;
  metric_rounding: "subpixel" | "pixel";
  wrap: "clip" | "word" | "char";
  align: "left" | "center" | "right";
  foreground: [number, number, number, number];
  background: [number, number, number, number];
  palette?: [number, number, number, number][];
  renderer?: RendererRole;
  letter_spacing_px: number;
  pipeline?: RenderPipeline;
  stem_fitting?: StemFitting;
  mono_raster?: { dropout: MonoDropout; include_stubs: boolean; font_instructions: boolean };
}

export interface PlaydateExportRequest {
  config: Pick<RenderSpec, "size_px" | "axes" | "hinting" | "output_bits" | "mono_threshold" |
    "gray_gamma" | "missing_glyphs" | "kerning" | "metric_rounding" | "mono_raster"> & { characters: string };
  pipeline: RenderPipeline;
  letter_spacing_px: number;
}

/** Narrow replaceable renderer surface. The worker runtime satisfies it
 * structurally; deterministic fakes implement it in tests and stories. It
 * lives in this type-only module (not the .tsx provider) so plain .ts
 * surfaces such as the fixture and the worker runtime can import it. */
export interface RendererService {
  ping(): Promise<{ available: boolean }>;
  inspect(bytes: ArrayBuffer): Promise<FontMetadata>;
  load(fontId: string, bytes: ArrayBuffer): Promise<void>;
  unload(fontId: string): Promise<void>;
  kerning(fontId: string, sizePx: number, axes: Record<string, number>): Promise<unknown>;
  exportPlaydate(fontId: string, request: PlaydateExportRequest): Promise<ArrayBuffer>;
  nextToken(): number;
  render(fontId: string, token: number, spec: RenderSpec): Promise<{
    token: number;
    dropped: boolean;
    pixels: RenderPixels;
  }>;
  terminate(): void;
}
