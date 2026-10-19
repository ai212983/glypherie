import * as React from "react";
import type { StoredFont } from "../../../fonts/storage.js";
import { controlAxes, displayName } from "../../../fonts/metadata";
import { Button } from "../../../../components/ui/button";
import { Label } from "../../../../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../../../../components/ui/card";

interface AxisControlsProps {
  font: StoredFont;
  axes: Record<string, number>;
  advancedOpen: boolean;
  onAxes: (axes: Record<string, number>) => void;
  onAdvancedOpen: (open: boolean) => void;
}

export function AxisControls({ font, axes, advancedOpen, onAxes, onAdvancedOpen }: AxisControlsProps): React.JSX.Element | null {
  const controls = controlAxes(font.metadata);
  if (controls.length === 0) return null;
  const visible = controls.filter((axis) => !axis.hidden);
  const hidden = controls.filter((axis) => axis.hidden);
  const renderAxis = (axis: (typeof controls)[number]): React.JSX.Element => (
    <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]" key={axis.tag}>
      <div className="interactive-axis-heading flex items-baseline justify-between gap-2">
        <Label htmlFor={`axis-${font.id}-${axis.tag}`}>{axis.name} ({axis.tag})</Label>
        <Button
          size="sm"
          variant="outline"
          data-axis-reset={axis.tag}
          aria-label={`Reset ${axis.name} (${axis.tag}) to default`}
          title="Restore default value"
          onClick={() => onAxes({ ...axes, [axis.tag]: axis.defaultValue })}
        >
          Reset
        </Button>
      </div>
      <div className="interactive-axis flex items-center gap-[.55rem]">
        <input
          id={`axis-${font.id}-${axis.tag}`}
          type="range"
          data-axis={axis.tag}
          min={axis.min}
          max={axis.max}
          step={axis.step}
          value={axes[axis.tag] ?? axis.defaultValue}
          onChange={(event) => onAxes({ ...axes, [axis.tag]: Number(event.target.value) })}
          className="w-full max-w-none min-w-0 accent-brand"
        />
        <output data-axis-value={axis.tag}>{axes[axis.tag] ?? axis.defaultValue}</output>
      </div>
    </div>
  );
  return (
    <Card className="interactive-axes mb-4 gap-4 p-4" aria-label={`${displayName(font)} variable axes`}>
      <CardHeader className="px-0">
        <CardTitle className="text-[.875rem]">Variable axes</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 px-0">
        {visible.map(renderAxis)}
        {hidden.length > 0 && (
          <details
            className="interactive-advanced-axes min-w-0 border-t border-solid border-line pt-4"
            open={advancedOpen}
            onToggle={(event) => onAdvancedOpen((event.target as HTMLDetailsElement).open)}
          >
            <summary className="cursor-pointer text-[.8rem] font-semibold">Advanced axes</summary>
            <div className="interactive-advanced-axis-controls mt-4 grid gap-4">
              {hidden.map(renderAxis)}
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
