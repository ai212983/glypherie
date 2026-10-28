import * as React from "react";
import type { CanvasFrame } from "../library/canvas-palettes.js";

interface GrayLevelSwatchesProps {
  levels: readonly number[];
  selected: number;
  onSelect: (index: number) => void;
  frame: CanvasFrame;
  binary?: boolean;
}

export function GrayLevelSwatches({ levels, selected, onSelect, frame, binary = false }: GrayLevelSwatchesProps): React.JSX.Element {
  const bits = Math.ceil(Math.log2(levels.length));
  const code = (index: number): string => `${index.toString(2).padStart(bits, "0")}b`;
  // Binary codes identify editable levels from paper to full ink.
  const indices = levels.map((_, index) => index);
  const ticks = [...new Set([0, ...[1, 2, 3].map((tick) => Math.min(levels.length - 1, Math.round(tick * levels.length / 4))), levels.length - 1])];
  return (
    <div className={`flex min-w-0 flex-col ${binary ? "gap-[6px] text-muted-foreground" : "gap-1"}`} role="group" aria-label="Gray level swatches" style={binary ? undefined : { color: frame.mutedCss }}>
      <div className="min-w-0 overflow-x-auto">
        <div className="flex h-5 w-max min-w-full gap-1 rounded-[4px] border p-[3px]" style={binary ? { borderColor: "#b8ae9d", backgroundColor: "#e4dac8" } : { borderColor: frame.borderCss, backgroundColor: frame.paperCss }}>
          {indices.map((index) => {
            const gray = levels[index] ?? 0;
            return (
              <button
                key={index}
                type="button"
                aria-label={`Select level ${index}`}
                aria-pressed={selected === index}
                className="h-full min-w-3 flex-1 cursor-pointer rounded-[2px] border border-black/20 p-0 outline-none hover:outline-solid hover:outline-1 hover:outline-offset-2 hover:outline-ring/40 focus-visible:outline-solid focus-visible:outline-2! focus-visible:outline-offset-2 focus-visible:outline-ring! aria-pressed:outline-solid aria-pressed:outline-1 aria-pressed:outline-offset-2 aria-pressed:outline-ring/40"
                style={{ backgroundColor: `rgb(${gray} ${gray} ${gray})` }}
                onClick={() => onSelect(index)}
              />
            );
          })}
        </div>
      </div>
      {binary && <div aria-hidden="true" className="flex justify-between px-[2px] font-studio text-[8px] leading-4">
        {ticks.map((tick) => <span key={tick}>{code(tick)}{tick === 0 ? " · Paper" : tick === levels.length - 1 ? " · Full ink" : ""}</span>)}
      </div>}
    </div>
  );
}
