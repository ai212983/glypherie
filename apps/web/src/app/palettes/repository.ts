import { fontDatabase, runWithReopen } from "../database.ts";
import { MONOCHROME_ID, validatePalette, type PalettePreset } from "./model.ts";
import { linearCurve, type GrayCurve } from "../features/grayscale/response-curve.ts";

export async function listPalettes(): Promise<PalettePreset[]> {
  return runWithReopen(() => fontDatabase.palettes.orderBy(":id").toArray());
}

export async function createPalette(): Promise<number> {
  return runWithReopen(() => fontDatabase.transaction("rw", fontDatabase.palettes, async () => {
    const id = await fontDatabase.palettes.add({ name: "Grayscale", curve: linearCurve(4) } as PalettePreset);
    await fontDatabase.palettes.update(id, { name: `Grayscale ${id}` });
    return id;
  }));
}

// Read/modify/write in one transaction: rapid curve operations compose, and
// an edit queued after deletion cannot recreate the removed preset.
export async function updatePalette(id: number, change: { name?: string; curve?: (curve: GrayCurve) => GrayCurve }): Promise<void> {
  if (id === MONOCHROME_ID) throw new Error("Monochrome is read-only.");
  return runWithReopen(() => fontDatabase.transaction("rw", fontDatabase.palettes, async () => {
    const existing = await fontDatabase.palettes.get(id);
    if (!existing) throw new Error("This palette was deleted. Select another preset.");
    const next = { ...existing, name: change.name ?? existing.name, curve: change.curve?.(existing.curve) ?? existing.curve };
    validatePalette(next);
    await fontDatabase.palettes.put(next);
  }));
}

export async function deletePalette(id: number): Promise<void> {
  if (id === MONOCHROME_ID) throw new Error("Monochrome is read-only.");
  return runWithReopen(() => fontDatabase.transaction("rw", [fontDatabase.palettes, fontDatabase.variants], async () => {
    await fontDatabase.palettes.delete(id);
    await fontDatabase.variants.toCollection().modify((row) => {
      if (row.settings.paletteId !== id) return;
      row.settings = { ...row.settings, paletteId: MONOCHROME_ID, profile: "mono_1bit", rasterization: "free_type_mono" };
      row.revision += 1;
      row.updatedAt = Date.now();
    });
  }));
}
