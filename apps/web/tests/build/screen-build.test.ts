import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildApp } from "../helpers/spa-helpers.ts";

test("production build publishes the standalone screen entry beneath the hosting prefix", async (t) => {
  const output = await buildApp(t, "/preview/", "https://example.test/preview/");
  const page = await fs.readFile(path.join(output, "screen", "index.html"), "utf8");
  assert.equal((page.match(/<title\b/g) ?? []).length, 1);
  assert.ok(page.includes("<title data-page-metadata>Screen — Glypherie</title>"));
  assert.ok(page.includes('rel="canonical" href="https://example.test/preview/screen/"'));
  assert.ok(page.includes('property="og:image" content="https://example.test/preview/icons/icon-512.png"'));
  assert.ok(page.includes('href="/preview/manifest.webmanifest"'));

  // Existing standalone entries and device artwork still publish alongside.
  for (const route of ["fonts/", "palettes/"]) {
    await fs.access(path.join(output, route, "index.html"));
  }
  for (const shell of [
    "xteink-x4.svg",
    "xteink-x3.svg",
    "inkplate-4-tempera.svg",
    "waveshare-esp32-s3-rlcd-4-2.svg",
    "playdate.svg",
    "boox-picco.svg",
  ]) {
    await fs.access(path.join(output, "devices", "shells", shell));
  }
});
