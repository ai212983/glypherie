// Transport lifecycle: bounded handshake/call deadlines, generation
// isolation across reconnects, protocol-mismatch mapping, and no automatic
// mutation retries. The owner is faked at the SharedWorker/Worker boundary;
// the adoption path uses the real events module.
import assert from "node:assert/strict";
import test, { after, afterEach, before } from "node:test";
import {
  closeDomainChannelForTests,
  getDomainVersion,
  resetDomainVersionForTests,
} from "../../src/app/domain/events.ts";
import { DOMAIN_PROTOCOL_VERSION } from "../../src/app/domain/protocol.ts";
import {
  callDomain,
  getDomainOwnerDiagnostics,
  initBrowserDomain,
  resetDomainTransportForTests,
  setTransportTimeoutsForTests,
} from "../../src/app/domain/runtime.ts";

interface FakePort {
  sent: unknown[];
  onmessage: ((event: { data: unknown }) => void) | null;
  onmessageerror: ((event: unknown) => void) | null;
  postMessage: (message: unknown) => void;
  start: () => void;
  close: () => void;
}

function fakePort(): FakePort {
  const port: FakePort = {
    sent: [],
    onmessage: null,
    onmessageerror: null,
    postMessage: (message: unknown) => {
      port.sent.push(message);
    },
    start: () => undefined,
    close: () => undefined,
  };
  return port;
}

class FakeSharedWorker {
  static instances: FakeSharedWorker[] = [];
  port: FakePort = fakePort();
  onerror: ((event: unknown) => void) | null = null;
  url: unknown;
  options: unknown;
  constructor(url: unknown, options?: unknown) {
    this.url = url;
    this.options = options;
    FakeSharedWorker.instances.push(this);
  }
}

class FakeWorker {
  static instances: FakeWorker[] = [];
  sent: unknown[] = [];
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onmessageerror: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  terminated = false;
  constructor(_url: unknown, _options?: unknown) {
    FakeWorker.instances.push(this);
  }
  postMessage(message: unknown): void {
    this.sent.push(message);
  }
  terminate(): void {
    this.terminated = true;
  }
}

function installShared(): void {
  (globalThis as Record<string, unknown>).window = {};
  (globalThis as Record<string, unknown>).SharedWorker = FakeSharedWorker;
  delete (globalThis as Record<string, unknown>).Worker;
}

function installDedicated(): void {
  (globalThis as Record<string, unknown>).window = {};
  delete (globalThis as Record<string, unknown>).SharedWorker;
  (globalThis as Record<string, unknown>).Worker = FakeWorker;
}

function lastShared(): FakeSharedWorker {
  const instance = FakeSharedWorker.instances.at(-1);
  assert.ok(instance, "a shared owner exists");
  return instance;
}

/** Answer the owner's latest received message with a worker response. */
function respond(port: FakePort, message: unknown): void {
  port.onmessage?.({ data: message });
}

function answerHandshake(port: FakePort, id: number, epoch = "epoch-1"): void {
  respond(port, { id, ok: true, protocol: DOMAIN_PROTOCOL_VERSION, epoch, result: null });
}

before(() => {
  installShared();
});

afterEach(() => {
  resetDomainTransportForTests();
  closeDomainChannelForTests();
  resetDomainVersionForTests();
  FakeSharedWorker.instances = [];
  FakeWorker.instances = [];
  installShared();
});

after(() => {
  resetDomainTransportForTests();
  closeDomainChannelForTests();
  resetDomainVersionForTests();
  delete (globalThis as Record<string, unknown>).window;
  delete (globalThis as Record<string, unknown>).SharedWorker;
  delete (globalThis as Record<string, unknown>).Worker;
});

test("handshake plus call round-trips through the shared owner", async () => {
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000 });
  const ready = initBrowserDomain();
  const worker = lastShared();
  assert.equal(worker.port.sent.length, 1);
  const handshake = worker.port.sent[0] as { id: number; method: string; params: unknown[] };
  assert.equal(handshake.method, "__protocol");
  assert.deepEqual(handshake.params, [DOMAIN_PROTOCOL_VERSION]);
  answerHandshake(worker.port, handshake.id);
  await ready;
  const pending = callDomain("listOutputProfiles", []);
  const call = worker.port.sent.at(-1) as { id: number; method: string };
  assert.equal(call.method, "listOutputProfiles");
  respond(worker.port, { id: call.id, ok: true, mutated: false, result: ["mono"] });
  assert.deepEqual(await pending, ["mono"]);
});

test("a committed write adopts the owner stamp exactly once", async () => {
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000 });
  const ready = initBrowserDomain();
  const worker = lastShared();
  answerHandshake(worker.port, (worker.port.sent[0] as { id: number }).id, "epoch-9");
  await ready;
  const before = getDomainVersion();
  const pending = callDomain("createScene", [
    { name: "Card", width: 400, height: 300, outputProfileId: "output-monochrome" },
  ]);
  const call = worker.port.sent.at(-1) as { id: number };
  respond(worker.port, { id: call.id, ok: true, mutated: true, epoch: "epoch-9", seq: 3, result: { ok: true } });
  assert.deepEqual(await pending, { ok: true });
  assert.equal(getDomainVersion(), before + 1);
  // A duplicate delivery of the same stamp never notifies twice.
  respond(worker.port, { id: call.id, ok: true, mutated: true, epoch: "epoch-9", seq: 3, result: { ok: true } });
  assert.equal(getDomainVersion(), before + 1);
});

test("a hung call fails the transport with a retryable error and no retry", async () => {
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 30 });
  const ready = initBrowserDomain();
  const worker = lastShared();
  answerHandshake(worker.port, (worker.port.sent[0] as { id: number }).id);
  await ready;
  const before = worker.port.sent.length;
  await assert.rejects(callDomain("updateScene", ["id", {}, 1]), (error: unknown) => {
    assert.equal((error as { code?: unknown }).code, "unavailable");
    assert.match((error as Error).message, /did not answer/);
    return true;
  });
  // The mutation was sent exactly once: the transport reports, never resends.
  assert.equal(worker.port.sent.length, before + 1);
  // The failed transport reconnects from scratch on the next call.
  const next = initBrowserDomain();
  const retry = lastShared();
  assert.notEqual(retry, worker, "a fresh owner is established");
  answerHandshake(retry.port, (retry.port.sent[0] as { id: number }).id);
  await next;
});

test("a late response from a dead generation never settles the new transport", async () => {
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 30 });
  const ready = initBrowserDomain();
  const first = lastShared();
  answerHandshake(first.port, (first.port.sent[0] as { id: number }).id);
  await ready;
  const call = callDomain("getScene", ["missing"]);
  const sent = first.port.sent.at(-1) as { id: number };
  await assert.rejects(call, /did not answer/);
  // Reconnect, then deliver the dead generation's late answer.
  const reconnected = initBrowserDomain();
  const second = lastShared();
  answerHandshake(second.port, (second.port.sent[0] as { id: number }).id);
  await reconnected;
  const fresh = callDomain("getScene", ["missing"]);
  const freshSent = second.port.sent.at(-1) as { id: number };
  respond(first.port, { id: sent.id, ok: true, mutated: false, result: "stale" });
  respond(second.port, { id: freshSent.id, ok: true, mutated: false, result: "fresh" });
  assert.equal(await fresh, "fresh");
});

test("a timed-out handshake cannot tear down an immediate retry", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  setTransportTimeoutsForTests({ handshakeMs: 30, callMs: 1000 });
  const failed = initBrowserDomain();
  const first = lastShared();
  const rejected = assert.rejects(failed, /did not answer/);
  t.mock.timers.tick(30);
  const retry = initBrowserDomain();
  const second = lastShared();
  assert.notEqual(second, first);
  answerHandshake(second.port, (second.port.sent[0] as { id: number }).id);
  await rejected;
  const active = await retry;
  const pending = active.call("listOutputProfiles", []);
  respond(second.port, { id: (second.port.sent.at(-1) as { id: number }).id, ok: true, result: ["healthy"] });
  assert.deepEqual(await pending, ["healthy"]);
});

for (const dedicated of [false, true]) {
  test(`late ${dedicated ? "dedicated" : "shared"} owner errors cannot break a successor`, async () => {
    if (dedicated) installDedicated();
    setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000 });
    const initial = initBrowserDomain();
    const first = dedicated ? FakeWorker.instances.at(-1)! : lastShared();
    const firstPort = first instanceof FakeWorker ? first : first.port;
    const firstId = (firstPort.sent[0] as { id: number }).id;
    firstPort.onmessage?.({ data: { id: firstId, ok: true, result: null } });
    const stale = await initial;
    first.onerror?.(new Error("owner failed"));
    const retry = initBrowserDomain();
    const second = dedicated ? FakeWorker.instances.at(-1)! : lastShared();
    const secondPort = second instanceof FakeWorker ? second : second.port;
    secondPort.onmessage?.({ data: { id: (secondPort.sent[0] as { id: number }).id, ok: true, result: null } });
    const active = await retry;
    const pending = active.call("getScene", ["scene"]);
    const freshId = (secondPort.sent.at(-1) as { id: number }).id;
    const version = getDomainVersion();
    first.onerror?.(new Error("late startup error"));
    firstPort.onmessageerror?.(new Error("late channel error"));
    firstPort.onmessage?.({ data: { commit: { epoch: "obsolete", seq: 999 } } });
    assert.equal(getDomainVersion(), version);
    await assert.rejects(stale.call("deleteScene", ["scene", 1]), /connection has closed/);
    secondPort.onmessage?.({ data: { id: freshId, ok: true, result: "healthy" } });
    assert.equal(await pending, "healthy");
  });
}

test("a pre-protocol owner maps to a version-skew error without naming tabs", async (t) => {
  t.mock.method(console, "warn", () => {});
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000, recoveryPauseMs: 5 });
  const ready = initBrowserDomain();
  const legacy = { code: "unavailable", message: 'Unknown domain method "__protocol".' };
  // A legacy owner carries no generation discriminator, so recovery retries
  // the bounded fresh handshakes and then reports the skew honestly.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const worker = lastShared();
    assert.equal(FakeSharedWorker.instances.length, attempt + 1);
    const handshake = worker.port.sent[0] as { id: number };
    respond(worker.port, { id: handshake.id, ok: false, error: legacy });
    if (attempt < 2) await new Promise((resolve) => setTimeout(resolve, 50));
  }
  await assert.rejects(ready, (error: unknown) => {
    assert.equal((error as { code?: unknown }).code, "stale-owner");
    assert.match((error as Error).message, /different app versions/);
    assert.doesNotMatch((error as Error).message, /other Glypherie tabs/);
    return true;
  });
  assert.equal(FakeSharedWorker.instances.length, 3, "recovery retries are bounded");
});

test("a same-name different-URL owner maps to the same close-tabs error", async () => {
  (globalThis as Record<string, unknown>).SharedWorker = class {
    constructor() {
      // What the platform throws when the name is live under another URL.
      throw new DOMException("A SharedWorker with this name exists for another URL.", "InvalidAccessError");
    }
  };
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000 });
  await assert.rejects(initBrowserDomain(), (error: unknown) => {
    assert.equal((error as { code?: unknown }).code, "blocked");
    assert.match((error as Error).message, /Close other Glypherie tabs/);
    return true;
  });
});

test("a worker startup error shortens the next handshake probe", async () => {
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000, startupRetryMs: 20 });
  const first = initBrowserDomain();
  const broken = lastShared();
  // The worker script fails to evaluate: the async error rejects fast.
  broken.onerror?.(new Error("forced domain owner startup failure"));
  await assert.rejects(first, /failed/);
  // A reconstruction against the same poisoned scope probes briefly instead
  // of burning the full handshake budget.
  const started = Date.now();
  const second = initBrowserDomain();
  const retry = lastShared();
  assert.notEqual(retry, broken, "a fresh owner is established");
  await assert.rejects(second, /did not answer/);
  assert.ok(Date.now() - started < 500, "the poisoned scope probes briefly");
});

test("dedicated fallback connects when SharedWorker is unavailable", async () => {
  installDedicated();
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000 });
  const ready = initBrowserDomain();
  const worker = FakeWorker.instances.at(-1);
  assert.ok(worker, "a dedicated owner exists");
  const handshake = worker.sent[0] as { id: number; method: string };
  assert.equal(handshake.method, "__protocol");
  worker.onmessage?.({
    data: { id: handshake.id, ok: true, protocol: DOMAIN_PROTOCOL_VERSION, epoch: "epoch-d", result: null },
  });
  await ready;
  const pending = callDomain("listOutputProfiles", []);
  const call = worker.sent.at(-1) as { id: number };
  worker.onmessage?.({ data: { id: call.id, ok: true, mutated: false, result: [] } });
  assert.deepEqual(await pending, []);
});

test("the reorder command requires a protocol newer than the pre-reorder owner", () => {
  // reorderSceneLabels did not exist under protocol 2: the default must have
  // moved past it so a live v2 owner fails the handshake before any write.
  assert.ok(DOMAIN_PROTOCOL_VERSION > 2, `reorderSceneLabels requires protocol > 2, got ${DOMAIN_PROTOCOL_VERSION}`);
});

test("semantic palette edits require a protocol newer than the snapshot-curve owner", () => {
  // Whole-curve snapshots were owner writes under protocol 8: the default must
  // have moved past it so a live v8 owner fails the handshake before serving
  // a semantic edit it would persist as an empty write.
  assert.ok(DOMAIN_PROTOCOL_VERSION > 8, `semantic palette edits require protocol > 8, got ${DOMAIN_PROTOCOL_VERSION}`);
});

test("the strength hard cut requires a protocol newer than the pre-cutover owner", () => {
  // Stored `strength` blends were admitted under protocol 4: the default must
  // have moved past it so a live v4 owner fails the handshake before serving
  // retained parameters.
  assert.ok(DOMAIN_PROTOCOL_VERSION > 4, `strength cutover requires protocol > 4, got ${DOMAIN_PROTOCOL_VERSION}`);
});

test("a version-2 owner rejects a current handshake before editor writes", async (t) => {
  t.mock.method(console, "warn", () => {});
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000, recoveryPauseMs: 5 });
  const ready = initBrowserDomain();
  // What a live protocol-2 owner answers when the tab speaks a newer
  // version: an explicit mismatch naming its own generation, never a join.
  // Both recovery handshakes rejoin the same retained scope, so the second
  // rejection short-circuits on the repeated epoch instead of spinning.
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const worker = lastShared();
    const handshake = worker.port.sent[0] as { id: number; params: unknown[] };
    if (attempt === 0) assert.deepEqual(handshake.params, [DOMAIN_PROTOCOL_VERSION]);
    respond(worker.port, {
      id: handshake.id,
      ok: false,
      error: {
        code: "blocked",
        message: "This tab needs a fresh domain owner. Close other Glypherie tabs, then reload to retry.",
        protocol: 2,
        epoch: "epoch-retained",
      },
    });
    if (attempt < 1) await new Promise((resolve) => setTimeout(resolve, 50));
  }
  await assert.rejects(ready, (error: unknown) => {
    assert.equal((error as { code?: unknown }).code, "stale-owner");
    assert.match((error as Error).message, /different app versions/);
    assert.doesNotMatch((error as Error).message, /other Glypherie tabs/);
    return true;
  });
  assert.equal(FakeSharedWorker.instances.length, 2, "a retained scope stops recovery immediately");
  assert.deepEqual(getDomainOwnerDiagnostics(), {
    tabProtocol: DOMAIN_PROTOCOL_VERSION,
    ownerProtocol: 2,
    ownerEpoch: "epoch-retained",
  });
});

test("a fresh scope after unpoisoning recovers transparently", async (t) => {
  t.mock.method(console, "warn", () => {});
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000, recoveryPauseMs: 5 });
  const ready = initBrowserDomain();
  const stale = lastShared();
  const first = stale.port.sent[0] as { id: number };
  // First scope is stale; the retry boots a fresh current scope.
  respond(stale.port, {
    id: first.id,
    ok: false,
    error: {
      code: "blocked",
      message: "This tab needs a fresh domain owner. Close other Glypherie tabs, then reload to retry.",
      protocol: DOMAIN_PROTOCOL_VERSION - 1,
      epoch: "epoch-old",
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 50));
  const fresh = lastShared();
  assert.notEqual(fresh, stale, "recovery re-handshakes on a fresh scope");
  answerHandshake(fresh.port, (fresh.port.sent[0] as { id: number }).id);
  await ready;
  const pending = callDomain("listOutputProfiles", []);
  const call = fresh.port.sent.at(-1) as { id: number };
  respond(fresh.port, { id: call.id, ok: true, mutated: false, result: ["mono"] });
  assert.deepEqual(await pending, ["mono"]);
});

test("an owner missing reorderSceneLabels maps to a version-skew error", async () => {
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000 });
  const ready = initBrowserDomain();
  const worker = lastShared();
  answerHandshake(worker.port, (worker.port.sent[0] as { id: number }).id);
  await ready;
  const pending = callDomain("reorderSceneLabels", ["scene", ["b", "a"], 1]);
  const call = worker.port.sent.at(-1) as { id: number };
  // Exactly what an older owner answers for a method it never implemented.
  respond(worker.port, {
    id: call.id,
    ok: false,
    error: { code: "unavailable", message: 'Unknown domain method "reorderSceneLabels".' },
  });
  await assert.rejects(pending, (error: unknown) => {
    assert.equal((error as { code?: unknown }).code, "stale-owner");
    assert.match((error as Error).message, /different app versions/);
    assert.doesNotMatch((error as Error).message, /Unknown domain method/);
    assert.doesNotMatch((error as Error).message, /other Glypherie tabs/);
    return true;
  });
});

// Update-check seam: the recovery step only asks the service worker for an
// update — it never reads or writes precaches and never fetches, because a
// refetch cannot change the running SharedWorker. These probes drive it
// through the public handshake while recording any storage/network touch so
// tests can prove none happens.
function installUpdateSeam(behavior: { update: "ok" | "throw" | "hang" | "missing" }): {
  updateCalls: number;
  cacheCalls: string[];
  fetchCalls: number;
  releaseHang: () => void;
  restore: () => void;
} {
  const cacheCalls: string[] = [];
  let fetchCalls = 0;
  let updateCalls = 0;
  let releaseHang: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    releaseHang = () => resolve();
  });
  const priorCaches = (globalThis as Record<string, unknown>).caches;
  const priorFetch = (globalThis as Record<string, unknown>).fetch;
  // Node ships a getter-only global navigator: redefine it, then restore.
  const priorNavigatorDesc = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const noteCache = (name: string): never => {
    cacheCalls.push(name);
    throw new Error(`recovery must not touch precaches (saw ${name})`);
  };
  (globalThis as Record<string, unknown>).caches = {
    keys: async (): Promise<never> => noteCache("keys"),
    open: async (): Promise<never> => noteCache("open"),
  };
  (globalThis as Record<string, unknown>).fetch = async (): Promise<never> => {
    fetchCalls += 1;
    throw new Error("recovery must not fetch; only the update check runs");
  };
  Object.defineProperty(globalThis, "navigator", {
    value: {
      serviceWorker: {
        getRegistration: async () =>
          behavior.update === "missing"
            ? undefined
            : {
                update: async () => {
                  updateCalls += 1;
                  if (behavior.update === "hang") await gate;
                  if (behavior.update === "throw") throw new Error("update unavailable");
                },
              },
      },
    },
    configurable: true,
    writable: true,
  });
  const restore = (): void => {
    if (priorCaches === undefined) delete (globalThis as Record<string, unknown>).caches;
    else (globalThis as Record<string, unknown>).caches = priorCaches;
    (globalThis as Record<string, unknown>).fetch = priorFetch;
    if (priorNavigatorDesc) Object.defineProperty(globalThis, "navigator", priorNavigatorDesc);
    else delete (globalThis as Record<string, unknown>).navigator;
  };
  return {
    get updateCalls() {
      return updateCalls;
    },
    cacheCalls,
    get fetchCalls() {
      return fetchCalls;
    },
    releaseHang,
    restore,
  };
}

function staleBlocked(id: number, epoch: string, protocol = 2): void {
  respond(lastShared().port, {
    id,
    ok: false,
    error: {
      code: "blocked",
      message: "This tab needs a fresh domain owner. Close other Glypherie tabs, then reload to retry.",
      protocol,
      epoch,
    },
  });
}

test("recovery only checks for an update and never touches precaches", async (t) => {
  t.mock.method(console, "warn", () => {});
  const seam = installUpdateSeam({ update: "ok" });
  try {
    setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000, recoveryPauseMs: 5 });
    const ready = initBrowserDomain();
    staleBlocked((lastShared().port.sent[0] as { id: number }).id, "epoch-scope-a");
    await new Promise((resolve) => setTimeout(resolve, 80));
    answerHandshake(lastShared().port, (lastShared().port.sent[0] as { id: number }).id);
    await ready;
    assert.equal(seam.updateCalls, 1, "exactly one update check runs per recovery");
    assert.deepEqual(seam.cacheCalls, [], "recovery never reads or writes precaches");
    assert.equal(seam.fetchCalls, 0, "a refetch cannot change the running worker, so none runs");
  } finally {
    seam.restore();
  }
});

test("recovery still completes when the update check fails", async (t) => {
  t.mock.method(console, "warn", () => {});
  const seam = installUpdateSeam({ update: "throw" });
  try {
    setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000, recoveryPauseMs: 5 });
    const ready = initBrowserDomain();
    staleBlocked((lastShared().port.sent[0] as { id: number }).id, "epoch-scope-b");
    await new Promise((resolve) => setTimeout(resolve, 80));
    answerHandshake(lastShared().port, (lastShared().port.sent[0] as { id: number }).id);
    await ready;
    assert.equal(seam.updateCalls, 1, "the failed check was attempted, not skipped");
    assert.deepEqual(seam.cacheCalls, [], "a failed check cannot fall back to precache writes");
    assert.equal(seam.fetchCalls, 0);
  } finally {
    seam.restore();
  }
});

test("a hanging update check cannot stall the next handshake", async (t) => {
  t.mock.method(console, "warn", () => {});
  const seam = installUpdateSeam({ update: "hang" });
  try {
    setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000, recoveryPauseMs: 5, recoveryTimeoutMs: 20 });
    const ready = initBrowserDomain();
    staleBlocked((lastShared().port.sent[0] as { id: number }).id, "epoch-scope-c");
    await new Promise((resolve) => setTimeout(resolve, 150));
    assert.equal(FakeSharedWorker.instances.length, 2, "the check has its own bounded deadline");
    answerHandshake(lastShared().port, (lastShared().port.sent[0] as { id: number }).id);
    await ready;
    assert.equal(seam.updateCalls, 1, "the hanging check ran once and timed out");
    assert.deepEqual(seam.cacheCalls, [], "a timed-out check writes nothing late");
  } finally {
    seam.releaseHang();
    seam.restore();
  }
});

test("concurrent callers share one recovery, not one retry each", async (t) => {
  t.mock.method(console, "warn", () => {});
  const seam = installUpdateSeam({ update: "ok" });
  try {
    setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000, recoveryPauseMs: 5 });
    const first = initBrowserDomain();
    const second = initBrowserDomain();
    staleBlocked((lastShared().port.sent[0] as { id: number }).id, "epoch-scope-d");
    await new Promise((resolve) => setTimeout(resolve, 80));
    answerHandshake(lastShared().port, (lastShared().port.sent[0] as { id: number }).id);
    assert.strictEqual(await first, await second, "one transport serves both callers");
    assert.equal(FakeSharedWorker.instances.length, 2, "one stale scope plus one fresh scope");
    assert.equal(seam.updateCalls, 1, "one update check per recovery, not per caller");
    assert.deepEqual(seam.cacheCalls, []);
    assert.equal(seam.fetchCalls, 0);
  } finally {
    seam.restore();
  }
});

test("a hanging update check cannot stall recovery", async (t) => {
  t.mock.method(console, "warn", () => {});
  const seam = installUpdateSeam({ update: "hang" });
  try {
    setTransportTimeoutsForTests({ handshakeMs: 1000, recoveryPauseMs: 5, recoveryTimeoutMs: 20 });
    const ready = initBrowserDomain();
    staleBlocked((lastShared().port.sent[0] as { id: number }).id, "epoch-update");
    await new Promise((resolve) => setTimeout(resolve, 80));
    assert.equal(seam.updateCalls, 1);
    assert.equal(FakeSharedWorker.instances.length, 2, "the next handshake starts despite the pending update");
    answerHandshake(lastShared().port, (lastShared().port.sent[0] as { id: number }).id);
    await ready;
  } finally {
    seam.releaseHang();
    seam.restore();
  }
});

test("recovery without a service worker still retries the handshake", async (t) => {
  t.mock.method(console, "warn", () => {});
  const seam = installUpdateSeam({ update: "missing" });
  try {
    setTransportTimeoutsForTests({ handshakeMs: 1000, recoveryPauseMs: 5 });
    const ready = initBrowserDomain();
    staleBlocked((lastShared().port.sent[0] as { id: number }).id, "epoch-uncached");
    await new Promise((resolve) => setTimeout(resolve, 80));
    answerHandshake(lastShared().port, (lastShared().port.sent[0] as { id: number }).id);
    await ready;
    assert.equal(seam.updateCalls, 0, "no registration means no check, yet recovery proceeds");
    assert.deepEqual(seam.cacheCalls, []);
    assert.equal(seam.fetchCalls, 0);
  } finally {
    seam.restore();
  }
});
