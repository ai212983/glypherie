// Scene stage: positioned WASM label layers over the screen paper with a
// react-moveable frame around the selected label's tight ink box. All
// coordinates entering the store are integer native device pixels; the
// cssScale presentation factor only converts pointer deltas and display
// sizes. Moveable is unmounted while a label edits text. Moveable's own
// lines are the single visible selection outline (the label frame draws
// none); Moveable also owns the drag hit geometry, so its cached rect must
// be refreshed whenever the committed label moves or resizes. Variant-backed
// labels drag only and show a grey outline; direct-font labels also resize,
// which changes their own renderer font size and saved wrap width.
import * as React from "react";
import Moveable from "react-moveable";
import type { VariantSettings } from "../../variants/model.js";
import type { RGBA } from "../../renderer/renderer-types.js";
import type { DomainPlacementView } from "../scenes/service.js";
import { EditableLabel } from "./EditableLabel.js";
import {
  AwaitedResizeCommit,
  dragNativeDelta,
  movePreviewClears,
  previewSuperseded,
  releasedPosition,
  resizeEstimates,
  resizePreviewClears,
} from "./stage-gesture.ts";

export interface StagePaint {
  fontId: string;
  settings: VariantSettings;
  ready: boolean;
  palette: RGBA[];
}

export interface StagePlacementPreview {
  id: string;
  x: number;
  y: number;
  fontSize?: number;
  width?: number;
}

export interface SceneStageProps {
  sceneWidth: number;
  sceneHeight: number;
  placements: DomainPlacementView[];
  // Keyed by placement id: variant and direct labels paint from different
  // sources and never share an entry.
  paints: Map<string, StagePaint>;
  // CSS px per native device px.
  cssScale: number;
  paperCss: string;
  // View-only native-pixel grid overlay; hidden unless zoom is above 100%.
  showGrid?: boolean;
  selectedId: string | null;
  editingId: string | null;
  tool: "select" | "text";
  onAddText: (x: number, y: number) => void;
  onMeasureLabel?: (id: string, width: number, height: number) => void;
  onPlacementPreview?: (preview: StagePlacementPreview) => void;
  onSelect: (id: string | null) => void;
  onBeginEdit: (id: string) => void;
  onCommitText: (id: string, text: string) => Promise<boolean>;
  onCancelEdit: () => void;
  // Resolves true once the move persists; false leaves the saved position
  // (conflict or failure) so the stage can release its pending preview.
  onCommitMove: (id: string, x: number, y: number) => Promise<boolean>;
  // Resize releases persist the label's own font size and wrap width together
  // with the anchored position in one revisioned save; the same handoff
  // rules as moves apply.
  onCommitResize: (id: string, fontSize: number, width: number, x: number, y: number) => Promise<boolean>;
  onNudge: (id: string, dx: number, dy: number) => void;
  onDeleteKey: (id: string) => void;
  onRenderError: (message: string) => void;
  onRenderOk: () => void;
}

// One gradient pair draws a canvas grid of 8 native device px cells at the
// fractional pitch 8 * cssScale (never integer-rounded, so origin and pitch
// stay exact at any zoom). A per-pixel pitch would alias into moire bands
// where the effective scale drops below 1 CSS px per native px; the 8px
// cell keeps one uniform readable spacing on every device. The line stays a
// small fraction of the pitch, capped at 1 CSS px, so the mesh stays subtle.
// https://www.w3.org/TR/css-images-3/#repeating-gradients
export const PIXEL_GRID_CELL_PX = 8;
function pixelGridOverlayStyle(cssScale: number): React.CSSProperties {
  const pitch = (Number.isFinite(cssScale) && cssScale > 0 ? cssScale : 1) * PIXEL_GRID_CELL_PX;
  const line = Math.min(1, pitch / 4);
  const color = "rgb(71 85 105 / 0.45)";
  return {
    position: "absolute",
    inset: 0,
    // Never intercepts canvas gestures; the stage keeps hit-testing labels.
    // https://www.w3.org/TR/css-ui-4/#pointer-events-control
    pointerEvents: "none",
    backgroundImage:
      `repeating-linear-gradient(to right, ${color} 0, ${color} ${line}px, transparent ${line}px, transparent ${pitch}px), ` +
      `repeating-linear-gradient(to bottom, ${color} 0, ${color} ${line}px, transparent ${line}px, transparent ${pitch}px)`,
  };
}

export function SceneStage(props: SceneStageProps): React.JSX.Element {
  const { sceneWidth, sceneHeight, placements, paints, cssScale, showGrid, onMeasureLabel, onPlacementPreview } = props;
  const framesRef = React.useRef(new Map<string, HTMLDivElement>());
  const dragStartRef = React.useRef<{ id: string; x: number; y: number } | null>(null);
  const resizeStartRef = React.useRef<{
    id: string;
    width: number;
    fontSize: number;
    boxWidth: number;
    boxHeight: number;
    x: number;
    y: number;
    // Cumulative resize translation in screen px from the latest OnResize
    // drag; the release commits the anchored position from this, never from
    // an end-event payload shape.
    lastDrag: readonly [number, number] | null;
    // Which corner handle drives the gesture ([-1,-1] is northwest); the
    // opposite ink corner stays fixed.
    lastDirection: readonly [number, number] | null;
    // Position and renderer frame bounds the gesture started from, in native
    // device px, when a committed paint for them was recorded. The release
    // corrects the position against the repaint's measured bounds, so the
    // opposite corner anchors against real geometry instead of a stretched
    // rectangle. Null when no committed paint was recorded: the release
    // commits the drag translation as-is.
    anchorBaseX: number;
    anchorBaseY: number;
    anchorInk: { x: number; y: number; width: number; height: number } | null;
  } | null>(null);
  // Latest reported renderer frame bounds per label, with the paint inputs
  // that produced them. Resize releases match the repaint of the released
  // size against this before committing, so one revisioned save carries the
  // position corrected against measured geometry.
  const inkByIdRef = React.useRef(
    new Map<
      string,
      {
        text: string;
        sizePx: number;
        width: number;
        ink: { x: number; y: number; width: number; height: number } | null;
      }
    >(),
  );
  // A release whose save waits for the repaint of the released size. The
  // pending preview already shows the released values; the write fires once
  // the measured bounds land (or the fallback after a paint failure or a
  // bounded wait), exactly once per release. The interaction core owns the
  // position math and the exactly-once outcome; the adapter owns the timer
  // and performs the commit the core decides.
  const resizeWaiter = React.useMemo(() => new AwaitedResizeCommit(), []);
  const awaitingTimeoutRef = React.useRef<number | null>(null);
  const clearAwaitingTimeout = React.useCallback((): void => {
    if (awaitingTimeoutRef.current !== null) {
      window.clearTimeout(awaitingTimeoutRef.current);
      awaitingTimeoutRef.current = null;
    }
  }, []);
  const clearAwaitingRelease = React.useCallback((): void => {
    clearAwaitingTimeout();
    resizeWaiter.cancel();
  }, [clearAwaitingTimeout, resizeWaiter]);
  const commitResizeRef = React.useRef(props.onCommitResize);
  commitResizeRef.current = props.onCommitResize;
  const moveableRef = React.useRef<Moveable | null>(null);
  const [, setMoveableTick] = React.useState(0);

  // Pending release preview: the released integer position stays visible
  // while the revisioned save is queued, so no frame repaints the old
  // coordinates. Per useOptimistic, the preview reconciles once the
  // authoritative props catch up and rolls back on rejection.
  const [pendingMove, setPendingMove] = React.useState<{ id: string; x: number; y: number } | null>(null);
  // Pending resize preview: the released font size, wrap width and anchored
  // position repaint through the real renderer while the save is queued, with
  // the same reconcile-or-roll-back handoff as moves.
  const [pendingResize, setPendingResize] = React.useState<{
    id: string;
    fontSize: number;
    width: number;
    x: number;
    y: number;
  } | null>(null);
  const pendingResizeRef = React.useRef(pendingResize);
  pendingResizeRef.current = pendingResize;

  const displayed = React.useMemo(() => {
    let next = placements;
    if (pendingMove) {
      let moved = false;
      next = next.map((placement) => {
        if (placement.id !== pendingMove.id) return placement;
        if (placement.x === pendingMove.x && placement.y === pendingMove.y) return placement;
        moved = true;
        return { ...placement, x: pendingMove.x, y: pendingMove.y };
      });
      if (!moved) next = placements;
    }
    if (pendingResize) {
      const preview = pendingResize;
      let resized = false;
      next = next.map((placement) => {
        if (placement.id !== preview.id || placement.textStyleId !== null) return placement;
        if (
          placement.fontSize === preview.fontSize &&
          placement.width === preview.width &&
          placement.x === preview.x &&
          placement.y === preview.y
        ) {
          return placement;
        }
        resized = true;
        return { ...placement, fontSize: preview.fontSize, width: preview.width, x: preview.x, y: preview.y };
      });
      if (!resized) next = pendingMove ? next : placements;
    }
    return next;
  }, [placements, pendingMove, pendingResize]);

  // The handoff clears only after the saved coordinates render (or the
  // pending label leaves the scene), never when the async command merely
  // returns while props are still old. Failures clear through the commit
  // acknowledgment below, restoring the authoritative position with the
  // existing recovery UI.
  React.useLayoutEffect(() => {
    if (!pendingMove) return;
    if (
      movePreviewClears(
        placements.find((placement) => placement.id === pendingMove.id),
        pendingMove,
      )
    ) {
      setPendingMove(null);
    }
  }, [placements, pendingMove]);

  // Resize handoff mirrors the move handoff against the label's own size,
  // wrap width and anchored position.
  React.useLayoutEffect(() => {
    if (!pendingResize) return;
    const canonical = placements.find((placement) => placement.id === pendingResize.id) ?? null;
    // A reference switch supersedes the direct-font gesture, including its
    // deferred save; variant geometry must come only from its saved style.
    if (previewSuperseded(canonical, pendingResize.id)) {
      if (resizeWaiter.peek()?.id === pendingResize.id) clearAwaitingRelease();
      setPendingResize(null);
      return;
    }
    if (canonical && resizePreviewClears(canonical, pendingResize)) {
      setPendingResize(null);
    }
  }, [placements, pendingResize, resizeWaiter, clearAwaitingRelease]);

  const ordered = React.useMemo(
    () => [...displayed].sort((left, right) => left.order - right.order || (left.id < right.id ? -1 : 1)),
    [displayed],
  );

  // Fires one awaited resize release with the given position, then hands the
  // preview to the usual reconcile-or-roll-back path. Exactly-once per
  // release: firing clears the waiter first, so late paints, errors and
  // the bounded wait cannot write twice.
  const fireResizeCommit = React.useCallback(
    (release: { id: string; fontSize: number; width: number }, x: number, y: number): void => {
      clearAwaitingRelease();
      setPendingResize({ id: release.id, fontSize: release.fontSize, width: release.width, x, y });
      onPlacementPreview?.({ id: release.id, fontSize: release.fontSize, width: release.width, x, y });
      void commitResizeRef.current(release.id, release.fontSize, release.width, x, y).then(
        (ok) => {
          if (!ok) {
            setPendingResize((current) =>
              current !== null &&
              current.id === release.id &&
              current.fontSize === release.fontSize &&
              current.width === release.width &&
              current.x === x &&
              current.y === y
                ? null
                : current,
            );
          }
        },
        () => {
          setPendingResize((current) =>
            current !== null &&
            current.id === release.id &&
            current.fontSize === release.fontSize &&
            current.width === release.width &&
            current.x === x &&
            current.y === y
              ? null
              : current,
          );
        },
      );
    },
    [clearAwaitingRelease, onPlacementPreview],
  );

  // Best-effort flush of an awaited release: corrected against measured
  // bounds when they already match, otherwise the drag translation. Used
  // when a new gesture starts on the same label, when a paint fails, and on
  // unmount, so a release never stalls without a save.
  const flushAwaitingResize = React.useCallback((): void => {
    const awaiting = resizeWaiter.peek();
    if (!awaiting) return;
    const commit = resizeWaiter.flush(inkByIdRef.current.get(awaiting.id) ?? null);
    if (commit) fireResizeCommit(commit.release, commit.x, commit.y);
  }, [fireResizeCommit, resizeWaiter]);

  // A failing paint cannot produce the bounds a release waits for; commit
  // whatever the waiter has instead of stalling the save.
  const onRenderError = React.useCallback(
    (message: string) => {
      flushAwaitingResize();
      props.onRenderError(message);
    },
    [flushAwaitingResize, props],
  );

  // Every committed label paint reports its measured frame bounds. A release
  // waiting for exactly these paint inputs commits its position corrected so
  // the opposite ink corner lands where the gesture started it; an inkless
  // paint for the awaited inputs commits the drag translation, since no
  // later repaint of the same inputs can measure more.
  const onFrameGeometry = React.useCallback(
    (
      placementId: string,
      box: { x: number; y: number; width: number; height: number } | null,
      sizePx: number,
      width: number,
      text: string,
    ): void => {
      inkByIdRef.current.set(placementId, { text, sizePx, width, ink: box });
      if (box) onMeasureLabel?.(placementId, box.width, box.height);
      // The core commits exactly once when the repaint of the awaited inputs
      // lands; an inkless paint commits the drag translation, since no later
      // repaint of the same inputs can measure more.
      const awaiting = resizeWaiter.peek();
      if (!awaiting || awaiting.id !== placementId) return;
      if (awaiting.text !== text || awaiting.fontSize !== sizePx || awaiting.width !== width) return;
      const commit = resizeWaiter.fulfill(box);
      if (commit) fireResizeCommit(commit.release, commit.x, commit.y);
    },
    [fireResizeCommit, onMeasureLabel, resizeWaiter],
  );

  // A release waiting for its repaint must not die with the stage: commit
  // best-effort on unmount.
  React.useEffect(() => () => flushAwaitingResize(), [flushAwaitingResize]);

  // Inline ref callbacks detach/attach on every render, so only bump the
  // Moveable target when membership actually changes; otherwise parent and
  // child re-renders ping-pong forever.
  const onFrameElement = React.useCallback((id: string, element: HTMLDivElement | null) => {
    if (element) {
      if (framesRef.current.get(id) === element) return;
      framesRef.current.set(id, element);
    } else {
      if (!framesRef.current.delete(id)) return;
    }
    setMoveableTick((tick) => tick + 1);
  }, []);

  const selected = selectedIdSelected(
    props.selectedId,
    displayed.filter((placement) => placement.visible !== false),
  );
  const selectedIsDirect = selected !== null && selected.textStyleId === null;
  const canonicalSelected = selectedIdSelected(props.selectedId, placements);
  const moveableTarget =
    props.tool === "select" && !props.editingId && selected ? (framesRef.current.get(selected.id) ?? null) : null;
  const selectedX = selected?.x;
  const selectedY = selected?.y;

  // The drag applies its transform to the label container (the frame's
  // parent), and commits reposition through the container's left/top, so the
  // target itself never carries a style change for Moveable's observers to
  // see. Refresh its cached rect explicitly once the commit has rendered;
  // the pending preview above moves the same left/top, so this observes the
  // displayed position and keeps the hit geometry on the visible bitmap.
  // Target resizes (text/font changes) arrive via useResizeObserver below.
  // Per Moveable's own contract (updateRect docs): a stale rect is a broken
  // hit target, not just a stale picture.
  React.useLayoutEffect(() => {
    if (moveableTarget) moveableRef.current?.updateRect();
  }, [moveableTarget, selectedX, selectedY, canonicalSelected?.fontSize, canonicalSelected?.width, cssScale]);

  return (
    // Clip paint and Moveable controls at the same device-canvas boundary.
    // overflow: clip also forbids focus/programmatic scrolling of the canvas:
    // https://www.w3.org/TR/css-overflow-3/#valdef-overflow-clip
    <div
      style={{
        position: "relative",
        width: Math.max(1, sceneWidth * cssScale),
        height: Math.max(1, sceneHeight * cssScale),
        overflow: "clip",
      }}
    >
      <div
        data-scene-stage
        role="application"
        aria-label={`Scene canvas, ${sceneWidth} by ${sceneHeight} pixels`}
        onPointerDown={(event) => {
          // Clicking empty paper clears the selection; label containers stop
          // this by selecting first (their handler runs before this bubbles).
          if (event.target === event.currentTarget) props.onSelect(null);
        }}
        style={{
          position: "relative",
          width: Math.max(1, sceneWidth * cssScale),
          height: Math.max(1, sceneHeight * cssScale),
          backgroundColor: props.paperCss,
          overflow: "clip",
        }}
      >
        {ordered
          .filter((placement) => placement.visible !== false)
          .map((placement) => {
            const paint = paints.get(placement.id);
            if (!paint) return null;
            // Variant labels wrap at the scene's right/bottom edges; direct
            // labels wrap at their own saved width, live-previewed while a
            // resize gesture or release save is pending.
            const preview = placement.textStyleId === null && pendingResize?.id === placement.id ? pendingResize : null;
            const settings = preview ? { ...paint.settings, sizePx: preview.fontSize } : paint.settings;
            const labelWidth =
              placement.textStyleId !== null
                ? Math.max(1, sceneWidth - placement.x)
                : Math.max(1, preview?.width ?? placement.width ?? 1);
            const labelHeight = Math.max(1, sceneHeight - placement.y);
            const clipped =
              placement.x < 0 || placement.y < 0 || placement.x >= sceneWidth || placement.y >= sceneHeight;
            return (
              <EditableLabel
                key={placement.id}
                placement={placement}
                fontId={paint.fontId}
                settings={settings}
                ready={paint.ready}
                labelWidth={labelWidth}
                labelHeight={labelHeight}
                cssScale={cssScale}
                palette={paint.palette}
                selected={props.selectedId === placement.id}
                editing={props.editingId === placement.id}
                resizing={preview !== null}
                clipped={clipped}
                onSelect={props.onSelect}
                onBeginEdit={props.onBeginEdit}
                onCommitText={props.onCommitText}
                onCancelEdit={props.onCancelEdit}
                onRenderError={onRenderError}
                onFrameGeometry={onFrameGeometry}
                onRenderOk={props.onRenderOk}
                onFrameElement={onFrameElement}
                onNudge={props.onNudge}
                onDeleteKey={props.onDeleteKey}
              />
            );
          })}
        {showGrid && (
          // Native-pixel grid: anchored to the stage origin and clipped to
          // the logical canvas by the stage's overflow, so it scrolls and
          // zooms with the canvas and never covers the body, rulers or
          // panels. Decorative only: hidden from assistive tech and focus,
          // and the Moveable handles render above it outside this node.
          <div data-scene-pixel-grid aria-hidden="true" style={pixelGridOverlayStyle(cssScale)} />
        )}
        {props.tool === "text" && (
          <div
            data-scene-text-placement
            style={{
              position: "absolute",
              inset: 0,
              zIndex: Math.max(0, ...placements.map((placement) => placement.order)) + 1,
              cursor: "crosshair",
            }}
            onPointerDown={(event) => {
              if (event.button !== 0 || !event.isPrimary) return;
              event.preventDefault();
              event.stopPropagation();
              const bounds = event.currentTarget.getBoundingClientRect();
              props.onAddText(
                Math.max(0, Math.min(sceneWidth - 1, Math.round((event.clientX - bounds.left) / cssScale))),
                Math.max(0, Math.min(sceneHeight - 1, Math.round((event.clientY - bounds.top) / cssScale))),
              );
            }}
          />
        )}
      </div>
      {moveableTarget && (
        <Moveable
          ref={moveableRef}
          target={moveableTarget}
          draggable
          // The selection outline is a move target too; only the corner
          // controls resize. Moveable's edgeDraggable keeps both gestures
          // on the same position/release path as dragging the label body.
          edgeDraggable
          linePadding={4}
          throttleDrag={1}
          resizable={selectedIsDirect}
          edge={false}
          throttleResize={1}
          // Proportional resize: width and height scale together, so pointer
          // motion along either axis resizes the label instead of snapping
          // back. Only direct labels expose resize handles; the variant
          // outline below never resizes, so this is inert for variants.
          keepRatio
          // Direct labels resize from the corners only, so no edge handle
          // ever covers the middle of a one-line label and steals its
          // selection click. Variant-backed labels render no resize handles
          // at all; the grey control color is the only visible outline.
          renderDirections={selectedIsDirect ? ["nw", "ne", "sw", "se"] : undefined}
          className={selectedIsDirect ? undefined : "scene-moveable-variant"}
          origin={false}
          useResizeObserver
          padding={{ left: 4, top: 4, right: 4, bottom: 4 }}
          onDragStart={() => {
            // A drag started while a save is pending begins from the
            // visible position, never a stale pre-save capture.
            const current = displayed.find((placement) => placement.id === props.selectedId);
            if (!current) {
              dragStartRef.current = null;
              return false;
            }
            dragStartRef.current = { id: current.id, x: current.x, y: current.y };
            return undefined;
          }}
          onDrag={(event) => {
            // Moveable owns the frame transform during the drag; mirror it
            // onto the label container so pixels follow the pointer. The
            // store commits once on release, rounded to the device grid.
            const container = (event.target as HTMLElement).parentElement;
            if (container) container.style.transform = event.transform;
            const start = dragStartRef.current;
            if (start) {
              const delta = dragNativeDelta([event.translate[0] ?? 0, event.translate[1] ?? 0], cssScale);
              onPlacementPreview?.({
                id: start.id,
                x: start.x + delta.dx,
                y: start.y + delta.dy,
              });
            }
          }}
          onDragEnd={(event) => {
            const start = dragStartRef.current;
            dragStartRef.current = null;
            const frame = event.target as HTMLElement;
            if (!start || start.id !== props.selectedId || !event.isDrag) {
              frame.style.transform = "";
              const container = frame.parentElement;
              if (container) container.style.transform = "";
              return;
            }
            // OnDragEnd carries no totals; the last OnDrag holds the
            // cumulative pointer translation in screen px.
            const last = event.lastEvent as { translate?: readonly [number, number] } | undefined;
            const { dx, dy } = dragNativeDelta(last?.translate ?? [0, 0], cssScale);
            const container = frame.parentElement;
            if (dx === 0 && dy === 0) {
              frame.style.transform = "";
              if (container) container.style.transform = "";
              return;
            }
            // Pin the released integer position onto the container in the
            // same frame the drag transform clears: the queued save has not
            // rendered yet, and without this the next paint shows the old
            // coordinates for at least one frame before snapping forward.
            const pending = { id: start.id, x: start.x + dx, y: start.y + dy };
            frame.style.transform = "";
            if (container) {
              container.style.transform = "";
              container.style.left = `${pending.x * cssScale}px`;
              container.style.top = `${pending.y * cssScale}px`;
            }
            setPendingMove(pending);
            void props.onCommitMove(pending.id, pending.x, pending.y).then(
              (ok) => {
                // Success reconciles through the layout handoff above once
                // the saved coordinates render; only a rejection releases
                // the preview, and only while it still describes this drop.
                if (!ok) {
                  setPendingMove((current) =>
                    current !== null && current.id === pending.id && current.x === pending.x && current.y === pending.y
                      ? null
                      : current,
                  );
                }
              },
              () => {
                setPendingMove((current) =>
                  current !== null && current.id === pending.id && current.x === pending.x && current.y === pending.y
                    ? null
                    : current,
                );
              },
            );
          }}
          onResizeStart={(event) => {
            // Resize gestures start from the visible size: a queued resize
            // save still rendering counts as the base, never the stale props.
            // A release still waiting for its repaint commits first, so the
            // new gesture bases on the saved values, never a stale preview.
            const current = displayed.find((placement) => placement.id === props.selectedId);
            const paint = current ? paints.get(current.id) : undefined;
            const box = (event.target as HTMLElement).getBoundingClientRect();
            if (!current || current.textStyleId !== null || !paint || box.width <= 0 || box.height <= 0) {
              resizeStartRef.current = null;
              return false;
            }
            if (resizeWaiter.peek()?.id === current.id) flushAwaitingResize();
            const preview =
              pendingResizeRef.current !== null && pendingResizeRef.current.id === current.id
                ? pendingResizeRef.current
                : null;
            const width = preview?.width ?? current.width ?? Math.max(1, sceneWidth - current.x);
            const fontSize = preview?.fontSize ?? paint.settings.sizePx;
            const baseX = preview?.x ?? current.x;
            const baseY = preview?.y ?? current.y;
            // The anchor snapshots the committed renderer frame the gesture
            // starts from. The release corrects the position against the
            // repaint's measured bounds, so the opposite ink corner holds.
            const recorded = inkByIdRef.current.get(current.id);
            const anchorInk =
              recorded &&
              recorded.ink &&
              recorded.text === current.text &&
              recorded.sizePx === fontSize &&
              recorded.width === width
                ? recorded.ink
                : null;
            resizeStartRef.current = {
              id: current.id,
              width,
              fontSize,
              boxWidth: box.width,
              boxHeight: box.height,
              x: baseX,
              y: baseY,
              lastDrag: null,
              lastDirection: null,
              anchorBaseX: baseX,
              anchorBaseY: baseY,
              anchorInk,
            };
            return undefined;
          }}
          onResize={(event) => {
            // Pin the target onto the pointer synchronously, the documented
            // Resizable pattern: the React repaint below lands a frame later
            // at the same size, so Moveable never re-anchors the gesture to
            // a lagging target and the events stay monotonic. The target is
            // the tight renderer ink frame, so the accompanying drag
            // translation keeps the opposite ink corner fixed while the
            // dragged corner follows the pointer; mirroring it onto the
            // label container (exactly like move drags do) keeps the pixels
            // under the pointer for every corner. The delivered paint is
            // always the real renderer output, never this transient frame
            // size. keepRatio scales both axes together, so the width ratio
            // below also carries pure-vertical pointer motion; ratios cancel
            // cssScale, so only the width delta and the drag translation
            // convert back to native pixels.
            const start = resizeStartRef.current;
            if (!start || start.id !== props.selectedId) return;
            const frame = event.target as HTMLElement;
            frame.style.width = `${event.width}px`;
            frame.style.height = `${event.height}px`;
            const container = frame.parentElement;
            if (container) container.style.transform = event.drag.transform;
            const translate = event.drag.translate as unknown as readonly [number, number];
            start.lastDrag = [translate[0] ?? 0, translate[1] ?? 0];
            const direction = event.direction as unknown as readonly [number, number];
            start.lastDirection = [direction[0] ?? 0, direction[1] ?? 0];
            // Moveable clamps extreme inward drags at zero or negative sizes;
            // pin to a positive pixel so the gesture commits the domain
            // minimum instead of being silently swallowed.
            const estimate = resizeEstimates(
              { fontSize: start.fontSize, width: start.width, boxWidth: start.boxWidth, boxHeight: start.boxHeight },
              event.width,
              cssScale,
            );
            if (!estimate) return;
            const { fontSize, width } = estimate;
            const dragDelta = dragNativeDelta([translate[0] ?? 0, translate[1] ?? 0], cssScale);
            onPlacementPreview?.({
              id: start.id,
              fontSize,
              width,
              x: start.x + dragDelta.dx,
              y: start.y + dragDelta.dy,
            });
            setPendingResize((current) =>
              current !== null &&
              current.id === start.id &&
              current.fontSize === fontSize &&
              current.width === width &&
              current.x === start.x &&
              current.y === start.y
                ? current
                : { id: start.id, fontSize, width, x: start.x, y: start.y },
            );
          }}
          onResizeEnd={(event) => {
            // Release the synchronous gesture size and translation: the frame
            // renders the last real paint again until the committed repaint
            // lands, so no gesture sizing can freeze past the release in any
            // outcome. The fallback position commits from the cumulative drag
            // translation rounded to the native grid; the frame's screen
            // offset is pinned onto the container in the same frame the
            // transform clears, exactly like move releases. The single
            // revisioned save waits for the repaint of the released size and
            // corrects the position against its measured frame bounds, so
            // the opposite ink corner anchors against real renderer geometry
            // rather than a stretched rectangle.
            const frame = event.target as HTMLElement;
            const container = frame.parentElement;
            // Single ownership seam for the frame's size after any
            // imperative resize mutation: the latest renderer-owned bounds
            // reported for the placement. Blank-clearing never restores
            // React's values (React only writes on virtual-style change),
            // so every release outcome restores the known bounds instead.
            const restoreFrameSize = (target: HTMLElement, placementId: string | null): void => {
              const latest = placementId ? (inkByIdRef.current.get(placementId)?.ink ?? null) : null;
              if (latest) {
                target.style.width = `${Math.max(1, latest.width * cssScale)}px`;
                target.style.height = `${Math.max(1, latest.height * cssScale)}px`;
              } else {
                target.style.width = "";
                target.style.height = "";
              }
            };
            const start = resizeStartRef.current;
            resizeStartRef.current = null;
            const preview = pendingResizeRef.current;
            if (!start || !preview || start.id !== props.selectedId || preview.id !== start.id || !event.isDrag) {
              restoreFrameSize(frame, start?.id ?? props.selectedId);
              if (container) container.style.transform = "";
              return;
            }
            const drag = start.lastDrag ?? ([0, 0] as const);
            const release = {
              id: preview.id,
              fontSize: preview.fontSize,
              width: preview.width,
              text: displayed.find((placement) => placement.id === preview.id)?.text ?? "",
            };
            const fallbackPosition = releasedPosition({ x: start.x, y: start.y }, drag, cssScale);
            const fallback = {
              ...release,
              x: fallbackPosition.x,
              y: fallbackPosition.y,
            };
            if (container) {
              container.style.left = `${fallback.x * cssScale}px`;
              container.style.top = `${fallback.y * cssScale}px`;
              container.style.transform = "";
            }
            // Yield the transient drag size to the latest renderer frame:
            // the reported bounds are what React last rendered (and what
            // stays visible until the awaited repaint lands), whether or
            // not a mid-gesture repaint already measured the released size.
            restoreFrameSize(frame, release.id);
            setPendingResize(fallback);
            if (!start.anchorInk || !start.lastDirection) {
              fireResizeCommit(release, fallback.x, fallback.y);
              return;
            }
            resizeWaiter.arm({
              ...release,
              fallbackX: fallback.x,
              fallbackY: fallback.y,
              anchorBaseX: start.anchorBaseX,
              anchorBaseY: start.anchorBaseY,
              anchorInk: start.anchorInk,
              lastDirection: start.lastDirection,
            });
            awaitingTimeoutRef.current = window.setTimeout(() => {
              awaitingTimeoutRef.current = null;
              const commit = resizeWaiter.flush(null);
              if (commit) fireResizeCommit(commit.release, commit.x, commit.y);
            }, 8000);
            // A mid-gesture repaint may already have measured the released
            // size (the gesture paused at its end); commit corrected at once
            // instead of waiting for a repaint that already landed.
            const recorded = inkByIdRef.current.get(release.id);
            if (
              recorded?.ink &&
              recorded.text === release.text &&
              recorded.sizePx === release.fontSize &&
              recorded.width === release.width
            ) {
              const commit = resizeWaiter.fulfill(recorded.ink);
              if (commit) fireResizeCommit(commit.release, commit.x, commit.y);
            }
          }}
        />
      )}
    </div>
  );
}

function selectedIdSelected(selectedId: string | null, placements: DomainPlacementView[]): DomainPlacementView | null {
  if (!selectedId) return null;
  return placements.find((placement) => placement.id === selectedId) ?? null;
}
