import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { selectPreview } from "../lib/selection.js";
import { createSpecimenImporter } from "../lib/specimens.js";
import { build, fixture } from "./helpers.js";

const reference = { id: "reference", kind: "reference", version: null };
const iteration = (id, version) => ({ id, kind: "iteration", version });

test("latest first-revision iteration compares with reference, independent of list order", () => {
  const selected = selectPreview([iteration("new", "001.02"), reference, iteration("old", "001.01")]);
  assert.equal(selected.current.id, "new");
  assert.equal(selected.previous.id, "reference");
});

test("revision and iteration sorting is numeric and baseline skips iterations in the current revision", () => {
  const selected = selectPreview([reference, iteration("a", "9.10"), iteration("b", "9.2"), iteration("c", "10.2"), iteration("d", "10.10")]);
  assert.equal(selected.current.id, "d");
  assert.equal(selected.previous.id, "a");
  assert.equal(selectPreview([reference]).previous, null);
  assert.throws(() => selectPreview([iteration("a", "1.1"), iteration("b", "001.01"), reference]), /Duplicate/);
  for (const version of ["iteration-1", "1.2.3", "0.1", "1.0", "1.-1", "4294967296.1"]) {
    assert.throws(() => selectPreview([reference, iteration("invalid", version)]));
  }
});

async function publishedFixture(t) {
  const f = await fixture(t);
  const variants = { reference: f.pointer.variant_id };
  for (const [id, version] of [["old", "001.01"], ["new", "001.02"]]) {
    await fs.cp(f.packageDir, path.join(f.root, id), { recursive: true });
    const manifest = structuredClone(f.manifest);
    manifest.variant = { ...manifest.variant, ...iteration(id, version) };
    await fs.writeFile(path.join(f.root, id, "manifest.json"), JSON.stringify(manifest));
    variants[id] = id;
  }
  await fs.writeFile(path.join(f.root, "published.json"), JSON.stringify({ schema_version: "specimen-publication-v1", variants }));
  return f;
}

test("published versions override a stale active pointer; missing latest content does not fall back", async (t) => {
  const f = await publishedFixture(t);
  const before = await fs.readFile(path.join(f.root, "active.json"));
  const importer = createSpecimenImporter(f.root);
  const selected = await importer.load();
  assert.equal(selected.state, "ready");
  assert.equal(selected.variantLabel, "001.02");
  assert.equal(selected.proposal, false);
  assert.equal(selected.selection.previous.id, "reference-test");
  assert.deepEqual(await fs.readFile(path.join(f.root, "active.json")), before);
  await fs.rm(path.join(f.root, "new"), { recursive: true });
  assert.equal((await importer.load()).state, "error");
});

test("index rejects missing or stale comparisons for the latest iteration", async (t) => {
  const f = await publishedFixture(t);
  await assert.rejects(build(f.root, f.output), /Comparison must show the selected/);
});

 test("renderer roles compare every working version with the approved baseline", () => {
 const baseline = {...iteration("approved", "001.01"), renderer: "baseline"};
 assert.equal(selectPreview([reference, baseline]).previous.id, "reference");
 for(const version of ["001.02", "002.01", "100.500"]){
 const candidate = {...iteration("working", version), renderer: "candidate"};
 const selected = selectPreview([candidate, reference, baseline]);
 assert.equal(selected.current.id,"working");
 assert.equal(selected.previous.id,"approved");
 assert.equal(selectPreview([candidate, baseline]).previous.id,"approved");
 assert.throws(() => selectPreview([candidate, reference]), /approved baseline/);
 }
 });
