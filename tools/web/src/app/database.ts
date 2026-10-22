import Dexie, { type Table } from "dexie";
import { MONOCHROME, type PalettePreset } from "./palettes/model.ts";
import type { FontMetadata, FontSource } from "./fonts/storage.ts";
import type { FontVariant } from "./variants/model.ts";

export interface FontRow {
  id: string;
  name: string;
  fileName: string;
  bytes: ArrayBuffer;
  metadata: FontMetadata;
  source: FontSource;
  addedAt: number;
}

export interface MetaRow {
  key: string;
  value: string;
}

export interface VariantRow {
  id: string;
  fontId: string;
  name: string;
  settingsVersion: 1;
  settings: FontVariant["settings"];
  sampleText: string;
  inheritSampleText?: boolean;
  revision: number;
  createdAt: number;
  updatedAt: number;
}

class FontLibraryDatabase extends Dexie {
  fonts!: Table<FontRow, string>;
  meta!: Table<MetaRow, string>;
  variants!: Table<VariantRow, string>;
  palettes!: Table<PalettePreset, number>;
  constructor() {
    super("font-library");
    this.version(1).stores({ fonts: "id, addedAt, source", meta: "key" });
    // Additive upgrade: fonts/meta carry over untouched, variants start empty.
    // The fontId index serves per-font variant queries; ordering is applied
    // deterministically (createdAt, id) at read time.
    this.version(2).stores({ fonts: "id, addedAt, source", meta: "key", variants: "id, fontId" });
    this.version(3).stores({ palettes: "++id" }).upgrade(async (tx) => {
      await tx.table("palettes").add(MONOCHROME);
      // Historical output profiles do not identify a defined palette.
      await tx.table("variants").toCollection().modify((row: VariantRow) => {
        row.settings.paletteId = MONOCHROME.id;
        row.settings.profile = "mono_1bit";
      });
    });
    this.on("populate", async (tx) => { await tx.table("palettes").add(MONOCHROME); });
  }
}

export const fontDatabase = new FontLibraryDatabase();

let databaseBlocked = false;
fontDatabase.on("blocked", () => {
  databaseBlocked = true;
});

export function isDatabaseBlocked(): boolean {
  return databaseBlocked;
}

export function errorName(error: unknown): string {
  return typeof error === "object" && error !== null && "name" in error
    ? String((error as { name: unknown }).name)
    : "";
}

// Reopen-and-retry for a database handle closed by a version upgrade in
// another tab; error mapping stays with the calling module so each error
// family keeps its own codes.
export async function runWithReopen<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (errorName(error) !== "DatabaseClosedError") throw error;
    await fontDatabase.open();
    return await operation();
  }
}
