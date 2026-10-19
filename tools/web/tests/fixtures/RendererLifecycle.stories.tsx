import type { Meta, StoryObj } from "@storybook/react-vite";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { RendererProvider, useRenderer } from "../../src/app/renderer/renderer-context.js";
import { FontCanvas } from "../../src/app/renderer/FontCanvas.js";
import {
  createFixtureRenderer,
  type FixtureRendererEvents,
} from "../../src/app/renderer/fixture-renderer.js";
import { useFontLibrary } from "../../src/app/fonts/useFontLibrary.js";
import { saveFont, type FontMetadata } from "../../src/app/fonts/storage.js";
import type { OutputProfile, RGBA } from "../../src/app/renderer/renderer-types.js";

interface HarnessArgs {
  text: string;
  fontId: string;
  sizePx: number;
  zoom: number;
  mode: "normal" | "exact";
  profile: OutputProfile;
  ready: boolean;
  debounceMs: number;
  latencyMs: number;
  viewportWidth: number;
  factoryBehavior: "ok" | "throw";
  palette?: RGBA[];
}

interface RenderCall {
  fontId: string;
  token: number;
  text: string;
  width: number;
  height: number;
  foreground: readonly [number, number, number, number];
  background: readonly [number, number, number, number];
  palette: ReadonlyArray<readonly [number, number, number, number]> | null;
}

// JSON text inputs stay strings so browser tests can drive exact color
// payloads (including invalid ones); unparseable text means "omitted".
function parsePaletteInput(value: string): RGBA[] | undefined {
  const trimmed = value.trim();
  if (trimmed === "") return undefined;
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (!Array.isArray(parsed)) return undefined;
    return parsed as unknown as RGBA[];
  } catch {
    return undefined;
  }
}

// Machine probes stay hidden: browser tests read their textContent, so no
// JSON/counter/session readout is ever visible.
function HarnessStatus(): React.JSX.Element {
  const { service, session, available, availabilityError } = useRenderer();
  let readiness = "renderer ready";
  if (available === false) readiness = `renderer unavailable (${availabilityError || "no details"})`;
  else if (!service || available === null) readiness = "renderer starting…";
  return (
    <>
      <p data-harness-readiness role="status">{readiness}</p>
      <output hidden data-harness-session>{session}</output>
      <output hidden data-harness-available>{available === null ? "starting" : String(available)}</output>
    </>
  );
}

// Mounted lifecycle harness around the real shared canvas. Internal inputs
// drive specimen, readiness, geometry and renderer replacement without
// remounting the canvas, so browser tests can assert the React effect wiring
// (not just the scheduler): StrictMode replay, session replacement,
// readiness/font/geometry transitions, debounce staleness and unmount.
let harnessRenders = 0;

function LifecycleHarness(args: HarnessArgs): React.JSX.Element {
  harnessRenders += 1;
  const counters = React.useRef({ constructed: 0, terminated: 0, renders: [] as RenderCall[] });
  const [, setTick] = React.useState(0);
  const [text, setText] = React.useState(args.text);
  const [fontId, setFontId] = React.useState(args.fontId);
  const [isReady, setIsReady] = React.useState(args.ready);
  const [mounted, setMounted] = React.useState(true);
  const [narrow, setNarrow] = React.useState(false);
  const [width, setWidth] = React.useState(args.viewportWidth);
  const [factoryId, setFactoryId] = React.useState(0);
  const [status, setStatus] = React.useState("Waiting for paint…");
  const [paints, setPaints] = React.useState(0);
  const [paletteText, setPaletteText] = React.useState(
    args.palette === undefined ? "" : JSON.stringify(args.palette),
  );
  const palette = parsePaletteInput(paletteText);
  const axes = React.useMemo(() => ({}), []);
  const events = React.useMemo(() => ({
    constructed: () => { counters.current.constructed += 1; },
    terminated: () => { counters.current.terminated += 1; },
    renderCalled: (call: RenderCall) => {
      counters.current.renders.push(call);
      setTick((tick) => tick + 1);
    },
  }), []);
  const createService = React.useCallback(() => {
    if (args.factoryBehavior === "throw") throw new Error("Harness factory failure (synthetic).");
    return createFixtureRenderer({
      scenario: "ok",
      latencyMs: args.latencyMs,
      lineHeight: 24,
      events,
    });
  }, [factoryId, args.factoryBehavior, args.latencyMs]);
  React.useEffect(() => {
    setStatus("Waiting for paint…");
  }, [text, fontId, isReady, mounted, narrow, width, factoryId, paletteText, args.mode, args.zoom, args.sizePx, args.profile]);
  return (
    <RendererProvider createService={createService}>
      <HarnessStatus />
      <p data-harness-status role="status">{status}</p>
      <output hidden data-harness-calls>{JSON.stringify(counters.current)}</output>
      <output hidden data-harness-renders>{harnessRenders}</output>
      <output hidden data-harness-paints>{paints}</output>
      <label>specimen text <input data-harness-text value={text} onChange={(event) => setText(event.target.value)} /></label>
      <label>font id <input data-harness-font value={fontId} onChange={(event) => setFontId(event.target.value)} /></label>
      <label>palette <input data-harness-palette value={paletteText} onChange={(event) => setPaletteText(event.target.value)} /></label>
      <label>ready <input data-harness-ready type="checkbox" checked={isReady} onChange={(event) => setIsReady(event.target.checked)} /></label>
      <label>mounted <input data-harness-mounted type="checkbox" checked={mounted} onChange={(event) => setMounted(event.target.checked)} /></label>
      <label>narrow <input data-harness-narrow type="checkbox" checked={narrow} onChange={(event) => setNarrow(event.target.checked)} /></label>
      <label>width <input data-harness-width type="number" value={width} onChange={(event) => setWidth(Number(event.target.value) || 0)} /></label>
      <button data-harness-replace type="button" onClick={() => setFactoryId((id) => id + 1)}>replace renderer</button>
      <div style={{ width: narrow ? 0 : width, maxWidth: "100%" }}>
        {mounted && (
          <FontCanvas
            fontId={fontId}
            text={text}
            sizePx={args.sizePx}
            axes={axes}
            profile={args.profile}
            role="candidate"
            spacing={0}
            kerning
            stemFitting="font_hints_first"
            zoom={args.zoom}
            mode={args.mode}
            palette={palette}
            ready={isReady}
            debounceMs={args.debounceMs}
            onPaint={(diagnostics) => {
              setPaints((count) => count + 1);
              setStatus(`painted fullHeight=${diagnostics.fullHeight} missing=${diagnostics.missing}`);
            }}
            onError={(message) => {
              setStatus(`error: ${message}`);
            }}
          />
        )}
      </div>
    </RendererProvider>
  );
}

interface StrictShared {
  canvas: { constructed: number; terminated: number; renders: RenderCall[] };
  library: { constructed: number; terminated: number; loads: Array<{ fontId: string }> };
}

function StrictSessionReadout({ prefix }: { prefix: string }): React.JSX.Element {
  const { session, available } = useRenderer();
  return (
    <>
      {prefix === "canvas"
        ? <><output hidden data-strict-canvas-session>{session}</output><output hidden data-strict-canvas-available>{String(available)}</output></>
        : <><output hidden data-strict-lib-session>{session}</output><output hidden data-strict-lib-available>{String(available)}</output></>}
    </>
  );
}

function StrictCanvasSection({ shared }: { shared: StrictShared }): React.JSX.Element {
  const [status, setStatus] = React.useState("Waiting for paint…");
  const events = React.useMemo<FixtureRendererEvents>(() => ({
    constructed: () => { shared.canvas.constructed += 1; },
    terminated: () => { shared.canvas.terminated += 1; },
    renderCalled: (call: RenderCall) => { shared.canvas.renders.push(call); },
  }), [shared]);
  const createService = React.useCallback(
    () => createFixtureRenderer({ scenario: "ok", latencyMs: 200, lineHeight: 24, events }),
    [events],
  );
  const axes = React.useMemo(() => ({}), []);
  return (
    <RendererProvider createService={createService}>
      <StrictSessionReadout prefix="canvas" />
      <p data-strict-canvas-status role="status">{status}</p>
      <output hidden data-strict-canvas-calls>{JSON.stringify(shared.canvas)}</output>
      <div style={{ width: 480, maxWidth: "100%" }}>
        <FontCanvas
          fontId="strict-font"
          text="Strict replay probe."
          sizePx={16}
          axes={axes}
          profile="mono_1bit"
          role="candidate"
          spacing={0}
          kerning
          stemFitting="font_hints_first"
          zoom={1}
          mode="normal"
          ready
          debounceMs={0}
          onPaint={() => setStatus("painted")}
          onError={(message) => setStatus(`error: ${message}`)}
        />
      </div>
    </RendererProvider>
  );
}

const STRICT_FONT_BYTES = Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + 3) % 251);

function strictFontMetadata(): FontMetadata {
  return {
    names: Object.fromEntries(
      ["family", "style", "full", "postscript", "version", "copyright", "manufacturer", "designer", "description", "vendor_url", "designer_url", "license", "license_url"].map((key) => [key, key === "family" ? "StrictHarness" : null])),
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
    kerning: { horizontal: true, vertical: false, sources: ["GPOS kern"] },
    style: { slope: "upright", weight_class: 400, width_class: 5, italic_angle: 0 },
    classification: { family_class: 0, panose: [2, 11, 5, 3, 3, 4, 3, 2, 2, 4], monospaced: false },
    coverage: { character_count: 1, ranges: [[65, 65]] },
    declared_unicode_ranges: [1, 0, 0, 0],
  };
}

function StrictLibraryInner({ shared }: { shared: StrictShared }): React.JSX.Element {
  const library = useFontLibrary();
  const { session } = useRenderer();
  const [fontId, setFontId] = React.useState<string | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      const stored = await saveFont({
        bytes: STRICT_FONT_BYTES.buffer.slice(0) as ArrayBuffer,
        fileName: "strict-harness.ttf",
        name: "Strict Harness",
        metadata: strictFontMetadata(),
        source: "uploaded",
      });
      if (!cancelled) setFontId(stored.id);
    })();
    return () => { cancelled = true; };
  }, []);
  React.useEffect(() => {
    if (fontId && library.fonts) library.ensureLoaded(fontId);
  }, [fontId, library.fonts, library.ensureLoaded]);
  const load = fontId ? library.loadStatus(fontId) : { state: "idle" as const, error: "" };
  return (
    <>
      <output hidden data-strict-lib-session>{session}</output>
      <output hidden data-strict-lib-fonts>{(library.fonts ?? []).length}</output>
      <output hidden data-strict-lib-font-id>{fontId ?? ""}</output>
      <output hidden data-strict-lib-load>{load.state}</output>
      <output hidden data-strict-lib-loaded>{fontId && library.loadedIds.has(fontId) ? "yes" : "no"}</output>
      <output hidden data-strict-lib-available>{String(library.rendererAvailable)}</output>
      <output hidden data-strict-lib-calls>{JSON.stringify(shared.library)}</output>
    </>
  );
}

function StrictLibrarySection({ shared }: { shared: StrictShared }): React.JSX.Element {
  const [factoryId, setFactoryId] = React.useState(0);
  const [mounted, setMounted] = React.useState(true);
  const events = React.useMemo<FixtureRendererEvents>(() => ({
    constructed: () => { shared.library.constructed += 1; },
    terminated: () => { shared.library.terminated += 1; },
    loadCalled: (call: { fontId: string }) => { shared.library.loads.push(call); },
  }), [shared]);
  const createService = React.useCallback(
    () => createFixtureRenderer({ scenario: "ok", latencyMs: 150, lineHeight: 24, events }),
    [factoryId, events],
  );
  return (
    <RendererProvider createService={createService}>
      <button data-strict-lib-replace type="button" onClick={() => setFactoryId((id) => id + 1)}>
        replace library renderer
      </button>
      <label>library mounted
        <input data-strict-lib-mounted type="checkbox" checked={mounted} onChange={(event) => setMounted(event.target.checked)} />
      </label>
      {mounted && <StrictLibraryInner shared={shared} />}
    </RendererProvider>
  );
}

// Genuine root-level StrictMode: the inner tree mounts through its own
// createRoot, so setup-cleanup-setup replays effects in development builds
// (a StrictMode wrapper nested under Storybook's non-strict root would not).
function StrictRootHarness(): React.JSX.Element {
  const hostRef = React.useRef<HTMLDivElement | null>(null);
  const sharedRef = React.useRef<StrictShared | null>(null);
  if (!sharedRef.current) {
    sharedRef.current = {
      canvas: { constructed: 0, terminated: 0, renders: [] },
      library: { constructed: 0, terminated: 0, loads: [] },
    };
  }
  React.useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const root = createRoot(host);
    const shared = sharedRef.current;
    if (shared) {
      root.render(
        <React.StrictMode>
          <StrictCanvasSection shared={shared} />
          <StrictLibrarySection shared={shared} />
        </React.StrictMode>,
      );
    }
    return () => { root.unmount(); };
  }, []);
  return <div ref={hostRef} />;
}

const meta = {
  title: "Renderer/LifecycleHarness",
  component: LifecycleHarness,
  // Opt-in test fixture only (loaded via STORYBOOK_TEST_HARNESSES=1); never
  // user documentation.
  tags: ["!autodocs"],
  parameters: {
    docs: {
      description: {
        component: "Mounted test harness for renderer lifecycle assertions (StrictMode replay, session replacement, readiness and debounce wiring). Not user documentation; driven by browser tests.",
      },
    },
  },
  argTypes: {
    text: { control: "text" },
    fontId: { control: "text" },
    sizePx: { control: { type: "number", min: 1, max: 128 } },
    zoom: { control: { type: "select" }, options: [1, 2, 3, 4] },
    mode: { control: { type: "radio" }, options: ["normal", "exact"] },
    profile: { control: { type: "select" }, options: ["mono_1bit", "gray_3bit"] },
    ready: { control: "boolean" },
    debounceMs: { control: { type: "number", min: 0, max: 1000 } },
    latencyMs: { control: { type: "number", min: 0, max: 1000 } },
    viewportWidth: { control: { type: "number", min: 0, max: 1200 } },
    factoryBehavior: { control: { type: "select" }, options: ["ok", "throw"] },
    palette: { control: "object" },
  },
  args: {
    text: "Agave grids glint.",
    fontId: "harness-font",
    sizePx: 16,
    zoom: 1,
    mode: "normal",
    profile: "mono_1bit",
    ready: true,
    debounceMs: 150,
    latencyMs: 5,
    viewportWidth: 480,
    factoryBehavior: "ok",
    palette: undefined,
  },
} satisfies Meta<typeof LifecycleHarness>;

export default meta;
type Story = StoryObj<typeof meta>;

// Parameterized runtime: latency, debounce, factory failure, and geometry
// variants reach it through story args (e.g. &args=latencyMs:250;debounceMs:0).
export const Default: Story = {};

export const StrictRoot: Story = {
  render: () => <StrictRootHarness />,
};
