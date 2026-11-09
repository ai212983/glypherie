// Structured character-coverage control shared by the standalone exporter
// and the Scene page. Named presets plus custom inclusive numeric ranges
// are the persisted model; the free-text field below is only an input
// adapter into parseCustomRange, never product state.
import * as React from "react";
import { Plus, X } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Switch } from "../../../components/ui/switch";
import { TooltipHint } from "../../../components/TooltipHint";
import {
  COVERAGE_PRESETS,
  COVERAGE_PRESET_IDS,
  coverageCount,
  formatCustomRange,
  normalizeCoverage,
  parseCustomRange,
  resolveCoverage,
  splitCoverageByAvailability,
  type CharacterCoverage,
  type CodepointRange,
  type CoveragePresetId,
} from "../../domain/coverage.ts";

export interface CoverageControlProps {
  coverage: CharacterCoverage;
  onCoverage: (next: CharacterCoverage) => void;
  disabled?: boolean;
  // Font metadata coverage; when present the summary reports covered and
  // missing scalars explicitly instead of leaving gaps silent.
  availableRanges?: readonly CodepointRange[];
}

function togglePreset(coverage: CharacterCoverage, id: CoveragePresetId): CharacterCoverage {
  const active = coverage.presetIds.includes(id);
  return normalizeCoverage({
    presetIds: active ? coverage.presetIds.filter((entry) => entry !== id) : [...coverage.presetIds, id],
    extraRanges: coverage.extraRanges,
  });
}

export function CoverageControl({
  coverage,
  onCoverage,
  disabled,
  availableRanges,
}: CoverageControlProps): React.JSX.Element {
  const [customText, setCustomText] = React.useState("");
  const [customError, setCustomError] = React.useState("");
  const id = React.useId();
  const resolved = React.useMemo(() => resolveCoverage(coverage), [coverage]);
  const total = coverageCount(resolved);
  const split = React.useMemo(
    () => (availableRanges ? splitCoverageByAvailability(resolved, availableRanges) : null),
    [resolved, availableRanges],
  );
  const covered = split ? coverageCount(split.covered) : total;
  const missing = split?.missing ?? [];

  const addCustom = (): void => {
    const text = customText.trim();
    if (!text) return;
    try {
      const range = parseCustomRange(text);
      onCoverage(normalizeCoverage({ presetIds: coverage.presetIds, extraRanges: [...coverage.extraRanges, range] }));
      setCustomText("");
      setCustomError("");
    } catch (error) {
      setCustomError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <div className="flex flex-col gap-3" data-coverage-control>
      <fieldset className="relative m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
        <legend className="sr-only">Character presets</legend>
        {COVERAGE_PRESET_IDS.map((presetId) => {
          const preset = COVERAGE_PRESETS[presetId];
          const checked = coverage.presetIds.includes(presetId);
          return (
            <div key={presetId} className="flex items-center justify-between gap-3">
              <TooltipHint content={preset.summary}>
                <Label htmlFor={`${id}-${presetId}`} className="text-xs">
                  {preset.label}
                </Label>
              </TooltipHint>
              <Switch
                id={`${id}-${presetId}`}
                data-coverage-preset={presetId}
                checked={checked}
                disabled={disabled}
                onCheckedChange={() => onCoverage(togglePreset(coverage, presetId))}
                aria-label={`${preset.label} preset`}
              />
            </div>
          );
        })}
      </fieldset>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${id}-custom`} className="text-xs">
          Custom range
        </Label>
        <div className="flex gap-2">
          <Input
            id={`${id}-custom`}
            data-coverage-custom
            value={customText}
            disabled={disabled}
            autoComplete="off"
            spellCheck={false}
            placeholder="(0x2500-0x257F)"
            onChange={(event) => {
              setCustomText(event.target.value);
              setCustomError("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addCustom();
              }
            }}
          />
          <TooltipHint content="Add an inclusive Unicode range">
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              data-coverage-add
              disabled={disabled || !customText.trim()}
              aria-label="Add custom range"
              onClick={addCustom}
            >
              <Plus aria-hidden="true" />
            </Button>
          </TooltipHint>
        </div>
        {customError && (
          <p role="alert" className="m-0 text-xs" data-coverage-error>
            {customError}
          </p>
        )}
        {coverage.extraRanges.length > 0 && (
          <ul className="m-0 flex list-none flex-wrap gap-1 p-0">
            {coverage.extraRanges.map((range, index) => (
              <li
                key={`${range.start}-${range.end}-${index}`}
                className="flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-xs"
              >
                <span>{formatCustomRange(range)}</span>
                <button
                  type="button"
                  data-coverage-remove={index}
                  disabled={disabled}
                  aria-label={`Remove range ${formatCustomRange(range)}`}
                  className="cursor-pointer bg-transparent p-0 text-soft underline"
                  onClick={() =>
                    onCoverage(
                      normalizeCoverage({
                        presetIds: coverage.presetIds,
                        extraRanges: coverage.extraRanges.filter((_, drop) => drop !== index),
                      }),
                    )
                  }
                >
                  <X aria-hidden="true" className="size-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="m-0 text-xs text-soft" data-coverage-count>
        {split ? `${covered} of ${total} characters in this font` : `${total} characters`}
      </p>
      {missing.length > 0 && (
        <p className="m-0 text-xs text-soft" data-coverage-missing>
          Missing from this font: {missing.map(formatCustomRange).join(", ")}
        </p>
      )}
    </div>
  );
}
