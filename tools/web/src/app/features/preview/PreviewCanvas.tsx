import * as React from "react";
import type { OutputProfile, RendererRole, StemFitting } from "../../renderer/renderer-types.js";
import { FontCanvas } from "../../renderer/FontCanvas.js";

export interface PreviewInputs {
  text: string;
  sizePx: number;
  axes: Record<string, number>;
  profile: OutputProfile;
  role: RendererRole;
  spacing: number;
  kerning: boolean;
  stemFitting: StemFitting;
}

interface PreviewCanvasProps extends PreviewInputs {
  fontId: string;
  zoom: number;
  pixelAccurate: boolean;
  onStatus: (message: string) => void;
}

// Interactive specimen: configurable render over the shared FontCanvas with
// the editor's 150 ms text debounce, exact/normal display modes, layout and
// status wording. Mounted only once the font is ready; readiness itself is
// owned by the caller.
export function PreviewCanvas(props: PreviewCanvasProps): React.JSX.Element {
  const { fontId, text, sizePx, axes, profile, role, spacing, kerning, stemFitting, zoom, pixelAccurate, onStatus } = props;
  return (
    <FontCanvas
      fontId={fontId}
      text={text}
      sizePx={sizePx}
      axes={axes}
      profile={profile}
      role={role}
      spacing={spacing}
      kerning={kerning}
      stemFitting={stemFitting}
      zoom={zoom}
      mode={pixelAccurate ? "exact" : "normal"}
      ready
      debounceMs={150}
      viewportProps={{
        className: "interactive-viewport block overflow-hidden",
        style: { width: "calc(100% - 2rem)", height: "auto", margin: "0 1rem 1rem" },
        tabIndex: 0,
        role: "region",
        "aria-label": "Interactive specimen",
      }}
      canvasProps={{ className: "interactive-canvas block [image-rendering:pixelated]" }}
      canvasFallback="Interactive preview needs JavaScript and the font renderer."
      onPaint={(diagnostics) => {
        onStatus(diagnostics.truncated ? "Text too long to preview fully." : "");
      }}
      onError={(message, info) => {
        if (/candidate/i.test(message)) onStatus("Candidate preview is unavailable in this build.");
        else if (info.renderer !== "baseline") onStatus(`Interactive ${info.renderer} preview failed.`);
        else onStatus("Interactive render failed.");
      }}
    />
  );
}
