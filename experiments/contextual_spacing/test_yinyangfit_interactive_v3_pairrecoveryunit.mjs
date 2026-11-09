// Pair-recovery unit gate (node only, no browser): single recovery
// authority, atomic reserve without clobber, and the terminal-store
// ownership gate. Drives the REAL production helpers from the wiring
// (FLIGHT block, now including the transport registry and the single
// acknowledgement-expiry handler) with stub page state; fake timers
// prove the production timer arms the verbatim handler at the 60 s
// bound without ever waiting.
//
// Usage: node test_yinyangfit_interactive_v3_pairrecoveryunit.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(resolve(root, "yinyangfit_interactive_v3_wiring.js"), "utf8");

function slice(name) {
  const begin = `/* __${name}_BEGIN__ */`;
  const end = `/* __${name}_END__ */`;
  const a = src.indexOf(begin),
    b = src.indexOf(end);
  assert.ok(a >= 0 && b > a, name + " block markers present");
  return src.slice(a, b + end.length);
}

const ctx = {};
vm.createContext(ctx);
// Fake timers: capture instead of waiting; the production bound is
// asserted, and firing the captured callback runs the verbatim
// production handler.
const armed = [],
  cleared = [];
ctx.setTimeout = (fn, ms) => {
  armed.push({ fn, ms });
  return armed.length;
};
ctx.clearTimeout = (id) => {
  cleared.push(id);
};
ctx.FLIGHT_ACK_MS = 60000;
ctx.flightCalls = {};
ctx.poolLogical = null;
ctx.renderSeq = 7;
ctx.settledWith = [];
ctx.settleCheck = (gen) => {
  ctx.settledWith.push(gen);
};
ctx.genNeeds = {};
ctx.noted = [];
ctx.noteScoreFailures = (ids) => {
  ctx.noted.push(...ids);
};
vm.runInContext(slice("PAIRCACHE_HELPERS"), ctx, { filename: "paircache" });
vm.runInContext(slice("FLIGHT_HELPERS"), ctx, { filename: "flight" });
ctx.flight = ctx.createFlight();

const F = ctx;
const SETTING = "rec-setting";
function key(name, metric = "0") {
  return F.pairIdentityKey(SETTING, name, metric);
}
const KA = key("a"),
  KB = key("b"),
  KC = key("c");

// Realm-safe structural compare: block values are built inside a vm
// context whose Array/Object prototypes differ from this realm's, so
// strict deepEqual would reject identical shapes.
function eq(actual, expected, msg) {
  assert.equal(JSON.stringify(actual), JSON.stringify(expected), msg);
}

let checks = 0;
const queue = [];
function check(name, fn) {
  queue.push([name, fn]);
}
function freshFlight() {
  const f = F.createFlight();
  F.flight = f;
  F.flightCalls = {};
  F.poolLogical = null;
  F.renderSeq = 7;
  F.settledWith = [];
  F.genNeeds = {};
  F.noted = [];
  armed.length = 0;
  cleared.length = 0;
  return f;
}

// ---- atomic reserve: no clobber -------------------------------------

check("reserve never overwrites a live owner", () => {
  const flight = freshFlight();
  const r1 = F.flightReserve(flight, [KA, KB], [1]);
  assert.ok(r1.callId, "first reserve owns");
  F.flightNewCall(r1.callId, r1.reserved);
  const starts = flight.stats.starts;
  // A racing recovery for [A, B, C] must join A/B, reserve only C.
  const r2 = F.flightReserve(flight, [KA, KB, KC], [2]);
  assert.ok(r2.callId, "partial reserve still returns a call");
  eq([...r2.reserved], [KC]);
  eq([...r2.joined].sort(), [KA, KB].sort());
  eq(r2.blocked, []);
  assert.equal(flight.running.get(KA).owner, r1.callId, "live owner unclobbered");
  assert.equal(flight.running.get(KB).owner, r1.callId);
  assert.ok(flight.running.get(KA).subs[2], "joining view subscribed");
  assert.equal(flight.stats.starts, starts + 1, "one start for C only");
});

check("fully owned reserve returns no call and no start", () => {
  const flight = freshFlight();
  const r1 = F.flightReserve(flight, [KA, KB], [1]);
  F.flightNewCall(r1.callId, r1.reserved);
  const starts = flight.stats.starts;
  const callsBefore = flight.calls.size;
  const r2 = F.flightReserve(flight, [KA, KB], [1]);
  assert.equal(r2.callId, null, "nothing reservable, no ghost call");
  eq(r2.reserved, []);
  eq([...r2.joined].sort(), [KA, KB].sort());
  assert.equal(flight.stats.starts, starts, "no start counter consumed");
  assert.equal(flight.calls.size, callsBefore, "no ghost call record");
});

check("stopping owner classifies blocked, never steals", () => {
  const flight = freshFlight();
  const r1 = F.flightReserve(flight, [KA], [1]);
  F.flightNewCall(r1.callId, r1.reserved);
  F.flightDetach(flight, 1);
  assert.ok(flight.running.get(KA).stopping, "armed stop");
  const r2 = F.flightReserve(flight, [KA, KB], [2]);
  eq(r2.blocked, [KA], "stopping key blocks");
  eq(r2.reserved, [KB], "absent key still reserves");
  assert.equal(flight.running.get(KA).owner, r1.callId, "stopping owner intact");
});

// ---- terminal-store ownership gate ----------------------------------

check("terminal gate: owner and ownerless store, third owner drops", () => {
  const flight = freshFlight();
  const r1 = F.flightReserve(flight, [KA], [1]);
  const r2 = F.flightReserve(flight, [KB], [2]);
  assert.equal(F.terminalOwnerAllows(flight, SETTING, r1.callId, "a", "0"), true, "current owner stores");
  assert.equal(
    F.terminalOwnerAllows(flight, SETTING, r2.callId, "a", "0"),
    false,
    "orphan terminal with live newer owner drops",
  );
  assert.equal(F.terminalOwnerAllows(flight, SETTING, r2.callId, "b", "0"), true, "self stores");
  F.flightAck(flight, r1.callId);
  assert.equal(F.terminalOwnerAllows(flight, SETTING, r1.callId, "a", "0"), true, "ownerless late data still caches");
  assert.equal(F.terminalOwnerAllows(flight, SETTING, "k9", "a", "1"), true, "metric is a separate key, no cross-talk");
  assert.equal(
    F.terminalOwnerAllows(flight, "other-setting", "k9", "a", "0"),
    true,
    "setting is a separate key, no cross-talk",
  );
});

// ---- single acknowledgement-expiry handler --------------------------

check("expiry posts cancel first, then releases, then re-resolves", () => {
  const flight = freshFlight();
  const r = F.flightReserve(flight, [KA, KB], [7]);
  F.flightNewCall(r.callId, r.reserved);
  const posted = [];
  let liveAtCancel = null;
  F.flightCalls[r.callId].transports.push({
    worker: {
      postMessage: (m) => {
        posted.push(m);
        liveAtCancel = flight.running.has(KA);
      },
    },
    jobId: "job-1",
  });
  assert.equal(armed.length, 1, "dispatch arms one ack timer");
  assert.equal(armed[0].ms, 60000, "production 60 s bound preserved");
  F.flightAckExpired(r.callId);
  eq(posted, [{ kind: "cancel", jobId: "job-1" }]);
  assert.equal(liveAtCancel, true, "cancel posted before release");
  assert.equal(flight.running.has(KA), false, "ownership released");
  assert.equal(flight.running.has(KB), false);
  assert.ok(F.flightCalls[r.callId] === undefined, "call record gone");
  assert.ok(cleared.length >= 1, "timer cleared");
  eq([...F.settledWith], [7], "current view re-resolves");
});

check("expiry skips a call owned by a live unsettled pool logical", () => {
  const flight = freshFlight();
  const r = F.flightReserve(flight, [KA], [7]);
  F.flightNewCall(r.callId, r.reserved);
  let cancels = 0;
  F.flightCalls[r.callId].transports.push({
    worker: {
      postMessage: () => {
        cancels++;
      },
    },
    jobId: "job-1",
  });
  F.poolLogical = { settled: false, flightCall: r.callId, seq: 7 };
  F.flightAckExpired(r.callId);
  assert.equal(cancels, 0, "no cancel while pool owns recovery");
  assert.ok(flight.running.has(KA), "pool ownership intact");
  assert.ok(F.flightCalls[r.callId] !== undefined, "call record intact");
  eq([...F.settledWith], [], "no re-resolve");
  // Settled pool: expiry cleans up without hanging.
  F.poolLogical.settled = true;
  F.flightAckExpired(r.callId);
  assert.equal(cancels, 1, "cancel after pool settled");
  assert.equal(flight.running.has(KA), false);
});

check("expiry proceeds for superseded or foreign pool calls", () => {
  const flight = freshFlight();
  const r = F.flightReserve(flight, [KA], [7]);
  F.flightNewCall(r.callId, r.reserved);
  // Pool logical owns a DIFFERENT call: this one has no live pool
  // authority, so the ack bound still cleans it up.
  F.poolLogical = { settled: false, flightCall: "k-other", seq: 7 };
  F.flightAckExpired(r.callId);
  assert.equal(flight.running.has(KA), false, "foreign call released");
  // Same call but a superseded generation: cleanup, no hang.
  const r2 = F.flightReserve(flight, [KB], [8]);
  F.flightNewCall(r2.callId, r2.reserved);
  F.poolLogical = { settled: false, flightCall: r2.callId, seq: 7 };
  F.renderSeq = 8;
  F.flightAckExpired(r2.callId);
  assert.equal(flight.running.has(KB), false, "superseded call released");
});

check("double expiry is a safe no-op", () => {
  freshFlight();
  const r = F.flightReserve(F.flight, [KA], [7]);
  F.flightNewCall(r.callId, r.reserved);
  F.flightAckExpired(r.callId);
  const settled = F.settledWith.length;
  F.flightAckExpired(r.callId);
  assert.equal(F.settledWith.length, settled, "no second re-resolve");
});

check("expiry counts only keys the current view still needs", () => {
  const flight = freshFlight();
  const r = F.flightReserve(flight, [KA, KB], [7]);
  F.flightNewCall(r.callId, r.reserved);
  F.genNeeds[7] = { keys: [{ key: KA }] };
  F.flightAckExpired(r.callId);
  eq([...F.noted], [KA], "only subscribed keys burn an attempt");
  // No current view at all: a detached expiry accrues nothing.
  F.noted.length = 0;
  const r2 = F.flightReserve(flight, [KA], [8]);
  F.flightNewCall(r2.callId, r2.reserved);
  F.renderSeq = 9;
  F.flightAckExpired(r2.callId);
  eq([...F.noted], [], "detached keys never accrue");
});

check("production timer fires the verbatim handler", () => {
  const flight = freshFlight();
  const r = F.flightReserve(flight, [KA], [7]);
  F.flightNewCall(r.callId, r.reserved);
  assert.equal(armed.length, 1);
  armed[0].fn();
  assert.equal(flight.running.has(KA), false, "timer ran expiry");
  eq([...F.settledWith], [7]);
});

check("released keys re-reserve under exactly one new owner", () => {
  const flight = freshFlight();
  const r = F.flightReserve(flight, [KA], [7]);
  F.flightNewCall(r.callId, r.reserved);
  F.flightAckExpired(r.callId);
  const starts = flight.stats.starts;
  const r2 = F.flightReserve(flight, [KA], [7]);
  assert.ok(r2.callId && r2.callId !== r.callId, "one new owner");
  eq(r2.reserved, [KA]);
  assert.equal(flight.running.get(KA).owner, r2.callId);
  assert.equal(flight.stats.starts, starts + 1, "single start");
});

// ---- flightFail stays a synchronous clobber-safe handoff ------------

check("flightFail hands off ownership and closes after one retry", () => {
  const flight = freshFlight();
  const r = F.flightReserve(flight, [KA, KB], [3]);
  const nid = F.flightFail(flight, r.callId);
  assert.ok(nid && nid !== r.callId, "bounded retry id");
  assert.equal(flight.running.get(KA).owner, nid, "ownership handed off");
  assert.equal(flight.running.get(KB).owner, nid);
  assert.ok(!flight.calls.has(r.callId), "old call gone");
  // Known limit (production-unreachable: the live path recovers via
  // recoverPoolJob; only the frozen-oracle node wrapper maps fail to
  // flightFail): the re-reserve copies subscriber indices, not views,
  // so a retried entry keeps a phantom sub instead of the real view.
  // Documented here, not changed: out of P3 scope.
  assert.ok(!flight.running.get(KA).subs[3], "phantom-index quirk noted");
  assert.equal(F.flightFail(flight, nid), null, "already retried: closed");
  assert.ok(!flight.running.has(KA), "fail-closed release, no hang");
});

for (const [name, fn] of queue) {
  try {
    fn();
    checks++;
    console.log("ok: " + name);
  } catch (e) {
    console.error("FAIL: " + name);
    console.error(e);
    process.exit(1);
  }
}
console.log(`pairrecovery unit: ${checks} checks passed`);
