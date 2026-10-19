import * as React from "react";
import type { OutputProfile, RendererRole, StemFitting } from "../../../renderer/renderer-types.js";
import { effectiveZoom, formatEffectiveZoom, magnification } from "../../../renderer/display-scaling.js";
import { Label } from "../../../../components/ui/label";
import { NativeSelect, NativeSelectOption } from "../../../../components/ui/native-select";

const ZOOM_STOPS = [1, 2, 3, 4];
const PROFILES: { id: OutputProfile; label: string }[] = [
  { id: "mono_1bit", label: "1-bit" },
  { id: "gray_3bit", label: "3-bit" },
];
const ROLES: { id: RendererRole; label: string }[] = [
  { id: "candidate", label: "Candidate (preview)" },
  { id: "baseline", label: "Baseline" },
  { id: "reference", label: "Reference" },
];

interface RendererControlsProps {
  profile: OutputProfile;
  role: RendererRole;
  stemFitting: StemFitting;
  zoom: number;
  pixelAccurate: boolean;
  rendererAvailable: boolean | null;
  ratio: number;
  onProfile: (profile: OutputProfile) => void;
  onRole: (role: RendererRole) => void;
  onStemFitting: (stemFitting: StemFitting) => void;
  onZoom: (zoom: number) => void;
  onPixelAccurate: (pixelAccurate: boolean) => void;
}

export function RendererControls({
  profile, role, stemFitting, zoom, pixelAccurate, rendererAvailable, ratio,
  onProfile, onRole, onStemFitting, onZoom, onPixelAccurate,
}: RendererControlsProps): React.JSX.Element {
  const zoomIndex = ZOOM_STOPS.indexOf(zoom);
  const showStem = role === "candidate" && profile === "mono_1bit";
  const mag = magnification(zoom, ratio);
  const disabled = rendererAvailable !== true;
  return (
    <div className="header-controls flex flex-wrap items-start gap-6">
      <fieldset className="profile-switch m-0 border-0 p-0" id="output-mode" disabled={disabled}>
        <legend className="mb-[.6rem] p-0 text-[.875rem] font-semibold">Output mode</legend>
        <div className="profile-options flex rounded-[6px] border border-solid border-line bg-card p-0.75">
          {PROFILES.map((entry) => (
            <label key={entry.id} className="relative cursor-pointer">
              <input
                type="radio"
                name="output-profile"
                value={entry.id}
                checked={profile === entry.id}
                onChange={() => onProfile(entry.id)}
                className="peer absolute inset-0 m-0 h-full w-full cursor-pointer opacity-0"
              />
              <span className="block rounded-[3px] bg-card px-[.85rem] py-[.45rem] text-[.875rem] text-soft peer-checked:bg-brand peer-checked:text-brand-contrast peer-focus-visible:ring-[3px] peer-focus-visible:ring-brand peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-page">{entry.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid max-w-65 gap-2 text-[.875rem] font-semibold">
        <Label htmlFor="renderer-role">Renderer</Label>
        <NativeSelect
          id="renderer-role"
          value={role}
          onChange={(event) => onRole(event.target.value as RendererRole)}
          disabled={disabled}
        >
          {ROLES.map((entry) => <NativeSelectOption key={entry.id} value={entry.id}>{entry.label}</NativeSelectOption>)}
        </NativeSelect>
      </div>
      <div className="grid max-w-65 gap-2 text-[.875rem] font-semibold" id="stem-fitting-control" hidden={!showStem}>
        <Label htmlFor="stem-fitting">Stem fitting</Label>
        <NativeSelect
          id="stem-fitting"
          aria-describedby="stem-fitting-hint"
          value={stemFitting === "upstream_mono" ? "upstream_mono" : ""}
          onChange={(event) => onStemFitting(
            event.target.value === "upstream_mono" ? "upstream_mono" : "font_hints_first",
          )}
          disabled={!showStem || disabled}
        >
          <NativeSelectOption value="">Font hints first</NativeSelectOption>
          <NativeSelectOption value="upstream_mono">Automatic Mono</NativeSelectOption>
        </NativeSelect>
        <span id="stem-fitting-hint" className="text-[.75rem] font-normal leading-[1.4] text-soft">
          Font hints first uses embedded instructions when available, otherwise automatic fitting.
        </span>
      </div>
      <div className="zoom-control w-60">
        <div className="zoom-heading flex items-baseline justify-between gap-2 text-[.875rem] font-semibold">
          <Label htmlFor="zoom">Zoom</Label>
          <output id="zoom-value" htmlFor="zoom">{`${zoom}×`}</output>
        </div>
        <input
          id="zoom"
          type="range"
          min={0}
          max={3}
          step={1}
          value={zoomIndex < 0 ? 0 : zoomIndex}
          aria-valuetext={`${zoom}×`}
          disabled={disabled}
          onChange={(event) => {
            const stop = ZOOM_STOPS[Number(event.target.value)] ?? 1;
            onZoom(stop);
          }}
          className="mx-0 my-[.6rem] block w-full cursor-pointer accent-brand"
        />
        <div className="zoom-stops flex justify-between px-0.75 text-[.75rem] text-soft" aria-hidden="true">
          <span>1×</span><span>2×</span><span>3×</span><span>4×</span>
        </div>
        <label className="pixel-accurate mt-[.55rem] flex cursor-pointer items-baseline gap-[.45rem] text-[.75rem]" title="Each pixel of the interactive text maps to a whole number of screen pixels. Its displayed size adjusts slightly to the magnification actually achieved.">
          <input
            id="pixel-accurate"
            type="checkbox"
            className="w-auto cursor-pointer accent-brand"
            checked={pixelAccurate}
            disabled={disabled}
            onChange={(event) => onPixelAccurate(event.target.checked)}
          />
          <span>Pixel-accurate display</span>
        </label>
        <p className="pixel-accurate-status mt-[.3rem] text-[.75rem] text-soft">
          <output id="pixel-accurate-status" aria-live="polite" hidden={!pixelAccurate}>
            {`Effective ${formatEffectiveZoom(effectiveZoom(mag, ratio))} · ${mag} screen px per font px`}
          </output>
        </p>
      </div>
    </div>
  );
}
