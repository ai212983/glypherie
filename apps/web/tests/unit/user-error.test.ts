import assert from "node:assert/strict";
import test from "node:test";
import { MigrationError } from "@nicia-ai/typegraph";
import { userError, UserFacingError } from "../../src/app/user-error.ts";
import { VariantStorageError } from "../../src/app/variants/model.ts";

test("errors hide internal details while preserving recovery instructions", (t) => {
  t.mock.method(console, "warn", () => {});
  const fallback = "Couldn’t save changes.";
  assert.equal(userError(new Error("Worker request 421 failed: invalid object"), fallback), fallback);
  assert.equal(
    userError(new VariantStorageError("conflict", "Expected revision 2; found 3 for id abc"), fallback),
    "Another tab changed this variant.",
  );
  assert.equal(
    userError(new VariantStorageError("blocked", "Old database version"), fallback),
    "Storage is blocked. Close other Glypherie tabs and reload.",
  );
  const stale = Object.assign(new Error("version skew"), {
    code: "stale-owner",
  });
  assert.match(userError(stale, fallback), /different app versions/);
  assert.doesNotMatch(userError(stale, fallback), /other Glypherie tabs/);
  assert.equal(
    userError(new VariantStorageError("quota-exceeded", "Browser variant storage is full"), fallback),
    "Browser storage is full. Remove a variant to free space.",
  );
  assert.equal(
    userError(new UserFacingError("Couldn’t import example.ttf."), fallback),
    "Couldn’t import example.ttf.",
  );
  const schemaFailure = new MigrationError(
    "Schema migration required: Nodes: 0 added, 0 removed, 1 modified. MIGRATE data for node kind " +
      '"RenderingProfile": Property schemas changed incompatibly in "RenderingProfile": kerning. ' +
      "Differences: /nodes/RenderingProfile/properties/properties/kerning/type",
    {
      graphId: "glypherie-domain-v1",
      fromVersion: 1,
      toVersion: 2,
      reason: "breaking-change",
    },
  );
  assert.equal(userError(schemaFailure, fallback), fallback);
  assert.doesNotMatch(userError(schemaFailure, fallback), /MIGRATE|RenderingProfile|kerning|glypherie-domain-v1/);
});
