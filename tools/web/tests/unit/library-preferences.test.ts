import assert from "node:assert/strict";
import test from "node:test";
import { LIBRARY_PREFERENCES_KEY, readStoredLibraryPreferences, writeStoredLibraryPreferences } from "../../src/app/features/library/preferences.ts";
import { MAX_TEXT_LENGTH, TEXT_DEFAULT } from "../../src/app/renderer/render-spec.ts";

function storage(values: Record<string, string> = {}, denied = false): () => void {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string): string | null => {
        if (denied) throw new Error("denied");
        return values[key] ?? null;
      },
      setItem: (key: string, value: string): void => {
        if (denied) throw new Error("denied");
        values[key] = value;
      },
    },
  });
  return () => {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  };
}

test("library preferences preserve text and empty samples independently of the global display preference", () => {
  const restore = storage({ "font-preview.zoom.specimen": "4" });
  try {
    assert.deepEqual(readStoredLibraryPreferences(), { text: TEXT_DEFAULT, baseSize: 16 });
    writeStoredLibraryPreferences({ text: "  Àg Sample  ", baseSize: 16 });
    assert.deepEqual(readStoredLibraryPreferences(), { text: "  Àg Sample  ", baseSize: 16 });
    writeStoredLibraryPreferences({ text: "", baseSize: 16 });
    assert.deepEqual(readStoredLibraryPreferences(), { text: "", baseSize: 16 });
  } finally { restore(); }
});

test("invalid saved settings use safe defaults and long text respects the input limit", () => {
  for (const raw of ["broken JSON", "null", "[]", '{"text":12,"zoom":9}', '{"zoom":"3"}', '{"zoom":1.5}']) {
    const restore = storage({ [LIBRARY_PREFERENCES_KEY]: raw });
    try { assert.deepEqual(readStoredLibraryPreferences(), { text: TEXT_DEFAULT, baseSize: 16 }); }
    finally { restore(); }
  }
  const restore = storage({ [LIBRARY_PREFERENCES_KEY]: JSON.stringify({ text: "a".repeat(MAX_TEXT_LENGTH + 1) }) });
  try { assert.equal(readStoredLibraryPreferences().text.length, MAX_TEXT_LENGTH); }
  finally { restore(); }
});

test("unavailable browser storage does not break the library controls", () => {
  const restore = storage({}, true);
  try {
    assert.deepEqual(readStoredLibraryPreferences(), { text: TEXT_DEFAULT, baseSize: 16 });
    assert.doesNotThrow(() => writeStoredLibraryPreferences({ text: "Sample", baseSize: 24 }));
  } finally { restore(); }
});

test("old library appearance values do not become font or specimen settings", () => {
  const values = { [LIBRARY_PREFERENCES_KEY]: JSON.stringify({ text: "Kept", baseSize: 24 }) };
  const restore = storage(values);
  try {
    assert.deepEqual(readStoredLibraryPreferences(), { text: "Kept", baseSize: 24 });
    writeStoredLibraryPreferences({ text: "New", baseSize: 32 });
    assert.deepEqual(JSON.parse(values[LIBRARY_PREFERENCES_KEY]), { text: "New", baseSize: 32 });
  } finally { restore(); }
});

test("base sizes validate and round-trip without discarding text", () => {
  for (const baseSize of [0, -1, 513, "24", null, undefined]) {
    const restore = storage({ [LIBRARY_PREFERENCES_KEY]: JSON.stringify({ text: "Kept", baseSize }) });
    try { assert.deepEqual(readStoredLibraryPreferences(), { text: "Kept", baseSize: 16 }); }
    finally { restore(); }
  }
  const restore = storage();
  try {
    for (const baseSize of [1, 8, 10, 12, 16, 16.5, 20, 24, 32, 48, 512] as const) {
      writeStoredLibraryPreferences({ text: "Ag", baseSize });
      assert.deepEqual(readStoredLibraryPreferences(), { text: "Ag", baseSize });
    }
  } finally { restore(); }
});

test("canvas palette references stay stable per preset and inverse", async () => {
  const { libraryPalette, canvasPaletteById } = await import("../../src/app/features/library/canvas-palettes.ts");
  assert.equal(libraryPalette("warm-paper", false), libraryPalette("warm-paper", false));
  assert.equal(libraryPalette("warm-paper", true), libraryPalette("warm-paper", true));
  assert.notEqual(libraryPalette("warm-paper", false), libraryPalette("warm-paper", true));
  assert.deepEqual(libraryPalette("warm-paper", false), [
    [244, 236, 220, 255],
    [26, 24, 21, 255],
  ]);
  assert.deepEqual(libraryPalette("warm-paper", true), [
    [26, 24, 21, 255],
    [244, 236, 220, 255],
  ]);
  assert.deepEqual(libraryPalette("cool-paper", false), [
    [232, 240, 248, 255],
    [27, 42, 58, 255],
  ]);
  assert.deepEqual(libraryPalette("black-white", false), [
    [255, 255, 255, 255],
    [0, 0, 0, 255],
  ]);
  assert.equal(canvasPaletteById("cool-paper").name, "Cool");
});

test("gray canvas palettes ramp paper to ink with stable identity", async () => {
  const { libraryPalette } = await import("../../src/app/features/library/canvas-palettes.ts");
  for (const id of ["black-white", "warm-paper", "cool-paper"] as const) {
    const normal = libraryPalette(id, false, "gray_3bit");
    const inverse = libraryPalette(id, true, "gray_3bit");
    assert.equal(normal.length, 8, `${id} gray palette carries eight levels`);
    assert.equal(inverse.length, 8, `${id} inverted gray palette carries eight levels`);
    const mono = libraryPalette(id, false);
    assert.deepEqual([normal[0], normal[7]], [mono[0], mono[1]], `${id} gray endpoints match the mono paper and ink`);
    assert.deepEqual([inverse[0], inverse[7]], [mono[1], mono[0]], `${id} inverted gray endpoints swap paper and ink`);
    assert.deepEqual([...inverse].reverse(), [...normal], `${id} inverse reverses the normal ramp`);
    assert.equal(libraryPalette(id, false, "gray_3bit"), normal, `${id} gray normal reference stays stable`);
    assert.equal(libraryPalette(id, true, "gray_3bit"), inverse, `${id} gray inverse reference stays stable`);
    assert.notEqual(normal, libraryPalette(id, false), `${id} gray and mono palettes stay distinct`);
    for (let channel = 0; channel < 3; channel += 1) {
      const from = normal[0]![channel]!;
      const to = normal[7]![channel]!;
      let previous = from;
      for (let step = 1; step < 8; step += 1) {
        const value = normal[step]![channel]!;
        assert.ok(
          to >= from ? value >= previous : value <= previous,
          `${id} gray channel ${channel} moves monotonically toward ink`,
        );
        previous = value;
      }
    }
    for (const entry of [...normal, ...inverse]) {
      assert.equal(entry[3], 255, `${id} gray entries stay opaque`);
    }
  }
});
