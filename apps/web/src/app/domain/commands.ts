// Domain commands over a DomainBackend. Every graph mutation runs inside one
// store.transaction (PGlite executes serially on the single owning engine), so
// required edges are created with their nodes and CAS checks are race-free.
// Variant and palette writes that also touch preferences run graph and
// auxiliary writes in one outer Drizzle transaction (see atomic.ts), so a
// failed preference write rolls back the graph write and the same revision
// can retry. Missing preferences fall back to defaults on read. All methods
// are plain structured-cloneable in/out so the browser worker can expose this
// surface over postMessage without serializing store callbacks.

import {
  MONOCHROME,
  type PalettePreset,
} from "../palettes/model.ts";
import {
  currentPreviewSettings,
  defaultVariantSettings,
  validateVariantSampleText,
  validateVariantSettings,
  type FontVariant,
  type VariantSettings,
} from "../variants/model.ts";
import { cloneKerning } from "../kerning/model.ts";
import { sql } from "drizzle-orm";
import { PREVIEW_MONO_RASTER, TEXT_DEFAULT } from "../renderer/render-spec.ts";
import { linearCurve, type GrayCurve } from "../features/grayscale/response-curve.ts";
import type { FontMetadata, FontSource, StoredFont } from "../fonts/storage.ts";
import {
  binaryLength,
  deleteBinary,
  kvGet,
  kvPut,
  readBinary,
  reserveLegacyPaletteId,
  writeBinaryIfAbsent,
  MONOCHROME_OUTPUT_ID,
  type AuxDb,
  type DomainBackend,
} from "./backend.ts";
import { withAtomicDomain } from "./atomic.ts";
import {
  assembleVariantViewIn,
  checkVariantName,
  checkVariantUpdateShape,
  curveProfile,
  getVariantView,
  listVariantViews,
  loadValidatedVariantUpdate,
  outputProfileByLegacyId,
  persistValidatedVariantGraph,
  persistValidatedVariantPrefs,
  previewKey,
  readPrefsIn,
  resolveOutputProfileIn,
  writePrefsIn,
} from "./variant-plan.ts";
import type {
  DomainOutputProfileView,
  DomainTextStyleView,
} from "./types.ts";

import { DomainError } from "./errors.ts";

export { DomainError } from "./errors.ts";
export type { DomainCode } from "./errors.ts";
export { curveProfile } from "./variant-plan.ts";
export type { PreviewPreferences } from "./variant-plan.ts";

type Store = DomainBackend["store"];

const now = (): number => Date.now();

function newId(): string {
  const id = globalThis.crypto?.randomUUID?.();
  if (typeof id !== "string" || id.length === 0) {
    throw new DomainError("unavailable", "Domain storage needs crypto.randomUUID, missing in this context.");
  }
  return id;
}

function failInvalid(message: string): never {
  throw new DomainError("invalid-input", message);
}

// ---- Font binaries ----

async function contentId(bytes: ArrayBuffer | Uint8Array): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new DomainError("unavailable", "Font storage needs WebCrypto SHA-256, missing in this context.");
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const digest = await subtle.digest("SHA-256", view as BufferSource);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function toArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer as ArrayBuffer;
}

export interface SaveFontInput {
  bytes: ArrayBuffer | Uint8Array;
  fileName: string;
  name: string;
  metadata: FontMetadata;
  source: FontSource;
}

function checkFontInput(input: SaveFontInput): { bytes: Uint8Array } {
  // Type-guard first: converting before the check allocates
  // attacker-sized buffers for numeric input and throws raw RangeErrors for
  // negative lengths instead of the domain's invalid-input failure.
  const raw: unknown =
    input !== null && typeof input === "object" ? (input as { bytes?: unknown }).bytes : undefined;
  if (!(raw instanceof ArrayBuffer) && !(raw instanceof Uint8Array)) {
    throw new DomainError("invalid-input", "Stored fonts need byte content.");
  }
  const bytes = raw instanceof Uint8Array ? raw : new Uint8Array(raw);
  if (bytes.byteLength === 0) throw new DomainError("invalid-input", "Refusing to store a font with no bytes.");
  if (typeof input.name !== "string" || input.name.trim() === "") {
    throw new DomainError("invalid-input", "Stored fonts need a non-empty name.");
  }
  if (typeof input.fileName !== "string" || input.fileName.trim() === "") {
    throw new DomainError("invalid-input", "Stored fonts need a non-empty file name.");
  }
  if (input.source !== "bundled" && input.source !== "uploaded") {
    throw new DomainError("invalid-input", "Font source must be bundled or uploaded.");
  }
  return { bytes };
}

interface FontNodeProps {
  name: string;
  fileName: string;
  metadata: FontMetadata;
  source: FontSource;
  addedAt: number;
}

async function readFontNode(store: Store, id: string): Promise<(FontNodeProps & { id: string }) | undefined> {
  const node = await store.nodes.Font.getById(id as never).catch(() => undefined);
  if (!node) return undefined;
  return {
    id: node.id as string,
    name: node.name as string,
    fileName: node.fileName as string,
    metadata: node.metadata as FontMetadata,
    source: node.source as FontSource,
    addedAt: node.addedAt as number,
  };
}

async function toStoredFont(backend: DomainBackend, props: FontNodeProps & { id: string }): Promise<StoredFont> {
  const bytes = await readBinary(backend.db, props.id);
  if (!bytes) throw new DomainError("unavailable", `Font "${props.id}" is indexed but its bytes are missing.`);
  return {
    id: props.id,
    name: props.name,
    fileName: props.fileName,
    bytes: toArrayBuffer(bytes),
    metadata: props.metadata,
    source: props.source,
    addedAt: props.addedAt,
  };
}

export async function saveFont(backend: DomainBackend, input: SaveFontInput): Promise<StoredFont> {
  const { bytes } = checkFontInput(input);
  const id = await contentId(bytes);
  await writeBinaryIfAbsent(backend.db, id, bytes).catch((error) => {
    throw new DomainError("unavailable", `Font binary write failed for "${input.fileName}".`, { cause: error });
  });
  const stored = await backend.store.transaction(async (tx) => {
    const existing = await readFontNode(tx as unknown as Store, id);
    if (existing) {
      if (existing.source === "uploaded" || input.source === "bundled") return existing;
      await tx.nodes.Font.update(existing.id as never, { source: "uploaded" } as never);
      return { ...existing, source: "uploaded" as FontSource };
    }
    const created = await tx.nodes.Font.create(
      { name: input.name, fileName: input.fileName, metadata: input.metadata as never, source: input.source, addedAt: now() },
      { id },
    );
    return {
      id: created.id as string,
      name: created.name as string,
      fileName: created.fileName as string,
      metadata: created.metadata as FontMetadata,
      source: created.source as FontSource,
      addedAt: created.addedAt as number,
    };
  });
  return toStoredFont(backend, stored);
}

export async function getFont(backend: DomainBackend, id: string): Promise<StoredFont | undefined> {
  const node = await readFontNode(backend.store, id);
  return node ? toStoredFont(backend, node) : undefined;
}

export async function listFonts(backend: DomainBackend): Promise<StoredFont[]> {
  const rows = await backend.store.query().from("Font", "f").select((ctx) => ctx.f).execute();
  const nodes = [...rows]
    .map((row) => ({
      id: String(row.id),
      name: String((row as Record<string, unknown>).name),
      addedAt: Number((row as Record<string, unknown>).addedAt),
    }))
    .sort((a, b) => a.addedAt - b.addedAt || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const fonts: StoredFont[] = [];
  for (const entry of nodes) {
    const node = await readFontNode(backend.store, entry.id);
    if (node) fonts.push(await toStoredFont(backend, node));
  }
  return fonts;
}

export async function updateFontMetadata(
  backend: DomainBackend,
  id: string,
  metadata: FontMetadata,
): Promise<void> {
  await backend.store.transaction(async (tx) => {
    const existing = await tx.nodes.Font.getById(id as never).catch(() => undefined);
    if (!existing) return;
    await tx.nodes.Font.update(id as never, { metadata: metadata as never });
  });
}

async function sceneNamesPlacing(
  store: Store,
  labelIds: readonly string[],
): Promise<string[]> {
  const names = new Set<string>();
  for (const labelId of labelIds) {
    const label = await store.nodes.Label.getById(labelId as never).catch(() => undefined);
    if (!label) continue;
    const placements = await store.edges.places.findTo(label);
    for (const edge of placements) {
      const scene = await store.nodes.Scene.getById(edge.fromId as never).catch(() => undefined);
      if (scene) names.add(String((scene as Record<string, unknown>).name));
    }
  }
  return [...names].sort();
}

export async function removeFont(backend: DomainBackend, id: string): Promise<void> {
  const removals: { binaries: string[]; prefs: string[] } = { binaries: [], prefs: [] };
  await backend.store.transaction(async (tx) => {
    const font = await tx.nodes.Font.getById(id as never).catch(() => undefined);
    if (!font) return;
    const variants = await tx.edges.variantOf.findTo(font);
    for (const variantEdge of variants) {
      const variant = await tx.nodes.FontVariant.getById(variantEdge.fromId as never).catch(() => undefined);
      if (!variant) {
        await tx.edges.variantOf.delete(variantEdge.id).catch(() => undefined);
        continue;
      }
      const styles = await tx.edges.usesVariant.findTo(variant);
      for (const styleEdge of styles) {
        const style = await tx.nodes.TextStyle.getById(styleEdge.fromId as never).catch(() => undefined);
        if (!style) {
          await tx.edges.usesVariant.delete(styleEdge.id).catch(() => undefined);
          continue;
        }
        const labels = await tx.edges.styledAs.findTo(style);
        if (labels.length > 0) {
          const scenes = await sceneNamesPlacing(tx as unknown as Store, labels.map((edge) => String(edge.fromId)));
          throw new DomainError(
            "referenced",
            `Refusing to remove a font whose text styles are used by labels${scenes.length > 0 ? ` in ${scenes.join(", ")}` : ""}.`,
          );
        }
        const profileEdges = await tx.edges.usesProfile.findFrom(style);
        // Edges detach before their nodes: hard deletes refuse connected nodes.
        await tx.edges.usesVariant.delete(styleEdge.id);
        for (const profileEdge of profileEdges) {
          await tx.edges.usesProfile.delete(profileEdge.id);
        }
        await tx.nodes.TextStyle.hardDelete(style.id);
        removals.prefs.push(`preview:${String(style.id)}`);
        for (const profileEdge of profileEdges) {
          const profile = await tx.nodes.RenderingProfile.getById(profileEdge.toId as never).catch(() => undefined);
          if (!profile) continue;
          const remaining = await tx.edges.usesProfile.findTo(profile);
          if (remaining.length === 0) await tx.nodes.RenderingProfile.hardDelete(profile.id);
        }
      }
      const remainingStyles = await tx.edges.usesVariant.findTo(variant);
      if (remainingStyles.length === 0) {
        await tx.edges.variantOf.delete(variantEdge.id);
        await tx.nodes.FontVariant.hardDelete(variant.id);
      }
    }
    await tx.nodes.Font.hardDelete(font.id);
    removals.binaries.push(id);
  });
  for (const key of removals.prefs) {
    await backend.db.execute(sql`DELETE FROM app_kv WHERE key = ${key}`).catch(() => undefined);
  }
  for (const contentIdValue of removals.binaries) {
    await deleteBinary(backend.db, contentIdValue).catch(() => undefined);
  }
}

// ---- Variant composite (legacy VariantSettings DTO over split entities) ----
//
// Preview preference and output-profile lookups live in ./variant-plan.ts:
// the validated plan owns them once per outer transaction.

export interface VariantInput {
  name?: string;
  settings?: VariantSettings;
  sampleText?: string;
  inheritSampleText?: boolean;
}

export type VariantChanges = VariantInput;

function resolveCreationSettings(input: VariantInput, fontId: string, metadata: FontMetadata): VariantSettings {
  const settings = input.settings ?? defaultVariantSettings({ id: fontId, metadata } as never);
  try {
    validateVariantSettings(settings, metadata);
  } catch (error) {
    throw new DomainError("invalid-settings", error instanceof Error ? error.message : "Invalid variant settings.", { cause: error });
  }
  try {
    validateVariantSampleText(input.sampleText ?? TEXT_DEFAULT, input.inheritSampleText ?? input.sampleText === undefined);
  } catch (error) {
    throw new DomainError("invalid-input", error instanceof Error ? error.message : "Invalid variant input.", { cause: error });
  }
  return settings;
}

async function resolveCreationName(txStore: Store, font: unknown, input: VariantInput): Promise<string> {
  if (input.name !== undefined) return input.name;
  const count = (await txStore.edges.variantOf.findTo(font as never)).length;
  const name = `Variant ${count + 1}`;
  checkVariantName(name);
  return name;
}

async function publishCreationPrefs(
  txStore: Store,
  txAux: AuxDb,
  styleId: string,
  input: VariantInput,
  settings: VariantSettings,
): Promise<void> {
  const output = await outputProfileByLegacyId(txStore, settings.paletteId ?? MONOCHROME.id)
    ?? await resolveOutputProfileIn(txStore, undefined);
  await writePrefsIn(txAux, styleId, {
    sampleText: input.sampleText ?? TEXT_DEFAULT,
    inheritSampleText: input.inheritSampleText ?? input.sampleText === undefined,
    outputProfileId: output.id,
  });
}

async function insertVariantGraph(
  tx: Store,
  font: unknown,
  name: string,
  settings: VariantSettings,
  stamp: number,
): Promise<string> {
  const variantNode = await tx.nodes.FontVariant.create({
    name,
    fontSize: settings.sizePx,
    axes: { ...settings.axes },
    revision: 1,
    createdAt: stamp,
    updatedAt: stamp,
  });
  await tx.edges.variantOf.create(variantNode, font as never, {});
  const profileNode = await tx.nodes.RenderingProfile.create({
    name,
    letterSpacing: settings.letterSpacingPx,
    kerning: cloneKerning(settings.kerning),
    useFontHints: settings.stemFitting === "font_hints_first",
    fitDiagonals: settings.diagonalFitting ?? false,
    revision: 1,
    createdAt: stamp,
    updatedAt: stamp,
  });
  const styleNode = await tx.nodes.TextStyle.create(
    { name, revision: 1, createdAt: stamp, updatedAt: stamp },
    { id: newId() },
  );
  await tx.edges.usesVariant.create(styleNode, variantNode, {});
  await tx.edges.usesProfile.create(styleNode, profileNode, {});
  return String(styleNode.id);
}

export async function createVariant(backend: DomainBackend, fontId: string, input: VariantInput = {}): Promise<FontVariant> {
  if (!input || typeof input !== "object" || Array.isArray(input)) failInvalid("Variant creation needs an input object.");
  if (input.name !== undefined) checkVariantName(input.name);
  return withAtomicDomain(backend, async (txStore, txAux) => {
    const font = await txStore.nodes.Font.getById(fontId as never).catch(() => undefined);
    if (!font) throw new DomainError("font-not-found", `Refusing to create a variant for missing font "${fontId}".`);
    const metadata = (font as unknown as Record<string, unknown>).metadata as FontMetadata;
    const settings = resolveCreationSettings(input, fontId, metadata);
    const name = await resolveCreationName(txStore, font, input);
    const createdId = await txStore.transaction(async (txNodes) =>
      insertVariantGraph(txNodes as unknown as Store, font, name, settings, now()));
    await publishCreationPrefs(txStore, txAux, createdId, input, settings);
    // Assembled inside the same transaction: the return view shares the
    // snapshot with the writes it reports.
    const assembled = await assembleVariantViewIn(txStore, txAux, createdId);
    if (!assembled) throw new DomainError("unavailable", `Variant "${createdId}" vanished after creation.`);
    return assembled;
  });
}

export async function getVariant(backend: DomainBackend, id: string): Promise<FontVariant | undefined> {
  return getVariantView(backend, id);
}

export async function listVariants(backend: DomainBackend, fontId?: string): Promise<FontVariant[]> {
  return listVariantViews(backend, fontId);
}

export async function updateVariant(
  backend: DomainBackend,
  id: string,
  changes: VariantChanges,
  expectedRevision: number,
): Promise<FontVariant> {
  checkVariantUpdateShape(changes, expectedRevision);
  const stamp = now();
  return withAtomicDomain(backend, async (txStore, txAux) => {
    // One validated plan owns every lookup; persistence consumes it without
    // re-reading, so the validated state can be trusted below.
    const plan = await loadValidatedVariantUpdate(txStore, txAux, id, changes, expectedRevision);
    await txStore.transaction(async (txNodes) => {
      await persistValidatedVariantGraph(txNodes as unknown as Store, plan, stamp);
    });
    await persistValidatedVariantPrefs(txAux, id, plan);
    const assembled = await assembleVariantViewIn(txStore, txAux, id);
    if (!assembled) throw new DomainError("not-found", `Variant "${id}" does not exist; refusing to recreate it.`);
    return assembled;
  });
}

export async function deleteVariant(backend: DomainBackend, id: string, expectedRevision?: number): Promise<void> {
  if (expectedRevision !== undefined && !Number.isInteger(expectedRevision)) {
    failInvalid("Variant deletion needs an integer expected revision.");
  }
  let prefsKey = "";
  await backend.store.transaction(async (tx) => {
    const style = await tx.nodes.TextStyle.getById(id as never).catch(() => undefined);
    if (!style) throw new DomainError("not-found", `Variant "${id}" does not exist.`);
    if (expectedRevision !== undefined && Number((style as unknown as Record<string, unknown>).revision) !== expectedRevision) {
      throw new DomainError("conflict", `Variant "${id}" changed underneath this delete.`);
    }
    const labels = await tx.edges.styledAs.findTo(style);
    if (labels.length > 0) {
      const scenes = await sceneNamesPlacing(tx as unknown as Store, labels.map((edge) => String(edge.fromId)));
      throw new DomainError(
        "referenced",
        `Refusing to delete a variant used by labels${scenes.length > 0 ? ` in ${scenes.join(", ")}` : ""}.`,
      );
    }
    const variantEdges = await tx.edges.usesVariant.findFrom(style);
    const profileEdges = await tx.edges.usesProfile.findFrom(style);
    const variantEdge = variantEdges[0];
    const profileEdge = profileEdges[0];
    for (const edge of variantEdges) await tx.edges.usesVariant.delete(edge.id).catch(() => undefined);
    for (const edge of profileEdges) await tx.edges.usesProfile.delete(edge.id).catch(() => undefined);
    await tx.nodes.TextStyle.hardDelete(style.id);
    prefsKey = previewKey(id);
    if (variantEdge) {
      const variant = await tx.nodes.FontVariant.getById(variantEdge.toId as never).catch(() => undefined);
      if (variant) {
        const remaining = await tx.edges.usesVariant.findTo(variant);
        if (remaining.length === 0) {
          const fontLinks = await tx.edges.variantOf.findFrom(variant);
          for (const link of fontLinks) await tx.edges.variantOf.delete(link.id).catch(() => undefined);
          await tx.nodes.FontVariant.hardDelete(variant.id);
        }
      }
    }
    if (profileEdge) {
      const profile = await tx.nodes.RenderingProfile.getById(profileEdge.toId as never).catch(() => undefined);
      if (profile) {
        const remaining = await tx.edges.usesProfile.findTo(profile);
        if (remaining.length === 0) await tx.nodes.RenderingProfile.hardDelete(profile.id);
      }
    }
  });
  if (prefsKey) await backend.db.execute(sql`DELETE FROM app_kv WHERE key = ${prefsKey}`).catch(() => undefined);
}

// ---- Output profiles (numeric-identity facade over graph nodes) ----

export async function listPalettes(backend: DomainBackend): Promise<PalettePreset[]> {
  const rows = await backend.store.query().from("OutputProfile", "o").select((ctx) => ctx.o).execute();
  return [...rows]
    .map((row) => {
      const record = row as unknown as Record<string, unknown>;
      return {
        id: typeof record.legacyPaletteId === "number" ? record.legacyPaletteId : -1,
        name: String(record.name),
        curve: (record.curve as GrayCurve).map((level) => ({ ...level })),
      };
    })
    .filter((preset) => preset.id >= 0)
    .sort((a, b) => a.id - b.id);
}

export async function createPalette(backend: DomainBackend): Promise<number> {
  // The reservation runs before (never inside) the graph transaction: it is
  // one atomic statement on the single-owner engine, so concurrent creators
  // serialize on the row lock and deleted IDs are never reissued. A
  // reservation whose graph write then fails leaves a gap, not a duplicate.
  const before = await backend.store.query().from("OutputProfile", "o").select((ctx) => ctx.o).execute();
  let max = -1;
  for (const row of before) {
    const legacyId = (row as unknown as Record<string, unknown>).legacyPaletteId;
    if (typeof legacyId === "number" && legacyId > max) max = legacyId;
  }
  const id = await reserveLegacyPaletteId(backend.db, max + 1);
  const stamp = now();
  await backend.store.transaction(async (tx) => {
    const live = await tx.query().from("OutputProfile", "o").select((ctx) => ctx.o).execute();
    if (live.some((row) => (row as unknown as Record<string, unknown>).legacyPaletteId === id)) {
      throw new DomainError("conflict", `Palette ${id} was created concurrently; retry the addition.`);
    }
    await tx.nodes.OutputProfile.create({
      name: `Grayscale ${id}`,
      curve: linearCurve(4).map((level) => ({ ...level })),
      legacyPaletteId: id,
      revision: 1,
      createdAt: stamp,
      updatedAt: stamp,
    });
  });
  return id;
}

// One gray level is valid when its value sits in the 8-bit range and its
// slope is finite; curve shape (length, pinned ends) is checked separately.
function isCurveLevelValid(level: GrayCurve[number]): boolean {
  return Number.isFinite(level.value) && level.value >= 0 && level.value <= 255 &&
    Number.isFinite(level.slope) && typeof level.pinned === "boolean";
}

function checkPaletteName(name: string): void {
  if (typeof name !== "string" || name.length === 0 || name.length > 120) {
    throw new DomainError("invalid-input", "Palette names must be non-empty text within 120 characters.");
  }
}

function checkPaletteCurve(curve: GrayCurve): void {
  const valid: readonly number[] = [2, 4, 8, 16];
  if (!valid.includes(curve.length) || !curve[0]?.pinned || !curve.at(-1)?.pinned ||
    !curve.every(isCurveLevelValid)) {
    throw new DomainError("invalid-settings", "Invalid palette preset.");
  }
}

function checkPalettePreset(name: string, curve: GrayCurve): void {
  checkPaletteName(name);
  checkPaletteCurve(curve);
}

export async function updatePalette(
  backend: DomainBackend,
  id: number,
  change: { name?: string; curve?: GrayCurve },
): Promise<void> {
  if (id === MONOCHROME.id) throw new DomainError("invalid-input", "Monochrome is read-only.");
  await backend.store.transaction(async (tx) => {
    const rows = await tx.query().from("OutputProfile", "o").select((ctx) => ctx.o).execute();
    const row = [...rows].find((candidate) => (candidate as unknown as Record<string, unknown>).legacyPaletteId === id);
    if (!row) throw new DomainError("not-found", "This palette was deleted. Select another preset.");
    const record = row as unknown as Record<string, unknown>;
    const curve = change.curve ?? (record.curve as GrayCurve);
    const next = {
      name: change.name ?? String(record.name),
      curve: curve.map((level) => ({ ...level })),
      revision: Number(record.revision) + 1,
      updatedAt: now(),
    };
    checkPalettePreset(next.name, next.curve);
    await tx.nodes.OutputProfile.update(row.id, next);
  });
}

// Styles whose preferences point at the deleted profile repoint to Monochrome
// in the same transaction: a failed repoint rolls back the deletion.
async function findPaletteAffectedStyles(txStore: Store, txAux: AuxDb, profileId: string): Promise<string[]> {
  const affected: string[] = [];
  const styles = await txStore.query().from("TextStyle", "s").select((ctx) => ctx.s).execute();
  for (const style of styles) {
    const prefs = await readPrefsIn(txAux, String(style.id));
    if (prefs?.outputProfileId === profileId) affected.push(String(style.id));
  }
  return affected;
}

async function repointPalettePrefs(txAux: AuxDb, styleIds: readonly string[]): Promise<void> {
  for (const styleId of styleIds) {
    const prefs = (await readPrefsIn(txAux, styleId)) ?? {
      sampleText: TEXT_DEFAULT,
      inheritSampleText: true,
      outputProfileId: MONOCHROME_OUTPUT_ID,
    };
    await writePrefsIn(txAux, styleId, { ...prefs, outputProfileId: MONOCHROME_OUTPUT_ID });
  }
}

export async function deletePalette(backend: DomainBackend, id: number): Promise<void> {
  if (id === MONOCHROME.id) throw new DomainError("invalid-input", "Monochrome is read-only.");
  const stamp = now();
  await withAtomicDomain(backend, async (txStore, txAux) => {
    const rows = await txStore.query().from("OutputProfile", "o").select((ctx) => ctx.o).execute();
    const row = [...rows].find((candidate) => (candidate as unknown as Record<string, unknown>).legacyPaletteId === id);
    if (!row) throw new DomainError("not-found", "This palette was deleted. Select another preset.");
    const scenes = await txStore.edges.defaultOutput.findTo(row);
    if (scenes.length > 0) {
      const names: string[] = [];
      for (const edge of scenes) {
        const scene = await txStore.nodes.Scene.getById(edge.fromId as never).catch(() => undefined);
        if (scene) names.push(String((scene as unknown as Record<string, unknown>).name));
      }
      throw new DomainError(
        "referenced",
        `Refusing to delete a palette used as the scene default${names.length > 0 ? ` in ${names.sort().join(", ")}` : ""}.`,
      );
    }
    const affectedStyles = await findPaletteAffectedStyles(txStore, txAux, String(row.id));
    await txStore.transaction(async (txNodes) => {
      const tx = txNodes as unknown as Store;
      for (const styleId of affectedStyles) {
        const style = await tx.nodes.TextStyle.getById(styleId as never).catch(() => undefined);
        if (!style) continue;
        await tx.nodes.TextStyle.update(style.id, {
          revision: Number((style as unknown as Record<string, unknown>).revision) + 1,
          updatedAt: stamp,
        });
      }
      await tx.nodes.OutputProfile.hardDelete(row.id);
    });
    await repointPalettePrefs(txAux, affectedStyles);
  });
}

// ---- Scenes and labels (owned by ./scene-commands.ts) ----

export {
  listScenes,
  getScene,
  createScene,
  updateScene,
  deleteScene,
  addSceneLabel,
  updateSceneLabel,
  removeSceneLabel,
  restoreSceneSnapshot,
} from "./scene-commands.ts";

// ---- Text styles and output profiles ----

export async function listTextStyles(backend: DomainBackend): Promise<DomainTextStyleView[]> {
  const rows = await backend.store.query().from("TextStyle", "s").select((ctx) => ctx.s).execute();
  const views: DomainTextStyleView[] = [];
  for (const row of rows) {
    const record = row as unknown as Record<string, unknown>;
    const variantEdges = await backend.store.edges.usesVariant.findFrom(row as never);
    const variantEdge = variantEdges[0];
    if (!variantEdge) continue;
    const variant = await backend.store.nodes.FontVariant.getById(variantEdge.toId as never).catch(() => undefined);
    if (!variant) continue;
    const variantRecord = variant as unknown as Record<string, unknown>;
    const fontEdges = await backend.store.edges.variantOf.findFrom(variant);
    const fontEdge = fontEdges[0];
    if (!fontEdge) continue;
    views.push({
      id: String(row.id),
      name: String(record.name),
      fontId: String(fontEdge.toId),
      fontSize: Number(variantRecord.fontSize),
    });
  }
  views.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : a.id < b.id ? -1 : 1));
  return views;
}

export async function listOutputProfiles(backend: DomainBackend): Promise<DomainOutputProfileView[]> {
  const rows = await backend.store.query().from("OutputProfile", "o").select((ctx) => ctx.o).execute();
  return [...rows]
    .map((row) => {
      const record = row as unknown as Record<string, unknown>;
      return {
        id: String(row.id),
        name: String(record.name),
        curve: (record.curve as GrayCurve).map((level) => ({ ...level })),
      };
    })
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : a.id < b.id ? -1 : 1));
}

// ---- Full render settings for one style plus an explicit output profile ----

export interface ResolvedTextStyle {
  id: string;
  name: string;
  fontId: string;
  settings: VariantSettings;
}

export async function resolveTextStyle(
  backend: DomainBackend,
  textStyleId: string,
  outputProfileId: string,
): Promise<ResolvedTextStyle> {
  // One read transaction shared with the batch resolver below, so a concurrent
  // edit cannot mix fields across committed revisions in a single resolve.
  const [resolved] = await backend.store.transaction(async (tx) => [
    await resolveOneInTx(tx as unknown as Store, textStyleId, outputProfileId),
  ]);
  return resolved;
}

// ---- Batched resolve: one read transaction, no mixed revisions ----

async function resolveOneInTx(tx: Store, styleId: string, outputId: string): Promise<ResolvedTextStyle> {
  const style = await tx.nodes.TextStyle.getById(styleId as never).catch(() => undefined);
  if (!style) throw new DomainError("not-found", `Text style "${styleId}" does not exist.`);
  const variantEdges = await tx.edges.usesVariant.findFrom(style);
  const profileEdges = await tx.edges.usesProfile.findFrom(style);
  const variantEdge = variantEdges[0];
  const profileEdge = profileEdges[0];
  if (!variantEdge || !profileEdge) {
    throw new DomainError("unavailable", `Text style "${styleId}" is missing its required font or profile link.`);
  }
  const variant = await tx.nodes.FontVariant.getById(variantEdge.toId as never).catch(() => undefined);
  const profile = await tx.nodes.RenderingProfile.getById(profileEdge.toId as never).catch(() => undefined);
  if (!variant || !profile) {
    throw new DomainError("unavailable", `Text style "${styleId}" links to a missing font variant or profile.`);
  }
  const variantRecord = variant as unknown as Record<string, unknown>;
  const profileRecord = profile as unknown as Record<string, unknown>;
  const fontLinks = await tx.edges.variantOf.findFrom(variant);
  const fontLink = fontLinks[0];
  if (!fontLink) throw new DomainError("unavailable", `Text style "${styleId}" links to a missing font.`);
  const outputNode = await tx.nodes.OutputProfile.getById(outputId as never).catch(() => undefined);
  if (!outputNode) throw new DomainError("not-found", `Output profile "${outputId}" does not exist.`);
  const outputRecord = outputNode as unknown as Record<string, unknown>;
  const curve = (outputRecord.curve as GrayCurve).map((level) => ({ ...level }));
  const legacyPaletteId = typeof outputRecord.legacyPaletteId === "number" ? outputRecord.legacyPaletteId : undefined;
  const settings = {
    ...currentPreviewSettings({
      sizePx: variantRecord.fontSize as number,
      axes: { ...(variantRecord.axes as Record<string, number>) },
      letterSpacingPx: profileRecord.letterSpacing as number,
      profile: curveProfile(curve),
      paletteId: legacyPaletteId,
      kerning: cloneKerning(profileRecord.kerning as never),
      stemFitting: profileRecord.useFontHints ? "font_hints_first" : "upstream_mono",
      diagonalFitting: profileRecord.fitDiagonals as boolean,
      monoRaster: { ...PREVIEW_MONO_RASTER },
      renderer: "candidate",
      rasterization: curve.length === 2 ? "free_type_mono" : "coverage",
    }),
  };
  settings.paletteId = legacyPaletteId;
  return {
    id: styleId,
    name: String((style as unknown as Record<string, unknown>).name),
    fontId: String(fontLink.toId),
    settings,
  };
}

export async function getSeedMarker(backend: DomainBackend): Promise<string | undefined> {
  return kvGet(backend.db, "seed:bundled-fonts");
}

export async function setSeedMarker(backend: DomainBackend, value: string): Promise<void> {
  if (typeof value !== "string") failInvalid("Seed markers must be strings.");
  await kvPut(backend.db, "seed:bundled-fonts", value);
}

export async function resolveTextStyles(
  backend: DomainBackend,
  textStyleIds: string[],
  outputProfileId: string,
): Promise<ResolvedTextStyle[]> {
  if (!Array.isArray(textStyleIds)) failInvalid("Batch resolve needs an array of text style ids.");
  return backend.store.transaction(async (tx) => {
    const resolved: ResolvedTextStyle[] = [];
    for (const styleId of textStyleIds) {
      if (typeof styleId !== "string") failInvalid("Batch resolve needs string text style ids.");
      resolved.push(await resolveOneInTx(tx as unknown as Store, styleId, outputProfileId));
    }
    return resolved;
  });
}
