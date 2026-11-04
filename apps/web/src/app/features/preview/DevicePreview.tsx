// cspell:words TEMPERA
import * as React from "react";
import type { KerningPreference } from "../../kerning/model.js";
import type { MonoRaster, OutputProfile, Rasterization, RendererRole, RGBA, StemFitting } from "../../renderer/renderer-types.js";
import { FontCanvas } from "../../renderer/FontCanvas.js";
import { oneToOneCssScale, referenceSizeCssScale } from "../../renderer/display-scaling.js";
import { useLiveRatio } from "../../renderer/live-ratio.js";
import { deviceById, DEVICE_CATALOG, type DeviceDefinition } from "../../devices/catalog.js";
import { DeviceShell } from "../../devices/DeviceShell.js";
import type { DeviceScaleMode } from "../../shell/display-preferences.js";

export interface DevicePreviewInputs {
  text: string;
  sizePx: number;
  axes: Record<string, number>;
  profile: OutputProfile;
  role: RendererRole;
  spacing: number;
  kerning: KerningPreference;
  stemFitting: StemFitting;
  diagonalFitting: boolean;
  monoRaster: MonoRaster;
  rasterization?: Rasterization;
}

interface DevicePreviewProps extends DevicePreviewInputs {
  fontId: string;
  zoom: number;
  palette?: readonly RGBA[];
  deviceId: string | null;
  scale: DeviceScaleMode;
  onStatus: (message: string) => void;
}

// Physical pixel grid tracking lives in the shared live-ratio owner so DPR
// transitions re-arm the resolution query (see live-ratio.ts).

// Fixed-framebuffer device preview: the render targets the catalog's native
// width and height exactly, the shell artwork scales with the screen aperture,
// and the screen shows through the shell's transparent aperture. Reference
// size uses the unmeasured CSS reference density; only Pixel 1:1 is exact.
export function DevicePreview(props: DevicePreviewProps): React.JSX.Element | null {
  const { deviceId, scale } = props;
  const device: DeviceDefinition | null = deviceById(DEVICE_CATALOG, deviceId);
  const ratio = useLiveRatio();
  const nativeSize = React.useMemo(
    () => (device ? { width: device.widthPx, height: device.heightPx } : null),
    [device],
  );
  const cssScale = device
    ? scale === "one-to-one"
      ? oneToOneCssScale(ratio)
      : referenceSizeCssScale(device.ppi)
    : 1;
  if (!device || !nativeSize) return null;
  return (
    <DeviceShell device={device} cssScale={cssScale}>
      {(layout) => (
        <FontCanvas
          fontId={props.fontId}
          text={props.text}
          sizePx={props.sizePx}
          axes={props.axes}
          profile={props.profile}
          role={props.role}
          spacing={props.spacing}
          kerning={props.kerning}
          stemFitting={props.stemFitting}
          diagonalFitting={props.diagonalFitting}
          monoRaster={props.monoRaster}
          rasterization={props.rasterization}
          zoom={props.zoom}
          mode="exact"
          nativeSize={nativeSize}
          cssScale={cssScale}
          compact
          ready
          clearOnError
          debounceMs={150}
          palette={props.palette}
          viewportProps={{
            className: "block overflow-hidden",
            style: {
              position: "absolute",
              left: layout.screenX,
              top: layout.screenY,
              width: layout.screenWidth,
              height: layout.screenHeight,
            },
            tabIndex: 0,
            role: "region",
            "aria-label": `${device.label} screen preview`,
          }}
          canvasProps={{ className: "block [image-rendering:pixelated]" }}
          canvasFallback="Preview unavailable."
          onPaint={(diagnostics) => {
            props.onStatus(diagnostics.truncated ? "Preview truncated." : "");
          }}
          onError={(message, info) => {
            console.warn("Device preview failed", info.renderer, message);
            props.onStatus(message.includes("requires the current preview pipeline") ? message : "Couldn’t render preview.");
          }}
        />
      )}
    </DeviceShell>
  );
}
