import type { RendererService } from "./renderer-types.js";
import type { FontMetadata } from "../fonts/storage.js";
import type { RenderSpec } from "./renderer-types.js";
import type { RenderPixels } from "./client.js";

// Deterministic stand-in for the worker renderer, for stories and browser
// inspection of canvas orchestration only. It produces synthetic pixels (no
// font binaries, no WASM build, no external fonts): band heights follow the
// requested text lines and pixel size, so layout, scaling and lifecycle
// behavior can be exercised without claiming anything about the real
// renderer's optics.
export type FixtureScenario = "ok" | "missing-glyphs" | "error" | "unavailable";

export interface FixtureRendererOptions {
  scenario?: FixtureScenario;
  latencyMs?: number;
  lineHeight?: number;
  events?: FixtureRendererEvents;
}

type Channels = readonly [number, number, number, number];

// Synthetic source-over matching the native composite (surface.rs): coverage
// scales source alpha in floating point with no intermediate rounding, the
// background contributes by its own alpha, and only the final bytes round.
export function compositeSourceOver(
  src: Channels,
  dst: Channels,
  coverage: number,
): [number, number, number, number] {
  const sa = (src[3] / 255) * coverage;
  const da = dst[3] / 255;
  const outa = sa + da * (1 - sa);
  if (outa <= 0) return [0, 0, 0, 0];
  const blend = (s: number, d: number): number => (s * sa + d * da * (1 - sa)) / outa;
  return [Math.round(blend(src[0], dst[0])), Math.round(blend(src[1], dst[1])), Math.round(blend(src[2], dst[2])), Math.round(outa * 255)];
}

// Lifecycle observations for mounted harness tests: construction,
// termination and every render request the instance serves.
export interface FixtureRendererEvents {
  constructed?: () => void;
  terminated?: () => void;
  renderCalled?: (call: {
    fontId: string;
    token: number;
    text: string;
    width: number;
    height: number;
    foreground: readonly [number, number, number, number];
    background: readonly [number, number, number, number];
    palette: ReadonlyArray<readonly [number, number, number, number]> | null;
  }) => void;
  loadCalled?: (call: { fontId: string }) => void;
}

function synthesizeFixturePixels(
  spec: RenderSpec,
  lineHeight: number,
  scenario: FixtureScenario,
): RenderPixels {
  const width = Math.min(4096, Math.max(1, Math.ceil(spec.width)));
  const height = Math.min(4096, Math.max(1, Math.ceil(spec.height)));
  // Empty text lays out zero lines and paints a blank canvas.
  const lines = spec.text === "" ? [] : spec.text.split(/\r\n|\r|\n/);
  const buffer = new ArrayBuffer(width * height * 4);
  const view = new Uint8ClampedArray(buffer);
  // Synthetic coverage demo, mirroring the native contract: the canvas
  // starts as the wire background; band rows cycle coverage levels, level
  // 0 leaves the background untouched, the default foreground takes
  // coverage level/(levels-1), and explicit entries take coverage 1.
  const background = spec.background ?? [255, 255, 255, 255];
  for (let i = 0; i < view.length; i += 4) {
    view[i] = background[0];
    view[i + 1] = background[1];
    view[i + 2] = background[2];
    view[i + 3] = background[3];
  }
  const foreground = spec.foreground ?? [36, 40, 43, 255];
  const palette = spec.palette ?? null;
  const levels = palette !== null ? palette.length : 1 << (spec.output_bits ?? 1);
  const size = Math.max(1, spec.size_px);
  lines.forEach((line, index) => {
    const top = Math.min(height, index * lineHeight);
    const band = Math.min(height - top, Math.max(1, Math.floor(lineHeight * 0.6)));
    const inkCols = Math.min(width - 8, Math.max(0, 8 + Math.floor(line.length * size * 0.6)));
    for (let row = 0; row < band; row += 1) {
      const level = row % Math.max(1, levels);
      if (level === 0) continue;
      const explicit = palette !== null ? palette[level % palette.length] : undefined;
      const color = explicit !== undefined
        ? compositeSourceOver(explicit, background, 1)
        : compositeSourceOver(foreground, background, level / Math.max(1, levels - 1));
      for (let col = 4; col < 4 + inkCols; col += 1) {
        const at = ((top + row) * width + col) * 4;
        view[at] = color[0];
        view[at + 1] = color[1];
        view[at + 2] = color[2];
        view[at + 3] = color[3];
      }
    }
  });
  return {
    width,
    height,
    pixels: buffer,
    layout: {
      lines: lines.map(() => ({ height_px: lineHeight })),
      missing_codepoints: scenario === "missing-glyphs" && lines.length > 0 ? [65, 66] : [],
    },
  };
}

function fixtureMetadata(): FontMetadata {
  return {
    names: { family: "Fixture", style: null, full: "Fixture Regular", postscript: null, version: null, copyright: null, manufacturer: null, designer: null, description: null, vendor_url: null, designer_url: null, license: null, license_url: null },
    axes: [],
    kerning: { horizontal: false, vertical: false, sources: [] },
    style: { slope: "upright", weight_class: 400, width_class: 5, italic_angle: 0 },
    classification: { family_class: 0, panose: [2, 11, 5, 3, 3, 4, 3, 2, 2, 4], monospaced: false },
    coverage: { character_count: 1, ranges: [[65, 65]] },
    declared_unicode_ranges: [1, 0, 0, 0],
  };
}

export function createFixtureRenderer(options: FixtureRendererOptions = {}): RendererService {
  const scenario = options.scenario ?? "ok";
  const latencyMs = options.latencyMs ?? 5;
  const lineHeight = options.lineHeight ?? 24;
  const events = options.events;
  let token = 0;
  let terminated = false;
  events?.constructed?.();

  const checkLive = (): void => {
    if (terminated) throw new Error("Worker terminated.");
  };

  return {
    async ping(): Promise<{ available: boolean }> {
      await new Promise((resolve) => setTimeout(resolve, latencyMs));
      if (scenario === "unavailable") throw new Error("Fixture renderer unavailable (synthetic).");
      checkLive();
      return { available: true };
    },
    async inspect(): Promise<FontMetadata> {
      checkLive();
      return fixtureMetadata();
    },
    async load(fontId: string): Promise<void> {
      events?.loadCalled?.({ fontId });
      await new Promise((resolve) => setTimeout(resolve, latencyMs));
      checkLive();
    },
    async unload(): Promise<void> {
      checkLive();
    },
    async kerning(): Promise<unknown> {
      checkLive();
      return { pairs: [], skipped_pairs: 0 };
    },
    async exportPlaydate(): Promise<ArrayBuffer> {
      checkLive();
      throw new Error("Playdate export requires the real font renderer.");
    },
    nextToken(): number {
      token += 1;
      return token;
    },
    async render(fontId: string, renderToken: number, spec: RenderSpec): Promise<{
      token: number;
      dropped: boolean;
      pixels: RenderPixels;
    }> {
      events?.renderCalled?.({
        fontId,
        token: renderToken,
        text: spec.text,
        width: spec.width,
        height: spec.height,
        foreground: [...(spec.foreground ?? [36, 40, 43, 255])],
        background: [...(spec.background ?? [255, 255, 255, 255])],
        palette: spec.palette ? spec.palette.map((entry) => [...entry] as [number, number, number, number]) : null,
      });
      await new Promise((resolve) => setTimeout(resolve, latencyMs));
      checkLive();
      if (scenario === "error") throw new Error("Fixture render failure (synthetic error path).");
      return {
        token: renderToken,
        dropped: false,
        pixels: synthesizeFixturePixels(spec, lineHeight, scenario),
      };
    },
    terminate(): void {
      terminated = true;
      events?.terminated?.();
    },
  };
}
