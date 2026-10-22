import assert from "node:assert/strict";
import test from "node:test";
import {
  palettesHash,
  parseHashRoute,
  resolveRoute,
  splitHash,
  variantHash,
  variantHashKeeping,
} from "../../src/app/navigation/router.ts";

const IDS = ["aaa", "bbb"];

test("hash parts split path from inner query", () => {
  assert.deepEqual(splitHash("#/font/aaa/?v=1&role=baseline"), { path: "/font/aaa/", search: "v=1&role=baseline" });
  assert.deepEqual(splitHash("#/"), { path: "/", search: "" });
  assert.deepEqual(splitHash(""), { path: "", search: "" });
  assert.deepEqual(splitHash("#/font/aaa"), { path: "/font/aaa", search: "" });
});

test("hash routes parse the library and font paths", () => {
  assert.deepEqual(parseHashRoute("#/"), { name: "index" });
  assert.deepEqual(parseHashRoute(""), { name: "index" });
  assert.deepEqual(parseHashRoute("#"), { name: "index" });
  assert.deepEqual(parseHashRoute("#/font/aaa/"), { name: "font", font: "aaa" });
  assert.deepEqual(parseHashRoute("#/font/aaa"), { name: "font", font: "aaa" });
  assert.deepEqual(parseHashRoute("#/font/aaa/?v=1"), { name: "font", font: "aaa" });
  assert.deepEqual(parseHashRoute("#/font/aaa/variant/vvv/"), { name: "variant", font: "aaa", variant: "vvv" });
  assert.deepEqual(parseHashRoute("#/font/aaa/variant/vvv"), { name: "variant", font: "aaa", variant: "vvv" });
  assert.deepEqual(
    parseHashRoute("#/font/aaa/variant/vvv/?utm=keep"),
    { name: "variant", font: "aaa", variant: "vvv" },
  );
  assert.equal(parseHashRoute("#/nope"), null);
  assert.equal(parseHashRoute("#/font/"), null);
  assert.equal(parseHashRoute("#/font/aaa/extra"), null);
  assert.equal(parseHashRoute("#/font/aaa/variant/"), null);
  assert.equal(parseHashRoute("#/font/aaa/variant/vvv/extra"), null);
  assert.equal(parseHashRoute("#family-aaa"), null);
});

test("bare roots resolve to the library", () => {
  assert.deepEqual(resolveRoute("", "", IDS), { page: "index" });
  assert.deepEqual(resolveRoute("#/", "", IDS), { page: "index" });
  assert.deepEqual(resolveRoute("#/", "?utm=keep", IDS), { page: "index" });
  assert.deepEqual(resolveRoute("", "?profile=gray_3bit&zoom=3", IDS), { page: "index" });
  assert.deepEqual(resolveRoute("#main", "", IDS), { page: "index" });
});

test("canonical font hashes select known fonts", () => {
  assert.deepEqual(resolveRoute("#/font/bbb/", "", IDS), { page: "font", font: "bbb" });
  assert.deepEqual(resolveRoute("#/font/bbb", "", IDS), { page: "font", font: "bbb" });
  assert.deepEqual(
    resolveRoute("#/font/bbb/?v=1&profile=gray_3bit&families=%7B%7D", "", IDS),
    { page: "font", font: "bbb" },
  );
});

test("variant hashes resolve to the variant page for known fonts", () => {
  assert.deepEqual(
    resolveRoute("#/font/bbb/variant/vvv/", "", IDS),
    { page: "variant", font: "bbb", variant: "vvv" },
  );
  assert.deepEqual(
    resolveRoute("#/font/bbb/variant/vvv", "", IDS),
    { page: "variant", font: "bbb", variant: "vvv" },
  );
  assert.deepEqual(
    resolveRoute("#/font/bbb/variant/vvv/?utm=keep", "", IDS),
    { page: "variant", font: "bbb", variant: "vvv" },
  );
  assert.equal(variantHash("bbb", "vvv"), "#/font/bbb/variant/vvv/");
  assert.equal(variantHashKeeping("bbb", "vvv", ""), "#/font/bbb/variant/vvv/");
  assert.equal(
    variantHashKeeping("bbb", "vvv", "v=1&font=bbb&profile=gray_3bit&role=baseline&utm=keep"),
    "#/font/bbb/variant/vvv/?utm=keep",
  );
});

test("variant hashes with unknown fonts recover on the library with a notice", () => {
  const unknown = resolveRoute("#/font/ghost/variant/vvv/", "", IDS);
  assert.equal(unknown.page, "index");
  assert.match((unknown as { notice?: string }).notice ?? "", /not found in this library/);
  const malformed = resolveRoute("#/font/bbb/variant/", "", IDS);
  assert.equal(malformed.page, "index");
  assert.match((malformed as { notice?: string }).notice ?? "", /Page not found/);
});

test("canonical font hashes win over conflicting legacy outer queries", () => {
  assert.deepEqual(resolveRoute("#/font/bbb/", "?font=aaa&v=1", IDS), { page: "font", font: "bbb" });
  assert.deepEqual(resolveRoute("#/font/bbb/", "", IDS), { page: "font", font: "bbb" });
});

test("legacy outer queries and family hashes still resolve", () => {
  assert.deepEqual(resolveRoute("", "?font=bbb", IDS), { page: "font", font: "bbb" });
  assert.deepEqual(resolveRoute("", "?font=bbb&utm=keep", IDS), { page: "font", font: "bbb" });
  assert.deepEqual(resolveRoute("#family-bbb", "", IDS), { page: "font", font: "bbb" });
  assert.deepEqual(
    resolveRoute("", "?v=1&font=bbb&profile=gray_3bit&families=%7B%7D", IDS),
    { page: "font", font: "bbb" },
  );
});

test("versioned snapshots without a font stay on the library", () => {
  assert.deepEqual(resolveRoute("", "?v=1", IDS), { page: "index" });
});

test("palettes hashes parse with or without a trailing slash or query", () => {
  assert.deepEqual(parseHashRoute("#/palettes/"), { name: "palettes" });
  assert.deepEqual(parseHashRoute("#/palettes"), { name: "palettes" });
  assert.deepEqual(parseHashRoute("#/palettes/?utm=keep"), { name: "palettes" });
});

test("palettes resolves without fonts and wins over stale font queries", () => {
  assert.deepEqual(resolveRoute("#/palettes/", "", IDS), { page: "palettes" });
  const noFonts: string[] = [];
  assert.deepEqual(resolveRoute("#/palettes/", "", noFonts), { page: "palettes" });
  assert.deepEqual(resolveRoute("#/palettes/", "?font=aaa&v=1", IDS), { page: "palettes" });
  assert.deepEqual(resolveRoute("#/palettes/?v=1&font=aaa", "", IDS), { page: "palettes" });
  assert.deepEqual(resolveRoute("#/palettes/?utm=keep", "", noFonts), { page: "palettes" });
});

test("palettes links drop snapshot state and keep foreign params", () => {
  assert.equal(palettesHash(""), "#/palettes/");
  assert.equal(palettesHash("v=1&font=aaa&profile=gray_3bit"), "#/palettes/");
  assert.equal(palettesHash("v=1&font=aaa&utm=keep"), "#/palettes/?utm=keep");
});

test("unknown ids and malformed routes recover on the library with a notice", () => {
  const minimal = resolveRoute("", "?font=ghost", IDS);
  assert.equal(minimal.page, "index");
  assert.match((minimal as { notice?: string }).notice ?? "", /not found in this library/);
  const snapshot = resolveRoute("", "?v=1&font=ghost", IDS);
  assert.equal(snapshot.page, "index");
  assert.match((snapshot as { notice?: string }).notice ?? "", /not found in this library/);
  const hash = resolveRoute("#family-ghost", "", IDS);
  assert.equal(hash.page, "index");
  assert.match((hash as { notice?: string }).notice ?? "", /not found in this library/);
  const unknown = resolveRoute("#/font/ghost/", "", IDS);
  assert.equal(unknown.page, "index");
  assert.match((unknown as { notice?: string }).notice ?? "", /not found in this library/);
  const malformed = resolveRoute("#/nope", "", IDS);
  assert.equal(malformed.page, "index");
  assert.match((malformed as { notice?: string }).notice ?? "", /Page not found/);
});
