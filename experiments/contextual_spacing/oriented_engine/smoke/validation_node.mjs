import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const leaf = new URL("../", import.meta.url);
const web = await import(new URL("pkg-web/yinyang_oriented_engine.js", leaf));
web.initSync({ module: readFileSync(new URL("pkg-web/yinyang_oriented_engine_bg.wasm", leaf)) });

for (const key of ["q", "kappa", "eps"]) {
  for (const value of ["bad", null, true, []]) {
    assert.throws(
      () => new web.YinYangEngine(JSON.stringify({ [key]: value })),
      `${key} must reject ${JSON.stringify(value)}`,
    );
  }
}
for (const key of ["sigmas", "weights"]) {
  for (const value of ["bad", null, true]) {
    assert.throws(
      () => new web.YinYangEngine(JSON.stringify({ [key]: value })),
      `${key} must reject ${JSON.stringify(value)}`,
    );
  }
}
for (const value of [null, [], "bad", 4]) {
  assert.throws(() => new web.YinYangEngine(JSON.stringify(value)), "parameter JSON must be an object");
}
const engine = new web.YinYangEngine(JSON.stringify({ q: 2.125, radius: 12 }));
assert.equal(JSON.parse(engine.version()).params.q, 2.125);
for (const cp of [65, 66]) {
  engine.load_glyph("blank", "capture", cp, 1, 1, 0, 0, new Float64Array([0]));
}
const result = JSON.parse(engine.score_pair("blank", 65, 66, 8, new Int32Array([-2, 0, 2]), 0.5, "notebook", 4));
assert.equal(result.uncertainty, "uncertainty_not_certified");
console.log("WASM validation rejects malformed parameters; exact values and uncertainty metadata pass.");
