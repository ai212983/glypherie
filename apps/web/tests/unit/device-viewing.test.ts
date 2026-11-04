// cspell:words Xteink
// Device viewing preferences: defaults, validation, persistence, recovery,
// and cleanup of the obsolete stored calibration field.
import assert from "node:assert/strict";
import test from "node:test";
import {
  GLOBAL_DEVICE_KEY,
  migrateDeviceViewingStorage,
  readDeviceViewing,
  writeDeviceViewing,
} from "../../src/app/shell/display-preferences.ts";

function withStorage(values: Record<string, string>, body: () => void): void {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  try {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => values[key] ?? null,
        setItem: (key: string, value: string) => { values[key] = value; },
      },
    });
    body();
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
}

test("device viewing defaults to the responsive specimen at reference size", () => {
  withStorage({}, () => {
    assert.deepEqual(readDeviceViewing(), { device: null, scale: "actual" });
  });
});

test("device viewing persists and validates stored values", () => {
  withStorage({}, () => {
    writeDeviceViewing({ device: "xteink-x4", scale: "one-to-one" });
    assert.deepEqual(readDeviceViewing(), { device: "xteink-x4", scale: "one-to-one" });
    assert.equal(JSON.parse((globalThis.localStorage?.getItem(GLOBAL_DEVICE_KEY) ?? "")).device, "xteink-x4");
  });
  for (const [stored, expected] of [
    ['{"device":"xteink-x3","scale":"one-to-one"}', { device: "xteink-x3", scale: "one-to-one" }],
    ['{"device":42,"scale":"actual"}', { device: null, scale: "actual" }],
    ['{"device":"inkplate-4-tempera","scale":"huge"}', { device: "inkplate-4-tempera", scale: "actual" }],
    ["broken", { device: null, scale: "actual" }],
    ["[1,2]", { device: null, scale: "actual" }],
  ] as [string, unknown][]) {
    withStorage({ [GLOBAL_DEVICE_KEY]: stored }, () => {
      assert.deepEqual(readDeviceViewing(), expected, stored);
    });
  }
});

test("stored calibration is dropped on read while device and scale survive", () => {
  for (const stored of [
    '{"device":"xteink-x4","scale":"one-to-one","calibration":120}',
    '{"device":"playdate","scale":"actual","calibration":109}',
    '{"device":null,"scale":"actual","calibration":300}',
    '{"calibration":96}',
  ]) {
    const values: Record<string, string> = {
      [GLOBAL_DEVICE_KEY]: stored,
      "font-preview.zoom.global": "3",
    };
    withStorage(values, () => {
      const seen = readDeviceViewing();
      assert.ok(!("calibration" in seen), `no calibration leaks into state (${stored})`);
      const raw = JSON.parse(values[GLOBAL_DEVICE_KEY] ?? "null") as Record<string, unknown>;
      assert.ok(!("calibration" in raw), `stored calibration cleaned (${stored})`);
      assert.equal(values["font-preview.zoom.global"], "3", "unrelated preferences untouched");
    });
  }
  // Malformed and out-of-range legacy values still recover to defaults.
  for (const [stored, expected] of [
    ['{"device":"playdate","scale":"actual","calibration":40}', { device: "playdate", scale: "actual" }],
    ['{"device":"playdate","scale":"actual","calibration":"wide"}', { device: "playdate", scale: "actual" }],
  ] as [string, unknown][]) {
    withStorage({ [GLOBAL_DEVICE_KEY]: stored }, () => {
      assert.deepEqual(readDeviceViewing(), expected, stored);
    });
  }
});

test("migration leaves clean, missing, and malformed storage alone", () => {
  withStorage({}, () => {
    migrateDeviceViewingStorage();
    assert.equal(globalThis.localStorage?.getItem(GLOBAL_DEVICE_KEY), null);
  });
  const clean = '{"device":"xteink-x4","scale":"actual"}';
  withStorage({ [GLOBAL_DEVICE_KEY]: clean }, () => {
    migrateDeviceViewingStorage();
    assert.equal(globalThis.localStorage?.getItem(GLOBAL_DEVICE_KEY), clean);
  });
  withStorage({ [GLOBAL_DEVICE_KEY]: "broken" }, () => {
    migrateDeviceViewingStorage();
    assert.equal(globalThis.localStorage?.getItem(GLOBAL_DEVICE_KEY), "broken");
  });
  const other: Record<string, string> = { "font-preview.canvas": '{"palette":"warm-paper"}' };
  withStorage(other, () => {
    migrateDeviceViewingStorage();
    assert.deepEqual(other, { "font-preview.canvas": '{"palette":"warm-paper"}' });
  });
});

test("device viewing tolerates unavailable storage", () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  try {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: () => { throw new Error("denied"); },
        setItem: () => { throw new Error("denied"); },
      },
    });
    assert.deepEqual(readDeviceViewing(), { device: null, scale: "actual" });
    assert.doesNotThrow(() => writeDeviceViewing({ device: "xteink-x4", scale: "actual" }));
    assert.doesNotThrow(() => migrateDeviceViewingStorage());
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
});
