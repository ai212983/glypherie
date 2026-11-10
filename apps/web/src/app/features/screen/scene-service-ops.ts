// Product binding from the scene-intent controller to the scenes service.
//
// This small adapter is the only place that couples the cohesive document
// edits to the worker-dispatched service; the controller itself accepts its
// operations as a dependency, so tests bind fakes or the in-memory backend
// without touching this module.
import {
  addSceneLabel,
  removeSceneLabel,
  reorderSceneLabels,
  updateScene,
  updateSceneLabel,
} from "../scenes/service.ts";
import type { SceneOps } from "./scene-intents.ts";

export const sceneServiceOps: SceneOps = {
  addSceneLabel,
  updateSceneLabel,
  updateScene,
  removeSceneLabel,
  reorderSceneLabels,
};
