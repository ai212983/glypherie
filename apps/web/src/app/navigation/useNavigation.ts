import * as React from "react";
import type { StoredFont } from "../fonts/storage.js";
import {
  createNavigationOwner,
  readProvisionalRoute,
  type NavigationOwner,
  type NavigationSnapshot,
  type Page,
  type PreviewSnapshot,
  type RendererRole,
  type Route,
} from "./navigation-owner.ts";

export type { NavigationSnapshot, Page };

// Only meaningful intents and snapshot reach consumers; catalog/history
// wiring stays private to the adapter.
export interface Navigation extends NavigationSnapshot {
  applySnapshot: (next: PreviewSnapshot, immediate?: boolean) => void;
  onPatch: (patch: Partial<PreviewSnapshot>, immediate?: boolean) => void;
  openPreview: (id: string, knownFont?: StoredFont) => void;
  openVariantId: (fontId: string, variantId: string) => void;
  openIndex: (message?: string) => void;
  openPalettes: () => void;
  openScreen: () => void;
  onRole: (next: RendererRole) => void;
  removePreviewFont: (targetId: string) => PreviewSnapshot | null;
  migrationBase: () => string;
  provisionalRoute: () => Route;
}

// Thin React adapter: the NavigationOwner holds location interpretation,
// canonicalization, deferred snapshot writes and history changes. This binds
// browser events and the owner subscription; App composes providers and
// pages with feature actions and notices.
export function useNavigation({
  fonts,
  onTransition,
}: {
  fonts: StoredFont[] | null;
  onTransition?: () => void;
}): Navigation {
  const ownerRef = React.useRef<NavigationOwner | null>(null);
  if (!ownerRef.current) {
    ownerRef.current = createNavigationOwner(onTransition);
  }
  const owner = ownerRef.current;
  const snapshot = React.useSyncExternalStore(owner.subscribe, owner.getSnapshot);

  React.useEffect(() => {
    owner.setCatalog(fonts);
  }, [owner, fonts]);

  React.useEffect(() => {
    const onRouteChange = (): void => {
      owner.handleHistoryChange();
    };
    window.addEventListener("popstate", onRouteChange);
    window.addEventListener("hashchange", onRouteChange);
    return () => {
      window.removeEventListener("popstate", onRouteChange);
      window.removeEventListener("hashchange", onRouteChange);
    };
  }, [owner]);

  React.useEffect(() => {
    const onHide = (): void => {
      owner.flushForHide();
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
    };
  }, [owner]);

  React.useEffect(() => () => owner.dispose(), [owner]);

  return React.useMemo(
    () => ({
      ...snapshot,
      applySnapshot: owner.applySnapshotIntent.bind(owner),
      onPatch: owner.onPatch.bind(owner),
      openPreview: owner.openPreview.bind(owner),
      openVariantId: owner.openVariantId.bind(owner),
      openIndex: owner.openIndex.bind(owner),
      openPalettes: owner.openPalettes.bind(owner),
      openScreen: owner.openScreen.bind(owner),
      onRole: owner.onRole.bind(owner),
      removePreviewFont: owner.removePreviewFont.bind(owner),
      migrationBase: () => owner.migrationBase(),
      provisionalRoute: () => readProvisionalRoute(),
    }),
    [owner, snapshot],
  );
}
