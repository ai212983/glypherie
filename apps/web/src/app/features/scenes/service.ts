// Binding to the graph-backed domain service (domain/service.ts, owned by
// the core worker). This module is the only scenes import of that path, so
// the pending-core gap stays localized here: every scenes consumer imports
// domain views and operations from here, never from domain/service.js
// directly.
export type {
  DomainTextStyleView,
  DomainOutputProfileView,
  DomainPlacementView,
  DomainSceneView,
} from "../../domain/service.js";
export {
  listTextStyles,
  listOutputProfiles,
  listScenes,
  getScene,
  createScene,
  updateScene,
  deleteScene,
  addSceneLabel,
  updateSceneLabel,
  removeSceneLabel,
  resolveTextStyle,
  resolveTextStyles,
  subscribeDomain,
  getDomainVersion,
} from "../../domain/service.js";
