// Shared domain service views. Worker B types scene/export UI against these
// exact names; additive fields are allowed but stated views must stay stable.
// Backed by the graph store (domain/graph.ts) through domain/service.ts.

import type { GrayCurve } from "./output-profiles/curve.ts";
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
  // Exactly one reference is set: a saved variant style, or a direct font
  // with its own size, wrap width and optional wght override (null means the
  // selected font's default). Persisted rows predating direct labels always
  // carry a style; rows predating the weight field read back null.
  textStyleId: string | null;
  fontId: string | null;
  fontSize: number | null;
  width: number | null;
  fontWeight: number | null;
  text: string;
  x: number;
  y: number;
  order: number;
  // Per-placement visibility; absent in older data means visible.
  visible?: boolean;
}

// Undo/redo snapshot payload: full scene content without placement ids, so a
// restore never depends on expired ids. Labels are matched by content order,
// which keeps duplicate identical labels stable across repeated cycles.
export interface SceneSnapshotPlacement {
  text: string;
  textStyleId: string | null;
  fontId: string | null;
  fontSize: number | null;
  width: number | null;
  fontWeight: number | null;
  x: number;
  y: number;
  order: number;
  // Per-placement visibility; absent in older data means visible.
  visible?: boolean;
}

// Label creation and patch shapes: either a saved variant style or a direct
// font reference with its own size, wrap width and optional wght override
// (absent/null means the selected font's default), never both.
export type SceneLabelInput = {
  text: string;
  x: number;
  y: number;
} & (
  | { textStyleId: string; fontId?: never; fontSize?: never; width?: never; fontWeight?: never }
  | { fontId: string; fontSize: number; width: number; fontWeight?: number | null; textStyleId?: never }
);

export type SceneLabelPatch = {
  visible?: boolean;
  text?: string;
  x?: number;
  y?: number;
  order?: number;
  textStyleId?: string;
  fontId?: string;
  fontSize?: number;
  width?: number;
  fontWeight?: number | null;
};

export interface SceneSnapshotInput {
  name: string;
  width: number;
  height: number;
  deviceId: string | null;
  rotation?: 0 | 90 | 180 | 270;
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
  // Clockwise body orientation; older scenes default to zero.
  rotation?: 0 | 90 | 180 | 270;
  revision: number;
  outputProfileId: string;
  exportCoverage: CharacterCoverage;
  placements: DomainPlacementView[];
}
