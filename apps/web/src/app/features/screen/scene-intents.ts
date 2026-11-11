// Cohesive document-edit intents for one scene session.
//
// The controller binds domain operations to a SceneDocumentSession: it owns
// command construction, no-op guards, new-label checkpoint rules and
// current-revision plumbing, so the workspace submits meaningful edit intents
// instead of raw queue callbacks. Queue execution, latest-base resolution,
// history checkpoints and remote adoption stay encapsulated in the session;
// selection, focus and other transient editing transitions stay with the UI,
// which applies them from the outcomes reported here.
//
// The domain operations arrive as an explicit dependency (product code binds
// the scenes service; tests bind fakes or the in-memory backend), keeping
// the feature/scenes/service boundary intact: every product write still goes
// through the service, never around it. Explicit typography and label intent
// data arrives per call; the controller never reaches into FontLibrary,
// viewport preferences, renderer scheduling or JSX.
import type { CharacterCoverage } from "../../domain/coverage.js";
import type { DomainPlacementView, DomainSceneView, SceneLabelInput, SceneLabelPatch } from "../../domain/types.js";
import { DIRECT_LABEL_DEFAULT_SIZE_PX } from "./direct-label.ts";
import { sortLayersTopFirst } from "./scene-order.ts";
import type { SceneDocumentSession } from "./scene-session.ts";

export type SceneUpdatePatch = Partial<
  Pick<DomainSceneView, "name" | "width" | "height" | "deviceId" | "rotation" | "outputProfileId" | "exportCoverage">
>;

export interface SceneOps {
  addSceneLabel: (sceneId: string, input: SceneLabelInput, expectedRevision: number) => Promise<DomainSceneView>;
  updateSceneLabel: (
    sceneId: string,
    placementId: string,
    patch: SceneLabelPatch,
    expectedRevision: number,
  ) => Promise<DomainSceneView>;
  updateScene: (sceneId: string, patch: SceneUpdatePatch, expectedRevision: number) => Promise<DomainSceneView>;
  removeSceneLabel: (sceneId: string, placementId: string, expectedRevision: number) => Promise<DomainSceneView>;
  reorderSceneLabels: (
    sceneId: string,
    orderedPlacementIds: string[],
    expectedRevision: number,
  ) => Promise<DomainSceneView>;
}

export type NewLabelReference = { kind: "style"; styleId: string } | { kind: "direct"; fontId: string };

export interface SceneIntents {
  commitMove: (placementId: string, x: number, y: number) => Promise<boolean>;
  commitResize: (placementId: string, fontSize: number, width: number, x: number, y: number) => Promise<boolean>;
  commitText: (placementId: string, text: string, options?: { isNewLabel?: boolean }) => Promise<boolean>;
  patchLabel: (placementId: string, patch: SceneLabelPatch) => Promise<boolean>;
  nudgeLabel: (placementId: string, dx: number, dy: number) => void;
  addLabel: (
    position: { x: number; y: number },
    reference: NewLabelReference | null,
    options?: { onCreated?: (placementId: string) => void },
  ) => Promise<string | null>;
  deleteLabel: (placementId: string) => Promise<boolean>;
  reorderLayers: (apply: (topFirst: DomainPlacementView[]) => string[] | null) => Promise<boolean>;
  moveLayer: (from: number, to: number) => Promise<boolean>;
  changeDevice: (target: {
    deviceId: string | null;
    width?: number;
    height?: number;
    rotation?: 0 | 90 | 180 | 270;
  }) => void;
  saveCoverage: (coverage: CharacterCoverage) => void;
  rotateDevice: () => void;
  saveDimensions: (width: number, height: number) => void;
  changeOutputProfile: (outputProfileId: string) => void;
  undo: () => Promise<boolean>;
  redo: () => Promise<boolean>;
}

export function createSceneIntents(session: SceneDocumentSession, ops: SceneOps): SceneIntents {
  function commitMove(placementId: string, x: number, y: number): Promise<boolean> {
    return session.submit(
      async (scene) => {
        const placement = scene.placements.find((candidate) => candidate.id === placementId);
        if (!placement || (placement.x === x && placement.y === y)) return scene;
        return ops.updateSceneLabel(scene.id, placementId, { x, y }, scene.revision);
      },
      { background: true },
    );
  }

  function commitResize(placementId: string, fontSize: number, width: number, x: number, y: number): Promise<boolean> {
    return session.submit(
      async (scene) => {
        const placement = scene.placements.find((candidate) => candidate.id === placementId);
        if (!placement || placement.textStyleId !== null) return scene;
        if (placement.fontSize === fontSize && placement.width === width && placement.x === x && placement.y === y) {
          return scene;
        }
        return ops.updateSceneLabel(scene.id, placementId, { fontSize, width, x, y }, scene.revision);
      },
      { background: true },
    );
  }

  // Resolves true when the text persists or when there is nothing to persist
  // (missing or unchanged placement); false keeps the draft open for recovery.
  function commitText(placementId: string, text: string, options?: { isNewLabel?: boolean }): Promise<boolean> {
    return session.submit(
      async (scene) => {
        const placement = scene.placements.find((candidate) => candidate.id === placementId);
        if (!placement) return scene;
        if (placement.text === text) return scene;
        return ops.updateSceneLabel(scene.id, placementId, { text }, scene.revision);
      },
      options?.isNewLabel === true ? { checkpoint: false } : undefined,
    );
  }

  // Position, size, wrap width and weight patches persist in the background
  // like drag releases; text, reference and order changes stay blocking.
  function patchLabel(placementId: string, patch: SceneLabelPatch): Promise<boolean> {
    const background =
      patch.text === undefined &&
      patch.textStyleId === undefined &&
      patch.fontId === undefined &&
      patch.order === undefined &&
      (patch.x !== undefined ||
        patch.y !== undefined ||
        patch.fontSize !== undefined ||
        patch.width !== undefined ||
        patch.fontWeight !== undefined);
    return session.submit(
      (scene) => ops.updateSceneLabel(scene.id, placementId, patch, scene.revision),
      background ? { background: true } : undefined,
    );
  }

  // Relative moves compute from the latest saved base when the queued
  // operation executes, so rapid key repeats accumulate instead of replaying
  // one stale coordinate.
  function nudgeLabel(placementId: string, dx: number, dy: number): void {
    void session.submit(
      async (scene) => {
        const placement = scene.placements.find((candidate) => candidate.id === placementId);
        if (!placement) return scene;
        return ops.updateSceneLabel(
          scene.id,
          placementId,
          { x: placement.x + dx, y: placement.y + dy },
          scene.revision,
        );
      },
      { background: true },
    );
  }

  // Creates a label and reports the added placement id for selection and
  // editing handoff; null when creation is blocked (already creating, an open
  // draft, a waiting conflict, or no reference available). The creation lease
  // is generation-scoped in the session: a gated creation in the old scene
  // never blocks the new scene, and its late finalizer never clears a newer
  // claim. onCreated runs only after the session accepts the write for the
  // current generation, before remote adoption can replace the open draft.
  async function addLabel(
    position: { x: number; y: number },
    reference: NewLabelReference | null,
    options?: { onCreated?: (placementId: string) => void },
  ): Promise<string | null> {
    const claim = session.tryClaimCreation();
    if (claim === null) return null;
    try {
      const snapshot = session.snapshot;
      if (snapshot.draftOpen || snapshot.conflict || !reference) return null;
      let addedId: string | null = null;
      const ok = await session.submit(
        async (scene) => {
          const base = { text: "Text", x: position.x, y: position.y };
          const next =
            reference.kind === "style"
              ? await ops.addSceneLabel(scene.id, { ...base, textStyleId: reference.styleId }, scene.revision)
              : await ops.addSceneLabel(
                  scene.id,
                  {
                    ...base,
                    fontId: reference.fontId,
                    fontSize: DIRECT_LABEL_DEFAULT_SIZE_PX,
                    width: Math.max(1, scene.width - position.x),
                  },
                  scene.revision,
                );
          const added = next.placements.find(
            (candidate) => !scene.placements.some((before) => before.id === candidate.id),
          );
          if (added) {
            addedId = added.id;
          }
          return next;
        },
        {
          onAccepted: () => {
            if (addedId) options?.onCreated?.(addedId);
          },
        },
      );
      return ok ? addedId : null;
    } finally {
      session.releaseCreation(claim);
    }
  }

  function deleteLabel(placementId: string): Promise<boolean> {
    return session.submit(async (scene) => {
      if (!scene.placements.some((candidate) => candidate.id === placementId)) return scene;
      return ops.removeSceneLabel(scene.id, placementId, scene.revision);
    });
  }

  // Layer intents resolve against the latest saved base when the queued
  // operation executes: a reorder computed from a stale view still lands on
  // the right neighbors after concurrent adds or removes. Stale layer writes
  // never issue while a draft edits or a conflict waits; the caller rolls
  // its optimistic order back on rejection.
  function reorderLayers(apply: (topFirst: DomainPlacementView[]) => string[] | null): Promise<boolean> {
    return session.submit(async (scene) => {
      // Resolve the top-first order against the latest base inside the queue:
      // a move computed from a stale view never runs against captured ids.
      const topFirst = sortLayersTopFirst(scene.placements);
      const bottomToTop = apply(topFirst);
      if (!bottomToTop) return scene;
      // Skip revision churn when the bottom-to-top sequence is already exact
      // and dense.
      const currentBottom = [...topFirst].reverse();
      const dense = currentBottom.every((placement, index) => placement.order === index);
      if (dense && currentBottom.map((placement) => placement.id).join("\0") === bottomToTop.join("\0")) {
        return scene;
      }
      return ops.reorderSceneLabels(scene.id, bottomToTop, scene.revision);
    });
  }

  // Index moves within the displayed top-first order compute from the latest
  // saved base when the queued operation executes, so a reorder from a stale
  // view still lands on the right neighbors after concurrent adds or removes.
  function moveLayer(from: number, to: number): Promise<boolean> {
    if (from === to) return Promise.resolve(true);
    const snapshot = session.snapshot;
    if (snapshot.draftOpen || snapshot.conflict) return Promise.resolve(false);
    return reorderLayers((topFirst) => {
      if (from < 0 || from >= topFirst.length || to < 0 || to >= topFirst.length) return null;
      const next = [...topFirst];
      const moved = next.splice(from, 1)[0];
      if (!moved) return null;
      next.splice(to, 0, moved);
      return [...next].reverse().map((placement) => placement.id);
    });
  }

  function changeDevice(target: {
    deviceId: string | null;
    width?: number;
    height?: number;
    rotation?: 0 | 90 | 180 | 270;
  }): void {
    // An explicit custom choice that already holds stays untouched without
    // queueing a no-op write.
    if (target.deviceId === null && session.snapshot.document?.deviceId === null) return;
    void session.submit((scene) =>
      // Device changes preserve native label coordinates; labels outside the
      // new frame keep their positions and surface clipping instead of being
      // rescaled or moved. A custom choice keeps the scene's own dimensions.
      ops.updateScene(
        scene.id,
        {
          deviceId: target.deviceId,
          ...(target.rotation !== undefined ? { rotation: target.rotation } : {}),
          ...(target.width !== undefined ? { width: target.width } : {}),
          ...(target.height !== undefined ? { height: target.height } : {}),
        },
        scene.revision,
      ),
    );
  }

  function saveCoverage(coverage: CharacterCoverage): void {
    void session.submit((scene) => ops.updateScene(scene.id, { exportCoverage: coverage }, scene.revision));
  }

  function rotateDevice(): void {
    void session.submit((scene) =>
      ops.updateScene(
        scene.id,
        {
          width: scene.height,
          height: scene.width,
          rotation: (((scene.rotation ?? 0) + 90) % 360) as DomainSceneView["rotation"],
        },
        scene.revision,
      ),
    );
  }

  function saveDimensions(width: number, height: number): void {
    void session.submit((scene) => ops.updateScene(scene.id, { width, height }, scene.revision));
  }

  function changeOutputProfile(outputProfileId: string): void {
    void session.submit((scene) => ops.updateScene(scene.id, { outputProfileId }, scene.revision));
  }

  return {
    commitMove,
    commitResize,
    commitText,
    patchLabel,
    nudgeLabel,
    addLabel,
    deleteLabel,
    reorderLayers,
    moveLayer,
    changeDevice,
    saveCoverage,
    rotateDevice,
    saveDimensions,
    changeOutputProfile,
    undo: () => session.undo(),
    redo: () => session.redo(),
  };
}
