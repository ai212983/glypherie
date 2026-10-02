import path from "node:path";
import { promises as fs } from "node:fs";
import { fileURLToPath } from "node:url";
import { createSpecimenImporter } from "./lib/specimens.js";
import { createComparisonImporter, glyphPages, removeStaleGlyphPages, validatePreviewScope } from "./lib/comparisons.js";
import { previewRoles } from "./lib/selection.js";
import { boundedFontFile, buildInteractive, publishInteractive } from "./lib/interactive.js";

export function configureWeb(eleventyConfig, options = {}) {
  const webRoot = path.dirname(fileURLToPath(import.meta.url));
  const specimenRoot = options.specimenRoot ?? path.resolve(webRoot, "../../out/specimens");
  const interactiveConfig = options.interactiveConfig ?? path.resolve(webRoot, "../generator/specimens.json");
  const repoRoot = options.repoRoot ?? path.resolve(webRoot, "../..");
  const importer = createSpecimenImporter(specimenRoot);
  const comparisonImporter = createComparisonImporter(specimenRoot);
  let specimens;
  let comparisons = [];
  let activeComparison = null;
  let versionRoles = null;
  eleventyConfig.addWatchTarget(path.join(specimenRoot, "published.json"));
  eleventyConfig.addWatchTarget(path.join(specimenRoot, "active.json"));
  eleventyConfig.addWatchTarget(path.join(specimenRoot, "comparisons/index.json"));
  eleventyConfig.addWatchTarget(path.join(webRoot, "assets/"));
  eleventyConfig.addWatchTarget(path.join(webRoot, "lib/"));
  eleventyConfig.addPassthroughCopy({ [path.join(webRoot, "assets")]: "assets" });
  eleventyConfig.addGlobalData("specimens", () => specimens);
  eleventyConfig.addGlobalData("comparisons", () => comparisons);
  eleventyConfig.addGlobalData("activeComparison", () => activeComparison);
  eleventyConfig.addGlobalData("versionRoles", () => versionRoles);
  eleventyConfig.addGlobalData("glyphPages", () => glyphPages(comparisons));
  eleventyConfig.on("eleventy.before", async ({ directories }) => {
    for (const obsolete of ["reviews", "review-content"]) {
      await fs.rm(path.join(path.resolve(directories.output), obsolete), { recursive: true, force: true });
    }
    specimens = await importer.load();
    // Interactive version switch, derived from the selected publication
    // view (never from revision numbers). Null hides the switch and keeps
    // the renderer's approved-baseline default.
    versionRoles = specimens.state === "ready" ? previewRoles(specimens.selection ?? null) : null;
    await importer.publish(specimens, path.resolve(directories.output));
    comparisons = await comparisonImporter.load();
    const matches = specimens.state === "ready"
      ? comparisons.filter((comparison) => comparison.current.package_id === specimens.pointer.variant_id)
      : [];
    if (matches.length > 1) throw new Error("Multiple comparisons select the active specimen package");
    activeComparison = matches[0] ?? null;
    if (specimens.state === "ready" && specimens.selection?.previous) {
      const { current, previous } = specimens.selection;
      if (!activeComparison || activeComparison.previous.package_id !== previous.id
        || activeComparison.current.generation_sha256 !== current.generation_sha256
        || activeComparison.previous.generation_sha256 !== previous.generation_sha256
        || activeComparison.current.label !== current.version
        || activeComparison.previous.label !== (previous.version ?? "Reference")) {
        throw new Error("Comparison must show the selected candidate against the approved baseline, or the baseline against reference; legacy manifests use their historical comparison.");
      }
      comparisons = [activeComparison];
    } else if (specimens.state === "ready" && specimens.selection) {
      comparisons = [];
      activeComparison = null;
    }
    if (specimens.state === "ready") {
      if (activeComparison) validatePreviewScope(activeComparison, specimens);
      const sameAxes = (a, b) => JSON.stringify(Object.entries(a).sort()) === JSON.stringify(Object.entries(b).sort());
      for (const family of specimens.families) {
        const comparisonFamily = activeComparison?.families.find((candidate) => candidate.id === family.id);
        for (const group of family.sizes) {
          const comparisonSize = comparisonFamily?.sizes.find((candidate) => candidate.size_px === group.size_px && sameAxes(candidate.axes, group.axes)) ?? null;
          group.glyphPreview = comparisonSize?.glyphs.length ? comparisonSize : null;
          group.attentionGroups = comparisonSize?.attentionGroups ?? [];
          group.attentionInitiallyVisible = comparisonSize?.attentionInitiallyVisible ?? false;
        }
      }
    }
    await comparisonImporter.publish(comparisons, path.resolve(directories.output));
    // Interactive specimens never gate the page: a missing config or font
    // source leaves disabled sections, but a malformed config fails loudly.
    let interactive = { doc: { schema_version: "web-interactive-v1", families: [] }, fonts: [] };
    if (specimens.state === "ready") {
      let raw = null;
      try {
        raw = JSON.parse(await fs.readFile(interactiveConfig, "utf8"));
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
      if (raw) {
        interactive = await buildInteractive({
          viewFamilies: specimens.families,
          configFamilies: Array.isArray(raw?.families) ? raw.families : [],
          profiles: Array.isArray(raw?.profiles) ? raw.profiles : [],
          cards: Array.isArray(raw?.cards) ? raw.cards : [],
          configDir: path.dirname(path.resolve(interactiveConfig)),
          repoRoot,
          readFont: (file) => boundedFontFile(file, repoRoot),
        });
      }
      for (const family of specimens.families) {
        family.interactive = interactive.doc.families.find((entry) => entry.id === family.id) ?? {
          available: false, axes: [], fontUrl: "", default_size_px: 16, default_axes: {}, render: {}, sample_text: "Aa", presets: [], default_preset: "custom",
        };
      }
    }
    await publishInteractive(interactive, path.resolve(directories.output));
  });
  eleventyConfig.on("eleventy.after", async ({ directories }) => {
    await removeStaleGlyphPages(comparisons, path.resolve(directories.output));
  });
  eleventyConfig.setNunjucksEnvironmentOptions({
    autoescape: true,
    throwOnUndefined: true,
  });

  eleventyConfig.setServerOptions({
    port: 8903,
    portReassignmentRetryCount: 0,
    showAllHosts: true,
  });

  return {
    dir: {
      input: path.join(webRoot, "pages"),
      output: path.resolve(webRoot, "../../out/web"),
    },
    templateFormats: ["html", "njk"],
    htmlTemplateEngine: "njk",
  };
}

export default function (eleventyConfig) {
  return configureWeb(eleventyConfig);
}
