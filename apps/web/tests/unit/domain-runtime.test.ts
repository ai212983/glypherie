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
import {
  callDomain,
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
    postMessage: (message: unknown) => { port.sent.push(message); },
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
  respond(port, { id, ok: true, protocol: 2, epoch, result: null });
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
  assert.deepEqual(handshake.params, [2]);
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
  const pending = callDomain("createScene", [{ name: "Card" }]);
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

test("a pre-protocol owner maps to an explicit close-tabs error", async () => {
  setTransportTimeoutsForTests({ handshakeMs: 1000, callMs: 1000 });
  const ready = initBrowserDomain();
  const worker = lastShared();
  const handshake = worker.port.sent[0] as { id: number };
  // Exactly what the old worker answered for an unknown method.
  respond(worker.port, {
    id: handshake.id,
    ok: false,
    error: { code: "unavailable", message: 'Unknown domain method "__protocol".' },
  });
  await assert.rejects(ready, (error: unknown) => {
    assert.equal((error as { code?: unknown }).code, "blocked");
    assert.match((error as Error).message, /Close other Glypherie tabs/);
    return true;
  });
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
  worker.onmessage?.({ data: { id: handshake.id, ok: true, protocol: 2, epoch: "epoch-d", result: null } });
  await ready;
  const pending = callDomain("listOutputProfiles", []);
  const call = worker.sent.at(-1) as { id: number };
  worker.onmessage?.({ data: { id: call.id, ok: true, mutated: false, result: [] } });
  assert.deepEqual(await pending, []);
});
