// Scene document session contract: the saved document/edit session owns
// queue ordering, remote adoption, successful-only history and undo/redo.
// These tests falsify public promises through the session's own interface,
// not its internal state.
import assert from "node:assert/strict";
import test from "node:test";
import { SceneDocumentSession, type SceneBundle } from "../../src/app/features/screen/scene-session.ts";
import { DEFAULT_CHARACTER_COVERAGE } from "../../src/app/domain/coverage.ts";
import type { DomainSceneView } from "../../src/app/domain/types.ts";

function scene(overrides: Partial<DomainSceneView> = {}): DomainSceneView {
  return {
    id: "scene-1",
    name: "Scene",
    width: 400,
    height: 300,
    deviceId: null,
    revision: 1,
    outputProfileId: "mono",
    exportCoverage: DEFAULT_CHARACTER_COVERAGE,
    placements: [],
    ...overrides,
  };
}

function placement(id: string, x: number, y: number) {
  return {
    id,
    labelId: `label-${id}`,
    textStyleId: "style-1",
    fontId: null,
    fontSize: null,
    width: null,
    fontWeight: null,
    text: "Text",
    x,
    y,
    order: 0,
  };
}

interface Harness {
  session: SceneDocumentSession;
  loads: string[];
  loadResolvers: Array<{
    resolve: (bundle: SceneBundle) => void;
    reject: (error: unknown) => void;
  }>;
  restored: Array<{ id: string; revision: number }>;
  failNextRestore: (error: unknown) => void;
}

async function harness(initial: DomainSceneView | null = scene()): Promise<Harness> {
  const loads: string[] = [];
  const loadResolvers: Harness["loadResolvers"] = [];
  const restored: Harness["restored"] = [];
  const failures: unknown[] = [];
  const session = new SceneDocumentSession({
    loadBundle: (id: string) => {
      loads.push(id);
      return new Promise<SceneBundle>((resolve, reject) => {
        loadResolvers.push({ resolve, reject });
      });
    },
    restore: async (id: string, revision: number, snapshot) => {
      restored.push({ id, revision });
      const failure = failures.shift();
      if (failure !== undefined) throw failure;
      // Applies the id-free snapshot content the way the domain restore
      // does, so assertions catch wrong content, order or dropped fields.
      return {
        id,
        name: snapshot.name,
        width: snapshot.width,
        height: snapshot.height,
        deviceId: snapshot.deviceId,
        rotation: snapshot.rotation,
        revision: revision + 1,
        outputProfileId: snapshot.outputProfileId,
        exportCoverage: snapshot.exportCoverage,
        placements: snapshot.placements.map((entry, index) => ({
          id: `restored-${revision + 1}-${index}`,
          labelId: `label-restored-${revision + 1}-${index}`,
          text: entry.text,
          textStyleId: entry.textStyleId,
          fontId: entry.fontId,
          fontSize: entry.fontSize,
          width: entry.width,
          fontWeight: entry.fontWeight,
          x: entry.x,
          y: entry.y,
          order: entry.order,
          visible: entry.visible,
        })),
      };
    },
    isConflict: (error: unknown) => error instanceof Error && /conflict/i.test(error.message),
  });
  const opened = session.openScene(initial?.id ?? "scene-1");
  assert.equal(loadResolvers.length, 1);
  loadResolvers[0]!.resolve({ scene: initial, styles: [], profiles: [] });
  await opened;
  return {
    session,
    loads,
    loadResolvers,
    restored,
    failNextRestore(error: unknown) {
      failures.push(error);
    },
  };
}

function bundleOf(next: DomainSceneView): SceneBundle {
  return { scene: next, styles: [], profiles: [] };
}

test("two commands pending serialize against the latest revision", async () => {
  const { session } = await harness(scene({ revision: 3 }));
  const seen: number[] = [];
  const first = session.submit(async (base) => {
    seen.push(base.revision);
    return { ...base, revision: base.revision + 1 };
  });
  const second = session.submit(async (base) => {
    seen.push(base.revision);
    return { ...base, revision: base.revision + 1 };
  });
  assert.equal(await first, true);
  assert.equal(await second, true);
  // The second intent executes against the first intent's result, never the
  // stale revision both were submitted under.
  assert.deepEqual(seen, [3, 4]);
  assert.equal(session.snapshot.document?.revision, 5);
});

test("relative nudges accumulate from the latest base", async () => {
  const start = scene({ revision: 7, placements: [placement("a", 10, 20)] });
  const { session } = await harness(start);
  const nudge = (dx: number) =>
    session.submit(
      async (base) => {
        const target = base.placements.find((entry) => entry.id === "a");
        assert.ok(target);
        return { ...base, revision: base.revision + 1, placements: [{ ...target, x: target.x + dx }] };
      },
      { background: true },
    );
  const both = await Promise.all([nudge(1), nudge(1)]);
  assert.deepEqual(both, [true, true]);
  assert.equal(session.snapshot.document?.placements[0]?.x, 12);
});

test("a no-op edit avoids an unwanted checkpoint", async () => {
  const { session } = await harness(scene({ revision: 2 }));
  const ok = await session.submit(async (base) => base);
  assert.equal(ok, true);
  assert.equal(session.snapshot.canUndo, false);
});

test("a failed command leaves history intact", async () => {
  const { session } = await harness(scene({ revision: 1 }));
  assert.equal(await session.submit(async (base) => ({ ...base, revision: base.revision + 1 })), true);
  assert.equal(session.snapshot.canUndo, true);
  const ok = await session.submit(async () => {
    throw new Error("boom");
  });
  assert.equal(ok, false);
  // The failed write checkpoints nothing and changes neither stack.
  assert.equal(session.snapshot.canUndo, true);
  assert.equal(session.snapshot.canRedo, false);
  assert.equal(session.snapshot.document?.revision, 2);
  assert.equal(session.snapshot.error, "boom");
});

test("a remote update with an open draft waits behind the banner", async () => {
  const { session, loadResolvers } = await harness(scene({ revision: 1 }));
  session.setDraftState({ hasOpenDraft: true, hasUnresolvedChanges: false });
  const reloaded = session.reload();
  assert.equal(loadResolvers.length, 2);
  loadResolvers[1]!.resolve(bundleOf(scene({ revision: 2 })));
  await reloaded;
  // The open in-place draft survives: no silent adoption, no auto replay.
  assert.equal(session.snapshot.document?.revision, 1);
  assert.equal(session.snapshot.conflict, true);
  assert.equal(session.snapshot.pendingRemote?.revision, 2);
});

test("a clean remote update adopts and drops stale history", async () => {
  const { session, loadResolvers } = await harness(scene({ revision: 1 }));
  assert.equal(await session.submit(async (base) => ({ ...base, revision: base.revision + 1 })), true);
  assert.equal(session.snapshot.canUndo, true);
  const reloaded = session.reload();
  loadResolvers[1]!.resolve(bundleOf(scene({ revision: 3 })));
  await reloaded;
  assert.equal(session.snapshot.document?.revision, 3);
  assert.equal(session.snapshot.conflict, false);
  // Adopting remote state drops local history: past snapshots predate it.
  assert.equal(session.snapshot.canUndo, false);
});

test("a stale scene result never publishes into the new scene", async () => {
  const slow: Harness["loadResolvers"] = [];
  const fast: Harness["loadResolvers"] = [];
  const loads: string[] = [];
  const session = new SceneDocumentSession({
    loadBundle: (id: string) => {
      loads.push(id);
      const sink = id === "slow" ? slow : fast;
      return new Promise<SceneBundle>((resolve, reject) => {
        sink.push({ resolve, reject });
      });
    },
    restore: async () => {
      throw new Error("unreachable");
    },
    isConflict: () => false,
  });
  const first = session.openScene("slow");
  const second = session.openScene("fast");
  fast[0]!.resolve(bundleOf(scene({ id: "fast", revision: 1 })));
  await second;
  assert.equal(session.snapshot.document?.id, "fast");
  // The superseded fetch resolves late: it must not publish or leak queued
  // status into the adopted scene.
  slow[0]!.resolve(bundleOf(scene({ id: "slow", revision: 9 })));
  await first;
  assert.equal(session.snapshot.document?.id, "fast");
  assert.equal(session.snapshot.document?.revision, 1);
  assert.deepEqual(loads, ["slow", "fast"]);
});

test("background placement writes leave controls enabled but block honest undo", async () => {
  const { session } = await harness(scene({ revision: 1 }));
  let release!: () => void;
  const gate = new Promise<DomainSceneView>((resolve) => {
    release = () => resolve(scene({ revision: 2 }));
  });
  const pending = session.submit(() => gate, { background: true });
  assert.equal(session.snapshot.pending, true);
  assert.equal(session.snapshot.blocking, false);
  assert.equal(session.snapshot.canUndo, false);
  release();
  assert.equal(await pending, true);
  assert.equal(session.snapshot.pending, false);
});

test("a failed restore leaves both history stacks intact", async () => {
  const { session, failNextRestore } = await harness(scene({ revision: 5 }));
  assert.equal(await session.submit(async (base) => ({ ...base, revision: base.revision + 1 })), true);
  assert.equal(session.snapshot.canUndo, true);
  failNextRestore(new Error("boom"));
  assert.equal(await session.undo(), false);
  // The rejection keeps the scene and both stacks untouched, so the undo
  // stays actionable for retry instead of consuming the candidate.
  assert.equal(session.snapshot.canUndo, true);
  assert.equal(session.snapshot.canRedo, false);
  assert.equal(session.snapshot.document?.revision, 6);
  assert.equal(await session.undo(), true);
  // The retry restores through a fresh revisioned command, not by replaying
  // the failed one.
  assert.equal(session.snapshot.document?.revision, 7);
  assert.equal(session.snapshot.canUndo, false);
  assert.equal(session.snapshot.canRedo, true);
});

test("dirty coverage refuses remote adoption until it is saved", async () => {
  const { session, loadResolvers } = await harness(scene({ revision: 4 }));
  // Unsaved coverage is unresolved local state even with no editor open.
  session.setDraftState({ hasOpenDraft: false, hasUnresolvedChanges: true });
  const held = session.reload();
  loadResolvers[1]!.resolve(bundleOf(scene({ revision: 5 })));
  await held;
  assert.equal(session.snapshot.document?.revision, 4);
  assert.equal(session.snapshot.conflict, true);
  assert.equal(session.snapshot.pendingRemote?.revision, 5);
  // Saving the coverage clears the dirty flag, so the next reload adopts.
  session.setDraftState({ hasOpenDraft: false, hasUnresolvedChanges: false });
  const adopted = session.reload();
  loadResolvers[2]!.resolve(bundleOf(scene({ revision: 5 })));
  await adopted;
  assert.equal(session.snapshot.document?.revision, 5);
  assert.equal(session.snapshot.conflict, false);
  assert.equal(session.snapshot.pendingRemote, null);
});

test("switching scenes drops queued work, history and conflict", async () => {
  const resolvers: Harness["loadResolvers"] = [];
  const seenByIntents: string[] = [];
  const session = new SceneDocumentSession({
    loadBundle: () =>
      new Promise<SceneBundle>((resolve, reject) => {
        resolvers.push({ resolve, reject });
      }),
    restore: async () => {
      throw new Error("unreachable");
    },
    isConflict: () => false,
  });
  // Establish the old document with successful history behind it.
  const firstOpen = session.openScene("old");
  resolvers[0]!.resolve(bundleOf(scene({ id: "old", revision: 1 })));
  await firstOpen;
  assert.equal(await session.submit(async (base) => ({ ...base, revision: base.revision + 1 })), true);
  assert.equal(session.snapshot.canUndo, true);
  // Start a gated command against the old scene, then switch away.
  let releaseOld!: (next: DomainSceneView) => void;
  const oldGate = new Promise<DomainSceneView>((resolve) => {
    releaseOld = resolve;
  });
  const oldFlight = session.submit((base) => {
    seenByIntents.push(base.id);
    return oldGate;
  });
  assert.equal(session.snapshot.pending, true);
  const secondOpen = session.openScene("next");
  resolvers[1]!.resolve(bundleOf(scene({ id: "next", revision: 1 })));
  await secondOpen;
  assert.equal(session.snapshot.document?.id, "next");
  // The new scene is usable while the old write is still gated: no pending
  // or blocking status leaks across, and new work checkpoints fresh history.
  assert.equal(session.snapshot.pending, false);
  assert.equal(session.snapshot.blocking, false);
  assert.equal(session.snapshot.canUndo, false);
  assert.equal(await session.submit(async (base) => ({ ...base, revision: base.revision + 1 })), true);
  assert.equal(session.snapshot.document?.revision, 2);
  assert.equal(session.snapshot.canUndo, true);
  // Settle the old command after the switch: it must not run against, publish
  // into, or checkpoint the new scene, and the late finalizer must not move
  // the new counters or emit stale status.
  releaseOld(scene({ id: "old", revision: 3 }));
  assert.equal(await oldFlight, false);
  assert.deepEqual(seenByIntents, []);
  assert.equal(session.snapshot.document?.id, "next");
  assert.equal(session.snapshot.document?.revision, 2);
  assert.equal(session.snapshot.pending, false);
  assert.equal(session.snapshot.blocking, false);
  assert.equal(session.snapshot.canUndo, true);
  assert.equal(session.snapshot.canRedo, false);
  assert.equal(session.snapshot.conflict, false);
  assert.equal(session.snapshot.pendingRemote, null);
});

test("multi-step undo and redo restore content in order", async () => {
  const start = scene({
    revision: 1,
    rotation: 90,
    placements: [{ ...placement("a", 10, 20), text: "v1", visible: false, fontWeight: 700 }],
  });
  const { session } = await harness(start);
  const rename = (text: string) =>
    session.submit(async (base) => ({
      ...base,
      revision: base.revision + 1,
      placements: base.placements.map((entry) => ({ ...entry, text })),
    }));
  assert.equal(await rename("v2"), true);
  assert.equal(await rename("v3"), true);
  assert.equal(session.snapshot.document?.revision, 3);
  assert.equal(await session.undo(), true);
  assert.equal(session.snapshot.document?.placements[0]?.text, "v2");
  assert.equal(session.snapshot.canUndo, true);
  assert.equal(session.snapshot.canRedo, true);
  assert.equal(await session.undo(), true);
  assert.equal(session.snapshot.document?.placements[0]?.text, "v1");
  assert.equal(session.snapshot.canUndo, false);
  assert.equal(session.snapshot.canRedo, true);
  assert.equal(await session.redo(), true);
  assert.equal(session.snapshot.document?.placements[0]?.text, "v2");
  assert.equal(await session.redo(), true);
  assert.equal(session.snapshot.document?.placements[0]?.text, "v3");
  assert.equal(session.snapshot.canUndo, true);
  assert.equal(session.snapshot.canRedo, false);
  // The id-free restore retains rotation, visibility, weight and coverage,
  // and never transfers the expired placement selection identity.
  const restored = session.snapshot.document;
  assert.equal(restored?.rotation, 90);
  assert.equal(restored?.placements[0]?.visible, false);
  assert.equal(restored?.placements[0]?.fontWeight, 700);
  assert.ok(restored?.placements[0]?.id.startsWith("restored-"));
  assert.equal(session.snapshot.document?.exportCoverage, DEFAULT_CHARACTER_COVERAGE);
});
