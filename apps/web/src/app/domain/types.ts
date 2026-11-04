// Shared domain service views. Worker B types scene/export UI against these
// exact names; additive fields are allowed but stated views must stay stable.
// Backed by the graph store (domain/graph.ts) through domain/service.ts.

import type { GrayCurve } from "../features/grayscale/response-curve.ts";
import type { CharacterCoverage } from "./coverage.ts";

export interface DomainTextStyleView {
  id: string;
  name: string;
  fontId: string;
  fontSize: number;
}

export interface DomainOutputProfileView {
  id: string;
  name: string;
  curve: GrayCurve;
}

export interface DomainPlacementView {
  id: string;
  labelId: string;
  textStyleId: string;
  text: string;
  x: number;
  y: number;
  order: number;
}

// Undo/redo snapshot payload: full scene content without placement ids, so a
// restore never depends on expired ids. Labels are matched by content order,
// which keeps duplicate identical labels stable across repeated cycles.
export interface SceneSnapshotPlacement {
  text: string;
  textStyleId: string;
  x: number;
  y: number;
  order: number;
}

export interface SceneSnapshotInput {
  name: string;
  width: number;
  height: number;
  deviceId: string | null;
  outputProfileId: string;
  exportCoverage: CharacterCoverage;
  placements: SceneSnapshotPlacement[];
}

export interface DomainSceneView {
  id: string;
  name: string;
  width: number;
  height: number;
  // Selected catalog device; null means a custom screen with the scene's own
  // width/height. Rows written before this field read back as null.
  deviceId: string | null;
  revision: number;
  outputProfileId: string;
  exportCoverage: CharacterCoverage;
  placements: DomainPlacementView[];
}
