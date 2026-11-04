// Pure caret-geometry coverage: synthetic editing stops exercise the line
// grouping, hit testing and movement rules. These fixtures stand in for the
// renderer contract shape only; production coordinates always come from the
// committed WASM layout, never from browser metrics.
import assert from "node:assert/strict";
import test from "node:test";
import {
  caretXOnLine,
  lineRange,
  moveVertically,
  normalizeRange,
  offsetAtPoint,
  resolveLineAffinity,
  selectionFromNative,
  selectionRects,
  visualLines,
} from "../../src/app/features/screen/caret-geometry.ts";
import type { RenderEditing } from "../../src/app/renderer/client.ts";

// Two visual lines with a soft break duplicating offset 5 on both lines, plus
// a surrogate pair (offsets 6..8) on the second line.
function editing(): RenderEditing {
  return {
    width: 60,
    height: 28,
    carets: [
      { offset: 0, line: 0, x: 0, y: 0, height: 14 },
      { offset: 2, line: 0, x: 20, y: 0, height: 14 },
      { offset: 5, line: 0, x: 50, y: 0, height: 14 },
      { offset: 5, line: 1, x: 0, y: 14, height: 14 },
      { offset: 6, line: 1, x: 10, y: 14, height: 14 },
      { offset: 8, line: 1, x: 30, y: 14, height: 14 },
    ],
  };
}

test("soft-break duplicates belong to both visual lines", () => {
  const lines = visualLines(editing());
  assert.deepEqual(lines.map((line) => [line.index, line.start, line.end]), [[0, 0, 5], [1, 5, 8]]);
});

test("pointer hits pick the containing line then the nearest stop", () => {
  assert.deepEqual(offsetAtPoint(editing(), 48, 4), { offset: 5, line: 0 });
  // Same offset exists on both lines; the y span decides the affinity.
  assert.deepEqual(offsetAtPoint(editing(), 2, 20), { offset: 5, line: 1 });
  assert.deepEqual(offsetAtPoint(editing(), 29, 20), { offset: 8, line: 1 });
  // Outside the text clamps to the first/last line and nearest stop.
  assert.deepEqual(offsetAtPoint(editing(), -40, -40), { offset: 0, line: 0 });
  assert.deepEqual(offsetAtPoint(editing(), 400, 400), { offset: 8, line: 1 });
});

test("selection rects span visual lines without collapsing", () => {
  const rects = selectionRects(editing(), { offset: 2, line: 0 }, { offset: 8, line: 1 });
  assert.equal(rects.length, 2);
  assert.deepEqual([rects[0]?.x, rects[0]?.width], [20, 30]);
  assert.deepEqual([rects[1]?.x, rects[1]?.width], [0, 30]);
  assert.deepEqual(selectionRects(editing(), { offset: 2, line: 0 }, { offset: 2, line: 0 }), []);
});

test("vertical movement keeps the goal column across lines", () => {
  const down = moveVertically(editing(), { offset: 2, line: 0 }, 20, 1);
  assert.deepEqual([down?.offset, down?.line], [6, 1]);
  const up = moveVertically(editing(), { offset: 8, line: 1 }, 30, -1);
  assert.deepEqual([up?.offset, up?.line], [2, 0]);
  // Past the edges the movement clamps instead of leaving the text.
  const top = moveVertically(editing(), { offset: 0, line: 0 }, 0, -1);
  assert.deepEqual([top?.offset, top?.line], [0, 0]);
});

test("line home and end follow visual lines, not the whole text", () => {
  assert.deepEqual(lineRange(editing(), 0), { start: 0, end: 5 });
  assert.deepEqual(lineRange(editing(), 1), { start: 5, end: 8 });
  assert.equal(caretXOnLine(editing(), 5, 1), 0);
  assert.equal(caretXOnLine(editing(), 8, 1), 30);
});

test("programmatic ranges normalize endpoints and keep the direction", () => {
  assert.deepEqual(normalizeRange(2, 2), { start: 2, end: 2, direction: "forward" });
  assert.deepEqual(normalizeRange(2, 8), { start: 2, end: 8, direction: "forward" });
  // Backward drags pass the larger anchor first; the ordered range still
  // reports backward so the focus end survives the round trip.
  assert.deepEqual(normalizeRange(8, 2), { start: 2, end: 8, direction: "backward" });
});

test("line affinity keeps the tracked soft-break side across repaints", () => {
  // Offset 5 duplicates on both lines; each side keeps its own affinity.
  assert.equal(resolveLineAffinity(editing(), 5, 0), 0);
  assert.equal(resolveLineAffinity(editing(), 5, 1), 1);
  // Offsets owned by one line move there; unknown lines fall back.
  assert.equal(resolveLineAffinity(editing(), 2, 1), 0);
  assert.equal(resolveLineAffinity(editing(), 8, 0), 1);
});

test("native selections mirror with their direction intact", () => {
  const forward = selectionFromNative(editing(), 2, 8, "forward");
  assert.deepEqual([forward.anchor.offset, forward.focus.offset], [2, 8]);
  const backward = selectionFromNative(editing(), 2, 8, "backward");
  assert.deepEqual([backward.anchor.offset, backward.focus.offset], [8, 2]);
  assert.deepEqual([backward.anchor.line, backward.focus.line], [1, 0]);
  const collapsed = selectionFromNative(editing(), 6, 6, "none");
  assert.deepEqual([collapsed.anchor.offset, collapsed.focus.offset], [6, 6]);
});

test("selection rects span a surrogate pair without splitting it", () => {
  // Offsets 6..8 are one multi-code-unit character on the second line.
  const rects = selectionRects(editing(), { offset: 6, line: 1 }, { offset: 8, line: 1 });
  assert.equal(rects.length, 1);
  assert.deepEqual([rects[0]?.x, rects[0]?.width], [10, 20]);
});
