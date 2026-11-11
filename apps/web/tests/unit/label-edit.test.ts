// Label edit core contract: the keyboard/selection/composition decisions at
// the DOM adapter seam, plus the draft/settle rules. Falsifies the key
// policy, cursor geometry outcomes and commit/cancel/ignore paths without a
// textarea or renderer. The fixture stands in for the renderer shape only;
// production coordinates always come from the committed WASM layout.
import assert from "node:assert/strict";
import test from "node:test";
import {
  LabelEditSession,
  classifyKey,
  lineEdge,
  moveCursor,
  resolveCaretLine,
  type EditKeyInput,
} from "../../src/app/features/screen/label-edit.ts";
import type { RenderEditing } from "../../src/app/renderer/client.ts";

// Two visual lines with a soft break duplicating offset 5 on both lines.
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

function key(overrides: Partial<EditKeyInput> = {}): EditKeyInput {
  return { key: "a", ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, composing: false, ...overrides };
}

test("escape cancels and ctrl+enter commits", () => {
  assert.deepEqual(classifyKey(key({ key: "Escape" })), { kind: "cancel" });
  assert.deepEqual(classifyKey(key({ key: "Enter", ctrlKey: true })), { kind: "commit" });
  assert.deepEqual(classifyKey(key({ key: "Enter", metaKey: true })), { kind: "commit" });
  // A plain Enter stays with the native textarea (newline), never commits.
  assert.deepEqual(classifyKey(key({ key: "Enter" })), { kind: "native" });
});

test("every composing key stays native, including arrows and home/end", () => {
  // The adapter must return these to the browser without preventDefault or
  // custom caret work: arrows move the IME candidate window, Enter confirms
  // the composition, Escape cancels it.
  for (const name of ["Escape", "Enter", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "a"]) {
    assert.deepEqual(classifyKey(key({ key: name, composing: true })), { kind: "native" }, name);
  }
  // Ctrl+Enter while composing still confirms the composition natively.
  assert.deepEqual(classifyKey(key({ key: "Enter", ctrlKey: true, composing: true })), { kind: "native" });
});

test("only unmodified cursor keys reach renderer geometry", () => {
  assert.deepEqual(classifyKey(key({ key: "ArrowDown" })), { kind: "cursor", key: "ArrowDown", extend: false });
  assert.deepEqual(classifyKey(key({ key: "Home", shiftKey: true })), { kind: "cursor", key: "Home", extend: true });
  // Remapped keys stay with the browser: word jumps, window shortcuts and
  // AltGraph input never move the label caret.
  assert.deepEqual(classifyKey(key({ key: "ArrowLeft", ctrlKey: true })), { kind: "native" });
  assert.deepEqual(classifyKey(key({ key: "ArrowUp", altKey: true })), { kind: "native" });
  assert.deepEqual(classifyKey(key({ key: "ArrowDown", metaKey: true })), { kind: "native" });
  assert.deepEqual(classifyKey(key({ key: "Home", ctrlKey: true })), { kind: "native" });
  assert.deepEqual(classifyKey(key({ key: "End", altKey: true })), { kind: "native" });
  assert.deepEqual(classifyKey(key({ key: "ArrowLeft" })), { kind: "native" });
  assert.deepEqual(classifyKey(key({ key: "a", ctrlKey: true })), { kind: "native" });
});

test("vertical motion keeps the goal column and honors extension", () => {
  const current = { anchor: { offset: 2, line: 0 }, focus: { offset: 2, line: 0 }, xGoal: 0, xGoalActive: false };
  const moved = moveCursor(editing(), current, { offset: 2, line: 0 }, "ArrowDown", false);
  assert.deepEqual(moved?.focus, { offset: 6, line: 1 });
  assert.equal(moved?.xGoalActive, true);
  // Extending keeps the tracked anchor while the focus follows.
  const extended = moveCursor(editing(), current, { offset: 2, line: 0 }, "ArrowDown", true);
  assert.deepEqual(extended?.anchor, { offset: 2, line: 0 });
  assert.deepEqual(extended?.focus, { offset: 6, line: 1 });
  // Past the edge the movement clamps instead of leaving the text.
  assert.deepEqual(moveCursor(editing(), null, { offset: 0, line: 0 }, "ArrowUp", false)?.focus, {
    offset: 0,
    line: 0,
  });
  // Without laid-out lines there is no move to commit.
  assert.equal(moveCursor({ width: 0, height: 0, carets: [] }, null, { offset: 0, line: 0 }, "ArrowUp", false), null);
});

test("line edges follow visual lines and backward affinity resolves", () => {
  const end = lineEdge(editing(), { offset: 2, line: 0 }, "End", false, null);
  assert.deepEqual(end.focus, { offset: 5, line: 0 });
  const home = lineEdge(editing(), { offset: 8, line: 1 }, "Home", true, {
    anchor: { offset: 2, line: 0 },
    focus: { offset: 8, line: 1 },
    xGoal: 0,
    xGoalActive: false,
  });
  assert.deepEqual(home.anchor, { offset: 2, line: 0 });
  assert.deepEqual(home.focus, { offset: 5, line: 1 });
  // An offset shared by adjacent lines keeps its tracked affinity.
  assert.deepEqual(resolveCaretLine(editing(), 5, 0), { offset: 5, line: 0 });
  assert.deepEqual(resolveCaretLine(editing(), 5, 1), { offset: 5, line: 1 });
});

test("the edit settles exactly once per session", () => {
  const session = new LabelEditSession("Text");
  assert.equal(session.settle(), true);
  // The blur fired by the commit's own focus move cannot resurrect or
  // duplicate the commit.
  assert.equal(session.settle(), false);
  assert.equal(session.settled, true);
});

test("blur commits changed text and confirms unchanged drafts", () => {
  const changed = new LabelEditSession("Text");
  assert.equal(
    changed.blurOutcome({ composing: false, focusedReload: false, draft: "Text!", savedText: "Text" }),
    "commit",
  );
  const unchanged = new LabelEditSession("Text");
  assert.equal(
    unchanged.blurOutcome({ composing: false, focusedReload: false, draft: "Text", savedText: "Text" }),
    "confirm",
  );
  // A blur ending an IME composition never commits half the composition.
  assert.equal(
    new LabelEditSession("Text").blurOutcome({
      composing: true,
      focusedReload: false,
      draft: "Tex",
      savedText: "Text",
    }),
    "ignore",
  );
  // Focus moving to the explicit discard control skips the commit.
  assert.equal(
    new LabelEditSession("Text").blurOutcome({
      composing: false,
      focusedReload: true,
      draft: "Text!",
      savedText: "Text",
    }),
    "ignore",
  );
});

test("a conflict rearms the session so the draft survives for recovery", () => {
  const session = new LabelEditSession("Text");
  assert.equal(session.settle(), true);
  session.rearm();
  assert.equal(session.settled, false);
  assert.equal(session.settle(), true);
});
