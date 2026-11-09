// Legacy Dexie snapshot reader for the one-way migration. Reads the legacy
// "font-library" database consistently (one read transaction), then hands a
// plain snapshot to the importer; Dexie is never written here and stays
// untouched so a failed import can always retry from the same source.

import { fontDatabase } from "./database.ts";
import type { FontRow, MetaRow, VariantRow } from "./database.ts";
import type { PalettePreset } from "./palettes/model.ts";
import type { FontMetadata, FontSource } from "./fonts/storage.ts";

export interface LegacyFontSnapshot {
  id: string;
  name: string;
  fileName: string;
  bytes: ArrayBuffer;
  metadata: FontMetadata;
  source: FontSource;
  addedAt: number;
}

export interface LegacyVariantSnapshot {
  id: string;
  fontId: string;
  name: string;
  settings: VariantRow["settings"];
  sampleText: string;
  inheritSampleText?: boolean;
  revision: number;
  createdAt: number;
  updatedAt: number;
}

export interface LegacySnapshot {
  fonts: LegacyFontSnapshot[];
  variants: LegacyVariantSnapshot[];
  // Legacy rows predate owner revisions; the importer assigns fresh ones.
  palettes: Omit<PalettePreset, "revision">[];
  seedMarker?: string;
  variantCount: number;
}

function toFontSnapshot(row: FontRow): LegacyFontSnapshot {
  const bytes =
    row.bytes instanceof ArrayBuffer ? row.bytes.slice(0) : (new Uint8Array(row.bytes).buffer as ArrayBuffer);
  return {
    id: row.id,
    name: row.name,
    fileName: row.fileName,
    bytes,
    metadata: row.metadata,
    source: row.source,
    addedAt: row.addedAt,
  };
}

export async function readLegacySnapshot(): Promise<LegacySnapshot> {
  return fontDatabase.transaction(
    "r",
    [fontDatabase.fonts, fontDatabase.meta, fontDatabase.variants, fontDatabase.palettes],
    async () => {
      const [fontRows, metaRows, variantRows, paletteRows] = await Promise.all([
        fontDatabase.fonts.toArray(),
        fontDatabase.meta.toArray(),
        fontDatabase.variants.toArray(),
        fontDatabase.palettes.toArray(),
      ]);
      const seedMarker = (metaRows as MetaRow[]).find((row) => row.key === "bundled-fonts")?.value;
      return {
        fonts: (fontRows as FontRow[]).map(toFontSnapshot),
        variants: (variantRows as VariantRow[]).map((row) => ({
          id: row.id,
          fontId: row.fontId,
          name: row.name,
          settings: { ...row.settings, axes: { ...row.settings.axes } },
          sampleText: row.sampleText,
          inheritSampleText: row.inheritSampleText,
          revision: row.revision,
          createdAt: row.createdAt,
          updatedAt: row.updatedAt,
        })),
        palettes: paletteRows.map((preset) => ({
          id: preset.id,
          name: preset.name,
          curve: preset.curve.map((level) => ({ ...level })),
        })),
        seedMarker,
        variantCount: (variantRows as VariantRow[]).length,
      };
    },
  );
}

/** Legacy row counts without materializing binaries; for import preflight. */
export async function legacyCounts(): Promise<{ fonts: number; variants: number; palettes: number }> {
  return fontDatabase.transaction(
    "r",
    [fontDatabase.fonts, fontDatabase.variants, fontDatabase.palettes],
    async () => ({
      fonts: await fontDatabase.fonts.count(),
      variants: await fontDatabase.variants.count(),
      palettes: await fontDatabase.palettes.count(),
    }),
  );
}
