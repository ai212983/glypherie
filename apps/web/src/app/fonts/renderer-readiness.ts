import * as React from "react";
import { getFont, updateFontMetadata } from "./storage.ts";
import {
  RendererFontReadinessStore,
  type FontLoadStatus,
  type ReadinessService,
  type RendererFontReadiness,
} from "./renderer-readiness-core.ts";

export type { ReadinessService, RendererFontReadiness } from "./renderer-readiness-core.ts";

const EMPTY_IDS: ReadonlySet<string> = new Set<string>();

const IDLE_STATUS: FontLoadStatus = { state: "idle", error: "" };

interface ReadinessHookArgs {
  service: ReadinessService | null;
  session: number;
  available: boolean | null;
}

// Thin React adapter over the framework-free readiness core: this binds the
// renderer session/availability and the domain byte/metadata ports, and
// exposes the subscribed snapshot. It never creates or terminates workers
// and owns no second cache; RendererProvider keeps the worker lifetime.
export function useRendererFontReadiness({ service, session, available }: ReadinessHookArgs): RendererFontReadiness {
  const storeRef = React.useRef<RendererFontReadinessStore | null>(null);
  if (!storeRef.current) {
    // Inspection here only reads stored bytes and metadata; the domain-owned
    // rows stay the single source of truth for the library list.
    storeRef.current = new RendererFontReadinessStore({
      readFont: async (id: string) => {
        const stored = await getFont(id);
        if (!stored) return null;
        return { bytes: stored.bytes, hints: stored.metadata.font_hints };
      },
      updateHints: (id: string, metadata) => updateFontMetadata(id, metadata),
      service: null,
    });
  }
  const store = storeRef.current;
  const snapshot = React.useSyncExternalStore(store.subscribe, store.getSnapshot);
  const sessionRef = React.useRef(session);
  const lifetimeRef = React.useRef(0);

  // Mount lifetime token: setup-cleanup-setup retires the old setup's
  // operations without ever reviving them, and unmount retires everything.
  React.useEffect(() => {
    lifetimeRef.current += 1;
    const owned = lifetimeRef.current;
    return () => {
      if (lifetimeRef.current === owned) {
        lifetimeRef.current += 1;
        store.dispose();
      }
    };
  }, [store]);

  React.useEffect(() => {
    store.updateService(service);
  }, [store, service]);

  React.useEffect(() => {
    sessionRef.current = session;
    store.replaceSession();
  }, [store, session]);

  // Readiness is only ever exposed for the current renderer session: until
  // the reset effect commits after a replacement, the exposed sets stay
  // empty even though the store still holds the previous session's values.
  const committed = sessionRef.current === session;

  const ensureLoaded = React.useCallback(
    (ids: string | readonly string[]) => {
      if (sessionRef.current !== session) return;
      store.ensureLoaded(ids, available !== true);
    },
    [store, session, available],
  );

  const loadStatus = React.useCallback(
    (id: string): FontLoadStatus => (committed ? (snapshot.statuses[id] ?? IDLE_STATUS) : IDLE_STATUS),
    [snapshot, committed],
  );

  const invalidateFont = React.useCallback(
    (id: string) => {
      store.invalidateFont(id);
    },
    [store],
  );

  const removeFont = React.useCallback(
    (id: string, removeData: () => Promise<void>) => store.removeFont(id, removeData),
    [store],
  );

  return React.useMemo(
    () => ({
      rendererAvailable: available,
      loadedIds: committed ? snapshot.loadedIds : EMPTY_IDS,
      ensureLoaded,
      loadStatus,
      invalidateFont,
      removeFont,
    }),
    [available, committed, snapshot, ensureLoaded, loadStatus, invalidateFont, removeFont],
  );
}
