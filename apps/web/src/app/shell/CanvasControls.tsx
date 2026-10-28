import * as React from "react";
import { Label } from "../../components/ui/label";
import { Button } from "../../components/ui/button";
import { ContrastIcon } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { CANVAS_PALETTES, canvasPaletteById, isCanvasPaletteId, type CanvasPalette } from "../features/library/canvas-palettes";
import { useDisplayPreferences } from "./DisplayPreferences";

function CanvasSwatch({ palette, inverse }: { palette: CanvasPalette; inverse: boolean }): React.JSX.Element {
  return (
    <span
      aria-hidden="true"
      data-canvas-swatch
      className="flex h-5 w-8 shrink-0 items-center justify-center rounded border border-studio-border text-[11px] leading-none font-bold"
      style={{
        backgroundColor: inverse ? palette.inkCss : palette.paperCss,
        color: inverse ? palette.paperCss : palette.inkCss,
      }}
    >
      A
    </span>
  );
}

export function CanvasControls(): React.JSX.Element {
  const { canvas: { palette, inverse }, onCanvas } = useDisplayPreferences();
  return (
    <div className="flex items-center gap-1" data-global-canvas role="group" aria-labelledby="canvas-heading">
      <h2 id="canvas-heading" className="sr-only">Canvas</h2>
      <div className="flex items-center gap-1">
        <Button
          id="canvas-inverse" data-canvas-inverse type="button" variant="ghost" size="icon-sm"
          role="switch" aria-label="Inverse canvas colors" aria-checked={inverse}
          onClick={() => onCanvas({ inverse: !inverse })}
        >
          <ContrastIcon className="size-4" aria-hidden="true" />
        </Button>
        <div className="min-w-0 flex-1">
          <Label htmlFor="canvas-preset" className="sr-only">Canvas preset</Label>
          <Select
            value={palette}
            onValueChange={(next) => {
              if (isCanvasPaletteId(next)) onCanvas({ palette: next });
            }}
          >
            <SelectTrigger
              id="canvas-preset"
              data-canvas-preset
              data-value={palette}
              size="sm"
              className="w-full bg-background text-[10px] shadow-studio-inset"
            >
              <SelectValue>
                <span data-canvas-value className="flex min-w-0 items-center gap-2">
                  <CanvasSwatch palette={canvasPaletteById(palette)} inverse={inverse} />
                  <span data-canvas-name className="truncate">{canvasPaletteById(palette).name}</span>
                </span>
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="studio-card bg-card font-studio text-[10px] text-card-foreground shadow-studio-card">
              {CANVAS_PALETTES.map((preset) => (
                <SelectItem key={preset.id} value={preset.id} className="text-[10px]">
                  <CanvasSwatch palette={preset} inverse={inverse} />
                  {preset.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}
