import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import type { FontVariant } from "../../variants/model.js";
import { displayName } from "../../fonts/metadata";
import { useAllVariants } from "../../variants/useFontVariants.js";
import { FontCard } from "./FontCard";
import { LibrarySidebar } from "./LibrarySidebar";
import { QuickFilter } from "./QuickFilter";
import { SiteHeader } from "../../shell/SiteHeader";
import type { FontLibrary } from "../../fonts/useFontLibrary";
import type { CanvasPaletteId } from "./canvas-palettes";
import type { LibraryBaseSize } from "./preferences";

const FILTER_NAME_KEYS = ["family", "full", "style", "subfamily", "postscript"] as const;

export function matchesFontFilter(font: StoredFont, query: string): boolean {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const names = font.metadata?.names ?? {};
  const haystack = [displayName(font), font.name, font.fileName, ...FILTER_NAME_KEYS.map((key) => names[key])]
    .filter((value): value is string => typeof value === "string")
    .join("\n")
    .toLowerCase();
  return terms.every((term) => haystack.includes(term));
}

interface LibraryPageProps {
  nav?: React.ReactNode;
  fonts: StoredFont[];
  notice: string;
  seedNote: string;
  importStatus: string;
  sampleText: string;
  sampleBaseSize: LibraryBaseSize;
  sampleZoom: number;
  samplePalette: CanvasPaletteId;
  sampleInverse: boolean;
  filter: string;
  library: FontLibrary;
  onAddVariant: (font: StoredFont) => Promise<void>;
  onOpenVariant: (font: StoredFont, variant: FontVariant) => void;
  onDeleteFont: (font: StoredFont) => void;
  onImport: (files: FileList | null) => void;
  onFilter: (filter: string) => void;
  onSampleText: (text: string) => void;
  onSampleBaseSize: (size: LibraryBaseSize) => void;
}

export function LibraryPage({
  nav, fonts, notice, seedNote, importStatus, sampleText, sampleBaseSize, sampleZoom, samplePalette, sampleInverse, filter, library,
  onAddVariant, onOpenVariant, onDeleteFont, onImport, onFilter, onSampleText, onSampleBaseSize,
}: LibraryPageProps): React.JSX.Element {
  const { ensureLoaded, rendererAvailable, loadedIds } = library;
  // One reactive query for every saved variant; variant writes never touch
  // the fonts store, so the card previews below never reload binaries.
  const variantState = useAllVariants();
  const byFont = React.useMemo(() => {
    const grouped = new Map<string, FontVariant[]>();
    for (const variant of variantState.variants) {
      const list = grouped.get(variant.fontId) ?? [];
      list.push(variant);
      grouped.set(variant.fontId, list);
    }
    return grouped;
  }, [variantState.variants]);
  // Only generated variants need native font loading; Source uses FontFace.
  React.useEffect(() => {
    const ids = [...byFont.keys()];
    if (ids.length > 0) ensureLoaded(ids);
  }, [byFont, ensureLoaded, rendererAvailable, loadedIds]);
  const visibleFonts = React.useMemo(
    () => fonts.filter((font) => matchesFontFilter(font, filter)),
    [fonts, filter],
  );
  return (
    <div className="flex flex-col lg:h-dvh lg:overflow-hidden">
      <div className="sticky top-0 z-40 shrink-0">
        <SiteHeader
          title="Glypherie"
          titleAs="div"
          variant="brand"
          nav={nav}
          search={<QuickFilter value={filter} onChange={onFilter} />}
        />
      </div>
      <main id="main" className="w-full flex-1 lg:flex lg:min-h-0 lg:flex-col">
        <h1 className="sr-only">Font library</h1>
        {notice && (
          <p className="mx-6 mt-5 max-w-[45rem] text-[.875rem] leading-[1.55]" role="alert" data-route-notice>
            {notice}
          </p>
        )}
        {seedNote && (
          <p className="intro mx-6 mt-5 text-[.875rem] leading-[1.55] text-soft" role="status">{seedNote}</p>
        )}
        {variantState.status === "error" && (
          <p className="mx-6 mt-5 max-w-[45rem] text-[.875rem] leading-[1.55]" role="alert" data-variant-list-error>
            {variantState.message}{" "}
            <button type="button" className="underline" data-variant-list-retry onClick={variantState.retry}>
              Retry
            </button>
          </p>
        )}
        <div className="flex min-h-[calc(100dvh-56px)] flex-col lg:min-h-0 lg:flex-1 lg:flex-row lg:overflow-hidden">
          <LibrarySidebar
            sampleText={sampleText}
            sampleBaseSize={sampleBaseSize}
            importStatus={importStatus}
            onSampleText={onSampleText}
            onSampleBaseSize={onSampleBaseSize}
            onImport={onImport}
          />
          <section aria-label="Font library" data-library-scroll className="min-w-0 flex-1 bg-studio-inset p-6 lg:h-full lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain">
            {fonts.length === 0 ? (
              <div className="content-state my-12 max-w-[45rem] leading-[1.6]">
                <h2>No fonts</h2>
                <p>Import a .ttf or .otf file.</p>
              </div>
            ) : visibleFonts.length === 0 ? (
              <div className="mx-auto my-0 w-full max-w-[60rem]">
                <div className="content-state my-12 max-w-[45rem] leading-[1.6]">
                  <h2>No matching fonts</h2>
                  <button type="button" className="underline" data-clear-filter onClick={() => onFilter("")}>
                    Clear filter
                  </button>
                </div>
              </div>
            ) : (
              <ul className="font-cards mx-auto my-0 grid w-full max-w-[60rem] grid-cols-1 list-none gap-6 p-0" data-font-cards>
                {visibleFonts.map((font) => (
                  <li key={font.id} className="min-w-0">
                    <FontCard
                      font={font}
                      text={sampleText}
                      baseSize={sampleBaseSize}
                      zoom={sampleZoom}
                      palette={samplePalette}
                      inverse={sampleInverse}
                      library={library}
                      variants={variantState.status === "loading" ? undefined : (byFont.get(font.id) ?? [])}
                      onAddVariant={onAddVariant}
                      onOpenVariant={onOpenVariant}
                      onDeleteFont={onDeleteFont}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
