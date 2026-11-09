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
  SceneLabelInput,
  SceneLabelPatch,
  SceneSnapshotInput,
} from "../../domain/service.js";
export {
  listTextStyles,
  listOutputProfiles,
  listScenes,
  getScene,
  createScene,
  ensureDefaultScene,
  updateScene,
  deleteScene,
  addSceneLabel,
  updateSceneLabel,
  removeSceneLabel,
  reorderSceneLabels,
  restoreSceneSnapshot,
  resolveTextStyle,
  resolveTextStyles,
  subscribeDomain,
  getDomainVersion,
  STALE_OWNER_RECOVERY_MESSAGE,
} from "../../domain/service.js";
