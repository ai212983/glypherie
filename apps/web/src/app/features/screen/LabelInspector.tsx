// Inspector for the selected scene label: text style, position, stacking
// order and label lifecycle. Text edits happen in place on the canvas; the
// style control only relinks the label to another saved text style and never
// mutates the shared style itself.
import * as React from "react";
import { ArrowDownToLine, ArrowUpToLine, Copy, Pencil, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { TooltipHint } from "../../../components/TooltipHint";
import type { DomainPlacementView, DomainTextStyleView } from "../scenes/service.js";

function styleLabel(style: DomainTextStyleView): string {
  return `${style.name} — ${style.fontSize}px`;
}

export function LabelInspector({ placement, styles, saving, onPatch, onDuplicate, onDelete, onBeginEdit }: {
  placement: DomainPlacementView;
  styles: DomainTextStyleView[];
  saving: boolean;
  onPatch: (patch: { textStyleId?: string; x?: number; y?: number; order?: number }) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onBeginEdit: () => void;
}): React.JSX.Element {
  const [x, setX] = React.useState(String(placement.x));
  const [y, setY] = React.useState(String(placement.y));
  // A background position save can commit new coordinates while the user
  // types here; committed values adopt only into fields without focus, so
  // an in-flight draft survives the re-render until commit or selection change.
  const placementIdRef = React.useRef(placement.id);
  React.useEffect(() => {
    const focusedId = document.activeElement instanceof HTMLElement ? document.activeElement.id : "";
    const switched = placement.id !== placementIdRef.current;
    if (switched || focusedId !== `inspector-x-${placement.id}`) setX(String(placement.x));
    if (switched || focusedId !== `inspector-y-${placement.id}`) setY(String(placement.y));
    placementIdRef.current = placement.id;
  }, [placement.x, placement.y, placement.id]);

  const commitPosition = (): void => {
    const parsedX = Math.round(Number(x));
    const parsedY = Math.round(Number(y));
    if (!Number.isInteger(parsedX) || !Number.isInteger(parsedY)) return;
    if (parsedX === placement.x && parsedY === placement.y) return;
    onPatch({ x: parsedX, y: parsedY });
  };

  return (
    <Card data-scene-inspector={placement.id}>
      <CardHeader>
        <CardTitle asChild><h2>Label</h2></CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="m-0 text-xs" data-scene-inspector-text>
          {placement.text === "" ? "(blank label)" : placement.text}
        </p>
        <div>
          <Button size="sm" data-scene-inspector-edit disabled={saving} onClick={onBeginEdit}>
            <Pencil aria-hidden="true" className="size-3 shrink-0" />Edit text in place
          </Button>
        </div>
        <div className="flex min-w-44 flex-1 flex-col gap-1">
          <Label htmlFor={`inspector-style-${placement.id}`}>Text style</Label>
          <Select value={placement.textStyleId} disabled={saving || styles.length === 0}
            onValueChange={(textStyleId) => {
              if (textStyleId !== placement.textStyleId) onPatch({ textStyleId });
            }}>
            <SelectTrigger id={`inspector-style-${placement.id}`} data-scene-inspector-style>
              <SelectValue placeholder="Choose a text style" />
            </SelectTrigger>
            <SelectContent>
              {styles.map((style) => (
                <SelectItem key={style.id} value={style.id}>{styleLabel(style)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor={`inspector-x-${placement.id}`}>X (px)</Label>
            <Input id={`inspector-x-${placement.id}`} data-scene-inspector-x type="number"
              value={x} disabled={saving} className="w-24"
              onChange={(event) => setX(event.target.value)}
              onBlur={commitPosition}
              onKeyDown={(event) => { if (event.key === "Enter") (event.target as HTMLInputElement).blur(); }} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor={`inspector-y-${placement.id}`}>Y (px)</Label>
            <Input id={`inspector-y-${placement.id}`} data-scene-inspector-y type="number"
              value={y} disabled={saving} className="w-24"
              onChange={(event) => setY(event.target.value)}
              onBlur={commitPosition}
              onKeyDown={(event) => { if (event.key === "Enter") (event.target as HTMLInputElement).blur(); }} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <TooltipHint content="Paint this label above the others">
            <Button type="button" variant="ghost" size="icon-xs" data-scene-inspector-front
              aria-label="Bring label forward" disabled={saving} onClick={() => onPatch({ order: placement.order + 1000 })}>
              <ArrowUpToLine aria-hidden="true" />
            </Button>
          </TooltipHint>
          <TooltipHint content="Paint this label below the others">
            <Button type="button" variant="ghost" size="icon-xs" data-scene-inspector-back
              aria-label="Send label backward" disabled={saving} onClick={() => onPatch({ order: placement.order - 1000 })}>
              <ArrowDownToLine aria-hidden="true" />
            </Button>
          </TooltipHint>
          <TooltipHint content="Duplicate this label">
            <Button type="button" variant="ghost" size="icon-xs" data-scene-inspector-duplicate
              aria-label="Duplicate label" disabled={saving} onClick={onDuplicate}>
              <Copy aria-hidden="true" />
            </Button>
          </TooltipHint>
          <TooltipHint content="Remove this label">
            <Button type="button" variant="ghost" size="icon-xs" data-scene-inspector-delete
              aria-label={`Delete label ${placement.text}`} disabled={saving} onClick={onDelete}>
              <Trash2 aria-hidden="true" />
            </Button>
          </TooltipHint>
        </div>
      </CardContent>
    </Card>
  );
}
