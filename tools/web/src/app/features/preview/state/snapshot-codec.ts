// Complete URL snapshots for the font preview.
// Pure codec (Node-testable): encoding, parsing, and validation of the
// versioned query snapshot. DOM, storage, and History writes live in the
// app snapshot layer (../../../navigation/snapshot.ts), not here.
//
// Format v1 (query, WHATWG URLSearchParams:
// https://url.spec.whatwg.org/#interface-urlsearchparams):
//   v=1 & font=<family-id> & profile=<id> & zoom=<1-4> & exact=<0|1>
//   & stem=<font_hints_first|upstream_mono> & kerning=<0|1> & families=<JSON>
// Older links may carry an obsolete `model` parameter; it is ignored on
// decoding and dropped when the snapshot is next written.
// `families` maps each family id to
// {size, axes, spacing, preset, text, advancedOpen, kerningOpen,
//  kerningFilter} with explicit values (defaults included) and the actual
// multiline text even when a preset is selected, so a copied URL does not
// depend on the other browser's storage or preset definitions. Unknown
// query parameters are preserved; the hosting path prefix is untouched.
import type { OutputProfile, StemFitting } from "../../../renderer/renderer-types.js";
import { OWNED_PARAMS, hashFamilyId } from "../../../navigation/router.ts";

export const SNAPSHOT_VERSION = 1;
const MAX_TEXT_LENGTH = 8192;
const PROFILES: readonly OutputProfile[] = ["mono_1bit", "gray_3bit"];
const ZOOM_STOPS: readonly number[] = [1, 2, 3, 4];
const STEM_FITTINGS: readonly StemFitting[] = ["font_hints_first", "upstream_mono"];

export interface AxisMeta {
  tag: string;
  min: number;
  max: number;
  defaultValue: number;
  hidden: boolean;
}

export interface FamilyMeta {
  id: string;
  defaultSize: number;
  defaultAxes: Record<string, number>;
  axes: AxisMeta[];
  sampleText: string;
  presets: { id: string; content: string }[];
  defaultPreset: string;
}

export interface FamilySnapshot {
  size: number;
  axes: Record<string, number>;
  spacing: number;
  preset: string;
  text: string;
  advancedOpen: boolean;
  kerningOpen: boolean;
  kerningFilter: string;
}

export interface PreviewSnapshot {
  version: 1;
  font: string;
  profile: OutputProfile;
  zoom: number;
  pixelAccurate: boolean;
  stemFitting: StemFitting;
  kerning: boolean;
  families: Record<string, FamilySnapshot>;
}

export interface GlobalDefaults {
  font: string;
  profile: OutputProfile;
  zoom: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clamp(value: number, min: number, max: number, fallback: number): number {
  return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
}

function parseBoolParam(value: string | null): boolean | null {
  if (value === "1" || value === "true") return true;
  if (value === "0" || value === "false") return false;
  return null;
}

export function presetForText(
  presets: { id: string; content: string }[],
  text: string,
): string {
  return presets.find((preset) => preset.content === text)?.id ?? "custom";
}

export function defaultFamilySnapshot(meta: FamilyMeta): FamilySnapshot {
  const axes: Record<string, number> = {};
  for (const axis of meta.axes) axes[axis.tag] = axis.defaultValue;
  for (const [tag, value] of Object.entries(meta.defaultAxes)) {
    if (!(tag in axes) && Number.isFinite(value)) axes[tag] = value;
  }
  return {
    size: clamp(meta.defaultSize, 1, 512, 16),
    axes,
    spacing: 0,
    preset: meta.defaultPreset,
    text: meta.sampleText.slice(0, MAX_TEXT_LENGTH),
    advancedOpen: false,
    kerningOpen: false,
    kerningFilter: "",
  };
}

export function defaultSnapshot(
  metas: FamilyMeta[],
  defaults: GlobalDefaults,
): PreviewSnapshot {
  const families: Record<string, FamilySnapshot> = {};
  for (const meta of metas) families[meta.id] = defaultFamilySnapshot(meta);
  return {
    version: 1,
    font: defaults.font,
    profile: defaults.profile,
    zoom: defaults.zoom,
    pixelAccurate: false,
    stemFitting: "font_hints_first",
    kerning: true,
    families,
  };
}

function validateFamilySnapshot(raw: unknown, meta: FamilyMeta): FamilySnapshot {
  const fallback = defaultFamilySnapshot(meta);
  if (!isRecord(raw)) return fallback;
  const axes: Record<string, number> = { ...fallback.axes };
  if (isRecord(raw.axes)) {
    for (const axis of meta.axes) {
      const value = raw.axes[axis.tag];
      if (typeof value === "number" && Number.isFinite(value)) {
        axes[axis.tag] = clamp(value, axis.min, axis.max, axis.defaultValue);
      }
    }
  }
  const presetIds = new Set([...meta.presets.map((preset) => preset.id), "custom"]);
  const text = typeof raw.text === "string"
    ? raw.text.slice(0, MAX_TEXT_LENGTH)
    : fallback.text;
  return {
    size: typeof raw.size === "number" ? clamp(raw.size, 1, 512, fallback.size) : fallback.size,
    axes,
    spacing: typeof raw.spacing === "number" ? clamp(raw.spacing, -2, 4, 0) : 0,
    preset: typeof raw.preset === "string" && presetIds.has(raw.preset)
      ? raw.preset
      : presetForText(meta.presets, text),
    text,
    advancedOpen: raw.advancedOpen === true,
    kerningOpen: raw.kerningOpen === true,
    kerningFilter: typeof raw.kerningFilter === "string"
      ? raw.kerningFilter.slice(0, 64)
      : "",
  };
}

function toSearchParams(search: string | URLSearchParams): URLSearchParams {
  if (search instanceof URLSearchParams) return new URLSearchParams(search);
  const text = search.startsWith("?") ? search.slice(1) : search;
  return new URLSearchParams(text);
}

/** Validated v1 snapshot, or null for plain, legacy, malformed or unknown-version URLs. */
export function parseUrlSnapshot(
  search: string | URLSearchParams,
  hash: string,
  metas: FamilyMeta[],
  defaults: GlobalDefaults,
): PreviewSnapshot | null {
  const params = toSearchParams(search);
  if (params.get("v") !== String(SNAPSHOT_VERSION)) return null;
  const ids = new Set(metas.map((meta) => meta.id));
  const hashId = hashFamilyId(hash ?? "");
  const fontParam = params.get("font");
  const font = fontParam && ids.has(fontParam)
    ? fontParam
    : hashId && ids.has(hashId) ? hashId : defaults.font;
  const profileParam = params.get("profile");
  const profile = (PROFILES as readonly string[]).includes(profileParam ?? "")
    ? (profileParam as OutputProfile)
    : defaults.profile;
  const zoomValue = Number(params.get("zoom"));
  const zoom = ZOOM_STOPS.includes(zoomValue) ? zoomValue : defaults.zoom;
  const exact = parseBoolParam(params.get("exact"));
  const stemParam = params.get("stem");
  const kerning = parseBoolParam(params.get("kerning"));
  let familiesRaw: unknown = null;
  const familiesParam = params.get("families");
  if (familiesParam) {
    try { familiesRaw = JSON.parse(familiesParam); } catch { familiesRaw = null; }
  }
  const families: Record<string, FamilySnapshot> = {};
  for (const meta of metas) {
    families[meta.id] = validateFamilySnapshot(
      isRecord(familiesRaw) ? familiesRaw[meta.id] : null,
      meta,
    );
  }
  return {
    version: 1,
    font,
    profile,
    zoom,
    pixelAccurate: exact ?? false,
    stemFitting: (STEM_FITTINGS as readonly string[]).includes(stemParam ?? "")
      ? (stemParam as StemFitting)
      : "font_hints_first",
    kerning: kerning ?? true,
    families,
  };
}

/** Legacy profile/zoom query, minimal `font` links, and #family selection (no `v` parameter). */
export function parseLegacyState(
  search: string | URLSearchParams,
  hash: string,
  metas: FamilyMeta[],
): { font?: string; profile?: OutputProfile; zoom?: number } {
  const params = toSearchParams(search);
  const result: { font?: string; profile?: OutputProfile; zoom?: number } = {};
  const ids = new Set(metas.map((meta) => meta.id));
  const hashId = hashFamilyId(hash ?? "");
  const fontParam = params.get("font");
  if (fontParam && ids.has(fontParam)) result.font = fontParam;
  else if (hashId && ids.has(hashId)) result.font = hashId;
  const profile = params.get("profile");
  if ((PROFILES as readonly string[]).includes(profile ?? "")) {
    result.profile = profile as OutputProfile;
  }
  const zoom = Number(params.get("zoom"));
  if (ZOOM_STOPS.includes(zoom)) result.zoom = zoom;
  return result;
}

/** Search params for `snapshot`, preserving unknown params from `baseSearch`. */
export function encodeUrlSnapshot(
  snapshot: PreviewSnapshot,
  baseSearch: string | URLSearchParams,
  familyOrder?: string[],
): URLSearchParams {
  const base = toSearchParams(baseSearch ?? "");
  const owned = new Set(OWNED_PARAMS);
  const result = new URLSearchParams();
  for (const [key, value] of base.entries()) {
    if (!owned.has(key)) result.append(key, value);
  }
  const order = familyOrder ?? Object.keys(snapshot.families);
  const families: Record<string, FamilySnapshot> = {};
  for (const id of order) {
    const family = snapshot.families[id];
    if (family) families[id] = family;
  }
  for (const [id, family] of Object.entries(snapshot.families)) {
    if (!(id in families)) families[id] = family;
  }
  const familiesJson: Record<string, Record<string, unknown>> = {};
  for (const [id, family] of Object.entries(families)) {
    familiesJson[id] = {
      size: family.size,
      axes: family.axes,
      spacing: family.spacing,
      preset: family.preset,
      text: family.text,
      advancedOpen: family.advancedOpen,
      kerningOpen: family.kerningOpen,
      kerningFilter: family.kerningFilter,
    };
  }
  result.set("v", String(SNAPSHOT_VERSION));
  result.set("font", snapshot.font);
  result.set("profile", snapshot.profile);
  result.set("zoom", String(snapshot.zoom));
  result.set("exact", snapshot.pixelAccurate ? "1" : "0");
  result.set("stem", snapshot.stemFitting);
  result.set("kerning", snapshot.kerning ? "1" : "0");
  result.set("families", JSON.stringify(familiesJson));
  return result;
}

/** Inner detail-hash params: versioned state without the font identity, which the hash path carries. */
export function encodeHashSearch(
  snapshot: PreviewSnapshot,
  baseSearch: string | URLSearchParams,
  familyOrder?: string[],
): URLSearchParams {
  const params = encodeUrlSnapshot(snapshot, baseSearch, familyOrder);
  params.delete("font");
  return params;
}
