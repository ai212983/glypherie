// Scene graph commands over scene nodes, placements and labels.

import type { DomainBackend } from "./backend.ts";
import { normalizeCoverage, type CharacterCoverage } from "./coverage.ts";
import { DomainError } from "./errors.ts";
import type {
  DomainPlacementView,
  DomainSceneView,
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

function checkLabelPatchShape(patch: unknown): void {
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
    failInvalid("Label updates need a patch object.");
  }
  const candidate = patch as { text?: unknown };
  if (candidate.text !== undefined) checkLabelText(candidate.text);
}

function checkLabelInput(input: unknown): void {
  if (!input || typeof input !== "object") failInvalid("Label placement needs an input object.");
  const candidate = input as { text?: unknown; x?: unknown; y?: unknown };
  checkLabelText(candidate.text);
  checkPlacementPoint(candidate.x, candidate.y);
}

function normalizeSceneCoverage(coverage: CharacterCoverage): CharacterCoverage {
  try {
    return normalizeCoverage(coverage);
  } catch (error) {
    throw new DomainError("invalid-input", error instanceof Error ? error.message : "Invalid export coverage.", { cause: error });
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

async function readPlacedView(store: Store, edge: { id: unknown; toId: unknown }): Promise<DomainPlacementView | undefined> {
  const edgeRecord = edge as unknown as Record<string, unknown>;
  const label = await store.nodes.Label.getById(edge.toId as never).catch(() => undefined);
  if (!label) return undefined;
  const labelRecord = label as unknown as Record<string, unknown>;
  const styleEdges = await store.edges.styledAs.findFrom(label);
  const styleEdge = styleEdges[0];
  if (!styleEdge) return undefined;
  return {
    id: String(edge.id),
    labelId: String(edge.toId),
    textStyleId: String(styleEdge.toId),
    text: String(labelRecord.text),
    x: Number(edgeRecord.x),
    y: Number(edgeRecord.y),
    order: Number(edgeRecord.order),
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

async function applyLabelContent(
  tx: Store,
  label: LabelHandle,
  patch: { text?: string; textStyleId?: string },
): Promise<void> {
  if (patch.text !== undefined) await tx.nodes.Label.update(label.id, { text: patch.text });
  if (patch.textStyleId !== undefined) {
    const style = await requireTextStyle(tx, patch.textStyleId);
    await setLabelStyle(tx, label, style);
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

function collectPlacementProps(patch: { x?: number; y?: number; order?: number }): Record<string, unknown> {
  const props: Record<string, unknown> = {};
  if (patch.x !== undefined) props.x = patch.x;
  if (patch.y !== undefined) props.y = patch.y;
  if (patch.order !== undefined) props.order = patch.order;
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
  const rows = await backend.store.query().from("Scene", "s").select((ctx) => ctx.s).execute();
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
  input: { name: string; width: number; height: number; deviceId?: string | null; outputProfileId: string; exportCoverage?: CharacterCoverage },
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

export async function updateScene(
  backend: DomainBackend,
  id: string,
  patch: Partial<Pick<DomainSceneView, "name" | "width" | "height" | "deviceId" | "outputProfileId" | "exportCoverage">>,
  expectedRevision: number,
): Promise<DomainSceneView> {
  checkScenePatchShape(patch);
  if (!Number.isInteger(expectedRevision)) failInvalid("Scene updates need an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, id, `Scene "${id}" does not exist; refusing to recreate it.`);
    requireSceneRevision(scene, expectedRevision, `Scene "${id}" changed underneath this edit (expected revision ${expectedRevision}).`);
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
  input: { text: string; textStyleId: string; x: number; y: number },
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  checkLabelInput(input);
  if (!Number.isInteger(expectedSceneRevision)) failInvalid("Label placement needs an integer expected revision.");
  await backend.store.transaction(async (tx) => {
    const txStore = tx as unknown as Store;
    const scene = await requireScene(txStore, sceneId, `Scene "${sceneId}" does not exist.`);
    requireSceneRevision(scene, expectedSceneRevision, `Scene "${sceneId}" changed underneath this edit.`);
    const style = await requireTextStyle(txStore, input.textStyleId);
    const label = await txStore.nodes.Label.create({ text: input.text });
    await setLabelStyle(txStore, label, style);
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
  patch: { text?: string; textStyleId?: string; x?: number; y?: number; order?: number },
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
  if (candidate.deviceId === undefined) failInvalid("Scene restore needs an explicit device selection (string or null).");
  checkSceneDevice(candidate.deviceId);
  if (typeof candidate.outputProfileId !== "string" || candidate.outputProfileId.length === 0) {
    failInvalid("Scene restore needs an output profile id.");
  }
  if (!Array.isArray(candidate.placements)) failInvalid("Scene restore needs a placements array.");
  for (const placement of candidate.placements) {
    if (!placement || typeof placement !== "object") failInvalid("Scene restore placements must be objects.");
    const entry = placement as Record<string, unknown>;
    checkLabelText(entry.text);
    if (typeof entry.textStyleId !== "string" || entry.textStyleId.length === 0) {
      failInvalid("Scene restore placements need a text style id.");
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
    requireSceneRevision(scene, expectedRevision, `Scene "${id}" changed underneath this edit (expected revision ${expectedRevision}).`);
    // Validate every referenced row before touching state.
    const profile = await requireOutputProfile(txStore, snapshot.outputProfileId);
    const record = scene as unknown as Record<string, unknown>;
    const next: Record<string, unknown> = { updatedAt: now(), revision: expectedRevision + 1 };
    applySceneScalars(record, {
      name: snapshot.name,
      width: snapshot.width,
      height: snapshot.height,
      deviceId: snapshot.deviceId,
      exportCoverage: snapshot.exportCoverage,
    }, next);
    await txStore.nodes.Scene.update(scene.id, next as never);
    await setSceneOutput(txStore, scene, profile);

    const edges = await txStore.edges.places.findFrom(scene);
    const current: Array<{
      edge: PlacementHandle;
      label: LabelHandle;
      text: string;
      textStyleId: string;
      x: number;
      y: number;
      order: number;
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
      if (!styleEdge) throw new DomainError("unavailable", `Placement "${String(edge.id)}" links to a missing text style.`);
      const edgeRecord = edge as unknown as Record<string, unknown>;
      current.push({
        edge,
        label,
        text: String(labelRecord.text),
        textStyleId: String(styleEdge.toId),
        x: Number(edgeRecord.x),
        y: Number(edgeRecord.y),
        order: Number(edgeRecord.order),
      });
    }
    current.sort((a, b) => a.order - b.order || (String(a.edge.id) < String(b.edge.id) ? -1 : 1));
    const target = snapshot.placements.map((placement, index) => ({ ...placement, index }));
    target.sort((a, b) => a.order - b.order || a.index - b.index);
    const targetStyles: TextStyleHandle[] = [];
    for (const entry of target) targetStyles.push(await requireTextStyle(txStore, entry.textStyleId));

    const shared = Math.min(current.length, target.length);
    for (let index = 0; index < shared; index++) {
      const entry = current[index]!;
      const wanted = target[index]!;
      if (entry.text !== wanted.text) await txStore.nodes.Label.update(entry.label.id, { text: wanted.text });
      if (entry.textStyleId !== wanted.textStyleId) {
        await setLabelStyle(txStore, entry.label, targetStyles[index]!);
      }
      const props: Record<string, unknown> = {};
      if (entry.x !== wanted.x) props.x = wanted.x;
      if (entry.y !== wanted.y) props.y = wanted.y;
      if (entry.order !== wanted.order) props.order = wanted.order;
      if (Object.keys(props).length > 0) await txStore.edges.places.update(entry.edge.id, props as never);
    }
    for (let index = shared; index < target.length; index++) {
      const wanted = target[index]!;
      const label = await txStore.nodes.Label.create({ text: wanted.text });
      await setLabelStyle(txStore, label, targetStyles[index]!);
      await txStore.edges.places.create(scene, label, { x: wanted.x, y: wanted.y, order: wanted.order });
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
