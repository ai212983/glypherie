import assert from "node:assert/strict";
import test from "node:test";
import {
  palettesPath,
  homePath,
  indexPath,
  parseRoute,
  resolveRoute,
  splitRoute,
  variantPath,
  variantPathKeeping,
} from "../../src/app/navigation/router.ts";

const IDS = ["aaa", "bbb"];

test("hash parts split path from inner query", () => {
  assert.deepEqual(splitRoute("#/font/aaa/?v=1&role=baseline"), { path: "/font/aaa/", search: "v=1&role=baseline" });
  assert.deepEqual(splitRoute("#/"), { path: "/", search: "" });
  assert.deepEqual(splitRoute(""), { path: "", search: "" });
  assert.deepEqual(splitRoute("#/font/aaa"), { path: "/font/aaa", search: "" });
});

test("hash routes parse the library and font paths", () => {
  assert.deepEqual(parseRoute("#/"), { name: "home" });
  assert.deepEqual(parseRoute(""), { name: "home" });
  assert.deepEqual(parseRoute("#"), { name: "home" });
  assert.deepEqual(parseRoute("#/font/aaa/"), { name: "font", font: "aaa" });
  assert.deepEqual(parseRoute("#/font/aaa"), { name: "font", font: "aaa" });
  assert.deepEqual(parseRoute("#/font/aaa/?v=1"), { name: "font", font: "aaa" });
  assert.deepEqual(parseRoute("#/font/aaa/variant/vvv/"), { name: "variant", font: "aaa", variant: "vvv" });
  assert.deepEqual(parseRoute("#/font/aaa/variant/vvv"), { name: "variant", font: "aaa", variant: "vvv" });
  assert.deepEqual(
    parseRoute("#/font/aaa/variant/vvv/?utm=keep"),
    { name: "variant", font: "aaa", variant: "vvv" },
  );
  assert.equal(parseRoute("#/nope"), null);
  assert.equal(parseRoute("#/font/"), null);
  assert.equal(parseRoute("#/font/aaa/extra"), null);
  assert.equal(parseRoute("#/font/aaa/variant/"), null);
  assert.equal(parseRoute("#/font/aaa/variant/vvv/extra"), null);
  assert.equal(parseRoute("#family-aaa"), null);
});

test("bare roots resolve to the landing and legacy library hashes migrate", () => {
  assert.deepEqual(resolveRoute("", "", IDS), { page: "home" });
  assert.deepEqual(resolveRoute("#/", "", IDS), { page: "index" });
  assert.deepEqual(resolveRoute("#/", "?utm=keep", IDS), { page: "index" });
  assert.deepEqual(resolveRoute("", "?profile=gray_3bit&zoom=3", IDS), { page: "home" });
  assert.deepEqual(resolveRoute("#main", "", IDS), { page: "home" });
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
  assert.equal(variantPath("bbb", "vvv"), "/font/bbb/variant/vvv/");
  assert.equal(variantPathKeeping("bbb", "vvv", ""), "/font/bbb/variant/vvv/");
  assert.equal(
    variantPathKeeping("bbb", "vvv", "v=1&font=bbb&profile=gray_3bit&role=baseline&utm=keep"),
    "/font/bbb/variant/vvv/?utm=keep",
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
  assert.deepEqual(parseRoute("#/palettes/"), { name: "palettes" });
  assert.deepEqual(parseRoute("#/palettes"), { name: "palettes" });
  assert.deepEqual(parseRoute("#/palettes/?utm=keep"), { name: "palettes" });
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
  assert.equal(palettesPath(""), "/palettes/");
  assert.equal(palettesPath("v=1&font=aaa&profile=gray_3bit"), "/palettes/");
  assert.equal(palettesPath("v=1&font=aaa&utm=keep"), "/palettes/?utm=keep");
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

test("clean paths resolve the library, previews, variants and palette lab", () => {
  assert.deepEqual(resolveRoute("/", "", IDS), { page: "home" });
  assert.deepEqual(resolveRoute("/font/bbb/", "?v=1&font=aaa", IDS), { page: "font", font: "bbb" });
  assert.deepEqual(resolveRoute("/font/bbb/variant/vvv/", "", IDS), { page: "variant", font: "bbb", variant: "vvv" });
  assert.deepEqual(resolveRoute("/palettes/", "?font=aaa", []), { page: "palettes" });
  assert.match((resolveRoute("/unknown/", "?font=aaa", IDS) as { notice: string }).notice, /Page not found/);
  assert.equal(parseRoute("/font/%zz/"), null);
  assert.equal(variantPath("a/b", "v?x"), "/font/a%2Fb/variant/v%3Fx/");
});


test("library paths are explicit and ignore stale font query state", () => {
  for (const path of ["/fonts/", "/fonts", "#/fonts/"]) {
    assert.deepEqual(parseRoute(path), { name: "index" });
    assert.deepEqual(resolveRoute(path, "?v=1&font=bbb", []), { page: "index" });
  }
  assert.equal(indexPath("?v=1&font=bbb&utm=keep"), "/fonts/?utm=keep");
  assert.equal(homePath("?v=1&font=bbb&utm=keep"), "/?utm=keep");
  assert.deepEqual(resolveRoute("/", "?utm=keep", []), { page: "home" });
  assert.deepEqual(resolveRoute("/", "?font=bbb&v=1", IDS), { page: "font", font: "bbb" });
});
