import * as React from "react";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Slider } from "./ui/slider";
import { FONT_SIZE_MAX, FONT_SIZE_MIN, FONT_SIZE_STOPS, fontSizePosition, isFontSize } from "./font-size";

interface FontSizeControlProps {
  id?: string;
  sizePx: number;
  disabled?: boolean;
  onSize: (value: number) => void;
}

export function FontSizeControl({ id, sizePx, disabled = false, onSize }: FontSizeControlProps): React.JSX.Element {
  const generatedId = React.useId();
  const inputId = id ?? `font-size-${generatedId}`;
  const labelId = `${inputId}-label`;
  const [draft, setDraft] = React.useState({ size: sizePx, text: String(sizePx) });

  return (
    <div className="interactive-field flex min-w-0 flex-col gap-2" data-font-size-control data-value={sizePx}>
      <div className="flex items-center justify-between gap-3">
        <Label id={labelId} htmlFor={inputId} variant="studio">Size</Label>
        <div className="relative w-24 shrink-0">
          <Input
            id={inputId}
            type="number"
            data-size-px
            aria-describedby={`${inputId}-unit`}
            min={FONT_SIZE_MIN}
            max={FONT_SIZE_MAX}
            step="any"
            disabled={disabled}
            className="h-8 w-full pr-8 pl-2 text-right tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
            value={draft.size === sizePx ? draft.text : String(sizePx)}
            onChange={(event) => {
              const value = event.target.valueAsNumber;
              setDraft({ size: isFontSize(value) ? value : sizePx, text: event.target.value });
              if (isFontSize(value)) onSize(value);
            }}
            onBlur={(event) => {
              const value = event.target.valueAsNumber;
              const next = Number.isFinite(value) ? Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, value)) : sizePx;
              setDraft({ size: next, text: String(next) });
              if (next !== sizePx) onSize(next);
            }}
          />
          <span id={`${inputId}-unit`} className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-xs text-muted-foreground">px</span>
        </div>
      </div>
      <div className="px-2">
        <Slider
          aria-labelledby={labelId}
          aria-valuetext={`${sizePx} pixels`}
          min={0}
          max={FONT_SIZE_STOPS.length - 1}
          step={1}
          value={[fontSizePosition(sizePx)]}
          disabled={disabled}
          className="h-6"
          onValueChange={([position]) => {
            if (position !== undefined) onSize(FONT_SIZE_STOPS[Math.round(position)]!);
          }}
          onKeyDownCapture={(event) => {
            // From a custom value, arrows choose the immediate neighboring
            // preset rather than adding one to a fractional slider index.
            let next: number | undefined;
            if (event.key === "ArrowRight" || event.key === "ArrowUp") {
              next = FONT_SIZE_STOPS.find((size) => size > sizePx) ?? FONT_SIZE_STOPS.at(-1);
            } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
              next = [...FONT_SIZE_STOPS].reverse().find((size) => size < sizePx) ?? FONT_SIZE_STOPS[0];
            }
            if (next !== undefined && !disabled) {
              event.preventDefault();
              onSize(next);
            }
          }}
        />
        <div className="relative h-6 text-[10px] text-muted-foreground tabular-nums">
          {FONT_SIZE_STOPS.map((size, index) => (
            <button
              key={size}
              type="button"
              data-size-stop={size}
              aria-label={`${size} px`}
              aria-pressed={sizePx === size}
              disabled={disabled}
              className="absolute top-0 flex h-6 min-w-6 -translate-x-1/2 flex-col items-center rounded-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50 aria-pressed:font-bold aria-pressed:text-foreground"
              style={{ left: `${index / (FONT_SIZE_STOPS.length - 1) * 100}%` }}
              onClick={() => onSize(size)}
            >
              <span aria-hidden="true" className="mb-0.5 h-1 w-px bg-current" />
              {size}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
