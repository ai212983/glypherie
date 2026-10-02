import { promises as fs } from "node:fs";
import path from "node:path";
import { atomicWrite, check, hash, isHash, isId, regularFile } from "./specimens.js";

// Publishes per-family interactive specimens: real source font bytes plus the
// render defaults and control ranges the preview page needs. Output stays in
// out/web (interactive.json plus interactive-fonts/); nothing here affects the
// published PNG assessment.
export const INTERACTIVE_SCHEMA = "web-interactive-v1";
export const FONT_DIR = "interactive-fonts";
const MAX_FONT_BYTES = 32 * 1024 * 1024;
const FONT_EXTENSIONS = new Set(["ttf", "otf"]);
const AXIS_TAG = /^[\x20-\x7e]{4}$/;

// Resolve a specimens.json `font` reference to a file inside the repository.
// Returns the absolute path, or null when the reference escapes the repo,
// uses an unsupported type, or has no usable file extension. Never throws for
// bad input; callers report the family as unavailable.
export function resolveFontFile(configDir, repoRoot, fontRef) {
  if (typeof fontRef !== "string" || !fontRef) return null;
  const resolved = path.resolve(configDir, fontRef);
  if (path.relative(repoRoot, resolved).startsWith("..")) return null;
  const extension = path.extname(resolved).slice(1).toLowerCase();
  if (!FONT_EXTENSIONS.has(extension)) return null;
  return resolved;
}

function renderDefaults(configProfiles) {
  const pick = (bits, key, fallback) => {
    const profile = (configProfiles ?? []).find((candidate) => candidate?.output_bits === bits);
    return Number.isFinite(profile?.[key]) ? profile[key] : fallback;
  };
  return {
    hinting: "auto",
    mono_threshold: pick(1, "mono_threshold", 128),
    gray_gamma: pick(3, "gray_gamma", 1.0),
  };
}

function controlAxes(metadata) {
  const axes = Array.isArray(metadata?.axes) ? metadata.axes : [];
  return axes
    .filter((axis) => axis && AXIS_TAG.test(axis.tag) && [axis.min, axis.default, axis.max].every(Number.isFinite)
      && axis.min <= axis.default && axis.default <= axis.max && axis.hidden !== true)
    .map((axis) => ({
      tag: axis.tag,
      name: typeof axis.name === "string" && axis.name.trim() ? axis.name : axis.tag,
      min: axis.min,
      default: axis.default,
      max: axis.max,
      step: [axis.min, axis.default, axis.max].every(Number.isInteger) ? 1 : 0.1,
    }));
}

function defaultState(family) {
  const group = [...(family.sizes ?? [])].sort((a, b) => a.size_px - b.size_px)[0] ?? null;
  const text = group?.items?.[0]?.text?.split("\n")[0] ?? "";
  return {
    size_px: Number.isFinite(group?.size_px) ? group.size_px : 16,
    axes: { ...(group?.axes ?? {}) },
    text: text.slice(0, 200),
  };
}

// Pure assembly from already-loaded inputs: manifest view families (id, name,
// source_sha256, metadata, sizes with axes/text) plus the generator config's
// family font references. `readFont` is injectable for tests; production
// passes a bounded regular-file read.
export async function buildInteractive({ viewFamilies, configFamilies, profiles, configDir, repoRoot, readFont }) {
  const configured = new Map((configFamilies ?? []).map((family) => [family?.id, family?.font]));
  const defaults = renderDefaults(profiles);
  const families = [];
  const fonts = [];
  for (const family of viewFamilies ?? []) {
    if (!isId(family.id)) continue;
    const state = defaultState(family);
    const entry = {
      id: family.id, name: family.name, available: false, axes: controlAxes(family.metadata),
      default_size_px: state.size_px, default_axes: state.axes, sample_text: state.text, render: defaults,
    };
    const file = resolveFontFile(configDir, repoRoot, configured.get(family.id));
    if (!file) {
      families.push({ ...entry, reason: "Font source is not configured for interactive preview." });
      continue;
    }
    let bytes;
    try {
      bytes = await readFont(file);
    } catch {
      families.push({ ...entry, reason: "Interactive preview is unavailable for this font." });
      continue;
    }
    if (hash(bytes) !== family.source_sha256) {
      families.push({ ...entry, reason: "Interactive preview is unavailable for this font." });
      continue;
    }
    const extension = path.extname(file).slice(1).toLowerCase();
    const target = `${FONT_DIR}/${family.id}.${extension}`;
    fonts.push({ target, bytes });
    families.push({ ...entry, available: true, fontUrl: `./${target}`, source_sha256: family.source_sha256 });
  }
  return { doc: { schema_version: INTERACTIVE_SCHEMA, families }, fonts };
}

export async function boundedFontFile(file, repoRoot) {
  // Resolve symlinks in every path component before the containment check so
  // a symlinked parent cannot smuggle the read outside the repository.
  const [realFile, realRoot] = await Promise.all([fs.realpath(path.resolve(file)), fs.realpath(repoRoot)]);
  if (path.relative(realRoot, realFile).startsWith("..")) throw new Error("Font source escapes the repository.");
  const stat = await regularFile(realFile, MAX_FONT_BYTES);
  check(stat.isFile(), "Expected a regular font file.");
  return fs.readFile(realFile);
}

export function validateInteractive(doc) {
  check(doc?.schema_version === INTERACTIVE_SCHEMA && Array.isArray(doc.families), "Unsupported interactive preview format.");
  for (const family of doc.families) {
    check(family && isId(family.id), "Invalid interactive family.");
    if (!family.available) continue;
    check(isHash(family.source_sha256) && typeof family.fontUrl === "string"
      && family.fontUrl === `./${FONT_DIR}/${family.id}.${path.extname(family.fontUrl).slice(1).toLowerCase()}`
      && Number.isFinite(family.default_size_px), "Invalid interactive family source.");
  }
}

export async function publishInteractive(result, output) {
  const doc = result?.doc ?? { schema_version: INTERACTIVE_SCHEMA, families: [] };
  validateInteractive(doc);
  const seen = new Set();
  for (const font of result?.fonts ?? []) {
    check(!seen.has(font.target) && font.target.startsWith(`${FONT_DIR}/`), "Invalid interactive font target.");
    seen.add(font.target);
    await atomicWrite(path.join(output, font.target), font.bytes);
  }
  await atomicWrite(path.join(output, "interactive.json"), Buffer.from(JSON.stringify(doc)));
}
