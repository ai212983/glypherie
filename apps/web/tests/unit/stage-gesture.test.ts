// Stage gesture core contract: native-pixel drag/resize math, anchored
// resize correction and pending preview reconciliation. Falsifies the public
// promises of the interaction core without Moveable or the DOM.
import assert from "node:assert/strict";
import test from "node:test";
import {
  AwaitedResizeCommit,
  correctedResizePosition,
  dragNativeDelta,
  movePreviewClears,
  previewSuperseded,
  releasedPosition,
  resizeEstimates,
  resizePreviewClears,
  type AwaitedRelease,
} from "../../src/app/features/screen/stage-gesture.ts";

test("drag deltas convert through cssScale to rounded native pixels", () => {
  assert.deepEqual(dragNativeDelta([10, 4], 2), { dx: 5, dy: 2 });
  // Fractional scales round to the device grid, never truncate toward zero.
  assert.deepEqual(dragNativeDelta([3, -4], 2), { dx: 2, dy: -2 });
  assert.deepEqual(dragNativeDelta([1, 1], 3), { dx: 0, dy: 0 });
});

test("resize estimates scale from the gesture start with domain clamps", () => {
  const start = { fontSize: 16, width: 200, boxWidth: 100, boxHeight: 20 };
  // Doubling the frame doubles the size and grows the wrap width by the
  // cssScale-corrected delta.
  assert.deepEqual(resizeEstimates(start, 200, 2), { fontSize: 32, width: 250 });
  // Extreme inward drags pin to the domain minimum instead of vanishing.
  assert.deepEqual(resizeEstimates(start, 1, 2), { fontSize: 1, width: 151 });
  assert.deepEqual(resizeEstimates({ fontSize: 16, width: 10, boxWidth: 100, boxHeight: 20 }, 1, 2), {
    fontSize: 1,
    width: 1,
  });
  // Non-finite spans never produce a commit candidate.
  assert.equal(resizeEstimates(start, Number.NaN, 2), null);
});

test("opposite ink corners anchor the released position", () => {
  const anchor = { x: 4, y: 2, width: 40, height: 12 };
  const measured = { x: 2, y: 1, width: 44, height: 14 };
  // A southeast drag fixes the northwest corner: the far corner lands where
  // the gesture started it.
  assert.deepEqual(correctedResizePosition(10, 20, anchor, [1, 1], measured), { x: 12, y: 21 });
  // A northwest drag fixes the southeast corner instead.
  assert.deepEqual(correctedResizePosition(10, 20, anchor, [-1, -1], measured), { x: 8, y: 19 });
});

test("releases fall back to the drag translation without measured paint", () => {
  assert.deepEqual(releasedPosition({ x: 10, y: 20 }, [7, -4], 2), { x: 14, y: 18 });
});

test("pending move previews clear only against the matching saved render", () => {
  assert.equal(movePreviewClears({ id: "a", x: 12, y: 20 }, { id: "a", x: 12, y: 20 }), true);
  assert.equal(movePreviewClears({ id: "a", x: 12, y: 20 }, { id: "a", x: 13, y: 20 }), false);
  // A label that left the scene releases its preview instead of hanging it.
  assert.equal(movePreviewClears(null, { id: "a", x: 12, y: 20 }), true);
});

test("pending resize previews clear against size, width and position together", () => {
  const pending = { id: "a", fontSize: 16, width: 200, x: 10, y: 20 };
  assert.equal(resizePreviewClears({ id: "a", x: 10, y: 20, fontSize: 16, width: 200 }, pending), true);
  assert.equal(resizePreviewClears({ id: "a", x: 10, y: 20, fontSize: 18, width: 200 }, pending), false);
});

test("a reference switch supersedes the direct-font gesture", () => {
  // Variant geometry must come only from its saved style, never from a stale
  // direct-font preview.
  assert.equal(previewSuperseded(null, "a"), true);
  assert.equal(previewSuperseded({ id: "a", textStyleId: "style-1" }, "a"), true);
  assert.equal(previewSuperseded({ id: "a", textStyleId: null }, "a"), false);
});

function release(): AwaitedRelease {
  return {
    id: "a",
    text: "Text",
    fontSize: 16,
    width: 200,
    fallbackX: 10,
    fallbackY: 20,
    anchorBaseX: 10,
    anchorBaseY: 20,
    anchorInk: { x: 0, y: 0, width: 40, height: 12 },
    lastDirection: [1, 1],
  };
}

test("an awaited release commits exactly once", () => {
  const waiter = new AwaitedResizeCommit();
  waiter.arm(release());
  const first = waiter.fulfill({ x: 0, y: 0, width: 44, height: 14 });
  assert.ok(first);
  assert.equal(first.release.id, "a");
  // A late paint, an error flush and the bounded wait cannot write twice.
  assert.equal(waiter.fulfill({ x: 0, y: 0, width: 44, height: 14 }), null);
  assert.equal(
    waiter.flush({ text: "Text", sizePx: 16, width: 200, ink: { x: 0, y: 0, width: 44, height: 14 } }),
    null,
  );
  assert.equal(waiter.pendingId, null);
});

test("an inkless repaint commits the drag translation", () => {
  // The fallback carries the release's own drag translation, since no later
  // repaint of the same inputs can measure more.
  const waiter = new AwaitedResizeCommit();
  waiter.arm({ ...release(), fallbackX: 11, fallbackY: 21 });
  const commit = waiter.fulfill(null);
  assert.deepEqual(commit && { x: commit.x, y: commit.y }, { x: 11, y: 21 });
});

test("a flush without a matching paint commits the translation", () => {
  const waiter = new AwaitedResizeCommit();
  waiter.arm(release());
  // Paint failure, unmount and the bounded wait share this path.
  const commit = waiter.flush(null);
  assert.deepEqual(commit && { x: commit.x, y: commit.y }, { x: 10, y: 20 });
  assert.equal(waiter.pendingId, null);
});

test("a flush against a stale repaint commits the translation", () => {
  const waiter = new AwaitedResizeCommit();
  waiter.arm(release());
  // A mid-gesture repaint for older inputs never corrects the release.
  const commit = waiter.flush({ text: "Older", sizePx: 16, width: 200, ink: { x: 0, y: 0, width: 44, height: 14 } });
  assert.deepEqual(commit && { x: commit.x, y: commit.y }, { x: 10, y: 20 });
  const sized = new AwaitedResizeCommit();
  sized.arm(release());
  const resized = sized.flush({ text: "Text", sizePx: 18, width: 200, ink: { x: 0, y: 0, width: 44, height: 14 } });
  assert.deepEqual(resized && { x: resized.x, y: resized.y }, { x: 10, y: 20 });
});
