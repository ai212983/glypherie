// Snapshot reads hold one transaction across every entity they assemble, so a
// concurrent committed edit cannot mix fields across revisions. Interleaving is
// injected at the transaction-handle seam while the test goes through the
// public consumer API: the read runs inside its normal transaction, the edit is
// issued from inside that transaction's handle (proving the seam is live) and
// queues on the single PGlite connection, then commits once the read releases.
// A single PGlite connection serializes transactions, so the queued edit is
// never awaited while holding the read transaction (that would deadlock);
// ordering comes from program order plus the engine queue, with no sleeps.

import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import {
  closeDomainForTests,
  getBackend,
  resetDomainForTests,
} from "../../src/app/domain/node-backend.ts";
import {
  listOutputProfiles,
  resolveTextStyle,
  resolveTextStyles,
} from "../../src/app/domain/service.ts";
import { saveFont, type FontMetadata } from "../../src/app/fonts/storage.ts";
import { createVariant, getVariant, updateVariant } from "../../src/app/variants/repository.ts";
import { kvGet } from "../../src/app/domain/backend.ts";
import { previewKey } from "../../src/app/domain/variant-plan.ts";

beforeEach(async () => {
  await resetDomainForTests();
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

async function saveFixture(seed = 0) {
  return saveFont({
    bytes: fontBytes(seed),
    fileName: "fixture.ttf",
    name: "Fixture",
    metadata: metadata(),
    source: "uploaded",
  });
}

async function monoId(): Promise<string> {
  const mono = (await listOutputProfiles()).find((profile) => profile.name === "Monochrome");
  assert.ok(mono);
  return mono.id;
}

// Mutable views of the handles this test wraps; restored in `finally`.
type StoreTx = (callback: (tx: unknown) => Promise<unknown>) => Promise<unknown>;
type DbTx = (callback: (tx: unknown) => Promise<unknown>) => Promise<unknown>;
interface NodeClient {
  getById: (...args: never[]) => Promise<unknown>;
}
interface TxNodes {
  nodes: Record<string, NodeClient>;
}

test("single and batch resolution agree on one style", async () => {
  const font = await saveFixture();
  const variant = await createVariant(font.id, { name: "Solo" });
  const mono = await monoId();
  const single = await resolveTextStyle(variant.id, mono);
  const [batched] = await resolveTextStyles([variant.id], mono);
  assert.ok(batched);
  assert.deepEqual(single, batched);
});

test("single resolution stays coherent across a concurrent committed edit", async () => {
  const font = await saveFixture();
  const initial = await createVariant(font.id, { name: "Snap" });
  const mono = await monoId();
  const before = { size: initial.settings.sizePx, spacing: initial.settings.letterSpacingPx };
  const backend = getBackend();
  const storeHandle = backend.store as unknown as { transaction: StoreTx };
  const realTransaction = storeHandle.transaction;
  let readOpen = false;
  let intercepted = false;
  let issuedWhileOpen = false;
  let txCalls = 0;
  let edit: ReturnType<typeof updateVariant> | undefined;
  storeHandle.transaction = async (callback: (tx: unknown) => Promise<unknown>) => {
    txCalls += 1;
    return realTransaction.call(backend.store, async (tx: unknown) => {
      readOpen = true;
      try {
        // Wrap the live transaction handle: the variant read below runs
        // through this seam inside the read's own transaction.
        const nodes = (tx as unknown as TxNodes).nodes;
        const variantClient = nodes["FontVariant"];
        assert.ok(variantClient);
        const realGetById = variantClient.getById.bind(variantClient);
        const wrappedTx = new Proxy(tx as Record<string, unknown>, {
          get(target, key) {
            if (key !== "nodes") return Reflect.get(target, key);
            return new Proxy(nodes, {
              get(nodesTarget, nodeKey) {
                if (nodeKey !== "FontVariant") return Reflect.get(nodesTarget, nodeKey);
                return new Proxy(variantClient, {
                  get(clientTarget, clientKey) {
                    if (clientKey !== "getById") return Reflect.get(clientTarget, clientKey);
                    return async (...args: never[]) => {
                      const node = await realGetById(...args);
                      if (!intercepted) {
                        intercepted = true;
                        issuedWhileOpen = readOpen;
                        // Fire-and-forget: awaiting here would deadlock, the
                        // queued edit runs once this read commits.
                        const pending = updateVariant(
                          initial.id,
                          {
                            name: "Snap after",
                            settings: { ...initial.settings, sizePx: 30, letterSpacingPx: 3 },
                          },
                          initial.revision,
                        );
                        pending.catch(() => undefined);
                        edit = pending;
                      }
                      return node;
                    };
                  },
                });
              },
            });
          },
        });
        // Await (not return) so `finally` runs after the read settles: a
        // bare return would drop `readOpen` before the read finishes.
        const out = await callback(wrappedTx);
        return out;
      } finally {
        readOpen = false;
      }
    });
  };
  let resolved: Awaited<ReturnType<typeof resolveTextStyle>>;
  try {
    resolved = await resolveTextStyle(initial.id, mono);
  } finally {
    storeHandle.transaction = realTransaction;
  }
  assert.equal(txCalls, 1, "expected the read to hold exactly one transaction");
  assert.ok(intercepted, "transaction-handle interception never fired");
  assert.ok(edit !== undefined, "concurrent edit was never issued during the read");
  assert.equal(issuedWhileOpen, true, "edit was not issued while the read held its transaction");
  const committed = await edit;
  assert.equal(committed.revision, initial.revision + 1, "queued edit did not commit after the read");
  const pair = { size: resolved.settings.sizePx, spacing: resolved.settings.letterSpacingPx };
  assert.deepEqual(pair, before, `torn snapshot: ${JSON.stringify({ before, pair })}`);
  const [batched] = await resolveTextStyles([initial.id], mono);
  assert.ok(batched);
  assert.deepEqual(
    { size: batched.settings.sizePx, spacing: batched.settings.letterSpacingPx },
    { size: 30, spacing: 3 },
    "subsequent read does not see the committed revision",
  );
  const again = await resolveTextStyle(initial.id, mono);
  assert.deepEqual(again, batched);
});

test("variant views stay coherent across a concurrent committed edit", async () => {
  const font = await saveFixture();
  const initial = await createVariant(font.id, { name: "View", sampleText: "before" });
  const backend = getBackend();
  const dbHandle = backend.db as unknown as { transaction: DbTx };
  const realDbTransaction = dbHandle.transaction;
  let readOpen = false;
  let intercepted = false;
  let issuedWhileOpen = false;
  let armed = true;
  let txCalls = 0;
  let edit: ReturnType<typeof updateVariant> | undefined;
  dbHandle.transaction = async (callback: (tx: unknown) => Promise<unknown>) => {
    if (!armed) return realDbTransaction.call(backend.db, callback);
    txCalls += 1;
    return realDbTransaction.call(backend.db, async (txDb: unknown) => {
      readOpen = true;
      try {
        // Wrap the live auxiliary handle: graph and preference reads below
        // both run through this handle inside the read's outer transaction.
        const handle = txDb as Record<string, unknown>;
        const realExecute = (handle["execute"] as (...args: never[]) => Promise<unknown>).bind(handle);
        const wrappedDb = new Proxy(handle, {
          get(target, key) {
            const value: unknown = Reflect.get(target, key);
            if (key !== "execute") {
              return typeof value === "function"
                ? (value as (...args: never[]) => unknown).bind(target)
                : value;
            }
            return async (...args: never[]) => {
              if (!intercepted) {
                intercepted = true;
                issuedWhileOpen = readOpen;
                armed = false;
                const pending = updateVariant(
                  initial.id,
                  { settings: { ...initial.settings, sizePx: 30 }, sampleText: "after" },
                  initial.revision,
                );
                pending.catch(() => undefined);
                edit = pending;
              }
              return realExecute(...args);
            };
          },
        });
        // Await (not return) so `finally` runs after the read settles.
        const out = await callback(wrappedDb);
        return out;
      } finally {
        readOpen = false;
      }
    });
  };
  let seen: Awaited<ReturnType<typeof getVariant>>;
  try {
    seen = await getVariant(initial.id);
  } finally {
    dbHandle.transaction = realDbTransaction;
  }
  assert.equal(txCalls, 1, "expected the view to hold exactly one outer transaction");
  assert.ok(intercepted, "transaction-handle interception never fired");
  assert.ok(edit !== undefined, "concurrent edit was never issued during the read");
  assert.equal(issuedWhileOpen, true, "edit was not issued while the read held its transaction");
  const committed = await edit;
  assert.equal(committed.revision, initial.revision + 1, "queued edit did not commit after the read");
  assert.ok(seen);
  assert.deepEqual(
    { size: seen.settings.sizePx, sample: seen.sampleText, rev: seen.revision },
    { size: initial.settings.sizePx, sample: "before", rev: initial.revision },
    `torn variant view: ${JSON.stringify(seen)}`,
  );
  const settled = await getVariant(initial.id);
  assert.equal(settled?.settings.sizePx, 30);
  assert.equal(settled?.sampleText, "after");
  assert.equal(settled?.revision, initial.revision + 1);
});

// Negative control: without a shared snapshot, separated autocommit reads with
// a committed edit between them mix revisions. Fully sequenced, no prod
// changes; proves the coherence predicates above can actually fail.
test("control: separated autocommit reads mix revisions without a snapshot", async () => {
  const font = await saveFixture();
  const initial = await createVariant(font.id, { name: "Ctl" });
  const backend = getBackend();
  const style = await backend.store.nodes.TextStyle.getById(initial.id as never).catch(() => undefined);
  assert.ok(style);
  const variantEdge = (await backend.store.edges.usesVariant.findFrom(style))[0];
  const profileEdge = (await backend.store.edges.usesProfile.findFrom(style))[0];
  assert.ok(variantEdge);
  assert.ok(profileEdge);
  const variantBefore = (await backend.store.nodes.FontVariant.getById(
    variantEdge.toId,
  )) as unknown as Record<string, unknown>;
  await updateVariant(
    initial.id,
    { name: "Ctl after", settings: { ...initial.settings, sizePx: 30, letterSpacingPx: 3 } },
    initial.revision,
  );
  const profileAfter = (await backend.store.nodes.RenderingProfile.getById(
    profileEdge.toId,
  )) as unknown as Record<string, unknown>;
  const torn = { size: variantBefore["fontSize"], spacing: profileAfter["letterSpacing"] };
  const coherent =
    (torn.size === initial.settings.sizePx && torn.spacing === initial.settings.letterSpacingPx) ||
    (torn.size === 30 && torn.spacing === 3);
  assert.equal(coherent, false, `control unexpectedly coherent: ${JSON.stringify(torn)}`);
});

// Negative control for the view predicate: a graph read and a preference read
// with a committed edit between them return the old size with the new sample.
test("control: separated graph and preference reads mix revisions without a snapshot", async () => {
  const font = await saveFixture();
  const initial = await createVariant(font.id, { name: "ViewCtl", sampleText: "before" });
  const backend = getBackend();
  const style = await backend.store.nodes.TextStyle.getById(initial.id as never).catch(() => undefined);
  assert.ok(style);
  const variantEdge = (await backend.store.edges.usesVariant.findFrom(style))[0];
  assert.ok(variantEdge);
  const variantBefore = (await backend.store.nodes.FontVariant.getById(
    variantEdge.toId,
  )) as unknown as Record<string, unknown>;
  await updateVariant(
    initial.id,
    { settings: { ...initial.settings, sizePx: 30 }, sampleText: "after" },
    initial.revision,
  );
  const raw = await kvGet(backend.db, previewKey(initial.id));
  assert.ok(raw);
  const prefsAfter = JSON.parse(raw) as { sampleText: string };
  const torn = { size: variantBefore["fontSize"], sample: prefsAfter.sampleText };
  const coherent =
    (torn.size === initial.settings.sizePx && torn.sample === "before") ||
    (torn.size === 30 && torn.sample === "after");
  assert.equal(coherent, false, `control unexpectedly coherent: ${JSON.stringify(torn)}`);
});
