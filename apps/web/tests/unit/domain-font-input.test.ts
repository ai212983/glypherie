// Font input boundary: the domain validates untrusted structured-cloneable
// input itself, so malformed bytes, names and sources fail as DomainError
// "invalid-input" (never a raw TypeError/RangeError) and concurrent saves of
// the same bytes converge on one content-addressed row.

import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { saveFont } from "../../src/app/domain/commands.ts";
import { DomainError } from "../../src/app/domain/errors.ts";
import { getBackend, closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import type { FontMetadata } from "../../src/app/fonts/storage.ts";

beforeEach(async () => {
  await resetDomainForTests();
});

after(async () => {
  await closeDomainForTests();
});

function metadata(): FontMetadata {
  return {
    names: { family: "Fixture" },
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
  };
}

const fontBytes = (seed = 0): ArrayBuffer =>
  Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;

function validInput() {
  return {
    bytes: fontBytes(3),
    fileName: "fixture.ttf",
    name: "Fixture",
    metadata: metadata(),
    source: "uploaded" as const,
  };
}

async function rejectsInvalidInput(input: unknown, pattern: RegExp): Promise<void> {
  await assert.rejects(
    saveFont(getBackend(), input as never),
    (error: unknown) => error instanceof DomainError && error.code === "invalid-input" && pattern.test(error.message),
  );
}

test("non-object input fails as invalid-input, not a raw TypeError", async () => {
  await rejectsInvalidInput(null, /byte content/);
  await rejectsInvalidInput(undefined, /byte content/);
  await rejectsInvalidInput("bytes", /byte content/);
});

test("non-byte content fails as invalid-input without allocating it", async () => {
  // A negative length makes the eager Uint8Array conversion throw a raw
  // RangeError; a positive number would allocate that many zero bytes first.
  await rejectsInvalidInput({ ...validInput(), bytes: -1 }, /byte content/);
  await rejectsInvalidInput({ ...validInput(), bytes: 64 }, /byte content/);
  await rejectsInvalidInput({ ...validInput(), bytes: "not-bytes" }, /byte content/);
});

test("empty bytes fail as no-bytes for both ArrayBuffer and Uint8Array", async () => {
  await rejectsInvalidInput({ ...validInput(), bytes: new ArrayBuffer(0) }, /no bytes/);
  await rejectsInvalidInput({ ...validInput(), bytes: new Uint8Array(0) }, /no bytes/);
});

test("empty names and unknown sources fail as invalid-input", async () => {
  await rejectsInvalidInput({ ...validInput(), name: "  " }, /non-empty name/);
  await rejectsInvalidInput({ ...validInput(), fileName: "" }, /non-empty file name/);
  await rejectsInvalidInput({ ...validInput(), source: "cdn" }, /bundled or uploaded/);
});

test("Uint8Array bytes store under the same content id as ArrayBuffer bytes", async () => {
  const raw = new Uint8Array(fontBytes(9));
  const fromView = await saveFont(getBackend(), { ...validInput(), bytes: raw });
  const fromBuffer = await saveFont(getBackend(), {
    ...validInput(),
    bytes: raw.buffer as ArrayBuffer,
    source: "bundled",
  });
  assert.equal(fromView.id, fromBuffer.id);
  // Uploaded wins over the earlier bundled row without duplicating the font.
  assert.equal(fromBuffer.source, "uploaded");
});

test("concurrent saves of the same bytes converge on one row", async () => {
  const backend = getBackend();
  const bytes = fontBytes(11);
  const [first, second] = await Promise.all([
    saveFont(backend, { ...validInput(), bytes }),
    saveFont(backend, { ...validInput(), bytes: bytes.slice(0) }),
  ]);
  assert.equal(first.id, second.id);
});
