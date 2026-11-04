// Standalone device viewer: a catalog device rendered through its vector
// shell with a neutral paper screen. Font-independent: no font library,
// renderer, or preview settings are needed. The device selection is local
// page state; the paper renders at the CSS reference density times a
// persisted preview-size percentage, and the collapsed disclosure reports
// the two detected monitor values with the size control and an approximate
// millimetre ruler.
import * as React from "react";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { Slider } from "../../../components/ui/slider";
import { TooltipHint } from "../../../components/TooltipHint";
import { deviceById, DEVICE_CATALOG } from "../../devices/catalog.js";
import { DeviceShell } from "../../devices/DeviceShell.js";
import { CSS_REFERENCE_PX_PER_IN, referenceSizeCssScale } from "../../renderer/display-scaling.js";
import { useLiveRatio } from "../../renderer/live-ratio.js";
import { resolveMonitorReading, type MonitorReading, type MonitorSnapshot } from "./monitor-info.js";
import {
  SCREEN_SIZE_DEFAULT,
  SCREEN_SIZE_MAX,
  SCREEN_SIZE_MIN,
  readScreenSizePercent,
  writeScreenSizePercent,
} from "./screen-size.js";

// Fixed neutral paper shown through the aperture; illustrative, not a device claim.
const SCREEN_PAPER = "#f5f2ea";

function readMonitorSnapshot(dpr: number): MonitorSnapshot {
  const screen = globalThis.window?.screen as { width?: unknown; height?: unknown } | undefined;
  return {
    screenWidth: screen?.width,
    screenHeight: screen?.height,
    devicePixelRatio: dpr,
  };
}

// Live DPR via the shared owner; resize covers monitor changes the browser
// exposes. Cleanup detaches the listener.
function useMonitorReading(): MonitorReading {
  const dpr = useLiveRatio();
  const [tick, bump] = React.useReducer((count: number) => count + 1, 0);
  React.useEffect(() => {
    const onChange = (): void => {
      bump();
    };
    window.addEventListener("resize", onChange);
    return () => {
      window.removeEventListener("resize", onChange);
    };
  }, []);
  return React.useMemo(() => resolveMonitorReading(readMonitorSnapshot(dpr)), [dpr, tick]);
}

const RULER_MM_TOTAL = 50;
const RULER_MM_STEP = 5;
const MM_PER_IN = 25.4;
const RULER_MAJOR_MM = [0, 10, 20, 30, 40, 50];

function SizeRuler({ size }: { size: number }): React.JSX.Element {
  const spanWidth = (RULER_MM_TOTAL / MM_PER_IN) * CSS_REFERENCE_PX_PER_IN * size / 100;
  return (
    <div className="mt-2 min-w-0" data-screen-ruler>
      <p className="m-0 text-[.8rem] text-soft">Ruler · 5 mm divisions</p>
      <div className="overflow-x-auto">
        <svg
          role="img"
          aria-label="Approximate 50 millimetre ruler with 5 millimetre divisions"
          width={spanWidth}
          height={spanWidth * 12 / RULER_MM_TOTAL}
          viewBox="0 0 50 12"
          className="block shrink-0"
        >
          <line x1={0} y1={1} x2={RULER_MM_TOTAL} y2={1} stroke="currentColor" strokeWidth={0.2} />
          {Array.from({ length: RULER_MM_TOTAL / RULER_MM_STEP + 1 }, (_, index) => {
            const mm = index * RULER_MM_STEP;
            const major = mm % 10 === 0;
            return (
              <line
                key={mm}
                data-screen-ruler-tick={mm}
                x1={mm}
                y1={1}
                x2={mm}
                y2={major ? 5 : 3.5}
                stroke="currentColor"
                strokeWidth={0.2}
              />
            );
          })}
          {RULER_MAJOR_MM.map((mm) => (
            <text
              key={mm}
              x={mm}
              y={9.5}
              textAnchor={mm === 0 ? "start" : mm === RULER_MM_TOTAL ? "end" : "middle"}
              fontSize={3}
              fill="currentColor"
            >
              {mm}
            </text>
          ))}
        </svg>
      </div>
      <p className="m-0 mt-1 text-[.8rem] text-soft">Adjust until the marks match a physical ruler.</p>
    </div>
  );
}

function DisplayDetails({ size, onSize }: { size: number; onSize: (value: number) => void }): React.JSX.Element {
  const reading = useMonitorReading();
  return (
    <details data-monitor-info className="min-w-0">
      <summary className="cursor-pointer text-[.8rem] font-semibold">Display details</summary>
      {reading.screen ? (
        <p data-monitor-screen className="m-0 mt-1 text-[.8rem] text-soft">
          Screen: {reading.screen.width} × {reading.screen.height} CSS px
        </p>
      ) : null}
      <p data-monitor-dpr className="m-0 mt-1 text-[.8rem] text-soft">
        Device pixel ratio: {reading.dpr}
      </p>
      <div className="mt-2 flex min-w-0 max-w-72 flex-col gap-1" data-screen-size>
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="screen-preview-size" className="text-[.8rem] font-semibold">Preview size</Label>
          <span data-screen-size-value className="text-[.8rem] text-soft tabular-nums">{size}%</span>
        </div>
        <Slider
          id="screen-preview-size"
          aria-label="Preview size"
          aria-valuetext={`${size} percent`}
          min={SCREEN_SIZE_MIN}
          max={SCREEN_SIZE_MAX}
          step={1}
          value={[size]}
          className="h-6"
          onValueChange={([next]) => {
            if (next !== undefined) onSize(Math.round(next));
          }}
        />
        <button
          type="button"
          data-screen-size-reset
          className="cursor-pointer self-start bg-transparent p-0 text-[.8rem] text-soft underline"
          onClick={() => onSize(SCREEN_SIZE_DEFAULT)}
        >
          Reset to 100%
        </button>
        <SizeRuler size={size} />
      </div>
    </details>
  );
}

export function ScreenPage(): React.JSX.Element {
  // The viewer always shows a real catalog device, never the null specimen.
  const [deviceId, setDeviceId] = React.useState<string>(
    () => DEVICE_CATALOG.devices[0]?.id ?? "",
  );
  const device = deviceById(DEVICE_CATALOG, deviceId) ?? DEVICE_CATALOG.devices[0];
  const [sizePercent, setSizePercent] = React.useState(readScreenSizePercent);
  if (!device) return <p role="status">No devices are available.</p>;
  const cssScale = referenceSizeCssScale(device.ppi) * sizePercent / 100;
  const handleSize = (next: number): void => {
    setSizePercent(next);
    writeScreenSizePercent(next);
  };
  const inches = device.widthPx / device.ppi;
  return (
    <div className="flex min-w-0 flex-col gap-4" data-screen-page>
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="screen-device-select">Device</Label>
        <Select value={device.id} onValueChange={setDeviceId}>
          <SelectTrigger id="screen-device-select" data-screen-device className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DEVICE_CATALOG.devices.map((entry) => (
              <SelectItem key={entry.id} value={entry.id}>{entry.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <p data-screen-device-meta className="m-0 text-[.8rem] text-soft">
        {device.widthPx} × {device.heightPx} px · {device.ppi} PPI · {inches.toFixed(2)} in wide
      </p>
      <p data-screen-approximate className="m-0 text-[.8rem] text-soft">
        <TooltipHint content="The browser reports CSS screen size and pixel ratio, not physical monitor dimensions, so true size stays approximate.">
          <span>Preview size is approximate.</span>
        </TooltipHint>
      </p>
      <DisplayDetails size={sizePercent} onSize={handleSize} />
      <div className="overflow-x-auto py-2">
        <DeviceShell key={device.id} device={device} cssScale={cssScale}>
          {(layout) => (
            <div
              data-screen-paper
              role="img"
              aria-label={`${device.label} blank paper screen`}
              style={{
                position: "absolute",
                left: layout.screenX,
                top: layout.screenY,
                width: layout.screenWidth,
                height: layout.screenHeight,
                backgroundColor: SCREEN_PAPER,
              }}
            />
          )}
        </DeviceShell>
      </div>
    </div>
  );
}
