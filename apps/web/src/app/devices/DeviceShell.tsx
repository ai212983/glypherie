// Shared device shell composition: the vector shell artwork scales with the
// screen aperture (see deviceLayout), and the caller paints the screen
// content through the shell's transparent aperture. Both the font editor's
// device preview and the standalone Screen page render through this owner,
// so shell/shell geometry stays single-sourced.
import * as React from "react";
import { deviceLayout, shellUrl, type DeviceDefinition, type DeviceLayout } from "./catalog.js";

interface DeviceShellProps {
  device: DeviceDefinition;
  // CSS px per device pixel; shell and screen scale together from the aperture.
  cssScale: number;
  // Screen content positioned over the aperture from the provided layout.
  children: (layout: DeviceLayout) => React.ReactNode;
}

export function DeviceShell({ device, cssScale, children }: DeviceShellProps): React.JSX.Element {
  const layout = deviceLayout(device, cssScale);
  const shell = shellUrl(device);
  return (
    <div
      data-device-preview={device.id}
      data-native-width={device.widthPx}
      data-native-height={device.heightPx}
      className="relative overflow-auto"
      style={{ width: layout.svgWidth, height: layout.svgHeight, maxWidth: "100%" }}
    >
      {children(layout)}
      <img
        src={shell}
        alt=""
        aria-hidden="true"
        data-device-shell={device.id}
        draggable={false}
        className="pointer-events-none block"
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: layout.svgWidth,
          height: layout.svgHeight,
        }}
      />
    </div>
  );
}
