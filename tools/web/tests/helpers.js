import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import Eleventy from "@11ty/eleventy";
import { PNG } from "pngjs";
import { configureWeb } from "../eleventy.config.js";

export const webRoot = fileURLToPath(new URL("..", import.meta.url));
export const pageRoot = path.join(webRoot, "pages");
export const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");

export function fontMetadata() {
  return {
    names: Object.fromEntries(["family", "style", "full", "postscript", "version", "copyright", "manufacturer", "designer", "description", "vendor_url", "designer_url", "license", "license_url"].map((key) => [key, key === "style" ? "Regular" : null])),
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
    kerning: { horizontal: true, vertical: false, sources: ["GPOS kern"] },
    style: { slope: "upright", weight_class: 400, width_class: 5, italic_angle: 0 },
    classification: { family_class: 0, panose: [2, 11, 5, 3, 3, 4, 3, 2, 2, 4], monospaced: false },
    coverage: { character_count: 3, ranges: [[65, 66], [0x1f600, 0x1f600]] },
    declared_unicode_ranges: [1, 0, 0, 0],
  };
}

export function png(levels = [0, 255, 255, 0], width = 2, height = 2) {
  const data = Buffer.from(levels.flatMap((level) => [level, level, level, 255]));
  return PNG.sync.write({ width, height, data }, { colorType: 0, bitDepth: 8 });
}

export async function fixture(t) {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "font-web-test-"));
  t.after(() => fs.rm(temp, { recursive: true, force: true }));
  const root = path.join(temp, "specimens");
  const output = path.join(temp, "web");
  const bytes = png();
  const imageHash = hash(bytes);
  const pointer = { schema_version: "web-active-v1", variant_id: "reference-test", manifest: "reference-test/manifest.json" };
  const item = {
    id: "reading-mono", profile: "mono_1bit", label: "Reading sample", text: "A V",
    outcome: "rendered", image: { path: `assets/${imageHash}.png`, sha256: imageHash },
  };
  const manifest = {
    schema_version: "web-specimens-v1",
    variant: { id: pointer.variant_id, kind: "reference", version: null, generation_sha256: "a".repeat(64), composition_sha256: "b".repeat(64) },
    profiles: [{ id: "mono_1bit", output_bits: 1 }, { id: "gray_3bit", output_bits: 3 }],
    families: [{
      id: "fixture", name: "Fixture font", source_sha256: "c".repeat(64),
      metadata: fontMetadata(),
      sizes: [{ size_px: 16, axes: { wght: 400 }, thumbnail: { width_px: 2, height_px: 2 }, items: [item, { ...item, id: "reading-gray", profile: "gray_3bit" }] }],
    }],
  };
  const packageDir = path.join(root, pointer.variant_id);
  const imagePath = path.join(packageDir, item.image.path);
  await fs.mkdir(path.dirname(imagePath), { recursive: true });
  await fs.writeFile(imagePath, bytes);
  const save = async () => {
    await fs.writeFile(path.join(root, "active.json"), JSON.stringify(pointer));
    await fs.writeFile(path.join(packageDir, "manifest.json"), JSON.stringify(manifest));
  };
  await save();
  return { root, output, pointer, manifest, packageDir, imagePath, bytes, save };
}

export async function build(root, output, options = {}) {
  const eleventy = new Eleventy(pageRoot, output, {
    configPath: false,
    quietMode: true,
    config: (config) => configureWeb(config, { specimenRoot: root, ...options }),
  });
  await eleventy.write();
  return fs.readFile(path.join(output, "index.html"), "utf8");
}

export async function serve(t, root) {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://localhost");
      if (!url.pathname.startsWith("/preview/")) throw new Error("Unknown prefix");
      let relative = decodeURIComponent(url.pathname.slice(9));
      if (!relative || relative.endsWith("/")) relative += "index.html";
      const file = path.resolve(root, relative);
      if (path.relative(root, file).startsWith("..")) throw new Error("Invalid path");
      const bytes = await fs.readFile(file);
      const mime = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".png": "image/png", ".wasm": "application/wasm", ".ttf": "font/ttf", ".otf": "font/otf" };
      response.writeHead(200, { "Content-Type": mime[path.extname(file)] ?? "application/json" });
      response.end(bytes);
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}/preview/`;
}
