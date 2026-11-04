export interface TypeFacetSettings {
  normalDistanceEm: number;
  intrusionToleranceEm: number;
  minimumDistanceEm: number;
  maxXExtremaOverlapEm: number;
}

/** Earlier saved variants carry only the first two controls. */
type TypeFacetPreference = Pick<TypeFacetSettings, "normalDistanceEm" | "intrusionToleranceEm"> &
  Partial<Pick<TypeFacetSettings, "minimumDistanceEm" | "maxXExtremaOverlapEm">>;

export interface FontForgeSettings {
  strength: number;
}

export interface HuHerschSettings {
  strength: number;
}

/** Each method owns its settings; tracking remains outside kerning. */
export interface KerningSettingsMap {
  source: { enabled: boolean };
  typefacet: TypeFacetSettings;
  hu_hersch: HuHerschSettings;
  fontforge: FontForgeSettings;
}

export type KerningMethod = keyof KerningSettingsMap;
export type KerningState = { method: KerningMethod } & KerningSettingsMap;

/** Historical booleans and two-method saved values migrate on normalization. */
export type KerningPreference = boolean | (
  Pick<KerningState, "method" | "source"> & { typefacet: TypeFacetPreference } &
  { hu_hersch?: Partial<HuHerschSettings> } & Partial<Pick<KerningState, "fontforge">>
);

export type KerningEdit = {
  [Method in KerningMethod]: { method: Method; settings: Method extends "typefacet" ? TypeFacetPreference : KerningSettingsMap[Method] }
}[KerningMethod];

export type KerningMethodRequest =
  | { method: "typefacet"; normal_distance_em: number; intrusion_tolerance_em: number; minimum_distance_em: number; max_x_extrema_overlap_em: number }
  | { method: "hu_hersch"; strength: number }
  | { method: "fontforge"; strength: number };

interface KerningMethodDescription {
  label: string;
  experimental: boolean;
  requiresExplicitPipeline: boolean;
  description: string;
}

/** Only methods compiled into the shared native/WASM renderer belong here. */
export const KERNING_METHODS = {
  source: {
    label: "Source", experimental: false, requiresExplicitPipeline: false,
    description: "Keeps the font's source kerning and fitted bearing corrections.",
  },
  typefacet: {
    label: "TypeFacet", experimental: true, requiresExplicitPipeline: true,
    description: "Manual optical spacing; adjust these parameters for the font.",
  },
  hu_hersch: {
    label: "Hu/Hersch", experimental: true, requiresExplicitPipeline: true,
    description: "Calibrates optical spacing to the font's reference alphabet density.",
  },
  fontforge: {
    label: "FontForge source-relative", experimental: true, requiresExplicitPipeline: true,
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
export function defaultKerningState(): KerningState {
  return {
    method: "source",
    source: { enabled: true },
    typefacet: { normalDistanceEm: 0.1, intrusionToleranceEm: 0.1, minimumDistanceEm: 0, maxXExtremaOverlapEm: 0.1 },
    hu_hersch: { strength: 1 },
    fontforge: { strength: 1 },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function validateKerningPreference(value: unknown): asserts value is KerningPreference {
  if (typeof value === "boolean") return;
  if (!isRecord(value) || !isKerningMethod(value.method)) {
    throw new Error("Unknown kerning method.");
  }
  if (!isRecord(value.source) || typeof value.source.enabled !== "boolean") {
    throw new Error("Source kerning must carry an enabled flag.");
  }
  if (!isRecord(value.typefacet)) throw new Error("TypeFacet settings are missing.");
  const normal = value.typefacet.normalDistanceEm;
  const intrusion = value.typefacet.intrusionToleranceEm;
  if (typeof normal !== "number" || !Number.isFinite(normal) || normal < 0.01 || normal > 0.5) {
    throw new Error("TypeFacet normal distance must be between 0.01 and 0.5 em.");
  }
  if (typeof intrusion !== "number" || !Number.isFinite(intrusion) || intrusion < 0 || intrusion > 0.5) {
    throw new Error("TypeFacet intrusion tolerance must be between 0 and 0.5 em.");
  }
  const minimum = value.typefacet.minimumDistanceEm === undefined ? 0 : value.typefacet.minimumDistanceEm;
  const overlap = value.typefacet.maxXExtremaOverlapEm === undefined ? 0.1 : value.typefacet.maxXExtremaOverlapEm;
  if (typeof minimum !== "number" || !Number.isFinite(minimum) || minimum < 0 || minimum > normal) {
    throw new Error("TypeFacet minimum clearance must be between 0 and the normal distance.");
  }
  if (typeof overlap !== "number" || !Number.isFinite(overlap) || overlap < 0 || overlap > 0.5) {
    throw new Error("TypeFacet maximum horizontal overlap must be between 0 and 0.5 em.");
  }
  if (value.hu_hersch !== undefined) {
    if (!isRecord(value.hu_hersch) || Object.keys(value.hu_hersch).some((key) => key !== "strength")) {
      throw new Error("Hu/Hersch only accepts correction strength.");
    }
    const strength = value.hu_hersch.strength === undefined ? 1 : value.hu_hersch.strength;
    if (typeof strength !== "number" || !Number.isFinite(strength) || strength < 0 || strength > 1) {
      throw new Error("Hu/Hersch correction strength must be between 0 and 1.");
    }
  }
  if (value.fontforge !== undefined) {
    if (!isRecord(value.fontforge)) throw new Error("FontForge settings are missing.");
    const strength = value.fontforge.strength;
    if (typeof strength !== "number" || !Number.isFinite(strength) || strength < 0 || strength > 1) {
      throw new Error("FontForge strength must be between 0 and 1.");
    }
  }
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
    hu_hersch: { strength: value.hu_hersch?.strength ?? 1 },
    fontforge: { strength: value.fontforge?.strength ?? 1 },
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
    case "hu_hersch": return { kerning: true, kerning_method: { method: "hu_hersch", strength: state.hu_hersch.strength } };
    case "fontforge": return { kerning: true, kerning_method: { method: "fontforge", strength: state.fontforge.strength } };
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
