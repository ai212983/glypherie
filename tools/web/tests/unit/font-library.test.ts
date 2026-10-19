import "fake-indexeddb/auto";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test, { beforeEach } from "node:test";
import Dexie from "dexie";
import {
  FontStorageError,
  fontDatabase,
  getFont,
  isFontDatabaseBlocked,
  listFonts,
  removeFont,
  saveFont,
  seedBundledFonts,
  type BundledFontDescriptor,
  type FontMetadata,
} from "../../src/app/fonts/storage.ts";

Dexie.dependencies.indexedDB = globalThis.indexedDB;
Dexie.dependencies.IDBKeyRange = globalThis.IDBKeyRange;

const sha256 = (bytes: ArrayBuffer): string =>
  createHash("sha256").update(Buffer.from(bytes)).digest("hex");
const fontBytes = (seed = 0): ArrayBuffer =>
  Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;

function metadata(): FontMetadata {
  return {
    names: Object.fromEntries(
      ["family", "style", "full", "postscript", "version", "copyright", "manufacturer", "designer", "description", "vendor_url", "designer_url", "license", "license_url"].map((key) => [key, key === "family" ? "Fixture" : null])),
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
    kerning: { horizontal: true, vertical: false, sources: ["GPOS kern"] },
    style: { slope: "upright", weight_class: 400, width_class: 5, italic_angle: 0 },
    classification: { family_class: 0, panose: [2, 11, 5, 3, 3, 4, 3, 2, 2, 4], monospaced: false },
    coverage: { character_count: 1, ranges: [[65, 65]] },
    declared_unicode_ranges: [1, 0, 0, 0],
  };
}

const descriptors: BundledFontDescriptor[] = [{ url: "fonts/fixture.ttf", name: "Fixture", fileName: "fixture.ttf" }];

interface StubResponse {
  ok: boolean;
  status: number;
  url?: string;
  arrayBuffer: () => Promise<ArrayBuffer>;
}

function stubFetch(handler: (url: string) => Promise<StubResponse>): { calls: string[]; restore: () => void } {
  const calls: string[] = [];
  const previous = globalThis.fetch;
  const stub = async (input: string | URL | Request): Promise<Response> => {
    const href = String(input);
    calls.push(href);
    const response = await handler(href);
    return {
      ok: response.ok,
      status: response.status,
      url: response.url ?? href,
      arrayBuffer: response.arrayBuffer,
    } as unknown as Response;
  };
  globalThis.fetch = stub as typeof fetch;
  return { calls, restore: () => { globalThis.fetch = previous; } };
}

const okResponse = (bytes: ArrayBuffer): StubResponse => ({ ok: true, status: 200, arrayBuffer: async () => bytes });

beforeEach(async () => {
  await fontDatabase.close();
  await Dexie.delete("font-library");
  assert.equal(isFontDatabaseBlocked(), false);
});

test("saves an uploaded font under its SHA-256 content id", async () => {
  const bytes = fontBytes();
  const stored = await saveFont({ bytes, fileName: "fixture.ttf", name: "Fixture", metadata: metadata(), source: "uploaded" });
  assert.equal(stored.id, sha256(bytes));
  assert.match(stored.id, /^[0-9a-f]{64}$/);
  assert.equal(stored.source, "uploaded");
  assert.deepEqual(Buffer.from(stored.bytes), Buffer.from(bytes));
  assert.deepEqual(await listFonts(), [stored]);
  assert.deepEqual(await getFont(stored.id), stored);
  assert.equal(await getFont("0".repeat(64)), undefined);
});

test("deduplicates identical bytes atomically and never downgrades uploaded source", async () => {
  const bytes = fontBytes();
  const uploaded = await saveFont({ bytes, fileName: "a.ttf", name: "A", metadata: metadata(), source: "uploaded" });
  const bundled = await saveFont({ bytes, fileName: "b.ttf", name: "B", metadata: metadata(), source: "bundled" });
  assert.equal(bundled.id, uploaded.id);
  assert.equal(bundled.source, "uploaded");
  assert.equal((await listFonts()).length, 1);

  await removeFont(uploaded.id);
  const first = await saveFont({ bytes, fileName: "b.ttf", name: "B", metadata: metadata(), source: "bundled" });
  assert.equal(first.source, "bundled");
  const promoted = await saveFont({ bytes, fileName: "a.ttf", name: "A", metadata: metadata(), source: "uploaded" });
  assert.equal(promoted.source, "uploaded");
  assert.equal((await listFonts()).length, 1);
});

test("fonts survive close and reopen", async () => {
  const bytes = fontBytes(3);
  const stored = await saveFont({ bytes, fileName: "persist.ttf", name: "Persist", metadata: metadata(), source: "uploaded" });
  await fontDatabase.close();
  const reopened = await getFont(stored.id);
  assert.deepEqual(reopened, stored);
  assert.ok(reopened);
  assert.deepEqual(Buffer.from(reopened.bytes), Buffer.from(bytes));
});

test("removal deletes only that font", async () => {
  const first = await saveFont({ bytes: fontBytes(1), fileName: "one.ttf", name: "One", metadata: metadata(), source: "uploaded" });
  const second = await saveFont({ bytes: fontBytes(2), fileName: "two.ttf", name: "Two", metadata: metadata(), source: "uploaded" });
  await removeFont(first.id);
  assert.equal(await getFont(first.id), undefined);
  assert.deepEqual((await listFonts()).map((font) => font.id), [second.id]);
  await removeFont("f".repeat(64));
});

test("rejects empty bytes and malformed metadata", async () => {
  const input = { bytes: new ArrayBuffer(0), fileName: "empty.ttf", name: "Empty", metadata: metadata(), source: "uploaded" as const };
  await assert.rejects(saveFont(input), (error) => error instanceof FontStorageError && error.code === "empty-bytes");
  const badAxes = metadata();
  badAxes.axes = [{ tag: "wght", name: "Weight", min: 100, default: 50, max: 900, hidden: false }];
  await assert.rejects(
    saveFont({ bytes: fontBytes(), fileName: "bad.ttf", name: "Bad", metadata: badAxes, source: "uploaded" }),
    (error) => error instanceof FontStorageError && error.code === "invalid-metadata",
  );
  await assert.rejects(
    // Negative case: null metadata the input types reject.
    saveFont({ bytes: fontBytes(), fileName: "bad.ttf", name: "Bad", metadata: null as unknown as FontMetadata, source: "uploaded" }),
    (error) => error instanceof FontStorageError && error.code === "invalid-metadata",
  );
  assert.deepEqual(await listFonts(), []);
});

test("seeds bundled fonts once and never restores a deleted bundled font", async (t) => {
  const stub = stubFetch(async (url) => {
    assert.equal(url, "fonts/fixture.ttf");
    return okResponse(fontBytes(9));
  });
  t.after(stub.restore);
  await seedBundledFonts(descriptors, async () => metadata());
  const fonts = await listFonts();
  assert.equal(fonts.length, 1);
  assert.equal(fonts[0]?.source, "bundled");
  assert.equal(fonts[0]?.name, "Fixture");

  await seedBundledFonts(descriptors, async () => metadata());
  assert.equal(stub.calls.length, 1);

  assert.ok(fonts[0]);
  await removeFont(fonts[0].id);
  await seedBundledFonts(descriptors, async () => metadata());
  assert.equal(stub.calls.length, 1);
  assert.deepEqual(await listFonts(), []);
});

test("concurrent seeds fetch each bundled font once", async (t) => {
  const stub = stubFetch(async () => okResponse(fontBytes(11)));
  t.after(stub.restore);
  await Promise.all([
    seedBundledFonts(descriptors, async () => metadata()),
    seedBundledFonts(descriptors, async () => metadata()),
  ]);
  assert.equal(stub.calls.length, 1);
  assert.equal((await listFonts()).length, 1);
});

test("a failed seed writes no marker so the next attempt retries", async (t) => {
  let failures = 1;
  const stub = stubFetch(async () => {
    if (failures > 0) {
      failures -= 1;
      return { ok: false, status: 404, arrayBuffer: async () => fontBytes() };
    }
    return okResponse(fontBytes(13));
  });
  t.after(stub.restore);
  await assert.rejects(seedBundledFonts(descriptors, async () => metadata()), (error) => error instanceof FontStorageError && error.code === "seed-failed");
  assert.deepEqual(await listFonts(), []);
  await seedBundledFonts(descriptors, async () => metadata());
  assert.equal((await listFonts()).length, 1);
  assert.equal(stub.calls.length, 2);
});

test("seed rejects empty downloads without storing anything", async (t) => {
  const stub = stubFetch(async () => okResponse(new ArrayBuffer(0)));
  t.after(stub.restore);
  await assert.rejects(seedBundledFonts(descriptors, async () => metadata()), (error) => error instanceof FontStorageError && error.code === "seed-failed");
  assert.equal(stub.calls.length, 1);
  assert.deepEqual(await listFonts(), []);
});

function stubLocation(href: string): () => void {
  const previous: unknown = globalThis.location;
  Object.defineProperty(globalThis, "location", { value: new URL(href), configurable: true, writable: true });
  return () => {
    if (previous === undefined) delete (globalThis as { location?: unknown }).location;
    else Object.defineProperty(globalThis, "location", { value: previous, configurable: true, writable: true });
  };
}

test("seed accepts Vite absolute same-origin urls under a Pages prefix", async (t) => {
  const restoreLocation = stubLocation("http://127.0.0.1:4173/font_generator/");
  t.after(restoreLocation);
  const absolute = "http://127.0.0.1:4173/font_generator/assets/font-AbC123.ttf";
  const stub = stubFetch(async (url) => {
    assert.equal(url, absolute);
    return { ...okResponse(fontBytes(21)), url: absolute };
  });
  t.after(stub.restore);
  await seedBundledFonts([{ url: absolute, name: "Vite Font", fileName: "font-AbC123.ttf" }], async () => metadata());
  const fonts = await listFonts();
  assert.equal(fonts.length, 1);
  assert.equal(fonts[0]?.source, "bundled");
  assert.equal(stub.calls.length, 1);
});

test("seed rejects cross-origin and unsafe-scheme urls without contacting the network", async (t) => {
  const restoreLocation = stubLocation("http://127.0.0.1:4173/font_generator/");
  t.after(restoreLocation);
  const stub = stubFetch(async () => okResponse(fontBytes()));
  t.after(stub.restore);
  for (const url of [
    "https://cdn.example.com/font.ttf",
    "//cdn.example.com/font.ttf",
    "data:font/ttf;base64,AA==",
    "blob:http://127.0.0.1:4173/uuid",
    "javascript:alert(1)",
  ]) {
    await assert.rejects(
      seedBundledFonts([{ url, name: "Remote", fileName: "remote.ttf" }], async () => metadata()),
      (error) => error instanceof FontStorageError && error.code === "invalid-descriptor",
      `expected rejection for ${url}`,
    );
  }
  assert.equal(stub.calls.length, 0);
  assert.deepEqual(await listFonts(), []);
});

test("seed fails when the response lands cross-origin", async (t) => {
  const restoreLocation = stubLocation("http://127.0.0.1:4173/font_generator/");
  t.after(restoreLocation);
  let attempts = 0;
  const stub = stubFetch(async () => {
    attempts += 1;
    const url = attempts === 1 ? "https://cdn.example.com/font.ttf" : "http://127.0.0.1:4173/font_generator/fonts/fixture.ttf";
    return { ...okResponse(fontBytes(23)), url };
  });
  t.after(stub.restore);
  await assert.rejects(
    seedBundledFonts(descriptors, async () => metadata()),
    (error) => error instanceof FontStorageError && error.code === "seed-failed",
  );
  assert.deepEqual(await listFonts(), []);
  await seedBundledFonts(descriptors, async () => metadata());
  assert.equal((await listFonts()).length, 1);
});

test("seed surfaces inspection failures for retry", async (t) => {
  const stub = stubFetch(async () => okResponse(fontBytes(17)));
  t.after(stub.restore);
  let attempts = 0;
  await assert.rejects(
    seedBundledFonts(descriptors, async () => {
      attempts += 1;
      throw new Error("worker parse failed");
    }),
    (error) => error instanceof FontStorageError && error.code === "seed-failed",
  );
  await seedBundledFonts(descriptors, async () => metadata());
  assert.equal(attempts, 1);
  assert.equal((await listFonts()).length, 1);
});
