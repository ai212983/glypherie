import assert from "node:assert/strict";
import test from "node:test";
import {
  SCREEN_SIZE_DEFAULT,
  SCREEN_SIZE_KEY,
  readScreenSizePercent,
  writeScreenSizePercent,
} from "../../src/app/features/screen/screen-size.ts";

function withStorage(values: Record<string, string>, body: () => void): void {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  try {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => values[key] ?? null,
        setItem: (key: string, value: string) => {
          values[key] = value;
        },
      },
    });
    body();
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
}

test("screen size defaults to 100 without storage", () => {
  withStorage({}, () => {
    assert.equal(readScreenSizePercent(), 100);
  });
});

test("screen size persists valid percentages and recovers from bad storage", () => {
  withStorage({}, () => {
    writeScreenSizePercent(120);
    assert.equal(readScreenSizePercent(), 120);
  });
  for (const [stored, expected] of [
    ["100", 100],
    ["50", 50],
    ["150", 150],
    ["120.6", 121],
    ["20", 50],
    ["400", 150],
    ["0", 50],
    ["NaN", SCREEN_SIZE_DEFAULT],
    ["huge", SCREEN_SIZE_DEFAULT],
    ["", 50],
    ["null", SCREEN_SIZE_DEFAULT],
  ] as [string, number][]) {
    withStorage({ [SCREEN_SIZE_KEY]: stored }, () => {
      assert.equal(readScreenSizePercent(), expected, `stored ${JSON.stringify(stored)}`);
    });
  }
});

test("screen size writes clamp into range and survive denied storage", () => {
  withStorage({}, () => {
    writeScreenSizePercent(20);
    assert.equal(readScreenSizePercent(), 50);
    writeScreenSizePercent(400);
    assert.equal(readScreenSizePercent(), 150);
    writeScreenSizePercent(Number.NaN);
    assert.equal(readScreenSizePercent(), SCREEN_SIZE_DEFAULT);
  });
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  try {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: () => {
          throw new Error("denied");
        },
        setItem: () => {
          throw new Error("denied");
        },
      },
    });
    assert.equal(readScreenSizePercent(), SCREEN_SIZE_DEFAULT);
    assert.doesNotThrow(() => writeScreenSizePercent(120));
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
});
