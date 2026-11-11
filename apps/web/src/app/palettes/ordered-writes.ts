import { linearCurve, type GrayCurve } from "../domain/output-profiles/curve.ts";
import type { PaletteEdit, PalettePreset } from "./model.ts";

interface PaletteWriteSnapshot {
  readonly id: number;
  readonly revision: number;
  readonly ownBumps: number;
}

// Same-view palette writes run in call order; every committed edit on a row
// bumps its revision, so the queue counts its own bumps per row to tell them
// apart from another tab's concurrent edits.
export function createOrderedPaletteWrites(deps: {
  listPalettes: () => Promise<PalettePreset[]>;
  updatePalette: (id: number, edit: PaletteEdit) => Promise<void>;
}): {
  run: <T>(operation: () => Promise<T>) => Promise<T>;
  edit: (id: number, operation: () => Promise<unknown>) => Promise<unknown>;
  captureRevision: (id: number, revision: number) => PaletteWriteSnapshot;
  resetCurve: (snapshot: PaletteWriteSnapshot) => Promise<unknown>;
} {
  const ownBumps = new Map<number, number>();
  const snapshots = new Map<number, PaletteWriteSnapshot>();
  let tail: Promise<void> = Promise.resolve();
  const enqueue = <T>(operation: () => Promise<T>): Promise<T> => {
    const run = tail.then(operation, operation);
    tail = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  };
  return {
    run: (operation) => enqueue(operation),
    // Keep the checkpoint while the rendered revision is unchanged, including
    // rerenders between a write acknowledgement and its live-query refresh.
    captureRevision: (id, revision) => {
      const previous = snapshots.get(id);
      if (previous?.revision === revision) return previous;
      const snapshot = { id, revision, ownBumps: ownBumps.get(id) ?? 0 };
      snapshots.set(id, snapshot);
      return snapshot;
    },
    edit: (id, operation) =>
      enqueue(async () => {
        const result = await operation();
        ownBumps.set(id, (ownBumps.get(id) ?? 0) + 1);
        return result;
      }),
    // Only this view's successful writes may advance a displayed checkpoint;
    // the final owner CAS also catches edits between this read and the update.
    resetCurve: ({ id, revision, ownBumps: renderedBumps }) => {
      return enqueue(async () => {
        const live = await deps.listPalettes();
        const row = live.find((preset) => preset.id === id);
        if (!row) throw new Error("This palette was deleted. Select another preset.");
        const expected = revision + ((ownBumps.get(id) ?? 0) - renderedBumps);
        if (row.revision !== expected) {
          throw new Error(`Palette "${id}" changed underneath this edit (expected revision ${expected}).`);
        }
        const curve: GrayCurve = linearCurve(row.curve.length);
        const result = await deps.updatePalette(id, { kind: "replace", curve, expectedRevision: row.revision });
        ownBumps.set(id, (ownBumps.get(id) ?? 0) + 1);
        return result;
      });
    },
  };
}
