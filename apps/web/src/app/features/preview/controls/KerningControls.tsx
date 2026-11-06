import * as React from "react";
import { Label } from "../../../../components/ui/label";
import { Slider } from "../../../../components/ui/slider";
import { ResetButton } from "../../../../components/ResetButton";
import { Switch } from "../../../../components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../../components/ui/select";
import { TooltipHint } from "../../../../components/TooltipHint";
import {
  assertNever, defaultKerningState, editKerning, isKerningMethod, KERNING_METHODS, normalizeKerning, selectKerningMethod,
  HU_HERSCH_APERTURE_MAX, HU_HERSCH_APERTURE_MIN, HU_HERSCH_GLOBAL_MAX, HU_HERSCH_GLOBAL_MIN,
  type HuHerschSettings, type KerningEdit, type KerningPreference, type KerningState, type TypeFacetSettings,
} from "../../../kerning/model";

function SourceControls({ fontId, enabled, onChange }: {
  fontId: string; enabled: boolean; onChange: (enabled: boolean) => void;
}): React.JSX.Element {
  return (
    <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]">
      <TooltipHint content="Uses the font's source kerning with Glypherie's current spacing.">
        <Label htmlFor={`kerning-${fontId}`}>Kerning</Label>
      </TooltipHint>
      <Switch id={`kerning-${fontId}`} data-kerning checked={enabled} onCheckedChange={onChange} />
    </div>
  );
}

function KerningSlider({ id, label, description, value, min, max, step, defaultValue, dataAttribute, unit = "em", onChange }: {
  id: string; label: string; description: string; value: number; min: number; max: number; step: number;
  defaultValue: number; dataAttribute: string; unit?: string; onChange: (value: number) => void;
}): React.JSX.Element {
  const format = (number: number): string => `${number}${unit ? ` ${unit}` : ""}`;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <TooltipHint content={description}>
          <Label id={`${id}-label`} htmlFor={id}>{label}</Label>
        </TooltipHint>
        <output className="shrink-0 font-mono tabular-nums text-muted-foreground">{format(value)}</output>
      </div>
      {min === max ? (
        <div id={id} {...{ [dataAttribute]: true }} className="relative flex h-4 items-center opacity-50">
          <div className="h-1.5 w-full rounded-full bg-muted" aria-hidden="true" />
          <span role="slider" aria-disabled="true" aria-orientation="horizontal"
            aria-labelledby={`${id}-label`} aria-valuetext={format(value)}
            aria-valuenow={value} aria-valuemin={min} aria-valuemax={max}
            className="absolute left-1/2 size-4 -translate-x-1/2 rounded-full border border-primary bg-white shadow-sm" />
        </div>
      ) : (
        <Slider id={id} {...{ [dataAttribute]: true }} value={[value]} min={min} max={max} step={step}
          aria-labelledby={`${id}-label`} aria-valuetext={format(value)}
          onValueChange={([next]) => {
            if (next !== undefined && Number.isFinite(next) && next >= min && next <= max) onChange(next);
          }} />
      )}
      <div className="flex justify-between text-[.7rem] text-muted-foreground">
        <span>{format(min)}</span><span>Default {format(defaultValue)}</span><span>{format(max)}</span>
      </div>
    </div>
  );
}

function TypeFacetControls({ fontId, settings, onChange }: {
  fontId: string; settings: TypeFacetSettings; onChange: (settings: TypeFacetSettings) => void;
}): React.JSX.Element {
  const defaults = defaultKerningState().typefacet;
  const isDefault = Object.keys(defaults).every((key) => settings[key as keyof TypeFacetSettings] === defaults[key as keyof TypeFacetSettings]);
  return (
    <div className="flex flex-col gap-4 text-[.8rem]" data-typefacet-controls>
      <KerningSlider id={`typefacet-normal-${fontId}`} dataAttribute="data-typefacet-normal"
        label="Normal distance" description="Spacing around glyph bodies. Lower values generally tighten spacing. It cannot be smaller than minimum clearance."
        value={settings.normalDistanceEm} min={Math.max(0.01, settings.minimumDistanceEm)} max={0.5} step={0.005}
        defaultValue={defaults.normalDistanceEm} onChange={(normalDistanceEm) => onChange({ ...settings, normalDistanceEm })} />
      <KerningSlider id={`typefacet-intrusion-${fontId}`} dataAttribute="data-typefacet-intrusion"
        label="Intrusion tolerance" description="Allows details to enter the virtual spacing region. Actual ink overlap remains forbidden, and the intrusion balance test still applies."
        value={settings.intrusionToleranceEm} min={0} max={0.5} step={0.005}
        defaultValue={defaults.intrusionToleranceEm} onChange={(intrusionToleranceEm) => onChange({ ...settings, intrusionToleranceEm })} />
      <KerningSlider id={`typefacet-minimum-${fontId}`} dataAttribute="data-typefacet-minimum"
        label="Minimum clearance" description="Minimum separation of the glyph profiles. Zero permits touching. Increase normal distance first to allow a larger minimum clearance."
        value={settings.minimumDistanceEm} min={0} max={settings.normalDistanceEm} step={0.005}
        defaultValue={defaults.minimumDistanceEm} onChange={(minimumDistanceEm) => onChange({ ...settings, minimumDistanceEm })} />
      <KerningSlider id={`typefacet-overlap-${fontId}`} dataAttribute="data-typefacet-overlap"
        label="Maximum horizontal overlap" description="How far glyph bounding boxes may interlock horizontally, useful for diagonals and overhangs. This does not permit actual ink overlap."
        value={settings.maxXExtremaOverlapEm} min={0} max={0.5} step={0.005}
        defaultValue={defaults.maxXExtremaOverlapEm} onChange={(maxXExtremaOverlapEm) => onChange({ ...settings, maxXExtremaOverlapEm })} />
      <div className="flex items-center justify-between gap-2 text-muted-foreground">
        <p>Spacing changes appear in whole pixels.</p>
        <TooltipHint content="Reset all four TypeFacet controls to their defaults.">
          <ResetButton aria-label="Reset TypeFacet settings" disabled={isDefault} onClick={() => onChange(defaults)} />
        </TooltipHint>
      </div>
    </div>
  );
}

function HuHerschControls({ fontId, settings, onChange }: {
  fontId: string; settings: HuHerschSettings; onChange: (settings: HuHerschSettings) => void;
}): React.JSX.Element {
  const defaults = defaultKerningState().hu_hersch;
  const isDefault = settings.apertureDepthFactor === defaults.apertureDepthFactor
    && settings.globalDepthFactor === defaults.globalDepthFactor;
  return (
    <div className="flex flex-col gap-4 text-[.8rem]" data-hu-hersch-controls>
      <KerningSlider id={`hu-hersch-cavity-${fontId}`} dataAttribute="data-hu-hersch-cavity"
        label="Cavity depth" description="How deep open cavities may read, as a fraction of the cavity opening height (patent depth factor, default 0.21). Lower values fill cavities more."
        value={settings.apertureDepthFactor} min={HU_HERSCH_APERTURE_MIN} max={HU_HERSCH_APERTURE_MAX} step={0.01}
        defaultValue={defaults.apertureDepthFactor} unit=""
        onChange={(apertureDepthFactor) => onChange({ ...settings, apertureDepthFactor })} />
      <KerningSlider id={`hu-hersch-visual-${fontId}`} dataAttribute="data-hu-hersch-visual"
        label="Maximum visual depth" description="How far glyph walls may recess, as a fraction of the reference body height (patent global factor, default 0.25). Both controls also move the shared density target."
        value={settings.globalDepthFactor} min={HU_HERSCH_GLOBAL_MIN} max={HU_HERSCH_GLOBAL_MAX} step={0.01}
        defaultValue={defaults.globalDepthFactor} unit=""
        onChange={(globalDepthFactor) => onChange({ ...settings, globalDepthFactor })} />
      <p className="text-muted-foreground">For Latin letter pairs and proportional digits. Tabular digit pairs, unsupported pairs and unavailable calibration retain Source spacing.</p>
      <div className="flex items-center justify-between gap-2 text-muted-foreground">
        <p>Spacing changes appear in whole pixels.</p>
        <TooltipHint content="Reset both Hu/Hersch depth controls to their defaults.">
          <ResetButton aria-label="Reset Hu/Hersch depths" disabled={isDefault} onClick={() => onChange(defaults)} />
        </TooltipHint>
      </div>
    </div>
  );
}

function FontForgeControls(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-3 text-[.8rem]" data-fontforge-controls>
      <p className="text-muted-foreground">Always applies the full source-relative correction to supported pairs. Tabular digit pairs, unsupported pairs and missing measurements retain Source spacing.</p>
    </div>
  );
}

function ActiveMethodControls({ fontId, state, onEdit }: {
  fontId: string; state: KerningState; onEdit: (edit: KerningEdit) => void;
}): React.JSX.Element {
  switch (state.method) {
    case "source": return <SourceControls fontId={fontId} enabled={state.source.enabled}
      onChange={(enabled) => onEdit({ method: "source", settings: { enabled } })} />;
    case "typefacet": return <TypeFacetControls fontId={fontId} settings={state.typefacet}
      onChange={(settings) => onEdit({ method: "typefacet", settings })} />;
    case "hu_hersch": return <HuHerschControls fontId={fontId} settings={state.hu_hersch}
      onChange={(settings) => onEdit({ method: "hu_hersch", settings })} />;
    case "fontforge": return <FontForgeControls />;
    default: return assertNever(state.method);
  }
}

export function KerningControls({ fontId, value, onChange }: {
  fontId: string;
  value: KerningPreference;
  onChange: (value: KerningPreference) => void;
}): React.JSX.Element {
  const state = normalizeKerning(value);
  const id = `kerning-method-${fontId}`;
  return (
    <div className="flex min-w-0 flex-col gap-3" data-kerning-controls>
      <div className="interactive-field flex flex-col gap-[.35rem] text-[.8rem]">
        <Label htmlFor={id}>Kerning method</Label>
        <Select value={state.method} onValueChange={(method) => {
          if (isKerningMethod(method)) onChange(selectKerningMethod(value, method));
        }}>
          <SelectTrigger id={id} data-kerning-method><SelectValue /></SelectTrigger>
          <SelectContent>
            {Object.entries(KERNING_METHODS).map(([method, description]) => (
              <SelectItem key={method} value={method}>
                {description.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {state.method !== "source" && (
        <p className="text-[.8rem] text-muted-foreground">{KERNING_METHODS[state.method].description}</p>
      )}
      <ActiveMethodControls fontId={fontId} state={state}
        onEdit={(edit) => onChange(editKerning(value, edit))} />
    </div>
  );
}
