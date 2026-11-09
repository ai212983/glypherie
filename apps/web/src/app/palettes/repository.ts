// Palette presets over OutputProfile graph nodes. Numeric identities are
// preserved for the existing UI and tests; only the storage mechanics moved
// to domain commands. Monochrome (id 0) stays read-only.
//
// Updates are semantic edits resolved inside one owner transaction: the client
// never reads a curve to compute its replacement, so concurrent edits from
// any tab serialize on the owner and compose instead of overwriting. There is
// deliberately no client-side lock: same-tab concurrency goes through the same
// owner serialization as cross-tab concurrency.

import { callDomain } from "../domain/runtime.ts";
import { MONOCHROME_ID, type PaletteEdit, type PalettePreset } from "./model.ts";

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

export async function updatePalette(id: number, edit: PaletteEdit): Promise<void> {
  if (id === MONOCHROME_ID) throw new Error("Monochrome is read-only.");
  try {
    await callDomain("updatePalette", [id, edit]);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const code = (error as { code?: unknown })?.code;
    if (code === "not-found") throw new Error("This palette was deleted. Select another preset.");
    throw new Error(message);
  }
}

export async function deletePalette(id: number): Promise<void> {
  if (id === MONOCHROME_ID) throw new Error("Monochrome is read-only.");
  try {
    await callDomain("deletePalette", [id]);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const code = (error as { code?: unknown })?.code;
    if (code === "not-found") throw new Error("This palette was deleted. Select another preset.");
    throw new Error(message);
  }
}
