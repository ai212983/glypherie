// Shared device shell composition: the vector shell artwork scales with the
// screen aperture (see deviceLayout), and the caller paints the screen
// content through the shell's transparent aperture. Both the font editor's
// device preview and the standalone Screen page render through this owner,
// so shell/shell geometry stays single-sourced.
import * as React from "react";
import { deviceLayout, deviceShownLayout, shellUrl, type DeviceDefinition, type DeviceLayout } from "./catalog.js";

interface DeviceShellProps {
  device: DeviceDefinition;
  // CSS px per device pixel; shell and screen scale together from the aperture.
  cssScale: number;
  rotation?: number;
  // Presentation-only body visibility. Hidden drops the shell artwork and
  // sizes the same wrapper to the bare screen aperture, so callers swap body
  // visibility without remounting the painted content.
  bodyVisible?: boolean;
  // Screen content positioned over the aperture from the provided layout.
  children: (layout: DeviceLayout) => React.ReactNode;
}

export function DeviceShell({
  device,
  cssScale,
  rotation = 0,
  bodyVisible = true,
  children,
}: DeviceShellProps): React.JSX.Element {
  const native = deviceLayout(device, cssScale);
  const shown: DeviceLayout = deviceShownLayout(device, cssScale, rotation, bodyVisible);
  const sideways = rotation === 90 || rotation === 270;
  const translateX = rotation === 90 ? native.svgHeight : rotation === 180 ? native.svgWidth : 0;
  const translateY = rotation === 180 ? native.svgHeight : rotation === 270 ? native.svgWidth : 0;
  const shell = shellUrl(device);
  return (
    <div
      data-device-preview={device.id}
      data-device-body={bodyVisible ? "shown" : "hidden"}
      data-native-width={sideways ? device.heightPx : device.widthPx}
      data-native-height={sideways ? device.widthPx : device.heightPx}
      data-device-rotation={rotation}
      className="relative overflow-auto"
      style={{ width: shown.svgWidth, height: shown.svgHeight, maxWidth: "100%" }}
    >
      {children(shown)}
      {bodyVisible && (
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
            width: native.svgWidth,
            height: native.svgHeight,
            transformOrigin: "0 0",
            transform: `translate(${translateX}px, ${translateY}px) rotate(${rotation}deg)`,
          }}
        />
      )}
    </div>
  );
}
