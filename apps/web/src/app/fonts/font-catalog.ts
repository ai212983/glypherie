import * as React from "react";
import { UserFacingError, userError } from "../user-error";
import { getDomainVersion, subscribeDomain } from "../domain/events.js";
import { ensureDomainMigrated } from "../domain/migrate.js";
import { listFonts, removeFont, saveFont, seedBundledFonts, type FontMetadata, type StoredFont } from "./storage.js";
import { BUNDLED_FONTS, relativeFontUrl } from "./bundled-fonts";

export interface UploadedFont {
  saved: StoredFont;
}

// Domain-owned library data: list, seeding, import, removal and metadata.
// Never touches renderer caches or session state; inspection needed for
// seeding/import arrives as an explicit narrow port from the caller.
export interface FontCatalog {
  fonts: StoredFont[] | null;
  seedNote: string;
  fontsError: string;
  retryFonts: () => void;
  importUpload: (file: File) => Promise<UploadedFont>;
  removeStoredData: (id: string) => Promise<void>;
}

interface CatalogArgs {
  inspect: ((bytes: ArrayBuffer) => Promise<FontMetadata>) | null;
  rendererAvailable: boolean | null;
}

// A data query must not depend on renderer cache state: the list stays
// uninitialized until the seed attempt settles, so route resolution never
// runs against a partial catalog and genuine font URLs cannot fall back to
// the library mid-seed.
export function useFontCatalog({ inspect, rendererAvailable }: CatalogArgs): FontCatalog {
  const [fontsQueryError, setFontsQueryError] = React.useState("");
  const [fontsAttempt, setFontsAttempt] = React.useState(0);
  const [seedSettled, setSeedSettled] = React.useState(false);
  const domainVersion = React.useSyncExternalStore(subscribeDomain, getDomainVersion);
  const [fonts, setFonts] = React.useState<StoredFont[] | null>(null);
  const [seedNote, setSeedNote] = React.useState("");

  const retryFonts = React.useCallback(() => {
    setFontsQueryError("");
    setFontsAttempt((value) => value + 1);
  }, []);

  React.useEffect(() => {
    if (!seedSettled) {
      setFonts(null);
      return;
    }
    let live = true;
    void listFonts().then(
      (list) => {
        if (!live) return;
        setFontsQueryError("");
        setFonts(list);
      },
      (error: unknown) => {
        if (!live) return;
        setFontsQueryError(userError(error, "Couldn’t load fonts."));
        setFonts(null);
      },
    );
    return () => {
      live = false;
    };
  }, [fontsAttempt, seedSettled, domainVersion]);

  React.useEffect(() => {
    // An unavailable renderer still settles boot so the stored library stays
    // accessible; only seeding needs the live renderer for inspection.
    if (rendererAvailable === null) return;
    if (rendererAvailable === false || !inspect) {
      setSeedSettled(true);
      return;
    }
    const inspectFonts = inspect;
    let cancelled = false;
    (async () => {
      try {
        // Legacy Dexie rows migrate into the domain store first, so seeding
        // keys off the migrated marker and never duplicates imported fonts.
        await ensureDomainMigrated();
      } catch (error) {
        if (!cancelled) setSeedNote(userError(error, "Couldn’t migrate saved fonts."));
      }
      try {
        await seedBundledFonts(
          BUNDLED_FONTS.map(({ url, name, fileName }) => ({ url: relativeFontUrl(url), name, fileName })),
          async (bytes: ArrayBuffer) => inspectFonts(bytes),
        );
      } catch (error) {
        if (!cancelled) setSeedNote(userError(error, "Couldn’t load bundled fonts."));
      }
      // The font list arrives through the reactive query above: it runs its
      // post-readiness read only after this boundary, atomically past seeding.
      if (!cancelled) setSeedSettled(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [inspect, rendererAvailable]);

  const importUpload = React.useCallback(
    async (file: File): Promise<UploadedFont> => {
      const bytes = await file.arrayBuffer();
      let metadata: FontMetadata;
      try {
        if (!inspect) throw new Error("The preview renderer is unavailable.");
        metadata = await inspect(bytes.slice(0));
      } catch (error) {
        throw new UserFacingError(userError(error, `Couldn’t import ${file.name}.`), { cause: error });
      }
      const names = metadata.names ?? {};
      const fallback = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
      const name =
        (typeof names.full === "string" && names.full.trim()) ||
        (typeof names.family === "string" && names.family.trim()) ||
        fallback ||
        file.name;
      let saved: StoredFont;
      try {
        saved = await saveFont({ bytes, fileName: file.name, name, metadata, source: "uploaded" });
      } catch (error) {
        throw new UserFacingError(userError(error, `Couldn’t import ${file.name}.`), { cause: error });
      }
      // The reactive font query picks up the new row; no manual refresh.
      return { saved };
    },
    [inspect],
  );

  const removeStoredData = React.useCallback(async (id: string): Promise<void> => {
    // Backend removal cascades the font's variants atomically; the reactive
    // queries drop both without a manual refresh.
    await removeFont(id);
  }, []);

  return {
    fonts,
    seedNote,
    fontsError: fontsQueryError,
    retryFonts,
    importUpload,
    removeStoredData,
  };
}
