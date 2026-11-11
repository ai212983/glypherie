import * as React from "react";
import { Grid3x3, Smartphone, TabletSmartphone } from "lucide-react";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { TooltipHint } from "../../../components/TooltipHint";
import deviceIcon from "../../../components/ui/assets/glypherie/device.svg";
import deviceChevron from "../../../components/ui/assets/glypherie/device-chevron.svg";
import { DEVICE_CATALOG, type DeviceDefinition } from "../../devices/catalog.js";
import { DEVICE_ZOOM_PRESETS } from "./device-zoom.js";

function ToggleHint({
  content,
  disabled,
  children,
}: {
  content: string;
  disabled: boolean;
  children: React.ReactElement<React.ComponentProps<typeof Button>>;
}): React.JSX.Element {
  return (
    <TooltipHint content={content}>
      {disabled ? (
        <span
          role="group"
          tabIndex={0}
          aria-label={children.props["aria-label"]}
          aria-disabled="true"
          className="inline-flex rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          {children}
        </span>
      ) : (
        children
      )}
    </TooltipHint>
  );
}

export function DeviceHeader({
  device,
  width,
  height,
  rotation,
  disabled,
  onDevice,
  onRotate,
  zoomPercent,
  onZoom,
  showBody,
  bodyToggleDisabled,
  bodyToggleHint,
  onToggleBody,
  gridVisible,
  gridToggleDisabled,
  gridToggleHint,
  onToggleGrid,
}: {
  device: DeviceDefinition | null;
  width: number;
  height: number;
  rotation: number;
  disabled: boolean;
  onDevice: (id: string) => void;
  onRotate: () => void;
  zoomPercent: number;
  onZoom: (percent: number) => void;
  showBody: boolean;
  bodyToggleDisabled: boolean;
  bodyToggleHint: string;
  onToggleBody: () => void;
  gridVisible: boolean;
  gridToggleDisabled: boolean;
  gridToggleHint: string;
  onToggleGrid: () => void;
}): React.JSX.Element {
  const diagonal = device ? (Math.hypot(device.widthPx, device.heightPx) / device.ppi).toFixed(1) : null;
  return (
    <header
      data-screen-device-header
      className="screen-device-header flex min-h-8 shrink-0 items-center gap-1.5 overflow-hidden border-b border-studio-border px-3 font-studio"
    >
      <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto">
        <img src={deviceIcon} alt="" aria-hidden="true" className="shrink-0" />
        <Select value={device?.id ?? "custom"} disabled={disabled} onValueChange={onDevice}>
          <SelectTrigger
            id="workspace-device"
            aria-label="Device"
            data-screen-device
            icon={<img src={deviceChevron} alt="" aria-hidden="true" />}
            className="screen-device-option h-6 shrink-0 gap-4 rounded-sm px-2.5 py-1 text-xs shadow-none"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DEVICE_CATALOG.devices.map((entry) => (
              <SelectItem key={entry.id} value={entry.id} className="font-studio text-xs">
                {entry.label}
              </SelectItem>
            ))}
            <SelectItem value="custom" className="font-studio text-xs">
              {device ? "Custom…" : `Custom ${width} × ${height}`}
            </SelectItem>
          </SelectContent>
        </Select>
        <div data-screen-device-meta className="flex shrink-0 items-center gap-1">
          {diagonal && (
            <Badge
              variant="outline"
              className="screen-device-parameter rounded-sm px-1.5 py-0.5 text-[10px] font-normal"
            >
              {diagonal}″
            </Badge>
          )}
          <Badge
            variant="outline"
            data-screen-resolution
            className="screen-device-parameter rounded-sm px-1.5 py-0.5 text-[10px] font-normal"
          >
            {width} × {height} px
          </Badge>
          <TooltipHint content={`Rotate device clockwise · currently ${rotation}°`}>
            <Button
              type="button"
              variant="outline"
              size="icon-xs"
              className="screen-device-parameter rounded-sm shadow-none"
              data-screen-rotate
              aria-label={`Rotate device clockwise (current rotation: ${rotation}°)`}
              disabled={disabled}
              onClick={onRotate}
            >
              <Smartphone aria-hidden="true" style={{ transform: `rotate(${rotation}deg)` }} />
            </Button>
          </TooltipHint>
          {device && (
            <Badge
              variant="outline"
              className="screen-device-parameter rounded-sm px-1.5 py-0.5 text-[10px] font-normal"
            >
              {device.ppi} PPI
            </Badge>
          )}
        </div>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        <Select value={String(zoomPercent)} onValueChange={(value) => onZoom(Number(value))}>
          <TooltipHint content={`Zoom the device canvas · currently ${zoomPercent}%`}>
            <SelectTrigger
              id="workspace-device-zoom"
              aria-label="Zoom"
              data-screen-zoom
              className="screen-device-option h-6 shrink-0 gap-2 rounded-sm px-2 py-1 text-xs shadow-none"
            >
              <SelectValue />
            </SelectTrigger>
          </TooltipHint>
          <SelectContent>
            {DEVICE_ZOOM_PRESETS.map((preset) => (
              <SelectItem key={preset} value={String(preset)} className="font-studio text-xs">
                {preset}%
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <ToggleHint content={bodyToggleHint} disabled={bodyToggleDisabled}>
          <Button
            type="button"
            variant="outline"
            size="icon-xs"
            className="screen-device-parameter rounded-sm shadow-none"
            data-screen-body-toggle
            aria-label={showBody ? "Hide device body" : "Show device body"}
            aria-pressed={showBody}
            disabled={bodyToggleDisabled}
            onClick={onToggleBody}
          >
            <TabletSmartphone aria-hidden="true" />
          </Button>
        </ToggleHint>
        <ToggleHint content={gridToggleHint} disabled={gridToggleDisabled}>
          <Button
            type="button"
            variant="outline"
            size="icon-xs"
            className="screen-device-parameter rounded-sm shadow-none"
            data-screen-grid-toggle
            aria-label={gridVisible ? "Hide grid" : "Show grid"}
            aria-pressed={gridVisible}
            disabled={gridToggleDisabled}
            onClick={onToggleGrid}
          >
            <Grid3x3 aria-hidden="true" />
          </Button>
        </ToggleHint>
      </div>
    </header>
  );
}
