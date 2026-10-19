// Reactive IndexedDB queries for saved font variants.
//
// All reads go through the repository so the schema keeps its single owner
// (app/database.ts). dexie-react-hooks re-runs each query when its observed
// tables change, including writes committed from another tab, per
// https://dexie.org/docs/dexie-react-hooks/useLiveQuery() — the editor and
// the library stay current without manual refresh calls.
//
// Query failures are caught into explicit error states with a retry that
// re-runs the query: the installed dexie-react-hooks build surfaces
// observable errors by throwing during render, so without this the app would
// white-screen instead of recovering.
import * as React from "react";
import { useLiveQuery } from "dexie-react-hooks";
import type { FontVariant } from "./model.js";
import { getVariant, listVariants } from "./repository.js";

function useQueryAttempt(): { attempt: number; retry: () => void } {
  const [attempt, setAttempt] = React.useState(0);
  const retry = React.useCallback(() => setAttempt((value) => value + 1), []);
  return { attempt, retry };
}

function queryMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error ?? "");
}

export interface LiveVariantList {
  status: "loading" | "error" | "ready";
  variants: FontVariant[];
  message: string;
  retry: () => void;
}

/** Every saved variant, with an explicit error state plus retry. */
export function useAllVariants(): LiveVariantList {
  const { attempt, retry } = useQueryAttempt();
  const row = useLiveQuery(
    async (): Promise<{ ok: true; variants: FontVariant[] } | { ok: false; message: string }> => {
      try {
        return { ok: true, variants: await listVariants() };
      } catch (error) {
        return { ok: false, message: queryMessage(error) };
      }
    },
    [attempt],
    undefined,
  );
  if (row === undefined) return { status: "loading", variants: [], message: "", retry };
  if (!row.ok) return { status: "error", variants: [], message: row.message, retry };
  return { status: "ready", variants: row.variants, message: "", retry };
}

export type LiveVariant =
  | { status: "loading" }
  | { status: "error"; message: string; retry: () => void }
  | { status: "missing" }
  | { status: "ready"; variant: FontVariant };

/** One saved variant by id, distinguishing loading, error, and deleted/missing. */
export function useLiveVariant(id: string): LiveVariant {
  const { attempt, retry } = useQueryAttempt();
  const row = useLiveQuery(
    async ():
      | Promise<{ ok: true; variant: FontVariant | undefined } | { ok: false; message: string }> => {
      try {
        return { ok: true, variant: await getVariant(id) };
      } catch (error) {
        return { ok: false, message: queryMessage(error) };
      }
    },
    [id, attempt],
    undefined,
  );
  if (row === undefined) return { status: "loading" };
  if (!row.ok) return { status: "error", message: row.message, retry };
  return row.variant ? { status: "ready", variant: row.variant } : { status: "missing" };
}
