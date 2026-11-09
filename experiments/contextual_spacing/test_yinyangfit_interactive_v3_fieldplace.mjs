// cspell:words yinyangfit
// Placement regression for the whole-text field view: each letter's slate
// must paint translated by its laid-out run origin.
// Glyph-local lattice + run origin = placed
// coords, the same translation the ink uses; map values never change here.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
function loadGlobal(path, name) {
  const sandbox = {};
  vm.createContext(sandbox);
  vm.runInContext(readFileSync(path, "utf8"), sandbox);
  assert.ok(sandbox[name], `${name} loads from ${path}`);
  return sandbox[name];
}
const YYV = loadGlobal(join(dir, "yinyangfit_interactive_v3_visual.js"), "YYVisual");

// Stub canvas recording every painted rect with its fill style.
function stubCanvas() {
  const rects = [];
  const ctx = {
    fillStyle: "#fff",
    setTransform() {},
    clearRect() {},
    fillRect(x, y, w, h) {
      rects.push({ x, y, w, h, style: ctx.fillStyle });
    },
  };
  return { rects, canvas: { width: 0, height: 0, style: {}, getContext: () => ctx } };
}

const emptyCell = { w: 1, h: 1, left: 0, top: 0, cover: [0] };
// Uniform glyph-local slate lattice: every lattice pixel paints.
function slateAt(x0, y0, w, h) {
  return { x0, y0, w, h, f: new Float64Array(w * h).fill(1) };
}
const alphas = { letter: 0.65, contrib: 1 };
const gains = { slate: 6, contrib: 4 };
const frame = { x0: -20, y0: -20, w: 200, h: 60 };

// One repeated letter at two laid-out origins: the same crop painted twice.
const F = slateAt(-11, -14, 30, 40);
function run(ox, oy) {
  return { cell: emptyCell, ox, oy };
}

function slateRects(fields, runs, zoom) {
  const stub = stubCanvas();
  YYV.drawExcerptField(stub.canvas, fields, frame, runs, "mono", [], alphas, zoom, gains);
  return stub.rects;
}

// Same values at different origins must paint shifted by the origin delta
// with unchanged local shape; the second letter must not reuse the first
// letter's pixels.
{
  const at0 = slateRects([F], [run(0, 0)], 1);
  const at80 = slateRects([F], [run(80, 0)], 1);
  assert.ok(at0.length > 0 && at80.length > 0, "slate paints");
  const set0 = new Set(at0.map((r) => r.x + "," + r.y));
  const set80 = new Set(at80.map((r) => r.x + "," + r.y));
  for (const r of at0) {
    assert.ok(set80.has(r.x + 80 + "," + r.y), `run at ox=80 repaints run-0 pixel (${r.x},${r.y}) shifted by +80`);
  }
  assert.equal(set80.size, set0.size, "translation keeps the local shape");
  const both = slateRects([F, F], [run(0, 0), run(80, 0)], 1);
  const right = both.filter((r) => r.x >= 69);
  assert.ok(right.length > 0, "displaced letter paints its own field at ox + lattice origin");
  assert.equal(right.length, at80.length, "displaced letter keeps its full translated shape");
}

// Zoom scales the translated paint without moving the source geometry.
{
  const z2 = slateRects([F], [run(80, 0)], 2);
  // PX(x) = (PAD_X + (x - frame.x0)) * z with PAD_X = 10.
  const wantX = (10 + (69 - frame.x0)) * 2;
  assert.ok(
    z2.some((r) => r.x === wantX),
    `2x paint starts at translated source px 69 (got ${z2[0]?.x})`,
  );
}

console.log("field placement checks passed");
