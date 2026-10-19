export type Route =
  | { page: "index"; notice?: string }
  | { page: "font"; font: string }
  | { page: "variant"; font: string; variant: string };

export interface HashParts {
  path: string;
  search: string;
}

export function splitHash(hash: string): HashParts {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  const query = raw.indexOf("?");
  if (query < 0) return { path: raw, search: "" };
  return { path: raw.slice(0, query), search: raw.slice(query + 1) };
}

export type HashRoute =
  | { name: "index" }
  | { name: "font"; font: string }
  | { name: "variant"; font: string; variant: string }
  | null;

export function parseHashRoute(hash: string): HashRoute {
  const { path } = splitHash(hash ?? "");
  if (path === "" || path === "/") return { name: "index" };
  const variant = path.match(/^\/font\/([^/]+)\/variant\/([^/]+)\/?$/);
  if (variant) {
    try {
      return {
        name: "variant",
        font: decodeURIComponent(variant[1] ?? ""),
        variant: decodeURIComponent(variant[2] ?? ""),
      };
    } catch {
      return null;
    }
  }
  const match = path.match(/^\/font\/([^/]+)\/?$/);
  if (!match) return null;
  try {
    return { name: "font", font: decodeURIComponent(match[1] ?? "") };
  } catch {
    return null;
  }
}

export function isRouteHash(hash: string): boolean {
  return (hash ?? "").startsWith("#/");
}

export function hashFamilyId(hash: string): string | null {
  return hash.match(/^#family-([A-Za-z0-9-]+)$/)?.[1] ?? null;
}

function outerParams(search: string | URLSearchParams): URLSearchParams {
  if (search instanceof URLSearchParams) return new URLSearchParams(search);
  const text = search.startsWith("?") ? search.slice(1) : search;
  return new URLSearchParams(text);
}

function unknownFontNotice(font: string): string {
  return `Font “${font}” is not in this library. Showing the font library instead.`;
}

export function resolveRoute(
  hash: string,
  outerSearch: string | URLSearchParams,
  knownIds: readonly string[],
): Route {
  const known = new Set(knownIds);
  const parsed = parseHashRoute(hash ?? "");
  if (parsed?.name === "variant") {
    // Shape-level resolution only: the variant row itself (existence and
    // font ownership) resolves asynchronously in the editor from IndexedDB.
    if (parsed.font && known.has(parsed.font) && parsed.variant) {
      return { page: "variant", font: parsed.font, variant: parsed.variant };
    }
    if (parsed.font && !known.has(parsed.font)) {
      return { page: "index", notice: unknownFontNotice(parsed.font) };
    }
    return { page: "index", notice: `Unknown route “${hash}”. Showing the font library instead.` };
  }
  if (parsed?.name === "font") {
    if (parsed.font && known.has(parsed.font)) return { page: "font", font: parsed.font };
    if (parsed.font) return { page: "index", notice: unknownFontNotice(parsed.font) };
    return { page: "index", notice: `Unknown route “${hash}”. Showing the font library instead.` };
  }
  if (parsed === null) {
    if (isRouteHash(hash ?? "")) {
      return { page: "index", notice: `Unknown route “${hash}”. Showing the font library instead.` };
    }
  } else if (hash === "#/" || splitHash(hash ?? "").search) {
    return { page: "index" };
  }
  const params = outerParams(outerSearch ?? "");
  const font = params.get("font");
  const hashId = hashFamilyId(hash ?? "");
  if (params.get("v") === "1") {
    if (font && known.has(font)) return { page: "font", font };
    if (font) return { page: "index", notice: unknownFontNotice(font) };
    return { page: "index" };
  }
  const selected = font ?? hashId;
  if (selected && known.has(selected)) return { page: "font", font: selected };
  if (selected) return { page: "index", notice: unknownFontNotice(selected) };
  return { page: "index" };
}

// Query parameters owned by the versioned preview snapshot codec. Route
// builders drop them when leaving a font route so stale settings do not
// leak into the library hash; every other param (e.g. role, utm) is kept.
export const OWNED_PARAMS: readonly string[] = [
  "v", "font", "profile", "zoom", "exact", "stem", "model", "kerning", "families",
];

/** Canonical detail hash for one font; settings ride the inner snapshot once edited. */
export function detailHash(font: string): string {
  return `#/font/${font}/`;
}

/** Canonical hash for one saved variant; its settings live in IndexedDB, never in the URL. */
export function variantHash(font: string, variant: string): string {
  return `#/font/${font}/variant/${variant}/`;
}

/**
 * Canonical variant hash keeping foreign params (e.g. utm) while dropping
 * snapshot state and the renderer role, which the saved variant owns.
 */
export function variantHashKeeping(
  font: string,
  variant: string,
  baseSearch: string | URLSearchParams,
): string {
  const base = outerParams(baseSearch ?? "");
  const dropped = new Set([...OWNED_PARAMS, "role"]);
  const result = new URLSearchParams();
  for (const [key, value] of base.entries()) {
    if (!dropped.has(key)) result.append(key, value);
  }
  const text = result.toString();
  return text ? `${variantHash(font, variant)}?${text}` : variantHash(font, variant);
}

/** Canonical library hash, keeping foreign params (e.g. role, utm) while dropping snapshot state. */
export function indexHash(baseSearch: string | URLSearchParams): string {
  const base = outerParams(baseSearch ?? "");
  const owned = new Set(OWNED_PARAMS);
  const result = new URLSearchParams();
  for (const [key, value] of base.entries()) {
    if (!owned.has(key)) result.append(key, value);
  }
  const text = result.toString();
  return text ? `#/?${text}` : `#/`;
}
