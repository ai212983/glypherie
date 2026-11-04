// Unified Screen page: saved compositions (formerly scenes) on a selected
// device with freely positioned labels. The legacy /scenes/ and
// /scene/<id>/ links render this same page; the canonical route is /screen/
// with the open composition in ?scene=. Display calibration (preview size,
// ruler, monitor reading) stays page-level and never writes the editor's
// device state.
import * as React from "react";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { Slider } from "../../../components/ui/slider";
import { TooltipHint } from "../../../components/TooltipHint";
import { deviceById, DEVICE_CATALOG } from "../../devices/catalog.js";
import { DeviceShell } from "../../devices/DeviceShell.js";
import type { FontLibrary } from "../../fonts/useFontLibrary.js";
import { readRouteSearch } from "../../navigation/location.js";
import { screenPath } from "../../navigation/router.js";
import { useLiveRatio } from "../../renderer/live-ratio.js";
import { CSS_REFERENCE_PX_PER_IN, referenceSizeCssScale } from "../../renderer/display-scaling.js";
import { resolveMonitorReading, type MonitorReading, type MonitorSnapshot } from "./monitor-info.js";
import {
  SCREEN_SIZE_DEFAULT,
  SCREEN_SIZE_MAX,
  SCREEN_SIZE_MIN,
  readScreenSizePercent,
  writeScreenSizePercent,
} from "./screen-size.js";
import { CompositionList } from "./CompositionList.js";
import { SceneWorkspace } from "./SceneWorkspace.js";
import { defaultNewSceneDevice } from "./device-resolution.js";
import {
  createScene,
  deleteScene,
  listOutputProfiles,
  listScenes,
  subscribeDomain,
  type DomainSceneView,
} from "../scenes/service.js";
import { isConflict } from "../scenes/conflict.js";

function sceneQuery(): string | null {
  try {
    const search = readRouteSearch() || window.location.search;
    return new URLSearchParams(search).get("scene");
  } catch {
    return null;
  }
}

function writeSceneQuery(scene: string | null): void {
  const search = readRouteSearch() || window.location.search;
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  if (scene) params.set("scene", scene);
  else params.delete("scene");
  const query = params.toString();
  const base = screenPath("");
  const path = query ? `${base}?${query}` : base;
  window.history.pushState(null, "", path);
}

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

// Fixed neutral paper shown through the aperture; illustrative, not a device claim.
const SCREEN_PAPER = "#f5f2ea";

// Standalone catalog viewer for the empty-selection state: a real catalog
// device through its vector shell with a neutral paper screen. Local page
// state only; the paper renders at the CSS reference density times the
// persisted preview-size percentage.
function DeviceViewer({ sizePercent }: { sizePercent: number }): React.JSX.Element {
  const [deviceId, setDeviceId] = React.useState<string>(
    () => DEVICE_CATALOG.devices[0]?.id ?? "",
  );
  const device = deviceById(DEVICE_CATALOG, deviceId) ?? DEVICE_CATALOG.devices[0];
  if (!device) return <p role="status">No devices are available.</p>;
  const cssScale = referenceSizeCssScale(device.ppi) * sizePercent / 100;
  const inches = device.widthPx / device.ppi;
  return (
    <>
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
    </>
  );
}

export function ScreenPage({ library, legacySceneId }: {
  library: FontLibrary;
  legacySceneId?: string | null;
}): React.JSX.Element {
  const [scenes, setScenes] = React.useState<DomainSceneView[] | null>(null);
  const [profileId, setProfileId] = React.useState<string | null>(null);
  const [activeId, setActiveId] = React.useState<string | null>(() => legacySceneId ?? sceneQuery());
  const [creating, setCreating] = React.useState(false);
  const [listError, setListError] = React.useState("");
  const [sizePercent, setSizePercent] = React.useState(readScreenSizePercent);

  const reload = React.useCallback(async () => {
    try {
      const [nextScenes, nextProfiles] = await Promise.all([listScenes(), listOutputProfiles()]);
      setScenes(nextScenes);
      setProfileId((current) => current ?? nextProfiles[0]?.id ?? null);
      setListError("");
    } catch (failure) {
      setListError(failure instanceof Error ? failure.message : "Couldn’t load compositions.");
    }
  }, []);

  React.useEffect(() => {
    void reload();
    return subscribeDomain(() => { void reload(); });
  }, [reload]);

  // Back/Forward across compositions stays on the Screen page (only the
  // ?scene= query changes), so the open composition follows the URL through
  // popstate/hashchange events instead of only following the deep-link prop.
  React.useEffect(() => {
    const syncFromRoute = (): void => {
      setActiveId(legacySceneId ?? sceneQuery());
    };
    syncFromRoute();
    window.addEventListener("popstate", syncFromRoute);
    window.addEventListener("hashchange", syncFromRoute);
    return () => {
      window.removeEventListener("popstate", syncFromRoute);
      window.removeEventListener("hashchange", syncFromRoute);
    };
  }, [legacySceneId]);

  const select = React.useCallback((id: string | null) => {
    setActiveId(id);
    writeSceneQuery(id);
  }, []);

  const create = React.useCallback(async (input: { name: string }): Promise<void> => {
    if (creating) return;
    setCreating(true);
    try {
      const profiles = await listOutputProfiles();
      const outputProfileId = profiles[0]?.id;
      if (!outputProfileId) throw new Error("No output profile is available for the composition.");
      const device = defaultNewSceneDevice(DEVICE_CATALOG.devices);
      if (!device) throw new Error("No device is available for the composition.");
      const created = await createScene({
        name: input.name,
        width: device.widthPx,
        height: device.heightPx,
        deviceId: device.id,
        outputProfileId,
      });
      await reload();
      select(created.id);
    } finally {
      setCreating(false);
    }
  }, [creating, reload, select]);

  const remove = React.useCallback(async (scene: DomainSceneView): Promise<void> => {
    try {
      await deleteScene(scene.id, scene.revision);
      setActiveId((current) => {
        const next = current === scene.id ? null : current;
        if (next !== current) writeSceneQuery(next);
        return next;
      });
      await reload();
    } catch (failure) {
      if (isConflict(failure)) {
        await reload();
        throw new Error("The composition changed in another tab; it was reloaded.");
      }
      throw failure;
    }
  }, [reload]);

  const handleSize = (next: number): void => {
    setSizePercent(next);
    writeScreenSizePercent(next);
  };

  return (
    <div className="flex min-w-0 flex-col gap-4" data-screen-page>
      <p data-screen-approximate className="m-0 text-[.8rem] text-soft">
        <TooltipHint content="The browser reports CSS screen size and pixel ratio, not physical monitor dimensions, so true size stays approximate.">
          <span>Preview size is approximate.</span>
        </TooltipHint>
      </p>
      <DisplayDetails size={sizePercent} onSize={handleSize} />
      {listError && <p role="alert" className="m-0 text-xs" data-screen-list-error>{listError}</p>}
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(16rem,20rem)_minmax(0,1fr)]">
        <CompositionList
          scenes={scenes}
          activeId={activeId}
          profilesLoaded={profileId !== null}
          creating={creating}
          onSelect={select}
          onCreate={create}
          onDelete={remove}
        />
        <div className="min-w-0">
          {activeId ? (
            <SceneWorkspace key={activeId} sceneId={activeId} library={library} sizePercent={sizePercent} onBack={() => select(null)} />
          ) : (
            <>
              <DeviceViewer sizePercent={sizePercent} />
              <p className="m-0 mt-2 text-xs text-soft" data-screen-no-selection>Select a composition to place labels on its screen.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
