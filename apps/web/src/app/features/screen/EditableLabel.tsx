// One scene label: WASM-rendered bitmap, tight selection frame and in-place
// editing. The visible text is always the committed FontCanvas paint; a
// transparent native textarea captures typing, selection, clipboard and IME
// while the caret and selection overlay draw solely from the committed
// diagnostics.layout.editing geometry. Missing geometry disables editing
// with a visible notice instead of approximating glyph positions.
import * as React from "react";
import { TooltipHint } from "../../../components/TooltipHint.js";
import { FontCanvas, type FontCanvasDiagnostics } from "../../renderer/FontCanvas.js";
import type { RenderEditing } from "../../renderer/client.js";
import type { VariantSettings } from "../../variants/model.js";
import type { RGBA } from "../../renderer/renderer-types.js";
import type { DomainPlacementView } from "../scenes/service.js";
import {
  LabelEditSession,
  classifyKey,
  lineEdge,
  moveCursor,
  resolveCaretLine,
  type SelectionState,
} from "./label-edit.ts";
import {
  caretXOnLine,
  normalizeRange,
  offsetAtPoint,
  selectionFromNative,
  selectionRects,
  visualLines,
  type CaretPosition,
} from "./caret-geometry.js";

interface InkBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface EditableLabelProps {
  placement: DomainPlacementView;
  fontId: string;
  settings: VariantSettings;
  ready: boolean;
  // Native request framebuffer: the label wraps at the scene's right/bottom.
  labelWidth: number;
  labelHeight: number;
  // CSS px per native device px; positions are integer device px.
  cssScale: number;
  palette: RGBA[];
  selected: boolean;
  editing: boolean;
  resizing?: boolean;
  clipped: boolean;
  onSelect: (id: string) => void;
  onBeginEdit: (id: string) => void;
  // Resolves false when the text could not persist (conflict or failure),
  // leaving the draft open for recovery.
  onCommitText: (id: string, text: string) => Promise<boolean>;
  onCancelEdit: () => void;
  onRenderError: (message: string) => void;
  onRenderOk: () => void;
  // Every committed paint reports the frame bounds it renders (tight ink, or
  // the renderer text extent when nothing painted) in native device px, with
  // the paint inputs that produced it. Resize anchoring consumes this to
  // place the committed position against real renderer geometry.
  onFrameGeometry?: (
    placementId: string,
    box: { x: number; y: number; width: number; height: number } | null,
    sizePx: number,
    width: number,
    text: string,
  ) => void;
  onFrameElement: (id: string, element: HTMLDivElement | null) => void;
  onNudge: (id: string, dx: number, dy: number) => void;
  onDeleteKey: (id: string) => void;
}

function clampOffset(text: string, offset: number): number {
  return Math.min(text.length, Math.max(0, offset));
}

// Tight ink bounds of the committed display canvas in native device px, or
// null when nothing painted (blank text, blanked error canvas). Alpha-only:
// the label palette keeps level 0 fully transparent so stacked labels never
// hide each other, which makes non-transparent pixels exactly the ink.
function measureInk(canvas: HTMLCanvasElement | null, labelWidth: number, shown: number): InkBox | null {
  if (!canvas || canvas.width === 0 || canvas.height === 0 || labelWidth <= 0 || shown <= 0) return null;
  let context: CanvasRenderingContext2D | null = null;
  try {
    context = canvas.getContext("2d", { alpha: true });
  } catch {
    return null;
  }
  if (!context) return null;
  let data: ImageData;
  try {
    data = context.getImageData(0, 0, canvas.width, canvas.height);
  } catch {
    return null;
  }
  let found = false;
  let bx0 = 0;
  let by0 = 0;
  let bx1 = 0;
  let by1 = 0;
  const pixels = data.data;
  for (let by = 0; by < canvas.height; by += 1) {
    for (let bx = 0; bx < canvas.width; bx += 1) {
      if (pixels[(by * canvas.width + bx) * 4 + 3] === 0) continue;
      if (!found) {
        bx0 = bx1 = bx;
        by0 = by1 = by;
        found = true;
      } else {
        if (bx < bx0) bx0 = bx;
        if (bx > bx1) bx1 = bx;
        if (by > by1) by1 = by;
      }
    }
  }
  if (!found) return null;
  const scaleX = canvas.width / labelWidth;
  const scaleY = canvas.height / shown;
  const x0 = Math.max(0, Math.floor(bx0 / scaleX));
  const x1 = Math.min(labelWidth, Math.ceil((bx1 + 1) / scaleX));
  const y0 = Math.max(0, Math.floor(by0 / scaleY));
  const y1 = Math.min(shown, Math.ceil((by1 + 1) / scaleY));
  if (x1 <= x0 || y1 <= y0) return null;
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

// Fallback frame from renderer geometry when no ink painted (blank or
// newline-only text): the laid-out text extent at the first line's origin.
function geometryBox(editing: RenderEditing): InkBox {
  const lines = visualLines(editing);
  const first = lines[0];
  let minX = Number.POSITIVE_INFINITY;
  for (const stop of editing.carets) {
    if (stop.x < minX) minX = stop.x;
  }
  if (!Number.isFinite(minX)) minX = 0;
  return {
    x: minX,
    y: first?.y ?? 0,
    width: Math.max(2, editing.width),
    height: editing.height > 0 ? editing.height : (first?.height ?? 0),
  };
}

export function EditableLabel(props: EditableLabelProps): React.JSX.Element {
  const { placement, fontId, settings, ready, labelWidth, labelHeight, cssScale, selected, editing, clipped } = props;
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const frameRef = React.useRef<HTMLDivElement | null>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const selectNewTextRef = React.useRef(editing);
  const editStartPointRef = React.useRef<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = React.useState<string | null>(null);
  const [paint, setPaint] = React.useState<{ geometry: RenderEditing; key: string } | null>(null);
  const [paintError, setPaintError] = React.useState("");
  const [inkBox, setInkBox] = React.useState<InkBox | null>(null);
  const [selection, setSelection] = React.useState<SelectionState | null>(null);
  const [, setSelectionTick] = React.useState(0);
  const selectionRef = React.useRef<SelectionState | null>(null);
  const paintRef = React.useRef(paint);
  const editingRef = React.useRef(editing);
  const dragRef = React.useRef(false);
  const composingRef = React.useRef(false);
  // Guards select events fired by our own setSelectionRange writes; native
  // edits still report through onSelect and are mirrored, never rewritten.
  const programmaticRef = React.useRef(false);
  // One edit session per in-place edit: commit and cancel both settle it
  // synchronously, so the blur fired by their own focus moves (or by the
  // unmount that follows) cannot resurrect a discarded draft or duplicate a
  // commit into a revision conflict. The core owns the settle rules; the
  // textarea owns native history, selection and composition behavior.
  const editSessionRef = React.useRef<LabelEditSession | null>(null);
  const displayText = editing && draft !== null ? draft : placement.text;

  // Every input that changes the WASM layout. A progressive resize paint
  // can precede the latest requested size; a paint whose key differs from
  // this one must not place the caret or hit-test the current draft.
  const renderKey = React.useMemo(
    () =>
      JSON.stringify({
        text: displayText,
        font: fontId,
        settings,
        frame: [labelWidth, labelHeight],
      }),
    [displayText, fontId, settings, labelWidth, labelHeight],
  );
  const renderKeyRef = React.useRef(renderKey);

  editingRef.current = editing;
  paintRef.current = paint;
  renderKeyRef.current = renderKey;

  // The committed canvas always matches the stored paint; only the overlay
  // needs the freshness gate against the draft.
  const committed = paint?.geometry ?? null;
  const geometry = paint && paint.key === renderKey ? paint.geometry : null;

  const currentGeometry = React.useCallback((): RenderEditing | null => {
    const current = paintRef.current;
    return current && current.key === renderKeyRef.current ? current.geometry : null;
  }, []);

  const pointInLabel = React.useCallback(
    (clientX: number, clientY: number): { x: number; y: number } | null => {
      const box = containerRef.current?.getBoundingClientRect();
      if (!box || box.width <= 0 || box.height <= 0) return null;
      return {
        x: (clientX - box.left) * (labelWidth / box.width),
        y: (clientY - box.top) * (labelHeight / box.height),
      };
    },
    [labelHeight, labelWidth],
  );

  const setSelectionState = React.useCallback((next: SelectionState | null) => {
    selectionRef.current = next;
    setSelection(next);
  }, []);

  // Drafts start from the saved text when editing begins and are discarded
  // when it ends; remote placement updates never overwrite an open draft.
  React.useEffect(() => {
    if (editing && draft === null) {
      editSessionRef.current = new LabelEditSession(placement.text);
      setDraft(placement.text);
      setSelectionState(null);
      setPaintError("");
    } else if (!editing) {
      editStartPointRef.current = null;
      editSessionRef.current = null;
      if (draft !== null) {
        setDraft(null);
        setSelectionState(null);
      }
    }
  }, [editing, draft, placement.text, setSelectionState]);

  // Writes one overlay state into the native textarea with ordered
  // endpoints; every programmatic sync goes through here.
  const writeSelection = React.useCallback((textarea: HTMLTextAreaElement, next: SelectionState) => {
    const { start, end, direction } = normalizeRange(next.anchor.offset, next.focus.offset);
    programmaticRef.current = true;
    try {
      textarea.setSelectionRange(start, end, direction);
    } catch {
      // The value may still hold the previous draft; input syncs it.
    }
    queueMicrotask(() => {
      programmaticRef.current = false;
    });
  }, []);

  // Mirrors the native textarea selection into the overlay without writing
  // back, so native arrows, word jumps, select-all and native undo just
  // work. Skipped when nothing moved, which breaks the programmatic
  // write/select-event loop.
  const mirrorTextarea = React.useCallback(
    (textarea: HTMLTextAreaElement) => {
      const value = textarea.value;
      const start = clampOffset(value, textarea.selectionStart);
      const end = clampOffset(value, textarea.selectionEnd);
      const direction = textarea.selectionDirection === "backward" ? "backward" : "forward";
      const tracked = selectionRef.current;
      const fresh = currentGeometry();
      let next: SelectionState;
      if (fresh) {
        next = {
          ...selectionFromNative(
            fresh,
            start,
            end,
            direction,
            tracked ? { anchor: tracked.anchor.line, focus: tracked.focus.line } : undefined,
          ),
          xGoal: 0,
          xGoalActive: false,
        };
      } else if (tracked) {
        const backward = direction === "backward";
        next = {
          anchor: { offset: backward ? end : start, line: tracked.anchor.line },
          focus: { offset: backward ? start : end, line: tracked.focus.line },
          xGoal: 0,
          xGoalActive: false,
        };
      } else {
        return;
      }
      const current = selectionRef.current;
      if (
        current &&
        current.anchor.offset === next.anchor.offset &&
        current.anchor.line === next.anchor.line &&
        current.focus.offset === next.focus.offset &&
        current.focus.line === next.focus.line
      ) {
        return;
      }
      selectionRef.current = next;
      setSelection(next);
    },
    [currentGeometry],
  );

  // Layout timing: the draft (and its textarea) initializes in a passive
  // effect one commit after editing starts, so focusing must wait for the
  // textarea to exist and must beat the browser's blur-to-body. A passive
  // focus here would either hit a stale ref or lose the race. A fresh paint
  // adopts the native selection (the source of truth, never reset here);
  // only a missing selection seeds the caret. Newly placed text starts selected
  // so typing replaces its placeholder. Pointer entry seeds from its native
  // hit point; keyboard entry starts at the end.
  React.useLayoutEffect(() => {
    if (!editing || draft === null) return;
    const textarea = textareaRef.current;
    if (textarea && document.activeElement !== textarea) textarea.focus({ preventScroll: true });
    if (textarea && selectNewTextRef.current) {
      // Select the placeholder before the renderer is ready, so immediate
      // typing replaces it even while the first paint is still pending.
      const initial: SelectionState = {
        anchor: { offset: 0, line: 0 },
        focus: { offset: textarea.value.length, line: 0 },
        xGoal: 0,
        xGoalActive: false,
      };
      selectNewTextRef.current = false;
      selectionRef.current = initial;
      setSelection(initial);
      writeSelection(textarea, initial);
    }
    const fresh = currentGeometry();
    if (!fresh) return;
    if (!selectionRef.current) {
      const lines = visualLines(fresh);
      const last = lines[lines.length - 1];
      const point = editStartPointRef.current;
      const { offset, line } = point
        ? offsetAtPoint(fresh, point.x, point.y)
        : { offset: last?.end ?? 0, line: last?.index ?? 0 };
      editStartPointRef.current = null;
      const seeded: SelectionState = {
        anchor: { offset, line },
        focus: { offset, line },
        xGoal: caretXOnLine(fresh, offset, line),
        xGoalActive: false,
      };
      selectionRef.current = seeded;
      setSelection(seeded);
      if (textarea) writeSelection(textarea, seeded);
    } else if (textarea) {
      mirrorTextarea(textarea);
    }
  }, [editing, draft, paint, currentGeometry, mirrorTextarea, writeSelection]);

  // The paint target stays FontCanvas's own ref: consumer canvasProps must
  // not carry a ref (the spread would detach the internal paint target and
  // paints would skip silently). Ink measurement queries the committed
  // canvas through the label container instead.
  const findCanvas = React.useCallback((): HTMLCanvasElement | null => {
    const container = containerRef.current;
    return container?.querySelector("canvas") ?? null;
  }, []);

  const canvasProps = React.useMemo(
    () => ({
      className: "block [image-rendering:pixelated]",
    }),
    [],
  );

  // Stable across renders: an inline ref callback would detach and reattach
  // on every render, and each detach would notify the parent again.
  // onFrameElement is a stable parent callback, so this identity only turns
  // over when the placement itself changes.
  const onFrameElement = props.onFrameElement;
  const frameRefCallback = React.useCallback(
    (element: HTMLDivElement | null) => {
      frameRef.current = element;
      onFrameElement(placement.id, element);
    },
    [placement.id, onFrameElement],
  );

  const viewportProps = React.useMemo(
    () => ({
      "data-scene-label": placement.id,
      role: "img",
      "aria-label": displayText,
    }),
    [placement.id, displayText],
  );

  const handlePaint = React.useCallback(
    (diagnostics: FontCanvasDiagnostics) => {
      const editingGeometry = diagnostics.layout?.editing ?? null;
      if (editingGeometry) {
        setPaint({ geometry: editingGeometry, key: renderKey });
        setPaintError("");
        props.onRenderOk();
      } else {
        setPaint(null);
        // Honest absence: fixture and synthetic renderers omit editing, and the
        // real path always reports it. Never approximate with browser metrics.
        props.onRenderError(
          `Label "${diagnostics.missing > 0 ? "…" : placement.text}" has no editing geometry in this preview.`,
        );
      }
      const shown = Math.min(labelHeight, Math.max(1, diagnostics.fullHeight));
      const ink = measureInk(findCanvas(), labelWidth, shown);
      setInkBox(ink);
      // Report the same frame the render below draws, so anchoring consumes
      // measured renderer bounds instead of an assumed rectangle.
      props.onFrameGeometry?.(
        placement.id,
        ink ?? (editingGeometry ? geometryBox(editingGeometry) : null),
        settings.sizePx,
        labelWidth,
        displayText,
      );
      // Seeding and line re-resolution run in the layout effect above, which
      // observes the new paint: the native selection is never reset here.
    },
    [findCanvas, labelHeight, labelWidth, displayText, placement.text, props, settings.sizePx, renderKey],
  );

  const handleError = React.useCallback(
    (message: string) => {
      // A failed paint blanks the canvas (clearOnError), so the committed
      // geometry goes with it; the draft text is kept for recovery on input.
      setPaint(null);
      setInkBox(null);
      setPaintError(message);
      props.onRenderError(`Label "${placement.text}": ${message}`);
    },
    [placement.text, props],
  );

  const applySelection = React.useCallback(
    (next: SelectionState) => {
      setSelectionState({ ...next, xGoalActive: false });
      setSelectionTick((tick) => tick + 1);
      const textarea = textareaRef.current;
      if (textarea) writeSelection(textarea, next);
    },
    [setSelectionState, writeSelection],
  );

  // Pointer hit testing against renderer caret stops, in native device px.
  // Stale geometry (input not yet repainted) refuses the hit so the caret
  // cannot land on a previous layout's stops.
  const hitTest = React.useCallback(
    (clientX: number, clientY: number): CaretPosition | null => {
      const geometry = currentGeometry();
      const point = pointInLabel(clientX, clientY);
      return geometry && point ? offsetAtPoint(geometry, point.x, point.y) : null;
    },
    [currentGeometry, pointInLabel],
  );

  // Non-editing selection lives on the tight frame below; the full-aperture
  // container only captures pointer drags for WASM caret placement while
  // editing (it is click-through otherwise, so stacked labels and empty
  // paper resolve by stacking order).
  const onFramePointerDown = React.useCallback(() => {
    if (editing) return;
    props.onSelect(placement.id);
    // The drag engine suppresses the mousedown default, so a click would
    // otherwise leave focus on the body and arrow keys dead. Focusing the
    // frame here makes click-then-nudge work; tabbing reaches it through
    // tabIndex and selects through onFocus.
    frameRef.current?.focus({ preventScroll: true });
  }, [editing, placement.id, props]);

  const onFrameDoubleClick = React.useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      // Suppress the browser's default word-select-and-focus pass, which
      // would otherwise move focus to the nearest focusable ancestor after
      // the capture textarea already took it.
      event.preventDefault();
      if (editing) return;
      if (paintRef.current) {
        // Keep the native point through draft/textarea mounting, then resolve
        // against fresh renderer stops before setting the native selection.
        editStartPointRef.current = pointInLabel(event.clientX, event.clientY);
        props.onBeginEdit(placement.id);
      } else props.onRenderError(`Label "${placement.text}" has no editing geometry in this preview.`);
    },
    [editing, placement.id, placement.text, pointInLabel, props],
  );

  const onPointerDown = React.useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!editing) return;
      if (event.button !== 0) return;
      event.preventDefault();
      const hit = hitTest(event.clientX, event.clientY);
      const geometry = currentGeometry();
      if (hit && geometry) {
        applySelection({
          anchor: hit,
          focus: hit,
          xGoal: caretXOnLine(geometry, hit.offset, hit.line),
          xGoalActive: false,
        });
      }
      dragRef.current = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      textareaRef.current?.focus();
    },
    [applySelection, currentGeometry, editing, hitTest],
  );

  const onPointerMove = React.useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!editing || !dragRef.current) return;
      const hit = hitTest(event.clientX, event.clientY);
      const current = selectionRef.current;
      const geometry = currentGeometry();
      if (hit && current && geometry) {
        // The anchor stays fixed while the focus follows the pointer either
        // way; the ordered write in applySelection keeps backward drags as one
        // real native range so typing replaces it.
        const next: SelectionState = {
          anchor: current.anchor,
          focus: hit,
          xGoal: caretXOnLine(geometry, hit.offset, hit.line),
          xGoalActive: false,
        };
        applySelection(next);
      }
    },
    [applySelection, currentGeometry, editing, hitTest],
  );

  const endPointerDrag = React.useCallback(() => {
    dragRef.current = false;
  }, []);

  // Post-settle commit body shared by explicit gestures and blur: the caller
  // owns the settle decision through the edit core, this only performs the
  // revisioned write and the recovery/focus handoff.
  const commitSettledDraft = React.useCallback(
    async (edit: LabelEditSession, text: string, refocus: boolean) => {
      const ok = await props.onCommitText(placement.id, text);
      // A conflict or failure keeps the draft open for recovery, so rearm
      // the session and let the next gesture settle the edit instead.
      if (!ok) edit.rearm();
      // A conflict keeps the draft open for recovery; only a completed edit
      // returns focus to the frame.
      if (ok && refocus && !editingRef.current) frameRef.current?.focus();
    },
    [placement.id, props],
  );

  const commitDraft = React.useCallback(
    async (refocus: boolean) => {
      const edit = editSessionRef.current;
      const text = draft;
      if (edit === null || text === null || !edit.settle()) return;
      await commitSettledDraft(edit, text, refocus);
    },
    [commitSettledDraft, draft],
  );

  const cancelDraft = React.useCallback(() => {
    if (!editSessionRef.current?.settle()) return;
    props.onCancelEdit();
  }, [props]);

  // Only Up/Down/Home/End reach renderer geometry, and only through the
  // core's cursor decision; every other key stays with the browser (arrows,
  // word jumps, select-all, native edit undo, and the whole IME). onSelect
  // mirrors native selection into the overlay. The adapter applies the
  // core's outcomes and never reinterprets a native action.
  const onTextareaKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      const action = classifyKey({
        key: event.key,
        ctrlKey: event.ctrlKey,
        metaKey: event.metaKey,
        altKey: event.altKey,
        shiftKey: event.shiftKey,
        composing: event.nativeEvent.isComposing || composingRef.current,
      });
      if (action.kind === "native") return;
      if (action.kind === "cancel") {
        event.preventDefault();
        cancelDraft();
        frameRef.current?.focus();
        return;
      }
      if (action.kind === "commit") {
        event.preventDefault();
        void commitDraft(true);
        return;
      }
      const textarea = event.currentTarget;
      const geometry = currentGeometry();
      if (!geometry) return;
      const text = textarea.value;
      // The true focus end: selectionStart for backward selections, so moves
      // from a backward caret extend the side the user sees.
      const backward = textarea.selectionDirection === "backward";
      const tracked = selectionRef.current;
      const focus = resolveCaretLine(
        geometry,
        clampOffset(text, backward ? textarea.selectionStart : textarea.selectionEnd),
        tracked?.focus.line ?? 0,
      );
      const current = selectionRef.current;
      const commitKeySelection = (next: SelectionState): void => {
        setSelectionState(next);
        setSelectionTick((tick) => tick + 1);
        writeSelection(textarea, next);
      };
      event.preventDefault();
      if (action.key === "ArrowUp" || action.key === "ArrowDown") {
        const next = moveCursor(geometry, current, focus, action.key, action.extend);
        if (!next) return;
        commitKeySelection(next);
        return;
      }
      commitKeySelection(lineEdge(geometry, focus, action.key, action.extend, current));
    },
    [cancelDraft, commitDraft, currentGeometry, setSelectionState, writeSelection],
  );

  const onTextareaChange = React.useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      setDraft(event.target.value);
      // The browser owns the native selection through typing (surrogate pairs
      // stay safe: every offset is a UTF-16 index into the same string the
      // stops describe); mirror it and drop the sticky goal column. Fresh
      // lines resolve once the repaint commits; the stale overlay hides until
      // then.
      mirrorTextarea(event.target);
    },
    [mirrorTextarea],
  );

  const onTextareaSelect = React.useCallback(
    (event: React.SyntheticEvent<HTMLTextAreaElement>) => {
      if (programmaticRef.current) return;
      mirrorTextarea(event.currentTarget);
    },
    [mirrorTextarea],
  );

  const onTextareaBlur = React.useCallback(
    (event: React.FocusEvent<HTMLTextAreaElement>) => {
      // A clear commit gesture: leaving the field persists the draft through
      // the revisioned store instead of discarding typed text. The settled arm
      // ignores the blur that a commit/cancel focus move or unmount fires.
      const edit = editSessionRef.current;
      if (edit === null || draft === null) return;
      const outcome = edit.blurOutcome({
        composing: composingRef.current,
        focusedReload:
          event.relatedTarget instanceof HTMLElement && event.relatedTarget.closest("[data-screen-reload]") !== null,
        draft,
        savedText: placement.text,
      });
      // A blur that ends an IME composition must not commit half of it; the
      // committed text arrives through change events and the next explicit
      // gesture settles the edit. Focus moving to the explicit discard
      // control skips the commit: the reload adopts the saved revision and
      // the unmount drops the draft, so committing first would only resurrect
      // it behind a conflict.
      if (outcome === "ignore" || !edit.settle()) return;
      if (outcome === "commit") void commitSettledDraft(edit, draft, false);
      else void props.onCommitText(placement.id, draft);
    },
    [commitSettledDraft, draft, placement.id, placement.text, props],
  );

  const onFrameKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Enter") {
        event.preventDefault();
        props.onBeginEdit(placement.id);
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        props.onDeleteKey(placement.id);
        return;
      }
      const step = event.shiftKey ? 10 : 1;
      if (
        event.key === "ArrowLeft" ||
        event.key === "ArrowRight" ||
        event.key === "ArrowUp" ||
        event.key === "ArrowDown"
      ) {
        event.preventDefault();
        const dx = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
        const dy = event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
        props.onNudge(placement.id, dx, dy);
      }
    },
    [placement.id, props],
  );

  const frameBox: InkBox | null = inkBox ?? (committed ? geometryBox(committed) : null);
  const overlaySelection = selection ?? null;
  // The overlay draws from fresh geometry only: after input, style or frame
  // changes it hides until the matching paint commits.
  const caret: (CaretPosition & { x: number; y: number; height: number }) | null = React.useMemo(() => {
    if (!geometry || !overlaySelection) return null;
    if (overlaySelection.anchor.offset !== overlaySelection.focus.offset) return null;
    const { offset, line } = overlaySelection.focus;
    const entry = visualLines(geometry).find((candidate) => candidate.index === line);
    return { offset, line, x: caretXOnLine(geometry, offset, line), y: entry?.y ?? 0, height: entry?.height ?? 0 };
  }, [geometry, overlaySelection]);
  const rects = React.useMemo(() => {
    if (!geometry || !overlaySelection) return [];
    return selectionRects(geometry, overlaySelection.anchor, overlaySelection.focus);
  }, [geometry, overlaySelection]);

  const focusCaret = overlaySelection
    ? { offset: overlaySelection.focus.offset, line: overlaySelection.focus.line }
    : null;
  const focusX = focusCaret && geometry ? caretXOnLine(geometry, focusCaret.offset, focusCaret.line) : 0;
  const focusLine =
    focusCaret && geometry ? visualLines(geometry).find((entry) => entry.index === focusCaret.line) : undefined;

  return (
    <div
      ref={containerRef}
      data-scene-label-container={placement.id}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endPointerDrag}
      onPointerCancel={endPointerDrag}
      style={{
        position: "absolute",
        left: placement.x * cssScale,
        top: placement.y * cssScale,
        width: Math.max(1, labelWidth * cssScale),
        height: Math.max(1, labelHeight * cssScale),
        zIndex: placement.order,
        // Click-through outside editing: with every label's bitmap box
        // inert, clicks land on the tightest frame above the ink (stacking
        // order decides overlaps) and empty paper reaches the stage, which
        // clears the selection. The pointer-events inheritance keeps the
        // whole subtree inert; only the frame below re-enables events.
        pointerEvents: editing ? "auto" : "none",
      }}
    >
      <FontCanvas
        fontId={fontId}
        text={displayText}
        sizePx={settings.sizePx}
        axes={settings.axes}
        profile={settings.profile}
        role="candidate"
        spacing={settings.letterSpacingPx}
        kerning={settings.kerning}
        stemFitting={settings.stemFitting}
        diagonalFitting={settings.diagonalFitting}
        monoRaster={settings.monoRaster}
        rasterization={settings.rasterization}
        zoom={1}
        mode="exact"
        nativeSize={{ width: labelWidth, height: labelHeight }}
        cssScale={cssScale}
        compact
        ready={ready}
        clearOnError
        debounceMs={0}
        progressiveResize={props.resizing && !editing}
        palette={props.palette}
        viewportProps={viewportProps}
        canvasProps={canvasProps}
        canvasFallback="Label preview unavailable."
        onPaint={handlePaint}
        onError={handleError}
      />
      {/* Tight selection frame over the measured ink (or the renderer text
      extent for blank text), never the full remaining aperture. The frame
      is the hit target for every non-editing label, selected or not; the
      Moveable drag frame attaches here and is unmounted while editing.
      The frame draws no outline of its own: Moveable's lines are the single
      visible selection outline, so the two can never diverge into a pair. */}
      <div
        ref={frameRefCallback}
        data-scene-label-frame={placement.id}
        tabIndex={editing ? -1 : 0}
        role="button"
        aria-label={`Label ${placement.text || "(blank)"}. Press Enter to edit.`}
        aria-selected={selected}
        onKeyDown={onFrameKeyDown}
        onFocus={() => props.onSelect(placement.id)}
        onPointerDown={onFramePointerDown}
        onDoubleClick={onFrameDoubleClick}
        style={
          frameBox
            ? {
                position: "absolute",
                left: frameBox.x * cssScale,
                top: frameBox.y * cssScale,
                width: Math.max(1, frameBox.width * cssScale),
                height: Math.max(1, frameBox.height * cssScale),
                outline: "none",
                pointerEvents: editing ? "none" : "auto",
                cursor: editing ? "text" : "move",
                touchAction: "none",
              }
            : {
                position: "absolute",
                inset: 0,
                outline: "none",
                pointerEvents: "none",
              }
        }
      />
      {clipped && (
        <span
          data-scene-label-clipped={placement.id}
          style={{
            position: "absolute",
            right: 0,
            top: 0,
            fontSize: 10,
            lineHeight: 1.4,
            padding: "0 4px",
            background: "var(--color-destructive)",
            color: "var(--color-destructive-foreground)",
            pointerEvents: "none",
          }}
        >
          Clipped
        </span>
      )}
      {(paintError || (!committed && selected)) && (
        <TooltipHint
          content={paintError ? `Preview failed; text kept: ${paintError}` : "No editing geometry in this preview."}
        >
          <span
            data-scene-label-unavailable={placement.id}
            role={paintError ? "alert" : "status"}
            tabIndex={0}
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              fontSize: 10,
              lineHeight: 1.4,
              padding: "0 4px",
              background: "var(--color-card)",
              color: "var(--color-soft)",
              border: "1px solid var(--color-line)",
              pointerEvents: "auto",
              maxWidth: "100%",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {paintError ? `Preview failed; text kept: ${paintError}` : "No editing geometry in this preview."}
          </span>
        </TooltipHint>
      )}
      {/* Caret and selection overlay drawn only from renderer stops. */}
      {editing && geometry && overlaySelection && (
        <div aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
          {rects.map((rect, index) => (
            <div
              key={index}
              data-scene-edit-selection={placement.id}
              style={{
                position: "absolute",
                left: rect.x * cssScale,
                top: rect.y * cssScale,
                width: Math.max(1, rect.width * cssScale),
                height: rect.height * cssScale,
                background: "color-mix(in srgb, var(--color-brand) 30%, transparent)",
              }}
            />
          ))}
          {caret && (
            <div
              data-scene-edit-caret={placement.id}
              style={{
                position: "absolute",
                left: caret.x * cssScale,
                top: caret.y * cssScale,
                width: 2,
                height: caret.height * cssScale,
                background: "#000",
              }}
            />
          )}
        </div>
      )}
      {/* Native text capture: invisible glyphs, caret and selection; the
      overlay above is the only visible caret. Kept on the focus caret so IME
      candidate windows anchor near the edit point. */}
      {editing && draft !== null && (
        <textarea
          ref={textareaRef}
          data-scene-edit-text={placement.id}
          className="scene-edit-textarea"
          aria-label={`Edit label text, currently ${placement.text || "blank"}`}
          aria-multiline="true"
          value={draft}
          rows={1}
          wrap="off"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          tabIndex={-1}
          onChange={onTextareaChange}
          onKeyDown={onTextareaKeyDown}
          onSelect={onTextareaSelect}
          onBlur={onTextareaBlur}
          onCompositionStart={() => {
            composingRef.current = true;
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
          }}
          style={{
            position: "absolute",
            left: Math.max(0, focusX * cssScale - 2),
            top: (focusLine?.y ?? 0) * cssScale,
            width: 12,
            height: Math.max(8, (focusLine?.height ?? 8) * cssScale),
            padding: 0,
            margin: 0,
            border: "none",
            outline: "none",
            resize: "none",
            overflow: "hidden",
            whiteSpace: "pre",
            caretColor: "transparent",
            pointerEvents: "none",
            fontSize: Math.max(8, (focusLine?.height ?? 8) * cssScale),
            lineHeight: 1,
            zIndex: 1,
          }}
        />
      )}
    </div>
  );
}
