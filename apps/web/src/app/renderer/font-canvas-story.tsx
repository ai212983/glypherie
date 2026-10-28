import type { Meta } from "@storybook/react-vite";
import * as React from "react";
import { Popover } from "radix-ui";
import { HexAlphaColorPicker, HexColorInput } from "react-colorful";
import { useArgs } from "storybook/preview-api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { RendererProvider, useRenderer, type RendererService } from "./renderer-context.js";
import { FontCanvas, type FontCanvasProps } from "./FontCanvas.js";
import { createFixtureRenderer } from "./fixture-renderer.js";
import { createWorkerRendererService } from "./worker-service.js";
import { BUNDLED_FONTS } from "../fonts/bundled-fonts.js";
import { useStoryFont } from "./story-font.js";
import type { OutputProfile, RGBA } from "./renderer-types.js";
import "./font-canvas-story.css";

// The real FontCanvas props this playground supports. Pick (not a copy)
// keeps the names and value types tied to FontCanvasProps: renaming a prop
// there fails compilation here instead of drifting into a stale control.
type RealStoryFields = Pick<
  FontCanvasProps,
  "text" | "sizePx" | "zoom" | "mode" | "profile" | "palette" | "ready"
>;

// Plain type alias (not an interface) so it stays assignable to Storybook's
// Args record for useArgs. Exported for the diagnostics story, the only
// other consumer of this canvas harness. Only RealStoryFields are
// FontCanvas props; the rest are story-only helpers (preview setup,
// diagnostics) that live in the inline panels and must never appear as
// component props or Controls rows.
export type CanvasStoryArgs = RealStoryFields & {
  fontName: string;
  viewportWidth: number;
  checkerboard: boolean;
  scenario: StoryScenario;
  diagnostic?: DiagnosticState;
};

// Real rendering stories: the same worker renderer and bundled font bytes
// the app uses, so text edits paint actual glyphs. The error/unavailable
// scenarios below keep the deterministic fixture (no WASM involved there);
// everything else renders through the preview worker.
type StoryScenario = "ok" | "error" | "unavailable";

type DiagnosticState =
  | "ready"
  | "error"
  | "unavailable"
  | "missing-glyphs"
  | "invalid-palette"
  | "not-ready"
  | "empty-text";

const DEFAULT_SPECIMEN = "Pack my box with five dozen liquor jugs.";

// Full deterministic bundles for the diagnostics story: selecting a state
// writes every state-related field (scenario, ready, text, mode), so no
// leftover from the previous negative case can leak through. Font, size,
// profile and user colors are genuinely independent controls and stay
// untouched, except that invalid-palette sets an actually invalid palette
// (the real prop, so validation runs against the real provider in-session)
// and ready restores the last successfully painted colors.
const DIAGNOSTIC_BASE = {
  scenario: "ok",
  ready: true,
  text: DEFAULT_SPECIMEN,
  mode: "normal",
} as const satisfies Partial<CanvasStoryArgs>;

const INVALID_PALETTE: RGBA[] = [
  [200, 30, 30, 255],
  [30, 90, 200, 255],
  [30, 180, 200, 255],
];

// Static state bundles carry no colors: applying a state always pairs its
// fields with the last healthy colors (or the story defaults before the
// first paint), so a leftover invalid palette can never leak into another
// state. Only invalid-palette sets colors itself — an actually invalid
// palette on the real prop. Ready has no static bundle either: it restores
// the last healthy paint dynamically.
const DIAGNOSTIC_PRESETS: Record<
  Exclude<DiagnosticState, "ready" | "invalid-palette">,
  Partial<CanvasStoryArgs>
> = {
  error: { ...DIAGNOSTIC_BASE, scenario: "error" },
  unavailable: { ...DIAGNOSTIC_BASE, scenario: "unavailable" },
  "missing-glyphs": { ...DIAGNOSTIC_BASE, text: "Ag 😀" },
  "not-ready": { ...DIAGNOSTIC_BASE, ready: false },
  "empty-text": { ...DIAGNOSTIC_BASE, text: "" },
};

const STORY_FONT_NAMES = BUNDLED_FONTS.map((entry) => entry.name);

// Color plumbing (story-only): the popup edits one combined #rrggbbaa
// value per entry, while the renderer takes readonly RGBA tuples.
function byteToHex(n: number): string {
  return Math.min(255, Math.max(0, Math.round(n))).toString(16).padStart(2, "0");
}

// Exact #rrggbbaa text for one palette entry: the single combined value the
// popup edits, so RGB and alpha can never disagree on screen.
function rgbaToHex8(entry: RGBA): string {
  return `#${byteToHex(entry[0])}${byteToHex(entry[1])}${byteToHex(entry[2])}${byteToHex(entry[3])}`;
}

// Expands the short forms the popup field accepts (#rgb, #rgba, #rrggbb)
// to full #rrggbbaa (opaque unless stated); anything else is rejected, so a
// half-typed field never commits a partial entry.
function normalizeHex8(value: string): string | undefined {
  let digits = value.trim();
  if (digits.startsWith("#")) digits = digits.slice(1);
  if (!/^[0-9a-f]+$/i.test(digits)) return undefined;
  digits = digits.toLowerCase();
  if (digits.length === 3) digits = digits.split("").map((c) => c + c).join("");
  if (digits.length === 4) digits = digits.split("").map((c) => c + c).join("");
  if (digits.length === 6) digits = `${digits}ff`;
  if (digits.length !== 8) return undefined;
  return `#${digits}`;
}

// Strict parse of a normalized combined value; anything else is ignored, so
// a half-typed field never commits a partial entry.
function hex8ToRgba(value: string): RGBA | undefined {
  const match = /^#([0-9a-f]{8})$/i.exec(value.trim());
  if (!match) return undefined;
  const digits = (match[1] as string).toLowerCase();
  const rgba: RGBA = [
    Number.parseInt(digits.slice(0, 2), 16),
    Number.parseInt(digits.slice(2, 4), 16),
    Number.parseInt(digits.slice(4, 6), 16),
    Number.parseInt(digits.slice(6, 8), 16),
  ];
  return rgba.every(isByte) ? rgba : undefined;
}

const DEFAULT_INK: RGBA = [36, 40, 43, 255];
const DEFAULT_PAPER: RGBA = [255, 255, 255, 255];
const TRANSPARENT: RGBA = [0, 0, 0, 0];

// Runtime shape checks for raw-committed values: explicit JSON commits pass
// verbatim (scalars, null, malformed tuples included) so the renderer can
// reject them, and the picker display below must never crash on them.
function isByte(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 255;
}

function isRGBA(value: unknown): value is RGBA {
  return Array.isArray(value) && value.length === 4 && value.every(isByte);
}

// The full-coverage ink is always the last entry: the Mono level-1 entry
// or the Gray level-7 entry. Level 1 of a Gray palette is only 1/7
// coverage, so reading palette[1] here would wash generated ramps out to a
// tint. Anything malformed falls back to the default ink; only the canvas
// paint (verbatim args) reports the problem.
function fullInk(palette: unknown): RGBA {
  const last = Array.isArray(palette) && palette.length > 0 ? palette[palette.length - 1] : undefined;
  return isRGBA(last) ? ([...last] as RGBA) : ([...DEFAULT_INK] as RGBA);
}

function isStoryLength(length: number): boolean {
  return length === 2 || length === 8;
}

// Complete palette for a target length: entry 0 is the paper, every active
// level carries the ink RGB at its coverage share of the ink alpha.
function seedFull(paper: RGBA, ink: RGBA, target: 2 | 8): RGBA[] {
  const next: RGBA[] = [[...paper] as RGBA];
  for (let level = 1; level < target; level += 1) {
    next.push([ink[0], ink[1], ink[2], Math.round((ink[3] * level) / (target - 1))]);
  }
  return next;
}

// Fit a valid-length palette (2 or 8 entries) to the target length for the
// current profile. Only the length changes: entry 0 (the paper) is always
// preserved, multi-level colors restore verbatim from the parked Gray
// palette when one was kept, and the collapse keeps the full-coverage ink.
// Anything else (an explicit raw length from the diagnostics tools) is left
// alone so it can error.
function fitPalette(
  palette: readonly RGBA[],
  target: 2 | 8,
  parkedGray: RGBA[] | undefined,
): RGBA[] {
  if (palette.length === target) return palette.map((entry) => [...entry] as RGBA);
  const paper = palette[0] !== undefined ? ([...palette[0]] as RGBA) : ([...DEFAULT_PAPER] as RGBA);
  if (target === 2) return [paper, fullInk(palette)];
  // Restoring the parked levels keeps the CURRENT paper: the parked array
  // only supplies the nonzero entries, so a paper edited while narrow is
  // never reverted to the parked one.
  if (parkedGray !== undefined && parkedGray.length === 8) {
    return [paper, ...parkedGray.slice(1).map((entry) => [...entry] as RGBA)];
  }
  return seedFull(paper, fullInk(palette), 8);
}

// One popup RGBA editor per palette entry: a swatch trigger showing the
// combined #rrggbbaa value, opening a HexAlphaColorPicker plus one combined
// hex field. Opacity lives only inside the popup — there is no separate
// alpha slider or readout anywhere. Rendered from the same bytes the canvas
// paints, so every visible value is what is rendered.
function RgbaPicker({ row, label, entry, title, open, onOpenChange, onCommit }: {
  row: string;
  label: string;
  entry: RGBA;
  title?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCommit: (entry: RGBA) => void;
}): React.JSX.Element {
  const value = rgbaToHex8(entry);
  const commit = (next: string): void => {
    const rgba = hex8ToRgba(normalizeHex8(next) ?? "");
    if (rgba !== undefined) onCommit(rgba);
  };
  return (
    <div data-picker-row={row} className="fc-rgba">
      {title !== undefined && <span className="fc-rgba-title">{title}</span>}
      <Popover.Root open={open} onOpenChange={onOpenChange}>
        <Popover.Trigger asChild>
          <button
            type="button"
            data-picker-trigger={row}
            aria-label={`${label} RGBA, current value ${value}`}
          >
            <span aria-hidden="true" className="fc-swatch" style={{ backgroundColor: value }} />
            <span data-picker-bytes={row}>{value}</span>
          </button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            data-rgba-pop={row}
            className="fc-rgba-pop"
            role="dialog"
            aria-label={`${label} RGBA picker`}
            sideOffset={6}
            collisionPadding={8}
          >
            <HexAlphaColorPicker color={value} onChange={commit} />
            <label className="fc-rgba-field">
              {`${label} RGBA`}
              <HexColorInput prefixed alpha color={value} onChange={commit} data-rgba-field={row} />
            </label>
            <p className="fc-rgba-hint">Combined hex: #rgb, #rgba, #rrggbb or #rrggbbaa.</p>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}

// Writes one actual palette entry verbatim. Arrays are cloned across the
// mapping; readonly inputs stay supported because nothing mutates in place.
function setPaletteEntryBytes(palette: readonly RGBA[], index: number, entry: RGBA): RGBA[] {
  const next: RGBA[] = palette.map((item) => [...item] as RGBA);
  while (next.length <= index) next.push([...TRANSPARENT] as RGBA);
  next[index] = [...entry] as RGBA;
  return next;
}

// The args hook lives in the story render function below; the panels are
// plain children receiving args plus the updater, so hook context is never
// in question. Playground setup configures the preview (font, viewport,
// transparency aid); it is not FontCanvas props. The pickers write the
// actual palette arg: entry 0 is the paper, the rest are ink levels (Mono
// shows Level 1; Gray shows 1..7). Malformed raw values hide their pickers
// (display-only guard); the verbatim args still reach the canvas so the
// error reports there.
function PreviewPanels({ args, updateArgs, viewPalette }: {
  args: CanvasStoryArgs;
  updateArgs: (patch: Partial<CanvasStoryArgs>) => void;
  viewPalette: readonly RGBA[] | undefined;
}): React.JSX.Element {
  const fontSelectId = React.useId();
  const target = args.profile === "mono_1bit" ? 2 : 8;
  const rawPalette: unknown = args.palette;
  const shapeOk =
    rawPalette === undefined || (Array.isArray(rawPalette) && rawPalette.every(isRGBA));
  const invalid =
    !shapeOk || (Array.isArray(rawPalette) && !isStoryLength(rawPalette.length));
  const ink = fullInk(viewPalette);
  const paper = (() => {
    if (!Array.isArray(rawPalette) || rawPalette.length === 0) return [...DEFAULT_PAPER] as RGBA;
    const entry0: unknown = rawPalette[0];
    return isRGBA(entry0) ? ([...entry0] as RGBA) : ([...DEFAULT_PAPER] as RGBA);
  })();
  const active = args.profile === "mono_1bit" ? [1] : [1, 2, 3, 4, 5, 6, 7];
  // Rows edit the fitted palette (valid lengths) so every picker commit
  // stays paintable. An omitted palette seeds from the defaults, matching
  // what the rows display.
  const rowsBase = viewPalette !== undefined && viewPalette.every(isRGBA)
    ? viewPalette
    : seedFull(DEFAULT_PAPER, DEFAULT_INK, target);
  // Only one popup stays open at a time, so editors never stack.
  const [openRow, setOpenRow] = React.useState<string | null>(null);
  const pickerProps = (row: string): { open: boolean; onOpenChange: (open: boolean) => void } => ({
    open: openRow === row,
    onOpenChange: (open: boolean) => setOpenRow(open ? row : null),
  });
  // Font color is an explicit draft: staging it repaints nothing, so
  // exploring the popup can never clobber a custom uneven palette — only
  // the rebuild below regenerates every ink level (keeping the paper). The
  // rows below it commit individual edits immediately instead. The draft
  // follows the painted full ink whenever that basis changes.
  const inkBasis = rgbaToHex8(ink);
  const [inkDraft, setInkDraft] = React.useState({ value: ink, basis: inkBasis });
  if (inkDraft.basis !== inkBasis) {
    setInkDraft({ value: ink, basis: inkBasis });
  }
  const rebuildInk = (): void => {
    updateArgs({ palette: seedFull(paper, inkDraft.value, target) });
  };
  const commitEntry = (index: number, entry: RGBA): void => {
    updateArgs({ palette: setPaletteEntryBytes(rowsBase, index, entry) });
  };
  return (
    <>
      <details data-setup-panel className="fc-disclosure" open>
        <summary>Preview setup</summary>
        <div className="fc-fields fc-setup">
          <label htmlFor={fontSelectId}>
            Font
            <Select
              value={args.fontName}
              onValueChange={(fontName) => updateArgs({ fontName })}
            >
              <SelectTrigger id={fontSelectId} data-setup-font><SelectValue /></SelectTrigger>
              <SelectContent>
                {STORY_FONT_NAMES.map((name) => <SelectItem key={name} value={name}>{name}</SelectItem>)}
              </SelectContent>
            </Select>
          </label>
          <label>
            Viewport width
            <input
              data-setup-width
              type="number"
              min={120}
              max={1200}
              step={10}
              value={args.viewportWidth}
              onChange={(event) => updateArgs({ viewportWidth: Number(event.target.value) || 0 })}
            />
          </label>
          <label>
            Checkerboard
            <input
              data-setup-checkerboard
              type="checkbox"
              checked={args.checkerboard}
              onChange={(event) => updateArgs({ checkerboard: event.target.checked })}
            />
          </label>
        </div>
      </details>
      {invalid ? (
        <p data-picker-note="invalid" className="fc-note">
          Custom palette value active: the pickers stay hidden while it applies verbatim.
          Edit it in Raw palette JSON below, or re-apply the Ready state.
        </p>
      ) : (
        <div data-color-playground>
          <RgbaPicker
            row="font"
            label="Font color"
            title="Font color"
            entry={inkDraft.value}
            onCommit={(entry) => setInkDraft((draft) => ({ ...draft, value: entry }))}
            {...pickerProps("font")}
          />
          <p data-paper-note className="fc-note">
            Font color is only a draft until rebuilt; rebuilding replaces every ink level.
          </p>
          <button type="button" data-apply-ink onClick={rebuildInk}>
            Rebuild ink levels from font color
          </button>
          <RgbaPicker
            row="background"
            label="Background color"
            title="Background color (palette entry 0)"
            entry={paper}
            onCommit={(entry) => commitEntry(0, entry)}
            {...pickerProps("background")}
          />
          <details data-levels-disclosure className="fc-disclosure">
            <summary>{`Coverage levels (${active.length})`}</summary>
            <table className="fc-levels" aria-label="Coverage levels">
              <thead>
                <tr><th scope="col">Level</th><th scope="col">RGBA</th></tr>
              </thead>
              <tbody>
                {active.map((level) => {
                  const entry = rowsBase[level] ?? DEFAULT_INK;
                  return (
                    <tr key={level}>
                      <th scope="row">{level}</th>
                      <td>
                        <RgbaPicker
                          row={`level-${level}`}
                          label={`Level ${level}`}
                          entry={entry}
                          onCommit={(next) => commitEntry(level, next)}
                          {...pickerProps(`level-${level}`)}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </details>
        </div>
      )}
    </>
  );
}

// Diagnostics state workflow: always visible near the preview, ahead of the
// optional appearance editors. Selecting a state applies its bundle
// immediately through onApplyPreset — including when the same state is
// already selected, via Apply state — so recovery never depends on a
// change-only passive effect. Labels are human-readable; values unchanged.
const DIAGNOSTIC_STATES: { value: DiagnosticState; label: string }[] = [
  { value: "ready", label: "Ready" },
  { value: "error", label: "Render error" },
  { value: "unavailable", label: "Service unavailable" },
  { value: "missing-glyphs", label: "Missing glyphs" },
  { value: "invalid-palette", label: "Invalid palette" },
  { value: "not-ready", label: "Not ready" },
  { value: "empty-text", label: "Empty text" },
];

function DiagnosticStateBar({ current, onApplyPreset }: {
  current: DiagnosticState;
  onApplyPreset: (state: DiagnosticState) => void;
}): React.JSX.Element {
  const stateSelectId = React.useId();
  return (
    <div data-diagnostic-tools className="fc-fields">
      <label htmlFor={stateSelectId}>
        Failure state
        <Select
          value={current}
          onValueChange={(value) => onApplyPreset(value as DiagnosticState)}
        >
          <SelectTrigger id={stateSelectId} data-diagnostic-state><SelectValue /></SelectTrigger>
          <SelectContent>
            {DIAGNOSTIC_STATES.map((state) => <SelectItem key={state.value} value={state.value}>{state.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </label>
      <div>
        <button type="button" data-diagnostic-apply onClick={() => onApplyPreset(current)}>
          Apply state
        </button>
      </div>
    </div>
  );
}

// Raw palette JSON editor: writes the ACTUAL palette arg verbatim (invalid
// values reach the renderer and error there). Collapsed by default inside
// its own disclosure; never rendered on normal stories.
function DiagnosticRawTools({ args, updateArgs }: {
  args: CanvasStoryArgs;
  updateArgs: (patch: Partial<CanvasStoryArgs>) => void;
}): React.JSX.Element {
  const paletteSource = args.palette === undefined ? "" : JSON.stringify(args.palette);
  const [paletteDraft, setPaletteDraft] = React.useState(paletteSource);
  const [paletteBasis, setPaletteBasis] = React.useState(paletteSource);
  const [rawError, setRawError] = React.useState("");
  // Drafts follow the actual props (preset selections, picker edits) until
  // the user types; an Apply or blur commits the draft back to the args.
  if (paletteBasis !== paletteSource) {
    setPaletteBasis(paletteSource);
    setPaletteDraft(paletteSource);
  }
  React.useEffect(() => {
    setRawError("");
  }, [paletteSource]);
  const commitJson = (text: string): void => {
    const trimmed = text.trim();
    if (trimmed === "") {
      // Blank means omitted: the renderer default applies, not an empty list.
      updateArgs({ palette: undefined });
      setRawError("");
      return;
    }
    try {
      const parsed: unknown = JSON.parse(trimmed);
      updateArgs({ palette: parsed } as Partial<CanvasStoryArgs>);
      setRawError("");
    } catch {
      setRawError("Invalid JSON for palette; the last value keeps applying.");
    }
  };
  return (
    <details data-raw-disclosure className="fc-disclosure">
      <summary>Raw palette JSON</summary>
      <div className="fc-fields">
        <label>
          Palette JSON (commits verbatim; blank restores the default)
          <textarea
            data-raw-palette
            data-raw-committed={paletteSource}
            rows={2}
            value={paletteDraft}
            onChange={(event) => setPaletteDraft(event.target.value)}
            onBlur={(event) => commitJson(event.target.value)}
          />
        </label>
        <div>
          <button type="button" data-raw-palette-apply onClick={() => commitJson(paletteDraft)}>
            Apply palette JSON
          </button>
        </div>
      </div>
      {rawError !== "" && <p data-raw-error role="alert" className="fc-error-text">{rawError}</p>}
    </details>
  );
}

// One human status line covers service, readiness and error states (the
// concise text screen readers announce); a clean paint renders no line at
// all, and a paint with uncovered characters or truncation reports just
// that. The exact machine fullHeight/missing/truncated line stays in the
// truly hidden probe below for automated checks — never announced, never
// shown.
function humanStatus(
  status: string,
  available: boolean | null,
  service: RendererService | null,
  availabilityError: string,
  loadError: string,
  argsReady: boolean,
  fontReady: boolean,
  paintInfo: { missing: number; truncated: boolean } | null,
): { text: string; tone: "ok" | "error" } | null {
  if (available === false) {
    return {
      text: `Renderer unavailable${availabilityError !== "" ? `: ${availabilityError}` : ""}`,
      tone: "error",
    };
  }
  if (!service || available === null) return { text: "Renderer starting…", tone: "ok" };
  if (loadError !== "") return { text: `Font failed to load: ${loadError}`, tone: "error" };
  if (!argsReady) return { text: "Rendering paused", tone: "ok" };
  if (!fontReady) return { text: "Waiting for the font to load…", tone: "ok" };
  if (status.startsWith("error:")) return { text: status.slice("error: ".length), tone: "error" };
  if (status.startsWith("painted")) {
    // An ordinary clean paint says nothing: the rendered canvas is the
    // confirmation. Only a paint with something to report (uncovered
    // characters, truncation) earns a human line.
    const notes = [
      paintInfo !== null && paintInfo.missing > 0
        ? `${paintInfo.missing} characters missing from the font`
        : "",
      paintInfo !== null && paintInfo.truncated ? "text truncated" : "",
    ].filter((note) => note !== "");
    return notes.length > 0 ? { text: notes.join(" — "), tone: "ok" } : null;
  }
  return { text: "Preparing preview…", tone: "ok" };
}

// Storybook invokes this as the story render function, inside preview-hook
// context: it is the only place useArgs may run. It renders immediately into
// the plain React child below, which owns all component state and effects.
// On the docs page (viewMode "docs", never a helper arg) the embedded
// editors collapse into one Edit preview disclosure per example; the
// standalone canvas keeps them directly accessible.
export function FontCanvasStory(args: CanvasStoryArgs, context?: { viewMode?: string }): React.JSX.Element {
  const [, updateArgs] = useArgs<CanvasStoryArgs>();
  const compactPanels = context?.viewMode === "docs";
  return <StagedFontCanvas args={args} updateArgs={updateArgs} compactPanels={compactPanels} />;
}

// Last successfully painted palette: presets restore it, so recovery
// repaints the user's healthy colors instead of resetting to defaults.
interface HealthySnapshot {
  palette: readonly RGBA[] | undefined;
  profile: OutputProfile;
}

// Controller state owned by StagedFontCanvas, ABOVE the keyed provider: the
// error/unavailable scenarios remount everything below, and preset recovery
// must survive that. Nothing here touches the painted status.
interface StoryController {
  noteHealthy: (snapshot: HealthySnapshot) => void;
  applyDiagnostic: (state: DiagnosticState) => void;
  parked: { current: { mono?: RGBA[]; gray?: RGBA[] } };
  lastTarget: { current: number | null };
}

// Shared by the main examples and the diagnostics story: provider choice,
// font loading, playground wiring, and canvas live here. The diagnostics
// story additionally opts into the simulation tools panel.
export function StagedFontCanvas({ args, updateArgs, diagnosticTools, compactPanels }: {
  args: CanvasStoryArgs;
  updateArgs: (patch: Partial<CanvasStoryArgs>) => void;
  diagnosticTools?: boolean;
  compactPanels?: boolean;
}): React.JSX.Element {
  const lastHealthy = React.useRef<HealthySnapshot | null>(null);
  const parked = React.useRef<{ mono?: RGBA[]; gray?: RGBA[] }>({});
  const lastTarget = React.useRef<number | null>(null);
  const noteHealthy = React.useCallback((snapshot: HealthySnapshot): void => {
    lastHealthy.current = snapshot;
  }, []);
  // Applies one diagnostics bundle immediately (never through a change-only
  // effect), so re-applying the already-selected state works too. Every
  // state except invalid-palette pairs its fields with the last healthy
  // colors — or the story defaults before the first paint — clearing any
  // prior invalid color state.
  const applyDiagnostic = React.useCallback((state: DiagnosticState): void => {
    if (state === "invalid-palette") {
      updateArgs({
        diagnostic: state,
        ...DIAGNOSTIC_BASE,
        palette: INVALID_PALETTE.map((entry) => [...entry] as RGBA),
      });
      return;
    }
    const saved = lastHealthy.current;
    const preset = state === "ready" ? DIAGNOSTIC_BASE : DIAGNOSTIC_PRESETS[state];
    let restored: RGBA[] | undefined = saved?.palette === undefined
      ? undefined
      : saved.palette.map((entry) => [...entry] as RGBA);
    // The stash may predate a profile switch made while invalid colors
    // blocked repainting: converge it to the current profile then. A stash
    // from the current profile restores verbatim, preserving explicitly
    // committed arrays.
    const profileTarget = args.profile === "mono_1bit" ? 2 : 8;
    if (
      saved !== null &&
      saved.profile !== args.profile &&
      restored !== undefined &&
      isStoryLength(restored.length) &&
      restored.length !== profileTarget
    ) {
      restored = fitPalette(restored, profileTarget, parked.current.gray);
    }
    updateArgs({
      diagnostic: state,
      ...preset,
      palette: restored,
    });
  }, [args.profile, updateArgs]);
  const controller: StoryController = { noteHealthy, applyDiagnostic, parked, lastTarget };
  // The ok scenario renders through the real preview worker; error and
  // unavailable keep the deterministic fixture that simulates them.
  const createService = React.useCallback(
    () => (args.scenario === "ok" ? createWorkerRendererService() : createFixtureRenderer({ scenario: args.scenario })),
    [args.scenario],
  );
  return (
    <RendererProvider key={args.scenario} createService={createService}>
      <StagedCanvas args={args} updateArgs={updateArgs} diagnosticTools={diagnosticTools} compactPanels={compactPanels} controller={controller} />
    </RendererProvider>
  );
}

export function FontCanvasDiagnosticsStory(args: CanvasStoryArgs): React.JSX.Element {
  const [, updateArgs] = useArgs<CanvasStoryArgs>();
  return <StagedFontCanvas args={args} updateArgs={updateArgs} diagnosticTools />;
}

function StagedCanvas({ args, updateArgs, diagnosticTools, compactPanels, controller }: {
  args: CanvasStoryArgs;
  updateArgs: (patch: Partial<CanvasStoryArgs>) => void;
  diagnosticTools?: boolean;
  compactPanels?: boolean;
  controller: StoryController;
}): React.JSX.Element {
  const { service, session, available, availabilityError } = useRenderer();
  const real = args.scenario === "ok";
  const storyFont = useStoryFont(service, session, available, real, real ? args.fontName : "");
  const ready = args.ready && storyFont.ready;
  const [status, setStatus] = React.useState("Waiting for paint…");
  const [paints, setPaints] = React.useState(0);
  const [paintInfo, setPaintInfo] = React.useState<{ missing: number; truncated: boolean } | null>(null);
  const { parked, lastTarget } = controller;
  const {
    text, sizePx, zoom, mode, profile, palette,
    viewportWidth, checkerboard,
  } = args;
  // The actual palette arg, validated at runtime: explicit raw commits pass
  // verbatim (scalars, null, malformed tuples included) so the renderer can
  // reject them. Only well-shaped RGBA arrays take part in fitting below.
  const rawPalette: unknown = palette;
  const validPalette: RGBA[] | undefined =
    Array.isArray(rawPalette) && rawPalette.every(isRGBA)
      ? rawPalette.map((entry) => [...(entry as RGBA)] as RGBA)
      : undefined;
  // Park every valid multi-level palette before a narrower target can
  // replace it in the args below. Declared first so it captures the full
  // palette on the same commit the target changes.
  React.useEffect(() => {
    if (validPalette?.length === 2) parked.current.mono = validPalette;
    else if (validPalette?.length === 8) parked.current.gray = validPalette;
  }, [palette]);
  // No resetting status on input changes: the initial state is Waiting, and
  // each paint/error report sets the authoritative last outcome. Any reset
  // here is a parent passive effect that runs after the child's report, so
  // it would overwrite real outcomes — including with Waiting when a
  // deduplicated request correctly produces no new paint.
  // Keep the actual palette arg at a valid length for the profile/editor.
  // The fit runs only when the target itself changed (profile/editor
  // switch): palette edits — pickers and explicit raw commits of any
  // length — never trigger it, so raw values reach the renderer verbatim
  // and error there instead of being silently repaired.
  const target = profile === "mono_1bit" ? 2 : 8;
  // A profile/editor switch leaves a valid-length palette mismatched for
  // one commit. Painting it verbatim would flash a generated Invalid
  // palette error before the fit below lands, so the canvas stays disabled
  // until the actual args converge. Explicit raw values are never gated:
  // only story lengths (1/2/8) take part, and only across a target change.
  const [pendingFit, setPendingFit] = React.useState<RGBA[] | null>(null);
  React.useEffect(() => {
    if (lastTarget.current === target) return;
    lastTarget.current = target;
    if (validPalette !== undefined && isStoryLength(validPalette.length) && validPalette.length !== target) {
      const fitted = fitPalette(validPalette, target, parked.current.gray);
      setPendingFit(fitted);
      updateArgs({ palette: fitted });
    }
  });
  // The gate lifts once the actual args converge (or an explicit raw value
  // replaces them); every panel commit below clears it directly.
  React.useEffect(() => {
    if (
      pendingFit !== null &&
      (validPalette === undefined ||
        !isStoryLength(validPalette.length) ||
        validPalette.length === target)
    ) {
      setPendingFit(null);
    }
  });
  const converting =
    pendingFit !== null || (validPalette !== undefined &&
      isStoryLength(validPalette.length) &&
      validPalette.length !== target &&
      lastTarget.current !== target);
  // Fitted view for the picker rows so they keep editing whole levels
  // across the switch commit; the canvas below always paints the actual
  // args, so Controls converge on exactly what is painted.
  const mismatched =
    validPalette !== undefined && isStoryLength(validPalette.length) && validPalette.length !== target;
  const viewPalette = mismatched
    ? fitPalette(validPalette, target, parked.current.gray)
    : validPalette;
  // Panel commits are explicit user values: they clear a pending conversion
  // gate (manager profile switches, the only other palette changer, keep it
  // until the args converge).
  const commitArgs = (patch: Partial<CanvasStoryArgs>): void => {
    setPendingFit(null);
    updateArgs(patch);
  };
  // One concise human line up front when there is something to say
  // (announced); the exact machine text stays in the truly hidden probe
  // below for automated checks. Service and readiness lead, so nothing
  // claims a ready preview while the font is still loading or the renderer
  // is down — and a clean paint claims nothing at all.
  const human = humanStatus(
    status, available, service, availabilityError ?? "", storyFont.loadError,
    args.ready, storyFont.ready, paintInfo,
  );
  return (
    <section data-fc-surface aria-label="FontCanvas preview">
      {human !== null && (
        <p data-story-human role="status" className="fc-human" data-tone={human.tone}>{human.text}</p>
      )}
      <div
        data-fc-preview
        style={{
          width: viewportWidth,
          ...(checkerboard
            ? { backgroundImage: "conic-gradient(#c9c9c9 0 25%, #f2f2f2 0 50%, #c9c9c9 0 75%, #f2f2f2 0)", backgroundSize: "16px 16px" }
            : {}),
        }}
      >
        <FontCanvas
          fontId={storyFont.fontId}
          text={text}
          sizePx={sizePx}
          axes={{}}
          profile={profile}
          role="baseline"
          spacing={0}
          kerning
          stemFitting="font_hints_first"
          monoRaster={{ dropout: "smart", includeStubs: false, fontInstructions: false }}
          zoom={zoom}
          mode={mode}
          palette={palette}
          ready={ready && !converting}
          debounceMs={150}
          viewportProps={{
            className: "block overflow-hidden",
            style: { width: "calc(100% - 2rem)", height: "auto", margin: "0 1rem 1rem" },
          }}
          canvasProps={{ className: "block [image-rendering:pixelated]" }}
          onPaint={(diagnostics) => {
            // Snapshot the ACTUAL painted args, never the fitted picker
            // view: restoring a converted representation would silently
            // rewrite explicitly committed palettes.
            controller.noteHealthy({
              palette,
              profile,
            });
            setPaints((count) => count + 1);
            setPaintInfo({ missing: diagnostics.missing, truncated: diagnostics.truncated });
            setStatus(
              `painted fullHeight=${diagnostics.fullHeight} `
              + `missing=${diagnostics.missing} truncated=${diagnostics.truncated}`,
            );
          }}
          onError={(message) => {
            setStatus(`error: ${message}`);
          }}
        />
      </div>
      <output data-story-status hidden>{status}</output>
      <p data-story-paints hidden>{paints}</p>
      {diagnosticTools && (
        <DiagnosticStateBar current={args.diagnostic ?? "ready"} onApplyPreset={controller.applyDiagnostic} />
      )}
      {compactPanels ? (
        <details data-edit-preview className="fc-disclosure">
          <summary>Edit preview</summary>
          <PreviewPanels args={args} updateArgs={commitArgs} viewPalette={viewPalette} />
        </details>
      ) : (
        <PreviewPanels args={args} updateArgs={commitArgs} viewPalette={viewPalette} />
      )}
      {diagnosticTools && (
        <DiagnosticRawTools args={args} updateArgs={commitArgs} />
      )}
    </section>
  );
}

type CanvasArgTypes = NonNullable<Meta<CanvasStoryArgs>["argTypes"]>;
type ArgRow = CanvasArgTypes[keyof CanvasArgTypes];

// Visible Controls/Docs rows, and nothing else, are real FontCanvas props:
// the Record key types fail compilation if a helper name lands here or a
// real prop row goes missing.
const realPropArgTypes: Record<keyof RealStoryFields, ArgRow> = {
  text: { control: "text", description: "Specimen text; empty text paints a blank canvas." },
  sizePx: { control: { type: "number", min: 1, max: 128 }, description: "Requested pixel size." },
  zoom: { control: { type: "select" }, options: [1, 2, 3, 4], description: "Integer display magnification." },
  mode: {
    control: { type: "radio" },
    options: ["normal", "exact"],
    description: "Normal and exact mirror the interactive specimen display modes.",
  },
  profile: {
    control: { type: "select" },
    options: ["mono_1bit", "gray_3bit"],
    description: "Output profile; sets the coverage levels (2 Mono, 8 Gray) a full palette must hold.",
  },
  // Actual painted values, edited through the pickers in the Playground
  // setup panel: control:false keeps the truthful row without a redundant
  // JSON editor (object values render as a dash, not as bytes).
  palette: {
    control: false,
    description: "Complete coverage palette as [r, g, b, a] byte tuples: exactly 2 (Mono) / 8 (Gray) entries with entry 0 as the paper; omitted paints default ink on paper. Edit with the Font color / Background / Level pickers.",
  },
  ready: {
    control: "boolean",
    description: "Allow rendering; the preview also waits for the selected font to load.",
  },
};

// Story-only helpers: hidden from Controls/Docs, living in the inline
// Playground setup / Diagnostic tools panels instead. The Record key type
// forces every non-prop arg to stay hidden here.
const helperArgTypes: Record<Exclude<keyof CanvasStoryArgs, keyof RealStoryFields>, ArgRow> = {
  fontName: { table: { disable: true } },
  viewportWidth: { table: { disable: true } },
  checkerboard: { table: { disable: true } },
  scenario: { table: { disable: true } },
  diagnostic: { table: { disable: true } },
};

export const canvasArgTypes: CanvasArgTypes = {
  ...realPropArgTypes,
  ...helperArgTypes,
};

export const defaultCanvasArgs: CanvasStoryArgs = {
  text: DEFAULT_SPECIMEN,
  sizePx: 16,
  zoom: 1,
  mode: "normal",
  profile: "mono_1bit",
  palette: undefined,
  ready: true,
  fontName: "Roboto",
  viewportWidth: 640,
  checkerboard: false,
  scenario: "ok",
};

// Truthful per-story source snippet: actual FontCanvas usage with the
// story's values, never wrapper/helper args. Shown instead of the
// autogenerated snippet, which would present story options as props.
export function fontCanvasSnippet(overrides: Partial<CanvasStoryArgs> = {}): string {
  const args = { ...defaultCanvasArgs, ...overrides };
  const tuple = (entry: RGBA): string => `[${entry[0]}, ${entry[1]}, ${entry[2]}, ${entry[3]}]`;
  return [
    "// Example FontCanvas usage (this story's values with the default Roboto fontId):",
    ...(args.palette === undefined ? ["// (palette omitted: default ink on paper)"] : []),
    "// Fixed preview props (axes, role, spacing, kerning, stem fitting, scan, debounce) shown literally;",
    "// viewport styling and paint callbacks omitted.",
    "<FontCanvas",
    '  fontId="storybook/Roboto.ttf"',
    `  text={${JSON.stringify(args.text)}}`,
    `  sizePx={${args.sizePx}}`,
    "  axes={{}}",
    `  profile="${args.profile}"`,
    '  role="baseline"',
    "  spacing={0}",
    "  kerning",
    '  stemFitting="font_hints_first"',
    '  monoRaster={{ dropout: "smart", includeStubs: false, fontInstructions: false }}',
    `  zoom={${args.zoom}}`,
    `  mode="${args.mode}"`,
    ...(args.palette === undefined ? [] : [`  palette={[${args.palette.map(tuple).join(", ")}]}`]),
    args.ready ? "  ready" : "  ready={false}",
    "  debounceMs={150}",
    "/>",
  ].join("\n");
}
