import { promises as fs } from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";
import { check, fields, nonemptyArray, hash, isHash, isId, isText, regularFile, directory, atomicWrite } from "./specimens.js";

const labels = { mono_1bit: "1-bit", gray_3bit: "3-bit" };
const added = "0,96,255";
const removed = "224,32,32";

export function validateComparison(manifest, entry) {
  fields(entry, ["id", "manifest"]);
  check(typeof entry.id === "string" && /^\d{2,8}$/.test(entry.id), "Invalid comparison route.");
  check(new RegExp(`^${entry.id}-[a-f0-9]{64}/manifest\\.json$`).test(entry.manifest), "Invalid comparison manifest path.");
  fields(manifest, ["schema_version", "id", "previous", "current", "profiles", "families"], ["statistics", "attention"]);
  check(manifest.schema_version === "web-glyph-comparison-v1" && manifest.id === entry.id, "Invalid comparison identity.");
  for (const side of [manifest.previous, manifest.current]) {
    fields(side, ["package_id", "label", "generation_sha256"]);
    check(isId(side.package_id) && side.package_id.length <= 193 && isText(side.label) && isHash(side.generation_sha256), "Invalid comparison input.");
  }
  nonemptyArray(manifest.profiles, "Comparison profiles");
  const profiles = new Map();
  for (const profile of manifest.profiles) {
    fields(profile, ["id", "output_bits"]);
    check((profile.id === "mono_1bit" && profile.output_bits === 1) || (profile.id === "gray_3bit" && profile.output_bits === 3), "Invalid comparison profile.");
    check(!profiles.has(profile.id), "Duplicate comparison profile.");
    profiles.set(profile.id, profile.output_bits);
  }
  if (manifest.statistics !== undefined) {
    check(Array.isArray(manifest.statistics) && manifest.statistics.length === profiles.size, "Invalid comparison statistics.");
    const seen = new Set();
    for (const stats of manifest.statistics) {
      fields(stats, ["profile", "same_symbols", "changed_symbols", "average_changed_pixels", "median_changed_pixels"], ["unavailable_symbols"]);
      check(profiles.has(stats.profile) && !seen.has(stats.profile), "Invalid statistics profile.");
      seen.add(stats.profile);
      check(stats.unavailable_symbols === undefined || stats.unavailable_symbols === 0, "Comparison contains missing glyphs.");
      check([stats.same_symbols, stats.changed_symbols].every((n) => Number.isSafeInteger(n) && n >= 0), "Invalid symbol counts.");
      check([stats.average_changed_pixels, stats.median_changed_pixels].every((n) => Number.isFinite(n)
        && (stats.changed_symbols ? n >= 1 && n <= 16 * 1024 * 1024 : n === 0)), "Invalid changed-pixel statistics.");
    }
  }
  nonemptyArray(manifest.families, "Comparison families");
  const familyIds = new Set();
  for (const family of manifest.families) {
    fields(family, ["id", "name", "sizes"]);
    check(isId(family.id) && isText(family.name) && !familyIds.has(family.id), "Invalid comparison family.");
    familyIds.add(family.id);
    nonemptyArray(family.sizes, "Comparison sizes");
    const sizes = new Set();
    for (const size of family.sizes) {
      fields(size, ["size_px", "axes", "canvas", "glyphs"]);
      check(Number.isFinite(size.size_px) && size.size_px >= 1 && size.size_px <= 512 && !sizes.has(size.size_px), "Invalid comparison size.");
      sizes.add(size.size_px);
      check(size.axes && typeof size.axes === "object" && !Array.isArray(size.axes)
        && Object.entries(size.axes).every(([tag, value]) => /^[\x20-\x7e]{4}$/.test(tag) && Number.isFinite(value)), "Invalid comparison axes.");
      fields(size.canvas, ["width_px", "height_px", "origin_x", "baseline_y", "padding_px"]);
      const { width_px: width, height_px: height, origin_x: x, baseline_y: y } = size.canvas;
      check(Number.isSafeInteger(width) && Number.isSafeInteger(height) && width > 0 && height > 0 && width * height <= 16 * 1024 * 1024
        && Number.isSafeInteger(x) && Number.isSafeInteger(y) && x >= 0 && x < width && y >= 0 && y < height, "Invalid comparison canvas.");
      check(Number.isSafeInteger(size.canvas.padding_px) && size.canvas.padding_px >= 0
        && size.canvas.padding_px * 2 <= Math.min(width, height), "Invalid comparison padding.");
      check(Array.isArray(size.glyphs), "Invalid comparison glyphs.");
      const codepoints = new Set();
      for (const glyph of size.glyphs) {
        fields(glyph, ["codepoint", "character", "profiles"]);
        check(Number.isSafeInteger(glyph.codepoint) && glyph.codepoint >= 0 && glyph.codepoint <= 0x10ffff
          && !(glyph.codepoint >= 0xd800 && glyph.codepoint <= 0xdfff)
          && String.fromCodePoint(glyph.codepoint) === glyph.character && !codepoints.has(glyph.codepoint), "Invalid comparison glyph.");
        codepoints.add(glyph.codepoint);
        nonemptyArray(glyph.profiles, "Glyph profiles");
        const seen = new Set();
        for (const profile of glyph.profiles) {
          fields(profile, ["id", "advance_px", "previous", "current", "difference", "reason"]);
          check(Number.isSafeInteger(profile.advance_px) && profile.advance_px > 0 && profile.advance_px <= 65536, "Invalid glyph advance.");
          check(profiles.has(profile.id) && !seen.has(profile.id), "Invalid glyph profile.");
          seen.add(profile.id);
          check(profile.previous && profile.current && profile.difference && profile.reason === null,
            `Missing comparison glyph images: ${family.id}, ${size.size_px} px, ${profile.id}, U+${glyph.codepoint.toString(16).toUpperCase().padStart(4, "0")}.`);
          for (const key of ["previous", "current", "difference"]) {
            if (profile[key] === null) continue;
            fields(profile[key], ["path", "sha256"]);
            check(isHash(profile[key].sha256) && profile[key].path === `assets/${profile[key].sha256}.png`, "Invalid glyph asset path.");
          }
        }
      }
    }
  }
  if (manifest.attention !== undefined) {
    check(Array.isArray(manifest.attention), "Invalid attention cases.");
    const ids = new Set(), cases = new Set();
    for (const item of manifest.attention) {
      fields(item, ["id", "family_id", "family_name", "codepoint", "character", "size_px", "axes", "status", "inspection", "description", "canvas", "profiles"]);
      check(isId(item.id) && !ids.has(item.id), "Invalid or duplicate attention ID.");
      ids.add(item.id);
      check(["pending", "confirmed"].includes(item.status) && isText(item.inspection) && item.inspection.length <= 160
        && typeof item.description === "string" && item.description.length <= 240,
        "Invalid attention status or inspection.");
      const family = manifest.families.find((f) => f.id === item.family_id);
      check(family && family.name === item.family_name, "Attention family differs from comparison.");
      for (const profile of item.profiles) {
        const key = JSON.stringify([item.family_id, item.size_px, Object.entries(item.axes).sort(), item.codepoint, profile.id]);
        check(!cases.has(key), "Duplicate attention symbol case."); cases.add(key);
      }
      // Reuse the full glyph/canvas/profile validation for marked and unchanged cases.
      validateComparison({ ...manifest, statistics: undefined, attention: undefined,
        families: [{ id: item.family_id, name: item.family_name, sizes: [{ size_px: item.size_px,
          axes: item.axes, canvas: item.canvas, glyphs: [{ codepoint: item.codepoint, character: item.character, profiles: item.profiles }] }] }],
      }, entry);
    }
  }
}

// Apply the selected specimen scope to every comparison surface, including annotations.
// This is deliberately derived from publication metadata, not a second hardcoded size list.
export function validatePreviewScope(comparison, specimens) {
  const sameAxes = (a, b) => JSON.stringify(Object.entries(a).sort()) === JSON.stringify(Object.entries(b).sort());
  const validate = (familyId, size, profiles) => {
    const family = specimens.families.find((f) => f.id === familyId);
    const group = family?.sizes.find((s) => s.size_px === size.size_px && sameAxes(s.axes, size.axes));
    check(group && profiles.every((p) => group.items.some((item) => item.profile === p.id)),
      `Comparison case outside published preview scope: ${familyId}, ${size.size_px} px. Keep diagnostic sizes/axes/profiles isolated.`);
  };
  for (const family of comparison.families) for (const size of family.sizes) {
    validate(family.id, size, size.glyphs.flatMap((g) => g.profiles));
  }
  for (const item of comparison.attention ?? []) validate(item.family_id, item, item.profiles);
}

function validateImage(bytes, canvas, bits, diff) {
  check(bytes.length >= 33 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
    && bytes.readUInt32BE(16) === canvas.width_px && bytes.readUInt32BE(20) === canvas.height_px,
    "Comparison PNG dimensions differ.");
  const image = PNG.sync.read(bytes, { checkCRC: true });
  check(bytes[24] === 8 && bytes[25] === 2 && image.width === canvas.width_px && image.height === canvas.height_px, "Comparison PNG dimensions or format differ.");
  const levels = (1 << bits) - 1;
  const palette = new Set(Array.from({ length: levels + 1 }, (_, q) => [255 - Math.round(q * 255 / levels)].flatMap((v) => [v, v, v]).join(",")));
  if (diff) { palette.add(added); palette.add(removed); }
  let changed = 0;
  for (let i = 0; i < image.data.length; i += 4) {
    const color = [...image.data.subarray(i, i + 3)].join(",");
    check(palette.has(color) && image.data[i + 3] === 255, "Unexpected comparison pixel color.");
    if (diff && (color === added || color === removed)) changed++;
  }
  return changed;
}

function view(manifest, packageId, changedImages) {
  const defaultProfile = manifest.profiles.find((p) => p.id === "mono_1bit")?.id ?? manifest.profiles[0].id;
  const attention = (manifest.attention ?? []).map((item) => ({ ...item,
    slug: `U${item.codepoint.toString(16).toUpperCase().padStart(4, "0")}`,
    anchor: `attention-${item.id}`,
    initiallyVisible: item.profiles.some((p) => p.id === defaultProfile),
    profiles: item.profiles.map((p) => ({ ...p, initiallyVisible: p.id === defaultProfile })),
  }));
  const sameAxes = (a, b) => JSON.stringify(Object.entries(a).sort()) === JSON.stringify(Object.entries(b).sort());
  const scopedAttention = (familyId, size) => attention.filter((item) => item.family_id === familyId
    && item.size_px === size.size_px && sameAxes(item.axes, size.axes));
  const attentionGroupsFor = (symbols) => {
    const groups = [];
    for (const symbol of symbols) {
      let group = groups.find((g) => g.inspection === symbol.inspection);
      if (!group) { group = { inspection: symbol.inspection, symbols: [], initiallyVisible: false }; groups.push(group); }
      group.symbols.push(symbol);
      group.initiallyVisible ||= symbol.initiallyVisible;
    }
    return groups;
  };
  const marked = (family, size, glyph, profile) => attention.some((item) => item.family_id === family.id
    && item.size_px === size.size_px && sameAxes(item.axes, size.axes)
    && item.codepoint === glyph.codepoint && item.profiles.some((p) => p.id === profile.id));
  const visibleManifest = {
    ...manifest,
    families: manifest.families.map((family) => ({
      ...family,
      sizes: family.sizes.map((size) => ({
        ...size,
        glyphs: size.glyphs.map((glyph) => ({
          ...glyph,
          profiles: glyph.profiles.filter((profile) => profile.difference && changedImages.get(profile.difference.sha256) > 0),
        })).filter((glyph) => glyph.profiles.length),
      })),
    })),
  };
  const families = visibleManifest.families.map((family) => ({
    ...family,
    initiallyVisible: family.sizes.some((s) => s.glyphs.some((g) => g.profiles.some((p) => p.id === defaultProfile))),
    sizes: [...family.sizes].sort((a, b) => a.size_px - b.size_px).map((size) => ({
      ...size,
      anchor: `size-${size.size_px}`,
      lineHeight: Math.max(1, size.canvas.height_px - 2 * size.canvas.padding_px),
      attentionGroups: attentionGroupsFor(scopedAttention(family.id, size)),
      attentionInitiallyVisible: scopedAttention(family.id, size).some((item) => item.initiallyVisible),
      initiallyVisible: size.glyphs.some((g) => g.profiles.some((p) => p.id === defaultProfile)),
      glyphs: size.glyphs.map((glyph) => ({
        ...glyph,
        slug: `U${glyph.codepoint.toString(16).toUpperCase().padStart(4, "0")}`,
        profiles: glyph.profiles.map((profile) => ({ ...profile, initiallyVisible: profile.id === defaultProfile,
          attention: marked(family, size, glyph, profile) })),
      })),
    })),
  }));
  const statistics = (manifest.statistics ?? []).map((stats) => {
    const changed = [];
    for (const family of manifest.families) for (const size of family.sizes) for (const glyph of size.glyphs) {
      const profile = glyph.profiles.find((profile) => profile.id === stats.profile);
      if (!profile) continue;
      if (changedImages.get(profile.difference.sha256) > 0) changed.push(changedImages.get(profile.difference.sha256));
    }
    changed.sort((a, b) => a - b);
    const average = changed.length ? changed.reduce((sum, n) => sum + n, 0) / changed.length : 0;
    const median = changed.length ? (changed[Math.floor((changed.length - 1) / 2)] + changed[Math.floor(changed.length / 2)]) / 2 : 0;
    check(stats.changed_symbols === changed.length
      && Math.abs(stats.average_changed_pixels - average) < 1e-9 && Math.abs(stats.median_changed_pixels - median) < 1e-9,
    "Comparison statistics differ from the exported glyphs.");
    const format = (n) => n.toLocaleString("en", { maximumFractionDigits: 2 });
    return { ...stats, sameLabel: format(stats.same_symbols), changedLabel: format(stats.changed_symbols),
      averageLabel: format(average), medianLabel: format(median) };
  });
  for (const family of families) for (const size of family.sizes) {
    size.ordinaryInitiallyVisible = size.glyphs.some((g) => g.profiles.some((p) => p.initiallyVisible && !p.attention));
  }
  return { ...manifest, packageId, defaultProfile, families, statistics, attention,
    profiles: manifest.profiles.map((p) => ({ ...p, label: labels[p.id] })) };
}

export function glyphPages(comparisons) {
  return comparisons.flatMap((comparison) => comparison.families.flatMap((family) => {
    const glyphs = new Map();
    for (const size of family.sizes) for (const glyph of size.glyphs) {
      const profiles = glyph.profiles.filter((p) => !p.attention);
      if (!profiles.length) continue;
      if (!glyphs.has(glyph.codepoint)) glyphs.set(glyph.codepoint, { comparison, familyId: family.id, familyName: family.name,
        character: glyph.character, slug: glyph.slug, sizes: [] });
      glyphs.get(glyph.codepoint).sizes.push({ ...size, profiles, attention: null });
    }
    for (const item of comparison.attention ?? []) {
      if (item.family_id !== family.id) continue;
      if (!glyphs.has(item.codepoint)) glyphs.set(item.codepoint, { comparison, familyId: family.id, familyName: family.name,
        character: item.character, slug: item.slug, sizes: [] });
      glyphs.get(item.codepoint).sizes.push({ ...item, attention: item });
    }
    return [...glyphs.values()].map((page) => {
      const available = new Set(page.sizes.flatMap((size) => size.profiles.map((profile) => profile.id)));
      const defaultProfile = available.has("mono_1bit") ? "mono_1bit" : [...available][0];
      return { ...page, comparison: { ...comparison, defaultProfile }, sizes: page.sizes.sort((a, b) => a.size_px - b.size_px).map((size) => ({
        ...size,
        initiallyVisible: size.profiles.some((profile) => profile.id === defaultProfile),
        profiles: size.profiles.map((profile) => ({ ...profile, initiallyVisible: profile.id === defaultProfile })),
      })) };
    });
  }));
}

export async function removeStaleGlyphPages(comparisons, output) {
  const wanted = new Set(glyphPages(comparisons).map((page) => `${page.comparison.id}/${page.familyId}/${page.slug}`));
  for (const comparison of comparisons) {
    const comparisonDir = path.join(output, comparison.id);
    try { await directory(comparisonDir); }
    catch (error) { if (error.code === "ENOENT") continue; throw error; }
    const index = path.join(comparisonDir, "index.html");
    try { await regularFile(index); }
    catch (error) { if (error.code === "ENOENT") continue; throw error; }
    await fs.unlink(index);
  }
  for (const comparison of comparisons) for (const family of comparison.families) {
    const familyDir = path.join(output, comparison.id, family.id);
    try { await directory(familyDir); }
    catch (error) { if (error.code === "ENOENT") continue; throw error; }
    for (const entry of await fs.readdir(familyDir, { withFileTypes: true })) {
      if (!entry.isDirectory() || !/^U[0-9A-F]{4,6}$/.test(entry.name)
        || wanted.has(`${comparison.id}/${family.id}/${entry.name}`)) continue;
      const index = path.join(familyDir, entry.name, "index.html");
      try { await regularFile(index); }
      catch (error) { if (error.code === "ENOENT") continue; throw error; }
      await fs.unlink(index);
    }
  }
}

export function createComparisonImporter(specimenRoot) {
  const root = path.join(specimenRoot, "comparisons");
  return {
    async load() {
      try { await regularFile(path.join(root, "index.json"), 1024 * 1024); }
      catch (error) { if (error.code === "ENOENT") return []; throw error; }
      await directory(root);
      const index = JSON.parse(await fs.readFile(path.join(root, "index.json")));
      fields(index, ["schema_version", "comparisons"]);
      check(index.schema_version === "web-comparisons-v1" && Array.isArray(index.comparisons), "Invalid comparison index.");
      const results = [], ids = new Set();
      for (const entry of index.comparisons) {
        fields(entry, ["id", "manifest"]);
        check(typeof entry.id === "string" && /^\d{2,8}$/.test(entry.id) && !ids.has(entry.id), "Invalid or duplicate comparison route.");
        ids.add(entry.id);
        check(new RegExp(`^${entry.id}-[a-f0-9]{64}/manifest\\.json$`).test(entry.manifest), "Invalid comparison manifest path.");
        const packageId = entry.manifest.split("/")[0];
        const packageDir = path.join(root, packageId);
        await directory(packageDir);
        await regularFile(path.join(packageDir, "manifest.json"), 16 * 1024 * 1024);
        const bytes = await fs.readFile(path.join(packageDir, "manifest.json"));
        check(hash(bytes) === packageId.slice(entry.id.length + 1), "Comparison manifest checksum differs.");
        const manifest = JSON.parse(bytes);
        validateComparison(manifest, entry);
        const assets = new Map(), checked = new Set(), changedImages = new Map();
        const groups = [...manifest.families.flatMap((family) => family.sizes), ...(manifest.attention ?? []).map((item) => ({
          canvas: item.canvas, glyphs: [{ profiles: item.profiles }],
        }))];
        for (const size of groups) for (const glyph of size.glyphs) for (const profile of glyph.profiles) {
          const bits = manifest.profiles.find((p) => p.id === profile.id).output_bits;
          for (const key of ["previous", "current", "difference"]) {
            const image = profile[key]; if (!image) continue;
            if (!assets.has(image.path)) {
              await directory(path.join(packageDir, "assets"));
              await regularFile(path.join(packageDir, image.path));
              const imageBytes = await fs.readFile(path.join(packageDir, image.path));
              check(hash(imageBytes) === image.sha256, "Comparison image checksum differs.");
              assets.set(image.path, imageBytes);
            }
            const validationKey = `${image.path}/${size.canvas.width_px}/${size.canvas.height_px}/${bits}/${key === "difference"}`;
            if (!checked.has(validationKey)) {
              const changed = validateImage(assets.get(image.path), size.canvas, bits, key === "difference");
              if (key === "difference") changedImages.set(image.sha256, changed);
              checked.add(validationKey);
            }
          }
        }
        results.push({ ...view(manifest, packageId, changedImages), manifestBytes: bytes, assets });
      }
      return results;
    },
    async publish(comparisons, output) {
      const content = path.join(output, "comparison-content");
      if (!comparisons.length) return;
      await fs.mkdir(content, { recursive: true });
      await directory(content);
      for (const comparison of comparisons) {
        const destination = path.join(content, comparison.packageId);
        await fs.mkdir(path.join(destination, "assets"), { recursive: true });
        await directory(destination);
        await directory(path.join(destination, "assets"));
        for (const [relative, bytes] of comparison.assets) await atomicWrite(path.join(destination, relative), bytes);
        await atomicWrite(path.join(destination, "manifest.json"), comparison.manifestBytes);
      }
    },
  };
}
