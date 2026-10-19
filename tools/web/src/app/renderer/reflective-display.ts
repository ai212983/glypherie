// cspell:words RLCD TEMPERA Soldered Waveshare Inkplate Playdate uncalibrated RRGGBB
// Appearance-only palette provider for reflective monochrome displays. A
// device preset plus optional paper/ink colors maps to an opaque two-entry
// mono palette (paper 0, ink 1). No lighting simulation: the defaults are
// carried-forward illustrative preview choices, not measured device colors.
import type { RGBA } from "./renderer-types.js";

export type ReflectiveDeviceId = "waveshare-esp32-s3-rlcd-4-2" | "inkplate-4tempera" | "playdate";

export interface ReflectiveDevicePreset {
  readonly id: ReflectiveDeviceId;
  readonly label: string;
  // Published native frame; the preview shows the app specimen layout, not this frame.
  readonly nativeWidthPx: number;
  readonly nativeHeightPx: number;
  readonly sources: readonly string[];
  // Illustrative defaults, NOT manufacturer-specified or calibrated colors.
  readonly defaultPaper: string;
  readonly defaultInk: string;
}

export const REFLECTIVE_DEVICES: Record<ReflectiveDeviceId, ReflectiveDevicePreset> = {
  "waveshare-esp32-s3-rlcd-4-2": {
    id: "waveshare-esp32-s3-rlcd-4-2",
    label: "Waveshare ESP32-S3-RLCD-4.2",
    nativeWidthPx: 300,
    nativeHeightPx: 400,
    sources: ["https://docs.waveshare.com/ESP32-S3-RLCD-4.2"],
    defaultPaper: "#999999",
    defaultInk: "#282828",
  },
  "inkplate-4tempera": {
    id: "inkplate-4tempera",
    label: "Inkplate 4 TEMPERA",
    nativeWidthPx: 600,
    nativeHeightPx: 600,
    sources: [
      "https://docs.soldered.com/inkplate/4tempera/overview/",
      "https://docs.soldered.com/inkplate/4tempera/basics/basic-display-modes/",
    ],
    defaultPaper: "#999999",
    defaultInk: "#2D2D2D",
  },
  "playdate": {
    id: "playdate",
    label: "Playdate",
    nativeWidthPx: 400,
    nativeHeightPx: 240,
    sources: ["https://help.play.date/developer/designing-for-playdate/"],
    defaultPaper: "#686868",
    defaultInk: "#191919",
  },
};

export interface ReflectiveDisplayConfig {
  readonly device: ReflectiveDeviceId;
  // Opaque #RRGGBB colors; omitted means the device default.
  readonly paper?: string;
  readonly ink?: string;
}

// Per-field color origin: omitted resolves the device default.
export type PaletteOrigin = "device-default" | "custom";

export interface ReflectiveDisplayResult {
  readonly device: ReflectiveDevicePreset;
  // Normalized uppercase #RRGGBB.
  readonly paper: string;
  readonly ink: string;
  readonly origin: { readonly paper: PaletteOrigin; readonly ink: PaletteOrigin };
  // Opaque two-entry mono palette: paper is index 0, ink is index 1.
  readonly palette: readonly [paper: RGBA, ink: RGBA];
}

function fail(message: string): never {
  throw new Error(message);
}

// Strict opaque 6-digit hex (#RRGGBB per W3C CSS Color 4 §5.2); returns the
// uppercase-normalized form. Lowercase input is accepted and normalized.
export function normalizeHexColor(name: string, value: unknown): string {
  if (typeof value !== "string" || !/^#[0-9a-fA-F]{6}$/.test(value)) {
    fail(`Invalid reflective config: ${name} must be an opaque #RRGGBB color.`);
  }
  return (value as string).toUpperCase();
}

function hexToRgba(hex: string): RGBA {
  const digits = hex.slice(1);
  const rgba: RGBA = [
    Number.parseInt(digits.slice(0, 2), 16),
    Number.parseInt(digits.slice(2, 4), 16),
    Number.parseInt(digits.slice(4, 6), 16),
    255,
  ];
  return Object.freeze(rgba) as unknown as RGBA;
}

function resolveColor(
  name: string,
  value: string | undefined,
  fallback: string,
): { hex: string; origin: PaletteOrigin } {
  if (value === undefined) return { hex: fallback, origin: "device-default" };
  return { hex: normalizeHexColor(name, value), origin: "custom" };
}

export function computeReflectiveDisplay(config: ReflectiveDisplayConfig): ReflectiveDisplayResult {
  if (typeof config !== "object" || config === null) {
    fail("Invalid reflective config: expected a config object.");
  }
  // String own-key membership: dictionary lookup alone would accept
  // inherited keys such as "toString" or "constructor".
  if (typeof config.device !== "string" || !Object.hasOwn(REFLECTIVE_DEVICES, config.device)) {
    fail(`Invalid reflective config: unknown device ${String(config.device)}.`);
  }
  const device = REFLECTIVE_DEVICES[config.device as ReflectiveDeviceId];
  const paper = resolveColor("paper", config.paper, device.defaultPaper);
  const ink = resolveColor("ink", config.ink, device.defaultInk);
  return {
    device,
    paper: paper.hex,
    ink: ink.hex,
    origin: Object.freeze({ paper: paper.origin, ink: ink.origin }) as {
      readonly paper: PaletteOrigin;
      readonly ink: PaletteOrigin;
    },
    palette: Object.freeze([hexToRgba(paper.hex), hexToRgba(ink.hex)]) as unknown as
      readonly [paper: RGBA, ink: RGBA],
  };
}
