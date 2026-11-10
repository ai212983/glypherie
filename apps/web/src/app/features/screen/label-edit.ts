// Cohesive label-edit interaction core: the keyboard, selection and
// composition decisions at the DOM adapter seam, plus the draft/settle rules.
// Framework-free and DOM-free: EditableLabel owns the textarea, IME events,
// caret/selection overlay, pointer capture, native undo and renderer paint,
// and calls into this core for every outcome. Native textarea edit history,
// backward selection direction and composition behavior stay with the DOM
// adapter; this core owns what each key means and what each cursor gesture
// resolves to against renderer geometry.
//
// The adapter applies outcomes and never reinterprets them: a "native"
// action returns to the browser without preventDefault or custom caret work,
// so composing arrows keep driving the IME candidate window instead of the
// label caret.
import type { RenderEditing } from "../../renderer/client.ts";
import { caretXOnLine, lineRange, moveVertically, resolveLineAffinity, type CaretPosition } from "./caret-geometry.ts";

export interface SelectionState {
  anchor: CaretPosition;
  focus: CaretPosition;
  xGoal: number;
  xGoalActive: boolean;
}

export type EditKeyAction =
  // The browser owns the key: typing, arrows, word jumps, select-all, native
  // edit undo and every key while composing. The adapter must not
  // preventDefault it or run custom caret geometry for it.
  | { kind: "native" }
  | { kind: "commit" }
  | { kind: "cancel" }
  // Renderer-geometry cursor motion: only Up/Down/Home/End without
  // remapping modifiers reach the wrapped WASM layout.
  | { kind: "cursor"; key: "ArrowUp" | "ArrowDown" | "Home" | "End"; extend: boolean };

export interface EditKeyInput {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  composing: boolean;
}

// The single key policy: IME owns every key while composing (Enter confirms
// the composition natively and must not commit, Escape cancels it natively,
// arrows move the candidate window); Ctrl/Cmd+Enter commits; Escape cancels;
// plain Enter stays with the native textarea. Only unmodified Up/Down/Home/
// End need renderer geometry, since browser rows follow the capture box
// rather than the wrapped WASM layout.
export function classifyKey(input: EditKeyInput): EditKeyAction {
  if (input.composing) return { kind: "native" };
  if (input.key === "Escape") return { kind: "cancel" };
  if (input.key === "Enter") {
    return input.ctrlKey || input.metaKey ? { kind: "commit" } : { kind: "native" };
  }
  if ((input.key === "ArrowUp" || input.key === "ArrowDown") && !input.altKey && !input.ctrlKey && !input.metaKey) {
    return { kind: "cursor", key: input.key, extend: input.shiftKey };
  }
  if ((input.key === "Home" || input.key === "End") && !input.ctrlKey && !input.metaKey && !input.altKey) {
    return { kind: "cursor", key: input.key, extend: input.shiftKey };
  }
  return { kind: "native" };
}

// Vertical cursor motion against renderer stops, keeping the sticky goal
// column across lines. Null when the edge clamps instead of moving.
export function moveCursor(
  geometry: RenderEditing,
  current: SelectionState | null,
  focus: CaretPosition,
  key: "ArrowUp" | "ArrowDown",
  extend: boolean,
): SelectionState | null {
  const direction = key === "ArrowDown" ? 1 : -1;
  const goal = current?.xGoalActive === true ? current.xGoal : caretXOnLine(geometry, focus.offset, focus.line);
  const moved = moveVertically(geometry, focus, goal, direction as 1 | -1);
  if (!moved) return null;
  if (extend && current) {
    return {
      anchor: current.anchor,
      focus: { offset: moved.offset, line: moved.line },
      xGoal: goal,
      xGoalActive: true,
    };
  }
  return {
    anchor: { offset: moved.offset, line: moved.line },
    focus: { offset: moved.offset, line: moved.line },
    xGoal: goal,
    xGoalActive: true,
  };
}

// Line-edge motion follows visual lines, not the whole text.
export function lineEdge(
  geometry: RenderEditing,
  focus: CaretPosition,
  key: "Home" | "End",
  extend: boolean,
  current: SelectionState | null,
): SelectionState {
  const range = lineRange(geometry, focus.line);
  const edge = key === "Home" ? range.start : range.end;
  const endpoint: CaretPosition = { offset: edge, line: focus.line };
  if (extend && current) {
    return { anchor: current.anchor, focus: endpoint, xGoal: 0, xGoalActive: false };
  }
  return { anchor: endpoint, focus: endpoint, xGoal: 0, xGoalActive: false };
}

// Resolves an endpoint onto its visual line, keeping the tracked affinity
// for offsets shared by adjacent lines (soft breaks, surrogate pairs). The
// DOM adapter reads the true native endpoint (selectionStart for the focus
// end of a backward selection) and applies the resolved line.
export function resolveCaretLine(geometry: RenderEditing, offset: number, lineHint: number): CaretPosition {
  return { offset, line: resolveLineAffinity(geometry, offset, lineHint) };
}

export type BlurOutcome =
  // Persist the changed draft through the revisioned store.
  | "commit"
  // The draft matches the saved text, yet still routes through the commit
  // path so a no-op edit settles consistently instead of branching.
  | "confirm"
  // Never commit: an IME composition in flight, or focus moving to the
  // explicit discard control whose unmount drops the draft.
  | "ignore";

export interface BlurState {
  composing: boolean;
  focusedReload: boolean;
  draft: string;
  savedText: string;
}

// One in-place edit session: the edit settles exactly once, so the blur
// fired by a commit/cancel focus move (or by the unmount that follows)
// cannot resurrect a discarded draft or duplicate a commit into a revision
// conflict. A conflict or failure rearms the session so the draft survives
// for recovery and the next gesture settles it.
export class LabelEditSession {
  private done = false;
  readonly initialText: string;

  constructor(initialText: string) {
    this.initialText = initialText;
  }

  get settled(): boolean {
    return this.done;
  }

  blurOutcome(state: BlurState): BlurOutcome {
    // A blur that ends an IME composition must not commit half of it; the
    // committed text arrives through change events and the next explicit
    // gesture settles the edit.
    if (state.composing) return "ignore";
    // Focus moving to the explicit discard control skips the commit: the
    // reload adopts the saved revision and the unmount drops the draft, so
    // committing first would only resurrect it behind a conflict.
    if (state.focusedReload) return "ignore";
    if (state.draft !== state.savedText) return "commit";
    return "confirm";
  }

  // Arms the settle exactly once; returns false when an earlier gesture
  // already settled this session.
  settle(): boolean {
    if (this.done) return false;
    this.done = true;
    return true;
  }

  rearm(): void {
    this.done = false;
  }
}
