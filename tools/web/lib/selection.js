import { promises as fs } from "node:fs";
import path from "node:path";
import { check, fields, isId, regularFile, directory, validateManifest } from "./specimens.js";

export function selectPreview(variants) {
  const references = variants.filter((variant) => variant.kind === "reference");
  check(references.length <= 1, "Preview requires a unique reference variant.");
  const versions = new Set();
  const iterations = variants.filter((variant) => variant.kind === "iteration").map((variant) => {
    check(typeof variant.version === "string" && /^[0-9]+\.[0-9]+$/.test(variant.version), "Iteration version must be numeric revision.iteration.");
    const key = variant.version.split(".").map(Number);
    check(key.every((n) => Number.isInteger(n) && n > 0 && n <= 4294967295), "Invalid revision or iteration number.");
    check(!versions.has(key.join(".")), "Duplicate revision/iteration version.");
    versions.add(key.join("."));
    return { ...variant, key };
  }).sort((a, b) => a.key[0] - b.key[0] || a.key[1] - b.key[1]);
  const baseline = iterations.findLast((variant) => variant.renderer === "baseline");
  check(baseline || !iterations.length || !variants.some((variant) => variant.renderer), "Explicit working preview requires an approved baseline.");
  const candidate = baseline && iterations.findLast((variant) => variant.renderer === "candidate"
    && (variant.key[0] > baseline.key[0] || variant.key[0] === baseline.key[0] && variant.key[1] > baseline.key[1]));
  const current = candidate || baseline || iterations.at(-1) || references[0];
  check(current, "No preview variants.");
  const previous = baseline ? candidate ? baseline : references[0] : iterations.length
    ? iterations.findLast((variant) => variant.key[0] < current.key[0]) ?? references[0]
    : null;
  check(!iterations.length || previous, "First revision requires reference for comparison.");
  return { current, previous };
}

export async function loadPreviewSelection(root) {
  const file = path.join(root, "published.json");
  try { await regularFile(file, 1024 * 1024); } catch (error) {
    if (error.code === "ENOENT") return null; // Single-package exports have only active.json.
    throw error;
  }
  const published = JSON.parse(await fs.readFile(file));
  fields(published, ["schema_version", "variants"]);
  check(published.schema_version === "specimen-publication-v1", "Unsupported specimen publication.");
  check(published.variants && typeof published.variants === "object" && !Array.isArray(published.variants), "Invalid specimen publication variants.");
  const variants = [];
  const ids = new Set();
  for (const [logical, id] of Object.entries(published.variants)) {
    check(isId(logical) && isId(id) && id.length <= 193 && !ids.has(id), "Invalid published package identity.");
    ids.add(id);
    await directory(path.join(root, id));
    const manifestPath = path.join(root, id, "manifest.json");
    await regularFile(manifestPath, 4 * 1024 * 1024);
    const manifest = JSON.parse(await fs.readFile(manifestPath));
    validateManifest(manifest, { schema_version: "web-active-v1", variant_id: id, manifest: `${id}/manifest.json` });
    variants.push(manifest.variant);
  }
  return selectPreview(variants);
}
