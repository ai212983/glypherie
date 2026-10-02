import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright-core";
import { PNG } from "pngjs";
import { createComparisonImporter, validateComparison, glyphPages } from "../lib/comparisons.js";
import { build, fixture, hash, serve } from "./helpers.js";

async function comparisonFixture(t) {
  const f = await fixture(t);
  const candidate = structuredClone(f.manifest);
  candidate.variant = { ...candidate.variant, id: "candidate-test", kind: "iteration", version: "001.01", generation_sha256: "b".repeat(64) };
  candidate.families[0].sizes.unshift({ ...structuredClone(candidate.families[0].sizes[0]), size_px: 14 });
  for (const group of candidate.families[0].sizes) {
    for (const item of group.items) item.id += `-${group.size_px}`;
  }
  await fs.cp(f.packageDir, path.join(f.root, "candidate-test"), { recursive: true });
  await fs.writeFile(path.join(f.root, "candidate-test/manifest.json"), JSON.stringify(candidate));
  await fs.writeFile(path.join(f.root, "active.json"), JSON.stringify({ ...f.pointer, variant_id: "candidate-test", manifest: "candidate-test/manifest.json" }));
  const assets = new Map();
  const profiles = [];
  for (const [id, bits] of [["mono_1bit", 1], ["gray_3bit", 3]]) {
    const previous = bits === 1 ? [0, 1, 0, 1] : [0, 7, 3, 0];
    const current = bits === 1 ? [1, 0, 0, 1] : [7, 0, 3, 0];
    const rgb = (q) => Array(3).fill(255 - Math.round(q * 255 / ((1 << bits) - 1)));
    const profile = { id, advance_px: 2, reason: null };
    for (const key of ["previous", "current", "difference"]) {
      const data = Buffer.from(current.flatMap((q, i) => [...(key === "difference"
        ? q > previous[i] ? [0, 96, 255] : q < previous[i] ? [224, 32, 32] : rgb(q)
        : rgb(key === "previous" ? previous[i] : q)), 255]));
      const bytes = PNG.sync.write({ width: 2, height: 2, data }, { colorType: 2, bitDepth: 8 });
      const sha256 = hash(bytes);
      profile[key] = { path: `assets/${sha256}.png`, sha256 };
      assets.set(profile[key].path, bytes);
    }
    profiles.push(profile);
  }
  const manifest = {
    schema_version: "web-glyph-comparison-v1", id: "01",
    previous: { label: "Reference", package_id: "reference-test", generation_sha256: "a".repeat(64) },
    current: { label: "001.01", package_id: "candidate-test", generation_sha256: "b".repeat(64) },
    profiles: [{ id: "mono_1bit", output_bits: 1 }, { id: "gray_3bit", output_bits: 3 }],
    families: [{ id: "fixture", name: "Fixture font", sizes: [16, 14].map((size_px) => ({
      size_px, axes: { wght: 400 }, canvas: { width_px: 2, height_px: 2, origin_x: 0, baseline_y: 0, padding_px: 0 },
      glyphs: ["A", "<"].map((character) => ({ codepoint: character.codePointAt(0), character, profiles: structuredClone(profiles) })),
    })) }],
  };
  const save = async () => {
    const bytes = Buffer.from(JSON.stringify(manifest));
    const packageId = `01-${hash(bytes)}`;
    const packageDir = path.join(f.root, "comparisons", packageId);
    await fs.mkdir(path.join(packageDir, "assets"), { recursive: true });
    for (const [relative, data] of assets) await fs.writeFile(path.join(packageDir, relative), data);
    await fs.writeFile(path.join(packageDir, "manifest.json"), bytes);
    const entry = { id: "01", manifest: `${packageId}/manifest.json` };
    await fs.writeFile(path.join(f.root, "comparisons/index.json"), JSON.stringify({ schema_version: "web-comparisons-v1", comparisons: [entry] }));
    return { entry, packageId, packageDir };
  };
  return { ...f, comparison: manifest, assets, saveComparison: save, ...await save() };
}

test("imports comparisons and copies exact prepared assets; pages group a symbol across sizes", async (t) => {
  const f = await comparisonFixture(t);
  const importer = createComparisonImporter(f.root);
  const comparisons = await importer.load();
  assert.equal(comparisons.length, 1);
  assert.deepEqual(comparisons[0].families[0].sizes.map((s) => s.size_px), [14, 16]);
  const pages = glyphPages(comparisons);
  assert.equal(pages.length, 2);
  assert.equal(pages[0].slug, "U0041");
  assert.equal(pages[1].slug, "U003C");
  assert.deepEqual(pages[0].sizes.map((s) => s.size_px), [14, 16]);
  await importer.publish(comparisons, f.output);
  for (const [relative, bytes] of f.assets) assert.deepEqual(await fs.readFile(path.join(f.output, "comparison-content", f.packageId, relative)), bytes);
  const html = await build(f.root, f.output);
  assert.match(html, /<p class="variant"><span>reference<\/span> → <span>001\.01<\/span><\/p>/);
  assert.match(html, /\.\/content\/candidate-test\//);
  assert.doesNotMatch(html, /\.\/content\/reference-test\//);
  assert.match(html, /\.\/01\/fixture\/U0041\/#size-14/);
  assert.match(html, /Compare &lt; in Fixture font/);
  await assert.rejects(fs.access(path.join(f.output, "01/index.html")), { code: "ENOENT" });
  const glyph = await fs.readFile(path.join(f.output, "01/fixture/U003C/index.html"), "utf8");
  assert.match(glyph, /Fixture font — &lt;/);
  assert.match(glyph, /Blue: added ink/);
  assert.match(glyph, /Red: removed ink/);
});

test("the active index only includes glyphs from its own comparison package", async (t) => {
  const f = await comparisonFixture(t);
  await fs.mkdir(path.join(f.output, "01"), { recursive: true });
  await fs.writeFile(path.join(f.output, "01/index.html"), '<script>location.replace("../")</script>');
  await f.save();
  const html = await build(f.root, f.output);
  assert.match(html, /<p class="variant"><span>reference<\/span><\/p>/);
  assert.doesNotMatch(html, /glyph-link/);
  await assert.rejects(fs.access(path.join(f.output, "01/index.html")), { code: "ENOENT" });
  const glyph = await fs.readFile(path.join(f.output, "01/fixture/U0041/index.html"), "utf8");
  assert.match(glyph, /href="\.\.\/\.\.\/\.\.\/#family-fixture"/);
});

test("only changed profiles and sizes produce thumbnails/pages; rebuilding removes stale pages", async (t) => {
  const f = await comparisonFixture(t);
  await build(f.root, f.output);
  const unchanged = (profile) => {
    profile.current = profile.previous;
    profile.difference = profile.previous;
  };
  for (const size of f.comparison.families[0].sizes) {
    for (const glyph of size.glyphs) for (const profile of glyph.profiles) {
      if (glyph.character === "<" || size.size_px === 16 || profile.id === "gray_3bit") unchanged(profile);
    }
  }
  await f.saveComparison();
  const comparisons = await createComparisonImporter(f.root).load();
  const pages = glyphPages(comparisons);
  assert.equal(pages.length, 1);
  assert.deepEqual(pages[0].sizes.map((size) => size.size_px), [14]);
  assert.deepEqual(pages[0].sizes[0].profiles.map((profile) => profile.id), ["mono_1bit"]);
  const html = await build(f.root, f.output);
  assert.equal((html.match(/class="specimen-card glyph-link"/g) ?? []).length, 1);
  assert.match(html, /U0041\/#size-14/);
  assert.doesNotMatch(html, /U003C/);
  await assert.rejects(fs.access(path.join(f.output, "01/fixture/U003C/index.html")), { code: "ENOENT" });
  const glyph = await fs.readFile(path.join(f.output, "01/fixture/U0041/index.html"), "utf8");
  assert.match(glyph, /id="size-14"/);
  assert.doesNotMatch(glyph, /id="size-16"/);
  assert.equal((glyph.match(/class="specimen-card"/g) ?? []).length, 3);
  for (const size of f.comparison.families[0].sizes) for (const entry of size.glyphs) for (const profile of entry.profiles) unchanged(profile);
  await f.saveComparison();
  assert.equal(glyphPages(await createComparisonImporter(f.root).load()).length, 0);
  const empty = await build(f.root, f.output);
  assert.doesNotMatch(empty, /glyph-sheet/);
  assert.match(empty, /Reading sample/);
  await assert.rejects(fs.access(path.join(f.output, "01/fixture/U0041/index.html")), { code: "ENOENT" });
});

test("gray-only pixel changes remain reviewable and become the symbol page default", async (t) => {
  const f = await comparisonFixture(t);
  for (const size of f.comparison.families[0].sizes) for (const glyph of size.glyphs) {
    glyph.profiles = glyph.profiles.filter((profile) => profile.id === "gray_3bit");
  }
  await f.saveComparison();
  const pages = glyphPages(await createComparisonImporter(f.root).load());
  assert.equal(pages.length, 2);
  assert.equal(pages[0].comparison.defaultProfile, "gray_3bit");
  assert.ok(pages[0].sizes.every((size) => size.initiallyVisible && size.profiles[0].initiallyVisible));
  const html = await build(f.root, f.output);
  assert.match(html, /class="specimen-row glyph-sheet"[^>]* hidden/);
  const glyph = await fs.readFile(path.join(f.output, "01/fixture/U0041/index.html"), "utf8");
  assert.match(glyph, /value="gray_3bit" checked/);
});

test("comparison metadata rejects unsafe routes, duplicate glyphs and missing images", async (t) => {
  const f = await comparisonFixture(t);
  for (const change of [
    (m, e) => { e.id = "../escape"; },
    (m, e) => { e.manifest = "../manifest.json"; },
    (m) => { m.id = "02"; },
    (m) => { m.families[0].id = "../escape"; },
    (m) => { m.families[0].sizes[0].canvas.width_px = 0; },
    (m) => { m.families[0].sizes[0].glyphs.push(m.families[0].sizes[0].glyphs[0]); },
    (m) => { m.families[0].sizes[0].glyphs[0].character = "X"; },
    (m) => { m.families[0].sizes[0].glyphs[0].profiles[0].current.path = "../outside.png"; },
    (m) => { m.families[0].sizes[0].glyphs[0].profiles[0].previous = null; },
  ]) {
    const m = structuredClone(f.comparison), e = structuredClone(f.entry);
    change(m, e);
    assert.throws(() => validateComparison(m, e));
  }
});

test("missing comparisons leave the active index available; damaged selected comparisons fail explicitly", async (t) => {
  const empty = await fixture(t);
  assert.deepEqual(await createComparisonImporter(empty.root).load(), []);
  const f = await comparisonFixture(t);
  const image = f.comparison.families[0].sizes[0].glyphs[0].profiles[0].current.path;
  await fs.writeFile(path.join(f.packageDir, image), Buffer.from("damaged"));
  await assert.rejects(() => createComparisonImporter(f.root).load(), /checksum/);
});

test("comparison import rejects symlinked assets", async (t) => {
  const f = await comparisonFixture(t);
  const relative = f.comparison.families[0].sizes[0].glyphs[0].profiles[0].current.path;
  const file = path.join(f.packageDir, relative);
  await fs.rename(file, `${file}.original`);
  await fs.symlink(`${file}.original`, file);
  await assert.rejects(() => createComparisonImporter(f.root).load(), /regular/);
});

const browserPath = process.env.WEB_TEST_BROWSER ?? "/opt/google/chrome/chrome";
const browserAvailable = await fs.access(browserPath).then(() => true, () => false);

async function attentionFixture(t) {
  const f = await comparisonFixture(t);
  const size = f.comparison.families[0].sizes.find((s) => s.size_px === 14);
  const profile = structuredClone(size.glyphs[0].profiles[0]);
  const mark = { id: "A-14", family_id: "fixture", family_name: "Fixture font", codepoint: 65,
    character: "A", size_px: 14, axes: { wght: 400 }, status: "pending",
    inspection: "Stroke continuity", description: "Lower junction <detail>.",
    canvas: size.canvas, profiles: [profile] };
  const unchanged = structuredClone(mark);
  unchanged.id = "A-16"; unchanged.size_px = 16;
  unchanged.profiles[0].current = unchanged.profiles[0].previous;
  unchanged.profiles[0].difference = unchanged.profiles[0].previous;
  f.comparison.families[0].sizes.find((s) => s.size_px === 16).glyphs[0].profiles[0] = structuredClone(unchanged.profiles[0]);
  f.comparison.attention = [mark, unchanged];
  await f.saveComparison();
  return f;
}

test("attention moves exact cases to scoped family/size cards and retains unchanged comparisons", async (t) => {
  const f = await attentionFixture(t);
  const comparison = (await createComparisonImporter(f.root).load())[0];
  assert.equal(comparison.attention.length, 2);
  const page = glyphPages([comparison]).find((p) => p.slug === "U0041");
  assert.equal(page.sizes.filter((s) => s.attention).length, 2);
  assert.equal(page.sizes.find((s) => s.anchor === "attention-A-16").axes.wght, 400);
  const scopedGroups = (view, size_px) => view.families[0].sizes.find((s) => s.size_px === size_px).attentionGroups;
  assert.deepEqual(scopedGroups(comparison, 14).map((g) => g.inspection), ["Stroke continuity"]);
  assert.deepEqual(scopedGroups(comparison, 16).map((g) => g.inspection), ["Stroke continuity"]);
  const html = await build(f.root, f.output);
  assert.match(html, /id="attention-fixture-14"/);
  assert.match(html, /id="attention-fixture-16"/);
  assert.match(html, /id="fixture-size-14"[\s\S]*?id="attention-fixture-14"[\s\S]*?id="fixture-size-16"[\s\S]*?id="attention-fixture-16"/);
  assert.match(html, /<h4 class="attention-heading"[^>]*>Attention<\/h4>/);
  assert.match(html, /<h5>Stroke continuity<\/h5>/);
  assert.match(html, /<strong>A<\/strong>/);
  assert.doesNotMatch(html, /Fixture font · A · 1[46] px/);
  assert.doesNotMatch(html, /These symbols need assessment|Diagnostic case|Attention · Pending assessment|wght 400/);
  assert.match(html, /Lower junction &lt;detail&gt;/);
  assert.match(html, /U0041\/#attention-A-14/);
  assert.match(html, /U0041\/#attention-A-16/);
  // The normal gray case still belongs to the ordinary list; the marked mono case does not.
  assert.doesNotMatch(html, /class="specimen-card glyph-link"[^>]*data-profile="mono_1bit"[^>]*href="\.\/01\/fixture\/U0041\/#size-14/);
  const symbol = await fs.readFile(path.join(f.output, "01/fixture/U0041/index.html"), "utf8");
  assert.match(symbol, /id="attention-A-16"/);
  assert.doesNotMatch(symbol, /wght 400|Pending assessment/);
  assert.match(symbol, /Lower junction &lt;detail&gt;/);
  f.comparison.attention[1].inspection = "Weight and contrast";
  f.comparison.attention[1].description = "";
  await f.saveComparison();
  const grouped = (await createComparisonImporter(f.root).load())[0];
  assert.deepEqual(scopedGroups(grouped, 14).map((g) => g.inspection), ["Stroke continuity"]);
  assert.deepEqual(scopedGroups(grouped, 16).map((g) => g.inspection), ["Weight and contrast"]);
  const concise = await build(f.root, f.output);
  assert.match(concise, /<h5>Weight and contrast<\/h5>/);
  assert.equal((concise.match(/class="attention-description"/g) ?? []).length, 1);
  f.comparison.attention = [f.comparison.attention[0]];
  await f.saveComparison();
  const scoped = await build(f.root, f.output);
  assert.match(scoped, /id="attention-fixture-14"/);
  assert.doesNotMatch(scoped, /id="attention-fixture-16"/);
  f.comparison.attention = [];
  await f.saveComparison();
  const cleared = await build(f.root, f.output);
  assert.doesNotMatch(cleared, /attention-block/);
  assert.doesNotMatch(await fs.readFile(path.join(f.output, "01/fixture/U0041/index.html"), "utf8"), /attention-A-16/);
});

test("attention annotations require an inspection type, valid identity, scope and image assets", async (t) => {
  const f = await attentionFixture(t);
  for (const change of [
    (m) => { m.attention[0].inspection = ""; },
    (m) => { m.attention[0].status = "accepted"; },
    (m) => { m.attention[0].id = "../escape"; },
    (m) => { m.attention[0].character = "B"; },
    (m) => { m.attention[0].family_id = "missing"; },
    (m) => { m.attention[0].profiles[0].current = null; },
    (m) => { m.attention.push(structuredClone(m.attention[0])); },
  ]) {
    const doc = structuredClone(f.comparison); change(doc);
    assert.throws(() => validateComparison(doc, f.entry));
  }
});

test("web rejects attention and ordinary comparisons outside the active specimen scope", async (t) => {
  const f = await attentionFixture(t);
  const original = structuredClone(f.comparison);
  for (const change of [
    (m) => { m.attention[0].size_px = 15; },
    (m) => { m.attention[0].axes.wght = 300; },
    (m) => { m.families[0].sizes[0].size_px = 15; },
    (m) => { m.families[0].sizes[0].axes.wght = 300; },
  ]) {
    Object.assign(f.comparison, structuredClone(original)); change(f.comparison);
    await f.saveComparison();
    await assert.rejects(() => build(f.root, f.output), /outside published preview scope/);
  }
});

test("attention links preserve profile and zoom under a hosting prefix", { skip: !browserAvailable }, async (t) => {
  const f = await attentionFixture(t); await build(f.root, f.output);
  const url = await serve(t, f.output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 390, height: 800 } });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${url}?profile=mono_1bit&zoom=4`);
  assert.equal(await page.locator(".attention-symbol:visible").count(), 2);
  assert.equal(await page.locator(".attention-block:visible").count(), 2);
  const link = page.locator('[data-attention-id="A-16"]');
  const destination = new URL(await link.getAttribute("href"));
  assert.ok(destination.pathname.startsWith("/preview/01/fixture/U0041/"));
  assert.equal(destination.hash, "#attention-A-16");
  assert.equal(destination.searchParams.get("profile"), "mono_1bit");
  assert.equal(destination.searchParams.get("zoom"), "4");
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.locator('input[value="gray_3bit"]').check();
  assert.equal(await page.locator(".attention-block:visible").count(), 0);
  assert.equal(await page.locator("#attention-fixture-14").isVisible(), false);
  assert.equal(await page.locator("#attention-fixture-16").isVisible(), false);
  await page.goto(destination.href);
  await page.waitForFunction(() => [...document.querySelectorAll("img")].filter((i) => i.closest(".specimen-card:not([hidden])")).every((i) => i.complete && i.naturalWidth));
  assert.equal(await page.locator("#attention-A-16").isVisible(), true);
  assert.match(await page.locator("#attention-A-16 .attention-note").innerText(), /Lower junction/);
  assert.deepEqual(errors, []);
});

test("impact statistics count repeated images per symbol, validate pixel counts, and switch output modes", async (t) => {
  const f = await comparisonFixture(t);
  let index = 0;
  for (const size of f.comparison.families[0].sizes) for (const glyph of size.glyphs) {
    const count = [1, 1, 1, 4][index++];
    const data = Buffer.from(Array.from({ length: 4 }, (_, i) => i < count ? [0, 96, 255, 255] : [255, 255, 255, 255]).flat());
    const bytes = PNG.sync.write({ width: 2, height: 2, data }, { colorType: 2, bitDepth: 8 });
    const sha256 = hash(bytes);
    glyph.profiles[0].difference = { path: `assets/${sha256}.png`, sha256 };
    f.assets.set(`assets/${sha256}.png`, bytes);
  }
  f.comparison.statistics = [
    { profile: "mono_1bit", same_symbols: 3, changed_symbols: 4, average_changed_pixels: 1.75, median_changed_pixels: 1 },
    { profile: "gray_3bit", same_symbols: 5, changed_symbols: 4, average_changed_pixels: 2, median_changed_pixels: 2 },
  ];
  await f.saveComparison();
  const [comparison] = await createComparisonImporter(f.root).load();
  assert.equal(comparison.statistics[0].changed_symbols, 4);
  assert.equal(comparison.statistics[0].averageLabel, "1.75");
  assert.equal(comparison.statistics[0].medianLabel, "1");
  const html = await build(f.root, f.output);
  assert.match(html, /Same symbols/);
  assert.match(html, /Average changed pixels<\/dt>/);
  assert.doesNotMatch(html, /Median changed pixels|per changed symbol|This is the active working output|Device-panel review|Unavailable symbols/);
  if (browserAvailable) {
    const url = await serve(t, f.output);
    const browser = await chromium.launch({ executablePath: browserPath, headless: true });
    t.after(() => browser.close());
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: "networkidle" });
    assert.equal(await page.locator('[data-impact-profile]:visible').count(), 1);
    assert.deepEqual(await page.locator('[data-impact-profile]:visible dd').allTextContents(), ["3", "4", "1.75"]);
    await page.getByRole("radio", { name: "3-bit", exact: true }).check();
    assert.equal(await page.locator('[data-impact-profile]:visible').count(), 1);
    assert.deepEqual(await page.locator('[data-impact-profile]:visible dd').allTextContents(), ["5", "4", "2"]);
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.locator('[data-impact-profile]:visible').getAttribute("data-impact-profile"), "gray_3bit");
    assert.deepEqual(await page.locator('[data-impact-profile]:visible dd').allTextContents(), ["5", "4", "2"]);
    await page.getByRole("radio", { name: "1-bit", exact: true }).check();
    assert.equal(await page.locator('[data-impact-profile]:visible').count(), 1);
    assert.deepEqual(await page.locator('[data-impact-profile]:visible dd').allTextContents(), ["3", "4", "1.75"]);
  }
  f.comparison.statistics[0].median_changed_pixels = 2;
  await f.saveComparison();
  await assert.rejects(() => createComparisonImporter(f.root).load(), /statistics differ/);
  f.comparison.statistics[0].median_changed_pixels = 1;
  f.comparison.statistics[0].same_symbols = -1;
  assert.throws(() => validateComparison(f.comparison, f.entry), /symbol counts/);
});

test("missing comparison images fail import and site builds; zero-change statistics remain meaningful", async (t) => {
  const f = await comparisonFixture(t);
  const profile = f.comparison.families[0].sizes[0].glyphs[0].profiles[0];
  const original = structuredClone(profile);
  for (const key of ["previous", "current", "difference"]) {
    Object.assign(profile, original, { [key]: null });
    await f.saveComparison();
    await assert.rejects(() => createComparisonImporter(f.root).load(), /Missing comparison glyph images: fixture, 16 px, mono_1bit, U\+0041/);
    await assert.rejects(() => build(f.root, f.output), /Missing comparison glyph images/);
  }

  for (const family of f.comparison.families) for (const size of family.sizes) size.glyphs = [];
  f.comparison.statistics = ["mono_1bit", "gray_3bit"].map((profile) => ({
    profile, same_symbols: 4, changed_symbols: 0, average_changed_pixels: 0, median_changed_pixels: 0,
  }));
  f.comparison.statistics[0].unavailable_symbols = 1;
  await f.saveComparison();
  await assert.rejects(() => createComparisonImporter(f.root).load(), /contains missing glyphs/);
  delete f.comparison.statistics[0].unavailable_symbols;
  await f.saveComparison();
  const [identical] = await createComparisonImporter(f.root).load();
  assert.equal(identical.statistics[0].sameLabel, "4");
  assert.equal(identical.statistics[0].averageLabel, "0");
  assert.equal(identical.statistics[0].medianLabel, "0");
  assert.equal(glyphPages([identical]).length, 0);
  const html = await build(f.root, f.output);
  assert.match(html, /Same symbols<\/dt><dd>4<\/dd>/);
  assert.match(html, /Changed symbols<\/dt><dd>0<\/dd>/);
  assert.doesNotMatch(html, /Unavailable symbols|excluded from pixel statistics/);
  delete f.comparison.statistics;
  await f.saveComparison();
  assert.match(await build(f.root, f.output), /Comparison statistics are unavailable/);
});

test("HTTP glyph links open new tabs, preserve mode/zoom, anchor the clicked size, and show aligned directional differences", { skip: !browserAvailable }, async (t) => {
  const f = await comparisonFixture(t);
  await build(f.root, f.output);
  const url = await serve(t, f.output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  let page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  const errors = [], failed = [];
  function watchPage(tab) {
    tab.on("pageerror", (error) => errors.push(error.message));
    tab.on("response", (response) => { if (response.status() >= 400 && !response.url().endsWith("favicon.ico")) failed.push(response.url()); });
  }
  watchPage(page);
  page.context().on("page", watchPage);
  const removedIndex = await page.request.get(`${url}01/`, { maxRedirects: 0 });
  assert.equal(removedIndex.status(), 404);
  assert.equal(removedIndex.headers().location, undefined);
  await page.goto(`${url}?profile=mono_1bit&zoom=1#family-fixture`, { waitUntil: "networkidle" });
  assert.equal(new URL(page.url()).pathname, "/preview/");
  assert.equal(new URL(page.url()).hash, "#family-fixture");
  assert.equal(await page.locator(".variant").textContent().then((text) => text.trim()), "reference → 001.01");
  assert.equal(await page.locator(".glyph-link:visible").count(), 4);
  assert.equal(await page.locator(".glyph-sheet").first().evaluate((sheet) => getComputedStyle(sheet).overflowX), "clip");
  assert.ok(await page.locator(".size-group").evaluateAll((groups) => groups.every((group) => {
    const sheet = group.querySelector(".glyph-sheet");
    const block = sheet.closest(".glyph-block");
    const sample = group.querySelector("figure.specimen-card");
    const blockStyle = getComputedStyle(block), sampleStyle = getComputedStyle(sample);
    const caption = getComputedStyle(block.querySelector("figcaption"));
    const sampleCaption = getComputedStyle(sample.querySelector("figcaption"));
    return group.lastElementChild === block && block.previousElementSibling.contains(sample)
      && blockStyle.borderTopWidth === "1px" && blockStyle.borderTopStyle === "solid"
      && blockStyle.borderTopColor === sampleStyle.borderTopColor
      && blockStyle.borderRadius === sampleStyle.borderRadius
      && blockStyle.backgroundColor === sampleStyle.backgroundColor
      && blockStyle.overflow === sampleStyle.overflow
      && caption.padding === sampleCaption.padding && caption.borderBottom === sampleCaption.borderBottom
      && block.getBoundingClientRect().width < group.getBoundingClientRect().width;
  })));
  assert.equal(await page.getByText("Select a symbol", { exact: false }).count(), 0);
  for (const [stop, zoom] of [[0, 1], [1, 2], [2, 3], [3, 4]]) {
    await page.locator("#zoom").fill(String(stop));
    const positions = await page.locator("#fixture-size-14 .glyph-link:visible").evaluateAll((links) => links.map((link) => {
      const rect = link.getBoundingClientRect(), style = getComputedStyle(link);
      return { left: rect.left, width: rect.width, padding: style.paddingLeft, border: style.borderLeftWidth };
    }));
    assert.equal(positions[0].width, 2 * zoom);
    assert.equal(positions[1].left, positions[0].left + positions[0].width);
    assert.ok(positions.every((p) => p.padding === "0px" && p.border === "0px"));
    assert.equal(await page.locator(".glyph-sheet").first().evaluate((sheet) => getComputedStyle(sheet).paddingLeft), `${8 * zoom}px`);
  }
  await page.getByRole("radio", { name: "3-bit", exact: true }).check();
  await page.locator("#zoom").fill("2");
  const mainPage = page;
  const mainUrl = page.url();
  [page] = await Promise.all([
    mainPage.waitForEvent("popup"),
    mainPage.locator('#fixture-size-16 .glyph-link[data-codepoint="65"]:visible').click(),
  ]);
  await page.waitForLoadState("networkidle");
  assert.equal(mainPage.url(), mainUrl);
  assert.equal(await page.evaluate(() => window.opener), null);
  assert.equal(new URL(page.url()).pathname, "/preview/01/fixture/U0041/");
  assert.equal(new URL(page.url()).hash, "#size-16");
  assert.equal(await page.getByRole("radio", { name: "3-bit", exact: true }).isChecked(), true);
  assert.equal(await page.locator("#zoom-value").textContent(), "4×");
  assert.equal(await page.locator(".specimen-card:visible").count(), 6);
  assert.deepEqual(await page.locator(".size-group").evaluateAll((groups) => groups.map((g) => g.id)), ["size-14", "size-16"]);
  const images = await page.locator(".specimen-card:visible img").evaluateAll((images) => images.map((i) => [i.getBoundingClientRect().width, i.getBoundingClientRect().height, getComputedStyle(i).imageRendering]));
  assert.ok(images.every(([w, h, rendering]) => w === 8 && h === 8 && rendering === "pixelated"));
  const diff = page.locator('#size-16 [data-kind="difference"][data-profile="gray_3bit"] img');
  const result = await page.request.get(await diff.getAttribute("src").then((src) => new URL(src, page.url()).href));
  const pixels = PNG.sync.read(await result.body()).data;
  assert.deepEqual([...pixels.subarray(0, 3)], [0, 96, 255]);
  assert.deepEqual([...pixels.subarray(4, 7)], [224, 32, 32]);
  assert.deepEqual([...pixels.subarray(8, 11)], [146, 146, 146]);
  await page.locator("#zoom").fill("0");
  await page.getByRole("radio", { name: "1-bit", exact: true }).check();
  await page.setViewportSize({ width: 360, height: 800 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.getByRole("link", { name: "All symbols", exact: true }).click();
  await page.waitForSelector("#zoom:not([disabled])");
  assert.equal(new URL(page.url()).pathname, "/preview/");
  assert.equal(await page.locator("#zoom-value").textContent(), "3×");
  assert.equal(await page.getByRole("radio", { name: "1-bit", exact: true }).isChecked(), true);
  assert.deepEqual(await page.evaluate(() => [localStorage.getItem("font-preview.zoom.specimen"), localStorage.getItem("font-preview.zoom.glyph")]), ["3", "1"]);
  [page] = await Promise.all([
    page.waitForEvent("popup"),
    page.locator('#fixture-size-14 .glyph-link[data-codepoint="65"]:visible').click(),
  ]);
  await page.waitForLoadState("networkidle");
  assert.equal(await page.locator("#zoom-value").textContent(), "1×");
  assert.deepEqual(errors, []);
  assert.deepEqual(failed, []);
  const context = await browser.newContext({ javaScriptEnabled: false });
  const staticPage = await context.newPage();
  await staticPage.goto(`${url}01/fixture/U0041/`);
  assert.equal(await staticPage.locator(".specimen-card:visible").count(), 6);
  assert.equal(await staticPage.locator("#zoom").isDisabled(), true);
  await context.close();
});

test("index publishes tweaks under the same iteration identity and removes obsolete review endpoints", async (t) => {
  const f = await comparisonFixture(t);
  // Publish a newer package within the same open iteration, retaining the old immutable package.
  const latest = structuredClone(JSON.parse(await fs.readFile(path.join(f.root, "candidate-test/manifest.json"))));
  latest.variant.id = "latest-test";
  latest.variant.version = "001.01";
  await fs.cp(path.join(f.root, "candidate-test"), path.join(f.root, "latest-test"), { recursive: true });
  await fs.writeFile(path.join(f.root, "latest-test/manifest.json"), JSON.stringify(latest));
  await fs.writeFile(path.join(f.root, "published.json"), JSON.stringify({ schema_version: "specimen-publication-v1", variants: {
    reference: "reference-test", "iteration-01": "latest-test",
  } }));
  f.comparison.current.package_id = "latest-test";
  f.comparison.current.label = "001.01";
  await f.saveComparison();
  await fs.mkdir(path.join(f.output, "reviews/obsolete"), { recursive: true });
  await fs.writeFile(path.join(f.output, "reviews/obsolete/index.html"), "obsolete");
  const html = await build(f.root, f.output);
  assert.match(html, /<span>001\.01<\/span>/);
  assert.match(html, /<p class="variant"><span>reference<\/span> → <span>001\.01<\/span><\/p>/);
  assert.doesNotMatch(html, /reviews\//);
  const url = await serve(t, f.output);
  assert.equal((await fetch(`${url}reviews/obsolete/`)).status, 404);
  f.comparison.previous.package_id = "candidate-test";
  f.comparison.previous.label = "001.01";
  await f.saveComparison();
  await assert.rejects(build(f.root, f.output), /Comparison must show the selected/);
});
