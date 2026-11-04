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

export interface DomainSceneView {
  id: string;
  name: string;
  width: number;
  height: number;
  revision: number;
  outputProfileId: string;
  exportCoverage: CharacterCoverage;
  placements: DomainPlacementView[];
}
