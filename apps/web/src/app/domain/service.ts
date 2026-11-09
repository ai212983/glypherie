// Public domain service for scene/export UI (worker B) and any other
// consumer. Exact exported names below are the integration contract; add
// fields but preserve the stated views. Backed by the ambient domain
// transport (browser worker proxy or direct Node backend).

import type { VariantSettings } from "../variants/model.ts";
import { callDomain } from "./runtime.ts";
import { getDomainVersion as getVersion, subscribeDomain as subscribe } from "./events.ts";
import type {
  DomainOutputProfileView,
  DomainSceneView,
  DomainTextStyleView,
  SceneLabelInput,
  SceneLabelPatch,
  SceneSnapshotInput,
} from "./types.ts";

export type {
  DomainOutputProfileView,
  DomainPlacementView,
  DomainSceneView,
  DomainTextStyleView,
  SceneLabelInput,
  SceneLabelPatch,
  SceneSnapshotInput,
} from "./types.ts";
export { STALE_OWNER_RECOVERY_MESSAGE } from "./runtime.ts";

export async function listTextStyles(): Promise<DomainTextStyleView[]> {
  return (await callDomain("listTextStyles", [])) as DomainTextStyleView[];
}

export async function listOutputProfiles(): Promise<DomainOutputProfileView[]> {
  return (await callDomain("listOutputProfiles", [])) as DomainOutputProfileView[];
}

export async function listScenes(): Promise<DomainSceneView[]> {
  return (await callDomain("listScenes", [])) as DomainSceneView[];
}

export async function getScene(id: string): Promise<DomainSceneView | undefined> {
  return (await callDomain("getScene", [id])) as DomainSceneView | undefined;
}

export async function createScene(input: {
  name: string;
  width: number;
  height: number;
  deviceId?: string | null;
  outputProfileId: string;
  exportCoverage?: DomainSceneView["exportCoverage"];
}): Promise<DomainSceneView> {
  return (await callDomain("createScene", [input])) as DomainSceneView;
}

/**
 * Resolve the one implicit default composition (stored marker, oldest saved
 * scene, or a new scene from the given params), atomically. The params only
 * take effect when no scene exists yet.
 */
export async function ensureDefaultScene(input: {
  name: string;
  width: number;
  height: number;
  deviceId?: string | null;
  outputProfileId: string;
}): Promise<DomainSceneView> {
  return (await callDomain("ensureDefaultScene", [input])) as DomainSceneView;
}

export async function updateScene(
  id: string,
  patch: Partial<
    Pick<DomainSceneView, "name" | "width" | "height" | "deviceId" | "outputProfileId" | "exportCoverage">
  >,
  expectedRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("updateScene", [id, patch, expectedRevision])) as DomainSceneView;
}

export async function deleteScene(id: string, expectedRevision: number): Promise<void> {
  await callDomain("deleteScene", [id, expectedRevision]);
}

export async function addSceneLabel(
  sceneId: string,
  input: SceneLabelInput,
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("addSceneLabel", [sceneId, input, expectedSceneRevision])) as DomainSceneView;
}

export async function updateSceneLabel(
  sceneId: string,
  placementId: string,
  patch: SceneLabelPatch,
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("updateSceneLabel", [
    sceneId,
    placementId,
    patch,
    expectedSceneRevision,
  ])) as DomainSceneView;
}

export async function removeSceneLabel(
  sceneId: string,
  placementId: string,
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("removeSceneLabel", [sceneId, placementId, expectedSceneRevision])) as DomainSceneView;
}

/**
 * Atomic layer reorder: assigns dense orders 0..n-1 following the given
 * bottom-to-top paint sequence in one revision-guarded transaction, without
 * changing placement identity.
 */
export async function reorderSceneLabels(
  sceneId: string,
  orderedPlacementIds: string[],
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("reorderSceneLabels", [
    sceneId,
    orderedPlacementIds,
    expectedSceneRevision,
  ])) as DomainSceneView;
}

/**
 * Atomic undo/redo restore: one revision-guarded transaction replaces the
 * whole scene content from an id-free snapshot. Any rejection rolls the
 * transaction back, so a failed restore never leaves a partial scene.
 */
export async function restoreSceneSnapshot(
  sceneId: string,
  expectedSceneRevision: number,
  snapshot: SceneSnapshotInput,
): Promise<DomainSceneView> {
  return (await callDomain("restoreSceneSnapshot", [sceneId, expectedSceneRevision, snapshot])) as DomainSceneView;
}

export async function resolveTextStyle(
  textStyleId: string,
  outputProfileId: string,
): Promise<{ id: string; name: string; fontId: string; settings: VariantSettings }> {
  return (await callDomain("resolveTextStyle", [textStyleId, outputProfileId])) as {
    id: string;
    name: string;
    fontId: string;
    settings: VariantSettings;
  };
}

/**
 * Batch resolver: every style, variant, profile and output row resolves in
 * one read transaction, so concurrent edits cannot mix revisions across the
 * batch. Prefer this over Promise.all of individual resolves for exports.
 */
export async function resolveTextStyles(
  textStyleIds: string[],
  outputProfileId: string,
): Promise<Array<{ id: string; name: string; fontId: string; settings: VariantSettings }>> {
  return (await callDomain("resolveTextStyles", [textStyleIds, outputProfileId])) as Array<{
    id: string;
    name: string;
    fontId: string;
    settings: VariantSettings;
  }>;
}

export function subscribeDomain(listener: () => void): () => void {
  return subscribe(listener);
}

export function getDomainVersion(): number {
  return getVersion();
}
