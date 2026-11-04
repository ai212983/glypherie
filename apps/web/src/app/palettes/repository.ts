// Palette presets over OutputProfile graph nodes. Numeric identities are
// preserved for the existing UI and tests; only the storage mechanics moved
// to domain commands. Monochrome (id 0) stays read-only.
//
// The updater closure cannot cross the worker boundary, so the facade
// resolves it against the current row first. Same-tab concurrent edits to
// one preset serialize on a per-id mutex, preserving read-modify-write
// composition; cross-tab races keep last-writer-wins.

import { callDomain } from "../domain/runtime.ts";
import { MONOCHROME_ID, type PalettePreset } from "./model.ts";
import type { GrayCurve } from "../features/grayscale/response-curve.ts";

const locks = new Map<number, Promise<void>>();

async function withPaletteLock<T>(id: number, operation: () => Promise<T>): Promise<T> {
  const previous = locks.get(id) ?? Promise.resolve();
  let release: () => void = () => {};
  const current = previous.then(() => new Promise<void>((resolve) => {
    release = resolve;
  }));
  locks.set(id, current);
  await previous;
  try {
    return await operation();
  } finally {
    release();
    if (locks.get(id) === current) locks.delete(id);
  }
}

export async function listPalettes(): Promise<PalettePreset[]> {
  try {
    return (await callDomain("listPalettes", [])) as PalettePreset[];
  } catch {
    throw new Error("Browser palette storage is unavailable in this context.");
  }
}

export async function createPalette(): Promise<number> {
  try {
    return (await callDomain("createPalette", [])) as number;
  } catch {
    throw new Error("Browser palette storage is unavailable in this context.");
  }
}

export async function updatePalette(id: number, change: { name?: string; curve?: (curve: GrayCurve) => GrayCurve }): Promise<void> {
  if (id === MONOCHROME_ID) throw new Error("Monochrome is read-only.");
  return withPaletteLock(id, async () => {
    try {
      const presets = (await callDomain("listPalettes", [])) as PalettePreset[];
      const current = presets.find((preset) => preset.id === id);
      if (!current) throw new Error("This palette was deleted. Select another preset.");
      await callDomain("updatePalette", [id, {
        ...(change.name !== undefined ? { name: change.name } : {}),
        ...(change.curve ? { curve: change.curve(current.curve.map((level) => ({ ...level }))) } : {}),
      }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const code = (error as { code?: unknown })?.code;
      if (code === "not-found") throw new Error("This palette was deleted. Select another preset.");
      throw new Error(message);
    }
  });
}

export async function deletePalette(id: number): Promise<void> {
  if (id === MONOCHROME_ID) throw new Error("Monochrome is read-only.");
  return withPaletteLock(id, async () => {
    try {
      await callDomain("deletePalette", [id]);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const code = (error as { code?: unknown })?.code;
      if (code === "not-found") throw new Error("This palette was deleted. Select another preset.");
      throw new Error(message);
    }
  });
}
