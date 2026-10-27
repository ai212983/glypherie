import { readRoutePath } from "./navigation/location";
import { userError } from "./user-error";
import * as React from "react";
import type { StoredFont } from "./fonts/storage.js";
import type { RendererRole } from "./renderer/renderer-types.js";
import { DisplayPreferencesProvider, useDisplayPreferences } from "./shell/DisplayPreferences";
import {
  canonicalPathFor,
  hasPendingSnapshotWrite,
  readRouteSearch,
  readInitialSnapshot,
  readRoleParam,
  replaceCanonicalPath,
  scheduleSnapshotWrite,
  cancelSnapshotWrite,
  writeRoleParam,
  writeSnapshotNow,
  type PreviewSnapshot,
} from "./navigation/snapshot";
import {
  defaultFamilySnapshot,
  parseLegacyState,
  parseUrlSnapshot,
  previewVariantSettings,
} from "./features/preview/state/snapshot-codec.js";
import {
  buildMetas,
  metaForFont,
} from "./features/preview/state/family-meta";
import { indexPath, palettesPath, resolveRoute, variantPathKeeping } from "./navigation/router";
import { useFontLibrary } from "./fonts/useFontLibrary";
import { displayName } from "./fonts/metadata";
import { createVariant } from "./variants/repository.js";
import { GrayscalePage } from "./features/grayscale/GrayscalePage";
import { LandingPage } from "./features/landing/LandingPage";
import { LibraryPage } from "./features/library/LibraryPage";
import { readStoredLibraryPreferences, writeStoredLibraryPreferences, type LibraryPreferences } from "./features/library/preferences";
import { FontPage } from "./features/preview/FontPage";
import { VariantPage } from "./features/variants/VariantPage";
import { NavLink } from "../components/NavLink";
import { PrimaryNav } from "./shell/PrimaryNav";
import { SiteHeader } from "./shell/SiteHeader";
import { SkipLink } from "./shell/SkipLink";

type Page =
  | { name: "home" }
  | { name: "palettes" }
  | { name: "index" }
  | { name: "preview"; font: string }
  | { name: "variant"; font: string; variant: string };

export function App(): React.JSX.Element {
  return <DisplayPreferencesProvider><AppContent /></DisplayPreferencesProvider>;
}

function AppContent(): React.JSX.Element {
  const { zoom, canvas: { palette: indexPalette, inverse: indexInverse } } = useDisplayPreferences();
  const library = useFontLibrary();
  const [page, setPage] = React.useState<Page | null>(null);
  const [snapshot, setSnapshot] = React.useState<PreviewSnapshot | null>(null);
  const [role, setRole] = React.useState<RendererRole>(() => {
    const inner = readRouteSearch();
    return readRoleParam(inner || window.location.search);
  });
  const [previewStatus, setPreviewStatus] = React.useState("");
  const [importStatus, setImportStatus] = React.useState("");
  const [detailNotice, setDetailNotice] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [libraryPreferences, setLibraryPreferences] = React.useState(readStoredLibraryPreferences);
  const { text: indexText, baseSize: indexBaseSize } = libraryPreferences;
  const [indexFilter, setIndexFilter] = React.useState("");
  const [savingVariant, setSavingVariant] = React.useState(false);
  const [saveVariantError, setSaveVariantError] = React.useState("");

  const onLibraryPreferences = (patch: Partial<LibraryPreferences>): void => {
    const next = { ...libraryPreferences, ...patch };
    setLibraryPreferences(next);
    writeStoredLibraryPreferences(next);
  };

  const fontsRef = React.useRef<StoredFont[] | null>(null);
  fontsRef.current = library.fonts;
  const snapshotRef = React.useRef<PreviewSnapshot | null>(null);
  snapshotRef.current = snapshot;
  const pageRef = React.useRef<Page | null>(null);
  pageRef.current = page;
  const handledHref = React.useRef("");

  const applySnapshot = React.useCallback((next: PreviewSnapshot, immediate = false) => {
    setSnapshot(next);
    const order = (fontsRef.current ?? []).map((font) => font.id);
    if (immediate) writeSnapshotNow(next, order);
    else scheduleSnapshotWrite(next, order);
  }, []);

  const onPatch = React.useCallback((patch: Partial<PreviewSnapshot>, immediate = false) => {
    const current = snapshotRef.current;
    if (!current) return;
    applySnapshot({ ...current, ...patch }, immediate);
  }, [applySnapshot]);

  const pushPath = React.useCallback((path: string): void => {
    // History entries carry identity only. Saved variant settings always
    // come from IndexedDB, never from history state, so Back cannot restore
    // stale settings over the database.
    window.history.pushState(null, "", path);
    handledHref.current = window.location.href;
  }, []);

  const migrationBase = (): string => {
    const inner = readRouteSearch();
    return inner || window.location.search;
  };

  // Unsaved per-font preview. Legacy outer queries and family fragments land
  // here. Navigation is plain route identity; the database owns variant
  // settings, so leaving an editor needs no flush gate.
  const openPreview = React.useCallback((id: string, knownFont?: StoredFont) => {
    const list = fontsRef.current ?? [];
    const target = knownFont ?? list.find((font) => font.id === id);
    if (!target) return;
    cancelSnapshotWrite();
    const metas = buildMetas(list);
    const base = snapshotRef.current ?? readInitialSnapshot(metas);
    const next: PreviewSnapshot = { ...base, font: id };
    if (!next.families[id]) {
      const meta = metaForFont(target);
      next.families = { ...next.families, [id]: defaultFamilySnapshot(meta) };
    }
    setSnapshot(next);
    setPage({ name: "preview", font: id });
    setNotice("");
    setPreviewStatus("");
    setDetailNotice("");
    setSaveVariantError("");
    pushPath(canonicalPathFor({ page: "font", font: id }, next, list.map((font) => font.id), migrationBase()));
  }, [pushPath]);

  const openVariantId = React.useCallback((fontId: string, variantId: string) => {
    cancelSnapshotWrite();
    setPage({ name: "variant", font: fontId, variant: variantId });
    setNotice("");
    setPreviewStatus("");
    setDetailNotice("");
    setSaveVariantError("");
    pushPath(variantPathKeeping(fontId, variantId, migrationBase()));
  }, [pushPath]);

  const openIndex = React.useCallback((message = "") => {
    cancelSnapshotWrite();
    setPage({ name: "index" });
    setNotice(message);
    setPreviewStatus("");
    setDetailNotice("");
    setSaveVariantError("");
    pushPath(indexPath(migrationBase()));
  }, [pushPath]);

  const openPalettes = React.useCallback(() => {
    cancelSnapshotWrite();
    setPage({ name: "palettes" });
    setNotice("");
    setPreviewStatus("");
    setDetailNotice("");
    setSaveVariantError("");
    pushPath(palettesPath(migrationBase()));
  }, [pushPath]);

  const primaryNav = (active: "fonts" | "palettes" | null): React.JSX.Element => (
    <PrimaryNav
      active={active}
      fontsHref={indexPath(migrationBase())}
      palettesHref={palettesPath(migrationBase())}
      onFonts={() => openIndex()}
      onPalettes={openPalettes}
    />
  );

  React.useEffect(() => {
    if (pageRef.current === null) {
      const probe = resolveRoute(readRoutePath(), window.location.search, []);
      if (probe.page === "palettes" || probe.page === "home") {
        const metas = buildMetas([]);
        const snap = readInitialSnapshot(metas);
        setPage(probe.page === "home" ? { name: "home" } : { name: "palettes" });
        setNotice("");
        const inner = readRouteSearch();
        replaceCanonicalPath(probe, snap, [], inner || window.location.search);
        setSnapshot(snap);
      }
    }
    if (library.fonts === null) return;
    if (pageRef.current !== null) return;
    const list = library.fonts;
    const metas = buildMetas(list);
    const route = resolveRoute(readRoutePath(), window.location.search, list.map((font) => font.id));
    if (route.page === "variant") {
      window.history.replaceState(null, "", variantPathKeeping(route.font, route.variant, migrationBase()));
      setPage({ name: "variant", font: route.font, variant: route.variant });
      setNotice("");
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
      setPage({ name: "preview", font: route.font });
      setNotice("");
    } else if (route.page === "palettes" || route.page === "home") {
      setPage(route.page === "home" ? { name: "home" } : { name: "palettes" });
      setNotice("");
    } else {
      setPage({ name: "index" });
      setNotice(route.notice ?? "");
    }
    const inner = readRouteSearch();
    replaceCanonicalPath(
      route.page === "index" ? { page: "index" } : route,
      snap,
      list.map((font) => font.id),
      inner || window.location.search,
    );
    setSnapshot(snap);
  }, [library.fonts]);

  React.useEffect(() => {
    const onRouteChange = (): void => {
      if (window.location.href === handledHref.current) return;
      cancelSnapshotWrite();
      const libraryPending = fontsRef.current === null;
      const list = fontsRef.current ?? [];
      const metas = buildMetas(list);
      const route = resolveRoute(readRoutePath(), window.location.search, list.map((font) => font.id));
      const inner = readRouteSearch();
      setRole(readRoleParam(inner || window.location.search));
      setPreviewStatus("");
      setDetailNotice("");
      setSaveVariantError("");
      const order = list.map((font) => font.id);
      const base = readRouteSearch() || window.location.search;
      if (route.page === "palettes" || route.page === "home") {
        const current = snapshotRef.current ?? readInitialSnapshot(metas);
        replaceCanonicalPath(route, current, order, base);
        if (!snapshotRef.current) setSnapshot(current);
        setPage(route.page === "home" ? { name: "home" } : { name: "palettes" });
        setNotice("");
      } else if (libraryPending) {
        return;
      } else if (route.page === "variant") {
        window.history.replaceState(null, "", variantPathKeeping(route.font, route.variant, base));
        setPage({ name: "variant", font: route.font, variant: route.variant });
        setNotice("");
      } else if (route.page === "font") {
        const search = readRouteSearch();
        const params = new URLSearchParams(search);
        if (params.get("v") === "1") {
          let snap = parseUrlSnapshot(search, "", metas, {
            font: route.font, profile: "mono_1bit",
          }) ?? readInitialSnapshot(metas);
          if (!metas.some((meta) => meta.id === snap.font)) snap = { ...snap, font: metas[0]?.id ?? "" };
          snap = { ...snap, font: route.font };
          replaceCanonicalPath({ page: "font", font: route.font }, snap, order, base);
          setSnapshot(snap);
        } else {
          const current = snapshotRef.current;
          if (current) {
            const legacy = parseLegacyState(window.location.search, window.location.hash, metas);
            const next: PreviewSnapshot = { ...current, font: route.font };
            if (legacy.profile) next.profile = legacy.profile;
            if (!next.families[route.font]) {
              const meta = metas.find((entry) => entry.id === route.font);
              if (meta) next.families = { ...next.families, [route.font]: defaultFamilySnapshot(meta) };
            }
            replaceCanonicalPath({ page: "font", font: route.font }, next, order, base);
            setSnapshot(next);
          } else {
            let snap = readInitialSnapshot(metas);
            snap = { ...snap, font: route.font };
            replaceCanonicalPath({ page: "font", font: route.font }, snap, order, base);
            setSnapshot(snap);
          }
        }
        setPage({ name: "preview", font: route.font });
        setNotice("");
      } else {
        const current = snapshotRef.current;
        if (current) replaceCanonicalPath({ page: "index" }, current, order, base);
        setPage({ name: "index" });
        setNotice(route.notice ?? "");
      }
      handledHref.current = window.location.href;
    };
    window.addEventListener("popstate", onRouteChange);
    window.addEventListener("hashchange", onRouteChange);
    return () => {
      window.removeEventListener("popstate", onRouteChange);
      window.removeEventListener("hashchange", onRouteChange);
    };
  }, []);

  React.useEffect(() => {
    const onHide = (): void => {
      const current = snapshotRef.current;
      if (current && hasPendingSnapshotWrite()) {
        writeSnapshotNow(current, (fontsRef.current ?? []).map((font) => font.id));
      }
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
    };
  }, []);

  const pageName = page?.name;
  const pageFont = page?.name === "preview" || page?.name === "variant" ? page.font : null;
  const ensureDetailLoaded = library.ensureLoaded;
  React.useEffect(() => {
    if ((pageName === "preview" || pageName === "variant") && pageFont) ensureDetailLoaded(pageFont);
  }, [pageName, pageFont, ensureDetailLoaded]);

  const onRole = (next: RendererRole): void => {
    setRole(next);
    writeRoleParam(next);
  };

  const onImport = (files: FileList | null): void => {
    const selected = Array.from(files ?? []);
    if (selected.length === 0) return;
    void (async () => {
      const results: string[] = [];
      for (const file of selected) {
        setImportStatus(`Importing ${file.name}…`);
        try {
          const { saved } = await library.importUpload(file);
          // Imports land on the library with the imported card; no variant is
          // created automatically.
          results.push(`Imported ${saved.name}.`);
        } catch (error) {
          results.push(userError(error, `Couldn’t import ${file.name}.`));
        }
      }
      setImportStatus(results.join(" "));
    })();
  };

  const onDeleteFont = (target: StoredFont): void => {
    const name = displayName(target);
    void (async () => {
      try {
        await library.removeStored(target.id);
        const current = snapshotRef.current;
        if (current) {
          const families = { ...current.families };
          delete families[target.id];
          const remaining = (fontsRef.current ?? []).filter((font) => font.id !== target.id);
          const next: PreviewSnapshot = { ...current, families };
          if (!remaining.some((font) => font.id === next.font)) {
            next.font = remaining[0]?.id ?? "";
          }
          setSnapshot(next);
        }
        openIndex(`Removed ${name}.`);
      } catch (error) {
        setPreviewStatus(userError(error, "Couldn’t delete font."));
      }
    })();
  };

  // Add variant creates the default saved variant first, then navigates only
  // after the write commits.
  const onAddVariant = React.useCallback(async (target: StoredFont): Promise<void> => {
    const created = await createVariant(target.id);
    openVariantId(created.fontId, created.id);
  }, [openVariantId]);

  const onSaveAsVariant = React.useCallback((): void => {
    if (page?.name !== "preview" || !snapshot) return;
    const active = (library.fonts ?? []).find((font) => font.id === page.font);
    const family = snapshot.families[page.font];
    if (!active || !family) return;
    if (savingVariant) return;
    setSavingVariant(true);
    setSaveVariantError("");
    void (async () => {
      try {
        const created = await createVariant(active.id, {
          settings: previewVariantSettings(family, snapshot, role),
          sampleText: family.text,
        });
        setSavingVariant(false);
        openVariantId(created.fontId, created.id);
      } catch (error) {
        setSavingVariant(false);
        setSaveVariantError(userError(error, "Couldn’t save variant."));
      }
    })();
  }, [library.fonts, openVariantId, page, role, savingVariant, snapshot]);

  if (page?.name === "home"
    || (page === null && resolveRoute(readRoutePath(), window.location.search, []).page === "home")) {
    return (
      <>
        <SkipLink />
        <LandingPage nav={primaryNav(null)} fontsHref={indexPath(migrationBase())} onFonts={() => openIndex()} />
      </>
    );
  }

  if (page?.name === "palettes"
    || (page === null && resolveRoute(readRoutePath(), window.location.search, []).page === "palettes")) {
    return (
      <>
        <SkipLink />
        <div className="flex flex-col lg:h-dvh lg:overflow-hidden">
          <div className="sticky top-0 z-40 shrink-0">
            <SiteHeader
              title="Glypherie"
              variant="brand"
              nav={primaryNav("palettes")}
            />
          </div>
          <main id="main" className="w-full flex-1 lg:flex lg:min-h-0 lg:flex-col">
            <GrayscalePage embedded baseSize={indexBaseSize} />
          </main>
        </div>
      </>
    );
  }

  if (library.fonts === null || page === null) {
    return (
      <>
        <SiteHeader title="Glypherie" variant="brand" nav={primaryNav("fonts")} />
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] leading-[1.6]">
          {library.bootError ? (
            <p role="alert" data-library-error>
              {library.bootError}{" "}
              <button type="button" className="underline" data-library-retry onClick={library.retryFonts}>
                Retry
              </button>
            </p>
          ) : (
            <p role="status">Loading font library…</p>
          )}
        </main>
      </>
    );
  }

  const fonts = library.fonts;

  if (page.name === "index") {
    return (
      <>
        <SkipLink />
        <LibraryPage
          nav={primaryNav("fonts")}
          fonts={fonts}
          notice={notice || library.bootError}
          seedNote={library.seedNote}
          importStatus={importStatus}
          sampleText={indexText}
          sampleBaseSize={indexBaseSize}
          sampleZoom={zoom}
          samplePalette={indexPalette}
          sampleInverse={indexInverse}
          filter={indexFilter}
          library={library}
          onAddVariant={onAddVariant}
          onOpenVariant={(font, variant) => openVariantId(font.id, variant.id)}
          onDeleteFont={onDeleteFont}
          onImport={onImport}
          onFilter={setIndexFilter}
          onSampleText={(text) => onLibraryPreferences({ text })}
          onSampleBaseSize={(baseSize) => onLibraryPreferences({ baseSize })}
        />
      </>
    );
  }

  if (page.name === "variant") {
    const active = fonts.find((font) => font.id === page.font) ?? null;
    return (
      <>
        <SkipLink />
        <VariantPage
          key={page.font}
          nav={primaryNav("fonts")}
          font={active}
          variantId={page.variant}
          baseSize={indexBaseSize}
          rootSampleText={indexText}
          library={library}
          onIndex={() => openIndex()}
          onOpenVariantId={openVariantId}
          onVariantDeleted={(name) => openIndex(`Deleted variant ${name}.`)}
          onAddVariant={onAddVariant}
        />
      </>
    );
  }

  if (snapshot === null) {
    return (
      <>
        <SiteHeader title="Glypherie" variant="brand" nav={primaryNav("fonts")} />
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] leading-[1.6]">
          <p role="status">Loading font preview…</p>
        </main>
      </>
    );
  }

  const active = fonts.find((font) => font.id === page.font) ?? null;
  const activeMeta = active ? metaForFont(active) : null;

  return (
    <>
      <SkipLink />
      {!active || !activeMeta ? (
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] max-w-[45rem] leading-[1.6]">
          <h1 className="m-0 text-[clamp(1.8rem,3vw,2.25rem)] font-[650] tracking-[-.035em]">Font preview</h1>
          <section className="content-state my-12 leading-[1.6]" role="alert">
            <h2>Font not found</h2>
            <p>
              <NavLink
                href={indexPath(migrationBase())}
                data-all-fonts
                onNavigate={() => openIndex()}
              >
                All fonts
              </NavLink>{" "}
            </p>
          </section>
        </main>
      ) : (
        <FontPage
          nav={primaryNav("fonts")}
          font={active}
          meta={activeMeta}
          snapshot={snapshot}
          role={role}
          previewStatus={previewStatus}
          notice={detailNotice}
          library={library}
          onSnapshot={applySnapshot}
          onPatch={onPatch}
          onRole={onRole}
          onStatus={setPreviewStatus}
          onOpenFont={(id) => openPreview(id)}
          onIndex={() => openIndex()}
          onDelete={() => onDeleteFont(active)}
          onSaveAsVariant={onSaveAsVariant}
          savingVariant={savingVariant}
          saveVariantError={saveVariantError}
        />
      )}
    </>
  );
}
