import * as React from "react";
import { TooltipHint } from "../../../../components/TooltipHint";
import { SlidersVertical } from "lucide-react";
import type { StoredFont } from "../../../fonts/storage.js";
import { controlAxes, displayName } from "../../../fonts/metadata";
import { ResetButton } from "../../../../components/ResetButton";
import { Label } from "../../../../components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "../../../../components/ui/card";

interface AxisControlsProps {
  font: StoredFont;
  axes: Record<string, number>;
  advancedOpen: boolean;
  onAxes: (axes: Record<string, number>) => void;
  onAdvancedOpen: (open: boolean) => void;
  appearance?: "classic" | "studio" | "embedded";
}

export function AxisControls({ font, axes, advancedOpen, onAxes, onAdvancedOpen, appearance = "classic" }: AxisControlsProps): React.JSX.Element | null {
  const controls = controlAxes(font.metadata);
  if (controls.length === 0) return null;
  const visible = controls.filter((axis) => !axis.hidden);
  const hidden = controls.filter((axis) => axis.hidden);
  const renderAxis = (axis: (typeof controls)[number]): React.JSX.Element => (
    <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]" key={axis.tag}>
      <div className="interactive-axis-heading flex items-center justify-between gap-2">
        <TooltipHint content={axis.name !== axis.tag ? axis.tag : undefined}>
          <Label htmlFor={`axis-${font.id}-${axis.tag}`}>{axis.name}</Label>
        </TooltipHint>
        <ResetButton
          data-axis-reset={axis.tag}
          aria-label={`Reset ${axis.name} (${axis.tag}) to default`}
          disabled={(axes[axis.tag] ?? axis.defaultValue) === axis.defaultValue}
          onClick={() => onAxes({ ...axes, [axis.tag]: axis.defaultValue })}
        />
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
  const fields = (
    <>
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
    </>
  );
  if (appearance === "embedded") return (
    <div className="interactive-axes grid gap-4" aria-label={`${displayName(font)} variable axes`}>
      <h3 className="m-0 text-[.8rem] font-semibold">Axes</h3>
      {fields}
    </div>
  );
  if (appearance === "studio") {
    return (
      <Card className="interactive-axes" aria-label={`${displayName(font)} variable axes`}>
        <CardHeader>
          <CardTitle asChild>
            <h2><SlidersVertical aria-hidden="true" className="size-3 shrink-0" />Axes</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          {fields}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card variant="plain" className="interactive-axes mb-4 gap-4 p-4" aria-label={`${displayName(font)} variable axes`}>
      <CardHeader className="px-0">
        <CardTitle className="flex items-center gap-[6px] text-[.875rem] text-studio-heading"><SlidersVertical aria-hidden="true" className="size-3 shrink-0" />Axes</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 px-0">
        {fields}
      </CardContent>
    </Card>
  );
}
