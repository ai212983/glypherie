import path from "node:path";
import { promises as fs } from "node:fs";
import { fileURLToPath } from "node:url";
import { createSpecimenImporter } from "./lib/specimens.js";
import { createComparisonImporter, glyphPages, removeStaleGlyphPages, validatePreviewScope } from "./lib/comparisons.js";

export function configureWeb(eleventyConfig, options = {}) {
  const webRoot = path.dirname(fileURLToPath(import.meta.url));
  const specimenRoot = options.specimenRoot ?? path.resolve(webRoot, "../../out/specimens");
  const importer = createSpecimenImporter(specimenRoot);
  const comparisonImporter = createComparisonImporter(specimenRoot);
  let specimens;
  let comparisons = [];
  let activeComparison = null;
  eleventyConfig.addWatchTarget(path.join(specimenRoot, "published.json"));
  eleventyConfig.addWatchTarget(path.join(specimenRoot, "active.json"));
  eleventyConfig.addWatchTarget(path.join(specimenRoot, "comparisons/index.json"));
  eleventyConfig.addWatchTarget(path.join(webRoot, "assets/"));
  eleventyConfig.addWatchTarget(path.join(webRoot, "lib/"));
  eleventyConfig.addPassthroughCopy({ [path.join(webRoot, "assets")]: "assets" });
  eleventyConfig.addGlobalData("specimens", () => specimens);
  eleventyConfig.addGlobalData("comparisons", () => comparisons);
  eleventyConfig.addGlobalData("activeComparison", () => activeComparison);
  eleventyConfig.addGlobalData("glyphPages", () => glyphPages(comparisons));
  eleventyConfig.on("eleventy.before", async ({ directories }) => {
    for (const obsolete of ["reviews", "review-content"]) {
      await fs.rm(path.join(path.resolve(directories.output), obsolete), { recursive: true, force: true });
    }
    specimens = await importer.load();
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
        throw new Error("Comparison must show the latest iteration against the previous revision's latest iteration, or reference.");
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
