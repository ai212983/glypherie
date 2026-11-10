import * as React from "react";
import type { StoredFont } from "./storage.js";
import { useRenderer } from "../renderer/renderer-context.js";
import { useFontCatalog, type FontCatalog, type UploadedFont } from "./font-catalog";
import { useRendererFontReadiness } from "./renderer-readiness";
import type { FontLoadStatus, RendererFontReadiness } from "./renderer-readiness-core";

export type { UploadedFont };
export type { FontCatalog };
export type { FontLoadStatus, RendererFontReadiness };
export type { StoredFont };
export type { FontLoadState } from "./renderer-readiness-core";

// Composed facade kept for migration: catalog owns domain list/seeding/
// import/remove/metadata, readiness owns session-specific loading/cache/
// status. New consumers take `catalog` or `readiness` explicitly; the flat
// fields below serve components that still take the whole library.
export interface FontLibrary {
  fonts: StoredFont[] | null;
  rendererAvailable: boolean | null;
  loadedIds: ReadonlySet<string>;
  bootError: string;
  seedNote: string;
  ensureLoaded: (ids: string | readonly string[]) => void;
  loadStatus: (id: string) => FontLoadStatus;
  importUpload: (file: File) => Promise<UploadedFont>;
  removeStored: (id: string) => Promise<void>;
  retryFonts: () => void;
  catalog: FontCatalog;
  readiness: RendererFontReadiness;
}

export function useFontLibrary(): FontLibrary {
  // The render worker is owned by RendererProvider; readiness only consumes
  // its service/session/availability, never creating or terminating one.
  const { service: client, session, available } = useRenderer();
  const inspect = React.useMemo(() => (client ? (bytes: ArrayBuffer) => client.inspect(bytes) : null), [client]);
  const catalog = useFontCatalog({ inspect, rendererAvailable: available });
  const readiness = useRendererFontReadiness({ service: client, session, available });

  const removeStored = React.useCallback(
    async (id: string): Promise<void> => {
      // Deletion owns the font across the domain await: unload targets the
      // originating worker only while its session is still current.
      await readiness.removeFont(id, () => catalog.removeStoredData(id));
    },
    [catalog, readiness],
  );

  // A failed ping still exposes stored fonts with the renderer unavailable;
  // only seeding and loading need the live renderer.
  const bootError = (available === false ? "Preview unavailable." : "") || catalog.fontsError;
  return {
    fonts: catalog.fonts,
    rendererAvailable: readiness.rendererAvailable,
    loadedIds: readiness.loadedIds,
    bootError,
    seedNote: catalog.seedNote,
    ensureLoaded: readiness.ensureLoaded,
    loadStatus: readiness.loadStatus,
    importUpload: catalog.importUpload,
    removeStored,
    retryFonts: catalog.retryFonts,
    catalog,
    readiness,
  };
}
