// On-scene label layers: frontmost label at the top, matching the stage
// paint order (ascending order, id tie-break) reversed. Rows reorder by
// pointer or keyboard drag through one atomic domain reorder, edit text in
// place, and stay selected in sync with the stage. Inline drafts mirror the
// stage editor contract: Escape cancels, blur or Ctrl/Cmd+Enter commits
// without duplicate writes, and a conflict keeps the draft open for recovery.
import * as React from "react";
import { DragDropProvider, KeyboardSensor, PointerSensor, type DragEndEvent } from "@dnd-kit/react";
import { isSortable, useSortable } from "@dnd-kit/react/sortable";
import { PointerActivationConstraints } from "@dnd-kit/dom";
import { EyeOff, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import layerText from "../../../components/ui/assets/glypherie/layer-text.svg";
import layerTextSelected from "../../../components/ui/assets/glypherie/layer-text-selected.svg";
import layerVisible from "../../../components/ui/assets/glypherie/layer-visible.svg";
import layerVisibleSelected from "../../../components/ui/assets/glypherie/layer-visible-selected.svg";
import "./SceneLayersPanel.css";
import { ScrollArea } from "../../../components/ui/scroll-area";
import { Textarea } from "../../../components/ui/textarea";
import { TooltipHint } from "../../../components/TooltipHint";
import type { DomainPlacementView } from "../scenes/service.js";
import { sortLayersTopFirst } from "./scene-order.ts";

// Row-wide drag with click fidelity: a small pointer travel lifts the row so
// clicks, double-clicks and text selection never start a drag, while touch
// keeps the official hold delay. Drags starting on visibility or the editor
// stay refused through the sensor defaults.
const layerSensors = [
  PointerSensor.configure({
    activationConstraints: (event) =>
      event.pointerType === "touch"
        ? [new PointerActivationConstraints.Delay({ value: 250, tolerance: 5 })]
        : [new PointerActivationConstraints.Distance({ value: 6 })],
  }),
  KeyboardSensor,
];

interface LayersPanelProps {
  placements: DomainPlacementView[];
  bounds: Record<string, { width: number; height: number }>;
  onToggleVisibility: (id: string, visible: boolean) => void;
  revision: number;
  selectedId: string | null;
  onDelete: (id: string) => void;
  deleteDisabled: boolean;
  editingId: string | null;
  // Blocking mutation, in-flight reorder, or conflict banner: no drag starts.
  saving: boolean;
  conflict: boolean;
  onSelect: (id: string | null) => void;
  onBeginEdit: (id: string) => void;
  onCommitText: (id: string, text: string) => Promise<boolean>;
  onCancelEdit: () => void;
  // Index move within the displayed top-first order; resolves against the
  // latest saved base and reports whether the save landed.
  onReorder: (from: number, to: number) => Promise<boolean>;
}

export function SceneLayersPanel(props: LayersPanelProps): React.JSX.Element {
  const topFirst = React.useMemo(() => sortLayersTopFirst(props.placements), [props.placements]);
  // Optimistic order from the last drop: during the drag the sortable
  // plugin moves rows and glides neighbors through its own transition; after
  // the drop the order survives until the saved props catch up, and rolls
  // back when the save is rejected.
  const [pending, setPending] = React.useState<{ ids: string[]; revision: number; acked: boolean } | null>(null);

  // A drop can only start when nothing optimistic is showing, so the base
  // here is always the rendered top-first order.
  const onDragEnd = React.useCallback(
    (event: DragEndEvent) => {
      if (event.canceled) return;
      const { source } = event.operation;
      if (!isSortable(source)) return;
      const { initialIndex, index } = source;
      if (initialIndex === index) return;
      const base = topFirst.map((placement) => placement.id);
      const next = [...base];
      const moved = next.splice(initialIndex, 1)[0];
      if (moved === undefined) return;
      next.splice(index, 0, moved);
      // One atomic save for the whole gesture; the dropped order stays until
      // the saved props arrive, then the effect below adopts it.
      setPending({ ids: next, revision: props.revision, acked: false });
      void props.onReorder(initialIndex, index).then((ok) => {
        if (!ok) {
          setPending(null);
          return;
        }
        setPending((current) =>
          current !== null && current.ids.join("\0") === next.join("\0") ? { ...current, acked: true } : current,
        );
      });
    },
    [props, props.revision, topFirst],
  );

  // The saved props own the truth: adopt them once they match the drop, and
  // drop the optimistic order when the set changes (add, remove, adoption)
  // or the acknowledged save is superseded by a newer revision.
  React.useEffect(() => {
    if (pending === null) return;
    const current = topFirst.map((placement) => placement.id);
    if (current.length !== pending.ids.length || current.some((id) => !pending.ids.includes(id))) {
      setPending(null);
      return;
    }
    if (current.join("\0") === pending.ids.join("\0")) {
      setPending(null);
      return;
    }
    if (pending.acked && props.revision !== pending.revision) setPending(null);
  }, [pending, props.revision, topFirst]);

  const byId = React.useMemo(() => new Map(topFirst.map((placement) => [placement.id, placement])), [topFirst]);
  const displayed = React.useMemo(() => {
    if (pending === null) return topFirst;
    const rows: DomainPlacementView[] = [];
    for (const id of pending.ids) {
      const placement = byId.get(id);
      if (placement !== undefined) rows.push(placement);
    }
    return rows.length === topFirst.length ? rows : topFirst;
  }, [byId, pending, topFirst]);

  const dragDisabled = props.editingId !== null || props.saving || props.conflict || pending !== null;

  return (
    <section data-scene-layers aria-label="Layers" className="scene-layers flex h-full min-h-0 flex-col font-studio">
      <h2 className="sr-only">Layers</h2>
      <div
        role="toolbar"
        aria-label="Layer actions"
        data-scene-layer-actions
        className="flex h-8 shrink-0 items-center gap-1 border-b border-studio-border px-2"
      >
        <TooltipHint content="Delete selected label">
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="Delete selected label"
            data-scene-layer-delete
            disabled={!props.selectedId || props.deleteDisabled || dragDisabled}
            onClick={() => {
              if (props.selectedId) props.onDelete(props.selectedId);
            }}
          >
            <Trash2 aria-hidden="true" className="size-3" />
          </Button>
        </TooltipHint>
      </div>
      <ScrollArea className="min-h-0 flex-1" data-screen-left-scroll>
        <div className="p-2">
          {displayed.length === 0 ? (
            <p className="m-0 text-xs text-soft" data-scene-layers-empty>
              No labels on this scene yet.
            </p>
          ) : (
            <DragDropProvider sensors={layerSensors} onDragEnd={onDragEnd}>
              <ul
                className="m-0 flex list-none flex-col gap-1 p-0"
                role="list"
                aria-label="Scene layers, frontmost first"
                data-scene-layer-list
              >
                {displayed.map((placement, index) => (
                  <LayerRow
                    key={placement.id}
                    placement={placement}
                    bounds={props.bounds[placement.id]}
                    onToggleVisibility={props.onToggleVisibility}
                    position={index}
                    selected={props.selectedId === placement.id}
                    editing={props.editingId === placement.id}
                    dragDisabled={dragDisabled}
                    onSelect={props.onSelect}
                    onBeginEdit={props.onBeginEdit}
                    onCommitText={props.onCommitText}
                    onCancelEdit={props.onCancelEdit}
                  />
                ))}
              </ul>
            </DragDropProvider>
          )}
        </div>
      </ScrollArea>
    </section>
  );
}

interface LayerRowProps {
  placement: DomainPlacementView;
  bounds?: { width: number; height: number };
  onToggleVisibility: (id: string, visible: boolean) => void;
  position: number;
  selected: boolean;
  editing: boolean;
  // No drag starts while another draft edits, a save runs, a conflict waits,
  // or a reorder is still in flight.
  dragDisabled: boolean;
  onSelect: (id: string | null) => void;
  onBeginEdit: (id: string) => void;
  onCommitText: (id: string, text: string) => Promise<boolean>;
  onCancelEdit: () => void;
}

function LayerRow(props: LayerRowProps): React.JSX.Element {
  const { placement } = props;
  // The row body is the only pointer and keyboard drag activator. The
  // sortable element stays the whole <li> so the drag lifts the whole row,
  // while the handle scopes both sensors to the body: the keyboard sensor
  // listens on the handle, so textarea and visibility-button keys never
  // reach it, and the pointer defaults refuse drags starting on those
  // controls. Space/Enter on the focused body starts the sortable drag (the
  // sensor consumes the key), so double-click opens editing.
  const { ref, handleRef, isDragSource, isDragging } = useSortable({
    id: placement.id,
    index: props.position,
    disabled: props.dragDisabled,
  });
  const [draft, setDraft] = React.useState<string | null>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  // Settles the edit exactly once: commit and cancel both arm it
  // synchronously, so the blur their focus moves fire cannot duplicate the
  // write or resurrect a discarded draft.
  const settledRef = React.useRef(false);

  // Drafts start from the saved text and never overwrite an open draft with
  // a remote update; discarding happens only when editing ends elsewhere.
  React.useEffect(() => {
    if (props.editing && draft === null) {
      settledRef.current = false;
      setDraft(placement.text);
    } else if (!props.editing && draft !== null) {
      setDraft(null);
    }
  }, [props.editing, draft, placement.text]);

  React.useLayoutEffect(() => {
    if (!props.editing || draft === null) return;
    const textarea = textareaRef.current;
    if (textarea && document.activeElement !== textarea) {
      textarea.focus({ preventScroll: true });
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    }
  }, [props.editing, draft]);

  const commitDraft = React.useCallback(async () => {
    const text = draft;
    if (text === null || settledRef.current) return;
    settledRef.current = true;
    const ok = await props.onCommitText(placement.id, text);
    // A conflict keeps the draft open for recovery; disarm the guard so the
    // next gesture settles the edit instead of being swallowed.
    if (!ok) settledRef.current = false;
  }, [draft, placement.id, props]);

  const cancelDraft = React.useCallback(() => {
    if (settledRef.current) return;
    settledRef.current = true;
    props.onCancelEdit();
  }, [props]);

  const onTextareaKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.nativeEvent.isComposing) return;
      if (event.key === "Escape") {
        event.preventDefault();
        cancelDraft();
        return;
      }
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        void commitDraft();
      }
    },
    [cancelDraft, commitDraft],
  );

  const onTextareaBlur = React.useCallback(() => {
    if (settledRef.current) return;
    if (draft !== null) void commitDraft();
  }, [commitDraft, draft]);

  const labelText = placement.text === "" ? "(blank label)" : placement.text;
  // The held row stays fully opaque on a solid raised surface, matching the
  // reference feedback; dimming it here would flash brightness on release.
  const dragging = isDragSource || isDragging;

  return (
    <li
      ref={ref}
      aria-current={props.selected ? "true" : undefined}
      aria-label={`Layer ${props.position + 1}: ${labelText}`}
      data-scene-layer={placement.id}
      data-hidden={placement.visible === false || undefined}
      data-dragging={dragging || undefined}
      className="scene-layer-row group/layer relative flex items-center gap-[6px] rounded-[4px] border border-transparent p-[7px] drop-shadow-[0_1px_1px_rgba(0,0,0,0.05)] transition-shadow duration-300"
    >
      {props.editing && draft !== null ? (
        <>
          {/* The handle stays mounted (hidden) while editing so the sortable
          activator never falls back to the row: the fallback would stamp
          role and aria-disabled onto the <li> around the live editor. */}
          <button
            type="button"
            ref={handleRef}
            data-scene-layer-handle={placement.id}
            aria-label={`Drag label ${labelText} to reorder`}
            hidden
            tabIndex={-1}
            aria-hidden="true"
          />
          <Textarea
            ref={textareaRef}
            value={draft}
            rows={2}
            aria-label={`Edit label text, layer ${props.position + 1}`}
            data-scene-layer-edit={placement.id}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onTextareaKeyDown}
            onBlur={onTextareaBlur}
            onClick={(event) => event.stopPropagation()}
            onFocus={(event) => event.stopPropagation()}
            className="min-h-0 flex-1 py-1 text-xs"
          />
        </>
      ) : (
        <button
          type="button"
          ref={handleRef}
          data-scene-layer-handle={placement.id}
          aria-label={`Drag label ${labelText} to reorder`}
          onClick={() => props.onSelect(placement.id)}
          onFocus={() => props.onSelect(placement.id)}
          onDoubleClick={() => {
            if (!props.dragDisabled) props.onBeginEdit(placement.id);
          }}
          className="flex min-w-0 flex-1 cursor-grab items-center gap-[6px] rounded-sm text-left touch-none outline-none focus-visible:ring-3 focus-visible:ring-ring/50 active:cursor-grabbing"
        >
          <img
            src={props.selected ? layerTextSelected : layerText}
            alt=""
            aria-hidden="true"
            className="shrink-0"
            data-scene-layer-icon={placement.id}
          />
          <span className="flex min-w-0 flex-1 flex-col">
            <span
              className="scene-layer-label truncate text-[11px] leading-4 font-medium"
              data-scene-layer-text={placement.id}
            >
              {labelText}
            </span>
            <span
              className="scene-layer-metadata truncate text-[9px] leading-4 font-normal"
              data-scene-layer-meta={placement.id}
            >
              {placement.x},{placement.y} • {props.bounds ? `${props.bounds.width}×${props.bounds.height}` : "—×—"}
            </span>
          </span>
        </button>
      )}
      {!props.editing && (
        <TooltipHint content={placement.visible === false ? "Show label" : "Hide label"}>
          <button
            type="button"
            className="scene-layer-visibility flex h-4 w-[11px] shrink-0 items-center justify-center rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={`${placement.visible === false ? "Show" : "Hide"} label ${labelText}`}
            aria-pressed={placement.visible !== false}
            disabled={props.dragDisabled}
            data-scene-layer-visibility={placement.id}
            onClick={() => props.onToggleVisibility(placement.id, placement.visible === false)}
          >
            {placement.visible === false ? (
              <EyeOff aria-hidden="true" className="h-[9px] w-[11px]" />
            ) : (
              <img src={props.selected ? layerVisibleSelected : layerVisible} alt="" aria-hidden="true" />
            )}
          </button>
        </TooltipHint>
      )}
    </li>
  );
}
