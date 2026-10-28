import * as React from "react";
import type { OutputProfile, StemFitting } from "../../../renderer/renderer-types.js";
import { TooltipHint } from "../../../../components/TooltipHint";
import { Label } from "../../../../components/ui/label";
import { Switch } from "../../../../components/ui/switch";

interface FittingControlsProps {
  profile: OutputProfile;
  stemFitting: StemFitting;
  diagonalFitting: boolean;
  disabled: boolean;
  hasFontHints: boolean;
  onStemFitting: (value: StemFitting) => void;
  onDiagonalFitting: (value: boolean) => void;
}

export function FittingControls({ profile, stemFitting, diagonalFitting, disabled, hasFontHints, onStemFitting, onDiagonalFitting }: FittingControlsProps): React.JSX.Element {
  return (
    <div className="relative grid gap-3 text-[.875rem]" id="stem-fitting-control">
      {profile === "mono_1bit" && hasFontHints && (
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="use-font-hints">Use font hints</Label>
          <TooltipHint content="Uses font hints where available and automatically fits the remaining axes.">
            <Switch id="use-font-hints" disabled={disabled} checked={stemFitting !== "upstream_mono"}
              onCheckedChange={(checked) => onStemFitting(checked ? "font_hints_first" : "upstream_mono")} />
          </TooltipHint>
        </div>
      )}
      {profile === "mono_1bit" && (
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="fit-diagonal-strokes">Fit diagonal strokes</Label>
          <TooltipHint content="Balances stroke widths, crossing placement, and flat terminal alignment.">
            <Switch id="fit-diagonal-strokes" disabled={disabled} checked={diagonalFitting}
              onCheckedChange={onDiagonalFitting} />
          </TooltipHint>
        </div>
      )}
    </div>
  );
}
