import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { createSpecimenImporter, validateManifest } from "../lib/specimens.js";
import { build, fixture, hash, png } from "./helpers.js";

test("imports the selected package, preserving family/item order and sorting sizes", async (t) => {
  const f = await fixture(t);
  const group = structuredClone(f.manifest.families[0].sizes[0]);
  group.size_px = 14;
  for (const item of group.items) item.id += "-14";
  f.manifest.families[0].sizes.push(group);
  await f.save();
  const result = await createSpecimenImporter(f.root).load();
  assert.equal(result.state, "ready");
  assert.equal(result.variantLabel, "reference");
  assert.deepEqual(result.families[0].sizes.map((s) => s.size_px), [14, 16]);
  assert.deepEqual(result.families[0].sizes[1].items.map((i) => i.profileLabel), ["1-bit", "3-bit"]);
});

test("previews an exact package without changing the active pointer", async (t) => {
  const f = await fixture(t);
  const before = await fs.readFile(path.join(f.root, "active.json"));
  const importer = createSpecimenImporter(f.root);
  const result = await importer.load(f.pointer.variant_id);
  assert.equal(result.state, "ready");
  assert.equal(result.proposal, true);
  assert.deepEqual(await fs.readFile(path.join(f.root, "active.json")), before);
  assert.equal((await importer.load()).proposal, false);
  assert.equal((await importer.load("../escape")).state, "error");
  assert.equal((await importer.load("missing-package")).state, "error");
});

test("copies the exact selected pointer, manifest, and image bytes", async (t) => {
  const f = await fixture(t);
  const importer = createSpecimenImporter(f.root);
  const result = await importer.load();
  await importer.publish(result, f.output);
  for (const relative of ["active.json", f.pointer.manifest, `${f.pointer.variant_id}/${f.manifest.families[0].sizes[0].items[0].image.path}`]) {
    assert.deepEqual(await fs.readFile(path.join(f.output, "content", relative)), await fs.readFile(path.join(f.root, relative)));
  }
  const file = path.join(f.output, "content", "active.json");
  const before = (await fs.stat(file)).mtimeMs;
  await importer.publish(result, f.output);
  assert.equal((await fs.stat(file)).mtimeMs, before);
});

test("a grayscale-only package defaults to its available mode", async (t) => {
  const f = await fixture(t);
  f.manifest.profiles = [f.manifest.profiles[1]];
  f.manifest.families[0].sizes[0].items = [f.manifest.families[0].sizes[0].items[1]];
  await f.save();
  const result = await createSpecimenImporter(f.root).load();
  assert.equal(result.defaultProfile, "gray_3bit");
  assert.deepEqual(result.profiles, [{ id: "gray_3bit", label: "3-bit" }]);
  assert.equal(result.families[0].initiallyVisible, true);
  assert.equal(result.families[0].sizes[0].items[0].initiallyVisible, true);
  const html = await build(f.root, f.output);
  assert.match(html, /value="gray_3bit" checked/);
  assert.doesNotMatch(html, /value="mono_1bit"/);
});

test("reuses unchanged validation and notices changed image contents", async (t) => {
  const f = await fixture(t);
  const importer = createSpecimenImporter(f.root);
  const first = await importer.load();
  assert.equal(await importer.load(), first);
  await fs.writeFile(f.imagePath, Buffer.from("damaged"));
  const failed = await importer.load();
  assert.equal(failed.state, "error");
  assert.match(failed.message, /checksum/);
});

test("missing pointer and missing source directory are empty states", async (t) => {
  const f = await fixture(t);
  assert.equal((await createSpecimenImporter(path.join(f.root, "missing")).load()).state, "empty");
  await fs.unlink(path.join(f.root, "active.json"));
  assert.equal((await createSpecimenImporter(f.root).load()).state, "empty");
});

test("malformed and incomplete selected packages produce errors, with no fallback", async (t) => {
  const f = await fixture(t);
  await fs.writeFile(path.join(f.root, "active.json"), "{");
  assert.equal((await createSpecimenImporter(f.root).load()).state, "error");
  await f.save();
  await fs.unlink(f.imagePath);
  const result = await createSpecimenImporter(f.root).load();
  assert.equal(result.state, "error");
  assert.equal(result.selectedVariant, "reference-test");
});

test("metadata boundary rejects unsafe paths, duplicate identities, and invalid outcomes", async (t) => {
  const f = await fixture(t);
  const mutations = [
    (m, p) => { p.variant_id = "../outside"; },
    (m, p) => { p.manifest = "../manifest.json"; },
    (m) => { m.variant.id = "different"; },
    (m) => { m.variant.version = "unexpected"; },
    (m) => { m.variant.composition_sha256 = "invalid"; },
    (m) => { m.profiles[0].output_bits = 3; },
    (m) => { m.families[0].sizes[0].items[0].profile = "missing"; },
    (m) => { m.families[0].sizes[0].items[1].id = m.families[0].sizes[0].items[0].id; },
    (m) => { m.families[0].sizes.push(structuredClone(m.families[0].sizes[0])); },
    (m) => { m.families[0].sizes[0].axes = []; },
    (m) => { m.families[0].sizes[0].thumbnail.width_px = 0; },
    (m) => { m.families[0].sizes[0].items[0].image.path = "../outside.png"; },
    (m) => { m.families[0].sizes[0].items[0].outcome = "unknown"; },
    (m) => { m.families[0].sizes[0].items[0].reason = "unexpected"; },
  ];
  for (const mutate of mutations) {
    const manifest = structuredClone(f.manifest);
    const pointer = structuredClone(f.pointer);
    mutate(manifest, pointer);
    assert.throws(() => validateManifest(manifest, pointer));
  }
});

test("rejects symlinked content even when it points within the package", async (t) => {
  const f = await fixture(t);
  const actual = f.imagePath + ".actual";
  await fs.rename(f.imagePath, actual);
  await fs.symlink(actual, f.imagePath);
  const result = await createSpecimenImporter(f.root).load();
  assert.equal(result.state, "error");
  assert.match(result.message, /regular/);
});

test("checks decoded PNG levels as well as dimensions and checksums", async (t) => {
  const f = await fixture(t);
  const invalid = png([127, 255, 255, 0]);
  const imageHash = hash(invalid);
  for (const item of f.manifest.families[0].sizes[0].items) item.image = { path: `assets/${imageHash}.png`, sha256: imageHash };
  await fs.writeFile(path.join(f.packageDir, "assets", `${imageHash}.png`), invalid);
  await f.save();
  const result = await createSpecimenImporter(f.root).load();
  assert.equal(result.state, "error");
  assert.match(result.message, /pixel levels/);
  f.manifest.families[0].sizes[0].thumbnail.width_px = 3;
  await f.save();
  assert.match((await createSpecimenImporter(f.root).load()).message, /dimensions/);
});

test("failure items retain outcomes, reasons, and dimensions in the importer view", async (t) => {
  const f = await fixture(t);
  for (const [i, item] of f.manifest.families[0].sizes[0].items.entries()) {
    delete item.image;
    item.outcome = i ? "unsupported" : "failed";
    item.reason = "Sample needs investigation.";
  }
  await f.save();
  const result = await createSpecimenImporter(f.root).load();
  assert.equal(result.state, "ready");
  assert.equal(result.assets.size, 0);
  const group = result.families[0].sizes[0];
  assert.deepEqual([group.thumbnail.width_px, group.thumbnail.height_px], [2, 2]);
  assert.deepEqual(group.items.map((item) => [item.outcome, item.reason]), [
    ["failed", "Sample needs investigation."],
    ["unsupported", "Sample needs investigation."],
  ]);
  const html = await build(f.root, f.output);
  assert.doesNotMatch(html, /specimen-card|sample-failure|<figcaption>/);
});

test("iteration labels are human-facing and metadata is HTML escaped", async (t) => {
  const f = await fixture(t);
  f.manifest.variant.kind = "iteration";
  f.manifest.variant.version = "Iteration 2 <test>";
  f.manifest.families[0].name = '<script>alert("family")</script>';
  f.manifest.families[0].sizes[0].items[0].label = "Reading <script>bad</script>";
  await f.save();
  const html = await build(f.root, f.output);
  assert.match(html, /Iteration 2 &lt;test&gt;/);
  assert.match(html, /&lt;script&gt;alert/);
  assert.doesNotMatch(html, /<script>alert/);
  assert.doesNotMatch(html.replace(/<[^>]*>/g, ""), /reference-test|aaaaaaaaaaaaaaaa/);
});

test("watch-style rebuilds reload the active content", async (t) => {
  const f = await fixture(t);
  const { default: Eleventy } = await import("@11ty/eleventy");
  const { configureWeb } = await import("../eleventy.config.js");
  const { pageRoot } = await import("./helpers.js");
  const eleventy = new Eleventy(pageRoot, f.output, { configPath: false, quietMode: true, config: (config) => configureWeb(config, { specimenRoot: f.root }) });
  await eleventy.write();
  f.manifest.families[0].name = "Updated family";
  await f.save();
  await eleventy.restart();
  await eleventy.init();
  await eleventy.write();
  const html = await fs.readFile(path.join(f.output, "index.html"), "utf8");
  assert.match(html, /Updated family/);
  assert.doesNotMatch(html, /Fixture font/);
});

test("empty and invalid imports build visible states and remove the served selection", async (t) => {
  const f = await fixture(t);
  await build(f.root, f.output);
  await fs.unlink(path.join(f.root, "active.json"));
  assert.match(await build(f.root, f.output), /No generated specimens yet/);
  await assert.rejects(fs.stat(path.join(f.output, "content", "active.json")), { code: "ENOENT" });
  await f.save();
  await fs.writeFile(f.imagePath, "bad PNG");
  const html = await build(f.root, f.output);
  assert.match(html, /Specimens could not be loaded/);
  assert.doesNotMatch(html, /<img /);
});
