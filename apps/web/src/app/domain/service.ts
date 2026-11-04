// Public domain service for scene/export UI (worker B) and any other
// consumer. Exact exported names below are the integration contract; add
// fields but preserve the stated views. Backed by the ambient domain
// transport (browser worker proxy or direct Node backend).

import type { VariantSettings } from "../variants/model.ts";
import { callDomain } from "./runtime.ts";
import { getDomainVersion as getVersion, subscribeDomain as subscribe } from "./events.ts";
import type {
  DomainOutputProfileView,
  DomainPlacementView,
  DomainSceneView,
  DomainTextStyleView,
} from "./types.ts";

export type {
  DomainOutputProfileView,
  DomainPlacementView,
  DomainSceneView,
  DomainTextStyleView,
} from "./types.ts";

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
  outputProfileId: string;
  exportCoverage?: DomainSceneView["exportCoverage"];
}): Promise<DomainSceneView> {
  return (await callDomain("createScene", [input])) as DomainSceneView;
}

export async function updateScene(
  id: string,
  patch: Partial<Pick<DomainSceneView, "name" | "width" | "height" | "outputProfileId" | "exportCoverage">>,
  expectedRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("updateScene", [id, patch, expectedRevision])) as DomainSceneView;
}

export async function deleteScene(id: string, expectedRevision: number): Promise<void> {
  await callDomain("deleteScene", [id, expectedRevision]);
}

export async function addSceneLabel(
  sceneId: string,
  input: { text: string; textStyleId: string; x: number; y: number },
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("addSceneLabel", [sceneId, input, expectedSceneRevision])) as DomainSceneView;
}

export async function updateSceneLabel(
  sceneId: string,
  placementId: string,
  patch: { text?: string; textStyleId?: string; x?: number; y?: number; order?: number },
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("updateSceneLabel", [sceneId, placementId, patch, expectedSceneRevision])) as DomainSceneView;
}

export async function removeSceneLabel(
  sceneId: string,
  placementId: string,
  expectedSceneRevision: number,
): Promise<DomainSceneView> {
  return (await callDomain("removeSceneLabel", [sceneId, placementId, expectedSceneRevision])) as DomainSceneView;
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
