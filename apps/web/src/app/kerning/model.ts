export interface TypeFacetSettings {
  normalDistanceEm: number;
  intrusionToleranceEm: number;
  minimumDistanceEm: number;
  maxXExtremaOverlapEm: number;
}

/** Earlier saved variants carry only the first two controls. */
type TypeFacetPreference = Pick<TypeFacetSettings, "normalDistanceEm" | "intrusionToleranceEm"> &
  Partial<Pick<TypeFacetSettings, "minimumDistanceEm" | "maxXExtremaOverlapEm">>;

export type FontForgeSettings = Record<string, never>;

export interface HuHerschSettings {
  apertureDepthFactor: number;
  globalDepthFactor: number;
}

/** Published Hu/Hersch construction constants (US5768490A, transformations C/D). */
export const HU_HERSCH_DEFAULTS = {
  apertureDepthFactor: 0.21,
  globalDepthFactor: 0.25,
} as const;

/** Project bounds for the depth-to-height ratios; the patent supplies the
 * defaults, not these adjustment limits. */
export const HU_HERSCH_APERTURE_MIN = 0;
export const HU_HERSCH_APERTURE_MAX = 1;
export const HU_HERSCH_GLOBAL_MIN = 0;
export const HU_HERSCH_GLOBAL_MAX = 1;

/** Each method owns its settings; tracking remains outside kerning. */
export interface KerningSettingsMap {
  source: { enabled: boolean };
  typefacet: TypeFacetSettings;
  hu_hersch: HuHerschSettings;
  fontforge: FontForgeSettings;
}

export type KerningMethod = keyof KerningSettingsMap;
export type KerningState = { method: KerningMethod } & KerningSettingsMap;

/** Historical booleans and two-method values migrate on normalization. The retired
 * `strength` blend is rejected wherever it appears. */
export type KerningPreference = boolean | (
  Pick<KerningState, "method" | "source"> & { typefacet: TypeFacetPreference } &
  { hu_hersch?: Partial<HuHerschSettings> } &
  { fontforge?: FontForgeSettings }
);

export type KerningEdit = {
  [Method in KerningMethod]: { method: Method; settings: Method extends "typefacet" ? TypeFacetPreference : KerningSettingsMap[Method] }
}[KerningMethod];

export type KerningMethodRequest =
  | { method: "typefacet"; normal_distance_em: number; intrusion_tolerance_em: number; minimum_distance_em: number; max_x_extrema_overlap_em: number }
  | { method: "hu_hersch"; aperture_depth_factor: number; global_depth_factor: number }
  | { method: "fontforge" };

interface KerningMethodDescription {
  label: string;
  requiresExplicitPipeline: boolean;
  description: string;
}

/** Only methods compiled into the shared native/WASM renderer belong here. */
export const KERNING_METHODS = {
  source: {
    label: "Source", requiresExplicitPipeline: false,
    description: "Keeps the font's source kerning and fitted bearing corrections.",
  },
  typefacet: {
    label: "TypeFacet", requiresExplicitPipeline: true,
    description: "Manual optical spacing; adjust these parameters for the font.",
  },
  hu_hersch: {
    label: "Hu/Hersch", requiresExplicitPipeline: true,
    description: "Calibrates optical spacing to the font's reference alphabet density.",
  },
  fontforge: {
    label: "FontForge source-relative", requiresExplicitPipeline: true,
    description: "Targets each source pair's original optical separation after fitting.",
  },
} as const satisfies Record<KerningMethod, KerningMethodDescription>;

export function isKerningMethod(value: unknown): value is KerningMethod {
  return typeof value === "string" && Object.hasOwn(KERNING_METHODS, value);
}

export function assertNever(value: never): never {
  throw new Error(`Unknown kerning method: ${String(value)}`);
}

// TypeFacet's upstream manual parameters; these are not a font-specific fit.
// Hu/Hersch depths are the published US5768490A construction constants.
export function defaultKerningState(): KerningState {
  return {
    method: "source",
    source: { enabled: true },
    typefacet: { normalDistanceEm: 0.1, intrusionToleranceEm: 0.1, minimumDistanceEm: 0, maxXExtremaOverlapEm: 0.1 },
    hu_hersch: { ...HU_HERSCH_DEFAULTS },
    fontforge: {},
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Shared finite-range rule for every em and depth-factor bound below. */
function isFiniteRange(value: unknown, min: number, max: number): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
}

function validateSourceSetting(value: unknown): void {
  if (!isRecord(value) || typeof value.enabled !== "boolean") {
    throw new Error("Source kerning must carry an enabled flag.");
  }
}

function validateTypeFacetSettings(value: unknown): void {
  if (!isRecord(value)) throw new Error("TypeFacet settings are missing.");
  const normal = value.normalDistanceEm;
  if (!isFiniteRange(normal, 0.01, 0.5)) {
    throw new Error("TypeFacet normal distance must be between 0.01 and 0.5 em.");
  }
  if (!isFiniteRange(value.intrusionToleranceEm, 0, 0.5)) {
    throw new Error("TypeFacet intrusion tolerance must be between 0 and 0.5 em.");
  }
  const minimum = value.minimumDistanceEm === undefined ? 0 : value.minimumDistanceEm;
  if (!isFiniteRange(minimum, 0, normal)) {
    throw new Error("TypeFacet minimum clearance must be between 0 and the normal distance.");
  }
  const overlap = value.maxXExtremaOverlapEm === undefined ? 0.1 : value.maxXExtremaOverlapEm;
  if (!isFiniteRange(overlap, 0, 0.5)) {
    throw new Error("TypeFacet maximum horizontal overlap must be between 0 and 0.5 em.");
  }
}

function validateHuHerschSettings(value: unknown): void {
  if (!isRecord(value)) throw new Error("Hu/Hersch settings are missing.");
  const known = new Set(["apertureDepthFactor", "globalDepthFactor"]);
  for (const key of Object.keys(value)) {
    if (!known.has(key)) throw new Error(`Hu/Hersch does not accept ${key}.`);
  }
  const aperture = value.apertureDepthFactor === undefined
    ? HU_HERSCH_DEFAULTS.apertureDepthFactor : value.apertureDepthFactor;
  if (!isFiniteRange(aperture, HU_HERSCH_APERTURE_MIN, HU_HERSCH_APERTURE_MAX)) {
    throw new Error("Hu/Hersch cavity depth must be between 0 and 1.");
  }
  const global = value.globalDepthFactor === undefined
    ? HU_HERSCH_DEFAULTS.globalDepthFactor : value.globalDepthFactor;
  if (!isFiniteRange(global, HU_HERSCH_GLOBAL_MIN, HU_HERSCH_GLOBAL_MAX)) {
    throw new Error("Hu/Hersch maximum visual depth must be between 0 and 1.");
  }
}

function validateFontforgeSettings(value: unknown): void {
  if (!isRecord(value)) throw new Error("FontForge settings are missing.");
  for (const key of Object.keys(value)) {
    throw new Error(`FontForge does not accept ${key}.`);
  }
}

export function validateKerningPreference(value: unknown): asserts value is KerningPreference {
  if (typeof value === "boolean") return;
  if (!isRecord(value) || !isKerningMethod(value.method)) {
    throw new Error("Unknown kerning method.");
  }
  validateSourceSetting(value.source);
  validateTypeFacetSettings(value.typefacet);
  if (value.hu_hersch !== undefined) validateHuHerschSettings(value.hu_hersch);
  if (value.fontforge !== undefined) validateFontforgeSettings(value.fontforge);
}

export function normalizeKerning(value: KerningPreference = true): KerningState {
  validateKerningPreference(value);
  if (typeof value === "boolean") return { ...defaultKerningState(), source: { enabled: value } };
  return {
    method: value.method,
    source: { enabled: value.source.enabled },
    typefacet: {
      normalDistanceEm: value.typefacet.normalDistanceEm,
      intrusionToleranceEm: value.typefacet.intrusionToleranceEm,
      minimumDistanceEm: value.typefacet.minimumDistanceEm ?? 0,
      maxXExtremaOverlapEm: value.typefacet.maxXExtremaOverlapEm ?? 0.1,
    },
    hu_hersch: {
      apertureDepthFactor: value.hu_hersch?.apertureDepthFactor ?? HU_HERSCH_DEFAULTS.apertureDepthFactor,
      globalDepthFactor: value.hu_hersch?.globalDepthFactor ?? HU_HERSCH_DEFAULTS.globalDepthFactor,
    },
    fontforge: {},
  };
}

export function cloneKerning(value: KerningPreference): KerningPreference {
  return typeof value === "boolean" ? value : normalizeKerning(value);
}

export function selectKerningMethod(value: KerningPreference, method: KerningMethod): KerningState {
  const state = normalizeKerning(value);
  if (!isKerningMethod(method)) throw new Error("Unknown kerning method.");
  return { ...state, method };
}

export function editKerning(value: KerningPreference, edit: KerningEdit): KerningState {
  const state = normalizeKerning(value);
  if (edit.method !== state.method) throw new Error("The kerning controls are no longer active.");
  let next: KerningState;
  switch (edit.method) {
    case "source": next = { ...state, source: { ...edit.settings } }; break;
    case "typefacet": next = { ...state, typefacet: {
      ...edit.settings,
      minimumDistanceEm: edit.settings.minimumDistanceEm === undefined ? state.typefacet.minimumDistanceEm : edit.settings.minimumDistanceEm,
      maxXExtremaOverlapEm: edit.settings.maxXExtremaOverlapEm === undefined ? state.typefacet.maxXExtremaOverlapEm : edit.settings.maxXExtremaOverlapEm,
    } }; break;
    case "hu_hersch": next = { ...state, hu_hersch: { ...edit.settings } }; break;
    case "fontforge": next = { ...state, fontforge: { ...edit.settings } }; break;
    default: return assertNever(edit);
  }
  return normalizeKerning(next);
}

export function isDefaultKerning(value: KerningPreference): boolean {
  return JSON.stringify(normalizeKerning(value)) === JSON.stringify(defaultKerningState());
}

/** Only active settings cross the native rendering seam and its cache identity. */
export function resolveKerning(value: KerningPreference = true): {
  kerning: boolean;
  kerning_method?: KerningMethodRequest;
} {
  const state = normalizeKerning(value);
  switch (state.method) {
    case "source": return { kerning: state.source.enabled };
    case "typefacet": return {
      kerning: true,
      kerning_method: {
        method: "typefacet", normal_distance_em: state.typefacet.normalDistanceEm,
        intrusion_tolerance_em: state.typefacet.intrusionToleranceEm,
        minimum_distance_em: state.typefacet.minimumDistanceEm,
        max_x_extrema_overlap_em: state.typefacet.maxXExtremaOverlapEm,
      },
    };
    case "hu_hersch": return { kerning: true, kerning_method: { method: "hu_hersch",
      aperture_depth_factor: state.hu_hersch.apertureDepthFactor,
      global_depth_factor: state.hu_hersch.globalDepthFactor } };
    case "fontforge": return { kerning: true, kerning_method: { method: "fontforge" } };
    default: return assertNever(state.method);
  }
}

export function parseKerning(value: unknown): KerningPreference | null {
  try {
    validateKerningPreference(value);
    return cloneKerning(value);
  } catch { return null; }
}

export function decodeKerning(value: string | null): KerningPreference | null {
  if (value === "1" || value === "true") return true;
  if (value === "0" || value === "false") return false;
  try { return parseKerning(JSON.parse(value ?? "")); } catch { return null; }
}

export function encodeKerning(value: KerningPreference): string {
  validateKerningPreference(value);
  return typeof value === "boolean" ? value ? "1" : "0" : JSON.stringify(normalizeKerning(value));
}
