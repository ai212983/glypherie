import * as React from "react";
import { Label } from "../../../../components/ui/label";
import { Input } from "../../../../components/ui/input";
import { Switch } from "../../../../components/ui/switch";
import { normalizedSpacing } from "../../../renderer/render-spec.js";

interface LayoutControlsProps {
  fontId: string;
  spacingPx: number;
  kerning: boolean;
  onSpacing: (value: number) => void;
  onKerning: (value: boolean) => void;
}
export function LayoutControls({ fontId, spacingPx, kerning, onSpacing, onKerning }: LayoutControlsProps): React.JSX.Element {
  return (
    <div className="grid gap-3">
      <div className="interactive-spacing m-0 flex min-w-0 flex-wrap items-end gap-x-5 gap-y-[.85rem] border-0 p-0">
        <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]">
          <Label htmlFor={`spacing-${fontId}`}>Tracking (px)</Label>
          <div className="interactive-axis flex items-center gap-[.55rem]">
            <input
              id={`spacing-${fontId}`}
              type="range"
              data-spacing
              className="w-40 max-w-[40vw] accent-brand"
              min={-2}
              max={4}
              step={1}
              value={spacingPx}
              onChange={(event) => onSpacing(Number(event.target.value))}
            />
            <Input
              type="number"
              data-spacing-number
              aria-label="Tracking (px)"
              className="w-[4.5rem]"
              min={-2}
              max={4}
              step={1}
              value={spacingPx}
              onChange={(event) => {
                const value = Number(event.target.value);
                if (Number.isFinite(value)) onSpacing(normalizedSpacing(value, "mono_1bit"));
              }}
            />
          </div>
        </div>
        <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]">
          <Label htmlFor={`kerning-${fontId}`}>Kerning</Label>
          <Switch
            id={`kerning-${fontId}`}
            data-kerning
            checked={kerning}
            onCheckedChange={onKerning}
          />
        </div>
      </div>
    </div>
  );
}
