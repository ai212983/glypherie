import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import type { BrowserContext } from "playwright-core";

test("coverage keeps scripts from every registered build regardless of the final page URL", async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-coverage-navigation-"));
  const previous = process.env.GLYPHERIE_COVERAGE_DIR;
  process.env.GLYPHERIE_COVERAGE_DIR = dir;
  t.after(async () => {
    if (previous === undefined) delete process.env.GLYPHERIE_COVERAGE_DIR;
    else process.env.GLYPHERIE_COVERAGE_DIR = previous;
    await fs.rm(dir, { recursive: true, force: true });
  });
  // Import after configuring the directory; browser-coverage captures it at module initialization.
  const { registerCoverageBuild, trackContextCoverage } = await import("../helpers/browser-coverage.ts");
  const firstRoot = path.join(dir, "first");
  const secondRoot = path.join(dir, "second");
  registerCoverageBuild("http://first.test", firstRoot, "/preview/");
  registerCoverageBuild("http://second.test", secondRoot, "/app/");
  const sourceMap = { version: 3, sources: ["src/app.ts"], names: [], mappings: "AAAA" };
  const source =
    "const value = 1;\n//# sourceMappingURL=data:application/json;base64," +
    Buffer.from(JSON.stringify(sourceMap)).toString("base64");
  const urls = ["http://first.test/preview/first.js", "http://second.test/app/second.js"];
  for (const finalUrl of ["http://first.test/preview/", "about:blank", "http://unregistered.test/"]) {
    await t.test(finalUrl, async () => {
      const before = new Set(await fs.readdir(dir));
      const page = {
        url: () => finalUrl,
        coverage: {
          startJSCoverage: async () => undefined,
          stopJSCoverage: async () =>
            [...urls, "http://unregistered.test/vendor.js"].map((url) => ({ url, source, functions: [] })),
        },
        close: async () => undefined,
      };
      const context = {
        newPage: async () => page,
        pages: () => [page],
        on: () => undefined,
        close: async () => undefined,
      } as unknown as BrowserContext;
      trackContextCoverage(context);
      const tracked = await context.newPage();
      await tracked.close();
      await context.close();
      const written = (await fs.readdir(dir)).filter((name) => !before.has(name));
      assert.equal(written.length, 1, "one coverage record survives page and context close");
      const saved = JSON.parse(await fs.readFile(path.join(dir, written[0]!), "utf8"));
      assert.deepEqual(
        saved.map((entry: { url: string }) => entry.url),
        urls,
      );
      assert.deepEqual(
        saved.map((entry: { scriptPath: string }) => entry.scriptPath),
        [path.join(firstRoot, "first.js"), path.join(secondRoot, "second.js")],
      );
      assert.ok(saved.every((entry: { mapStatus: string }) => entry.mapStatus === "ok"));
    });
  }
});
