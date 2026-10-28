import * as React from "react";
import { MAX_TEXT_LENGTH } from "../../../renderer/render-spec";
import { TEXT_PRESETS, presetForText } from "../presets";
import { Label } from "../../../../components/ui/label";
import { Textarea } from "../../../../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../../components/ui/select";

import { SampleTextAreaControl } from "../../library/SampleTextControl";

interface SpecimenControlsProps {
  controlId: string;
  legend: string;
  text: string;
  onText: (text: string) => void;
  inheritance?: { active: boolean; onInherit: () => void };
  maxLength?: number;
  insetSampleText?: boolean;
  hideTextLabel?: boolean;
  inlinePreset?: boolean;
}

export function SpecimenControls({
  controlId, legend, text, onText, inheritance, maxLength = MAX_TEXT_LENGTH, insetSampleText = false, hideTextLabel = false, inlinePreset = false,
}: SpecimenControlsProps): React.JSX.Element {
  const presetId = inheritance?.active ? "inherit" : presetForText(text);
  return (
    <fieldset className="interactive-controls m-0 flex flex-wrap items-end gap-x-5 gap-y-[.85rem] border-0 p-0">
      <legend className="visually-hidden sr-only">{legend}</legend>
      <div className={inlinePreset ? "interactive-field flex w-full items-center gap-3 text-[.8rem]" : "interactive-field flex flex-col gap-[.35rem] text-[.8rem]"}>
        <Label htmlFor={`preset-${controlId}`} className="shrink-0">Preset</Label>
        <Select
          value={presetId}
          onValueChange={(id) => {
            if (id === "inherit") { inheritance?.onInherit(); return; }
            if (id === "custom") return;
            const content = TEXT_PRESETS.find((preset) => preset.id === id)?.content;
            if (content !== undefined) onText(content.slice(0, maxLength));
          }}
        >
          <SelectTrigger id={`preset-${controlId}`} data-preset className={inlinePreset ? "w-fit! min-w-0 flex-none" : undefined}>
            <SelectValue>{presetId === "custom" ? "Custom" : undefined}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {inheritance && <SelectItem value="inherit">Default</SelectItem>}
            {TEXT_PRESETS.filter((preset) => preset.id !== "custom").map((preset) => (
              <SelectItem key={preset.id} value={preset.id}>{preset.title}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {insetSampleText ? (
        <SampleTextAreaControl hideLabel={hideTextLabel} id={`text-${controlId}`} data-text rows={3} maxLength={maxLength} value={text} onValueChange={onText} />
      ) : <div className="interactive-field interactive-text flex flex-[1_1_100%] flex-col gap-[.35rem] text-[.8rem]">
        <Label htmlFor={`text-${controlId}`}>Sample text</Label>
        <Textarea
          id={`text-${controlId}`}
          data-text
          rows={3}
          className="min-h-[calc(3lh+1rem+2px)]"
          maxLength={maxLength}
          autoComplete="off"
          spellCheck={false}
          value={text}
          onChange={(event) => onText(event.target.value.slice(0, maxLength))}
        />
      </div>}
    </fieldset>
  );
}
