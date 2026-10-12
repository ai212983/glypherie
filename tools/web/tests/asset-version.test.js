import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { versionedWasmUrls } from "../assets/interactive.js";
import { build, fixture, webRoot } from "./helpers.js";

const scriptVersion = (html) => {
  const match = html.match(/\.\/assets\/interactive\.js\?v=([0-9a-f]+)/);
  assert.ok(match, "interactive script carries a version query");
  return match[1];
};

test("renderer asset version is stable across repeat builds", async (t) => {
  const f = await fixture(t);
  const first = scriptVersion(await build(f.root, f.output));
  assert.match(first, /^[0-9a-f]{16}$/);
  assert.equal(scriptVersion(await build(f.root, f.output)), first, "repeat builds keep the version");
});

test("staged renderer bytes invalidate the version", async (t) => {
  const f = await fixture(t);
  const missing = scriptVersion(await build(f.root, f.output));
  const wasmDir = path.join(f.output, "assets/wasm");
  await fs.mkdir(wasmDir, { recursive: true });
  const js = path.join(wasmDir, "font_wasm.js");
  const binary = path.join(wasmDir, "font_wasm_bg.wasm");
  await fs.writeFile(js, "renderer-js-v1");
  await fs.writeFile(binary, Buffer.from("renderer-bin-v1"));
  const staged = scriptVersion(await build(f.root, f.output));
  assert.notEqual(staged, missing, "staged renderer bytes change the version");
  assert.equal(scriptVersion(await build(f.root, f.output)), staged, "staged bytes are stable");
  await fs.writeFile(js, "renderer-js-v2");
  assert.notEqual(scriptVersion(await build(f.root, f.output)), staged, "changed WASM JS invalidates");
  await fs.writeFile(js, "renderer-js-v1");
  await fs.writeFile(binary, Buffer.from("renderer-bin-v2"));
  assert.notEqual(scriptVersion(await build(f.root, f.output)), staged, "changed WASM binary invalidates");
});

test("helper-only bytes invalidate both consumers' helper URL", async (t) => {
  const f = await fixture(t);
  // Isolated asset copy: mutations never touch sources shared with other tests.
  const assets = await fs.mkdtemp(path.join(os.tmpdir(), "font-assets-test-"));
  t.after(() => fs.rm(assets, { recursive: true, force: true }));
  for (const name of ["index.js", "interactive.js", "display-scaling.js", "index.css"]) {
    await fs.copyFile(path.join(webRoot, "assets", name), path.join(assets, name));
  }
  const options = { assetRoot: assets };
  const versionsOf = (html) => {
    const index = html.match(/\.\/assets\/index\.js\?v=([0-9a-f]+)/);
    const interactive = html.match(/\.\/assets\/interactive\.js\?v=([0-9a-f]+)/);
    assert.ok(index, "index script carries a version query");
    assert.ok(interactive, "interactive script carries a version query");
    return { index: index[1], interactive: interactive[1] };
  };
  const helperOf = async (consumer) => {
    const text = await fs.readFile(path.join(f.output, "assets", consumer), "utf8");
    const match = text.match(/\.\/display-scaling\.js\?v=([0-9a-f]+)/);
    assert.ok(match, `${consumer} references the versioned helper`);
    return match[1];
  };
  // Missing-WASM degraded mode still versions both consumers.
  let html = await build(f.root, f.output, options);
  const versions = versionsOf(html);
  assert.equal(versions.index, versions.interactive, "both scripts share one version");
  assert.equal(await helperOf("index.js"), versions.index, "index helper matches");
  assert.equal(await helperOf("interactive.js"), versions.interactive, "interactive helper matches");
  assert.ok(html.includes('src="./assets/index.js?v='), "relative script URL works beneath a prefix");
  assert.equal(versionsOf(await build(f.root, f.output, options)).index, versions.index, "identical rebuilds keep the version");

  // Changing ONLY helper bytes changes the helper URL; both consumers match.
  const helper = path.join(assets, "display-scaling.js");
  await fs.writeFile(helper, `${await fs.readFile(helper, "utf8")}\nexport const CACHE_BUST = 1;\n`);
  html = await build(f.root, f.output, options);
  const next = versionsOf(html);
  assert.notEqual(next.index, versions.index, "helper-only change invalidates the version");
  assert.equal(await helperOf("index.js"), next.index, "index fetches the new helper");
  assert.equal(await helperOf("interactive.js"), next.interactive, "interactive fetches the new helper");

  // Staged WASM still invalidates on top of the helper version.
  const wasmDir = path.join(f.output, "assets/wasm");
  await fs.mkdir(wasmDir, { recursive: true });
  await fs.writeFile(path.join(wasmDir, "font_wasm.js"), "renderer-js-v1");
  await fs.writeFile(path.join(wasmDir, "font_wasm_bg.wasm"), Buffer.from("renderer-bin-v1"));
  const staged = versionsOf(await build(f.root, f.output, options));
  assert.notEqual(staged.index, next.index, "staged renderer bytes change the version");
  assert.equal(await helperOf("index.js"), staged.index, "index helper follows the staged version");
  assert.equal(await helperOf("interactive.js"), staged.interactive, "interactive helper follows the staged version");
});

test("WASM JS and binary share the script version query", () => {
  const versioned = versionedWasmUrls("http://localhost/preview/assets/interactive.js?v=abc123");
  assert.ok(versioned.wasmUrl.endsWith("/assets/wasm/font_wasm.js?v=abc123"));
  assert.ok(versioned.wasmBinaryUrl.endsWith("/assets/wasm/font_wasm_bg.wasm?v=abc123"));
  const plain = versionedWasmUrls("http://localhost/preview/assets/interactive.js");
  assert.ok(plain.wasmUrl.endsWith("/assets/wasm/font_wasm.js"));
  assert.ok(!plain.wasmUrl.includes("?"), "unversioned script keeps WASM unversioned");
  assert.ok(plain.wasmBinaryUrl.endsWith("/assets/wasm/font_wasm_bg.wasm"));
  assert.ok(!plain.wasmBinaryUrl.includes("?"), "unversioned script keeps the binary unversioned");
});
