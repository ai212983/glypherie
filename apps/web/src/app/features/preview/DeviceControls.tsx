// cspell:words TEMPERA
import * as React from "react";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "../../../components/ui/toggle-group";
import { TooltipHint } from "../../../components/TooltipHint";
import { DEVICE_CATALOG, deviceById } from "../../devices/catalog.js";
import { CSS_REFERENCE_PX_PER_IN } from "../../renderer/display-scaling.js";
import { type DeviceScaleMode } from "../../shell/display-preferences.js";

interface DeviceControlsProps {
  deviceId: string | null;
  unknownDevice: string | null;
  scale: DeviceScaleMode;
  onDevice: (id: string | null) => void;
  onScale: (scale: DeviceScaleMode) => void;
}

// Physical screen width in inches, from native pixels over the catalog PPI.
export function physicalWidthIn(deviceId: string | null): number | null {
  const device = deviceById(DEVICE_CATALOG, deviceId);
  if (!device) return null;
  return device.widthPx / device.ppi;
}

export function DeviceControls({
  deviceId,
  unknownDevice,
  scale,
  onDevice,
  onScale,
}: DeviceControlsProps): React.JSX.Element {
  const device = deviceById(DEVICE_CATALOG, deviceId);
  const inches = device ? device.widthPx / device.ppi : null;
  return (
    <div className="flex min-w-0 flex-col gap-3" data-device-controls>
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="device-select">Device</Label>
        <TooltipHint content="Fixed native framebuffer preview. Font settings, URLs and saved variants are unchanged.">
          <Select
            value={device ? device.id : "specimen"}
            onValueChange={(next) => onDevice(next === "specimen" ? null : next)}
          >
            <SelectTrigger id="device-select" data-device-select className="w-52">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="specimen">Responsive specimen</SelectItem>
              {DEVICE_CATALOG.devices.map((entry) => (
                <SelectItem key={entry.id} value={entry.id}>
                  {entry.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </TooltipHint>
      </div>
      {unknownDevice && (
        <p role="alert" data-unknown-device className="m-0 text-[.8rem] text-soft">
          Unknown device “{unknownDevice}” — showing the responsive specimen.
        </p>
      )}
      {device && (
        <>
          <p data-device-meta className="m-0 text-[.8rem] text-soft">
            {device.widthPx} × {device.heightPx} px · {device.ppi} PPI
            {inches !== null && ` · ${inches.toFixed(2)} in wide`}
          </p>
          <div className="flex items-center justify-between gap-3">
            <Label id="device-scale-label">Size</Label>
            <TooltipHint
              content={`Reference size renders at the ${CSS_REFERENCE_PX_PER_IN} CSS px/in reference (unmeasured monitor); Pixel 1:1 maps one device pixel to one monitor pixel.`}
            >
              <ToggleGroup
                type="single"
                aria-labelledby="device-scale-label"
                data-device-scale
                value={scale}
                onValueChange={(next) => {
                  if (next === "actual" || next === "one-to-one") onScale(next);
                }}
              >
                <ToggleGroupItem value="actual" aria-label="Actual size">
                  Actual
                </ToggleGroupItem>
                <ToggleGroupItem value="one-to-one" aria-label="Pixel 1:1">
                  1:1
                </ToggleGroupItem>
              </ToggleGroup>
            </TooltipHint>
          </div>
        </>
      )}
    </div>
  );
}
