import { errorName, fontDatabase, isDatabaseBlocked, runWithReopen } from "../database.ts";
import type { VariantRow } from "../database.ts";
import { DEFAULT_MONO_RASTER, TEXT_DEFAULT } from "../renderer/render-spec.ts";
import {
  defaultVariantSettings,
  currentPreviewSettings,
  validateVariantName,
  validateVariantSampleText,
  validateVariantSettings,
  VariantStorageError,
  type FontVariant,
  type VariantSettings,
} from "./model.ts";

import { resolvePalette } from "../palettes/model.ts";
import { paletteProfile } from "../palettes/render.ts";

export { VariantStorageError };

async function definedPaletteSettings(settings: VariantSettings): Promise<VariantSettings> {
  const row = settings.paletteId === undefined ? undefined : await fontDatabase.palettes.get(settings.paletteId);
  const preset = resolvePalette(row ? [row] : [], settings.paletteId);
  return currentPreviewSettings({ ...settings, paletteId: preset.id, profile: paletteProfile(preset) });
}

export interface VariantInput {
  name?: string;
  settings?: VariantSettings;
  sampleText?: string;
  inheritSampleText?: boolean;
}

export interface VariantChanges {
  name?: string;
  settings?: VariantSettings;
  sampleText?: string;
  inheritSampleText?: boolean;
}

function throwIfBlocked(): void {
  if (isDatabaseBlocked()) {
    throw new VariantStorageError(
      "blocked",
      "Variant storage is blocked by another open tab holding an older database version. Close other tabs and reload.",
    );
  }
}

function mapStorageError(error: unknown): VariantStorageError {
  if (error instanceof VariantStorageError) return error;
  if (errorName(error) === "QuotaExceededError") {
    return new VariantStorageError(
      "quota-exceeded",
      "Browser variant storage is full. Remove a variant to free space; nothing was uploaded anywhere.",
      { cause: error },
    );
  }
  return new VariantStorageError("unavailable", "Browser variant storage is unavailable in this context.", {
    cause: error,
  });
}

async function runVariant<T>(operation: () => Promise<T>): Promise<T> {
  throwIfBlocked();
  try {
    return await runWithReopen(operation);
  } catch (error) {
    throw mapStorageError(error);
  }
}

function newVariantId(): string {
  const id = globalThis.crypto?.randomUUID?.();
  if (typeof id !== "string" || id.length === 0) {
    throw new VariantStorageError("unavailable", "Variant storage needs crypto.randomUUID, missing in this context.");
  }
  return id;
}

function toVariant(row: VariantRow): FontVariant {
  return {
    id: row.id,
    fontId: row.fontId,
    name: row.name,
    settingsVersion: row.settingsVersion,
    // Rows written before scan controls carry no monoRaster, and rows
    // written before the font-instructions toggle carry no flag. Fill the
    // historical schema before applying the current preview policy.
    settings: currentPreviewSettings({
      ...row.settings,
      monoRaster: row.settings.monoRaster === undefined
        ? { ...DEFAULT_MONO_RASTER }
        : { ...row.settings.monoRaster, fontInstructions: row.settings.monoRaster.fontInstructions ?? false },
      axes: { ...row.settings.axes },
    }),
    sampleText: row.sampleText,
    inheritSampleText: row.inheritSampleText ?? false,
    revision: row.revision,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  };
}

function compareVariants(a: FontVariant | VariantRow, b: FontVariant | VariantRow): number {
  return a.createdAt - b.createdAt || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
}

export async function createVariant(fontId: string, input: VariantInput = {}): Promise<FontVariant> {
  const id = newVariantId();
  const now = Date.now();
  return runVariant(() =>
    fontDatabase.transaction("rw", [fontDatabase.fonts, fontDatabase.variants, fontDatabase.palettes], async () => {
      const font = await fontDatabase.fonts.get(fontId);
      if (!font) {
        throw new VariantStorageError("font-not-found", `Refusing to create a variant for missing font "${fontId}".`);
      }
      const inputSettings = input.settings ?? defaultVariantSettings(font);
      validateVariantSettings(inputSettings, font.metadata);
      const settings = await definedPaletteSettings(inputSettings);
      let name = input.name;
      if (name === undefined) {
        // Counted inside the transaction so concurrent creates sequence stably.
        const count = await fontDatabase.variants.where("fontId").equals(fontId).count();
        name = `Variant ${count + 1}`;
      }
      validateVariantName(name);
      const sampleText = input.sampleText ?? TEXT_DEFAULT;
      const inheritSampleText = input.inheritSampleText ?? input.sampleText === undefined;
      validateVariantSampleText(sampleText, inheritSampleText);
      const row: VariantRow = {
        id,
        fontId,
        name,
        settingsVersion: 1,
        settings: { ...settings, axes: { ...settings.axes } },
        sampleText,
        inheritSampleText,
        revision: 1,
        createdAt: now,
        updatedAt: now,
      };
      await fontDatabase.variants.add(row);
      return toVariant(row);
    }),
  );
}

export async function getVariant(id: string): Promise<FontVariant | undefined> {
  return runVariant(async () => {
    const row = await fontDatabase.variants.get(id);
    return row ? toVariant({ ...row, settings: await definedPaletteSettings(row.settings) }) : undefined;
  });
}

export async function listVariants(fontId?: string): Promise<FontVariant[]> {
  return runVariant(async () => {
    const rows = fontId === undefined
      ? await fontDatabase.variants.toArray()
      : await fontDatabase.variants.where("fontId").equals(fontId).toArray();
    return (await Promise.all(rows.map(async (row) => toVariant({ ...row, settings: await definedPaletteSettings(row.settings) })))).sort(compareVariants);
  });
}

export async function updateVariant(
  id: string,
  changes: VariantChanges,
  expectedRevision: number,
): Promise<FontVariant> {
  if (!changes || typeof changes !== "object" || Array.isArray(changes)) {
    throw new VariantStorageError("invalid-input", "Variant updates need a changes object.");
  }
  if (!Number.isInteger(expectedRevision)) {
    throw new VariantStorageError("invalid-input", "Variant updates need an integer expected revision.");
  }
  return runVariant(() =>
    fontDatabase.transaction("rw", [fontDatabase.fonts, fontDatabase.variants, fontDatabase.palettes], async () => {
      // Read-compare-write in one transaction; a deleted row stays deleted.
      const existing = await fontDatabase.variants.get(id);
      if (!existing) {
        throw new VariantStorageError("not-found", `Variant "${id}" does not exist; refusing to recreate it.`);
      }
      if (existing.revision !== expectedRevision) {
        throw new VariantStorageError(
          "conflict",
          `Variant "${id}" changed underneath this edit (expected revision ${expectedRevision}, found ${existing.revision}).`,
        );
      }
      let settings = existing.settings;
      if (changes.settings !== undefined) {
        const font = await fontDatabase.fonts.get(existing.fontId);
        if (!font) {
          throw new VariantStorageError(
            "font-not-found",
            `Refusing to update a variant whose font "${existing.fontId}" is missing.`,
          );
        }
        validateVariantSettings(changes.settings, font.metadata);
        settings = await definedPaletteSettings({ ...changes.settings, axes: { ...changes.settings.axes } });
      }
      let name = existing.name;
      if (changes.name !== undefined) {
        validateVariantName(changes.name);
        name = changes.name;
      }
      const sampleText = changes.sampleText === undefined ? existing.sampleText : changes.sampleText;
      const inheritSampleText = changes.inheritSampleText
        ?? (changes.sampleText !== undefined ? false : existing.inheritSampleText ?? false);
      validateVariantSampleText(sampleText, inheritSampleText);
      const next: VariantRow = {
        ...existing,
        name,
        settings: { ...settings, axes: { ...settings.axes } },
        sampleText,
        inheritSampleText,
        revision: existing.revision + 1,
        updatedAt: Date.now(),
      };
      // put() on the existing key updates in place; the get() above keeps a
      // concurrent delete-then-recreate from silently resurrecting this row
      // under a stale revision.
      await fontDatabase.variants.put(next);
      return toVariant(next);
    }),
  );
}

export async function deleteVariant(id: string, expectedRevision?: number): Promise<void> {
  if (expectedRevision !== undefined && !Number.isInteger(expectedRevision)) {
    throw new VariantStorageError("invalid-input", "Variant deletion needs an integer expected revision.");
  }
  return runVariant(() =>
    fontDatabase.transaction("rw", fontDatabase.variants, async () => {
      const existing = await fontDatabase.variants.get(id);
      if (!existing) {
        throw new VariantStorageError("not-found", `Variant "${id}" does not exist.`);
      }
      if (expectedRevision !== undefined && existing.revision !== expectedRevision) {
        throw new VariantStorageError(
          "conflict",
          `Variant "${id}" changed underneath this delete (expected revision ${expectedRevision}, found ${existing.revision}).`,
        );
      }
      await fontDatabase.variants.delete(id);
    }),
  );
}
