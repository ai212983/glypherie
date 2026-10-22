import { userError } from "../../user-error";
import * as React from "react";
import type { RGBA } from "../../renderer/renderer-types.js";
import type { LibraryBaseSize } from "../library/preferences.js";
import { BUNDLED_FONTS } from "../../fonts/bundled-fonts";
import { paletteCoverage, tintCoverage } from "./gray-levels";

const previewFontLoads = new Map<string, Promise<FontFace>>();

function loadPreviewFont(fileName: string): Promise<FontFace> {
  const cached = previewFontLoads.get(fileName);
  if (cached) return cached;
  const descriptor = BUNDLED_FONTS.find((entry) => entry.fileName === fileName);
  if (!descriptor) return Promise.reject(new Error("The preview font is unavailable."));
  // Register the canonical bundled asset independently of library bootstrap.
  // https://www.w3.org/TR/css-font-loading-3/#fontface-interface
  const face = new FontFace(`palette-preview-${fileName}`, `url(${JSON.stringify(descriptor.url)})`);
  const pending = face.load().then((loaded) => {
    document.fonts.add(loaded);
    return loaded;
  }).catch((failure: unknown) => {
    previewFontLoads.delete(fileName);
    throw failure;
  });
  previewFontLoads.set(fileName, pending);
  return pending;
}

const FRAME_INSET = 12;
const LINE_HEIGHT_RATIO = 34 / 24;

interface RasterPreviewProps {
  text: string;
  levels: readonly number[];
  zoom: number;
  baseSize: LibraryBaseSize;
  compact?: boolean;
  fontFileName?: string;
  display?: { paper: RGBA; ink: RGBA };
  header?: React.ReactNode;
  footer?: React.ReactNode;
}

export function RasterPreview({ text, levels, zoom, baseSize, compact = false, fontFileName = "Roboto.ttf", display, header, footer }: RasterPreviewProps): React.JSX.Element {
  const viewport = React.useRef<HTMLDivElement | null>(null);
  const canvas = React.useRef<HTMLCanvasElement | null>(null);
  const [width, setWidth] = React.useState(0);
  const [coverage, setCoverage] = React.useState<ImageData | null>(null);
  const [error, setError] = React.useState("");
  const inset = compact ? 0 : FRAME_INSET;
  const nativeWidth = Math.max(32, Math.floor((width - inset * 2) / zoom));
  const font = `400 ${baseSize}px "palette-preview-${fontFileName}"`;
  const lineHeight = baseSize * LINE_HEIGHT_RATIO;
  const paperPixel = display && levels.length > 0
    ? tintCoverage(new Uint8ClampedArray([levels[0] ?? 0, 0, 0, 255]), display.paper, display.ink)
    : null;
  const paperCss = paperPixel
    ? `rgb(${paperPixel[0]} ${paperPixel[1]} ${paperPixel[2]})`
    : `rgb(${levels[0]} ${levels[0]} ${levels[0]})`;

  React.useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const measure = (): void => setWidth(element.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    if (width === 0) return;
    let cancelled = false;
    setError("");
    // Native-size browser text alpha supplies the mask. This is a local
    // palette specimen, independent of the generator's fitting/scanners.
    // https://html.spec.whatwg.org/multipage/canvas.html#drawing-text-to-the-bitmap
    void loadPreviewFont(fontFileName).then(() => {
      if (cancelled) return;
      const source = document.createElement("canvas");
      source.width = nativeWidth;
      const context = source.getContext("2d", { willReadFrequently: true });
      if (!context) throw new Error("The rasterized preview is unavailable.");
      context.font = font;
      // Both previews fit the actual text bounds around the same baselines.
      // Include blank line boxes so intentional whitespace survives the trim.
      // https://html.spec.whatwg.org/multipage/canvas.html#textmetrics
      context.textBaseline = "top";
      const lines = [""];
      for (const character of text.replace(/\r\n?/g, "\n")) {
        const last = lines.length - 1;
        if (character === "\n") lines.push("");
        else if (lines[last] && context.measureText(lines[last] + character).width > nativeWidth) lines.push(character);
        else lines[last] += character;
      }
      let paintedTop = Infinity;
      let paintedBottom = -Infinity;
      for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index] ?? "";
        const top = index * lineHeight;
        const metrics = context.measureText(line);
        const blank = line.trim() === "";
        paintedTop = Math.min(paintedTop, blank ? top : top - metrics.actualBoundingBoxAscent);
        paintedBottom = Math.max(paintedBottom, blank ? top + lineHeight : top + metrics.actualBoundingBoxDescent);
      }
      const origin = Math.floor(paintedTop);
      source.height = Math.max(1, Math.ceil(paintedBottom) - origin);
      // Resizing clears the context state; draw once on transparent pixels
      // before mapping its alpha to the palette's discrete coverage indices.
      context.font = font;
      context.textBaseline = "top";
      context.fillStyle = "black";
      lines.forEach((line, index) => context.fillText(line, 0, index * lineHeight - origin));
      setCoverage(context.getImageData(0, 0, source.width, source.height));
    }).catch((failure: unknown) => {
      if (cancelled) return;
      setCoverage(null);
      setError(userError(failure, "Preview unavailable."));
    });
    return () => { cancelled = true; };
  }, [text, nativeWidth, width, font, fontFileName, lineHeight]);

  React.useEffect(() => {
    const output = canvas.current;
    if (!output) return;
    delete output.dataset.rendered;
    if (!coverage) { output.width = 0; output.height = 0; return; }
    output.width = coverage.width;
    output.height = coverage.height;
    const context = output.getContext("2d");
    if (!context) { setError("Preview unavailable."); return; }
    const pixels = paletteCoverage(coverage.data, levels);
    const displayPixels = display ? tintCoverage(pixels, display.paper, display.ink) : pixels;
    context.putImageData(new ImageData(displayPixels, coverage.width, coverage.height), 0, 0);
    output.dataset.rendered = "true";
  }, [coverage, levels, display]);

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {error && <p role="alert" className="m-0 text-sm">{error}</p>}
      <div ref={viewport} className={compact ? "min-w-0 overflow-hidden" : "min-w-0 overflow-hidden rounded-lg border border-border"} style={{ backgroundColor: paperCss }}>
        {header}
        <canvas
          ref={canvas} role="img" aria-label={`Rasterized text preview: ${text || "blank"}`} aria-hidden={compact ? true : undefined}
          className="block [image-rendering:pixelated]"
          style={{ width: coverage ? coverage.width * zoom : 0, height: coverage ? coverage.height * zoom : 0, marginBlock: compact ? 0 : 32, marginInline: inset }}
        >{text || "Blank text preview"}</canvas>
        {footer}
      </div>
    </div>
  );
}
