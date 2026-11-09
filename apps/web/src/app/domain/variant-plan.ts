// Validated mutation plans and snapshot views share one transaction across
// graph nodes and preferences.

import { MONOCHROME, profileForCurve } from "../palettes/model.ts";
import {
  currentPreviewSettings,
  validateVariantName,
  validateVariantSampleText,
  validateVariantSettings,
  type FontVariant,
  type VariantSettings,
} from "../variants/model.ts";
import { cloneKerning } from "../kerning/model.ts";
import { PREVIEW_MONO_RASTER, TEXT_DEFAULT } from "../renderer/render-spec.ts";
import type { FontMetadata } from "../fonts/storage.ts";
import type { GrayCurve } from "../features/grayscale/response-curve.ts";
import { kvGet, kvPut, MONOCHROME_OUTPUT_ID, type AuxDb, type DomainBackend } from "./backend.ts";
import { withAtomicDomain } from "./atomic.ts";
import { DomainError } from "./errors.ts";

type Store = DomainBackend["store"];

type StyleNode = NonNullable<Awaited<ReturnType<Store["nodes"]["TextStyle"]["getById"]>>>;
type VariantNode = NonNullable<Awaited<ReturnType<Store["nodes"]["FontVariant"]["getById"]>>>;
type ProfileNode = NonNullable<Awaited<ReturnType<Store["nodes"]["RenderingProfile"]["getById"]>>>;

export interface PreviewPreferences {
  sampleText: string;
  inheritSampleText: boolean;
  outputProfileId: string;
}

export interface VariantUpdateInput {
  name?: string;
  settings?: VariantSettings;
  sampleText?: string;
  inheritSampleText?: boolean;
}

export const previewKey = (textStyleId: string): string => `preview:${textStyleId}`;

function defaultPrefs(outputProfileId: string): PreviewPreferences {
  return { sampleText: TEXT_DEFAULT, inheritSampleText: true, outputProfileId };
}

export async function readPrefsIn(aux: AuxDb, textStyleId: string): Promise<PreviewPreferences | undefined> {
  const raw = await kvGet(aux, previewKey(textStyleId));
  if (raw === undefined) return undefined;
  try {
    const parsed = JSON.parse(raw) as Partial<PreviewPreferences>;
    if (
      typeof parsed.sampleText !== "string" ||
      typeof parsed.inheritSampleText !== "boolean" ||
      typeof parsed.outputProfileId !== "string"
    )
      return undefined;
    return {
      sampleText: parsed.sampleText,
      inheritSampleText: parsed.inheritSampleText,
      outputProfileId: parsed.outputProfileId,
    };
  } catch {
    return undefined;
  }
}

// Preference writes join the caller's outer transaction: a failure rejects the
// whole variant or palette write instead of leaving a partial commit behind.
export async function writePrefsIn(aux: AuxDb, textStyleId: string, prefs: PreviewPreferences): Promise<void> {
  try {
    await kvPut(aux, previewKey(textStyleId), JSON.stringify(prefs));
  } catch (error) {
    throw new DomainError("unavailable", `Preferences for variant "${textStyleId}" did not persist; retry the edit.`, {
      cause: error,
    });
  }
}

// Curve length derives the output profile; owned by palettes/model.ts.
export function curveProfile(curve: GrayCurve): VariantSettings["profile"] {
  return profileForCurve(curve);
}

async function outputProfileById(
  store: Store,
  id: string,
): Promise<
  | {
      id: string;
      name: string;
      curve: GrayCurve;
      legacyPaletteId?: number;
    }
  | undefined
> {
  const node = await store.nodes.OutputProfile.getById(id as never).catch(() => undefined);
  if (!node) return undefined;
  const record = node as unknown as Record<string, unknown>;
  return {
    id: String(node.id),
    name: String(record.name),
    curve: (record.curve as GrayCurve).map((level) => ({ ...level })),
    legacyPaletteId: typeof record.legacyPaletteId === "number" ? record.legacyPaletteId : undefined,
  };
}

export async function resolveOutputProfileIn(
  store: Store,
  outputProfileId: string | undefined,
): Promise<{ id: string; name: string; curve: GrayCurve; legacyPaletteId?: number }> {
  const direct = outputProfileId ? await outputProfileById(store, outputProfileId) : undefined;
  if (direct) return direct;
  const fallback = await outputProfileById(store, MONOCHROME_OUTPUT_ID);
  if (!fallback) throw new DomainError("unavailable", "The Monochrome output profile is missing.");
  return fallback;
}

export async function outputProfileByLegacyId(
  store: Store,
  legacyId: number,
): Promise<
  | {
      id: string;
      name: string;
      curve: GrayCurve;
      legacyPaletteId?: number;
    }
  | undefined
> {
  const rows = await store
    .query()
    .from("OutputProfile", "o")
    .select((ctx) => ctx.o)
    .execute();
  for (const row of rows) {
    const record = row as unknown as Record<string, unknown>;
    if (record.legacyPaletteId === legacyId) {
      return {
        id: String(row.id),
        name: String(record.name),
        curve: (record.curve as GrayCurve).map((level) => ({ ...level })),
        legacyPaletteId: legacyId,
      };
    }
  }
  return undefined;
}

export function checkVariantName(name: string): void {
  try {
    validateVariantName(name);
  } catch (error) {
    throw new DomainError("invalid-input", error instanceof Error ? error.message : "Invalid variant name.", {
      cause: error,
    });
  }
}

export function checkVariantUpdateShape(changes: VariantUpdateInput, expectedRevision: number): void {
  if (!changes || typeof changes !== "object" || Array.isArray(changes)) {
    throw new DomainError("invalid-input", "Variant updates need a changes object.");
  }
  if (!Number.isInteger(expectedRevision)) {
    throw new DomainError("invalid-input", "Variant updates need an integer expected revision.");
  }
  if (changes.name !== undefined) checkVariantName(changes.name);
}

// ---- Validated update plan: one lookup pass per outer transaction ----

// The graph write one update needs. Rename tolerates a missing profile node
// exactly as the old rename path did (edge present, node gone skips the
// profile rename); the settings path requires it. Sample-only edits bump
// only the style revision.
type GraphUpdate =
  | { kind: "settings"; name: string; settings: VariantSettings; variantRevision: number; profileRevision: number }
  | { kind: "rename"; name: string; profileRevision: number | undefined }
  | { kind: "touch"; name: string };

interface PrefsUpdate {
  base: PreviewPreferences;
  outputProfileId?: string;
  sample?: { sampleText: string; inheritSampleText: boolean };
}

export interface ValidatedVariantUpdate {
  styleId: string;
  variantId: string;
  profileId: string;
  expectedRevision: number;
  graph: GraphUpdate;
  prefs: PrefsUpdate | undefined;
}

// Style, required edges and variant node. Later steps reuse these handles,
// so nothing downstream re-reads them.
async function loadUpdateTarget(
  txStore: Store,
  id: string,
): Promise<{ style: StyleNode; variant: VariantNode; profileId: string }> {
  const style = await txStore.nodes.TextStyle.getById(id as never).catch(() => undefined);
  if (!style) throw new DomainError("not-found", `Variant "${id}" does not exist; refusing to recreate it.`);
  const variantEdges = await txStore.edges.usesVariant.findFrom(style);
  const profileEdges = await txStore.edges.usesProfile.findFrom(style);
  const variantEdge = variantEdges[0];
  const profileEdge = profileEdges[0];
  if (!variantEdge || !profileEdge) {
    throw new DomainError("unavailable", `Variant "${id}" is missing its required font or profile link.`);
  }
  const variant = await txStore.nodes.FontVariant.getById(variantEdge.toId).catch(() => undefined);
  if (!variant) throw new DomainError("unavailable", `Variant "${id}" links to a missing font variant.`);
  return { style, variant, profileId: String(profileEdge.toId) };
}

async function resolveUpdateSettings(
  txStore: Store,
  id: string,
  variant: VariantNode,
  settings: VariantSettings,
): Promise<{ outputProfileId: string }> {
  const fontLinks = await txStore.edges.variantOf.findFrom(variant);
  const fontLink = fontLinks[0];
  if (!fontLink) throw new DomainError("unavailable", `Variant "${id}" links to a missing font.`);
  const fontNode = await txStore.nodes.Font.getById(fontLink.toId).catch(() => undefined);
  if (!fontNode) throw new DomainError("font-not-found", "Refusing to update a variant whose font is missing.");
  try {
    validateVariantSettings(settings, fontNode.metadata as FontMetadata);
  } catch (error) {
    throw new DomainError("invalid-settings", error instanceof Error ? error.message : "Invalid variant settings.", {
      cause: error,
    });
  }
  const output =
    (await outputProfileByLegacyId(txStore, settings.paletteId ?? MONOCHROME.id)) ??
    (await resolveOutputProfileIn(txStore, undefined));
  return { outputProfileId: output.id };
}

// Pure merge of sample keys over the single preference read: validation only,
// no storage access, so persistence reuses the same base without re-reading.
function resolveUpdateSample(base: PreviewPreferences, changes: VariantUpdateInput): PrefsUpdate["sample"] {
  if (changes.sampleText === undefined && changes.inheritSampleText === undefined) return undefined;
  const sampleText = changes.sampleText ?? base.sampleText;
  const inheritSampleText =
    changes.inheritSampleText ?? (changes.sampleText !== undefined ? false : base.inheritSampleText);
  try {
    validateVariantSampleText(sampleText, inheritSampleText);
  } catch (error) {
    throw new DomainError("invalid-input", error instanceof Error ? error.message : "Invalid sample text.", {
      cause: error,
    });
  }
  return { sampleText, inheritSampleText };
}

async function resolveGraphUpdate(
  txStore: Store,
  id: string,
  target: { style: StyleNode; variant: VariantNode; profileId: string },
  name: string,
  settings: VariantSettings | undefined,
): Promise<GraphUpdate> {
  if (settings !== undefined) {
    const profile = await txStore.nodes.RenderingProfile.getById(target.profileId as never).catch(() => undefined);
    if (!profile) throw new DomainError("unavailable", `Variant "${id}" links to a missing rendering profile.`);
    return {
      kind: "settings",
      name,
      settings,
      variantRevision: target.variant.revision,
      profileRevision: profile.revision,
    };
  }
  if (name !== target.style.name) {
    const profile = await txStore.nodes.RenderingProfile.getById(target.profileId as never).catch(() => undefined);
    return { kind: "rename", name, profileRevision: profile?.revision };
  }
  return { kind: "touch", name };
}

// One preference read per update, reused by validation and persistence:
// settings-only edits keep the stored sample, sample edits keep the stored
// profile, and untouched preferences skip storage entirely.
async function planPrefsUpdate(
  txAux: AuxDb,
  id: string,
  changes: VariantUpdateInput,
  outputProfileId: string | undefined,
): Promise<{ base: PreviewPreferences; sample: PrefsUpdate["sample"] } | undefined> {
  if (outputProfileId === undefined && changes.sampleText === undefined && changes.inheritSampleText === undefined)
    return undefined;
  const base = (await readPrefsIn(txAux, id)) ?? defaultPrefs(MONOCHROME_OUTPUT_ID);
  return { base, sample: resolveUpdateSample(base, changes) };
}

export async function loadValidatedVariantUpdate(
  txStore: Store,
  txAux: AuxDb,
  id: string,
  changes: VariantUpdateInput,
  expectedRevision: number,
): Promise<ValidatedVariantUpdate> {
  const target = await loadUpdateTarget(txStore, id);
  const name = changes.name ?? target.style.name;
  const settings = changes.settings;
  const outputProfileId =
    settings !== undefined
      ? (await resolveUpdateSettings(txStore, id, target.variant, settings)).outputProfileId
      : undefined;
  const prefsUpdate = await planPrefsUpdate(txAux, id, changes, outputProfileId);
  // CAS stays after validation, matching the old plan-then-nested-check
  // order: bad settings or sample text report before a stale revision does.
  if (target.style.revision !== expectedRevision) {
    throw new DomainError(
      "conflict",
      `Variant "${id}" changed underneath this edit (expected revision ${expectedRevision}).`,
    );
  }
  const graph = await resolveGraphUpdate(txStore, id, target, name, settings);
  return {
    styleId: id,
    variantId: String(target.variant.id),
    profileId: target.profileId,
    expectedRevision,
    graph,
    prefs:
      prefsUpdate === undefined ? undefined : { base: prefsUpdate.base, outputProfileId, sample: prefsUpdate.sample },
  };
}

// ---- Persistence: consumes the plan, performs no lookups ----

export async function persistValidatedVariantGraph(
  tx: Store,
  plan: ValidatedVariantUpdate,
  stamp: number,
): Promise<void> {
  const graph = plan.graph;
  if (graph.kind === "settings") {
    await tx.nodes.FontVariant.update(plan.variantId as never, {
      name: graph.name,
      fontSize: graph.settings.sizePx,
      axes: { ...graph.settings.axes },
      revision: graph.variantRevision + 1,
      updatedAt: stamp,
    });
    await tx.nodes.RenderingProfile.update(plan.profileId as never, {
      name: graph.name,
      letterSpacing: graph.settings.letterSpacingPx,
      kerning: cloneKerning(graph.settings.kerning as never),
      useFontHints: graph.settings.stemFitting === "font_hints_first",
      fitDiagonals: graph.settings.diagonalFitting ?? false,
      revision: graph.profileRevision + 1,
      updatedAt: stamp,
    });
  } else if (graph.kind === "rename") {
    await tx.nodes.FontVariant.update(plan.variantId as never, { name: graph.name, updatedAt: stamp });
    if (graph.profileRevision !== undefined) {
      await tx.nodes.RenderingProfile.update(plan.profileId as never, { name: graph.name, updatedAt: stamp });
    }
  }
  await tx.nodes.TextStyle.update(plan.styleId as never, {
    name: graph.name,
    revision: plan.expectedRevision + 1,
    updatedAt: stamp,
  });
}

// One write from the single preference read: no re-read, no second write
// when settings and sample change together.
export async function persistValidatedVariantPrefs(
  txAux: AuxDb,
  styleId: string,
  plan: ValidatedVariantUpdate,
): Promise<void> {
  if (plan.prefs === undefined) return;
  const next: PreviewPreferences = { ...plan.prefs.base };
  if (plan.prefs.outputProfileId !== undefined) next.outputProfileId = plan.prefs.outputProfileId;
  if (plan.prefs.sample !== undefined) {
    next.sampleText = plan.prefs.sample.sampleText;
    next.inheritSampleText = plan.prefs.sample.inheritSampleText;
  }
  await writePrefsIn(txAux, styleId, next);
}

// ---- Snapshot view assembly: graph and preferences from one transaction ----

interface ResolvedOutput {
  curve: GrayCurve;
  legacyPaletteId?: number;
}

interface VariantViewSource {
  styleId: string;
  style: StyleNode;
  variant: VariantNode;
  profile: ProfileNode;
  fontId: string;
  output: ResolvedOutput;
  prefs: PreviewPreferences | undefined;
}

function buildVariantView(view: VariantViewSource): FontVariant {
  const { style, variant, profile, output, prefs } = view;
  const settings = currentPreviewSettings({
    sizePx: variant.fontSize,
    axes: { ...variant.axes },
    letterSpacingPx: profile.letterSpacing,
    profile: curveProfile(output.curve),
    paletteId: output.legacyPaletteId ?? MONOCHROME.id,
    kerning: cloneKerning(profile.kerning as never),
    stemFitting: profile.useFontHints ? "font_hints_first" : "upstream_mono",
    diagonalFitting: profile.fitDiagonals,
    monoRaster: { ...PREVIEW_MONO_RASTER },
    renderer: "candidate",
    rasterization: output.curve.length === 2 ? "free_type_mono" : "coverage",
  });
  return {
    id: view.styleId,
    fontId: view.fontId,
    name: style.name,
    settingsVersion: 1,
    settings,
    sampleText: prefs?.sampleText ?? TEXT_DEFAULT,
    inheritSampleText: prefs?.inheritSampleText ?? false,
    revision: style.revision,
    createdAt: style.createdAt,
    updatedAt: style.updatedAt,
  };
}

// Every read flows through the caller's transaction handles, so one view
// never mixes graph fields from before a concurrent atomic update with
// preferences from after it.
export async function assembleVariantViewIn(
  txStore: Store,
  txAux: AuxDb,
  styleId: string,
): Promise<FontVariant | undefined> {
  const style = await txStore.nodes.TextStyle.getById(styleId as never).catch(() => undefined);
  if (!style) return undefined;
  const variantEdges = await txStore.edges.usesVariant.findFrom(style);
  const profileEdges = await txStore.edges.usesProfile.findFrom(style);
  const variantEdge = variantEdges[0];
  const profileEdge = profileEdges[0];
  if (!variantEdge || !profileEdge) {
    throw new DomainError("unavailable", `Variant "${styleId}" is missing its required font or profile link.`);
  }
  const variant = await txStore.nodes.FontVariant.getById(variantEdge.toId).catch(() => undefined);
  const profile = await txStore.nodes.RenderingProfile.getById(profileEdge.toId).catch(() => undefined);
  if (!variant || !profile) {
    throw new DomainError("unavailable", `Variant "${styleId}" links to a missing font variant or profile.`);
  }
  const fontEdges = await txStore.edges.variantOf.findFrom(variant);
  const fontEdge = fontEdges[0];
  if (!fontEdge) throw new DomainError("unavailable", `Variant "${styleId}" links to a missing font.`);
  const prefs = await readPrefsIn(txAux, styleId);
  const output = await resolveOutputProfileIn(txStore, prefs?.outputProfileId);
  return buildVariantView({ styleId, style, variant, profile, fontId: String(fontEdge.toId), output, prefs });
}

// Read-only snapshot through the same outer-transaction primitive as writes:
// the empty commit changes nothing, but graph and preferences share one
// snapshot instead of separate autocommit reads.
export function getVariantView(backend: DomainBackend, styleId: string): Promise<FontVariant | undefined> {
  return withAtomicDomain(backend, (txStore, txAux) => assembleVariantViewIn(txStore, txAux, styleId));
}

export function listVariantViews(backend: DomainBackend, fontId?: string): Promise<FontVariant[]> {
  return withAtomicDomain(backend, async (txStore, txAux) => {
    const rows = await txStore
      .query()
      .from("TextStyle", "s")
      .select((ctx) => ctx.s)
      .execute();
    const styles = [...rows]
      .map((row) => {
        const record = row as unknown as Record<string, unknown>;
        return { id: String(row.id), createdAt: Number(record.createdAt) };
      })
      .sort((a, b) => a.createdAt - b.createdAt || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    const variants: FontVariant[] = [];
    for (const entry of styles) {
      const view = await assembleVariantViewIn(txStore, txAux, entry.id);
      if (view && (fontId === undefined || view.fontId === fontId)) variants.push(view);
    }
    return variants;
  });
}
