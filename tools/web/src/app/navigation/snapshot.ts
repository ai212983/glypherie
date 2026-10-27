// Preview-URL snapshots for the SPA. Reuses the versioned query format and
// pure codec from the legacy preview (v, font, profile, exact, stem,
// kerning, families; History.replaceState, 250 ms
// debounce), built from the live library instead of generator exports: no
// family is hardcoded.
// cspell:words metas
import type { RendererRole } from "../renderer/renderer-types.js";
import {
  defaultSnapshot,
  encodeHashSearch,
  parseLegacyState,
  parseUrlSnapshot,
  type FamilyMeta,
  type GlobalDefaults,
  type PreviewSnapshot,
} from "../features/preview/state/snapshot-codec.js";
import {
  detailPath,
  indexPath,
  homePath,
  isRoutePath,
  palettesPath,
  parseRoute,
  type Route,
} from "./router.js";

import { readRoutePath, readRouteSearch } from "./location.js";
export { readRouteSearch } from "./location.js";

export type { PreviewSnapshot, FamilySnapshot } from "../features/preview/state/snapshot-codec.js";

const EXACT_KEY = "font-preview.pixel-accurate";
const SPACING_KEY = "font-preview.spacing";
const WRITE_DEBOUNCE_MS = 250;

// Renderer role lives outside the versioned snapshot codec: it is a
// validated app-level query param, preserved across snapshot writes because
// the codec keeps unknown params, and ignored by older links.
export const SNAPSHOT_ROLES: readonly RendererRole[] = ["candidate", "baseline", "reference"];

export function readRoleParam(search: string): RendererRole {
  const value = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search).get("role");
  return (SNAPSHOT_ROLES as readonly string[]).includes(value ?? "") ? (value as RendererRole) : "candidate";
}

export function writeRoleParam(role: RendererRole): void {
  const params = new URLSearchParams(readRouteSearch());
  params.set("role", role);
  window.history.replaceState(window.history.state, "", `${window.location.pathname}?${params}`);
}

function readStoredGlobals(): { kerning?: boolean } {
  const result: { kerning?: boolean } = {};
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(SPACING_KEY) ?? "");
    if (parsed && typeof parsed === "object" && typeof (parsed as Record<string, unknown>).kerning === "boolean") {
      result.kerning = (parsed as { kerning: boolean }).kerning;
    }
  } catch { /* storage unavailable */ }
  return result;
}

function withStoredGlobals(snapshot: PreviewSnapshot): PreviewSnapshot {
  const stored = readStoredGlobals();
  snapshot.pixelAccurate = true;
  if (stored.kerning !== undefined) snapshot.kerning = stored.kerning;
  return snapshot;
}

export function readInitialSnapshot(metas: FamilyMeta[]): PreviewSnapshot {
  const ids = new Set(metas.map((meta) => meta.id));
  const defaults: GlobalDefaults = {
    font: metas[0]?.id ?? "",
    profile: "mono_1bit",
  };
  const path = readRoutePath();
  const outer = window.location.search;
  const parsed = parseRoute(path);
  if (parsed?.name === "font" && parsed.font && ids.has(parsed.font)) {
    const versioned = parseUrlSnapshot(readRouteSearch(), "", metas, { ...defaults, font: parsed.font });
    const snapshot = versioned ?? withStoredGlobals(defaultSnapshot(metas, { ...defaults, font: parsed.font }));
    snapshot.font = parsed.font;
    return snapshot;
  }
  if (parsed?.name === "font" || (parsed === null && isRoutePath(path))) {
    return defaultSnapshot(metas, defaults);
  }
  const legacy = legacyFont(outer, window.location.hash, metas);
  if (legacy && ids.has(legacy)) {
    const versioned = parseUrlSnapshot(outer, window.location.hash, metas, { ...defaults, font: legacy });
    if (versioned) {
      versioned.font = legacy;
      return versioned;
    }
    const snapshot = withStoredGlobals(defaultSnapshot(metas, { ...defaults, font: legacy }));
    const state = parseLegacyState(outer, window.location.hash, metas);
    if (state.profile) snapshot.profile = state.profile;
    snapshot.font = legacy;
    return snapshot;
  }
  return withStoredGlobals(defaultSnapshot(metas, defaults));
}

function legacyFont(outer: string, hash: string, metas: FamilyMeta[]): string | null {
  const params = new URLSearchParams(outer.startsWith("?") ? outer.slice(1) : outer);
  if (params.get("v") === "1") return params.get("font");
  const state = parseLegacyState(outer, hash, metas);
  return state.font ?? params.get("font");
}

let writeTimer: ReturnType<typeof setTimeout> | undefined;

export function scheduleSnapshotWrite(snapshot: PreviewSnapshot, familyOrder: string[]): void {
  clearTimeout(writeTimer);
  writeTimer = setTimeout(() => {
    writeTimer = undefined;
    writeSnapshotNow(snapshot, familyOrder);
  }, WRITE_DEBOUNCE_MS);
}

export function hasPendingSnapshotWrite(): boolean {
  return writeTimer !== undefined;
}

// Drop a pending debounced write without touching the URL. Page navigation
// calls this first so a stale timer cannot rewrite the address bar back to
// the page the user just left.
export function cancelSnapshotWrite(): void {
  clearTimeout(writeTimer);
  writeTimer = undefined;
}

function historyStateFor(snapshot: PreviewSnapshot): { previewSnapshot: PreviewSnapshot } {
  return { previewSnapshot: snapshot };
}

export function writeSnapshotNow(snapshot: PreviewSnapshot, familyOrder: string[]): void {
  clearTimeout(writeTimer);
  writeTimer = undefined;
  const params = encodeHashSearch(snapshot, readRouteSearch(), familyOrder);
  const text = params.toString();
  const url = `${detailPath(snapshot.font)}${text ? `?${text}` : ""}`;
  window.history.replaceState(historyStateFor(snapshot), "", url);
  try {
    localStorage.setItem(EXACT_KEY, "true");
    localStorage.setItem(SPACING_KEY, JSON.stringify({ kerning: snapshot.kerning }));
  } catch { /* storage unavailable */ }
}

// Canonical URL for a resolved route, migrating legacy queries and fragments.
export function canonicalPathFor(
  route: Route,
  snapshot: PreviewSnapshot,
  familyOrder: string[],
  baseSearch: string,
): string {
  if (route.page === "font") {
    return `${detailPath(route.font)}?${encodeHashSearch(snapshot, baseSearch, familyOrder).toString()}`;
  }
  if (route.page === "palettes") return palettesPath(baseSearch);
  if (route.page === "home") return homePath(baseSearch);
  return indexPath(baseSearch);
}

export function replaceCanonicalPath(
  route: Route,
  snapshot: PreviewSnapshot,
  familyOrder: string[],
  baseSearch: string,
): void {
  const path = canonicalPathFor(route, snapshot, familyOrder, baseSearch);
  window.history.replaceState(historyStateFor(snapshot), "", path);
}
