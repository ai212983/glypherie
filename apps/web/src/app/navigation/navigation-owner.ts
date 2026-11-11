import type { StoredFont } from "../fonts/storage.js";
import type { RendererRole } from "../renderer/renderer-types.js";
import {
  canonicalPathFor,
  cancelSnapshotWrite,
  hasPendingSnapshotWrite,
  readInitialSnapshot,
  readRoleParam,
  readRouteSearch,
  replaceCanonicalPath,
  scheduleSnapshotWrite,
  writeRoleParam,
  writeSnapshotNow,
  type PreviewSnapshot,
} from "./snapshot.ts";
import { defaultFamilySnapshot, parseLegacyState, parseUrlSnapshot } from "../features/preview/state/snapshot-codec.ts";
import { buildMetas, metaForFont } from "../features/preview/state/family-meta.ts";
import { indexPath, palettesPath, resolveRoute, screenPath, variantPathKeeping, type Route } from "./router.ts";
import { readRoutePath } from "./location.ts";

export type { PreviewSnapshot };
export type { RendererRole };
export type { Route };

export type Page =
  | { name: "home" }
  | { name: "palettes" }
  // The unified Screen page also serves the legacy /scenes/ and
  // /scene/<id>/ links: they open the same default composition and the URL
  // canonicalizes to /screen/ without scene selection.
  | { name: "screen" }
  | { name: "index" }
  | { name: "preview"; font: string }
  | { name: "variant"; font: string; variant: string };

export interface NavigationSnapshot {
  page: Page | null;
  snapshot: PreviewSnapshot | null;
  role: RendererRole;
  notice: string;
  detailNotice: string;
}

interface PendingLocation {
  path: string;
  search: string;
  hash: string;
}

// Catalog-independent destinations resolve while the library (or renderer)
// is still pending; font, variant and index routes wait for the catalog so
// a genuine font URL cannot fall back to the library mid-seed.
function shouldDeferRouteWhileCatalogPending(route: Route): boolean {
  return route.page === "font" || route.page === "variant" || route.page === "index";
}

function removeFontFromSnapshot(
  snapshot: PreviewSnapshot,
  removedId: string,
  remainingIds: readonly string[],
): PreviewSnapshot {
  const families = { ...snapshot.families };
  delete families[removedId];
  const next: PreviewSnapshot = { ...snapshot, families };
  if (!remainingIds.some((id) => id === next.font)) {
    next.font = remainingIds[0] ?? "";
  }
  return next;
}

// Owns current route, deferred history navigation and debounced snapshot URL writes. useNavigation
// binds browser events and subscriptions.
export class NavigationOwner {
  private catalog: StoredFont[] | null = null;
  private pendingLocation: PendingLocation | null = null;
  private handledHref = "";
  private state: NavigationSnapshot;
  private cached: NavigationSnapshot;
  private listeners = new Set<() => void>();
  private onTransition: (() => void) | undefined;

  constructor(onTransition?: () => void) {
    this.onTransition = onTransition;
    const inner = readRouteSearch();
    this.state = {
      page: null,
      snapshot: null,
      role: readRoleParam(inner || window.location.search),
      notice: "",
      detailNotice: "",
    };
    this.cached = this.state;
  }

  subscribe = (notify: () => void): (() => void) => {
    this.listeners.add(notify);
    return () => {
      this.listeners.delete(notify);
    };
  };

  // Keep snapshot identity stable between emissions for useSyncExternalStore.
  getSnapshot = (): NavigationSnapshot => this.cached;

  private emit(): void {
    this.cached = { ...this.state };
    for (const notify of [...this.listeners]) notify();
  }

  migrationBase(): string {
    const inner = readRouteSearch();
    return inner || window.location.search;
  }

  private pushPath(path: string): void {
    // History carries identity; IndexedDB owns saved settings so Back cannot restore stale edits.
    window.history.pushState(null, "", path);
    this.handledHref = window.location.href;
  }

  // One shared admission rule: a new explicit transition supersedes any
  // deferred write and any remembered pending route, so a stale timer or an
  // old deferred request can never hijack the newer destination.
  private admitTransition(): void {
    cancelSnapshotWrite();
    this.pendingLocation = null;
  }

  private applySnapshot(next: PreviewSnapshot, immediate = false): void {
    this.state.snapshot = next;
    const order = (this.catalog ?? []).map((font) => font.id);
    if (immediate) writeSnapshotNow(next, order);
    else scheduleSnapshotWrite(next, order);
    this.emit();
  }

  onPatch(patch: Partial<PreviewSnapshot>, immediate = false): void {
    const current = this.state.snapshot;
    if (!current) return;
    this.applySnapshot({ ...current, ...patch }, immediate);
  }

  applySnapshotIntent(next: PreviewSnapshot, immediate = false): void {
    this.applySnapshot(next, immediate);
  }

  openPreview(id: string, knownFont?: StoredFont): void {
    const list = this.catalog ?? [];
    const target = knownFont ?? list.find((font) => font.id === id);
    if (!target) return;
    this.admitTransition();
    const metas = buildMetas(list);
    const base = this.state.snapshot ?? readInitialSnapshot(metas);
    const next: PreviewSnapshot = { ...base, font: id };
    if (!next.families[id]) {
      const meta = metaForFont(target);
      next.families = { ...next.families, [id]: defaultFamilySnapshot(meta) };
    }
    this.state.snapshot = next;
    this.state.page = { name: "preview", font: id };
    this.state.notice = "";
    this.state.detailNotice = "";
    this.onTransition?.();
    this.pushPath(
      canonicalPathFor(
        { page: "font", font: id },
        next,
        list.map((font) => font.id),
        this.migrationBase(),
      ),
    );
    this.emit();
  }

  openVariantId(fontId: string, variantId: string): void {
    this.admitTransition();
    this.state.page = { name: "variant", font: fontId, variant: variantId };
    this.state.notice = "";
    this.state.detailNotice = "";
    this.onTransition?.();
    this.pushPath(variantPathKeeping(fontId, variantId, this.migrationBase()));
    this.emit();
  }

  openIndex(message = ""): void {
    this.admitTransition();
    this.state.page = { name: "index" };
    this.state.notice = message;
    this.state.detailNotice = "";
    this.onTransition?.();
    this.pushPath(indexPath(this.migrationBase()));
    this.emit();
  }

  openPalettes(): void {
    this.admitTransition();
    this.state.page = { name: "palettes" };
    this.state.notice = "";
    this.state.detailNotice = "";
    this.onTransition?.();
    this.pushPath(palettesPath(this.migrationBase()));
    this.emit();
  }

  openScreen(): void {
    this.admitTransition();
    this.state.page = { name: "screen" };
    this.state.notice = "";
    this.state.detailNotice = "";
    this.onTransition?.();
    this.pushPath(screenPath(this.migrationBase()));
    this.emit();
  }

  onRole(next: RendererRole): void {
    this.state.role = next;
    writeRoleParam(next);
    // A role switch replaces the URL in place: track it like a push so a
    // later traversal back to an identical font URL is not mistaken for a
    // duplicate popstate/hashchange event.
    this.handledHref = window.location.href;
    this.emit();
  }

  removePreviewFont(targetId: string): PreviewSnapshot | null {
    const current = this.state.snapshot;
    if (!current) return null;
    const remaining = (this.catalog ?? []).filter((font) => font.id !== targetId);
    const next = removeFontFromSnapshot(
      current,
      targetId,
      remaining.map((font) => font.id),
    );
    this.state.snapshot = next;
    this.emit();
    return next;
  }

  setCatalog(catalog: StoredFont[] | null): void {
    this.catalog = catalog;
    if (this.state.page === null) {
      this.resolveBoot();
    } else if (this.pendingLocation && catalog !== null) {
      const pending = this.pendingLocation;
      this.pendingLocation = null;
      this.resolveHistoryLocation(pending);
      this.emit();
    }
  }

  handleHistoryChange(): void {
    if (window.location.href === this.handledHref) return;
    cancelSnapshotWrite();
    const innerRole = readRouteSearch();
    this.state.role = readRoleParam(innerRole || window.location.search);
    this.state.detailNotice = "";
    this.onTransition?.();
    const location: PendingLocation = {
      path: readRoutePath(),
      search: window.location.search,
      hash: window.location.hash,
    };
    const list = this.catalog ?? [];
    const route = resolveRoute(
      location.path,
      location.search,
      list.map((font) => font.id),
    );
    if (!shouldDeferRouteWhileCatalogPending(route)) {
      this.pendingLocation = null;
      this.resolveChrome(
        route,
        list.map((font) => font.id),
        this.migrationBase(),
      );
    } else if (this.catalog === null) {
      // The catalog is still pending: keep the existing page and remember
      // the request so it resolves when the catalog arrives instead of
      // being lost behind the unrelated existing page.
      this.pendingLocation = location;
    } else {
      this.pendingLocation = null;
      this.resolveHistoryLocation(location);
    }
    this.handledHref = window.location.href;
    this.emit();
  }

  flushForHide(): void {
    const current = this.state.snapshot;
    if (current && hasPendingSnapshotWrite()) {
      writeSnapshotNow(
        current,
        (this.catalog ?? []).map((font) => font.id),
      );
    }
  }

  dispose(): void {
    cancelSnapshotWrite();
    this.listeners.clear();
  }

  private resolveChrome(route: Route, order: string[], base: string): void {
    const list = this.catalog ?? [];
    const metas = buildMetas(list);
    const current = this.state.snapshot ?? readInitialSnapshot(metas);
    replaceCanonicalPath(route, current, order, base);
    if (!this.state.snapshot) this.state.snapshot = current;
    this.state.page =
      route.page === "home"
        ? { name: "home" }
        : route.page === "screen"
          ? { name: "screen" }
          : route.page === "scenes"
            ? { name: "screen" }
            : route.page === "scene"
              ? { name: "screen" }
              : { name: "palettes" };
    this.state.notice = "";
  }

  private resolveHistoryLocation(location: PendingLocation): void {
    const list = this.catalog ?? [];
    const metas = buildMetas(list);
    const route = resolveRoute(
      location.path,
      location.search,
      list.map((font) => font.id),
    );
    const inner = readRouteSearch();
    this.state.role = readRoleParam(inner || window.location.search);
    this.state.detailNotice = "";
    const order = list.map((font) => font.id);
    const base = readRouteSearch() || window.location.search;
    if (
      route.page === "palettes" ||
      route.page === "screen" ||
      route.page === "home" ||
      route.page === "scenes" ||
      route.page === "scene"
    ) {
      this.resolveChrome(route, order, base);
    } else if (route.page === "variant") {
      window.history.replaceState(null, "", variantPathKeeping(route.font, route.variant, base));
      this.state.page = { name: "variant", font: route.font, variant: route.variant };
      this.state.notice = "";
    } else if (route.page === "font") {
      this.resolveFontHistory(route.font, metas, order, base);
      this.state.page = { name: "preview", font: route.font };
      this.state.notice = "";
    } else {
      const current = this.state.snapshot;
      if (current) replaceCanonicalPath({ page: "index" }, current, order, base);
      this.state.page = { name: "index" };
      this.state.notice = route.notice ?? "";
    }
  }

  private resolveFontHistory(font: string, metas: ReturnType<typeof buildMetas>, order: string[], base: string): void {
    const search = readRouteSearch();
    const params = new URLSearchParams(search);
    if (params.get("v") === "1") {
      // Versioned URL restore: the address bar owns the preview.
      let snap =
        parseUrlSnapshot(search, "", metas, {
          font,
          profile: "mono_1bit",
        }) ?? readInitialSnapshot(metas);
      if (!metas.some((meta) => meta.id === snap.font)) snap = { ...snap, font: metas[0]?.id ?? "" };
      snap = { ...snap, font };
      replaceCanonicalPath({ page: "font", font }, snap, order, base);
      this.state.snapshot = snap;
    } else {
      // History navigation retains the current unsaved preview.
      const current = this.state.snapshot;
      if (current) {
        const legacy = parseLegacyState(window.location.search, window.location.hash, metas);
        const next: PreviewSnapshot = { ...current, font };
        if (legacy.profile) next.profile = legacy.profile;
        if (!next.families[font]) {
          const meta = metas.find((entry) => entry.id === font);
          if (meta) next.families = { ...next.families, [font]: defaultFamilySnapshot(meta) };
        }
        replaceCanonicalPath({ page: "font", font }, next, order, base);
        this.state.snapshot = next;
      } else {
        let snap = readInitialSnapshot(metas);
        snap = { ...snap, font };
        replaceCanonicalPath({ page: "font", font }, snap, order, base);
        this.state.snapshot = snap;
      }
    }
  }

  private resolveBoot(): void {
    if (this.state.page !== null) return;
    const probe = resolveRoute(readRoutePath(), window.location.search, []);
    if (
      probe.page === "palettes" ||
      probe.page === "screen" ||
      probe.page === "home" ||
      probe.page === "scenes" ||
      probe.page === "scene"
    ) {
      const metas = buildMetas([]);
      const snap = readInitialSnapshot(metas);
      this.state.page =
        probe.page === "home"
          ? { name: "home" }
          : probe.page === "screen"
            ? { name: "screen" }
            : probe.page === "scenes"
              ? { name: "screen" }
              : probe.page === "scene"
                ? { name: "screen" }
                : { name: "palettes" };
      this.state.notice = "";
      const inner = readRouteSearch();
      replaceCanonicalPath(probe, snap, [], inner || window.location.search);
      this.state.snapshot = snap;
      this.emit();
    }
    if (this.catalog === null) return;
    this.pendingLocation = null;
    if (this.state.page !== null) return;
    const list = this.catalog;
    const metas = buildMetas(list);
    const route = resolveRoute(
      readRoutePath(),
      window.location.search,
      list.map((font) => font.id),
    );
    if (route.page === "variant") {
      window.history.replaceState(null, "", variantPathKeeping(route.font, route.variant, this.migrationBase()));
      this.state.page = { name: "variant", font: route.font, variant: route.variant };
      this.state.notice = "";
      this.emit();
      return;
    }
    let snap = readInitialSnapshot(metas);
    if (!metas.some((meta) => meta.id === snap.font)) {
      snap = { ...snap, font: metas[0]?.id ?? "" };
    }
    if (route.page === "font") {
      snap = { ...snap, font: route.font };
      if (!snap.families[route.font]) {
        const meta = metas.find((entry) => entry.id === route.font);
        if (meta) snap = { ...snap, families: { ...snap.families, [route.font]: defaultFamilySnapshot(meta) } };
      }
      this.state.page = { name: "preview", font: route.font };
      this.state.notice = "";
    } else if (
      route.page === "palettes" ||
      route.page === "screen" ||
      route.page === "home" ||
      route.page === "scenes" ||
      route.page === "scene"
    ) {
      this.state.page =
        route.page === "home"
          ? { name: "home" }
          : route.page === "screen"
            ? { name: "screen" }
            : route.page === "scenes"
              ? { name: "screen" }
              : route.page === "scene"
                ? { name: "screen" }
                : { name: "palettes" };
      this.state.notice = "";
    } else {
      this.state.page = { name: "index" };
      this.state.notice = route.notice ?? "";
    }
    const inner = readRouteSearch();
    replaceCanonicalPath(
      route.page === "index" ? { page: "index" } : route,
      snap,
      list.map((font) => font.id),
      inner || window.location.search,
    );
    this.state.snapshot = snap;
    this.emit();
  }
}

export function createNavigationOwner(onTransition?: () => void): NavigationOwner {
  return new NavigationOwner(onTransition);
}

export function readProvisionalRoute(): Route {
  // Render-time boot probe with no catalog: lets the shell select
  // catalog-independent pages before boot resolves. Pure read, no history
  // writes; canonicalization happens in the owner at its sync boundary.
  return resolveRoute(readRoutePath(), window.location.search, []);
}
