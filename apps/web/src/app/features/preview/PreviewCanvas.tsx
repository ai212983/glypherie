import * as React from "react";
import type { MonoRaster, OutputProfile, Rasterization, RendererRole, RGBA, StemFitting } from "../../renderer/renderer-types.js";
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
  diagonalFitting: boolean;
  monoRaster: MonoRaster;
  rasterization?: Rasterization;
}

interface PreviewCanvasProps extends PreviewInputs {
  fontId: string;
  zoom: number;
  palette?: readonly RGBA[];
  framed?: boolean;
  onStatus: (message: string) => void;
}

// Interactive specimen: configurable render over the shared FontCanvas with
// the editor's 150 ms text debounce, exact/normal display modes, layout and
// status wording. Mounted only once the font is ready; readiness itself is
// owned by the caller.
export function PreviewCanvas(props: PreviewCanvasProps): React.JSX.Element {
  const { fontId, text, sizePx, axes, profile, role, spacing, kerning, stemFitting, diagonalFitting, monoRaster, rasterization, zoom, palette, framed, onStatus } = props;
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
      diagonalFitting={diagonalFitting}
      monoRaster={monoRaster}
      rasterization={rasterization}
      zoom={zoom}
      mode="exact"
      ready
      debounceMs={150}
      palette={palette}
      viewportProps={framed ? {
        className: "interactive-viewport block min-w-0 overflow-hidden",
        tabIndex: 0,
        role: "region",
        "aria-label": "Interactive specimen",
      } : {
        className: "interactive-viewport block overflow-hidden",
        style: { width: "calc(100% - 2rem)", height: "auto", margin: "0 1rem 1rem" },
        tabIndex: 0,
        role: "region",
        "aria-label": "Interactive specimen",
      }}
      canvasProps={{ className: "interactive-canvas block [image-rendering:pixelated]" }}
      canvasFallback="Preview unavailable."
      onPaint={(diagnostics) => {
        onStatus(diagnostics.truncated ? "Preview truncated." : "");
      }}
      onError={(message, info) => {
        console.warn("Preview failed", info.renderer, message);
        onStatus("Couldn’t render preview.");
      }}
    />
  );
}
