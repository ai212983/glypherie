import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import type { FontVariant } from "../../variants/model.js";
import { useAllVariants } from "../../variants/useFontVariants.js";
import { FontCard } from "./FontCard";
import { LibrarySidebar } from "./LibrarySidebar";
import { SiteHeader } from "../../shell/SiteHeader";
import { Badge } from "../../../components/ui/badge";
import type { FontLibrary } from "../../fonts/useFontLibrary";

interface LibraryPageProps {
  fonts: StoredFont[];
  notice: string;
  seedNote: string;
  importStatus: string;
  sampleText: string;
  sampleZoom: number;
  library: FontLibrary;
  onAddVariant: (font: StoredFont) => Promise<void>;
  onOpenVariant: (font: StoredFont, variant: FontVariant) => void;
  onDeleteFont: (font: StoredFont) => void;
  onImport: (files: FileList | null) => void;
  onSampleText: (text: string) => void;
  onSampleZoom: (zoom: number) => void;
}

export function LibraryPage({
  fonts, notice, seedNote, importStatus, sampleText, sampleZoom, library,
  onAddVariant, onOpenVariant, onDeleteFont, onImport, onSampleText, onSampleZoom,
}: LibraryPageProps): React.JSX.Element {
  const { ensureLoaded, rendererAvailable, loadedIds } = library;
  React.useEffect(() => {
    if (fonts.length > 0) ensureLoaded(fonts.map((font) => font.id));
  }, [fonts, ensureLoaded, rendererAvailable, loadedIds]);
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
  return (
    <>
      <SiteHeader
        eyebrow={<p className="eyebrow m-0 text-[.75rem] tracking-[.1em] uppercase">Font workshop</p>}
        title="Font preview"
        sub={
          <p className="variant mt-[.4rem] flex items-center gap-[.65rem] text-[.8rem] text-soft">
            <Badge variant="secondary">local preview</Badge>
          </p>
        }
      />
      <main id="main" className="mx-auto w-[min(100%-3rem,1440px)]">
        {notice && (
          <p className="mt-5 max-w-[45rem] text-[.875rem] leading-[1.55]" role="alert" data-route-notice>
            {notice}
          </p>
        )}
        {seedNote && (
          <p className="intro m-0 mt-5 text-[.875rem] leading-[1.55] text-soft" role="status">{seedNote}</p>
        )}
        {variantState.status === "error" && (
          <p className="mt-5 max-w-[45rem] text-[.875rem] leading-[1.55]" role="alert" data-variant-list-error>
            Saved variants could not be loaded: {variantState.message}{" "}
            <button type="button" className="underline" data-variant-list-retry onClick={variantState.retry}>
              Retry
            </button>
          </p>
        )}
        <div className="flex flex-col gap-8 py-8 lg:flex-row">
          <LibrarySidebar
            sampleText={sampleText}
            sampleZoom={sampleZoom}
            importStatus={importStatus}
            onSampleText={onSampleText}
            onSampleZoom={onSampleZoom}
            onImport={onImport}
          />
          <section aria-label="Font library" className="min-w-0 flex-1">
            {fonts.length === 0 ? (
              <div className="content-state my-12 max-w-[45rem] leading-[1.6]">
                <h2>No fonts in the library yet.</h2>
                <p>Import a TrueType or OpenType file to begin. Bundled fonts seed automatically on first launch.</p>
              </div>
            ) : (
              <ul className="font-cards m-0 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3" data-font-cards>
                {fonts.map((font) => (
                  <li key={font.id} className="min-w-0">
                    <FontCard
                      font={font}
                      text={sampleText}
                      zoom={sampleZoom}
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
    </>
  );
}
