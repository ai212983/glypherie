// cspell:words dctx nctx
import * as React from "react";
import { useRenderer, type RendererService } from "./renderer-context.js";
import {
  RenderScheduler,
  buildRequestKey,
  type FontCanvasMode,
} from "./render-scheduler.js";
import {
  backingSize,
  cssSize,
  magnification,
  nativeHeightCap,
  nativeWidthFor,
  snapTranslation,
} from "./display-scaling.js";
import type { OutputProfile, RendererRole, RGBA, StemFitting } from "./renderer-types.js";
import { logicalBounds, toRenderSpec } from "./render-spec";
import { layoutHeight } from "./render-layout.js";
import type { RenderPixels } from "./client";
import type { RenderSpec } from "./renderer-types.js";

export interface FontCanvasDiagnostics {
  missing: number;
  fullHeight: number;
  truncated: boolean;
}

export interface FontCanvasProps {
  fontId: string;
  text: string;
  sizePx: number;
  axes: Record<string, number>;
  profile: OutputProfile;
  role: RendererRole;
  spacing: number;
  kerning: boolean;
  stemFitting: StemFitting;
  zoom: number;
  mode: FontCanvasMode;
  // Complete coverage palette (exactly 2 Mono / 8 Gray entries, entry 0 is
  // the paper); omitted paints the default ink on paper.
  palette?: readonly RGBA[];
  // Font loaded into the current renderer session. Toggling re-renders even
  // when the specimen is unchanged; the scheduler identity is reset while
  // disabled so no keyed remount is needed.
  ready: boolean;
  // Text-change debounce; other inputs render without waiting.
  debounceMs: number;
  viewportProps?: React.HTMLAttributes<HTMLDivElement> & { [key: `data-${string}`]: string };
  canvasProps?: React.CanvasHTMLAttributes<HTMLCanvasElement> & { [key: `data-${string}`]: string };
  canvasFallback?: React.ReactNode;
  // Extra per-request identity recorded on the canvas for tests and stories.
  debugIdentity?: (measuredWidth: number) => Record<string, unknown>;
  exposeFullHeight?: boolean;
  // Blank the committed canvas when a render fails, so a stale paint cannot
  // survive an error. Defaults to false; card-style consumers opt in.
  clearOnError?: boolean;
  onPaint?: (diagnostics: FontCanvasDiagnostics) => void;
  onError?: (message: string, info: { renderer: RendererRole }) => void;
}

function deviceRatio(): number {
  const ratio = Number(window.devicePixelRatio);
  return Number.isFinite(ratio) && ratio > 0 ? ratio : 1;
}

function nativeCap(width: number): number {
  return Math.min(4096, Math.max(1, Math.floor(16777216 / Math.max(1, width))));
}

function clearDisplay(display: HTMLCanvasElement): void {
  display.width = 0;
  display.height = 0;
  delete display.dataset.rendered;
  delete display.dataset.fullHeight;
  delete display.dataset.renderKey;
}

function blit(native: HTMLCanvasElement, data: RenderPixels): void {
  if (data.pixels.byteLength !== data.width * data.height * 4) throw new Error("Invalid render pixels.");
  native.width = data.width;
  native.height = data.height;
  const nctx = native.getContext("2d", { alpha: true });
  if (!nctx) throw new Error("Canvas 2D context unavailable.");
  nctx.imageSmoothingEnabled = false;
  nctx.putImageData(new ImageData(new Uint8ClampedArray(data.pixels), data.width, data.height), 0, 0);
}

function displayContext(display: HTMLCanvasElement): CanvasRenderingContext2D {
  const dctx = display.getContext("2d", { alpha: true });
  if (!dctx) throw new Error("Canvas 2D context unavailable.");
  dctx.imageSmoothingEnabled = false;
  return dctx;
}

function rgbaCss(color: readonly [number, number, number, number]): string {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${color[3] / 255})`;
}

// The renderer already composites ink over the background, so the display
// frame is rebuilt without blending over stale paint: clear everything
// (a transparent background fill would leave old opaque pixels behind),
// then copy the image region verbatim. Only the uncovered padding takes the
// background, as source-over on cleared pixels: filling the whole canvas,
// even destination-over, would composite the background a second time behind
// translucent image pixels (alpha and RGB both shift). The drawn image
// always starts at the origin, leaving at most a right and a bottom strip.
function commitDisplay(
  display: HTMLCanvasElement,
  background: readonly [number, number, number, number],
  imageWidth: number,
  imageHeight: number,
  draw: (dctx: CanvasRenderingContext2D) => void,
): void {
  const dctx = displayContext(display);
  dctx.globalCompositeOperation = "source-over";
  dctx.clearRect(0, 0, display.width, display.height);
  dctx.globalCompositeOperation = "copy";
  draw(dctx);
  dctx.globalCompositeOperation = "source-over";
  dctx.fillStyle = rgbaCss(background);
  if (imageWidth < display.width) dctx.fillRect(imageWidth, 0, display.width - imageWidth, display.height);
  if (imageHeight < display.height) dctx.fillRect(0, imageHeight, imageWidth, display.height - imageHeight);
  display.dataset.rendered = "true";
}

function paintNormal(
  display: HTMLCanvasElement,
  native: HTMLCanvasElement,
  data: RenderPixels,
  shown: number,
  scale: number,
  cssWidth: number,
  background: readonly [number, number, number, number],
): void {
  if (!Number.isInteger(shown) || shown <= 0 || shown > data.height) throw new Error("Invalid shown height.");
  blit(native, data);
  // Exact-mode leftovers must not survive a display-mode switch: clear the
  // pixel-snapping transform and the reserved viewport height together.
  display.style.transform = "";
  display.style.position = "";
  display.style.transformOrigin = "";
  display.style.left = "";
  display.style.top = "";
  const parent = display.parentElement;
  if (parent) parent.style.height = "auto";
  // Backing width commits only with a validated paint, never ahead of an
  // awaited render, so pending or stale work cannot resize the live canvas.
  if (cssWidth > 0 && display.width !== cssWidth) {
    display.width = cssWidth;
    display.style.width = `${cssWidth}px`;
  }
  const height = Math.min(16384, Math.max(1, shown * scale));
  if (display.height !== height) {
    display.height = height;
    display.style.height = `${height}px`;
  }
  commitDisplay(display, background, data.width * scale, shown * scale, (dctx) => {
    dctx.drawImage(native, 0, 0, data.width, shown, 0, 0, data.width * scale, shown * scale);
  });
  display.style.width = `${display.width}px`;
  display.style.height = `${display.height}px`;
}

function paintExact(
  display: HTMLCanvasElement,
  native: HTMLCanvasElement,
  data: RenderPixels,
  shown: number,
  mag: number,
  background: readonly [number, number, number, number],
): void {
  if (!Number.isInteger(shown) || shown <= 0 || shown > data.height) throw new Error("Invalid shown height.");
  if (!Number.isInteger(mag) || mag < 1) throw new Error("Invalid magnification.");
  const ratio = deviceRatio();
  blit(native, data);
  const backing = backingSize(data.width, shown, mag);
  if (display.width !== backing.width) display.width = backing.width;
  if (display.height !== backing.height) display.height = backing.height;
  display.style.width = `${backing.width}px`;
  display.style.height = `${backing.height}px`;
  const parent = display.parentElement;
  if (parent) parent.style.height = `${cssSize(backing.height, ratio) + 1 + 1 / ratio}px`;
  display.style.position = "relative";
  display.style.transformOrigin = "0 0";
  // Snap from a fresh layout origin: clear stale placement before measuring
  // so repeated renders cannot accumulate offsets across zoom, mode, resize
  // or DPR changes.
  display.style.transform = "";
  display.style.left = "0px";
  display.style.top = "0px";
  const rect = display.getBoundingClientRect();
  display.style.left = `${Math.ceil(rect.left) - rect.left}px`;
  display.style.top = `${Math.ceil(rect.top) - rect.top}px`;
  const snapped = display.getBoundingClientRect();
  const { dx, dy } = snapTranslation(snapped.left, snapped.top, ratio);
  display.style.transform = `translate(${dx}px, ${dy}px) scale(${1 / ratio})`;
  commitDisplay(display, background, backing.width, backing.height, (dctx) => {
    dctx.drawImage(native, 0, 0, data.width, shown, 0, 0, backing.width, backing.height);
  });
}

interface Measured {
  width: number;
  estimate: number;
  cap: number;
  keyExtra: unknown;
  cssW: number;
  mag: number;
}

function lineCount(text: string): number {
  return text.split(/\r\n|\r|\n/).length;
}

interface RenderHookOptions {
  service: RendererService | null;
  session: number;
  available: boolean | null;
  enabled: boolean;
  fontId: string;
  text: string;
  sizePx: number;
  axes: Record<string, number>;
  profile: OutputProfile;
  role: RendererRole;
  spacing: number;
  kerning: boolean;
  stemFitting: StemFitting;
  zoom: number;
  mode: FontCanvasMode;
  palette?: readonly RGBA[];
  debounceMs: number;
  exposeFullHeight: boolean;
  clearOnError: boolean;
  debugIdentity?: (measuredWidth: number) => Record<string, unknown>;
  onPaint?: (diagnostics: FontCanvasDiagnostics) => void;
  onError?: (message: string, info: { renderer: RendererRole }) => void;
}

// Request scheduling, dedupe, two-pass layout resolution and per-consumer
// stale-result protection for one mounted canvas. Identity covers the
// renderer session and font; disabling resets identity so re-enabling
// re-renders with unchanged inputs. Layout effects close the stale-result
// window around committed input changes: invalidation runs before any async
// completion can be delivered.
function useFontRender(options: RenderHookOptions): {
  viewportRef: React.RefObject<HTMLDivElement | null>;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
} {
  const viewportRef = React.useRef<HTMLDivElement | null>(null);
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const nativeRef = React.useRef<HTMLCanvasElement | null>(null);
  const schedulerRef = React.useRef<RenderScheduler | null>(null);
  if (!schedulerRef.current) schedulerRef.current = new RenderScheduler();
  const [measureTick, setMeasureTick] = React.useState(0);
  const textRef = React.useRef(options.text);
  const outcomeRef = React.useRef(options);

  const {
    service, session, available, enabled, fontId, text, sizePx, axes, profile, role,
    spacing, kerning, stemFitting, zoom, mode, palette, debounceMs,
  } = options;
  const active = enabled && service !== null && available === true;

  const measure = (): Measured | null => {
    const viewport = viewportRef.current;
    if (!viewport) return null;
    const ratio = deviceRatio();
    if (mode === "exact") {
      const gutter = 1 + 1 / ratio;
      const cssW = viewport.clientWidth - gutter;
      if (cssW <= 0) return null;
      const mag = magnification(zoom, ratio);
      const width = nativeWidthFor(cssW, mag, ratio);
      const cap = nativeHeightCap(width, mag);
      const estimate = Math.min(cap, Math.max(1, lineCount(text) * Math.ceil(sizePx * 2)));
      return { width, estimate, cap, keyExtra: { cssW, dpr: ratio, mag }, cssW, mag };
    }
    const cssW = viewport.clientWidth;
    if (cssW <= 0) return null;
    const width = logicalBounds(cssW, zoom);
    const cap = nativeCap(width);
    const estimate = Math.min(cap, Math.max(1, lineCount(text) * Math.ceil(sizePx * 2)));
    return { width, estimate, cap, keyExtra: { displayW: cssW }, cssW, mag: zoom };
  };

  React.useLayoutEffect(() => {
    // Commit the latest callbacks here, not during render, so an abandoned
    // concurrent render cannot relabel old pixels with speculative values.
    outcomeRef.current = options;
    const scheduler = schedulerRef.current;
    if (!scheduler) return;
    if (!active) {
      scheduler.cancel();
      return;
    }
    const measured = measure();
    if (!measured) {
      // A zero-width (hidden) viewport cannot produce a request: invalidate
      // pending work so it cannot paint for a geometry that no longer holds.
      scheduler.cancel();
      return;
    }
    if (!service) return;
    const current = service;
    const base = {
      text, sizePx, axes, profile, width: measured.width,
      role, letterSpacingPx: spacing, kerning, stemFitting,
      palette,
    };
    const specForHeight = (height: number): RenderSpec =>
      toRenderSpec({ ...base, height });
    // Invalid colors never reach the scheduler: report through onError and
    // reset identity so a valid correction re-renders without remounting.
    let firstSpec: RenderSpec;
    let key: string;
    try {
      firstSpec = specForHeight(measured.estimate);
      key = buildRequestKey({
        session,
        fontId,
        mode,
        zoom,
        width: measured.width,
        extra: measured.keyExtra,
        spec: firstSpec,
      });
    } catch (error) {
      scheduler.cancel();
      const message = error instanceof Error ? error.message : String(error ?? "");
      outcomeRef.current.onError?.(message, { renderer: role });
      return;
    }
    const paintBackground = firstSpec.background;
    const textChanged = text !== textRef.current;
    textRef.current = text;
    const cssWidth = Math.round(measured.cssW);
    const mag = measured.mag;
    const paintMode = mode;
    const paintZoom = zoom;
    scheduler.request({
      key,
      fontId,
      estimate: measured.estimate,
      cap: measured.cap,
      specForHeight,
      contentHeight: layoutHeight,
      debounceMs,
      immediate: !textChanged,
      nextToken: () => current.nextToken(),
      render: (id, token, spec) => current.render(id, token, spec),
      onPaint: ({ data, fullHeight, shown, truncated }) => {
        const display = canvasRef.current;
        if (!display) return;
        const native = nativeRef.current ?? document.createElement("canvas");
        nativeRef.current = native;
        if (paintMode === "exact") {
          paintExact(display, native, data, shown, mag, paintBackground);
        } else {
          paintNormal(display, native, data, shown, paintZoom, cssWidth, paintBackground);
        }
        const outcome = outcomeRef.current;
        const identity = outcome.debugIdentity?.(measured.width);
        if (identity !== undefined) display.dataset.renderKey = JSON.stringify(identity);
        if (outcome.exposeFullHeight) display.dataset.fullHeight = String(fullHeight);
        outcome.onPaint?.({
          missing: data.layout?.missing_codepoints?.length ?? 0,
          fullHeight,
          truncated,
        });
      },
      onError: (error: unknown) => {
        const peer = outcomeRef.current;
        const display = canvasRef.current;
        if (display && peer.clearOnError) clearDisplay(display);
        const message = error instanceof Error ? error.message : String(error ?? "");
        peer.onError?.(message, { renderer: role });
      },
    });
  }, [
    service, session, available, active, measureTick,
    fontId, text, sizePx, axes, profile, role, spacing, kerning, stemFitting,
    zoom, mode, palette, debounceMs,
  ]);

  React.useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const observer = new ResizeObserver(() => setMeasureTick((tick) => tick + 1));
    observer.observe(viewport);
    const onDisplay = (): void => setMeasureTick((tick) => tick + 1);
    let ratio: number | null = null;
    let query: MediaQueryList | null = null;
    const watch = (): void => {
      const next = deviceRatio();
      if (next === ratio) return;
      query?.removeEventListener("change", watch);
      ratio = next;
      query = window.matchMedia(`(resolution: ${next}dppx)`);
      query.addEventListener("change", watch);
      if (ratio !== null) onDisplay();
    };
    watch();
    window.addEventListener("resize", onDisplay);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", onDisplay);
      query?.removeEventListener("change", watch);
    };
  }, [mode]);

  React.useEffect(() => {
    const scheduler = schedulerRef.current;
    return () => scheduler?.cancel();
  }, []);

  return { viewportRef, canvasRef };
}

// Shared font rendering canvas: viewport measurement, resize/DPR tracking
// and normal vs pixel-accurate painting over one RenderScheduler per mounted
// canvas, so distinct consumers of the same font stay independent. It knows
// display scaling, never consumer identity: card layout stays in the wrapper.
export function FontCanvas(props: FontCanvasProps): React.JSX.Element {
  const { service, session, available } = useRenderer();
  const { viewportRef, canvasRef } = useFontRender({
    service,
    session,
    available,
    enabled: props.ready,
    fontId: props.fontId,
    text: props.text,
    sizePx: props.sizePx,
    axes: props.axes,
    profile: props.profile,
    role: props.role,
    spacing: props.spacing,
    kerning: props.kerning,
    stemFitting: props.stemFitting,
    zoom: props.zoom,
    mode: props.mode,
    palette: props.palette,
    debounceMs: props.debounceMs,
    exposeFullHeight: props.exposeFullHeight ?? false,
    clearOnError: props.clearOnError ?? false,
    debugIdentity: props.debugIdentity,
    onPaint: props.onPaint,
    onError: props.onError,
  });

  return (
    <div ref={viewportRef} {...props.viewportProps}>
      <canvas ref={canvasRef} {...props.canvasProps}>
        {props.canvasFallback}
      </canvas>
    </div>
  );
}
