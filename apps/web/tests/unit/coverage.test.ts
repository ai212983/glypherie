import assert from "node:assert/strict";
import test from "node:test";
import {
  COVERAGE_PRESET_IDS,
  COVERAGE_PRESETS,
  DEFAULT_CHARACTER_COVERAGE,
  coverageCount,
  expandRanges,
  formatCustomRange,
  normalizeCoverage,
  normalizeRanges,
  parseCustomRange,
  resolveCoverage,
  splitCoverageByAvailability,
} from "../../src/app/domain/coverage.ts";
import { PLAYDATE_ASCII } from "../../src/app/features/preview/playdate-export.ts";

test("normalizeRanges sorts and joins overlapping/adjacent runs, keeping singletons", () => {
  assert.deepEqual(
    normalizeRanges([
      { start: 0x30, end: 0x39 },
      { start: 0x41, end: 0x41 },
      { start: 0x35, end: 0x43 },
      { start: 0x44, end: 0x46 },
    ]),
    [{ start: 0x30, end: 0x46 }],
  );
  assert.deepEqual(normalizeRanges([]), []);
  assert.deepEqual(normalizeRanges([{ start: 5, end: 5 }]), [{ start: 5, end: 5 }]);
});

test("resolveCoverage is additive over presets and custom ranges", () => {
  const resolved = resolveCoverage({
    presetIds: ["greek"],
    extraRanges: [{ start: 0x3a0, end: 0x3a0 }, { start: 0x400, end: 0x401 }],
  });
  // 0x400 is adjacent to the Greek block end 0x3FF, so it merges; the 0x3A0
  // singleton is already contained.
  assert.deepEqual(resolved, [
    { start: 0x370, end: 0x401 },
    { start: 0x1f00, end: 0x1fff },
  ]);
});

test("empty coverage resolves to nothing: no hidden base or replacement character", () => {
  assert.deepEqual(resolveCoverage({ presetIds: [], extraRanges: [] }), []);
});

test("unknown preset IDs throw with the available catalog", () => {
  assert.throws(
    () => resolveCoverage({ presetIds: ["nope" as never], extraRanges: [] }),
    /Unknown coverage preset 'nope'. Available: /,
  );
  assert.throws(() => normalizeCoverage({ presetIds: ["cjk-sc" as never], extraRanges: [] }), /Unknown coverage preset/);
});

test("invalid scalar intervals throw", () => {
  for (const range of [
    { start: 10, end: 9 },
    { start: -1, end: 5 },
    { start: 0, end: 0x110000 },
    { start: 1.5, end: 5 },
    { start: Number.NaN, end: 5 },
    { start: 0, end: Number.POSITIVE_INFINITY },
    { start: 0xd800, end: 0xd800 },
    { start: 0xdfff, end: 0xe000 },
    { start: 0x41, end: 0xe000 },
  ]) {
    assert.throws(() => normalizeRanges([range]), /[Cc]overage|range|scalar|surrogate/i, JSON.stringify(range));
  }
});

test("default coverage matches the current export default of printable ASCII", () => {
  assert.deepEqual(DEFAULT_CHARACTER_COVERAGE, { presetIds: ["ascii"], extraRanges: [] });
  const resolved = resolveCoverage(DEFAULT_CHARACTER_COVERAGE);
  assert.deepEqual(resolved, [{ start: 0x20, end: 0x7e }]);
  assert.equal(coverageCount(resolved), 95);
  assert.deepEqual(expandRanges(resolved, 1024), [...PLAYDATE_ASCII].map((ch) => ch.codePointAt(0)!));
});

test("reading preset is the union of the regional and symbol presets", () => {
  const union = resolveCoverage({
    presetIds: ["ascii", "latin", "greek", "cyrillic", "symbols"],
    extraRanges: [],
  });
  assert.deepEqual(resolveCoverage({ presetIds: ["reading"], extraRanges: [] }), union);
});

test("normalizeCoverage preserves chosen preset IDs in deterministic catalog order", () => {
  const normalized = normalizeCoverage({
    presetIds: ["symbols", "ascii", "symbols", "greek"],
    extraRanges: [
      { start: 0x42, end: 0x44 },
      { start: 0x40, end: 0x41 },
    ],
  });
  assert.deepEqual(normalized.presetIds, ["ascii", "greek", "symbols"]);
  assert.deepEqual(normalized.extraRanges, [{ start: 0x40, end: 0x44 }]);
  assert.ok(COVERAGE_PRESET_IDS.every((id) => Object.hasOwn(COVERAGE_PRESETS, id)));
});

test("coverageCount preflights huge inputs without expanding them", () => {
  const all = [
    { start: 0, end: 0xd7ff },
    { start: 0xe000, end: 0x10ffff },
  ];
  assert.equal(coverageCount(all), 0x10ffff + 1 - 2048);
  assert.throws(() => expandRanges(all, 1024), /above the expansion limit/);
});

test("expandRanges is explicitly bounded and ascending", () => {
  assert.deepEqual(expandRanges([{ start: 0x43, end: 0x43 }, { start: 0x41, end: 0x42 }], 4), [0x41, 0x42, 0x43]);
  assert.deepEqual(expandRanges([{ start: 0x41, end: 0x42 }], 2), [0x41, 0x42]);
  assert.deepEqual(expandRanges([], 0), []);
  assert.throws(() => expandRanges([{ start: 0x41, end: 0x42 }], 1), /expansion limit/);
  assert.throws(() => expandRanges([{ start: 0x41, end: 0x41 }], -1), /nonnegative integer/);
});

test("splitCoverageByAvailability reports missing coverage instead of dropping it", () => {
  const requested = resolveCoverage({ presetIds: ["ascii", "greek"], extraRanges: [] });
  const asciiOnly = resolveCoverage({ presetIds: ["ascii"], extraRanges: [] });
  const split = splitCoverageByAvailability(requested, asciiOnly);
  assert.deepEqual(split.covered, asciiOnly);
  assert.deepEqual(split.missing, [
    { start: 0x370, end: 0x3ff },
    { start: 0x1f00, end: 0x1fff },
  ]);
  const partial = splitCoverageByAvailability(
    [{ start: 0x20, end: 0x30 }],
    [{ start: 0x25, end: 0x27 }],
  );
  assert.deepEqual(partial.covered, [{ start: 0x25, end: 0x27 }]);
  assert.deepEqual(partial.missing, [
    { start: 0x20, end: 0x24 },
    { start: 0x28, end: 0x30 },
  ]);
});

test("splitCoverageByAvailability keeps a singleton/singleton intersection", () => {
  const split = splitCoverageByAvailability(
    [{ start: 0x41, end: 0x41 }],
    [{ start: 0x41, end: 0x41 }],
  );
  assert.deepEqual(split.covered, [{ start: 0x41, end: 0x41 }]);
  assert.deepEqual(split.missing, []);
});

test("splitCoverageByAvailability keeps an endpoint-only intersection", () => {
  const split = splitCoverageByAvailability(
    [{ start: 0x20, end: 0x30 }],
    [{ start: 0x30, end: 0x35 }],
  );
  assert.deepEqual(split.covered, [{ start: 0x30, end: 0x30 }]);
  assert.deepEqual(split.missing, [{ start: 0x20, end: 0x2f }]);
});

test("custom range strings round-trip through the parse/format adapters", () => {
  assert.deepEqual(parseCustomRange("(0x2500-0x257F)"), { start: 0x2500, end: 0x257f });
  assert.equal(formatCustomRange({ start: 0x2500, end: 0x257f }), "(0x2500-0x257F)");
  assert.deepEqual(parseCustomRange(formatCustomRange({ start: 0x41, end: 0x41 })), { start: 0x41, end: 0x41 });
  for (const text of ["latin", "(0x30-0x20)", "(0xD800-0xDFFF)", "(41-42)", ""]) {
    assert.throws(() => parseCustomRange(text), /[Ii]nvalid/, text || "(empty)");
  }
});
