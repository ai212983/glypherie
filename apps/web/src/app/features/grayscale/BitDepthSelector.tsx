import * as React from "react";
import { ResetButton } from "../../../components/ResetButton";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "../../../components/ui/toggle-group";
import bitDepthIcon from "../../../components/ui/assets/bit-depth.svg";
import type { CanvasFrame } from "../library/canvas-palettes.js";
import { GrayLevelSwatches } from "./GrayLevelSwatches";
import { paletteDepthLabel } from "./PaletteDepthLabel";

interface BitDepthSelectorProps {
  levels: readonly number[];
  selected: number;
  onSelect: (index: number) => void;
  onCountChange: (count: number) => void;
  readOnly: boolean;
  frame: CanvasFrame;
  children?: React.ReactNode;
  onReset?: () => void;
  resetDisabled?: boolean;
}

export function BitDepthSelector({ levels, selected, onSelect, onCountChange, readOnly, frame, children, onReset, resetDisabled }: BitDepthSelectorProps): React.JSX.Element {
  const id = React.useId();

  return (
    <Card className="p-[15px]" role="group" aria-labelledby={id}>
      <CardHeader className="items-center pb-[7px]">
        <CardTitle asChild>
          <h2 id={id}><span aria-hidden="true" className="block size-[11.25px] shrink-0 bg-current [mask-position:center] [mask-repeat:no-repeat]" style={{ maskImage: `url(${bitDepthIcon})` }} />Bit-depth &amp; gray levels</h2>
        </CardTitle>
        {onReset && <CardAction className="self-center">
          <ResetButton aria-label="Reset levels" disabled={readOnly || resetDisabled} onClick={onReset} />
        </CardAction>}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-[6px]">
          <div className="flex items-center justify-between gap-2 text-[10px] leading-4">
            <span className="font-semibold text-muted-foreground uppercase">Quantization depth</span>
          </div>
          <ToggleGroup
            type="single" value={String(levels.length)} disabled={readOnly}
            aria-label="Quantization depth" className="grid w-full grid-cols-4 gap-1"
            onValueChange={(count) => { if (count) onCountChange(Number(count)); }}
          >
            {[1, 2, 3, 4].map((depth) => (
              <ToggleGroupItem
                key={depth} value={String(2 ** depth)} aria-label={paletteDepthLabel(2 ** depth)}
                className="h-[44px] w-full min-w-0 flex-col gap-0 rounded-lg border border-border bg-background px-1 py-[6px] text-muted-foreground shadow-studio-inset hover:bg-background hover:text-foreground data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground data-[state=on]:shadow-xs"
              >
                <span className="text-[11px] leading-[14.5px] font-bold">{depth}-bit</span>
                <span className="text-[9px] leading-4 font-normal in-data-[state=on]:font-semibold">{2 ** depth} levels</span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        <div className="border-t border-border/80 pt-[5px]">
          <GrayLevelSwatches levels={levels} selected={selected} onSelect={onSelect} frame={frame} binary />
        </div>
        {children}
      </CardContent>
    </Card>
  );
}
