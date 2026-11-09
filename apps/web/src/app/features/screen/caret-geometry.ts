// Caret and selection geometry for in-place label editing, derived solely
// from the renderer's committed diagnostics.layout.editing stops. These
// helpers never measure browser glyphs: every coordinate comes from the WASM
// layout pass that painted the pixels on screen. Offsets are JS UTF-16 text
// boundaries; duplicate offsets at soft line breaks belong to two lines.
import type { RenderCaret, RenderEditing } from "../../renderer/client.js";

export interface VisualLine {
  index: number;
  start: number;
  end: number;
  y: number;
  height: number;
}

export interface CaretPosition {
  offset: number;
  line: number;
}

export type SelectionDirection = "forward" | "backward";

export interface SelectionRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

// Group caret stops into visual lines. A stop sitting on a soft break is
// claimed by both lines, so each line spans its own stops' offset range.
export function visualLines(editing: RenderEditing): VisualLine[] {
  const byLine = new Map<number, RenderCaret[]>();
  for (const stop of editing.carets) {
    const group = byLine.get(stop.line);
    if (group) group.push(stop);
    else byLine.set(stop.line, [stop]);
  }
  return [...byLine.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([index, stops]) => {
      let start = Number.POSITIVE_INFINITY;
      let end = Number.NEGATIVE_INFINITY;
      let y = stops[0]?.y ?? 0;
      let height = stops[0]?.height ?? 0;
      for (const stop of stops) {
        if (stop.offset < start) {
          start = stop.offset;
          y = stop.y;
          height = stop.height;
        }
        if (stop.offset > end) end = stop.offset;
      }
      return { index, start, end, y, height };
    });
}

// The x of one offset on one visual line. Exact stops always carry it; the
// nearest stop is a defensive fallback and never a browser measurement.
export function caretXOnLine(editing: RenderEditing, offset: number, line: number): number {
  let exact: RenderCaret | undefined;
  let nearest: RenderCaret | undefined;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const stop of editing.carets) {
    if (stop.line !== line) continue;
    if (stop.offset === offset) {
      exact = stop;
      break;
    }
    const distance = Math.abs(stop.offset - offset);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearest = stop;
    }
  }
  return (exact ?? nearest)?.x ?? 0;
}

// Pointer hit test in native source pixels: the line whose vertical span
// holds the point (clamped to the first/last line outside), then the nearest
// stop on that line.
export function offsetAtPoint(editing: RenderEditing, px: number, py: number): CaretPosition {
  const lines = visualLines(editing);
  if (lines.length === 0) return { offset: 0, line: 0 };
  let picked = lines[0]!;
  if (py < (lines[0]?.y ?? 0)) {
    picked = lines[0]!;
  } else {
    picked = lines[lines.length - 1]!;
    for (const line of lines) {
      if (py < line.y + line.height) {
        picked = line;
        break;
      }
    }
  }
  let best = Number.POSITIVE_INFINITY;
  let offset = picked.start;
  for (const stop of editing.carets) {
    if (stop.line !== picked.index) continue;
    const distance = Math.abs(stop.x - px);
    if (distance < best) {
      best = distance;
      offset = stop.offset;
    }
  }
  return { offset, line: picked.index };
}

// Per-line selection rectangles for [anchor, focus] in native source
// pixels. Collapsed selections draw a caret instead and yield no rects.
export function selectionRects(editing: RenderEditing, anchor: CaretPosition, focus: CaretPosition): SelectionRect[] {
  const low = Math.min(anchor.offset, focus.offset);
  const high = Math.max(anchor.offset, focus.offset);
  if (low === high) return [];
  const rects: SelectionRect[] = [];
  for (const line of visualLines(editing)) {
    const start = Math.max(low, line.start);
    const end = Math.min(high, line.end);
    if (start > end) continue;
    const x0 = caretXOnLine(editing, start, line.index);
    const x1 = caretXOnLine(editing, end, line.index);
    if (x1 > x0) rects.push({ x: x0, y: line.y, width: x1 - x0, height: line.height });
  }
  return rects;
}

// Visual-line up/down movement keeping a goal column across repeated moves.
// Ties prefer the smaller offset for determinism.
export function moveVertically(
  editing: RenderEditing,
  position: CaretPosition,
  xGoal: number,
  direction: 1 | -1,
): (CaretPosition & { x: number }) | null {
  const lines = visualLines(editing);
  if (lines.length === 0) return null;
  const current = lines.findIndex((line) => line.index === position.line);
  const next = Math.min(lines.length - 1, Math.max(0, (current < 0 ? 0 : current) + direction));
  const target = lines[next];
  if (!target) return null;
  let offset = target.start;
  let x = caretXOnLine(editing, offset, target.index);
  let best = Math.abs(x - xGoal);
  for (const stop of editing.carets) {
    if (stop.line !== target.index) continue;
    const distance = Math.abs(stop.x - xGoal);
    if (distance < best || (distance === best && stop.offset < offset)) {
      best = distance;
      offset = stop.offset;
      x = stop.x;
    }
  }
  return { offset, line: target.index, x };
}

export function lineRange(editing: RenderEditing, line: number): { start: number; end: number } {
  for (const entry of visualLines(editing)) {
    if (entry.index === line) return { start: entry.start, end: entry.end };
  }
  return { start: 0, end: 0 };
}

// setSelectionRange takes ordered endpoints plus the direction: passing
// anchor/focus raw throws (or selects wrong) for backward selections, so
// every programmatic sync goes through here.
export function normalizeRange(
  anchorOffset: number,
  focusOffset: number,
): { start: number; end: number; direction: SelectionDirection } {
  return anchorOffset <= focusOffset
    ? { start: anchorOffset, end: focusOffset, direction: "forward" }
    : { start: focusOffset, end: anchorOffset, direction: "backward" };
}

// Visual-line affinity of one offset against fresh geometry. Soft-break
// duplicates sit on two lines; keep the tracked line when it still contains
// the offset so a repaint never jumps the caret across the break.
export function resolveLineAffinity(editing: RenderEditing, offset: number, tracked: number): number {
  const lines = visualLines(editing);
  if (lines.some((entry) => entry.index === tracked && offset >= entry.start && offset <= entry.end)) {
    return tracked;
  }
  return lines.find((entry) => offset >= entry.start && offset <= entry.end)?.index ?? tracked;
}

// Overlay state mirroring one native textarea selection. "none" arrives for
// collapsed programmatic selections; backward selections swap the ends.
export function selectionFromNative(
  editing: RenderEditing,
  start: number,
  end: number,
  direction: SelectionDirection | "none",
  tracked?: { anchor: number; focus: number },
): { anchor: CaretPosition; focus: CaretPosition } {
  const backward = direction === "backward";
  const anchorOffset = backward ? end : start;
  const focusOffset = backward ? start : end;
  return {
    anchor: { offset: anchorOffset, line: resolveLineAffinity(editing, anchorOffset, tracked?.anchor ?? 0) },
    focus: { offset: focusOffset, line: resolveLineAffinity(editing, focusOffset, tracked?.focus ?? 0) },
  };
}
