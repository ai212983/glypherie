import { UserFacingError, userError } from "../user-error";
import * as React from "react";
import { useLiveQuery } from "dexie-react-hooks";
import {
  getFont,
  listFonts,
  removeFont,
  saveFont,
  seedBundledFonts,
  updateFontMetadata,
  type StoredFont,
} from "./storage.js";
import { BUNDLED_FONTS, relativeFontUrl } from "./bundled-fonts";
import { useRenderer } from "../renderer/renderer-context.js";

export interface UploadedFont {
  saved: StoredFont;
}

export type FontLoadState = "idle" | "loading" | "ready" | "error";

const EMPTY_IDS: ReadonlySet<string> = new Set<string>();

export interface FontLoadStatus {
  state: FontLoadState;
  error: string;
}

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
}

export function useFontLibrary(): FontLibrary {
  // The render worker is owned by RendererProvider; this hook only consumes
  // it for inspection and font loading, never creating or terminating one.
  const { service: client, session, available } = useRenderer();
  const rendererAvailable = available;
  // Reactive font list: variant writes touch only the variants store, so
  // editing a variant never re-reads font binaries. Worker load state below
  // stays separate from this database data.
  const [fontsQueryError, setFontsQueryError] = React.useState("");
  const [fontsAttempt, setFontsAttempt] = React.useState(0);
  // Boot readiness: the font list stays uninitialized until the seed attempt
  // settles, so route resolution never runs against a partial catalog and
  // genuine font URLs cannot fall back to the library mid-seed.
  const [seedSettled, setSeedSettled] = React.useState(false);
  const retryFonts = React.useCallback(() => {
    setFontsQueryError("");
    setFontsAttempt((value) => value + 1);
  }, []);
  const liveFonts = useLiveQuery(
    async (): Promise<StoredFont[] | null> => {
      if (!seedSettled) return null;
      try {
        const list = await listFonts();
        setFontsQueryError("");
        return list;
      } catch (error) {
        setFontsQueryError(userError(error, "Couldn’t load fonts."));
        return null;
      }
    },
    [fontsAttempt, seedSettled],
    undefined,
  );
  const fonts = liveFonts === undefined ? null : liveFonts;
  const [loadedIds, setLoadedIds] = React.useState<ReadonlySet<string>>(new Set());
  const [seedNote, setSeedNote] = React.useState("");
  const [loadStates, setLoadStates] = React.useState<Record<string, FontLoadStatus>>({});
  const loadingRef = React.useRef(new Set<string>());
  const failedRef = React.useRef(new Set<string>());
  const loadedRef = React.useRef(new Set<string>());
  const generationRef = React.useRef<Record<string, number>>({});
  const sessionRef = React.useRef(session);
  const lifetimeRef = React.useRef(0);

  // Mount lifetime token: each setup owns the operations it starts. Replay
  // (setup-cleanup-setup) retires the old setup's operations without ever
  // reviving them, and unmount retires everything.
  React.useEffect(() => {
    lifetimeRef.current += 1;
    const owned = lifetimeRef.current;
    return () => {
      if (lifetimeRef.current === owned) lifetimeRef.current += 1;
    };
  }, []);

  // Readiness below is only ever exposed for the current renderer session:
  // until the reset effect commits after a replacement, the exposed sets stay
  // empty even though state still holds the previous session's values.
  const sessionCommitted = sessionRef.current === session;
  const exposedLoadedIds = sessionCommitted ? loadedIds : EMPTY_IDS;

  const loadStatus = React.useCallback((id: string): FontLoadStatus => {
    if (sessionRef.current !== session) return { state: "idle", error: "" };
    return loadStates[id] ?? { state: "idle", error: "" };
  }, [loadStates, session]);

  // A new renderer session starts with an empty worker-side font cache, so
  // readiness cached for the previous worker is dropped and its in-flight
  // loads no longer complete.
  React.useEffect(() => {
    sessionRef.current = session;
    generationRef.current = {};
    loadingRef.current = new Set<string>();
    failedRef.current = new Set<string>();
    loadedRef.current = new Set<string>();
    setLoadedIds(new Set<string>());
    setLoadStates({});
  }, [session]);

  React.useEffect(() => {
    // An unavailable renderer still settles boot so the stored library stays
    // accessible; only seeding needs the live renderer for inspection.
    if (rendererAvailable === null) return;
    if (rendererAvailable === false || !client) {
      setSeedSettled(true);
      return;
    }
    const renderer = client;
    let cancelled = false;
    (async () => {
      try {
        await seedBundledFonts(
          BUNDLED_FONTS.map(({ url, name, fileName }) => ({ url: relativeFontUrl(url), name, fileName })),
          async (bytes: ArrayBuffer) => renderer.inspect(bytes),
        );
      } catch (error) {
        if (!cancelled) setSeedNote(userError(error, "Couldn’t load bundled fonts."));
      }
      // The font list arrives through the reactive query above: it runs its
      // post-readiness read only after this boundary, atomically past seeding.
      if (!cancelled) setSeedSettled(true);
    })();
    return () => { cancelled = true; };
  }, [client, session, rendererAvailable]);

  const ensureLoaded = React.useCallback((ids: string | readonly string[]) => {
    if (!client || rendererAvailable !== true) return;
    const renderer = client;
    const wanted = session;
    const loaded = loadedRef.current;
    const targets = [...new Set(Array.isArray(ids) ? ids : [ids])]
      .filter((id) => !loaded.has(id) && !loadingRef.current.has(id) && !failedRef.current.has(id));
    if (targets.length === 0) return;
    for (const id of targets) {
      loadingRef.current.add(id);
      setLoadStates((prev) => ({ ...prev, [id]: { state: "loading", error: "" } }));
    }
    void (async () => {
      await Promise.all(targets.map(async (id) => {
        const generation = generationRef.current[id] ?? 0;
        const epoch = lifetimeRef.current;
        const live = (): boolean =>
          lifetimeRef.current === epoch && sessionRef.current === wanted && (generationRef.current[id] ?? 0) === generation;
        try {
          const stored = await getFont(id);
          if (!live()) return;
          if (!stored) throw new Error("Font data is missing from the library.");
          if (stored.metadata.font_hints === undefined) {
            const metadata = await renderer.inspect(stored.bytes.slice(0));
            if (!live()) return;
            await updateFontMetadata(id, metadata);
            if (!live()) return;
          }
          await renderer.load(id, stored.bytes.slice(0));
          if (!live()) return;
          loadedRef.current.add(id);
          setLoadedIds(new Set(loadedRef.current));
          setLoadStates((prev) => ({ ...prev, [id]: { state: "ready", error: "" } }));
        } catch (error) {
          if (!live()) return;
          failedRef.current.add(id);
          setLoadStates((prev) => ({
            ...prev,
            [id]: { state: "error", error: userError(error, "Couldn’t load font.") },
          }));
        } finally {
          if (live()) loadingRef.current.delete(id);
        }
      }));
    })();
  }, [client, session, rendererAvailable]);

  const importUpload = React.useCallback(async (file: File): Promise<UploadedFont> => {
    const bytes = await file.arrayBuffer();
    let metadata;
    try {
      if (!client) throw new Error("The preview renderer is unavailable.");
      metadata = await client.inspect(bytes.slice(0));
    } catch (error) {
      throw new UserFacingError(userError(error, `Couldn’t import ${file.name}.`), { cause: error });
    }
    const names = (metadata as { names?: Record<string, string | null> }).names ?? {};
    const fallback = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
    const name = (typeof names.full === "string" && names.full.trim())
      || (typeof names.family === "string" && names.family.trim())
      || fallback || file.name;
    let saved: StoredFont;
    try {
      saved = await saveFont({ bytes, fileName: file.name, name, metadata, source: "uploaded" });
    } catch (error) {
      throw new UserFacingError(userError(error, `Couldn’t import ${file.name}.`), { cause: error });
    }
    // The reactive font query picks up the new row; no manual refresh.
    return { saved };
  }, [client]);

  const removeStored = React.useCallback(async (id: string): Promise<void> => {
    generationRef.current[id] = (generationRef.current[id] ?? 0) + 1;
    // Backend removal cascades the font's variants atomically; the reactive
    // queries drop both without a manual refresh.
    await removeFont(id);
    await client?.unload(id).catch(() => undefined);
    loadingRef.current.delete(id);
    failedRef.current.delete(id);
    loadedRef.current.delete(id);
    setLoadedIds(new Set(loadedRef.current));
    setLoadStates((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, [client]);

  // A failed ping still exposes stored fonts with the renderer unavailable;
  // only seeding and loading need the live renderer.
  const bootError = (rendererAvailable === false ? "Preview unavailable." : "") || fontsQueryError;
  return {
    fonts, rendererAvailable, loadedIds: exposedLoadedIds, bootError, seedNote,
    ensureLoaded, loadStatus, importUpload, removeStored, retryFonts,
  };
}
