// Owner-stamp notification semantics: a new owner epoch is always adopted
// (its sequence restarts, so cross-epoch numbers are incomparable), within
// one epoch only a higher sequence advances, and legacy bare numbers never
// suppress anything. A failing subscriber never breaks the write path.
import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import {
  adoptOwnerWrite,
  broadcastOwnerWrite,
  closeDomainChannelForTests,
  getDomainVersion,
  notifyDomainWrite,
  resetDomainVersionForTests,
  subscribeDomain,
} from "../../src/app/domain/events.ts";

afterEach(() => {
  closeDomainChannelForTests();
  resetDomainVersionForTests();
});

test("stamps from one owner epoch advance every tab exactly once", () => {
  let calls = 0;
  subscribeDomain(() => { calls += 1; });
  adoptOwnerWrite({ epoch: "a", seq: 1 });
  assert.equal(getDomainVersion(), 1);
  assert.equal(calls, 1);
  adoptOwnerWrite({ epoch: "a", seq: 2 });
  assert.equal(getDomainVersion(), 2);
  assert.equal(calls, 2);
});

test("stale duplicates and out-of-order events within one epoch are ignored", () => {
  let calls = 0;
  subscribeDomain(() => { calls += 1; });
  adoptOwnerWrite({ epoch: "a", seq: 5 });
  assert.equal(calls, 1);
  adoptOwnerWrite({ epoch: "a", seq: 5 });
  adoptOwnerWrite({ epoch: "a", seq: 3 });
  assert.equal(getDomainVersion(), 1);
  assert.equal(calls, 1);
  adoptOwnerWrite({ epoch: "a", seq: 6 });
  assert.equal(getDomainVersion(), 2);
  assert.equal(calls, 2);
});

test("a restarted owner epoch is adopted even though its sequence restarts", () => {
  let calls = 0;
  subscribeDomain(() => { calls += 1; });
  adoptOwnerWrite({ epoch: "a", seq: 7 });
  assert.equal(getDomainVersion(), 1);
  // The new owner's seq 1 is incomparable with epoch "a": suppressing it
  // would lose a real remote change, so the epoch change always advances.
  adoptOwnerWrite({ epoch: "b", seq: 1 });
  assert.equal(getDomainVersion(), 2);
  assert.equal(calls, 2);
  // Epochs are incomparable both ways: a late stamp from any other epoch
  // adopts (a spurious re-read at worst), while same-epoch discipline
  // resumes under the newly adopted epoch.
  adoptOwnerWrite({ epoch: "a", seq: 8 });
  assert.equal(getDomainVersion(), 3);
  assert.equal(calls, 3);
  adoptOwnerWrite({ epoch: "a", seq: 8 });
  adoptOwnerWrite({ epoch: "a", seq: 5 });
  assert.equal(getDomainVersion(), 3);
  assert.equal(calls, 3);
  adoptOwnerWrite({ epoch: "a", seq: 9 });
  assert.equal(getDomainVersion(), 4);
  assert.equal(calls, 4);
});

test("legacy bare numbers never suppress a real change", () => {
  let calls = 0;
  subscribeDomain(() => { calls += 1; });
  // Legacy counters from pre-stamp peers carry no epoch: every delivery fans
  // out locally instead of risking suppression by an unrelated counter.
  adoptOwnerWrite(5);
  assert.equal(getDomainVersion(), 1);
  adoptOwnerWrite(5);
  adoptOwnerWrite(3);
  assert.equal(getDomainVersion(), 3);
  assert.equal(calls, 3);
  // A stamped write after legacy bumps still advances exactly once.
  adoptOwnerWrite({ epoch: "a", seq: 1 });
  assert.equal(getDomainVersion(), 4);
  assert.equal(calls, 4);
});

test("a failing subscriber never breaks the write path", () => {
  subscribeDomain(() => { throw new Error("boom"); });
  let calls = 0;
  subscribeDomain(() => { calls += 1; });
  notifyDomainWrite();
  assert.equal(calls, 1);
  adoptOwnerWrite({ epoch: "a", seq: 9 });
  assert.equal(calls, 2);
});

test("relaying a stamp is safe to call and keeps pre-stamp peers in sync", () => {
  // No assertion on delivery (same-process relay never loops back); this
  // guards the wire shape the owner and old tabs rely on.
  broadcastOwnerWrite({ epoch: "a", seq: 4 });
  broadcastOwnerWrite(4);
  assert.equal(getDomainVersion(), 0);
});
