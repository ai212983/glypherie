// Scene coordinates use integer native device pixels; cssScale maps them to CSS pixels. Moveable
// owns selection and gesture hit geometry, while the renderer owns ink bounds.
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
  // Paints keyed by placement id.
  paints: Map<string, StagePaint>;
  // CSS px per native device px.
  cssScale: number;
  paperCss: string;
  // View-only grid visibility, resolved by the workspace's zoom preference.
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

// Eight-native-pixel cells keep the grid legible when one native pixel is smaller than a CSS pixel.
// Preserve fractional pitch so it stays aligned with the canvas.
// https://www.w3.org/TR/css-images-3/#repeating-gradients
export const PIXEL_GRID_CELL_PX = 8;
function pixelGridOverlayStyle(cssScale: number): React.CSSProperties {
  const pitch = (Number.isFinite(cssScale) && cssScale > 0 ? cssScale : 1) * PIXEL_GRID_CELL_PX;
  const line = Math.min(1, pitch / 4);
  const color = "rgb(71 85 105 / 0.45)";
  return {
    position: "absolute",
    inset: 0,
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
    // Latest cumulative OnResize drag translation in CSS pixels; OnResizeEnd has no totals.
    lastDrag: readonly [number, number] | null;
    // Which corner handle drives the gesture ([-1,-1] is northwest); the
    // opposite ink corner stays fixed.
    lastDirection: readonly [number, number] | null;
    // Gesture-start origin and ink bounds in native pixels. A null ink rect selects the
    // drag-translation fallback.
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
  // The core consumes a pending release at most once; this adapter owns its fallback timer and
  // starts persistence.
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

  const [pendingMove, setPendingMove] = React.useState<{ id: string; x: number; y: number } | null>(null);
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

  React.useLayoutEffect(() => {
    if (!pendingResize) return;
    const canonical = placements.find((placement) => placement.id === pendingResize.id) ?? null;
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

  // Clear the release and its timer before queuing persistence, so late callbacks cannot consume
  // another gesture.
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

  // Consume a waiting release before another resize starts, even on a different label; its repaint
  // may still be pending.
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

  // Match all recorded paint inputs before fulfilling a release; stale geometry must not anchor a
  // newer resize.
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

  // Drag moves the target's parent, which Moveable's target ResizeObserver does not observe.
  // Refresh the cached rect after displayed geometry changes.
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
          // Keep the grid in the canvas paint layer so it pans and zooms with labels.
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
          edgeDraggable
          linePadding={4}
          throttleDrag={1}
          resizable={selectedIsDirect}
          edge={false}
          throttleResize={1}
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
            const current = displayed.find((placement) => placement.id === props.selectedId);
            if (!current) {
              dragStartRef.current = null;
              return false;
            }
            dragStartRef.current = { id: current.id, x: current.x, y: current.y };
            return undefined;
          }}
          onDrag={(event) => {
            // Moveable transforms the ink frame; mirror that transform onto its parent so the
            // rendered pixels follow it.
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
            // A pending save's visible preview remains the gesture base until saved props catch up.
            // Flush any awaited release before accepting another resize.
            const current = displayed.find((placement) => placement.id === props.selectedId);
            const paint = current ? paints.get(current.id) : undefined;
            const box = (event.target as HTMLElement).getBoundingClientRect();
            if (!current || current.textStyleId !== null || !paint || box.width <= 0 || box.height <= 0) {
              resizeStartRef.current = null;
              return false;
            }
            flushAwaitingResize();
            const preview =
              pendingResizeRef.current !== null && pendingResizeRef.current.id === current.id
                ? pendingResizeRef.current
                : null;
            const width = preview?.width ?? current.width ?? Math.max(1, sceneWidth - current.x);
            const fontSize = preview?.fontSize ?? paint.settings.sizePx;
            const baseX = preview?.x ?? current.x;
            const baseY = preview?.y ?? current.y;
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
            // Update Moveable's frame synchronously while the renderer repaint is pending. Mirror
            // translation onto the label parent; the renderer still owns the final ink bounds.
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
            const frame = event.target as HTMLElement;
            const container = frame.parentElement;
            // Restore the renderer's explicit bounds after imperative sizing. React will not
            // rewrite unchanged style props, so clearing inline width and height can leave the
            // frame collapsed.
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
