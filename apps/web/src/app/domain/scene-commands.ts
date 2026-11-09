// Scene graph commands over scene nodes, placements and labels.

import { sql } from "drizzle-orm";
import { createStore } from "@nicia-ai/typegraph";
import { createPostgresBackend } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { domainGraph, FONT_SIZE_MAX, FONT_SIZE_MIN, SCENE_DIMENSION_MAX, SCENE_DIMENSION_MIN } from "./graph.ts";
import { kvGet, kvPut, type AuxDb, type DomainBackend } from "./backend.ts";
import { normalizeCoverage, type CharacterCoverage } from "./coverage.ts";
import { DomainError } from "./errors.ts";
import type {
  DomainPlacementView,
  DomainSceneView,
  SceneLabelInput,
  SceneLabelPatch,
  SceneSnapshotInput,
} from "./types.ts";

type Store = DomainBackend["store"];

// store.transaction hands out a context with the same node/edge surface as
// the store (see commands.ts resolveOneInTx); helpers take Store so both
// call shapes share one rule, and each closure aliases tx once.
const now = (): number => Date.now();

function failInvalid(message: string): never {
  throw new DomainError("invalid-input", message);
}

// ---- Boundary validation: outside data is checked once here, trusted below ----

function checkSceneName(name: unknown): void {
  if (typeof name !== "string" || name.trim() === "" || name.length > 120) {
    failInvalid("Scene names must be non-empty text within 120 characters.");
  }
}

function checkSceneDimensions(width: unknown, height: unknown): void {
  for (const value of [width, height]) {
    if (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > 4096) {
      failInvalid("Scene dimensions must be integers within 1..4096.");
    }
  }
}

function checkPlacementPoint(x: unknown, y: unknown): void {
  for (const value of [x, y]) {
    if (typeof value !== "number" || !Number.isInteger(value) || !Number.isFinite(value)) {
      failInvalid("Label positions must sit on the native pixel grid (integer x/y).");
    }
  }
}

// Empty text is allowed: no domain policy forbids it, only stricter UI input.
function checkLabelText(text: unknown): void {
  if (typeof text !== "string" || text.length > 8192) {
    failInvalid("Label text must be a string within 8192 characters.");
  }
}

function checkPlacementOrder(order: unknown): void {
  if (!Number.isInteger(order) || !Number.isFinite(order)) {
    failInvalid("Placement order must be a stable integer.");
  }
}

// The domain stores the selected device as an opaque id so the graph never
// depends on the catalog; the screen UI resolves it and keeps custom screens
// as null with the scene's own dimensions.
function checkSceneDevice(deviceId: unknown): void {
  if (deviceId === null || deviceId === undefined) return;
  if (typeof deviceId !== "string" || deviceId.length === 0 || deviceId.length > 80) {
    failInvalid("Scene device ids must be non-empty text within 80 characters.");
  }
}

function checkScenePatchShape(patch: unknown): void {
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
    failInvalid("Scene updates need a patch object.");
  }
}

function checkDirectFontId(fontId: unknown): void {
  if (typeof fontId !== "string" || fontId.length === 0 || fontId.length > 128) {
    failInvalid("Direct labels need a font reference within 128 characters.");
  }
}

function checkDirectFontSize(fontSize: unknown): void {
  if (
    typeof fontSize !== "number" ||
    !Number.isInteger(fontSize) ||
    fontSize < FONT_SIZE_MIN ||
    fontSize > FONT_SIZE_MAX
  ) {
    failInvalid(`Direct label sizes must be integers within ${FONT_SIZE_MIN}..${FONT_SIZE_MAX}.`);
  }
}

function checkDirectWidth(width: unknown): void {
  if (
    typeof width !== "number" ||
    !Number.isInteger(width) ||
    width < SCENE_DIMENSION_MIN ||
    width > SCENE_DIMENSION_MAX
  ) {
    failInvalid(`Direct label widths must be integers within ${SCENE_DIMENSION_MIN}..${SCENE_DIMENSION_MAX}.`);
  }
}

// The font's own wght axis bounds a direct weight override, following the
// OpenType wght range 1..1000 (https://learn.microsoft.com/en-us/typography/opentype/spec/dvaraxistag_wght).
// Absent/null means the selected font's default; per-font support is checked
// separately against the font's metadata.
function checkDirectFontWeightShape(weight: unknown): void {
  if (weight === null || weight === undefined) return;
  if (typeof weight !== "number" || !Number.isFinite(weight) || weight < 1 || weight > 1000) {
    failInvalid("Direct label weights must be numbers within 1..1000.");
  }
}

interface FontWghtAxis {
  min: number;
  default: number;
  max: number;
}

// The font's wght axis from its stored metadata, when the font varies weight
// at all. Static fonts (no wght tag) never receive an override.
function fontWghtAxis(fontRecord: Record<string, unknown>): FontWghtAxis | null {
  const metadata = fontRecord.metadata as { axes?: unknown } | undefined;
  const axes = Array.isArray(metadata?.axes) ? (metadata.axes as Record<string, unknown>[]) : [];
  const axis = axes.find((entry) => entry?.tag === "wght");
  if (!axis) return null;
  const { min, default: fallback, max } = axis as { min?: unknown; default?: unknown; max?: unknown };
  if (
    typeof min !== "number" ||
    typeof fallback !== "number" ||
    typeof max !== "number" ||
    !Number.isFinite(min) ||
    !Number.isFinite(fallback) ||
    !Number.isFinite(max) ||
    !(min <= fallback && fallback <= max)
  ) {
    return null;
  }
  return { min, default: fallback, max };
}

// An explicitly requested weight must be supported by the target font and sit
// inside its axis bounds; static fonts only accept the absent/default form.
function checkDirectFontWeight(weight: unknown, axis: FontWghtAxis | null): void {
  checkDirectFontWeightShape(weight);
  if (weight === null || weight === undefined) return;
  if (!axis) failInvalid("Direct label weights need a font with a wght axis.");
  if ((weight as number) < axis.min || (weight as number) > axis.max) {
    failInvalid(`Direct label weights must sit within the font's wght ${axis.min}..${axis.max}.`);
  }
}

// A carried weight (kept across a font switch or a variant-to-direct
// conversion) resolves to a valid destination weight instead of failing: it
// clamps into the destination axis, and clears when the destination cannot
// vary weight, so a static font never receives an unsupported override.
function resolveCarriedFontWeight(carried: number | null, axis: FontWghtAxis | null): number | null {
  if (carried === null || axis === null) return null;
  if (!Number.isFinite(carried)) return null;
  return Math.min(axis.max, Math.max(axis.min, carried));
}

// Exactly one reference per label: a saved variant style, or a direct font
// with its own size, wrap width and optional weight override. Stray fields
// from the other shape fail instead of merging into a half-direct label.
function checkLabelReference(input: {
  textStyleId?: unknown;
  fontId?: unknown;
  fontSize?: unknown;
  width?: unknown;
  fontWeight?: unknown;
}): void {
  const styled = input.textStyleId !== undefined;
  const direct =
    input.fontId !== undefined ||
    input.fontSize !== undefined ||
    input.width !== undefined ||
    input.fontWeight !== undefined;
  if (styled === direct) {
    failInvalid("Label placement needs either a text style or a direct font reference.");
  }
  if (styled) {
    if (typeof input.textStyleId !== "string" || input.textStyleId.length === 0) {
      failInvalid("Label placement needs a text style id.");
    }
    return;
  }
  checkDirectFontId(input.fontId);
  checkDirectFontSize(input.fontSize);
  checkDirectWidth(input.width);
  checkDirectFontWeightShape(input.fontWeight);
}

function checkLabelPatchShape(patch: unknown): void {
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
    failInvalid("Label updates need a patch object.");
  }
  const candidate = patch as {
    text?: unknown;
    visible?: unknown;
    textStyleId?: unknown;
    fontId?: unknown;
    fontSize?: unknown;
    width?: unknown;
    fontWeight?: unknown;
  };
  if (candidate.visible !== undefined && typeof candidate.visible !== "boolean")
    failInvalid("Label visibility must be a boolean.");
  if (candidate.text !== undefined) checkLabelText(candidate.text);
  if (
    candidate.textStyleId !== undefined &&
    (typeof candidate.textStyleId !== "string" || candidate.textStyleId.length === 0)
  ) {
    failInvalid("Label placement needs a text style id.");
  }
  if (
    candidate.textStyleId !== undefined &&
    (candidate.fontId !== undefined ||
      candidate.fontSize !== undefined ||
      candidate.width !== undefined ||
      candidate.fontWeight !== undefined)
  ) {
    failInvalid("Label updates cannot combine a text style with direct font fields.");
  }
  if (candidate.fontId !== undefined) checkDirectFontId(candidate.fontId);
  if (candidate.fontSize !== undefined) checkDirectFontSize(candidate.fontSize);
  if (candidate.width !== undefined) checkDirectWidth(candidate.width);
  if (candidate.fontWeight !== undefined) checkDirectFontWeightShape(candidate.fontWeight);
}

function checkLabelInput(input: unknown): void {
  if (!input || typeof input !== "object") failInvalid("Label placement needs an input object.");
  const candidate = input as { text?: unknown; x?: unknown; y?: unknown };
  checkLabelText(candidate.text);
  checkPlacementPoint(candidate.x, candidate.y);
  checkLabelReference(candidate as SceneLabelInput);
}

function normalizeSceneCoverage(coverage: CharacterCoverage): CharacterCoverage {
  try {
    return normalizeCoverage(coverage);
  } catch (error) {
    throw new DomainError("invalid-input", error instanceof Error ? error.message : "Invalid export coverage.", {
      cause: error,
    });
  }
}

// Partial moves merge against the stored point before the grid check.
function checkPlacementMove(edge: { id: unknown }, patch: { x?: number; y?: number }): void {
  if (patch.x !== undefined || patch.y !== undefined) {
    const edgeRecord = edge as unknown as Record<string, unknown>;
    checkPlacementPoint(patch.x ?? edgeRecord.x, patch.y ?? edgeRecord.y);
  }
}

// ---- View building: torn edges are skipped, never surfaced ----

async function readPlacedView(
  store: Store,
  edge: { id: unknown; toId: unknown },
): Promise<DomainPlacementView | undefined> {
  const edgeRecord = edge as unknown as Record<string, unknown>;
  const label = await store.nodes.Label.getById(edge.toId as never).catch(() => undefined);
  if (!label) return undefined;
  const labelRecord = label as unknown as Record<string, unknown>;
  const styleEdges = await store.edges.styledAs.findFrom(label);
  const styleEdge = styleEdges[0];
  const directFontId = typeof labelRecord.fontId === "string" ? labelRecord.fontId : null;
  if (!styleEdge && directFontId === null) return undefined;
  if (!styleEdge) {
    // Rows validated on write carry the full direct triple; anything else is
    // torn and skipped like a missing style edge. The weight override is
    // optional: rows predating it read back null (the font default).
    const fontSize = labelRecord.fontSize;
    const width = labelRecord.width;
    if (
      typeof fontSize !== "number" ||
      !Number.isInteger(fontSize) ||
      typeof width !== "number" ||
      !Number.isInteger(width)
    ) {
      return undefined;
    }
    const fontWeight = labelRecord.fontWeight;
    return {
      id: String(edge.id),
      labelId: String(edge.toId),
      textStyleId: null,
      fontId: directFontId,
      fontSize,
      width,
      fontWeight: typeof fontWeight === "number" && Number.isFinite(fontWeight) ? fontWeight : null,
      text: String(labelRecord.text),
      x: Number(edgeRecord.x),
      y: Number(edgeRecord.y),
      order: Number(edgeRecord.order),
      visible: edgeRecord.visible !== false,
    };
  }
  return {
    id: String(edge.id),
    labelId: String(edge.toId),
    textStyleId: String(styleEdge.toId),
    fontId: null,
    fontSize: null,
    width: null,
    fontWeight: null,
    text: String(labelRecord.text),
    x: Number(edgeRecord.x),
    y: Number(edgeRecord.y),
    order: Number(edgeRecord.order),
    visible: edgeRecord.visible !== false,
  };
}

async function buildSceneView(store: Store, sceneId: string): Promise<DomainSceneView | undefined> {
  const scene = await store.nodes.Scene.getById(sceneId as never).catch(() => undefined);
  if (!scene) return undefined;
  const record = scene as unknown as Record<string, unknown>;
  const outputEdges = await store.edges.defaultOutput.findFrom(scene);
  const outputEdge = outputEdges[0];
  if (!outputEdge) throw new DomainError("unavailable", `Scene "${sceneId}" is missing its default output.`);
  const placements = await store.edges.places.findFrom(scene);
  const views: DomainPlacementView[] = [];
  for (const edge of placements) {
    const view = await readPlacedView(store, edge);
    if (view) views.push(view);
  }
  views.sort((a, b) => a.order - b.order || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return {
    id: String(scene.id),
    name: String(record.name),
    width: Number(record.width),
    height: Number(record.height),
    // Rows written before the device field carry no value and read as a
    // custom screen rather than failing or adopting a catalog device.
    deviceId: typeof record.deviceId === "string" ? String(record.deviceId) : null,
    revision: Number(record.revision),
    outputProfileId: String(outputEdge.toId),
    exportCoverage: normalizeCoverage(record.exportCoverage as CharacterCoverage),
    placements: views,
  };
}

// ---- Transaction helpers: one rule lives in exactly one place ----

// Fetch-or-not-found is one rule shared by every entity lookup below; the
// named wrappers bind only the entity and its message.
async function requireEntity<T>(fetch: () => Promise<T | undefined>, message: string): Promise<T> {
  const entity = await fetch().catch(() => undefined);
  if (!entity) throw new DomainError("not-found", message);
  return entity;
}

async function requireScene(tx: Store, sceneId: string, message: string) {
  return requireEntity(() => tx.nodes.Scene.getById(sceneId as never), message);
}

type SceneHandle = Awaited<ReturnType<typeof requireScene>>;

function requireSceneRevision(scene: SceneHandle, expectedRevision: number, message: string): void {
  const revision = Number((scene as unknown as Record<string, unknown>).revision);
  if (revision !== expectedRevision) throw new DomainError("conflict", message);
}

async function requireOwnedPlacement(tx: Store, sceneId: string, placementId: string) {
  const edge = await tx.edges.places.getById(placementId as never).catch(() => undefined);
  if (!edge || String(edge.fromId) !== sceneId) {
    throw new DomainError("not-found", `Placement "${placementId}" does not exist in scene "${sceneId}".`);
  }
  return edge;
}

type PlacementHandle = Awaited<ReturnType<typeof requireOwnedPlacement>>;

async function requirePlacementLabel(tx: Store, placementId: string, labelId: unknown) {
  return requireEntity(
    () => tx.nodes.Label.getById(labelId as never),
    `Placement "${placementId}" links to a missing label.`,
  );
}

type LabelHandle = Awaited<ReturnType<typeof requirePlacementLabel>>;

async function requireTextStyle(tx: Store, textStyleId: string) {
  return requireEntity(
    () => tx.nodes.TextStyle.getById(textStyleId as never),
    `Text style "${textStyleId}" does not exist.`,
  );
}

type TextStyleHandle = Awaited<ReturnType<typeof requireTextStyle>>;

async function requireDirectFont(txStore: Store, fontId: string) {
  return requireEntity(() => txStore.nodes.Font.getById(fontId as never), `Font "${fontId}" does not exist.`);
}

// The variant style's resolved wght, for a variant-to-direct conversion that
// carries no explicit weight. Saved variants always carry the font's complete
// axis set (validateVariantSettings rejects a missing wght), so the entry is
// read directly. Missing links read as no carried weight rather than
// failing: the destination default then applies.
async function resolveStyleWght(tx: Store, textStyleId: unknown): Promise<number | null> {
  const style = await tx.nodes.TextStyle.getById(textStyleId as never).catch(() => undefined);
  if (!style) return null;
  const variantEdges = await tx.edges.usesVariant.findFrom(style);
  const variantEdge = variantEdges[0];
  if (!variantEdge) return null;
  const variant = await tx.nodes.FontVariant.getById(variantEdge.toId as never).catch(() => undefined);
  const axes = (variant as unknown as Record<string, unknown> | undefined)?.axes as Record<string, unknown> | undefined;
  const wght = axes?.wght;
  return typeof wght === "number" && Number.isFinite(wght) ? wght : null;
}

// Direct fields merge against the stored triple before the range check, so a
// font switch without sizes keeps the label's own size, width and resolved
// weight. An explicit weight is strictly validated against the target font;
// a carried weight (kept across a font switch or converted from the previous
// style) resolves into the destination's support instead of failing.
async function collectDirectProps(
  tx: Store,
  labelRecord: Record<string, unknown>,
  patch: { fontId?: string; fontSize?: number; width?: number; fontWeight?: number | null },
  previousWght: number | null,
): Promise<Record<string, unknown>> {
  const next: Record<string, unknown> = {};
  if (patch.fontId !== undefined) next.fontId = patch.fontId;
  else if (typeof labelRecord.fontId !== "string") {
    failInvalid("Switching a variant label to a direct font needs a font reference.");
  }
  const fontSize = patch.fontSize ?? labelRecord.fontSize;
  const width = patch.width ?? labelRecord.width;
  checkDirectFontSize(fontSize);
  checkDirectWidth(width);
  next.fontSize = fontSize;
  next.width = width;
  const targetFontId = (next.fontId ?? labelRecord.fontId) as string;
  const targetFont = await requireDirectFont(tx, targetFontId);
  const axis = fontWghtAxis(targetFont as unknown as Record<string, unknown>);
  if (patch.fontWeight !== undefined) {
    checkDirectFontWeight(patch.fontWeight, axis);
    next.fontWeight = patch.fontWeight;
  } else {
    const stored = labelRecord.fontWeight;
    const carried = typeof stored === "number" && Number.isFinite(stored) ? stored : previousWght;
    next.fontWeight = resolveCarriedFontWeight(carried, axis);
  }
  return next;
}

async function requireOutputProfile(tx: Store, outputProfileId: string) {
  return requireEntity(
    () => tx.nodes.OutputProfile.getById(outputProfileId as never),
    `Output profile "${outputProfileId}" does not exist.`,
  );
}

type OutputProfileHandle = Awaited<ReturnType<typeof requireOutputProfile>>;

// Label ↔ style links are replaced wholesale, so add and update share one rule.
async function setLabelStyle(tx: Store, label: LabelHandle, style: TextStyleHandle): Promise<void> {
  const styleEdges = await tx.edges.styledAs.findFrom(label);
  for (const styleEdge of styleEdges) await tx.edges.styledAs.delete(styleEdge.id);
  await tx.edges.styledAs.create(label, style, {});
}

// A label survives while any placement still points at it.
async function retireLabelIfOrphaned(tx: Store, label: LabelHandle): Promise<void> {
  const remaining = await tx.edges.places.findTo(label);
  if (remaining.length > 0) return;
  const styleEdges = await tx.edges.styledAs.findFrom(label);
  for (const styleEdge of styleEdges) await tx.edges.styledAs.delete(styleEdge.id);
  await tx.nodes.Label.hardDelete(label.id);
}

async function bumpSceneRevision(tx: Store, scene: SceneHandle, expectedRevision: number): Promise<void> {
  await tx.nodes.Scene.update(scene.id, { revision: expectedRevision + 1, updatedAt: now() } as never);
}

async function setSceneOutput(tx: Store, scene: SceneHandle, profile: OutputProfileHandle): Promise<void> {
  const edges = await tx.edges.defaultOutput.findFrom(scene);
  for (const edge of edges) await tx.edges.defaultOutput.delete(edge.id);
  await tx.edges.defaultOutput.create(scene, profile, {});
}

async function applyLabelContent(tx: Store, label: LabelHandle, patch: SceneLabelPatch): Promise<void> {
  if (patch.text !== undefined) await tx.nodes.Label.update(label.id, { text: patch.text });
  if (patch.textStyleId !== undefined) {
    const style = await requireTextStyle(tx, patch.textStyleId);
    await setLabelStyle(tx, label, style);
    // A style relink drops the direct fields wholesale: the variant owns the
    // label's size and weight from here on, never a leftover per-label
    // override.
    await tx.nodes.Label.update(label.id, { fontId: null, fontSize: null, width: null, fontWeight: null });
    return;
  }
  if (
    patch.fontId !== undefined ||
    patch.fontSize !== undefined ||
    patch.width !== undefined ||
    patch.fontWeight !== undefined
  ) {
    const styleEdges = await tx.edges.styledAs.findFrom(label);
    // A variant-to-direct conversion preserves the style's resolved wght as
    // the carried weight when the patch carries none itself.
    const previousWght = styleEdges[0] ? await resolveStyleWght(tx, styleEdges[0].toId) : null;
    for (const styleEdge of styleEdges) await tx.edges.styledAs.delete(styleEdge.id);
    const record = await tx.nodes.Label.getById(label.id).catch(() => undefined);
    const current = (record ?? label) as unknown as Record<string, unknown>;
    await tx.nodes.Label.update(label.id, await collectDirectProps(tx, current, patch, previousWght));
  }
}

// Scalar scene fields merge into the next node props; the output edge swaps
// separately in setSceneOutput.
function applySceneScalars(
  record: Record<string, unknown>,
  patch: Partial<Pick<DomainSceneView, "name" | "width" | "height" | "deviceId" | "exportCoverage">>,
  next: Record<string, unknown>,
): void {
  if (patch.name !== undefined) {
    checkSceneName(patch.name);
    next.name = patch.name;
  }
  if (patch.width !== undefined || patch.height !== undefined) {
    checkSceneDimensions(patch.width ?? record.width, patch.height ?? record.height);
    if (patch.width !== undefined) next.width = patch.width;
    if (patch.height !== undefined) next.height = patch.height;
  }
  if (patch.deviceId !== undefined) {
    checkSceneDevice(patch.deviceId);
    next.deviceId = patch.deviceId;
  }
  if (patch.exportCoverage !== undefined) {
    next.exportCoverage = normalizeSceneCoverage(patch.exportCoverage);
  }
}

function collectPlacementProps(patch: {
  x?: number;
  y?: number;
  order?: number;
  visible?: boolean;
}): Record<string, unknown> {
  const props: Record<string, unknown> = {};
  if (patch.x !== undefined) props.x = patch.x;
  if (patch.y !== undefined) props.y = patch.y;
  if (patch.order !== undefined) props.order = patch.order;
  if (patch.visible !== undefined) props.visible = patch.visible;
  return props;
}

function nextPlacementOrder(existing: readonly unknown[]): number {
  let order = 0;
  for (const edge of existing) {
    order = Math.max(order, Number((edge as unknown as Record<string, unknown>).order) + 1);
  }
  return order;
}

// ---- Scene commands: thin orchestration over the helpers above ----

export async function listScenes(backend: DomainBackend): Promise<DomainSceneView[]> {
  const rows = await backend.store
    .query()
    .from("Scene", "s")
    .select((ctx) => ctx.s)
    .execute();
  const views: DomainSceneView[] = [];
  for (const row of rows) {
    const view = await buildSceneView(backend.store, String(row.id));
    if (view) views.push(view);
  }
  views.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : a.id < b.id ? -1 : 1));
  return views;
}

export async function getScene(backend: DomainBackend, id: string): Promise<DomainSceneView | undefined> {
  return buildSceneView(backend.store, id);
}

export async function createScene(
  backend: DomainBackend,
  input: {
    name: string;
    width: number;
    height: number;
    deviceId?: string | null;
    outputProfileId: string;
    exportCoverage?: CharacterCoverage;
  },
): Promise<DomainSceneView> {
  if (!input || typeof input !== "object") failInvalid("Scene creation needs an input object.");
  checkSceneName(input.name);
  checkSceneDimensions(input.width, input.height);
  checkSceneDevice(input.deviceId);
  await requireOutputProfile(backend.store, input.outputProfileId);
  const coverage = normalizeSceneCoverage(input.exportCoverage ?? { presetIds: ["ascii"], extraRanges: [] });
  const created = await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const stamp = now();
    const scene = await txStore.nodes.Scene.create({
      name: input.name,
      width: input.width,
      height: input.height,
      deviceId: input.deviceId ?? null,
      exportCoverage: coverage as never,
      revision: 1,
      createdAt: stamp,
      updatedAt: stamp,
    });
    const profile = await requireOutputProfile(txStore, input.outputProfileId);
    await txStore.edges.defaultOutput.create(scene, profile, {});
    return String(scene.id);
  });
  const view = await buildSceneView(backend.store, created);
  if (!view) throw new DomainError("unavailable", "Scene vanished after creation.");
  return view;
}

// ---- Default composition: one implicit persistent scene ----

// Durable default association: a scene id in the auxiliary key-value table,
// adopted or created inside one outer transaction (see below). The graph
// schema stays untouched; the marker is the only new durable state.
export const DEFAULT_SCENE_KEY = "screen:default-scene-id";

// Advisory-lock key serializing concurrent default resolutions at the
// database: the loser blocks on the winner's transaction, then re-reads the
// winner's marker below instead of creating a duplicate. Distinct from the
// legacy-import lock in importer.ts.
const DEFAULT_SCENE_LOCK_A = 818528;
const DEFAULT_SCENE_LOCK_B = 1;

function compareSceneAge(a: Record<string, unknown>, b: Record<string, unknown>): number {
  const age = Number(a.createdAt) - Number(b.createdAt);
  if (age !== 0) return age;
  const left = String(a.id);
  const right = String(b.id);
  return left < right ? -1 : left > right ? 1 : 0;
}

/**
 * Resolve the one implicit default composition: the stored marker when it
 * still names a scene, otherwise the oldest saved scene by (createdAt, then
 * stable id), otherwise a new scene from the given creation params. All
 * check-then-act steps run in one outer transaction under an advisory lock,
 * so repeat calls, reloads, StrictMode replays and concurrent tabs converge
 * on one id without duplicate creation. Existing scenes are never renamed,
 * modified or deleted to designate the default.
 */
export async function ensureDefaultScene(
  backend: DomainBackend,
  input: { name: string; width: number; height: number; deviceId?: string | null; outputProfileId: string },
): Promise<DomainSceneView> {
  if (!input || typeof input !== "object") failInvalid("Default composition needs an input object.");
  checkSceneName(input.name);
  checkSceneDimensions(input.width, input.height);
  checkSceneDevice(input.deviceId);
  await requireOutputProfile(backend.store, input.outputProfileId);
  let id = "";
  await backend.db.transaction(async (txDb) => {
    const tx = txDb as unknown as AuxDb;
    // Serialize simultaneous resolutions at the database; the lock is
    // transaction-scoped, so the loser re-reads the winner's marker below.
    await tx.execute(sql`SELECT pg_advisory_xact_lock(${DEFAULT_SCENE_LOCK_A}, ${DEFAULT_SCENE_LOCK_B})`);
    // Transaction-scoped graph store over the same handle: graph and marker
    // writes commit or roll back as one unit (see importer.ts).
    const txStore = createStore(
      domainGraph,
      createPostgresBackend(txDb as never, { vector: false, fulltext: false }),
    ) as Store;
    const marked = await kvGet(tx, DEFAULT_SCENE_KEY);
    if (marked !== undefined) {
      const kept = await buildSceneView(txStore, marked);
      if (kept) {
        id = kept.id;
        return;
      }
      // A marker naming a deleted scene falls through to adoption below,
      // which overwrites the stale marker.
    }
    const rows = await txStore
      .query()
      .from("Scene", "s")
      .select((ctx) => ctx.s)
      .execute();
    const oldest = rows.map((row) => row as unknown as Record<string, unknown>).sort(compareSceneAge)[0];
    if (oldest) {
      id = String(oldest.id);
      await kvPut(tx, DEFAULT_SCENE_KEY, id);
      return;
    }
    const coverage = normalizeSceneCoverage({ presetIds: ["ascii"], extraRanges: [] });
    const stamp = now();
    const scene = await txStore.nodes.Scene.create({
      name: input.name,
      width: input.width,
      height: input.height,
      deviceId: input.deviceId ?? null,
      exportCoverage: coverage as never,
      revision: 1,
      createdAt: stamp,
      updatedAt: stamp,
    });
    const profile = await requireOutputProfile(txStore, input.outputProfileId);
    await txStore.edges.defaultOutput.create(scene, profile, {});
    id = String(scene.id);
    await kvPut(tx, DEFAULT_SCENE_KEY, id);
  });
  const view = await buildSceneView(backend.store, id);
  if (!view) throw new DomainError("unavailable", "Default composition vanished after resolution.");
  return view;
}

export async function updateScene(
  backend: DomainBackend,
  id: string,
  patch: Partial<
    Pick<DomainSceneView, "name" | "width" | "height" | "deviceId" | "outputProfileId" | "exportCoverage">
  >,
  expectedRevision: number,
): Promise<DomainSceneView> {
  checkScenePatchShape(patch);
  if (!Number.isInteger(expectedRevision)) failInvalid("Scene updates need an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, id, `Scene "${id}" does not exist; refusing to recreate it.`);
    requireSceneRevision(
      scene,
      expectedRevision,
      `Scene "${id}" changed underneath this edit (expected revision ${expectedRevision}).`,
    );
    const record = scene as unknown as Record<string, unknown>;
    const next: Record<string, unknown> = { updatedAt: now(), revision: expectedRevision + 1 };
    applySceneScalars(record, patch, next);
    if (patch.outputProfileId !== undefined) {
      const profile = await requireOutputProfile(txStore, patch.outputProfileId);
      await setSceneOutput(txStore, scene, profile);
    }
    await txStore.nodes.Scene.update(scene.id, next as never);
  });
  const view = await buildSceneView(backend.store, id);
  if (!view) throw new DomainError("not-found", `Scene "${id}" does not exist.`);
  return view;
}

export async function deleteScene(backend: DomainBackend, id: string, expectedRevision: number): Promise<void> {
  if (!Number.isInteger(expectedRevision)) failInvalid("Scene deletion needs an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, id, `Scene "${id}" does not exist.`);
    requireSceneRevision(scene, expectedRevision, `Scene "${id}" changed underneath this delete.`);
    const placements = await txStore.edges.places.findFrom(scene);
    for (const edge of placements) {
      await txStore.edges.places.delete(edge.id);
      const label = await txStore.nodes.Label.getById(edge.toId as never).catch(() => undefined);
      if (!label) continue;
      await retireLabelIfOrphaned(txStore, label);
    }
    const outputs = await txStore.edges.defaultOutput.findFrom(scene);
    for (const edge of outputs) await txStore.edges.defaultOutput.delete(edge.id);
    await txStore.nodes.Scene.hardDelete(scene.id);
  });
}

export async function addSceneLabel(
  backend: DomainBackend,
  sceneId: string,
  input: SceneLabelInput,
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  checkLabelInput(input);
  if (!Number.isInteger(expectedSceneRevision)) failInvalid("Label placement needs an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, sceneId, `Scene "${sceneId}" does not exist.`);
    requireSceneRevision(scene, expectedSceneRevision, `Scene "${sceneId}" changed underneath this edit.`);
    // A direct label is created with its own font fields and no style edge;
    // no hidden variant or shared style is created or touched. The weight
    // override defaults to the font default when absent.
    const label =
      input.textStyleId !== undefined
        ? await txStore.nodes.Label.create({ text: input.text })
        : await txStore.nodes.Label.create({
            text: input.text,
            fontId: input.fontId,
            fontSize: input.fontSize,
            width: input.width,
            fontWeight: input.fontWeight ?? null,
          });
    if (input.textStyleId !== undefined) {
      const style = await requireTextStyle(txStore, input.textStyleId);
      await setLabelStyle(txStore, label, style);
    } else {
      const font = await requireDirectFont(txStore, input.fontId);
      checkDirectFontWeight(input.fontWeight, fontWghtAxis(font as unknown as Record<string, unknown>));
    }
    const existing = await txStore.edges.places.findFrom(scene);
    await txStore.edges.places.create(scene, label, { x: input.x, y: input.y, order: nextPlacementOrder(existing) });
    await bumpSceneRevision(txStore, scene, expectedSceneRevision);
  });
  const view = await buildSceneView(backend.store, sceneId);
  if (!view) throw new DomainError("not-found", `Scene "${sceneId}" does not exist.`);
  return view;
}

export async function updateSceneLabel(
  backend: DomainBackend,
  sceneId: string,
  placementId: string,
  patch: SceneLabelPatch,
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  checkLabelPatchShape(patch);
  if (!Number.isInteger(expectedSceneRevision)) failInvalid("Label updates need an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, sceneId, `Scene "${sceneId}" does not exist.`);
    requireSceneRevision(scene, expectedSceneRevision, `Scene "${sceneId}" changed underneath this edit.`);
    const edge = await requireOwnedPlacement(txStore, sceneId, placementId);
    checkPlacementMove(edge, patch);
    if (patch.order !== undefined) checkPlacementOrder(patch.order);
    const label = await requirePlacementLabel(txStore, placementId, edge.toId);
    await applyLabelContent(txStore, label, patch);
    const props = collectPlacementProps(patch);
    if (Object.keys(props).length > 0) await txStore.edges.places.update(edge.id, props as never);
    await bumpSceneRevision(txStore, scene, expectedSceneRevision);
  });
  const view = await buildSceneView(backend.store, sceneId);
  if (!view) throw new DomainError("not-found", `Scene "${sceneId}" does not exist.`);
  return view;
}

export async function removeSceneLabel(
  backend: DomainBackend,
  sceneId: string,
  placementId: string,
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  if (!Number.isInteger(expectedSceneRevision)) failInvalid("Label removal needs an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, sceneId, `Scene "${sceneId}" does not exist.`);
    requireSceneRevision(scene, expectedSceneRevision, `Scene "${sceneId}" changed underneath this edit.`);
    const edge = await requireOwnedPlacement(txStore, sceneId, placementId);
    await txStore.edges.places.delete(edge.id);
    const label = await txStore.nodes.Label.getById(edge.toId as never).catch(() => undefined);
    if (label) await retireLabelIfOrphaned(txStore, label);
    await bumpSceneRevision(txStore, scene, expectedSceneRevision);
  });
  const view = await buildSceneView(backend.store, sceneId);
  if (!view) throw new DomainError("not-found", `Scene "${sceneId}" does not exist.`);
  return view;
}

// Atomic layer reorder: one revision-guarded transaction assigns dense orders
// 0..n-1 following the given bottom-to-top paint sequence (back first, front
// last), so sparse or tied integer orders collapse to the exact visual order
// without changing placement identity. A failed validation or a stale
// revision rolls back without touching state; a missing scene reports
// not-found without recreating it. Undo/redo keep working because the
// revision bump and the id-free snapshot restore both cover orders.
export async function reorderSceneLabels(
  backend: DomainBackend,
  sceneId: string,
  orderedPlacementIds: string[],
  expectedRevision: number,
): Promise<DomainSceneView> {
  if (
    !Array.isArray(orderedPlacementIds) ||
    orderedPlacementIds.some((id) => typeof id !== "string" || id.length === 0)
  ) {
    failInvalid("Layer reorder needs an array of placement ids in bottom-to-top order.");
  }
  if (new Set(orderedPlacementIds).size !== orderedPlacementIds.length) {
    failInvalid("Layer reorder needs each placement id exactly once.");
  }
  if (!Number.isInteger(expectedRevision)) failInvalid("Layer reorder needs an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, sceneId, `Scene "${sceneId}" does not exist.`);
    requireSceneRevision(scene, expectedRevision, `Scene "${sceneId}" changed underneath this edit.`);
    const edges = await txStore.edges.places.findFrom(scene);
    if (edges.length !== orderedPlacementIds.length) {
      failInvalid("Layer reorder must list every on-scene label exactly once.");
    }
    const byId = new Map(edges.map((edge) => [String(edge.id), edge]));
    for (const id of orderedPlacementIds) {
      if (!byId.has(id)) failInvalid("Layer reorder lists a label that is not on this scene.");
    }
    for (let index = 0; index < orderedPlacementIds.length; index += 1) {
      const edge = byId.get(orderedPlacementIds[index]!)!;
      const record = edge as unknown as Record<string, unknown>;
      if (Number(record.order) !== index) {
        await txStore.edges.places.update(edge.id, { order: index } as never);
      }
    }
    await bumpSceneRevision(txStore, scene, expectedRevision);
  });
  const view = await buildSceneView(backend.store, sceneId);
  if (!view) throw new DomainError("not-found", `Scene "${sceneId}" does not exist.`);
  return view;
}

// Snapshot restores carry no placement ids: labels pair by content order, so
// re-created ids from an earlier undo never confuse the match and duplicate
// identical labels restore as the same multiset.
function checkSnapshotInput(snapshot: unknown): asserts snapshot is SceneSnapshotInput {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) {
    failInvalid("Scene restore needs a snapshot object.");
  }
  const candidate = snapshot as Record<string, unknown>;
  checkSceneName(candidate.name);
  checkSceneDimensions(candidate.width, candidate.height);
  if (candidate.deviceId === undefined)
    failInvalid("Scene restore needs an explicit device selection (string or null).");
  checkSceneDevice(candidate.deviceId);
  if (typeof candidate.outputProfileId !== "string" || candidate.outputProfileId.length === 0) {
    failInvalid("Scene restore needs an output profile id.");
  }
  if (!Array.isArray(candidate.placements)) failInvalid("Scene restore needs a placements array.");
  for (const placement of candidate.placements) {
    if (!placement || typeof placement !== "object") failInvalid("Scene restore placements must be objects.");
    const entry = placement as Record<string, unknown>;
    checkLabelText(entry.text);
    if (entry.visible !== undefined && typeof entry.visible !== "boolean")
      failInvalid("Label visibility must be a boolean.");
    // Historical snapshots always carry a style; direct labels carry the
    // font fields with an explicit null style. The weight override stays
    // optional: snapshots predating it omit the field and read as default.
    if (entry.textStyleId !== undefined && entry.textStyleId !== null) {
      if (typeof entry.textStyleId !== "string" || entry.textStyleId.length === 0) {
        failInvalid("Scene restore placements need a text style id.");
      }
      if (
        (entry.fontId !== undefined && entry.fontId !== null) ||
        (entry.fontSize !== undefined && entry.fontSize !== null) ||
        (entry.width !== undefined && entry.width !== null) ||
        (entry.fontWeight !== undefined && entry.fontWeight !== null)
      ) {
        failInvalid("Scene restore placements cannot combine a text style with direct font fields.");
      }
    } else {
      checkDirectFontId(entry.fontId);
      checkDirectFontSize(entry.fontSize);
      checkDirectWidth(entry.width);
      checkDirectFontWeightShape(entry.fontWeight);
    }
    checkPlacementPoint(entry.x, entry.y);
    checkPlacementOrder(entry.order);
  }
}

// Atomic undo/redo restore: one revision-guarded transaction replaces the
// whole scene content. Every boundary rule above still applies, and any
// rejection (stale revision, unknown style, invalid content) rolls back the
// transaction, so a failed restore never leaves a partial scene behind. A
// missing scene reports not-found without recreating it.
export async function restoreSceneSnapshot(
  backend: DomainBackend,
  id: string,
  expectedRevision: number,
  snapshot: SceneSnapshotInput,
): Promise<DomainSceneView> {
  checkSnapshotInput(snapshot);
  if (!Number.isInteger(expectedRevision)) failInvalid("Scene restore needs an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, id, `Scene "${id}" does not exist; refusing to recreate it.`);
    requireSceneRevision(
      scene,
      expectedRevision,
      `Scene "${id}" changed underneath this edit (expected revision ${expectedRevision}).`,
    );
    // Validate every referenced row before touching state.
    const profile = await requireOutputProfile(txStore, snapshot.outputProfileId);
    const record = scene as unknown as Record<string, unknown>;
    const next: Record<string, unknown> = { updatedAt: now(), revision: expectedRevision + 1 };
    applySceneScalars(
      record,
      {
        name: snapshot.name,
        width: snapshot.width,
        height: snapshot.height,
        deviceId: snapshot.deviceId,
        exportCoverage: snapshot.exportCoverage,
      },
      next,
    );
    await txStore.nodes.Scene.update(scene.id, next as never);
    await setSceneOutput(txStore, scene, profile);

    const edges = await txStore.edges.places.findFrom(scene);
    const current: Array<{
      edge: PlacementHandle;
      label: LabelHandle;
      text: string;
      textStyleId: string | null;
      fontId: string | null;
      fontSize: number | null;
      width: number | null;
      fontWeight: number | null;
      x: number;
      y: number;
      order: number;
      visible: boolean;
    }> = [];
    const torn: PlacementHandle[] = [];
    for (const edge of edges) {
      const label = await txStore.nodes.Label.getById(edge.toId as never).catch(() => undefined);
      if (!label) {
        torn.push(edge);
        continue;
      }
      const labelRecord = label as unknown as Record<string, unknown>;
      const styleEdges = await txStore.edges.styledAs.findFrom(label);
      const styleEdge = styleEdges[0];
      const directFontId = typeof labelRecord.fontId === "string" ? labelRecord.fontId : null;
      if (!styleEdge && directFontId === null) {
        throw new DomainError("unavailable", `Placement "${String(edge.id)}" links to a missing text style.`);
      }
      const edgeRecord = edge as unknown as Record<string, unknown>;
      const storedWeight = labelRecord.fontWeight;
      current.push({
        edge,
        label,
        text: String(labelRecord.text),
        textStyleId: styleEdge ? String(styleEdge.toId) : null,
        fontId: styleEdge ? null : directFontId,
        fontSize: styleEdge ? null : Number(labelRecord.fontSize),
        width: styleEdge ? null : Number(labelRecord.width),
        fontWeight:
          styleEdge || typeof storedWeight !== "number" || !Number.isFinite(storedWeight) ? null : storedWeight,
        x: Number(edgeRecord.x),
        y: Number(edgeRecord.y),
        order: Number(edgeRecord.order),
        visible: edgeRecord.visible !== false,
      });
    }
    current.sort((a, b) => a.order - b.order || (String(a.edge.id) < String(b.edge.id) ? -1 : 1));
    const target = snapshot.placements.map((placement, index) => ({ ...placement, index }));
    target.sort((a, b) => a.order - b.order || a.index - b.index);
    for (const entry of target) {
      if (entry.textStyleId !== undefined && entry.textStyleId !== null) {
        await requireTextStyle(txStore, entry.textStyleId);
      } else {
        const font = await requireDirectFont(txStore, entry.fontId!);
        checkDirectFontWeight(entry.fontWeight ?? null, fontWghtAxis(font as unknown as Record<string, unknown>));
      }
    }

    const shared = Math.min(current.length, target.length);
    for (let index = 0; index < shared; index++) {
      const entry = current[index]!;
      const wanted = target[index]!;
      if (entry.text !== wanted.text) await txStore.nodes.Label.update(entry.label.id, { text: wanted.text });
      const wantedStyle = wanted.textStyleId ?? null;
      if (entry.textStyleId !== wantedStyle) {
        if (wantedStyle !== null) {
          await setLabelStyle(txStore, entry.label, await requireTextStyle(txStore, wantedStyle));
        } else {
          const styleEdges = await txStore.edges.styledAs.findFrom(entry.label);
          for (const styleEdge of styleEdges) await txStore.edges.styledAs.delete(styleEdge.id);
        }
      }
      // Direct fields always land wholesale on a kind match; a kind switch
      // without sizes cannot happen here because the snapshot was validated.
      // An omitted weight reads as the font default, like older snapshots.
      const wantedWeight = wanted.fontWeight ?? null;
      const wantedDirect =
        wantedStyle === null
          ? { fontId: wanted.fontId!, fontSize: wanted.fontSize!, width: wanted.width!, fontWeight: wantedWeight }
          : { fontId: null, fontSize: null, width: null, fontWeight: null };
      const directProps: Record<string, unknown> = {};
      if (entry.fontId !== wantedDirect.fontId) directProps.fontId = wantedDirect.fontId;
      if (entry.fontSize !== wantedDirect.fontSize) directProps.fontSize = wantedDirect.fontSize;
      if (entry.width !== wantedDirect.width) directProps.width = wantedDirect.width;
      if (entry.fontWeight !== wantedDirect.fontWeight) directProps.fontWeight = wantedDirect.fontWeight;
      if (Object.keys(directProps).length > 0) {
        await txStore.nodes.Label.update(entry.label.id, directProps as never);
      }
      const props: Record<string, unknown> = {};
      if (entry.x !== wanted.x) props.x = wanted.x;
      if (entry.y !== wanted.y) props.y = wanted.y;
      if (entry.order !== wanted.order) props.order = wanted.order;
      if (entry.visible !== (wanted.visible !== false)) props.visible = wanted.visible !== false;
      if (Object.keys(props).length > 0) await txStore.edges.places.update(entry.edge.id, props as never);
    }
    for (let index = shared; index < target.length; index++) {
      const wanted = target[index]!;
      const wantedStyle = wanted.textStyleId ?? null;
      const label =
        wantedStyle !== null
          ? await txStore.nodes.Label.create({ text: wanted.text })
          : await txStore.nodes.Label.create({
              text: wanted.text,
              fontId: wanted.fontId!,
              fontSize: wanted.fontSize!,
              width: wanted.width!,
              fontWeight: wanted.fontWeight ?? null,
            });
      if (wantedStyle !== null) {
        await setLabelStyle(txStore, label, await requireTextStyle(txStore, wantedStyle));
      }
      await txStore.edges.places.create(scene, label, {
        x: wanted.x,
        y: wanted.y,
        order: wanted.order,
        visible: wanted.visible !== false,
      });
    }
    for (let index = shared; index < current.length; index++) {
      const entry = current[index]!;
      await txStore.edges.places.delete(entry.edge.id);
      await retireLabelIfOrphaned(txStore, entry.label);
    }
    for (const edge of torn) await txStore.edges.places.delete(edge.id);
  });
  const view = await buildSceneView(backend.store, id);
  if (!view) throw new DomainError("not-found", `Scene "${id}" does not exist.`);
  return view;
}
