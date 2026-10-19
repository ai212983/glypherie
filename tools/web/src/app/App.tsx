import * as React from "react";
import type { StoredFont } from "./fonts/storage.js";
import type { RendererRole } from "./renderer/renderer-types.js";
import {
  canonicalHashFor,
  hasPendingSnapshotWrite,
  readHashSearch,
  readInitialSnapshot,
  readRoleParam,
  replaceCanonicalHash,
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
} from "./features/preview/state/snapshot-codec.js";
import {
  buildMetas,
  metaForFont,
} from "./features/preview/state/family-meta";
import { indexHash, resolveRoute, splitHash, variantHashKeeping } from "./navigation/router";
import { TEXT_DEFAULT } from "./renderer/render-spec";
import { useFontLibrary } from "./fonts/useFontLibrary";
import { displayName } from "./fonts/metadata";
import { createVariant } from "./variants/repository.js";
import { LibraryPage } from "./features/library/LibraryPage";
import { FontPage } from "./features/preview/FontPage";
import { VariantPage } from "./features/variants/VariantPage";
import { NavLink } from "../components/NavLink";
import { SiteHeader } from "./shell/SiteHeader";
import { SkipLink } from "./shell/SkipLink";

type Page =
  | { name: "index" }
  | { name: "preview"; font: string }
  | { name: "variant"; font: string; variant: string };

export function App(): React.JSX.Element {
  const library = useFontLibrary();
  const [page, setPage] = React.useState<Page | null>(null);
  const [snapshot, setSnapshot] = React.useState<PreviewSnapshot | null>(null);
  const [role, setRole] = React.useState<RendererRole>(() => {
    const inner = splitHash(window.location.hash).search;
    return readRoleParam(inner || window.location.search);
  });
  const [previewStatus, setPreviewStatus] = React.useState("");
  const [importStatus, setImportStatus] = React.useState("");
  const [detailNotice, setDetailNotice] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [ratio, setRatio] = React.useState(() => Number(window.devicePixelRatio) || 1);
  const [indexText, setIndexText] = React.useState(TEXT_DEFAULT);
  const [indexZoom, setIndexZoom] = React.useState(1);
  const [savingVariant, setSavingVariant] = React.useState(false);
  const [saveVariantError, setSaveVariantError] = React.useState("");

  const fontsRef = React.useRef<StoredFont[] | null>(null);
  fontsRef.current = library.fonts;
  const snapshotRef = React.useRef<PreviewSnapshot | null>(null);
  snapshotRef.current = snapshot;
  const pageRef = React.useRef<Page | null>(null);
  pageRef.current = page;

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

  const pushHash = React.useCallback((hash: string): void => {
    // History entries carry identity only. Saved variant settings always
    // come from IndexedDB, never from history state, so Back cannot restore
    // stale settings over the database.
    window.history.pushState(null, "", `${window.location.pathname}${window.location.search}${hash}`);
  }, []);

  const migrationBase = (): string => {
    const inner = readHashSearch();
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
    pushHash(canonicalHashFor({ page: "font", font: id }, next, list.map((font) => font.id), migrationBase()));
  }, [pushHash]);

  const openVariantId = React.useCallback((fontId: string, variantId: string) => {
    cancelSnapshotWrite();
    setPage({ name: "variant", font: fontId, variant: variantId });
    setNotice("");
    setPreviewStatus("");
    setDetailNotice("");
    setSaveVariantError("");
    pushHash(variantHashKeeping(fontId, variantId, migrationBase()));
  }, [pushHash]);

  const openIndex = React.useCallback((message = "") => {
    cancelSnapshotWrite();
    setPage({ name: "index" });
    setNotice(message);
    setPreviewStatus("");
    setDetailNotice("");
    setSaveVariantError("");
    pushHash(indexHash(migrationBase()));
  }, [pushHash]);

  React.useEffect(() => {
    if (library.fonts === null) return;
    if (pageRef.current !== null) return;
    const list = library.fonts;
    const metas = buildMetas(list);
    const route = resolveRoute(window.location.hash, window.location.search, list.map((font) => font.id));
    if (route.page === "variant") {
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
    } else {
      setPage({ name: "index" });
      setNotice(route.notice ?? "");
    }
    const inner = readHashSearch();
    replaceCanonicalHash(
      route.page === "font" ? route : { page: "index" },
      snap,
      list.map((font) => font.id),
      inner || window.location.search,
    );
    setSnapshot(snap);
  }, [library.fonts]);

  const handledHref = React.useRef("");
  React.useEffect(() => {
    const onRouteChange = (): void => {
      if (window.location.href === handledHref.current) return;
      cancelSnapshotWrite();
      const list = fontsRef.current ?? [];
      if (!list.length) return;
      const metas = buildMetas(list);
      const route = resolveRoute(window.location.hash, window.location.search, list.map((font) => font.id));
      const inner = readHashSearch();
      setRole(readRoleParam(inner || window.location.search));
      setPreviewStatus("");
      setDetailNotice("");
      setSaveVariantError("");
      const order = list.map((font) => font.id);
      const base = readHashSearch() || window.location.search;
      if (route.page === "variant") {
        setPage({ name: "variant", font: route.font, variant: route.variant });
        setNotice("");
      } else if (route.page === "font") {
        const { search } = splitHash(window.location.hash);
        const params = new URLSearchParams(search);
        if (params.get("v") === "1") {
          let snap = parseUrlSnapshot(search, "", metas, {
            font: route.font, profile: "mono_1bit", zoom: 1,
          }) ?? readInitialSnapshot(metas);
          if (!metas.some((meta) => meta.id === snap.font)) snap = { ...snap, font: metas[0]?.id ?? "" };
          snap = { ...snap, font: route.font };
          replaceCanonicalHash({ page: "font", font: route.font }, snap, order, base);
          setSnapshot(snap);
        } else {
          const current = snapshotRef.current;
          if (current) {
            const legacy = parseLegacyState(window.location.search, window.location.hash, metas);
            const next: PreviewSnapshot = { ...current, font: route.font };
            if (legacy.profile) next.profile = legacy.profile;
            if (legacy.zoom !== undefined) next.zoom = legacy.zoom;
            if (!next.families[route.font]) {
              const meta = metas.find((entry) => entry.id === route.font);
              if (meta) next.families = { ...next.families, [route.font]: defaultFamilySnapshot(meta) };
            }
            replaceCanonicalHash({ page: "font", font: route.font }, next, order, base);
            setSnapshot(next);
          } else {
            let snap = readInitialSnapshot(metas);
            snap = { ...snap, font: route.font };
            replaceCanonicalHash({ page: "font", font: route.font }, snap, order, base);
            setSnapshot(snap);
          }
        }
        setPage({ name: "preview", font: route.font });
        setNotice("");
      } else {
        const current = snapshotRef.current;
        if (current) replaceCanonicalHash({ page: "index" }, current, order, base);
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
    const onRatio = (): void => setRatio(Number(window.devicePixelRatio) || 1);
    const onHide = (): void => {
      const current = snapshotRef.current;
      if (current && hasPendingSnapshotWrite()) {
        writeSnapshotNow(current, (fontsRef.current ?? []).map((font) => font.id));
      }
    };
    window.addEventListener("resize", onRatio);
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("resize", onRatio);
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
    const file = files?.[0];
    if (!file) return;
    setImportStatus(`Importing ${file.name}…`);
    void (async () => {
      try {
        const { saved } = await library.importUpload(file);
        // Imports land on the library with the imported card; no variant is
        // created automatically.
        setImportStatus(`Imported ${saved.name}.`);
      } catch (error) {
        setImportStatus(error instanceof Error ? error.message : String(error ?? ""));
      }
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
        setPreviewStatus(error instanceof Error ? error.message : String(error ?? ""));
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
          settings: {
            sizePx: family.size,
            axes: { ...family.axes },
            letterSpacingPx: family.spacing,
            profile: snapshot.profile,
            kerning: snapshot.kerning,
            stemFitting: snapshot.stemFitting,
            renderer: role,
          },
          sampleText: family.text,
        });
        setSavingVariant(false);
        openVariantId(created.fontId, created.id);
      } catch (error) {
        setSavingVariant(false);
        setSaveVariantError(error instanceof Error ? error.message : String(error ?? ""));
      }
    })();
  }, [library.fonts, openVariantId, page, role, savingVariant, snapshot]);

  if (library.fonts === null || page === null) {
    return (
      <>
        <SiteHeader
          eyebrow={<p className="eyebrow m-0 text-[.75rem] tracking-[.1em] uppercase">Font workshop</p>}
          title="Font preview"
        />
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] leading-[1.6]">
          {library.bootError ? (
            <p role="alert" data-library-error>
              Font library could not be loaded: {library.bootError}{" "}
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
          fonts={fonts}
          notice={notice || library.bootError}
          seedNote={library.seedNote}
          importStatus={importStatus}
          sampleText={indexText}
          sampleZoom={indexZoom}
          library={library}
          onAddVariant={onAddVariant}
          onOpenVariant={(font, variant) => openVariantId(font.id, variant.id)}
          onDeleteFont={onDeleteFont}
          onImport={onImport}
          onSampleText={setIndexText}
          onSampleZoom={setIndexZoom}
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
          key={`${page.font}/${page.variant}`}
          font={active}
          variantId={page.variant}
          library={library}
          ratio={ratio}
          onIndex={() => openIndex()}
          onOpenVariantId={openVariantId}
          onVariantDeleted={(name) => openIndex(`Deleted variant ${name}.`)}
        />
      </>
    );
  }

  if (snapshot === null) {
    return (
      <>
        <SiteHeader
          eyebrow={<p className="eyebrow m-0 text-[.75rem] tracking-[-.035em]">Font workshop</p>}
          title="Font preview"
        />
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
            <h2>This font is no longer in the library.</h2>
            <p>{notice || "It may have been removed in another tab."} Return to{" "}
              <NavLink
                href={`${window.location.pathname}#/`}
                data-all-fonts
                onNavigate={() => openIndex()}
              >
                All fonts
              </NavLink>{" "}
              to pick another.
            </p>
          </section>
        </main>
      ) : (
        <FontPage
          font={active}
          meta={activeMeta}
          snapshot={snapshot}
          role={role}
          ratio={ratio}
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
