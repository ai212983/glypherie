import * as React from "react";
import type { PalettePreset } from "../../../palettes/model";
import { Select, SelectContent, SelectDisplay, SelectItem, SelectTrigger, SelectValue } from "../../../../components/ui/select";
import { Label } from "../../../../components/ui/label";
import { PaletteDepthLabel } from "../../grayscale/PaletteDepthLabel";
import { curveLevels } from "../../grayscale/response-curve";
import "./OutputControls.css";

function PaletteChoice({ preset }: { preset: PalettePreset }): React.JSX.Element {
  const levels = curveLevels(preset.curve);
  return (
    <span className="palette-choice">
      <span className="palette-choice-heading">
        <span data-palette-name className="palette-choice-name">{preset.name || "Untitled grayscale"}</span>{" "}
        <PaletteDepthLabel count={levels.length} className="palette-choice-depth" />
      </span>
      <span className="palette-choice-swatches" aria-hidden="true">
        {levels.map((gray, index) => (
          <span key={index} style={{ backgroundColor: `rgb(${gray} ${gray} ${gray})` }} />
        ))}
      </span>
    </span>
  );
}

export function OutputControls({ presets, paletteId, disabled, onPalette }: {
  presets: readonly PalettePreset[];
  paletteId: number;
  disabled: boolean;
  onPalette: (value: number) => void;
}): React.JSX.Element {
  const id = React.useId();
  const staticValue = disabled || presets.length <= 1;
  const selected = presets.find((preset) => preset.id === paletteId);
  return (
    <div className="palette-picker flex min-w-0 flex-col gap-3" id="output-mode">
      <Label asChild={staticValue} id={`${id}-label`} htmlFor={staticValue ? undefined : id}>
        {staticValue ? <span>Palette</span> : "Palette"}
      </Label>
      {staticValue ? (
        <SelectDisplay id={id} data-output-palette role="group" aria-labelledby={`${id}-label`}>
          {selected && <PaletteChoice preset={selected} />}
        </SelectDisplay>
      ) : <Select value={String(paletteId)} onValueChange={(value) => onPalette(Number(value))}>
        <SelectTrigger id={id} data-output-palette><SelectValue /></SelectTrigger>
        <SelectContent className="palette-picker-menu">
          {presets.map((preset) => (
            <SelectItem key={preset.id} value={String(preset.id)} textValue={preset.name || "Untitled grayscale"}>
              <PaletteChoice preset={preset} />
            </SelectItem>
          ))}
        </SelectContent>
      </Select>}
    </div>
  );
}
