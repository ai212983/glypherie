import type { OutputProfile, RGBA } from "../../renderer/renderer-types.js";

export type CanvasPaletteId = "black-white" | "warm-paper" | "cool-paper";

export interface CanvasPalette {
  id: CanvasPaletteId;
  name: string;
  paper: RGBA;
  ink: RGBA;
  paperCss: string;
  inkCss: string;
}

const BLACK_WHITE: CanvasPalette = {
  id: "black-white",
  name: "Neutral",
  paper: [255, 255, 255, 255],
  ink: [0, 0, 0, 255],
  paperCss: "#ffffff",
  inkCss: "#000000",
};

const WARM_PAPER: CanvasPalette = {
  id: "warm-paper",
  name: "Warm",
  paper: [244, 236, 220, 255],
  ink: [26, 24, 21, 255],
  paperCss: "#f4ecdc",
  inkCss: "#1a1815",
};

const COOL_PAPER: CanvasPalette = {
  id: "cool-paper",
  name: "Cool",
  paper: [232, 240, 248, 255],
  ink: [27, 42, 58, 255],
  paperCss: "#e8f0f8",
  inkCss: "#1b2a3a",
};

export const CANVAS_PALETTES: readonly CanvasPalette[] = [BLACK_WHITE, WARM_PAPER, COOL_PAPER];

export const DEFAULT_CANVAS_PALETTE_ID: CanvasPaletteId = "black-white";

export function isCanvasPaletteId(value: unknown): value is CanvasPaletteId {
  return value === "black-white" || value === "warm-paper" || value === "cool-paper";
}

export function canvasPaletteById(id: CanvasPaletteId): CanvasPalette {
  return CANVAS_PALETTES.find((palette) => palette.id === id) ?? BLACK_WHITE;
}

const PALETTE_REFS: Record<CanvasPaletteId, { normal: readonly RGBA[]; inverse: readonly RGBA[] }> = {
  "black-white": {
    normal: [BLACK_WHITE.paper, BLACK_WHITE.ink],
    inverse: [BLACK_WHITE.ink, BLACK_WHITE.paper],
  },
  "warm-paper": {
    normal: [WARM_PAPER.paper, WARM_PAPER.ink],
    inverse: [WARM_PAPER.ink, WARM_PAPER.paper],
  },
  "cool-paper": {
    normal: [COOL_PAPER.paper, COOL_PAPER.ink],
    inverse: [COOL_PAPER.ink, COOL_PAPER.paper],
  },
};

export function libraryPalette(id: CanvasPaletteId, inverse: boolean, profile: OutputProfile = "mono_1bit"): readonly RGBA[] {
  if (profile === "gray_3bit") {
    const ramp = GRAY_RAMPS[id] ?? GRAY_RAMPS["black-white"];
    return inverse ? ramp.inverse : ramp.normal;
  }
  const pair = PALETTE_REFS[id] ?? PALETTE_REFS["black-white"];
  return inverse ? pair.inverse : pair.normal;
}

function buildGrayRamp(paper: RGBA, ink: RGBA): readonly RGBA[] {
  const ramp: RGBA[] = [];
  for (let step = 0; step < 8; step += 1) {
    const share = step / 7;
    ramp.push([
      Math.round(paper[0] + (ink[0] - paper[0]) * share),
      Math.round(paper[1] + (ink[1] - paper[1]) * share),
      Math.round(paper[2] + (ink[2] - paper[2]) * share),
      255,
    ]);
  }
  return ramp;
}

function grayPair(paper: RGBA, ink: RGBA): { normal: readonly RGBA[]; inverse: readonly RGBA[] } {
  const normal = buildGrayRamp(paper, ink);
  return { normal, inverse: [...normal].reverse() };
}

const GRAY_RAMPS: Record<CanvasPaletteId, { normal: readonly RGBA[]; inverse: readonly RGBA[] }> = {
  "black-white": grayPair(BLACK_WHITE.paper, BLACK_WHITE.ink),
  "warm-paper": grayPair(WARM_PAPER.paper, WARM_PAPER.ink),
  "cool-paper": grayPair(COOL_PAPER.paper, COOL_PAPER.ink),
};

export interface CanvasFrame {
  paperCss: string;
  inkCss: string;
  borderCss: string;
  mutedCss: string;
  dividerCss: string;
}

function mixHex(inkCss: string, paperCss: string, inkShare: number): string {
  const channels = [1, 3, 5].map((at) => {
    const ink = parseInt(inkCss.slice(at, at + 2), 16);
    const paper = parseInt(paperCss.slice(at, at + 2), 16);
    return Math.round(ink * inkShare + paper * (1 - inkShare)).toString(16).padStart(2, "0");
  });
  return `#${channels.join("")}`;
}

export function libraryFrame(id: CanvasPaletteId, inverse: boolean): CanvasFrame {
  const palette = canvasPaletteById(id);
  const paperCss = inverse ? palette.inkCss : palette.paperCss;
  const inkCss = inverse ? palette.paperCss : palette.inkCss;
  if (id === "warm-paper" && !inverse) {
    return { paperCss, inkCss, borderCss: "#c8bfae", mutedCss: "#575249", dividerCss: "#dad0bd" };
  }
  return {
    paperCss,
    inkCss,
    borderCss: mixHex(inkCss, paperCss, 0.21),
    mutedCss: mixHex(inkCss, paperCss, 0.73),
    dividerCss: mixHex(inkCss, paperCss, 0.13),
  };
}
