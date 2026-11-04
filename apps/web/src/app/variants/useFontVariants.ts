// Reactive saved-variant queries over the domain graph. Reads go through
// the repository facade (split entities assembled to the legacy DTO); the
// version counter re-runs each query after committed writes, including
// cross-tab broadcasts, without manual refresh calls.

import * as React from "react";
import { subscribeDomain, getDomainVersion } from "../domain/events.js";
import { userError } from "../user-error";
import type { FontVariant } from "./model.js";
import { getVariant, listVariants } from "./repository.js";

function useDomainVersion(): number {
  return React.useSyncExternalStore(subscribeDomain, getDomainVersion);
}

function useQueryAttempt(): { attempt: number; retry: () => void } {
  const [attempt, setAttempt] = React.useState(0);
  const retry = React.useCallback(() => setAttempt((value) => value + 1), []);
  return { attempt, retry };
}

function queryMessage(error: unknown): string {
  return userError(error, "Couldn’t load saved variants.");
}

export interface LiveVariantList {
  status: "loading" | "error" | "ready";
  variants: FontVariant[];
  message: string;
  retry: () => void;
}

function useVariantList(fontId?: string): LiveVariantList {
  const { attempt, retry } = useQueryAttempt();
  const version = useDomainVersion();
  const [state, setState] = React.useState<{ status: "loading" | "error" | "ready"; variants: FontVariant[]; message: string }>(
    { status: "loading", variants: [], message: "" },
  );
  React.useEffect(() => {
    let live = true;
    void listVariants(fontId).then(
      (variants) => {
        if (live) setState({ status: "ready", variants, message: "" });
      },
      (error: unknown) => {
        if (live) setState({ status: "error", variants: [], message: queryMessage(error) });
      },
    );
    return () => { live = false; };
  }, [fontId, attempt, version]);
  return { ...state, retry };
}

/** Every saved variant, with an explicit error state plus retry. */
export function useAllVariants(): LiveVariantList {
  return useVariantList();
}

export function useFontVariants(fontId: string): LiveVariantList {
  return useVariantList(fontId);
}

export type LiveVariant =
  | { status: "loading" }
  | { status: "error"; message: string; retry: () => void }
  | { status: "missing" }
  | { status: "ready"; variant: FontVariant };

/** One saved variant by id, distinguishing loading, error, and deleted/missing. */
export function useLiveVariant(id: string): LiveVariant {
  const { attempt, retry } = useQueryAttempt();
  const version = useDomainVersion();
  const [state, setState] = React.useState<LiveVariant>({ status: "loading" });
  React.useEffect(() => {
    let live = true;
    void getVariant(id).then(
      (variant) => {
        if (!live) return;
        setState(variant ? { status: "ready", variant } : { status: "missing" });
      },
      (error: unknown) => {
        if (live) setState({ status: "error", message: queryMessage(error), retry });
      },
    );
    return () => { live = false; };
  }, [id, attempt, version, retry]);
  return state;
}
