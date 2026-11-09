// Structured character coverage: numeric intervals are canonical, named
// presets resolve via the data catalog, custom UI range strings stay in
// parse/format adapters. Adapted from CrossGlyph resolve_intervals and
// merge_intervals (src/crossglyph/cpfont/convert.py, pinned 7c106a5).
// Departures: no hidden base-preset or U+FFFD auto-include, no truncation;
// resolveCoverage reports the full requested set and limit checks belong to
// the exporter boundary. This module never encodes the native 1024-scalar
// export subset limit. Serialization to the WASM characters string belongs to
// the export/renderer adapter, outside this canonical data.

import { COVERAGE_PRESETS, COVERAGE_PRESET_IDS } from "./coverage-presets.ts";
import type { CoveragePresetId } from "./coverage-presets.ts";

export type { CoveragePresetId } from "./coverage-presets.ts";
export { COVERAGE_PRESETS, COVERAGE_PRESET_IDS } from "./coverage-presets.ts";

// Largest valid Unicode scalar value.
export const MAX_CODEPOINT = 0x10ffff;

const SURROGATE_START = 0xd800;
const SURROGATE_END = 0xdfff;

// Closed inclusive integer Unicode scalar interval.
export interface CodepointRange {
  readonly start: number;
  readonly end: number;
}

// Requested coverage: named presets plus custom extra intervals, additive.
export interface CharacterCoverage {
  readonly presetIds: readonly CoveragePresetId[];
  readonly extraRanges: readonly CodepointRange[];
}

export class CoverageError extends Error {}

// ASCII equivalent of the current export default (PLAYDATE_ASCII, U+0020-U+007E).
export const DEFAULT_CHARACTER_COVERAGE: CharacterCoverage = {
  presetIds: ["ascii"],
  extraRanges: [],
};

function checkRange(range: CodepointRange): void {
  const { start, end } = range;
  if (!Number.isInteger(start) || !Number.isInteger(end) || !Number.isFinite(start) || !Number.isFinite(end)) {
    throw new CoverageError(`Coverage range bounds must be finite integers, got [${start}, ${end}].`);
  }
  if (start < 0 || end > MAX_CODEPOINT || start > end) {
    throw new CoverageError(`Invalid codepoint range [${start}, ${end}]; expected 0 <= start <= end <= 0x10FFFF.`);
  }
  if (start <= SURROGATE_END && end >= SURROGATE_START) {
    throw new CoverageError(`Invalid codepoint range [${start}, ${end}]; surrogates are not valid output codepoints.`);
  }
}

// Sorted ascending with overlapping/adjacent runs joined; singletons are
// equal endpoints. Throws CoverageError on invalid scalar intervals.
export function normalizeRanges(ranges: readonly CodepointRange[]): CodepointRange[] {
  const sorted = ranges.map((range) => {
    checkRange(range);
    return { start: range.start, end: range.end };
  });
  sorted.sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: { start: number; end: number }[] = [];
  for (const range of sorted) {
    const last = merged[merged.length - 1];
    if (last !== undefined && range.start <= last.end + 1) {
      last.end = Math.max(last.end, range.end);
    } else {
      merged.push({ ...range });
    }
  }
  return merged;
}

function checkPresetId(id: string): asserts id is CoveragePresetId {
  if (!Object.hasOwn(COVERAGE_PRESETS, id)) {
    throw new CoverageError(`Unknown coverage preset '${id}'. Available: ${COVERAGE_PRESET_IDS.join(", ")}.`);
  }
}

// Deduplicated preset IDs in catalog order with normalized extras; the
// chosen preset IDs are preserved, unknown IDs throw.
export function normalizeCoverage(coverage: CharacterCoverage): CharacterCoverage {
  const seen = new Set<string>();
  for (const id of coverage.presetIds) {
    checkPresetId(id);
    seen.add(id);
  }
  return {
    presetIds: COVERAGE_PRESET_IDS.filter((id) => seen.has(id)),
    extraRanges: normalizeRanges(coverage.extraRanges),
  };
}

// Full requested coverage, independently of font-available ranges; missing
// glyphs stay visible via splitCoverageByAvailability instead of dropping.
export function resolveCoverage(coverage: CharacterCoverage): CodepointRange[] {
  const normalized = normalizeCoverage(coverage);
  const all: CodepointRange[] = [];
  for (const id of normalized.presetIds) {
    all.push(...COVERAGE_PRESETS[id].ranges);
  }
  all.push(...normalized.extraRanges);
  return normalizeRanges(all);
}

// Scalar count of the union without expanding it; use for preflight before
// any bounded expansion or exporter limit check.
export function coverageCount(ranges: readonly CodepointRange[]): number {
  let count = 0;
  for (const range of normalizeRanges(ranges)) {
    count += range.end - range.start + 1;
  }
  return count;
}

// Ascending scalar list; throws when the union exceeds limit so huge inputs
// can never expand eagerly. The limit belongs to the caller (exporter/UI).
export function expandRanges(ranges: readonly CodepointRange[], limit: number): number[] {
  if (!Number.isInteger(limit) || limit < 0) {
    throw new CoverageError(`Expansion limit must be a nonnegative integer, got ${limit}.`);
  }
  const normalized = normalizeRanges(ranges);
  const count = coverageCount(normalized);
  if (count > limit) {
    throw new CoverageError(`Coverage holds ${count} scalars, above the expansion limit of ${limit}.`);
  }
  const out: number[] = [];
  for (const range of normalized) {
    for (let cp = range.start; cp <= range.end; cp += 1) {
      out.push(cp);
    }
  }
  return out;
}

export interface CoverageSplit {
  readonly covered: CodepointRange[];
  readonly missing: CodepointRange[];
}

// Partition normalized requested ranges against normalized font-available
// ranges (renderer metadata); both sides stay reportable, nothing is dropped.
export function splitCoverageByAvailability(
  requested: readonly CodepointRange[],
  available: readonly CodepointRange[],
): CoverageSplit {
  const want = normalizeRanges(requested);
  const have = normalizeRanges(available);
  const covered: CodepointRange[] = [];
  for (const a of want) {
    for (const b of have) {
      const start = Math.max(a.start, b.start);
      const end = Math.min(a.end, b.end);
      if (start <= end) covered.push({ start, end });
    }
  }
  let missing: CodepointRange[] = [...want];
  for (const b of have) {
    const rest: CodepointRange[] = [];
    for (const m of missing) {
      if (b.end < m.start || b.start > m.end) {
        rest.push(m);
        continue;
      }
      if (m.start < b.start) rest.push({ start: m.start, end: b.start - 1 });
      if (m.end > b.end) rest.push({ start: b.end + 1, end: m.end });
    }
    missing = rest;
  }
  return { covered: normalizeRanges(covered), missing };
}

const CUSTOM_RANGE_PATTERN = /^\(0x([0-9a-fA-F]+)-0x([0-9a-fA-F]+)\)$/;

function hex(codepoint: number): string {
  return `0x${codepoint.toString(16).toUpperCase().padStart(4, "0")}`;
}

// Parse a custom UI range string such as "(0x2500-0x257F)".
export function parseCustomRange(text: string): CodepointRange {
  const match = CUSTOM_RANGE_PATTERN.exec(text.trim());
  if (match?.[1] === undefined || match[2] === undefined) {
    throw new CoverageError(`Invalid custom range '${text}'; expected format (0xSTART-0xEND).`);
  }
  const range = { start: parseInt(match[1], 16), end: parseInt(match[2], 16) };
  checkRange(range);
  return range;
}

// Format for parseCustomRange round-trips.
export function formatCustomRange(range: CodepointRange): string {
  checkRange(range);
  return `(${hex(range.start)}-${hex(range.end)})`;
}
