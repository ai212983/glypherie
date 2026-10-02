import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { previewRoles, selectPreview } from "../lib/selection.js";
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

test("preview roles follow variant metadata, never revision numbers", () => {
  const reference = { id: "reference", kind: "reference", version: null, renderer: "reference" };
  const baseline = { id: "approved", kind: "iteration", version: "001.01", renderer: "baseline" };
  for (const version of ["001.02", "002.01", "100.500"]) {
    const candidate = { id: "working", kind: "iteration", version, renderer: "candidate" };
    assert.deepEqual(previewRoles({ current: candidate, previous: baseline }), {
      latest: { role: "candidate", label: version },
      previous: { role: "baseline", label: "001.01" },
    });
  }
  assert.deepEqual(previewRoles({ current: baseline, previous: reference }), {
    latest: { role: "baseline", label: "001.01" },
    previous: { role: "reference", label: "Reference" },
  });
  assert.equal(previewRoles({ current: reference, previous: null }), null);
  assert.equal(previewRoles(null), null);
  assert.deepEqual(previewRoles({
    current: { id: "old", kind: "iteration", version: "000.09" },
    previous: reference,
  }), {
    latest: { role: "baseline", label: "000.09" },
    previous: { role: "reference", label: "Reference" },
  });
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
