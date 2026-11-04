// Scene stage: positioned WASM label layers over the screen paper with a
// react-moveable drag frame around the selected label's tight ink box. All
// coordinates entering the store are integer native device pixels; the
// cssScale presentation factor only converts pointer deltas and display
// sizes. Moveable is unmounted while a label edits text. Moveable's own
// lines are the single visible selection outline (the label frame draws
// none); Moveable also owns the drag hit geometry, so its cached rect must
// be refreshed whenever the committed label moves or resizes.
import * as React from "react";
import Moveable from "react-moveable";
import type { VariantSettings } from "../../variants/model.js";
import type { RGBA } from "../../renderer/renderer-types.js";
import type { DomainPlacementView } from "../scenes/service.js";
import { EditableLabel } from "./EditableLabel.js";

export interface StagePaint {
  fontId: string;
  settings: VariantSettings;
  ready: boolean;
  palette: RGBA[];
}

export interface SceneStageProps {
  sceneWidth: number;
  sceneHeight: number;
  placements: DomainPlacementView[];
  paints: Map<string, StagePaint>;
  // CSS px per native device px.
  cssScale: number;
  paperCss: string;
  selectedId: string | null;
  editingId: string | null;
  onSelect: (id: string | null) => void;
  onBeginEdit: (id: string) => void;
  onCommitText: (id: string, text: string) => Promise<boolean>;
  onCancelEdit: () => void;
  // Resolves true once the move persists; false leaves the saved position
  // (conflict or failure) so the stage can release its pending preview.
  onCommitMove: (id: string, x: number, y: number) => Promise<boolean>;
  onNudge: (id: string, dx: number, dy: number) => void;
  onDeleteKey: (id: string) => void;
  onRenderError: (message: string) => void;
  onRenderOk: () => void;
}

export function SceneStage(props: SceneStageProps): React.JSX.Element {
  const { sceneWidth, sceneHeight, placements, paints, cssScale } = props;
  const framesRef = React.useRef(new Map<string, HTMLDivElement>());
  const dragStartRef = React.useRef<{ id: string; x: number; y: number } | null>(null);
  const moveableRef = React.useRef<Moveable | null>(null);
  const [, setMoveableTick] = React.useState(0);

  // Pending release preview: the released integer position stays visible
  // while the revisioned save is queued, so no frame repaints the old
  // coordinates. Per useOptimistic, the preview reconciles once the
  // authoritative props catch up and rolls back on rejection.
  const [pendingMove, setPendingMove] = React.useState<{ id: string; x: number; y: number } | null>(null);

  const displayed = React.useMemo(() => {
    if (!pendingMove) return placements;
    let moved = false;
    const next = placements.map((placement) => {
      if (placement.id !== pendingMove.id) return placement;
      if (placement.x === pendingMove.x && placement.y === pendingMove.y) return placement;
      moved = true;
      return { ...placement, x: pendingMove.x, y: pendingMove.y };
    });
    return moved ? next : placements;
  }, [placements, pendingMove]);

  // The handoff clears only after the saved coordinates render (or the
  // pending label leaves the scene), never when the async command merely
  // returns while props are still old. Failures clear through the commit
  // acknowledgment below, restoring the authoritative position with the
  // existing recovery UI.
  React.useLayoutEffect(() => {
    if (!pendingMove) return;
    const canonical = placements.find((placement) => placement.id === pendingMove.id);
    if (!canonical || (canonical.x === pendingMove.x && canonical.y === pendingMove.y)) {
      setPendingMove(null);
    }
  }, [placements, pendingMove]);

  const ordered = React.useMemo(
    () => [...displayed].sort((left, right) => left.order - right.order || (left.id < right.id ? -1 : 1)),
    [displayed],
  );

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

  const selected = selectedIdSelected(props.selectedId, displayed);
  const moveableTarget = !props.editingId && selected ? (framesRef.current.get(selected.id) ?? null) : null;
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
  }, [moveableTarget, selectedX, selectedY, cssScale]);

  return (
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
        overflow: "hidden",
      }}
    >
      {ordered.map((placement) => {
        const paint = paints.get(placement.textStyleId);
        if (!paint) return null;
        const labelWidth = Math.max(1, sceneWidth - placement.x);
        const labelHeight = Math.max(1, sceneHeight - placement.y);
        const clipped = placement.x < 0 || placement.y < 0
          || placement.x >= sceneWidth || placement.y >= sceneHeight;
        return (
          <EditableLabel
            key={placement.id}
            placement={placement}
            fontId={paint.fontId}
            settings={paint.settings}
            ready={paint.ready}
            labelWidth={labelWidth}
            labelHeight={labelHeight}
            cssScale={cssScale}
            palette={paint.palette}
            selected={props.selectedId === placement.id}
            editing={props.editingId === placement.id}
            clipped={clipped}
            onSelect={props.onSelect}
            onBeginEdit={props.onBeginEdit}
            onCommitText={props.onCommitText}
            onCancelEdit={props.onCancelEdit}
            onRenderError={props.onRenderError}
            onRenderOk={props.onRenderOk}
            onFrameElement={onFrameElement}
            onNudge={props.onNudge}
            onDeleteKey={props.onDeleteKey}
          />
        );
      })}
      {moveableTarget && (
        <Moveable
          ref={moveableRef}
          target={moveableTarget}
          draggable
          throttleDrag={1}
          origin={false}
          useResizeObserver
          padding={{ left: 4, top: 4, right: 4, bottom: 4 }}
          onDragStart={(event) => {
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
            const translate = last?.translate ?? [0, 0];
            const dx = Math.round(translate[0] / cssScale);
            const dy = Math.round(translate[1] / cssScale);
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
                    current !== null && current.id === pending.id
                    && current.x === pending.x && current.y === pending.y ? null : current,
                  );
                }
              },
              () => {
                setPendingMove((current) =>
                  current !== null && current.id === pending.id
                  && current.x === pending.x && current.y === pending.y ? null : current,
                );
              },
            );
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
