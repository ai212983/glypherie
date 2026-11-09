// Scene/ZIP export with injected fakes: the native renderer and domain are
// never touched. Verifies complete archives, unique filenames, structured
// coverage handling and style-identified failures without partial downloads.
import assert from "node:assert/strict";
import test from "node:test";
import { unzipSync } from "fflate";
import {
  coverageToCharacters,
  exportTextStylesToZip,
  FontExportError,
  uniqueExportFileNames,
  type FontExportServices,
  type FontExportStyleSnapshot,
} from "../../src/app/domain/font-export.ts";
import { DEFAULT_CHARACTER_COVERAGE } from "../../src/app/domain/coverage.ts";
import type { PlaydateExportRequest } from "../../src/app/renderer/renderer-types.ts";
import type { VariantSettings } from "../../src/app/variants/model.ts";

function settings(profile: VariantSettings["profile"] = "mono_1bit", sizePx = 16): VariantSettings {
  return {
    sizePx,
    axes: {},
    letterSpacingPx: 0,
    profile,
    renderer: "candidate",
    stemFitting: "font_hints_first",
    diagonalFitting: false,
    kerning: true,
    monoRaster: { dropout: "smart", includeStubs: false, fontInstructions: false },
  };
}

interface FakeStyle extends FontExportStyleSnapshot {
  available: { start: number; end: number }[] | null;
}

function fakeServices(
  styles: FakeStyle[],
  hooks: {
    failExport?: (fontId: string) => Error | null;
  } = {},
): {
  services: FontExportServices;
  requests: { fontId: string; request: PlaydateExportRequest }[];
  batches: string[][];
} {
  const requests: { fontId: string; request: PlaydateExportRequest }[] = [];
  const batches: string[][] = [];
  const byId = new Map(styles.map((style) => [style.id, style]));
  return {
    requests,
    batches,
    services: {
      resolveTextStyles: async (textStyleIds) => {
        batches.push([...textStyleIds]);
        return textStyleIds.map((textStyleId) => {
          const style = byId.get(textStyleId);
          if (!style) throw new Error(`Unknown text style ${textStyleId}.`);
          return { id: style.id, name: style.name, fontId: style.fontId, settings: style.settings };
        });
      },
      fontCoverage: async (fontId) => styles.find((style) => style.fontId === fontId)?.available ?? null,
      ensureFontReady: async () => {},
      exportPlaydate: async (fontId, request) => {
        requests.push({ fontId, request });
        const failure = hooks.failExport?.(fontId);
        if (failure) throw failure;
        return new TextEncoder().encode(`fnt:${fontId}:${request.config.characters.length}`).buffer;
      },
    },
  };
}

test("coverage adapter renders the ASCII default as one ordered string", () => {
  assert.equal(coverageToCharacters(DEFAULT_CHARACTER_COVERAGE).length, 95);
  assert.equal(coverageToCharacters(DEFAULT_CHARACTER_COVERAGE).codePointAt(0), 0x20);
  assert.equal(
    coverageToCharacters({
      presetIds: [],
      extraRanges: [
        { start: 0x7e, end: 0x7e },
        { start: 0x20, end: 0x20 },
      ],
    }),
    " ~",
  );
});

test("coverage adapter rejects controls and oversized sets without silent truncation", () => {
  assert.throws(
    () => coverageToCharacters({ presetIds: [], extraRanges: [{ start: 0x0a, end: 0x0a }] }),
    /no exportable characters|outside the Playdate/,
  );
  assert.throws(
    () =>
      coverageToCharacters({
        presetIds: [],
        extraRanges: [
          { start: 0x20, end: 0x7e },
          { start: 0xa0, end: 0x5ff },
        ],
      }),
    /above the expansion limit|exceeds/,
  );
  assert.throws(
    () => coverageToCharacters({ presetIds: ["reading"], extraRanges: [] }),
    /above the expansion limit|exceeds/,
  );
});

test("export zips every style with shared resolved request values and unique filenames", async () => {
  const styles: FakeStyle[] = [
    { id: "s1", name: "Body", fontId: "f1", settings: settings("mono_1bit", 16), available: null },
    { id: "s2", name: "Body", fontId: "f2", settings: settings("mono_1bit", 16), available: null },
    {
      id: "s3",
      name: "Head",
      fontId: "f1",
      settings: { ...settings("mono_1bit", 24), letterSpacingPx: 1 },
      available: null,
    },
  ];
  const { services, requests, batches } = fakeServices(styles);
  const result = await exportTextStylesToZip(
    {
      textStyleIds: ["s1", "s2", "s3"],
      outputProfileId: "mono",
      coverage: DEFAULT_CHARACTER_COVERAGE,
      format: "playdate",
    },
    services,
  );
  assert.deepEqual(batches, [["s1", "s2", "s3"]]);
  assert.equal(result.fileName, "fonts-playdate.zip");
  assert.deepEqual(result.files, ["Body-16px.fnt", "Body-16px-2.fnt", "Head-24px.fnt"]);
  assert.deepEqual(result.missing, []);
  assert.equal(requests.length, 3);
  assert.equal(requests[0]?.request.config.characters.length, 95);
  assert.equal(requests[2]?.request.letter_spacing_px, 1);
  const archive = unzipSync(result.bytes);
  assert.deepEqual(Object.keys(archive).sort(), ["Body-16px-2.fnt", "Body-16px.fnt", "Head-24px.fnt"]);
  assert.equal(new TextDecoder().decode(archive["Body-16px.fnt"]), "fnt:f1:95");
});

test("missing font coverage is reported and only the covered set is generated", async () => {
  const styles: FakeStyle[] = [
    { id: "s1", name: "Body", fontId: "f1", settings: settings(), available: [{ start: 0x20, end: 0x7e }] },
  ];
  const { services, requests } = fakeServices(styles);
  const result = await exportTextStylesToZip(
    {
      textStyleIds: ["s1"],
      outputProfileId: "mono",
      coverage: { presetIds: ["ascii", "greek"], extraRanges: [] },
      format: "playdate",
    },
    services,
  );
  assert.equal(requests.length, 1);
  assert.equal(requests[0]?.request.config.characters.length, 95);
  assert.equal(result.missing.length, 1);
  assert.equal(result.missing[0]?.textStyleId, "s1");
  assert.deepEqual(result.missing[0]?.ranges, [
    { start: 0x370, end: 0x3ff },
    { start: 0x1f00, end: 0x1fff },
  ]);
});

test("grayscale styles fail by name and no archive downloads", async () => {
  const styles: FakeStyle[] = [
    { id: "s1", name: "Body", fontId: "f1", settings: settings(), available: null },
    { id: "s2", name: "Gray caption", fontId: "f1", settings: settings("gray_3bit"), available: null },
  ];
  const { services, requests } = fakeServices(styles);
  await assert.rejects(
    () =>
      exportTextStylesToZip(
        {
          textStyleIds: ["s1", "s2"],
          outputProfileId: "gray",
          coverage: DEFAULT_CHARACTER_COVERAGE,
          format: "playdate",
        },
        services,
      ),
    (error: unknown) => {
      assert.ok(error instanceof FontExportError);
      assert.equal(error.failures.length, 1);
      assert.equal(error.failures[0]?.textStyleId, "s2");
      assert.match(error.failures[0]?.message ?? "", /Monochrome/);
      assert.match(String(error), /Gray caption/);
      return true;
    },
  );
  assert.equal(requests.length, 1);
});

test("native export errors name the style and abort the archive", async () => {
  const styles: FakeStyle[] = [
    { id: "s1", name: "Body", fontId: "f1", settings: settings(), available: null },
    { id: "s2", name: "Broken", fontId: "f9", settings: settings(), available: null },
  ];
  const { services } = fakeServices(styles, {
    failExport: (fontId) => (fontId === "f9" ? new Error("U+0370 unsupported shaping") : null),
  });
  await assert.rejects(
    () =>
      exportTextStylesToZip(
        {
          textStyleIds: ["s1", "s2"],
          outputProfileId: "mono",
          coverage: DEFAULT_CHARACTER_COVERAGE,
          format: "playdate",
        },
        services,
      ),
    (error: unknown) => {
      assert.ok(error instanceof FontExportError);
      assert.equal(error.failures.length, 1);
      assert.match(String(error), /Broken/);
      assert.match(String(error), /U\+0370/);
      return true;
    },
  );
});

test("empty style lists and control-only coverage fail before any export", async () => {
  const { services, requests } = fakeServices([]);
  await assert.rejects(
    () =>
      exportTextStylesToZip(
        { textStyleIds: [], outputProfileId: "mono", coverage: DEFAULT_CHARACTER_COVERAGE, format: "playdate" },
        services,
      ),
    /at least one text style/,
  );
  assert.equal(requests.length, 0);
});

test("unique filenames stay deterministic across repeats", () => {
  assert.deepEqual(uniqueExportFileNames(["A-16px.fnt", "A-16px.fnt", "A-16px.fnt"]), [
    "A-16px.fnt",
    "A-16px-2.fnt",
    "A-16px-3.fnt",
  ]);
});

test("direct-font snapshots export alongside styles with shared filenames", async () => {
  const styles: FakeStyle[] = [
    { id: "s1", name: "Body", fontId: "f1", settings: settings("mono_1bit", 16), available: null },
  ];
  const { services, requests } = fakeServices(styles);
  const direct: FontExportStyleSnapshot = {
    id: "direct:f1:24",
    name: "Literata",
    fontId: "f1",
    settings: settings("mono_1bit", 24),
  };
  const result = await exportTextStylesToZip(
    {
      textStyleIds: ["s1"],
      outputProfileId: "mono",
      coverage: DEFAULT_CHARACTER_COVERAGE,
      format: "playdate",
      extraSnapshots: [direct],
    },
    services,
  );
  // The direct font reuses its own family name and size for the filename,
  // sharing the unique-name pool with the resolved styles.
  assert.deepEqual(result.files, ["Body-16px.fnt", "Literata-24px.fnt"]);
  assert.deepEqual(result.missing, []);
  assert.equal(requests.length, 2);
  assert.equal(requests[1]?.fontId, "f1");
  assert.equal(requests[1]?.request.config.size_px, 24);
  const archive = unzipSync(result.bytes);
  assert.deepEqual(Object.keys(archive).sort(), ["Body-16px.fnt", "Literata-24px.fnt"]);

  // A scene with only direct labels still exports; a scene with neither
  // still fails before any export.
  const only = await exportTextStylesToZip(
    {
      textStyleIds: [],
      outputProfileId: "mono",
      coverage: DEFAULT_CHARACTER_COVERAGE,
      format: "playdate",
      extraSnapshots: [direct],
    },
    services,
  );
  assert.deepEqual(only.files, ["Literata-24px.fnt"]);
  await assert.rejects(
    () =>
      exportTextStylesToZip(
        { textStyleIds: [], outputProfileId: "mono", coverage: DEFAULT_CHARACTER_COVERAGE, format: "playdate" },
        services,
      ),
    /at least one text style/,
  );
});
