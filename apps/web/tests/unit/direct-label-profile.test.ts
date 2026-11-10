// Direct-label render settings: profile mapping, wght axis handling, effective
// weight clamping, settings parity and export snapshot dedup/skips.
import assert from "node:assert/strict";
import test from "node:test";
import {
  directExportSnapshots,
  directLabelProfile,
  directLabelSettings,
  directWghtAxis,
  effectiveDirectWeight,
  type DirectExportPlacement,
} from "../../src/app/features/screen/direct-label.ts";
import { linearCurve } from "../../src/app/domain/output-profiles/curve.ts";
import { PREVIEW_MONO_RASTER } from "../../src/app/renderer/render-spec.ts";
import type { FontMetadata, StoredFont } from "../../src/app/fonts/storage.ts";

function wghtMetadata(min: number, def: number, max: number): FontMetadata {
  return {
    names: { family: "Fixture" },
    axes: [{ tag: "wght", name: "Weight", min, default: def, max, hidden: false }],
  };
}

function staticMetadata(): FontMetadata {
  return { names: { family: "Static" }, axes: [] };
}

function storedFont(meta: FontMetadata, id = "font-1"): StoredFont {
  return {
    id,
    name: "Fixture",
    fileName: "fixture.ttf",
    bytes: new ArrayBuffer(8),
    metadata: meta,
    source: "uploaded",
    addedAt: 1,
  };
}

const FULL = wghtMetadata(100, 400, 900);

test("curve length maps to the output profile with fallback to 3-bit gray", () => {
  assert.equal(directLabelProfile(linearCurve(2)), "mono_1bit");
  assert.equal(directLabelProfile(linearCurve(4)), "gray_2bit");
  assert.equal(directLabelProfile(linearCurve(16)), "gray_4bit");
  // Depths without a dedicated profile keep the established gray fallback.
  assert.equal(directLabelProfile(linearCurve(8)), "gray_3bit");
  assert.equal(directLabelProfile(linearCurve(3)), "gray_3bit");
});

test("wght axis resolves only for well-formed ordered bounds", () => {
  assert.deepEqual(directWghtAxis(storedFont(FULL)), { min: 100, default: 400, max: 900 });
  // Degenerate but ordered bounds still carry the axis.
  assert.deepEqual(directWghtAxis(storedFont(wghtMetadata(400, 400, 400))), {
    min: 400,
    default: 400,
    max: 400,
  });
  for (const font of [null, undefined]) {
    assert.equal(directWghtAxis(font), null);
  }
  const noMeta = storedFont(FULL);
  assert.equal(directWghtAxis({ ...noMeta, metadata: undefined as never }), null);
  assert.equal(directWghtAxis({ ...noMeta, metadata: { names: {} } as never }), null);
  assert.equal(directWghtAxis({ ...noMeta, metadata: { names: {}, axes: "wght" } as never }), null);
  assert.equal(directWghtAxis(storedFont(staticMetadata())), null);
  assert.equal(
    directWghtAxis(
      storedFont({
        names: { family: "X" },
        axes: [{ tag: "wdth", name: "W", min: 50, default: 100, max: 200, hidden: false }],
      }),
    ),
    null,
  );
  // Non-finite or unordered bounds never produce an axis.
  assert.equal(directWghtAxis(storedFont(wghtMetadata(Number.NaN, 400, 900))), null);
  assert.equal(directWghtAxis(storedFont(wghtMetadata(100, Number.POSITIVE_INFINITY, 900))), null);
  assert.equal(directWghtAxis(storedFont(wghtMetadata(100, 400, Number.NaN))), null);
  assert.equal(directWghtAxis(storedFont(wghtMetadata(500, 400, 900))), null);
  assert.equal(directWghtAxis(storedFont(wghtMetadata(100, 950, 900))), null);
  const withNull = storedFont(FULL);
  assert.deepEqual(
    directWghtAxis({
      ...withNull,
      metadata: { names: { family: "F" }, axes: [null, ...(withNull.metadata.axes as [])] as never },
    }),
    { min: 100, default: 400, max: 900 },
  );
});

test("effective weight defaults, clamps and stays null without an axis", () => {
  const font = storedFont(FULL);
  assert.equal(effectiveDirectWeight(font, null), 400);
  assert.equal(effectiveDirectWeight(font, 700), 700);
  assert.equal(effectiveDirectWeight(font, 50), 100);
  assert.equal(effectiveDirectWeight(font, 950), 900);
  assert.equal(effectiveDirectWeight(font, Number.NaN), 400);
  assert.equal(effectiveDirectWeight(font, Number.POSITIVE_INFINITY), 400);
  const fixed = storedFont(staticMetadata());
  assert.equal(effectiveDirectWeight(fixed, null), null);
  assert.equal(effectiveDirectWeight(fixed, 700), null);
  assert.equal(effectiveDirectWeight(null, 700), null);
  assert.equal(effectiveDirectWeight(undefined, null), null);
});

test("label settings carry size, profile, weight and preview pipeline", () => {
  const font = storedFont(FULL);
  const mono = directLabelSettings(font, 16, linearCurve(2), null);
  assert.deepEqual(
    [mono.sizePx, mono.profile, mono.rasterization, mono.renderer, mono.letterSpacingPx, mono.kerning],
    [16, "mono_1bit", "free_type_mono", "candidate", 0, true],
  );
  assert.deepEqual(mono.axes, { wght: 400 });
  assert.equal(mono.stemFitting, "font_hints_first");
  assert.equal(typeof mono.diagonalFitting, "boolean");
  assert.deepEqual(mono.monoRaster, { ...PREVIEW_MONO_RASTER });

  const gray = directLabelSettings(font, 24, linearCurve(4), 700);
  assert.deepEqual([gray.sizePx, gray.profile, gray.rasterization], [24, "gray_2bit", "coverage"]);
  assert.deepEqual(gray.axes, { wght: 700 });

  // The default and an explicit same-value override produce identical settings.
  assert.deepEqual(
    directLabelSettings(font, 16, linearCurve(2), null),
    directLabelSettings(font, 16, linearCurve(2), 400),
  );

  // Static fonts never receive an unsupported wght coordinate.
  const fixed = directLabelSettings(storedFont(staticMetadata()), 16, linearCurve(2), 700);
  assert.deepEqual(fixed.axes, {});
  assert.equal(fixed.profile, "mono_1bit");
});

test("an explicit zero weight stays distinct from an absent weight", () => {
  // A zero-based axis keeps 0 in range: null falls back to the default while
  // an explicit 0 clamps to the axis floor, and the export key follows the
  // effective coordinate in both cases.
  const zeroFont = storedFont(wghtMetadata(0, 50, 100), "zero-font");
  assert.equal(effectiveDirectWeight(zeroFont, null), 50);
  assert.equal(effectiveDirectWeight(zeroFont, 0), 0);
  const fonts = new Map([[zeroFont.id, zeroFont]]);
  const snapshots = directExportSnapshots(
    [
      { fontId: zeroFont.id, fontSize: 16, fontWeight: null },
      { fontId: zeroFont.id, fontSize: 16, fontWeight: 0 },
    ],
    fonts,
    linearCurve(2),
  );
  assert.deepEqual(
    snapshots.map((snapshot) => snapshot.id),
    [`direct:${zeroFont.id}:16:50`, `direct:${zeroFont.id}:16:0`],
  );
});

test("export snapshots skip invalid placements and dedup by effective weight", () => {
  const font = storedFont(FULL);
  const fonts = new Map([[font.id, font]]);
  const curve = linearCurve(2);
  assert.deepEqual(directExportSnapshots([], fonts, curve), []);
  const placements: readonly DirectExportPlacement[] = [
    { fontId: null, fontSize: 16, fontWeight: null },
    { fontId: font.id, fontSize: null, fontWeight: null },
    { fontId: "missing", fontSize: 16, fontWeight: null },
    { fontId: font.id, fontSize: 16, fontWeight: null },
    { fontId: font.id, fontSize: 16, fontWeight: 400 },
    { fontId: font.id, fontSize: 16, fontWeight: 700 },
    { fontId: font.id, fontSize: 24, fontWeight: null },
  ];
  const snapshots = directExportSnapshots(placements, fonts, curve);
  assert.deepEqual(
    snapshots.map((snapshot) => snapshot.id),
    [`direct:${font.id}:16:400`, `direct:${font.id}:16:700`, `direct:${font.id}:24:400`],
  );
  assert.deepEqual(
    snapshots.map((snapshot) => snapshot.settings.axes.wght),
    [400, 700, 400],
  );
  for (const snapshot of snapshots) {
    assert.equal(snapshot.fontId, font.id);
    assert.equal(snapshot.name, font.name);
  }
});
