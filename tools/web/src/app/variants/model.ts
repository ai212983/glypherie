import type { FontMetadata, StoredFont } from "../fonts/storage.ts";
import type {
  OutputProfile,
  RendererRole,
  StemFitting,
} from "../renderer/renderer-types.ts";
import { MAX_TEXT_LENGTH } from "../renderer/render-spec.ts";

export interface VariantSettings {
  sizePx: number;
  axes: Record<string, number>;
  letterSpacingPx: number;
  profile: OutputProfile;
  kerning: boolean;
  stemFitting: StemFitting;
  renderer: RendererRole;
}

export interface FontVariant {
  id: string;
  fontId: string;
  name: string;
  settingsVersion: 1;
  settings: VariantSettings;
  sampleText: string;
  revision: number;
  createdAt: number;
  updatedAt: number;
}

/** Editable persisted fields of one variant; the editor draft shape. */
export type VariantDraft = Pick<FontVariant, "name" | "settings" | "sampleText">;

// Bounds mirror the preview controls and render contracts: size clamps to
// 1..512 (SpecimenControls), spacing to -2..4 (snapshot-codec), sample text
// to MAX_TEXT_LENGTH (render-spec).
export const VARIANT_SIZE_MIN = 1;
export const VARIANT_SIZE_MAX = 512;
export const VARIANT_SPACING_MIN = -2;
export const VARIANT_SPACING_MAX = 4;
export const VARIANT_NAME_MAX_LENGTH = 120;
export const VARIANT_SAMPLE_TEXT_MAX_LENGTH = MAX_TEXT_LENGTH;

const PROFILES: readonly OutputProfile[] = ["mono_1bit", "gray_3bit"];
const STEM_FITTINGS: readonly StemFitting[] = ["font_hints_first", "upstream_mono"];
const RENDERERS: readonly RendererRole[] = ["baseline", "reference", "candidate"];

export type VariantStorageErrorCode =
  | "conflict"
  | "not-found"
  | "font-not-found"
  | "invalid-settings"
  | "invalid-input"
  | "blocked"
  | "quota-exceeded"
  | "unavailable";

export class VariantStorageError extends Error {
  readonly code: VariantStorageErrorCode;
  constructor(code: VariantStorageErrorCode, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "VariantStorageError";
    this.code = code;
  }
}

// Every axis in the font's own metadata (hidden axes included) contributes
// its default; static fonts (no axes) yield axes={}. No global axis list.
export function defaultVariantSettings(font: StoredFont): VariantSettings {
  const axes: Record<string, number> = {};
  for (const axis of font.metadata?.axes ?? []) {
    if (typeof axis.tag === "string" && Number.isFinite(axis.default)) {
      axes[axis.tag] = axis.default;
    }
  }
  return {
    sizePx: 16,
    axes,
    letterSpacingPx: 0,
    profile: "mono_1bit",
    kerning: true,
    stemFitting: "font_hints_first",
    renderer: "candidate",
  };
}

function fail(why: string): never {
  throw new VariantStorageError("invalid-settings", `Refusing to store malformed variant settings: ${why}.`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Saved settings must carry the font's complete axis set: unknown tags,
// missing tags, NaN, and out-of-range values are rejected.
export function validateVariantSettings(settings: VariantSettings, metadata: FontMetadata): void {
  if (!isRecord(settings)) fail("settings must be an object");
  const typed = settings as VariantSettings;
  if (typeof typed.sizePx !== "number" || !Number.isFinite(typed.sizePx)) fail("sizePx must be a finite number");
  if (typed.sizePx < VARIANT_SIZE_MIN || typed.sizePx > VARIANT_SIZE_MAX) {
    fail(`sizePx must sit within ${VARIANT_SIZE_MIN}..${VARIANT_SIZE_MAX}`);
  }
  if (typeof typed.letterSpacingPx !== "number" || !Number.isFinite(typed.letterSpacingPx)) {
    fail("letterSpacingPx must be a finite number");
  }
  if (typed.letterSpacingPx < VARIANT_SPACING_MIN || typed.letterSpacingPx > VARIANT_SPACING_MAX) {
    fail(`letterSpacingPx must sit within ${VARIANT_SPACING_MIN}..${VARIANT_SPACING_MAX}`);
  }
  if (!(PROFILES as readonly string[]).includes(typed.profile)) fail("profile must be a known output profile");
  if (typeof typed.kerning !== "boolean") fail("kerning must be a boolean");
  if (!(STEM_FITTINGS as readonly string[]).includes(typed.stemFitting)) {
    fail("stemFitting must be a known stem-fitting strategy");
  }
  if (!(RENDERERS as readonly string[]).includes(typed.renderer)) fail("renderer must be a known renderer role");
  if (!metadata || !Array.isArray(metadata.axes)) fail("font metadata must carry an axes array");
  if (!isRecord(typed.axes)) fail("axes must be an object");
  const expected = new Map<string, { min: number; max: number }>();
  for (const axis of metadata.axes) {
    if (!axis || typeof axis.tag !== "string") fail("every axis must carry a string tag");
    expected.set(axis.tag, { min: axis.min, max: axis.max });
  }
  const actual = typed.axes as Record<string, unknown>;
  for (const tag of Object.keys(actual)) {
    if (!expected.has(tag)) fail(`unknown axis "${tag}" for this font`);
  }
  for (const [tag, bounds] of expected) {
    const value = actual[tag];
    if (typeof value !== "number" || !Number.isFinite(value)) fail(`axis "${tag}" must be a finite number`);
    if (value < bounds.min || value > bounds.max) fail(`axis "${tag}" must sit within its font range`);
  }
}

export function validateVariantName(name: string): void {
  if (typeof name !== "string" || name.trim() === "") {
    throw new VariantStorageError("invalid-input", "Variant names must be non-empty text.");
  }
  if (name.length > VARIANT_NAME_MAX_LENGTH) {
    throw new VariantStorageError(
      "invalid-input",
      `Variant names must stay within ${VARIANT_NAME_MAX_LENGTH} characters.`,
    );
  }
}

export function validateVariantSampleText(sampleText: string): void {
  if (typeof sampleText !== "string") {
    throw new VariantStorageError("invalid-input", "Variant sample text must be a string.");
  }
  if (sampleText.length > VARIANT_SAMPLE_TEXT_MAX_LENGTH) {
    throw new VariantStorageError(
      "invalid-input",
      `Variant sample text must stay within ${VARIANT_SAMPLE_TEXT_MAX_LENGTH} characters.`,
    );
  }
}
