import assert from "node:assert/strict";
import test from "node:test";
import {
  legacyScreenPath,
  parseRoute,
  resolveRoute,
  screenPath,
} from "../../src/app/navigation/router.ts";

const IDS = ["aaa", "bbb"];

test("screen paths parse with or without a trailing slash, hash, or query", () => {
  assert.deepEqual(parseRoute("/screen/"), { name: "screen" });
  assert.deepEqual(parseRoute("/screen"), { name: "screen" });
  assert.deepEqual(parseRoute("#/screen/"), { name: "screen" });
  assert.deepEqual(parseRoute("#/screen"), { name: "screen" });
  assert.deepEqual(parseRoute("/screen/?utm=keep"), { name: "screen" });
  assert.equal(parseRoute("/screen/extra/"), null);
  assert.equal(parseRoute("/screens/"), null);
});

test("screen resolves without fonts and wins over stale font queries", () => {
  assert.deepEqual(resolveRoute("/screen/", "", IDS), { page: "screen" });
  assert.deepEqual(resolveRoute("/screen/", "", []), { page: "screen" });
  assert.deepEqual(resolveRoute("#/screen/", "", IDS), { page: "screen" });
  assert.deepEqual(resolveRoute("/screen/", "?font=aaa&v=1", IDS), { page: "screen" });
  assert.deepEqual(resolveRoute("/screen/?v=1&font=aaa", "", IDS), { page: "screen" });
  assert.deepEqual(resolveRoute("/screen/?utm=keep", "", []), { page: "screen" });
  const malformed = resolveRoute("/screen/extra/", "", IDS);
  assert.equal(malformed.page, "index");
  assert.match((malformed as { notice?: string }).notice ?? "", /Page not found/);
});

test("screen links drop snapshot state and keep foreign params", () => {
  assert.equal(screenPath(""), "/screen/");
  assert.equal(screenPath("v=1&font=aaa&profile=gray_3bit"), "/screen/");
  assert.equal(screenPath("v=1&font=aaa&utm=keep"), "/screen/?utm=keep");
});

test("legacy scene routes canonicalize directly to the Screen route", () => {
  assert.equal(legacyScreenPath(null, ""), "/screen/");
  assert.equal(legacyScreenPath(null, "v=1&font=aaa&utm=keep"), "/screen/?utm=keep");
  assert.equal(legacyScreenPath("abc", ""), "/screen/?scene=abc");
  assert.equal(legacyScreenPath("abc", "utm=keep"), "/screen/?scene=abc&utm=keep");
  assert.equal(
    legacyScreenPath("abc", "v=1&font=aaa&utm=keep"),
    "/screen/?scene=abc&utm=keep",
  );
});
