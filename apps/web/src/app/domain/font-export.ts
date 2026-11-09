// Structured-coverage bitmap-font ZIP export shared by the Scene page and
// the standalone exporter. Scene UI never touches this module's internals:
// it passes { textStyleIds, outputProfileId, coverage, format } plus
// injected services. Text styles resolve through the injected domain seam,
// fonts load through the existing font repository/renderer service, and
// bytes come from the existing native Playdate exporter. Numeric intervals
// stay canonical until coverageToCharacters, the only adapter that renders
// the WASM `characters` string for the current Playdate API.
import { zipSync } from "fflate";
import {
  CoverageError,
  coverageCount,
  expandRanges,
  normalizeRanges,
  resolveCoverage,
  splitCoverageByAvailability,
  type CharacterCoverage,
  type CodepointRange,
} from "./coverage.ts";
import { toRenderSpec } from "../renderer/render-spec.ts";
import type { PlaydateExportRequest } from "../renderer/renderer-types.ts";
import type { VariantSettings } from "../variants/model.ts";

// Native Playdate export subset: 1-1024 distinct scalars within
// U+0020-U+3FFFF, excluding controls and unsupported shaping
// (crates/generator/API.md). The cap stays native; this module never raises
// it and never claims a generic gray format.
export const PLAYDATE_EXPORT_MAX_SCALARS = 1024;
export const PLAYDATE_EXPORT_MIN_CODEPOINT = 0x20;
export const PLAYDATE_EXPORT_MAX_CODEPOINT = 0x3ffff;
const CONTROL_RANGES: readonly CodepointRange[] = [
  { start: 0x00, end: 0x1f },
  { start: 0x7f, end: 0x9f },
];
// Export window with the surrogate span excluded so the range validator
// (shared with coverage.ts) accepts every window edge.
const EXPORT_WINDOW_RANGES: readonly CodepointRange[] = [
  { start: PLAYDATE_EXPORT_MIN_CODEPOINT, end: 0xd7ff },
  { start: 0xe000, end: PLAYDATE_EXPORT_MAX_CODEPOINT },
];

// Supported subset of requested ranges: inside the export window and
// outside the control ranges. Both exclusions are reported, never silently
// dropped into the generated set.
export function splitExportWindow(requested: readonly CodepointRange[]): {
  supported: CodepointRange[];
  unsupported: CodepointRange[];
} {
  const normalized = normalizeRanges(requested);
  const inWindow = splitCoverageByAvailability(normalized, EXPORT_WINDOW_RANGES);
  const againstControls = splitCoverageByAvailability(inWindow.covered, CONTROL_RANGES);
  return {
    supported: againstControls.missing,
    unsupported: normalizeRanges([...inWindow.missing, ...againstControls.covered]),
  };
}

// Final compatibility adapter for the current WASM API: structured coverage
// becomes the `characters` string here and nowhere else. Limit checks apply
// to the actual generated set; an empty set fails instead of exporting
// nothing.
export function coverageToCharacters(coverage: CharacterCoverage): string {
  const { supported, unsupported } = splitExportWindow(resolveCoverage(coverage));
  if (unsupported.length > 0) {
    throw new CoverageError(`Coverage holds ${coverageCount(unsupported)} scalars outside the Playdate export subset.`);
  }
  const scalars = expandRanges(supported, PLAYDATE_EXPORT_MAX_SCALARS);
  if (scalars.length === 0) {
    throw new CoverageError("Coverage holds no exportable characters for Playdate output.");
  }
  return String.fromCodePoint(...scalars);
}

// Same finalized pipeline, tracking, axes and kerning as the live preview
// (the toRenderSpec seam both entry points share). Grayscale fails here so
// the exporter never silently forces mono.
export function playdateRequestForSettings(
  settings: VariantSettings,
  coverage: CharacterCoverage,
): PlaydateExportRequest {
  if (settings.profile !== "mono_1bit") throw new Error("Select Monochrome output to export for Playdate.");
  const characters = coverageToCharacters(coverage);
  const spec = toRenderSpec({
    text: "",
    width: 1,
    height: 1,
    sizePx: settings.sizePx,
    axes: settings.axes,
    profile: settings.profile,
    rasterization: "free_type_mono",
    stemFitting: settings.stemFitting,
    diagonalFitting: settings.diagonalFitting,
    letterSpacingPx: settings.letterSpacingPx,
    kerning: settings.kerning,
  });
  const {
    size_px,
    axes,
    hinting,
    output_bits,
    mono_threshold,
    gray_gamma,
    missing_glyphs,
    kerning,
    metric_rounding,
    mono_raster,
  } = spec;
  return {
    config: {
      size_px,
      axes,
      hinting,
      output_bits,
      mono_threshold,
      gray_gamma,
      missing_glyphs,
      kerning,
      metric_rounding,
      mono_raster,
      characters,
    },
    pipeline: spec.pipeline!,
    letter_spacing_px: spec.letter_spacing_px,
    ...(spec.kerning_method ? { kerning_method: spec.kerning_method } : {}),
  };
}

// Portable download filename; the slug keeps letters, digits, _ and -.
export function playdateFileName(name: string, sizePx: number): string {
  const stem =
    name
      .replace(/[^\p{L}\p{N}_-]+/gu, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "font";
  return `${stem}-${sizePx}px.fnt`;
}

// Deterministic unique entry names for one archive: repeats gain a numeric
// suffix in input order, so equal style names and sizes never collide.
export function uniqueExportFileNames(names: readonly string[]): string[] {
  const used = new Set<string>();
  return names.map((name) => {
    if (!used.has(name)) {
      used.add(name);
      return name;
    }
    const dot = name.lastIndexOf(".");
    const stem = dot < 0 ? name : name.slice(0, dot);
    const extension = dot < 0 ? "" : name.slice(dot);
    let counter = 2;
    while (used.has(`${stem}-${counter}${extension}`)) counter += 1;
    const unique = `${stem}-${counter}${extension}`;
    used.add(unique);
    return unique;
  });
}

export interface FontExportStyleSnapshot {
  id: string;
  name: string;
  fontId: string;
  settings: VariantSettings;
}

export interface FontExportServices {
  // One graph read transaction for every requested style, so concurrent edits
  // cannot mix revisions across the batch.
  resolveTextStyles(textStyleIds: string[], outputProfileId: string): Promise<FontExportStyleSnapshot[]>;
  // Font metadata coverage for availability splits; null when unknown, in
  // which case the full requested set goes to the native exporter.
  fontCoverage(fontId: string): Promise<readonly CodepointRange[] | null>;
  ensureFontReady(fontId: string): Promise<void>;
  exportPlaydate(fontId: string, request: PlaydateExportRequest): Promise<ArrayBuffer>;
}

export interface FontExportInput {
  textStyleIds: string[];
  outputProfileId: string;
  coverage: CharacterCoverage;
  format: "playdate";
  // Direct-font labels resolved by the caller (the domain has no saved style
  // for them); appended after the resolved styles in the same archive.
  extraSnapshots?: FontExportStyleSnapshot[];
}

export interface FontExportMissing {
  textStyleId: string;
  name: string;
  ranges: CodepointRange[];
}

export interface FontExportFailure {
  textStyleId: string;
  name: string;
  message: string;
}

export interface FontExportResult {
  bytes: Uint8Array;
  fileName: string;
  files: string[];
  missing: FontExportMissing[];
}

export class FontExportError extends Error {
  readonly failures: FontExportFailure[];
  constructor(failures: FontExportFailure[]) {
    super(failures.map((failure) => `"${failure.name}": ${failure.message}`).join(" "));
    this.name = "FontExportError";
    this.failures = failures;
  }
}

export interface FontExportProgress {
  done: number;
  total: number;
  name: string;
}

// Scene export packages bitmap fonts for ALL text styles, never only the
// styles placed labels reference. Snapshots resolve first; generation runs
// after, outside any database transaction. A style failure names the style
// and aborts the archive: no partial-success ZIP downloads silently.
export async function exportTextStylesToZip(
  input: FontExportInput,
  services: FontExportServices,
  onProgress?: (progress: FontExportProgress) => void,
): Promise<FontExportResult> {
  if (input.format !== "playdate") throw new Error(`Unsupported font export format '${input.format}'.`);
  const extras = input.extraSnapshots ?? [];
  if (input.textStyleIds.length === 0 && extras.length === 0) {
    throw new Error("Font export needs at least one text style.");
  }
  const requested = resolveCoverage(input.coverage);
  const snapshots = [...(await services.resolveTextStyles(input.textStyleIds, input.outputProfileId)), ...extras];
  const entries: { name: string; bytes: Uint8Array }[] = [];
  const missing: FontExportMissing[] = [];
  const failures: FontExportFailure[] = [];
  for (const [index, snapshot] of snapshots.entries()) {
    onProgress?.({ done: index, total: snapshots.length, name: snapshot.name });
    try {
      await services.ensureFontReady(snapshot.fontId);
      const available = await services.fontCoverage(snapshot.fontId);
      let covered = requested;
      if (available !== null) {
        const split = splitCoverageByAvailability(requested, available);
        covered = split.covered;
        if (split.missing.length > 0) {
          missing.push({ textStyleId: snapshot.id, name: snapshot.name, ranges: split.missing });
        }
      }
      const window = splitExportWindow(covered);
      if (window.unsupported.length > 0) {
        throw new Error(`holds ${coverageCount(window.unsupported)} characters outside the Playdate export subset.`);
      }
      const scalars = expandRanges(window.supported, PLAYDATE_EXPORT_MAX_SCALARS);
      if (scalars.length === 0) {
        throw new Error("covers no exportable characters for Playdate output.");
      }
      const request = playdateRequestForSettings(snapshot.settings, { presetIds: [], extraRanges: window.supported });
      const buffer = await services.exportPlaydate(snapshot.fontId, request);
      entries.push({
        name: playdateFileName(snapshot.name, snapshot.settings.sizePx),
        bytes: new Uint8Array(buffer),
      });
    } catch (error) {
      failures.push({
        textStyleId: snapshot.id,
        name: snapshot.name,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }
  onProgress?.({ done: snapshots.length, total: snapshots.length, name: "" });
  if (failures.length > 0) throw new FontExportError(failures);
  const files = uniqueExportFileNames(entries.map((entry) => entry.name));
  const archive: Record<string, Uint8Array> = {};
  entries.forEach((entry, index) => {
    archive[files[index]!] = entry.bytes;
  });
  return { bytes: zipSync(archive), fileName: "fonts-playdate.zip", files, missing };
}
