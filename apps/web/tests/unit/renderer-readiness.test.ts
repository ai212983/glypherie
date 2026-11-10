import assert from "node:assert/strict";
import test from "node:test";
import { RendererFontReadinessStore, type ReadinessService } from "../../src/app/fonts/renderer-readiness-core.ts";
import type { FontMetadata } from "../../src/app/fonts/storage.ts";

interface HeldLoad {
  id: string;
  release: () => void;
  reject: (error: Error) => void;
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((accept, deny) => {
    resolve = accept;
    reject = deny;
  });
  return { promise, resolve, reject };
}

const fontBytes = (seed: number): ArrayBuffer =>
  Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;

// Fake renderer with a real worker-side loaded set: unloading a live font
// actually evicts it, so tests prove the cache never lies about the worker.
function fakeService() {
  const workerLoaded = new Set<string>();
  const unloaded: string[] = [];
  const loaded: Array<{ id: string; bytes: ArrayBuffer }> = [];
  const service: ReadinessService = {
    inspect: async () => ({ names: { family: "Fixture" }, axes: [], font_hints: true }),
    load: async (id, bytes) => {
      workerLoaded.add(id);
      loaded.push({ id, bytes });
    },
    unload: async (id) => {
      unloaded.push(id);
      workerLoaded.delete(id);
    },
  };
  return { service, workerLoaded, unloaded, loaded };
}

function harness() {
  const loads: HeldLoad[] = [];
  const hintUpdates: Array<{ id: string; metadata: FontMetadata }> = [];
  const stored = new Map<string, { bytes: ArrayBuffer; hints: boolean | null | undefined }>();
  stored.set("alpha", { bytes: fontBytes(3), hints: undefined });
  const first = fakeService();
  const readFont = (id: string) => {
    const gate = deferred<{ bytes: ArrayBuffer; hints: boolean | null | undefined } | null>();
    const entry = stored.get(id) ?? null;
    loads.push({
      id,
      release: () => gate.resolve(entry === null ? null : { bytes: entry.bytes, hints: entry.hints }),
      reject: (error: Error) => gate.reject(error),
    });
    return gate.promise;
  };
  const store = new RendererFontReadinessStore({
    readFont,
    updateHints: async (id, metadata) => void hintUpdates.push({ id, metadata }),
    service: first.service,
  });
  return { store, loads, hintUpdates, stored, first };
}

const tick = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
};

test("unchanged reads share one snapshot identity; transitions replace it", async () => {
  const { store, loads } = harness();
  const before = store.getSnapshot();
  assert.equal(store.getSnapshot(), before);
  store.ensureLoaded("alpha", false);
  const loading = store.getSnapshot();
  assert.notEqual(loading, before);
  assert.equal(store.getSnapshot(), loading);
  assert.deepEqual(loading.statuses["alpha"], { state: "loading", error: "" });
  loads[0]!.release();
  await tick();
  const ready = store.getSnapshot();
  assert.notEqual(ready, loading);
  assert.equal(store.getSnapshot(), ready);
  assert.ok(ready.loadedIds.has("alpha"));
  store.invalidateFont("alpha");
  const invalidated = store.getSnapshot();
  assert.notEqual(invalidated, ready);
  assert.equal(invalidated.statuses["alpha"], undefined);
});

test("admission is subscription-visible during a held load and completion reaches the renderer", async () => {
  const { store, loads, stored, first } = harness();
  const seen: string[] = [];
  const stop = store.subscribe(() => seen.push(store.getSnapshot().statuses["alpha"]?.state ?? "idle"));
  assert.equal(store.loadStatus("alpha").state, "idle");
  store.ensureLoaded("alpha", false);
  // Loading is visible synchronously at admission, before the load completes.
  assert.equal(store.loadStatus("alpha").state, "loading");
  assert.deepEqual(seen[seen.length - 1], "loading");
  assert.equal(loads.length, 1);
  loads[0]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "ready");
  assert.deepEqual(seen[seen.length - 1], "ready");
  // The held load actually reached the renderer with an owned buffer copy.
  assert.equal(first.loaded.length, 1);
  const original = stored.get("alpha")!.bytes;
  assert.ok(first.loaded[0]!.bytes !== original);
  assert.deepEqual(Buffer.from(first.loaded[0]!.bytes), Buffer.from(original));
  assert.ok(first.workerLoaded.has("alpha"));
  stop();
});

test("session replacement during a held load suppresses the late completion", async () => {
  const { store, loads } = harness();
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 1);
  // A recreated worker starts with an empty cache: exposure drops
  // synchronously, before any passive reset effect could run.
  store.replaceSession();
  assert.deepEqual([...store.getSnapshot().loadedIds], []);
  assert.equal(store.loadStatus("alpha").state, "idle");
  loads[0]!.release();
  await tick();
  assert.ok(!store.getSnapshot().loadedIds.has("alpha"));
  assert.equal(store.loadStatus("alpha").state, "idle");
});

test("an old-session completion cannot overwrite a newer session load", async () => {
  const { store, loads, first } = harness();
  store.ensureLoaded("alpha", false);
  store.replaceSession();
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 2);
  loads[0]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "loading");
  assert.ok(!store.getSnapshot().loadedIds.has("alpha"));
  loads[1]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "ready");
  assert.equal(first.loaded.length, 1);
});

test("deletion unloads the originating worker and wins over a held load", async () => {
  const { store, loads, first } = harness();
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 1);
  const removing = store.removeFont("alpha", async () => undefined);
  assert.equal(store.loadStatus("alpha").state, "idle");
  await removing;
  assert.deepEqual(first.unloaded, ["alpha"]);
  assert.ok(!first.workerLoaded.has("alpha"));
  assert.ok(!store.getSnapshot().loadedIds.has("alpha"));
  // The pre-deletion load resolves late and stays suppressed.
  loads[0]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "idle");
  assert.equal(loads.length, 1);
});

test("a late old deletion never evicts the new session worker font", async () => {
  const { store, loads, first } = harness();
  const second = fakeService();
  // The old session holds an in-flight load that never completes in time.
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 1);
  // Deletion starts against the old worker with a held domain removal.
  const domainRemoval = deferred<void>();
  const removing = store.removeFont("alpha", () => domainRemoval.promise);
  // While the deletion still owns the id, no new load may re-admit it.
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 1);
  // The session switches; while the deletion still owns the id, the new
  // session must not re-admit a load for it either.
  store.updateService(second.service);
  store.replaceSession();
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 1);
  domainRemoval.resolve();
  await removing;
  // The late old deletion skipped the unload: the old worker is gone and the
  // new session owns its own cache.
  assert.deepEqual(second.unloaded, []);
  assert.deepEqual(first.unloaded, []);
  // Once released, the new session load proceeds and reaches its worker.
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 2);
  loads[1]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "ready");
  assert.ok(second.workerLoaded.has("alpha"));
  assert.ok(store.getSnapshot().loadedIds.has("alpha"));
  // The suppressed old-session load resolves last and changes nothing real.
  loads[0]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "ready");
  assert.ok(second.workerLoaded.has("alpha"));
  assert.ok(store.getSnapshot().loadedIds.has("alpha"));
});

test("a failed domain removal releases the id without resurrecting readiness", async () => {
  const { store, loads, first } = harness();
  store.ensureLoaded("alpha", false);
  loads[0]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "ready");
  await assert.rejects(
    store.removeFont("alpha", async () => {
      throw new Error("domain down");
    }),
    /domain down/,
  );
  assert.equal(store.loadStatus("alpha").state, "idle");
  assert.deepEqual(first.unloaded, ["alpha"]);
  // The next ensureLoaded honestly reloads through the normal path.
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 2);
  loads[1]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "ready");
  assert.ok(first.workerLoaded.has("alpha"));
});

test("unmount retires in-flight loads and a fresh mount retries through subscribers", async () => {
  const { store, loads } = harness();
  const first: number[] = [];
  const stopFirst = store.subscribe(() => first.push(first.length));
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 1);
  assert.ok(first.length >= 1);
  // StrictMode-style setup-cleanup-setup: the old setup retires without
  // mutating settled state, and the new setup subscribes fresh.
  stopFirst();
  store.dispose();
  const second: number[] = [];
  const stopSecond = store.subscribe(() => second.push(second.length));
  loads[0]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "idle");
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 2);
  loads[1]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "ready");
  assert.ok(second.length >= 2);
  stopSecond();
});

test("duplicate requests share one underlying load", async () => {
  const { store, loads } = harness();
  store.ensureLoaded(["alpha", "alpha"], false);
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 1);
  loads[0]!.release();
  await tick();
  assert.ok(store.getSnapshot().loadedIds.has("alpha"));
});

test("a failed load reports its error and retries only after invalidation", async () => {
  const { store, loads } = harness();
  store.ensureLoaded("alpha", false);
  loads[0]!.reject(new Error("boom"));
  await tick();
  assert.equal(store.loadStatus("alpha").state, "error");
  assert.match(store.loadStatus("alpha").error, /boom/);
  store.ensureLoaded("alpha", false);
  await tick();
  assert.equal(loads.length, 1);
  store.invalidateFont("alpha");
  store.ensureLoaded("alpha", false);
  assert.equal(loads.length, 2);
  loads[1]!.release();
  await tick();
  assert.equal(store.loadStatus("alpha").state, "ready");
});

test("an unavailable renderer performs no loads and reports idle", async () => {
  const { store, loads } = harness();
  store.ensureLoaded("alpha", true);
  await tick();
  assert.equal(loads.length, 0);
  assert.equal(store.loadStatus("alpha").state, "idle");
});

test("missing font data fails the load instead of poisoning the cache", async () => {
  const { store, loads, first } = harness();
  store.ensureLoaded("ghost", false);
  assert.equal(loads.length, 1);
  loads[0]!.release();
  await tick();
  assert.ok(!store.getSnapshot().loadedIds.has("ghost"));
  assert.equal(store.loadStatus("ghost").state, "error");
  assert.match(store.loadStatus("ghost").error, /missing from the library/);
  assert.equal(first.loaded.length, 0);
  assert.ok(!first.workerLoaded.has("ghost"));
});
