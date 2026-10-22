import * as React from "react";
import { Input } from "../../../components/ui/input";
import { Textarea } from "../../../components/ui/textarea";
import { Label } from "../../../components/ui/label";

interface SampleTextControlProps extends Omit<React.ComponentProps<typeof Input>, "type" | "className" | "value" | "onChange"> {
  label?: string;
  value: string;
  onValueChange: (text: string) => void;
}

const SAMPLE_TEXT_LABEL = "Sample text";
const sampleTextInputClass = "rounded-none border-0 bg-transparent p-0 text-[12px] leading-6 shadow-none focus-visible:outline-none focus-visible:ring-0 md:text-[12px] dark:bg-transparent";

function SampleTextField({ id, label, hideLabel = false, children }: { id: string; label: string; hideLabel?: boolean; children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="relative flex w-full flex-col gap-1 rounded-lg border border-primary/40 bg-background p-2 shadow-studio-inset focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
      <Label htmlFor={id} variant="studio" className={hideLabel ? "sr-only" : undefined}>{label}</Label>
      {children}
    </div>
  );
}

interface SampleTextAreaControlProps extends Omit<React.ComponentProps<typeof Textarea>, "className" | "value" | "onChange"> {
  label?: string;
  hideLabel?: boolean;
  value: string;
  onValueChange: (text: string) => void;
}

export function SampleTextAreaControl({
  id: providedId, label = SAMPLE_TEXT_LABEL, hideLabel, value, onValueChange, maxLength, ...props
}: SampleTextAreaControlProps): React.JSX.Element {
  const generatedId = React.useId();
  const id = providedId ?? generatedId;
  return (
    <SampleTextField id={id} label={label} hideLabel={hideLabel}>
      <Textarea
        {...props}
        id={id}
        autoComplete="off"
        spellCheck={false}
        maxLength={maxLength}
        value={value}
        onChange={(event) => onValueChange(maxLength === undefined ? event.target.value : event.target.value.slice(0, maxLength))}
        className={`min-h-[calc(3lh+2px)] ${sampleTextInputClass}`}
      />
    </SampleTextField>
  );
}

export function SampleTextControl({
  id: providedId, label = SAMPLE_TEXT_LABEL, value, onValueChange, maxLength, ...props
}: SampleTextControlProps): React.JSX.Element {
  const generatedId = React.useId();
  const id = providedId ?? generatedId;
  return (
    <SampleTextField id={id} label={label}>
      <Input
        {...props}
        id={id}
        type="text"
        autoComplete="off"
        spellCheck={false}
        maxLength={maxLength}
        value={value}
        onChange={(event) => onValueChange(maxLength === undefined ? event.target.value : event.target.value.slice(0, maxLength))}
        className={`h-6 ${sampleTextInputClass}`}
      />
    </SampleTextField>
  );
}
