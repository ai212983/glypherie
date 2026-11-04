// Supported character-coverage presets.
//
// Adapted from CrossGlyph INTERVAL_PRESETS
// (src/crossglyph/cpfont/convert.py, pinned 7c106a5) and
// docs/fonts.md#character-coverage. Only the generator-supported repertoire
// (Latin, Greek, Cyrillic, common symbols; crates/generator/API.md) is
// catalogued: combining marks and complex scripts are excluded because the
// generator reports them as unsupported shaping, and C0/C1 controls are
// excluded because export rejects controls. Ranges that a preset needs are
// listed explicitly in that preset; nothing is auto-included elsewhere.
// Coverage selects stored scalars only and never implies text shaping.

import type { CodepointRange } from "./coverage.ts";

export type CoveragePresetId = "ascii" | "latin" | "greek" | "cyrillic" | "symbols" | "reading";

export interface CoveragePreset {
  readonly id: CoveragePresetId;
  readonly label: string;
  readonly summary: string;
  readonly ranges: readonly CodepointRange[];
}

const ASCII_RANGES: readonly CodepointRange[] = [{ start: 0x20, end: 0x7e }];

// Printable Latin-1 supplement plus Latin Extended-A/B, Latin Extended
// Additional and Latin ligatures; slices of CrossGlyph latin-ext/default.
const LATIN_RANGES: readonly CodepointRange[] = [
  { start: 0xa0, end: 0xff },
  { start: 0x100, end: 0x24f },
  { start: 0x1e00, end: 0x1eff },
  { start: 0xfb00, end: 0xfb06 },
];

// CrossGlyph greek preset verbatim.
const GREEK_RANGES: readonly CodepointRange[] = [
  { start: 0x370, end: 0x3ff },
  { start: 0x1f00, end: 0x1fff },
];

// CrossGlyph cyrillic preset verbatim.
const CYRILLIC_RANGES: readonly CodepointRange[] = [
  { start: 0x400, end: 0x4ff },
  { start: 0x500, end: 0x52f },
];

// General punctuation (CrossGlyph base) plus the CrossGlyph symbols preset.
const SYMBOL_RANGES: readonly CodepointRange[] = [
  { start: 0x2000, end: 0x206f },
  { start: 0x2070, end: 0x209f },
  { start: 0x20a0, end: 0x20cf },
  { start: 0x2150, end: 0x218f },
  { start: 0x2190, end: 0x21ff },
  { start: 0x2200, end: 0x22ff },
  { start: 0x2500, end: 0x257f },
  { start: 0x25a0, end: 0x25ff },
  { start: 0x2600, end: 0x26ff },
  { start: 0x2700, end: 0x27bf },
];

export const COVERAGE_PRESET_IDS: readonly CoveragePresetId[] = [
  "ascii",
  "latin",
  "greek",
  "cyrillic",
  "symbols",
  "reading",
];

export const COVERAGE_PRESETS: Readonly<Record<CoveragePresetId, CoveragePreset>> = {
  ascii: {
    id: "ascii",
    label: "ASCII printable",
    summary: "Printable ASCII (U+0020-U+007E). Matches the current export default.",
    ranges: ASCII_RANGES,
  },
  latin: {
    id: "latin",
    label: "Latin",
    summary: "Printable Latin-1 supplement, Latin Extended blocks and Latin ligatures, as isolated glyphs.",
    ranges: LATIN_RANGES,
  },
  greek: {
    id: "greek",
    label: "Greek",
    summary: "Greek and Coptic plus Greek Extended, as isolated glyphs.",
    ranges: GREEK_RANGES,
  },
  cyrillic: {
    id: "cyrillic",
    label: "Cyrillic",
    summary: "Cyrillic and Cyrillic Supplement, as isolated glyphs.",
    ranges: CYRILLIC_RANGES,
  },
  symbols: {
    id: "symbols",
    label: "Symbols",
    summary: "General punctuation, currency, arrows, math operators and geometric/dingbat symbols.",
    ranges: SYMBOL_RANGES,
  },
  reading: {
    id: "reading",
    label: "Reading",
    summary: "Composite of the Latin, Greek, Cyrillic and symbol presets for continuous reading text.",
    ranges: [...ASCII_RANGES, ...LATIN_RANGES, ...GREEK_RANGES, ...CYRILLIC_RANGES, ...SYMBOL_RANGES],
  },
};
