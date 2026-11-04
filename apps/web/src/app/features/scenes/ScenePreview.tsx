// Scene preview: placed labels rendered through the real FontCanvas at
// their scene positions, never browser text masquerading as bitmaps. Each
// label paints on its own transparent canvas stacked over paper, so an
// opaque background can never hide another label's ink.
import * as React from "react";
import { linearCurve, type GrayCurve } from "../grayscale/response-curve";
import { useDisplayPreferences } from "../../shell/DisplayPreferences";
import { FontCanvas } from "../../renderer/FontCanvas";
import { profileBits } from "../../renderer/render-spec";
import type { VariantSettings } from "../../variants/model";
import type { DomainPlacementView } from "./service";
import { sceneLabelPalette, scenePaperCss } from "./scene-palette";

export interface SceneLabelPaint {
  placement: DomainPlacementView;
  fontId: string;
  settings: VariantSettings;
  ready: boolean;
}

export function ScenePreview({ width, height, labels, curve, onRenderError }: {
  width: number;
  height: number;
  labels: SceneLabelPaint[];
  curve: GrayCurve | undefined;
  onRenderError?: (message: string) => void;
}): React.JSX.Element {
  const { zoom, canvas: { palette: appearance, inverse } } = useDisplayPreferences();
  const ordered = React.useMemo(
    () => [...labels].sort((left, right) => left.placement.order - right.placement.order),
    [labels],
  );
  const paper = scenePaperCss(appearance, inverse);
  return (
    <div
      data-scene-preview
      role="img"
      aria-label={`Scene preview, ${width} by ${height} pixels`}
      style={{ position: "relative", width: width * zoom, height: height * zoom, overflow: "auto" }}
    >
      <div style={{ position: "relative", width, height, transform: `scale(${zoom})`, transformOrigin: "top left", backgroundColor: paper }}>
        {ordered.map(({ placement, fontId, settings, ready }) => {
          const labelWidth = Math.max(1, width - placement.x);
          const labelHeight = Math.max(1, height - placement.y);
          // The scene curve drives every label; a length mismatch against a
          // label profile falls back to a linear ramp of the right length so
          // the native palette contract (exactly 2^bits entries) still holds.
          const effective = curve?.length === 1 << profileBits(settings.profile)
            ? curve
            : linearCurve(1 << profileBits(settings.profile));
          return (
            <div key={placement.id} style={{ position: "absolute", left: placement.x, top: placement.y, width: labelWidth, height: labelHeight, overflow: "hidden" }}>
              <FontCanvas
                fontId={fontId}
                text={placement.text}
                sizePx={settings.sizePx}
                axes={settings.axes}
                profile={settings.profile}
                role="candidate"
                spacing={settings.letterSpacingPx}
                kerning={settings.kerning}
                stemFitting={settings.stemFitting}
                diagonalFitting={settings.diagonalFitting}
                monoRaster={settings.monoRaster}
                rasterization={settings.rasterization}
                zoom={1}
                mode="exact"
                ready={ready}
                clearOnError
                debounceMs={0}
                palette={sceneLabelPalette(effective, appearance, inverse)}
                viewportProps={{
                  "data-scene-label": placement.id,
                  role: "img",
                  "aria-label": placement.text,
                }}
                canvasProps={{ className: "block [image-rendering:pixelated]" }}
                canvasFallback="Label preview unavailable."
                onError={(message) => onRenderError?.(`Label "${placement.text}": ${message}`)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
