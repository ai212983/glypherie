import { userError } from "./user-error";
import * as React from "react";
import type { StoredFont } from "./fonts/storage.js";
import { DisplayPreferencesProvider, useDisplayPreferences } from "./shell/DisplayPreferences";
import { useNavigation } from "./navigation/useNavigation";
import { previewVariantSettings } from "./features/preview/state/snapshot-codec.js";
import { indexPath, palettesPath, screenPath } from "./navigation/router";
import { metaForFont } from "./features/preview/state/family-meta";
import { useFontLibrary } from "./fonts/useFontLibrary";
import { displayName } from "./fonts/metadata";
import { createVariant } from "./variants/repository.js";
import { GrayscalePage } from "./features/grayscale/GrayscalePage";
import { ScreenPage } from "./features/screen/ScreenPage";
import { LandingPage } from "./features/landing/LandingPage";
import { LibraryPage } from "./features/library/LibraryPage";
import {
  readStoredLibraryPreferences,
  writeStoredLibraryPreferences,
  type LibraryPreferences,
} from "./features/library/preferences";
import { FontPage } from "./features/preview/FontPage";
import { VariantPage } from "./features/variants/VariantPage";
import { NavLink } from "../components/NavLink";
import { PrimaryNav } from "./shell/PrimaryNav";
import { SiteHeader } from "./shell/SiteHeader";
import { SkipLink } from "./shell/SkipLink";
import { PageMetadata, PublicPageMetadata } from "./shell/PageMetadata";
import { PREVIEW_DESCRIPTION } from "./shell/page-metadata";

export function App(): React.JSX.Element {
  return (
    <DisplayPreferencesProvider>
      <AppContent />
    </DisplayPreferencesProvider>
  );
}

function AppContent(): React.JSX.Element {
  const {
    zoom,
    canvas: { palette: indexPalette, inverse: indexInverse },
  } = useDisplayPreferences();
  const library = useFontLibrary();
  const [previewStatus, setPreviewStatus] = React.useState("");
  const [importStatus, setImportStatus] = React.useState("");
  const [libraryPreferences, setLibraryPreferences] = React.useState(readStoredLibraryPreferences);
  const { text: indexText, baseSize: indexBaseSize } = libraryPreferences;
  const [indexFilter, setIndexFilter] = React.useState("");
  const [savingVariant, setSavingVariant] = React.useState(false);
  const [saveVariantError, setSaveVariantError] = React.useState("");

  const clearFeatureStatus = React.useCallback((): void => {
    setPreviewStatus("");
    setSaveVariantError("");
  }, []);
  // Location interpretation, canonicalization, deferred snapshot writes and
  // history changes live in the navigation owner; this composes providers
  // and pages with feature actions and notices.
  const navigation = useNavigation({ fonts: library.fonts, onTransition: clearFeatureStatus });
  const {
    page,
    snapshot,
    role,
    notice,
    detailNotice,
    applySnapshot,
    onPatch,
    openPreview,
    openVariantId,
    openIndex,
    openPalettes,
    openScreen,
    onRole,
    removePreviewFont,
    migrationBase,
    provisionalRoute,
  } = navigation;

  const onLibraryPreferences = (patch: Partial<LibraryPreferences>): void => {
    const next = { ...libraryPreferences, ...patch };
    setLibraryPreferences(next);
    writeStoredLibraryPreferences(next);
  };

  const primaryNav = (active: "fonts" | "palettes" | "screen" | null): React.JSX.Element => (
    <PrimaryNav
      active={active}
      fontsHref={indexPath(migrationBase())}
      palettesHref={palettesPath(migrationBase())}
      screenHref={screenPath(migrationBase())}
      onFonts={() => openIndex()}
      onPalettes={openPalettes}
      onScreen={openScreen}
    />
  );

  const pageName = page?.name;
  const pageFont = page?.name === "preview" || page?.name === "variant" ? page.font : null;
  const ensureDetailLoaded = library.ensureLoaded;
  React.useEffect(() => {
    if ((pageName === "preview" || pageName === "variant") && pageFont) ensureDetailLoaded(pageFont);
  }, [pageName, pageFont, ensureDetailLoaded]);

  const onDeleteFont = (target: StoredFont): void => {
    const name = displayName(target);
    void (async () => {
      try {
        await library.removeStored(target.id);
        removePreviewFont(target.id);
        openIndex(`Removed ${name}.`);
      } catch (error) {
        setPreviewStatus(userError(error, "Couldn’t delete font."));
      }
    })();
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
          results.push(`Imported ${saved.name}.`);
        } catch (error) {
          results.push(userError(error, `Couldn’t import ${file.name}.`));
        }
      }
      setImportStatus(results.join(" "));
    })();
  };

  const onAddVariant = React.useCallback(
    async (target: StoredFont): Promise<void> => {
      const created = await createVariant(target.id);
      openVariantId(created.fontId, created.id);
    },
    [openVariantId],
  );

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

  // Provisional boot route from the navigation owner: catalog-independent
  // pages render before boot resolves. Render stays pure; canonicalization
  // happens in the owner at its synchronization boundary.
  const provisional = page === null ? provisionalRoute() : null;

  if (page?.name === "home" || provisional?.page === "home") {
    return (
      <>
        <SkipLink />
        <PublicPageMetadata page="home" />
        <LandingPage nav={primaryNav(null)} fontsHref={indexPath(migrationBase())} onFonts={() => openIndex()} />
      </>
    );
  }

  if (page?.name === "palettes" || provisional?.page === "palettes") {
    return (
      <>
        <SkipLink />
        <PublicPageMetadata page="palettes" />
        <div className="flex flex-col lg:h-dvh lg:overflow-hidden">
          <div className="sticky top-0 z-40 shrink-0">
            <SiteHeader title="Glypherie" titleAs="div" variant="brand" nav={primaryNav("palettes")} />
          </div>
          <main id="main" className="w-full flex-1 lg:flex lg:min-h-0 lg:flex-col">
            <h1 className="sr-only">Palettes</h1>
            <GrayscalePage embedded baseSize={indexBaseSize} />
          </main>
        </div>
      </>
    );
  }

  // The unified Screen page serves the canonical /screen/ route and the
  // legacy /scenes/ and /scene/<id>/ links: they open the default
  // composition, and the navigation effects canonicalize the URL directly to
  // /screen/ without scene selection, never from inside this render.
  const legacyScenesRoute = provisional?.page === "scenes";
  const legacySceneRoute = provisional?.page === "scene" ? provisional : null;
  const screenRoute =
    page?.name === "screen" || legacyScenesRoute || legacySceneRoute !== null || provisional?.page === "screen";

  if (screenRoute) {
    return (
      <>
        <SkipLink />
        {legacySceneRoute !== null ? (
          <PageMetadata
            title="Screen — Glypherie"
            description="Edit saved compositions on device screens: labels, text styles, bitmap preview and Playdate font export."
          />
        ) : (
          <PublicPageMetadata page="screen" />
        )}
        <div className="flex h-full min-h-0 flex-col overflow-hidden">
          <div className="sticky top-0 z-40 shrink-0">
            <SiteHeader title="Glypherie" titleAs="div" variant="brand" nav={primaryNav("screen")} />
          </div>
          <main id="main" className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
            <h1 className="sr-only">Screen</h1>
            <ScreenPage library={library} />
          </main>
        </div>
      </>
    );
  }

  if (library.fonts === null || page === null) {
    return (
      <>
        <PageMetadata
          title={`${library.bootError ? "Couldn’t load font library" : "Loading font library"} — Glypherie`}
          description={PREVIEW_DESCRIPTION}
        />
        <SiteHeader title="Glypherie" titleAs="div" variant="brand" nav={primaryNav("fonts")} />
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] leading-[1.6]">
          <h1 className="sr-only">Font library</h1>
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
        <PublicPageMetadata page="fonts" />
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
          readiness={library.readiness}
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
          readiness={library.readiness}
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
        <PageMetadata title="Loading font preview — Glypherie" description={PREVIEW_DESCRIPTION} />
        <SiteHeader title="Glypherie" titleAs="div" variant="brand" nav={primaryNav("fonts")} />
        <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] leading-[1.6]">
          <h1 className="sr-only">Font preview</h1>
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
          <PageMetadata title="Font not found — Glypherie" description={PREVIEW_DESCRIPTION} />
          <h1 className="m-0 text-[clamp(1.8rem,3vw,2.25rem)] font-[650] tracking-[-.035em]">Font not found</h1>
          <section className="content-state my-12 leading-[1.6]" role="alert">
            <h2>Font not found</h2>
            <p>
              <NavLink href={indexPath(migrationBase())} data-all-fonts onNavigate={() => openIndex()}>
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
          readiness={library.readiness}
          fonts={fonts}
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
