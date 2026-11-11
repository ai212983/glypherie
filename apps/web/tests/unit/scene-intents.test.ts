// Scene intent controller contract: document edits resolve against the
// latest saved base when the queued operation executes. These tests drive the
// controller through the real domain backend (adapted without the worker
// dispatch, which plain node cannot resolve), so controller drift that the
// generic session tests cannot see still fails here.
import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import type { DomainBackend } from "../../src/app/domain/backend.ts";
import {
  addSceneLabel,
  createScene,
  getScene,
  removeSceneLabel,
  reorderSceneLabels,
  restoreSceneSnapshot,
  updateScene,
  updateSceneLabel,
} from "../../src/app/domain/scene-commands.ts";
import { listOutputProfiles } from "../../src/app/domain/service.ts";
import type { SceneLabelPatch } from "../../src/app/domain/types.ts";
import { isConflict } from "../../src/app/features/scenes/conflict.ts";
import { createVariant } from "../../src/app/variants/repository.ts";
import { saveFont, type FontMetadata } from "../../src/app/fonts/storage.ts";
import { DEFAULT_CHARACTER_COVERAGE } from "../../src/app/domain/coverage.ts";
import type { DomainSceneView, SceneLabelInput, SceneSnapshotInput } from "../../src/app/domain/types.ts";
import { SceneDocumentSession } from "../../src/app/features/screen/scene-session.ts";
import { sortLayersTopFirst } from "../../src/app/features/screen/scene-order.ts";
import {
  createSceneIntents,
  type NewLabelReference,
  type SceneIntents,
  type SceneOps,
  type SceneUpdatePatch,
} from "../../src/app/features/screen/scene-intents.ts";

let backend: DomainBackend;

beforeEach(async () => {
  backend = await resetDomainForTests();
});

after(async () => {
  await closeDomainForTests();
});

function metadata(): FontMetadata {
  return {
    names: { family: "Fixture" },
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
  };
}

const fontBytes = (seed = 0): ArrayBuffer =>
  Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;

async function styleId(seed = 0): Promise<string> {
  const font = await saveFont({
    bytes: fontBytes(seed),
    fileName: "fixture.ttf",
    name: "Fixture",
    metadata: metadata(),
    source: "uploaded",
  });
  const style = await createVariant(font.id, { name: `Body ${seed}` });
  return style.id;
}

// Real domain logic behind the controller's operations seam, without the
// worker dispatch that plain node cannot resolve; the queue, guards and
// ordering under test live in the controller and session either way.
function backendOps(): SceneOps {
  return {
    addSceneLabel: (sceneId: string, input: SceneLabelInput, revision: number) =>
      addSceneLabel(backend, sceneId, input, revision),
    updateSceneLabel: (sceneId: string, placementId: string, patch: SceneLabelPatch, revision: number) =>
      updateSceneLabel(backend, sceneId, placementId, patch, revision),
    updateScene: (sceneId: string, patch: SceneUpdatePatch, revision: number) =>
      updateScene(backend, sceneId, patch, revision),
    removeSceneLabel: (sceneId: string, placementId: string, revision: number) =>
      removeSceneLabel(backend, sceneId, placementId, revision),
    reorderSceneLabels: (sceneId: string, orderedIds: string[], revision: number) =>
      reorderSceneLabels(backend, sceneId, orderedIds, revision),
  };
}

async function setupScene(texts: string[]): Promise<{ intents: SceneIntents; session: SceneDocumentSession }> {
  assert.ok(backend);
  const profiles = await listOutputProfiles();
  const mono = profiles.find((profile) => profile.name === "Monochrome");
  assert.ok(mono);
  const style = await styleId();
  const created = await createScene(backend, { name: "Card", width: 400, height: 300, outputProfileId: mono.id });
  const session = new SceneDocumentSession({
    loadBundle: async (id: string) => {
      const scene = await getScene(backend, id);
      return { scene: scene ?? null, styles: [], profiles: [] };
    },
    restore: (id: string, revision: number, snapshot: SceneSnapshotInput) =>
      restoreSceneSnapshot(backend, id, revision, snapshot),
    isConflict,
  });
  await session.openScene(created.id);
  const intents = createSceneIntents(session, backendOps());
  const reference: NewLabelReference = { kind: "style", styleId: style };
  for (const [index, text] of texts.entries()) {
    const addedId = await intents.addLabel({ x: 8 + index * 40, y: 8 }, reference);
    assert.ok(addedId);
    assert.equal(await intents.commitText(addedId, text, { isNewLabel: true }), true);
  }
  return { intents, session };
}

function topTexts(session: SceneDocumentSession): (string | undefined)[] {
  const document = session.snapshot.document;
  assert.ok(document);
  return sortLayersTopFirst(document.placements).map((placement) => placement.text);
}

test("a layer move queued behind an add lands on the latest order", async () => {
  const { intents, session } = await setupScene(["A", "B", "C"]);
  assert.deepEqual(topTexts(session), ["C", "B", "A"]);
  const revision = session.snapshot.document?.revision;
  assert.ok(revision);
  const style = await styleId(1);
  const reference: NewLabelReference = { kind: "style", styleId: style };
  // Queue the add and the move without awaiting between them: the move must
  // resolve its top-first list against the base that includes the new label.
  const added = intents.addLabel({ x: 200, y: 8 }, reference);
  const moved = intents.moveLayer(0, 2);
  const [addedId, movedOk] = await Promise.all([added, moved]);
  assert.ok(addedId);
  assert.equal(movedOk, true);
  assert.equal(await intents.commitText(addedId, "D", { isNewLabel: true }), true);
  // The stale-list outcome would strand the new label; the latest base keeps
  // all four neighbors in their moved positions.
  assert.deepEqual(topTexts(session), ["C", "B", "D", "A"]);
  const document = session.snapshot.document;
  assert.ok(document);
  assert.equal(document.placements.length, 4);
  assert.equal(document.revision, revision! + 3);
});

test("exact and out-of-range moves skip revision churn", async () => {
  const { intents, session } = await setupScene(["A", "B"]);
  const revision = session.snapshot.document?.revision;
  assert.ok(revision);
  assert.equal(await intents.moveLayer(1, 1), true);
  assert.equal(session.snapshot.document?.revision, revision);
  assert.equal(await intents.moveLayer(0, 9), true);
  assert.equal(session.snapshot.document?.revision, revision);
  assert.deepEqual(topTexts(session), ["B", "A"]);
});

test("initial typing completes the creation undo step", async () => {
  const { intents, session } = await setupScene([]);
  const style = await styleId(2);
  const reference: NewLabelReference = { kind: "style", styleId: style };
  const addedId = await intents.addLabel({ x: 8, y: 8 }, reference);
  assert.ok(addedId);
  assert.equal(await intents.commitText(addedId, "Hello", { isNewLabel: true }), true);
  assert.equal(session.snapshot.document?.placements.length, 1);
  // One undo removes the created label entirely instead of restoring the
  // untyped placeholder as a separate step.
  assert.equal(await intents.undo(), true);
  assert.equal(session.snapshot.document?.placements.length, 0);
});

function fakeScene(id: string, revision: number): DomainSceneView {
  return {
    id,
    name: "Scene",
    width: 400,
    height: 300,
    deviceId: null,
    revision,
    outputProfileId: "mono",
    exportCoverage: DEFAULT_CHARACTER_COVERAGE,
    placements: [],
  };
}

test("a gated creation in the old scene never blocks the new scene", async () => {
  const documents = new Map<string, DomainSceneView>([
    ["old", fakeScene("old", 1)],
    ["next", fakeScene("next", 1)],
  ]);
  const releases = new Map<string, () => void>();
  const gated = new Set(["old"]);
  let counter = 0;
  const ops: SceneOps = {
    addSceneLabel: (sceneId: string, input: SceneLabelInput, revision: number) => {
      const base = documents.get(sceneId);
      assert.ok(base);
      const next: DomainSceneView = {
        ...base,
        revision: revision + 1,
        placements: [
          ...base.placements,
          {
            id: `added-${counter++}`,
            labelId: `label-${counter}`,
            textStyleId: input.textStyleId ?? null,
            fontId: input.fontId ?? null,
            fontSize: input.fontSize ?? null,
            width: input.width ?? null,
            fontWeight: null,
            text: input.text,
            x: input.x,
            y: input.y,
            order: base.placements.length,
          },
        ],
      };
      if (gated.has(sceneId)) {
        return new Promise<DomainSceneView>((resolve) => {
          releases.set(sceneId, () => {
            documents.set(sceneId, next);
            resolve(next);
          });
        });
      }
      documents.set(sceneId, next);
      return Promise.resolve(next);
    },
    updateSceneLabel: () => Promise.reject(new Error("unexpected")),
    updateScene: () => Promise.reject(new Error("unexpected")),
    removeSceneLabel: () => Promise.reject(new Error("unexpected")),
    reorderSceneLabels: () => Promise.reject(new Error("unexpected")),
  };
  const session = new SceneDocumentSession({
    loadBundle: async (id: string) => ({ scene: documents.get(id) ?? null, styles: [], profiles: [] }),
    restore: () => Promise.reject(new Error("unexpected")),
    isConflict,
  });
  await session.openScene("old");
  const reference: NewLabelReference = { kind: "style", styleId: "style-1" };
  const handoffs: string[] = [];
  const onCreated = (id: string): void => {
    handoffs.push(id);
    session.setDraftState({ hasOpenDraft: true, hasUnresolvedChanges: false });
  };
  // Gate a creation in the old scene, then switch away while it is pending.
  const oldFlight = createSceneIntents(session, ops).addLabel({ x: 8, y: 8 }, reference, { onCreated });
  // Let the queued executor reach the gated operation before switching, so
  // the old creation is genuinely inflight (not merely submitted).
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(session.snapshot.pending, true);
  assert.ok(releases.get("old"));
  await session.openScene("next");
  // The new scene is usable while the old write is still gated: creation
  // admission is generation-scoped, so no stale lease blocks it.
  assert.equal(session.snapshot.pending, false);
  const fresh = createSceneIntents(session, ops);
  const addedId = await fresh.addLabel({ x: 16, y: 16 }, reference, { onCreated });
  assert.ok(addedId);
  assert.deepEqual(handoffs, [addedId]);
  assert.equal(session.snapshot.draftOpen, true);
  session.setDraftState({ hasOpenDraft: false, hasUnresolvedChanges: false });
  assert.equal(session.snapshot.document?.id, "next");
  assert.equal(session.snapshot.document?.placements.length, 1);
  // Settle the old creation late: it reports blocked, publishes nothing,
  // and its finalizer never clears the newer scene's lease.
  releases.get("old")!();
  assert.equal(await oldFlight, null);
  assert.deepEqual(handoffs, [addedId]);
  assert.equal(session.snapshot.draftOpen, false);
  assert.equal(session.snapshot.document?.id, "next");
  assert.equal(session.snapshot.document?.placements.length, 1);
  assert.equal(session.snapshot.pending, false);
  // Creation remains admitted after both finalizers ran.
  const secondId = await fresh.addLabel({ x: 24, y: 24 }, reference);
  assert.ok(secondId);
  assert.equal(session.snapshot.document?.placements.length, 2);
});
