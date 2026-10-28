import assert from "node:assert/strict";
import test from "node:test";
import { GLOBAL_ZOOM_KEY, readGlobalZoom, writeGlobalZoom, GLOBAL_CANVAS_KEY, readCanvasAppearance, writeCanvasAppearance } from "../../src/app/shell/display-preferences.ts";

test("global zoom migrates old preferences, validates storage and persists separately", () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  try {
    for (const [values, expected] of [
      [{}, 2],
      [{ [GLOBAL_ZOOM_KEY]: "4", "font-preview.library": '{"zoom":3}' }, 4],
      [{ "font-preview.library": '{"zoom":3}', "font-preview.zoom.specimen": "1" }, 3],
      [{ "font-preview.zoom.specimen": "1" }, 1],
      [{ [GLOBAL_ZOOM_KEY]: "9", "font-preview.library": '{"zoom":1.5}' }, 2],
      [{ [GLOBAL_ZOOM_KEY]: "NaN" }, 2],
    ] as [Record<string, string>, number][]) {
      Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
        getItem: (key: string) => values[key] ?? null,
        setItem: (key: string, value: string) => { values[key] = value; },
      } });
      assert.equal(readGlobalZoom(), expected);
      writeGlobalZoom(3);
      assert.equal(readGlobalZoom(), 3);
      assert.equal(values[GLOBAL_ZOOM_KEY], "3");
    }
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
      getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("denied"); },
    } });
    assert.equal(readGlobalZoom(), 2);
    assert.doesNotThrow(() => writeGlobalZoom(4));
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
});

 test("canvas appearance migrates library settings and persists independently", () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  try {
    for (const [stored, expected] of [
      [{}, { palette: "black-white", inverse: false }],
      [{ "font-preview.library": '{"text":"Kept","palette":"warm-paper","inverse":true}' }, { palette: "warm-paper", inverse: true }],
      [{ [GLOBAL_CANVAS_KEY]: '{"palette":"cool-paper","inverse":false}', "font-preview.library": '{"palette":"warm-paper","inverse":true}' }, { palette: "cool-paper", inverse: false }],
      [{ [GLOBAL_CANVAS_KEY]: '{"palette":"invalid","inverse":"yes"}' }, { palette: "black-white", inverse: false }],
      [{ [GLOBAL_CANVAS_KEY]: 'broken' }, { palette: "black-white", inverse: false }],
    ] as [Record<string, string>, unknown][]) {
      Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
        getItem: (key: string) => stored[key] ?? null,
        setItem: (key: string, value: string) => { stored[key] = value; },
      } });
      assert.deepEqual(readCanvasAppearance(), expected);
      const originalLibrary = stored["font-preview.library"];
      for (const palette of ["black-white", "warm-paper", "cool-paper"] as const) {
        for (const inverse of [true, false]) {
          writeCanvasAppearance({ palette, inverse });
          assert.deepEqual(readCanvasAppearance(), { palette, inverse });
        }
      }
      assert.equal(stored["font-preview.library"], originalLibrary);
    }
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
      getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("denied"); },
    } });
    assert.deepEqual(readCanvasAppearance(), { palette: "black-white", inverse: false });
    assert.doesNotThrow(() => writeCanvasAppearance({ palette: "warm-paper", inverse: true }));
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
});
