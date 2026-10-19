import * as React from "react";
import type { StoredFont } from "../../../fonts/storage.js";
import { MAX_TEXT_LENGTH } from "../../../renderer/render-spec";
import { TEXT_PRESETS, presetForText } from "../presets";
import { Button } from "../../../../components/ui/button";
import { Label } from "../../../../components/ui/label";
import { Input } from "../../../../components/ui/input";
import { Textarea } from "../../../../components/ui/textarea";
import { NativeSelect, NativeSelectOption } from "../../../../components/ui/native-select";
import { displayName } from "../../../fonts/metadata";

interface SpecimenControlsProps {
  font: StoredFont;
  sizePx: number;
  spacingPx: number;
  kerning: boolean;
  text: string;
  onSize: (sizePx: number) => void;
  onSpacing: (spacingPx: number) => void;
  onKerning: (kerning: boolean) => void;
  onText: (text: string) => void;
  onReset: () => void;
}

export function SpecimenControls({
  font, sizePx, spacingPx, kerning, text, onSize, onSpacing, onKerning, onText, onReset,
}: SpecimenControlsProps): React.JSX.Element {
  return (
    <fieldset className="interactive-controls m-0 flex flex-wrap items-end gap-x-5 gap-y-[.85rem] border-0 p-0">
      <legend className="visually-hidden sr-only">{displayName(font)} interactive controls</legend>
      <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]">
        <Label htmlFor={`size-${font.id}`}>Font size (px)</Label>
        <Input
          id={`size-${font.id}`}
          type="number"
          data-size-px
          min={1}
          max={512}
          step={0.5}
          value={sizePx}
          onChange={(event) => {
            const value = Number(event.target.value);
            if (Number.isFinite(value)) onSize(Math.min(512, Math.max(1, value)));
          }}
        />
      </div>
      <fieldset className="interactive-spacing m-0 flex min-w-0 flex-wrap items-end gap-x-5 gap-y-[.85rem] border-0 p-0">
        <legend className="p-0 text-[.8rem] font-semibold">Spacing and kerning</legend>
        <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]">
          <Label htmlFor={`spacing-${font.id}`}>Spacing (px)</Label>
          <div className="interactive-axis flex items-center gap-[.55rem]">
            <input
              id={`spacing-${font.id}`}
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
              aria-label="Spacing (px)"
              className="w-[4.5rem]"
              min={-2}
              max={4}
              step={1}
              value={spacingPx}
              onChange={(event) => {
                const value = Number(event.target.value);
                if (Number.isFinite(value)) onSpacing(Math.min(4, Math.max(-2, value)));
              }}
            />
          </div>
        </div>
        <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]">
          <Label htmlFor={`kerning-${font.id}`}>Kerning</Label>
          <input
            id={`kerning-${font.id}`}
            type="checkbox"
            data-kerning
            className="m-0 h-4 w-4 cursor-pointer accent-brand"
            checked={kerning}
            onChange={(event) => onKerning(event.target.checked)}
          />
        </div>
      </fieldset>
      <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]">
        <Label htmlFor={`preset-${font.id}`}>Preset</Label>
        <NativeSelect
          id={`preset-${font.id}`}
          data-preset
          value={presetForText(text)}
          onChange={(event) => {
            const id = event.target.value;
            if (id === "custom") return;
            const content = TEXT_PRESETS.find((preset) => preset.id === id)?.content;
            if (content !== undefined) onText(content.slice(0, MAX_TEXT_LENGTH));
          }}
        >
          {TEXT_PRESETS.map((preset) => (
            <NativeSelectOption key={preset.id} value={preset.id}>{preset.title}</NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <div className="interactive-field interactive-text flex flex-[1_1_100%] flex-col gap-[.35rem] text-[.8rem]">
        <Label htmlFor={`text-${font.id}`}>Sample text</Label>
        <Textarea
          id={`text-${font.id}`}
          data-text
          rows={4}
          maxLength={MAX_TEXT_LENGTH}
          autoComplete="off"
          spellCheck={false}
          value={text}
          onChange={(event) => onText(event.target.value.slice(0, MAX_TEXT_LENGTH))}
        />
      </div>
      <Button data-reset onClick={onReset}>
        Reset
      </Button>
    </fieldset>
  );
}
