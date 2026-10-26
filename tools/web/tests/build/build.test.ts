import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { runInNewContext } from "node:vm";
import { buildApp, fontDir, repoRoot, sha256 } from "../helpers/spa-helpers.ts";

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
  const rendererPackage = process.env.FONT_WASM_PREVIEW_DIR
    ?? path.join(repoRoot, "tools", "wasm", "pkg-web-preview-simd128");
  assert.equal(
    sha256(await fs.readFile(path.join(output, "assets", wasm[0]!))),
    sha256(await fs.readFile(path.join(rendererPackage, "font_wasm_bg.wasm"))),
    "configured renderer bytes reach the build unchanged (standard SIMD by default)",
  );

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

  const rendererLicense = await fs.readFile(path.join(output, "renderer-license.txt"), "utf8");
  assert.ok(rendererLicense.includes("FreeType 2.15.0"));
  assert.ok(rendererLicense.includes("The FreeType Project LICENSE"));

  const cssName = cssNames[0];
  assert.ok(cssName, "hashed stylesheet name");
  const css = await fs.readFile(path.join(output, "assets", cssName), "utf8");
  assert.ok(css.includes("--primary:"), "theme tokens reach the stylesheet");
  assert.ok(css.includes(":focus-visible"), "focus styling reaches the stylesheet");
  assert.doesNotMatch(css, /bg-oklch\(/, "no unresolved raw color utilities");

  assert.ok(html.includes("/preview/assets/"), "asset URLs use the configured hosting prefix");
  await fs.access(path.join(output, "404.html"));
  assert.doesNotMatch(html, /src=["']\/(?!preview)/, "no root-absolute asset URLs");
  await fs.access(path.join(output, "manifest.webmanifest"));
  await fs.access(path.join(output, "sw.js"));
});


test("Pages transport preserves URLs beneath root and project hosting prefixes", async (t) => {
  for (const base of ["/", "/preview/"]) {
    const output = await buildApp(t, base);
    const index = await fs.readFile(path.join(output, "index.html"), "utf8");
    const fallback = await fs.readFile(path.join(output, "404.html"), "utf8");
    const restore = index.match(/<script>([\s\S]*?__pages_route[\s\S]*?)<\/script>/)?.[1];
    const redirect = fallback.match(/<script>([\s\S]*?)<\/script>/)?.[1];
    assert.ok(restore);
    assert.ok(redirect);
    const original = new URL(`https://example.test${base}font/a/variant/b/?v=1&text=%26%2B%3F%23&literal=~and~#anchor`);
    let redirected = "";
    runInNewContext(redirect, { location: {
      pathname: original.pathname, search: original.search, hash: original.hash,
      replace: (url: string) => { redirected = url; },
    }, encodeURIComponent });
    const entry = new URL(redirected, original.origin);
    assert.equal(entry.pathname, base);
    let restored = "";
    runInNewContext(restore, {
      location: entry, URL, URLSearchParams,
      history: { replaceState: (_state: unknown, _title: string, url: string) => { restored = url; } },
    });
    assert.equal(restored, original.pathname + original.search + original.hash);
    // A forged transport query must not navigate outside this app's origin or prefix.
    for (const target of ["https://elsewhere.test/", "//elsewhere.test/"]) {
      restored = "";
      runInNewContext(restore, {
        location: new URL(`${original.origin}${base}?__pages_route=${encodeURIComponent(target)}`), URL, URLSearchParams,
        history: { replaceState: () => { restored = "unexpected"; } },
      });
      assert.equal(restored, "");
    }
  }
});
