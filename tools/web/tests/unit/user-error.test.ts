import assert from "node:assert/strict";
import test from "node:test";
import { userError, UserFacingError } from "../../src/app/user-error.ts";
import { VariantStorageError } from "../../src/app/variants/model.ts";

test("errors hide internal details while preserving recovery instructions", (t) => {
  t.mock.method(console, "warn", () => {});
  const fallback = "Couldn’t save changes.";
  assert.equal(userError(new Error("Worker request 421 failed: invalid object"), fallback), fallback);
  assert.equal(userError(new VariantStorageError("conflict", "Expected revision 2; found 3 for id abc"), fallback),
    "Another tab changed this variant.");
  assert.equal(userError(new VariantStorageError("blocked", "Old database version"), fallback),
    "Storage is blocked. Close other Glypherie tabs and reload.");
  assert.equal(userError(new VariantStorageError("quota-exceeded", "Browser variant storage is full"), fallback),
    "Browser storage is full. Remove a variant to free space.");
  assert.equal(userError(new UserFacingError("Couldn’t import example.ttf."), fallback), "Couldn’t import example.ttf.");
});
