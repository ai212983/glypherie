// Autosaving per-variant draft: local edits render immediately, one
// debounced IndexedDB write at a time. The editor stays keyed by variant id;
// a newer variant prop only replaces a clean draft, never dirty local edits.
// A hard close before the last write lands is inherently unsaved.
import * as React from "react";
import type { FontVariant, VariantDraft } from "./model.js";
import { updateVariant } from "./repository.js";

export interface VariantDraftState {
  draft: VariantDraft;
  status: "saving" | "saved" | "error";
  error: Error | null;
  update: (patch: Partial<VariantDraft>) => void;
  retry: () => void;
  reload: () => void;
}

const SAVE_DELAY_MS = 300;

const draftJson = (draft: VariantDraft): string => JSON.stringify(draft);

function draftOf(variant: FontVariant): VariantDraft {
  return {
    name: variant.name,
    settings: { ...variant.settings, axes: { ...variant.settings.axes } },
    sampleText: variant.sampleText,
    inheritSampleText: variant.inheritSampleText ?? false,
  };
}

/** Called only with the hydrated variant; the editor component is keyed by id. */
export function useVariantDraft(variant: FontVariant): VariantDraftState {
  const [draft, setDraft] = React.useState<VariantDraft>(() => draftOf(variant));
  const [status, setStatus] = React.useState<"saving" | "saved" | "error">("saved");
  const [error, setError] = React.useState<Error | null>(null);

  const draftRef = React.useRef(draft);
  const variantRef = React.useRef(variant);
  variantRef.current = variant;
  const baseRef = React.useRef({ revision: variant.revision, json: draftJson(draftOf(variant)) });
  const inflightRef = React.useRef(false);
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = React.useRef(true);

  const startFlight = React.useCallback((payload: VariantDraft): void => {
    const target = variantRef.current;
    const expected = baseRef.current.revision;
    inflightRef.current = true;
    void updateVariant(
      target.id,
      {
        name: payload.name,
        settings: { ...payload.settings, axes: { ...payload.settings.axes } },
        sampleText: payload.sampleText,
        inheritSampleText: payload.inheritSampleText,
      },
      expected,
    ).then(
      (saved) => {
        const normalized = draftOf(saved);
        // Never regress the base: a newer prop may already have adopted a
        // later revision while this flight was in the air.
        if (saved.revision > baseRef.current.revision) {
          baseRef.current = { revision: saved.revision, json: draftJson(normalized) };
        }
        inflightRef.current = false;
        // A draft identical to the submitted payload holds no true edits: the
        // row only carries repository normalization (such as a live palette
        // depth change), so adopt it instead of re-flighting. Adopt only when
        // the base reflects this save.
        const current = draftRef.current;
        if (current && draftJson(current) !== baseRef.current.json) {
          if (draftJson(current) === draftJson(payload) && saved.revision >= baseRef.current.revision) {
            draftRef.current = normalized;
            if (!mountedRef.current) return;
            setDraft(normalized);
            setStatus("saved");
            setError(null);
            return;
          }
          startFlight(current);
          return;
        }
        if (!mountedRef.current) return;
        setStatus("saved");
        setError(null);
      },
      (failure: unknown) => {
        inflightRef.current = false;
        if (!mountedRef.current) return;
        setStatus("error");
        setError(failure instanceof Error ? failure : new Error(String(failure ?? "")));
      },
    );
  }, []);

  const sendIfDirty = React.useCallback((): void => {
    const current = draftRef.current;
    if (!current || draftJson(current) === baseRef.current.json) {
      if (mountedRef.current && current) {
        setStatus("saved");
        setError(null);
      }
      return;
    }
    startFlight(current);
  }, [startFlight]);

  const schedule = React.useCallback((): void => {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      if (inflightRef.current) return;
      sendIfDirty();
    }, SAVE_DELAY_MS);
  }, [sendIfDirty]);

  const update = React.useCallback((patch: Partial<VariantDraft>): void => {
    const prev = draftRef.current;
    if (!prev || !mountedRef.current) return;
    const next: VariantDraft = {
      name: patch.name ?? prev.name,
      settings: patch.settings ?? prev.settings,
      sampleText: patch.sampleText ?? prev.sampleText,
      inheritSampleText: patch.inheritSampleText ?? prev.inheritSampleText,
    };
    if (draftJson(next) === draftJson(prev)) return;
    draftRef.current = next;
    setDraft(next);
    setStatus("saving");
    setError(null);
    if (inflightRef.current) return;
    schedule();
  }, [schedule]);

  const retry = React.useCallback((): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const current = draftRef.current;
    if (!mountedRef.current || !current) return;
    if (draftJson(current) === baseRef.current.json) {
      setStatus("saved");
      setError(null);
      return;
    }
    setStatus("saving");
    setError(null);
    if (inflightRef.current) return;
    startFlight(current);
  }, [startFlight]);

  // Explicit UI action: discard the local draft and adopt the newest prop.
  const reload = React.useCallback((): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const latest = variantRef.current;
    const json = draftJson(draftOf(latest));
    baseRef.current = { revision: latest.revision, json };
    const next = draftOf(latest);
    draftRef.current = next;
    if (!mountedRef.current) return;
    setDraft(next);
    setStatus("saved");
    setError(null);
  }, []);

  // A newer prop replaces a clean draft, as does same-revision repository
  // normalization (a live palette depth change bumps no revision); dirty
  // local edits are never overwritten and surface a CAS conflict on save.
  // Never adopt while a write is in flight: a draft equal to the old base
  // can still have an uncommitted different payload in flight (changed then
  // reverted), and adopting the remote prop then would replace that intent.
  React.useEffect(() => {
    if (inflightRef.current) return;
    if (variant.revision < baseRef.current.revision) return;
    const current = draftRef.current;
    if (!current || draftJson(current) !== baseRef.current.json) return;
    const json = draftJson(draftOf(variant));
    if (variant.revision === baseRef.current.revision && json === baseRef.current.json) return;
    baseRef.current = { revision: variant.revision, json };
    const next = draftOf(variant);
    draftRef.current = next;
    setDraft(next);
    setStatus("saved");
    setError(null);
  }, [variant]);

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      // Last-chance send of the latest draft; an in-flight write drains it
      // on settle. All setters stay mount-guarded.
      if (!inflightRef.current) sendIfDirty();
    };
  }, [sendIfDirty]);

  return { draft, status, error, update, retry, reload };
}
