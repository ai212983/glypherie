import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildApp, fontDir, sha256 } from "../helpers/spa-helpers.ts";

async function filesByExtension(root: string, extension: string): Promise<string[]> {
  const found: string[] = [];
  for (const entry of await fs.readdir(path.join(root, "assets"), { withFileTypes: true })) {
    if (entry.isFile() && entry.name.endsWith(extension)) found.push(entry.name);
  }
  return found;
}

test("production build emits hashed app, renderer, fonts, and licenses with no specimen dependency", async (t) => {
  const output = await buildApp(t);
  const html = await fs.readFile(path.join(output, "index.html"), "utf8");
  assert.match(html, /<div id="root"><\/div>/);
  assert.match(html, /<noscript>/);
  assert.doesNotMatch(html, /specimens\.json|out\/specimens/);

  const scripts = await filesByExtension(output, ".js");
  assert.ok(scripts.some((name) => /^index-[\w-]+\.js$/.test(name)), "hashed app chunk");
  assert.ok(scripts.some((name) => /^font-worker-[\w-]+\.js$/.test(name)), "hashed worker chunk");
  const cssNames = await filesByExtension(output, ".css");
  assert.equal(cssNames.length, 1, "one hashed stylesheet");
  const wasm = await filesByExtension(output, ".wasm");
  assert.equal(wasm.length, 1, "one hashed renderer binary");

  const fontPackages: Array<[string, string]> = [
    ["Roboto.ttf", "OFL-Roboto.txt"],
    ["Roboto-Italic.ttf", "OFL-Roboto.txt"],
    ["RobotoFlex.ttf", "OFL-RobotoFlex.txt"],
    ["Literata.ttf", "OFL-Literata.txt"],
    ["SourceSans3.ttf", "OFL-SourceSans3.txt"],
  ];
  for (const [source, _] of fontPackages) {
    const built = (await filesByExtension(output, ".ttf")).find((name) => name.startsWith(source.replace(".ttf", "-")));
    assert.ok(built, `hashed ${source} emitted`);
    assert.equal(
      sha256(await fs.readFile(path.join(output, "assets", built))),
      sha256(await fs.readFile(path.join(fontDir, source))),
      `${source} bytes unchanged from canonical fonts/`,
    );
  }
  const licenseSources = [...new Set(fontPackages.map(([, license]) => license))];
  for (const license of licenseSources) {
    const builtLicense = (await filesByExtension(output, ".txt")).find((name) => name.startsWith(license.replace(".txt", "-")));
    assert.ok(builtLicense, `hashed ${license} emitted`);
    assert.equal(
      (await fs.readFile(path.join(output, "assets", builtLicense), "utf8")),
      (await fs.readFile(path.join(fontDir, license), "utf8")),
      `${license} text unchanged`,
    );
  }

  const cssName = cssNames[0];
  assert.ok(cssName, "hashed stylesheet name");
  const css = await fs.readFile(path.join(output, "assets", cssName), "utf8");
  assert.ok(css.includes("--primary:"), "theme tokens reach the stylesheet");
  assert.ok(css.includes(":focus-visible"), "focus styling reaches the stylesheet");
  assert.doesNotMatch(css, /bg-oklch\(/, "no unresolved raw color utilities");

  assert.ok(html.includes("./assets/") || html.includes("assets/"), "relative asset URLs work beneath a prefix");
  assert.doesNotMatch(html, /src=["']\/(?!preview)/, "no root-absolute asset URLs");
  await fs.access(path.join(output, "manifest.webmanifest"));
  await fs.access(path.join(output, "sw.js"));
});
