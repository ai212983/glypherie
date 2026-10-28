import assert from "node:assert/strict";
import test from "node:test";
import {
  readStoredTheme,
  THEME_STORAGE_KEY,
  writeStoredTheme,
} from "../../src/components/theme/theme.ts";

function stubStorage(behavior: { get: () => string | null; set: (value: string) => void }): () => void {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      getItem: (key: string): string | null => (key === THEME_STORAGE_KEY ? behavior.get() : null),
      setItem: (key: string, value: string): void => {
        if (key === THEME_STORAGE_KEY) behavior.set(value);
      },
    },
    configurable: true,
    writable: true,
  });
  return () => {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  };
}

test("stored theme round-trips and rejects unknown values", () => {
  let held: string | null = null;
  const restore = stubStorage({ get: () => held, set: (value) => { held = value; } });
  try {
    assert.equal(readStoredTheme(), null);
    writeStoredTheme("dark");
    assert.equal(held, "dark");
    assert.equal(readStoredTheme(), "dark");
    held = "sepia";
    assert.equal(readStoredTheme(), null);
  } finally {
    restore();
  }
});

test("unavailable storage degrades to defaults without throwing", () => {
  const restore = stubStorage({
    get: () => { throw new Error("denied"); },
    set: () => { throw new Error("denied"); },
  });
  try {
    assert.equal(readStoredTheme(), null);
    writeStoredTheme("dark");
  } finally {
    restore();
  }
});
