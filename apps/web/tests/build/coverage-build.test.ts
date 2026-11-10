import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { buildApp } from "../helpers/spa-helpers.ts";

// Coverage builds are opt-in (GLYPHERIE_COVERAGE=1): the default production
// build must carry no sourcemaps or instrumentation references, so test and
// release bytes stay identical with and without the coverage producer.
test("production build carries no coverage maps by default", async (t) => {
  const output = await buildApp(t);
  const assets = path.join(output, "assets");
  const names = await fs.readdir(assets);
  assert.deepEqual(
    names.filter((name) => name.endsWith(".map")),
    [],
    "no sourcemap files in the default build",
  );
  const scripts = names.filter((name) => name.endsWith(".js"));
  assert.ok(scripts.length > 0, "build emits app scripts");
  for (const name of scripts) {
    const text = await fs.readFile(path.join(assets, name), "utf8");
    assert.doesNotMatch(text, /sourceMappingURL/, `${name} has no sourcemap reference`);
  }
});
