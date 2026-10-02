import { createHash, randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";
import { loadPreviewSelection } from "./selection.js";

const MAX_PIXELS = 16 * 1024 * 1024;
const profileLabels = { mono_1bit: "1-bit", gray_3bit: "3-bit" };
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const isHash = (value) => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const isId = (value) => typeof value === "string" && /^[A-Za-z0-9_-]+$/.test(value);
const isText = (value) => typeof value === "string" && value.trim().length > 0;

export { check, fields, nonemptyArray, hash, isHash, isId, isText, regularFile, directory, atomicWrite };

function check(condition, message) {
  if (!condition) throw new Error(message);
}

function fields(value, required, optional = []) {
  check(value && typeof value === "object" && !Array.isArray(value), "Expected an object.");
  check(required.every((key) => Object.hasOwn(value, key)), "Required metadata is missing.");
  check(Object.keys(value).every((key) => required.includes(key) || optional.includes(key)), "Unexpected metadata field.");
}

function nonemptyArray(value, label) {
  check(Array.isArray(value) && value.length > 0, `${label} must contain records.`);
}

export function validateManifest(manifest, pointer) {
  fields(pointer, ["schema_version", "variant_id", "manifest"]);
  check(pointer.schema_version === "web-active-v1", "Unsupported active selection format.");
  check(isId(pointer.variant_id) && pointer.variant_id.length <= 193, "Invalid active variant identity.");
  check(pointer.manifest === `${pointer.variant_id}/manifest.json`, "Active manifest path is invalid.");
  fields(manifest, ["schema_version", "variant", "profiles", "families"]);
  check(manifest.schema_version === "web-specimens-v1", "Unsupported specimen format.");
  fields(manifest.variant, ["id", "kind", "version", "generation_sha256", "composition_sha256"], ["renderer"]);
  const variant = manifest.variant;
  check(variant.renderer === undefined || ["reference", "baseline", "candidate"].includes(variant.renderer), "Invalid renderer role.");
  check(variant.renderer === undefined || (variant.kind === "reference") === (variant.renderer === "reference"), "Renderer role differs from package kind.");
  check(variant.id === pointer.variant_id, "The package differs from the active selection.");
  check((variant.kind === "reference" && variant.version === null)
    || (variant.kind === "iteration" && isText(variant.version)), "Invalid renderer version.");
  check(isHash(variant.generation_sha256) && isHash(variant.composition_sha256), "Invalid render identity.");
  nonemptyArray(manifest.profiles, "Profiles");
  const profiles = new Map();
  for (const profile of manifest.profiles) {
    fields(profile, ["id", "output_bits"]);
    check((profile.id === "mono_1bit" && profile.output_bits === 1)
      || (profile.id === "gray_3bit" && profile.output_bits === 3), "Unsupported output profile.");
    check(!profiles.has(profile.id), "Duplicate output profile.");
    profiles.set(profile.id, profile.output_bits);
  }
  nonemptyArray(manifest.families, "Families");
  const families = new Set();
  const items = new Set();
  for (const family of manifest.families) {
    fields(family, ["id", "name", "source_sha256", "sizes"]);
    check(isId(family.id) && isText(family.name) && isHash(family.source_sha256), "Invalid font family metadata.");
    check(!families.has(family.id), "Duplicate font family.");
    families.add(family.id);
    nonemptyArray(family.sizes, "Sizes");
    const sizes = new Set();
    for (const group of family.sizes) {
      fields(group, ["size_px", "axes", "thumbnail", "items"]);
      check(Number.isFinite(group.size_px) && group.size_px >= 1 && group.size_px <= 512
        && !sizes.has(group.size_px), `Invalid or duplicate size for ${family.name}.`);
      sizes.add(group.size_px);
      check(group.axes && typeof group.axes === "object" && !Array.isArray(group.axes)
        && Object.entries(group.axes).every(([tag, value]) => /^[\x20-\x7e]{4}$/.test(tag)
          && Number.isFinite(value)), `Invalid axes for ${family.name}.`);
      fields(group.thumbnail, ["width_px", "height_px"]);
      const { width_px: width, height_px: height } = group.thumbnail;
      check(Number.isSafeInteger(width) && Number.isSafeInteger(height) && width > 0 && height > 0
        && width * height <= MAX_PIXELS, `Invalid specimen dimensions for ${family.name}.`);
      nonemptyArray(group.items, "Samples");
      for (const item of group.items) {
        fields(item, ["id", "profile", "label", "text", "outcome"], ["image", "reason"]);
        check(isText(item.id) && isText(item.label) && isText(item.text)
          && !items.has(item.id), "Invalid or duplicate sample metadata.");
        items.add(item.id);
        check(profiles.has(item.profile), "Sample refers to an unknown output profile.");
        if (item.outcome === "rendered") {
          fields(item.image, ["path", "sha256"]);
          check(isHash(item.image.sha256) && item.image.path === `assets/${item.image.sha256}.png`
            && !Object.hasOwn(item, "reason"), "Invalid specimen image reference.");
        } else {
          check(["failed", "unsupported"].includes(item.outcome) && isText(item.reason)
            && !Object.hasOwn(item, "image"), "Invalid sample outcome.");
        }
      }
    }
  }
}

async function regularFile(file, maxBytes = 64 * 1024 * 1024) {
  const stat = await fs.lstat(file);
  check(stat.isFile() && stat.size <= maxBytes, "Expected a regular, bounded content file.");
  return stat;
}

async function directory(dir) {
  check((await fs.lstat(dir)).isDirectory(), "Expected a content directory, not a link.");
}

function validatePng(bytes, group, bits, label) {
  check(bytes.length >= 33 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
    && bytes.readUInt32BE(8) === 13 && bytes.toString("ascii", 12, 16) === "IHDR", `Invalid PNG for ${label}.`);
  check(bytes.readUInt32BE(16) === group.thumbnail.width_px
    && bytes.readUInt32BE(20) === group.thumbnail.height_px
    && bytes[24] === 8 && bytes[25] === 0, `PNG dimensions or grayscale format differ for ${label}.`);
  const image = PNG.sync.read(bytes, { checkCRC: true });
  const levels = (1 << bits) - 1;
  const palette = new Set(Array.from({ length: levels + 1 }, (_, q) => 255 - Math.round(q * 255 / levels)));
  for (let i = 0; i < image.data.length; i += 4) {
    check(palette.has(image.data[i]) && image.data[i] === image.data[i + 1]
      && image.data[i] === image.data[i + 2] && image.data[i + 3] === 255, `Unexpected pixel levels for ${label}.`);
  }
}

function view(manifest, pointer) {
  const defaultProfile = manifest.profiles.find((profile) => profile.id === "mono_1bit")?.id
    ?? manifest.profiles[0].id;
  return {
    state: "ready",
    proposal: false,
    variantLabel: manifest.variant.kind === "reference" ? "reference" : manifest.variant.version,
    defaultProfile,
    profiles: manifest.profiles.map((profile) => ({ id: profile.id, label: profileLabels[profile.id] })),
    families: manifest.families.map((family) => ({
      id: family.id,
      name: family.name,
      initiallyVisible: family.sizes.some((group) => group.items.some((item) => item.profile === defaultProfile)),
      sizes: [...family.sizes].sort((a, b) => a.size_px - b.size_px).map((group) => ({
        ...group,
        initiallyVisible: group.items.some((item) => item.profile === defaultProfile),
        items: group.items.map((item) => ({
          ...item,
          initiallyVisible: item.profile === defaultProfile,
          profileLabel: profileLabels[item.profile],
          imageUrl: item.image ? `./content/${pointer.variant_id}/${item.image.path}` : null,
        })),
      })),
    })),
  };
}

async function atomicWrite(file, bytes) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  await directory(path.dirname(file));
  try {
    await regularFile(file);
    if ((await fs.readFile(file)).equals(bytes)) return;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const temp = `${file}.${randomUUID()}.tmp`;
  try {
    await fs.writeFile(temp, bytes, { flag: "wx" });
    await fs.rename(temp, file);
  } finally {
    await fs.rm(temp, { force: true });
  }
}

export function createSpecimenImporter(root) {
  let cached = null;
  return {
    async load(selectedVariant = null) {
      let pointer;
      try {
        await directory(root);
        const pointerPath = path.join(root, "active.json");
        const selection = selectedVariant === null ? await loadPreviewSelection(root) : null;
        const selectedId = selectedVariant ?? selection?.current.id ?? null;
        try {
          if (selectedId !== null) {
            check(isId(selectedId) && selectedId.length <= 193, "Invalid preview variant identity.");
          } else {
            await regularFile(pointerPath, 4096);
          }
        } catch (error) {
          if (error.code === "ENOENT") return { state: "empty", families: [], variantLabel: null };
          throw error;
        }
        const pointerBytes = selectedId === null ? await fs.readFile(pointerPath) : Buffer.from(JSON.stringify({
          schema_version: "web-active-v1", variant_id: selectedId, manifest: `${selectedId}/manifest.json`,
        }));
        pointer = JSON.parse(pointerBytes);
        fields(pointer, ["schema_version", "variant_id", "manifest"]);
        check(pointer.schema_version === "web-active-v1" && isId(pointer.variant_id)
          && pointer.variant_id.length <= 193 && pointer.manifest === `${pointer.variant_id}/manifest.json`, "Invalid active selection.");
        const packageDir = path.join(root, pointer.variant_id);
        await directory(packageDir);
        const manifestPath = path.join(packageDir, "manifest.json");
        await regularFile(manifestPath, 4 * 1024 * 1024);
        const manifestBytes = await fs.readFile(manifestPath);
        const manifest = JSON.parse(manifestBytes);
        validateManifest(manifest, pointer);
        const files = new Map();
        const imageChecks = [];
        for (const family of manifest.families) for (const group of family.sizes) for (const item of group.items) {
          if (item.outcome !== "rendered") continue;
          await directory(path.join(packageDir, "assets"));
          const file = path.join(packageDir, item.image.path);
          const stat = await regularFile(file);
          files.set(item.image.path, [stat.size, stat.mtimeMs, stat.ctimeMs, stat.ino, stat.dev]);
          imageChecks.push({ item, group, file, label: `${family.name}, ${group.size_px} px, ${profileLabels[item.profile]}, ${item.label}` });
        }
        const key = hash(Buffer.concat([pointerBytes, manifestBytes, Buffer.from(JSON.stringify(selection)), Buffer.from(JSON.stringify([...files])),
          Buffer.from(selectedVariant === null ? "active" : "proposal")]));
        if (cached?.key === key) return cached.result;
        const assets = new Map();
        for (const { item, group, file, label } of imageChecks) {
          let bytes = assets.get(item.image.path);
          if (!bytes) {
            bytes = await fs.readFile(file);
            check(hash(bytes) === item.image.sha256, `Image checksum differs for ${label}.`);
            assets.set(item.image.path, bytes);
          }
          validatePng(bytes, group, manifest.profiles.find((p) => p.id === item.profile).output_bits, label);
        }
        const result = { ...view(manifest, pointer), selection, proposal: selectedVariant !== null, pointer, pointerBytes, manifestBytes, assets };
        cached = { key, result };
        return result;
      } catch (error) {
        cached = null;
        if (error.code === "ENOENT" && !pointer) {
          try {
            await fs.lstat(root);
          } catch (rootError) {
            if (rootError.code === "ENOENT") return { state: "empty", families: [], variantLabel: null };
          }
        }
        return {
          state: "error", families: [], variantLabel: null,
          message: error.code === "ENOENT" ? "The selected specimen package is incomplete." : error.message,
          selectedVariant: typeof pointer?.variant_id === "string" ? pointer.variant_id : "Unrecognized selection",
        };
      }
    },

    async publish(result, output) {
      const content = path.join(output, "content");
      await fs.mkdir(content, { recursive: true });
      await directory(content);
      if (result.state !== "ready") {
        await fs.rm(path.join(content, "active.json"), { force: true });
        return;
      }
      const packageDir = path.join(content, result.pointer.variant_id);
      await fs.mkdir(packageDir, { recursive: true });
      await directory(packageDir);
      for (const [relative, bytes] of result.assets) await atomicWrite(path.join(packageDir, relative), bytes);
      await atomicWrite(path.join(packageDir, "manifest.json"), result.manifestBytes);
      await atomicWrite(path.join(content, "active.json"), result.pointerBytes);
    },
  };
}
