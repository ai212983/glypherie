// Unified Screen page: one implicit default composition on a selected
// device with freely positioned labels. There is no composition list, create
// UI or selection state: every Screen route (including the legacy /scenes/,
// /scene/<id>/ and ?scene= links) opens the same durable default and the URL
// normalizes to /screen/ without scene selection. Display calibration
// (preview size, ruler, monitor reading) stays page-level and never writes
// the editor's device state.
import * as React from "react";
import "./ScreenPage.css";
import { Label } from "../../../components/ui/label";
import { Slider } from "../../../components/ui/slider";
import { DEVICE_CATALOG } from "../../devices/catalog.js";
import type { FontLibrary } from "../../fonts/useFontLibrary.js";
import { readRouteSearch } from "../../navigation/location.js";
import { screenPath } from "../../navigation/router.js";
import { useLiveRatio } from "../../renderer/live-ratio.js";
import { CSS_REFERENCE_PX_PER_IN } from "../../renderer/display-scaling.js";
import { resolveMonitorReading, type MonitorReading, type MonitorSnapshot } from "./monitor-info.js";
import {
  SCREEN_SIZE_DEFAULT,
  SCREEN_SIZE_MAX,
  SCREEN_SIZE_MIN,
  readScreenSizePercent,
  writeScreenSizePercent,
} from "./screen-size.js";
import { SceneWorkspace } from "./SceneWorkspace.js";
import { defaultNewSceneDevice } from "./device-resolution.js";
import { userError } from "../../user-error";
import { ensureDefaultScene, getScene, listOutputProfiles, subscribeDomain } from "../scenes/service.js";

// Drop scene selection from the URL without adding history entries, so
// Back/Forward can never reveal another composition. Foreign params and the
// hosting prefix ride along through screenPath; hash routes are left for the
// app-level canonicalization that already owns them.
function normalizeScreenUrl(): void {
  if (window.location.hash.startsWith("#/")) return;
  const path = window.location.pathname;
  const legacyPath = /^\/scenes?\/?$/.test(path) || /^\/scene\/[^/]+\/?$/.test(path);
  const params = new URLSearchParams(readRouteSearch());
  const dropScene = params.has("scene");
  params.delete("scene");
  if (!dropScene && !legacyPath) return;
  window.history.replaceState(null, "", screenPath(params));
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
  const spanWidth = ((RULER_MM_TOTAL / MM_PER_IN) * CSS_REFERENCE_PX_PER_IN * size) / 100;
  return (
    <div className="mt-2 min-w-0" data-screen-ruler>
      <p className="m-0 text-[.8rem] text-soft">Ruler · 5 mm divisions</p>
      <div className="overflow-x-auto">
        <svg
          role="img"
          aria-label="Approximate 50 millimetre ruler with 5 millimetre divisions"
          width={spanWidth}
          height={(spanWidth * 12) / RULER_MM_TOTAL}
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
          <Label htmlFor="screen-preview-size" className="text-[.8rem] font-semibold">
            Preview size
          </Label>
          <span data-screen-size-value className="text-[.8rem] text-soft tabular-nums">
            {size}%
          </span>
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

export function ScreenPage({ library }: { library: FontLibrary }): React.JSX.Element {
  const [sceneId, setSceneId] = React.useState<string | null>(null);
  const [ensureError, setEnsureError] = React.useState("");
  const [sizePercent, setSizePercent] = React.useState(readScreenSizePercent);
  // Reload generation: a slow rejection must never clear a newer success.
  const seqRef = React.useRef(0);
  const sceneIdRef = React.useRef<string | null>(null);

  const ensure = React.useCallback(async () => {
    const request = (seqRef.current += 1);
    setEnsureError("");
    try {
      const profiles = await listOutputProfiles();
      const outputProfileId = profiles[0]?.id;
      if (!outputProfileId) throw new Error("No output profile is available for the composition.");
      const device = defaultNewSceneDevice(DEVICE_CATALOG.devices);
      if (!device) throw new Error("No device is available for the composition.");
      const ensured = await ensureDefaultScene({
        name: "Default",
        width: device.widthPx,
        height: device.heightPx,
        deviceId: device.id,
        outputProfileId,
      });
      if (seqRef.current !== request) return;
      sceneIdRef.current = ensured.id;
      setSceneId(ensured.id);
      normalizeScreenUrl();
    } catch (failure) {
      if (seqRef.current !== request) return;
      // Raw startup failures carry schema SQL, JSON paths and migration
      // instructions; the shared formatter keeps those in the console and
      // shows an actionable message instead.
      setEnsureError(userError(failure, "Couldn’t open the default composition."));
    }
  }, []);

  const ensureRef = React.useRef(ensure);
  ensureRef.current = ensure;

  React.useEffect(() => {
    // Normalize up front so Back/Forward onto a ?scene= or legacy URL cleans
    // immediately, even while the first ensure is still in flight.
    normalizeScreenUrl();
    void ensureRef.current();
    const stop = subscribeDomain(() => {
      // Revalidate after remote commits only once a default is held. A
      // confirmed deletion (not a transient read failure) drops the held id
      // so the page re-resolves instead of stranding the workspace. Never
      // start an ensure from the pre-resolution state — every ensure
      // announces, so spawning one per announcement while the id is still
      // null would invalidate the in-flight resolution forever and strand
      // the page on its loading state.
      const current = sceneIdRef.current;
      if (!current) return;
      void (async () => {
        let kept: Awaited<ReturnType<typeof getScene>>;
        try {
          kept = await getScene(current);
        } catch {
          return;
        }
        if (kept !== undefined) return;
        sceneIdRef.current = null;
        setSceneId(null);
        await ensureRef.current();
      })();
    });
    // Back/Forward across compositions cannot resurface selection: any
    // scene-carrying URL normalizes back to the default without history churn.
    const onRouteChange = (): void => {
      normalizeScreenUrl();
    };
    window.addEventListener("popstate", onRouteChange);
    window.addEventListener("hashchange", onRouteChange);
    return () => {
      seqRef.current += 1;
      stop();
      window.removeEventListener("popstate", onRouteChange);
      window.removeEventListener("hashchange", onRouteChange);
    };
  }, []);

  const retryEnsure = React.useCallback(() => {
    void ensureRef.current();
  }, []);

  const handleSize = (next: number): void => {
    setSizePercent(next);
    writeScreenSizePercent(next);
  };

  // Page-level calibration stays state-owned here but renders inside the
  // workspace right column, so every non-stage control shares one region.
  const pageControls = <DisplayDetails size={sizePercent} onSize={handleSize} />;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-4" data-screen-page>
      <div className="min-h-0 min-w-0 flex-1">
        {sceneId ? (
          <SceneWorkspace
            key={sceneId}
            sceneId={sceneId}
            library={library}
            sizePercent={sizePercent}
            pageControls={pageControls}
          />
        ) : ensureError ? (
          <div className="flex min-w-0 flex-col items-start gap-2">
            <p role="alert" className="m-0 text-xs" data-screen-default-error>
              {ensureError}
            </p>
            <button
              type="button"
              data-screen-default-retry
              className="cursor-pointer self-start bg-transparent p-0 text-[.8rem] text-soft underline"
              onClick={retryEnsure}
            >
              Retry
            </button>
          </div>
        ) : (
          <p role="status" className="m-0 text-xs" data-screen-default-loading>
            Opening the default composition…
          </p>
        )}
      </div>
    </div>
  );
}
