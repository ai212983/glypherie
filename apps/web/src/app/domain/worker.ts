// Domain worker: owns PGlite and every graph command. Runs as a SharedWorker
// in browsers (one instance per origin: every tab's commands execute on the
// same engine and store) with a dedicated-worker fallback where SharedWorker
// is unavailable. The main thread posts {id, method, params} per connection
// and awaits a cloned result. Transaction callbacks stay inside this worker,
// so the host never serializes them across the boundary. Each committed write
// returns the owner's generation stamp (epoch per worker lifetime plus its
// sequence); skipped imports report no write. Commits are announced to every
// tab directly, so followers learn of a write even when the writing tab
// closes before its response arrives.

import { createDomainBackend, DOMAIN_DATA_DIR, type DomainBackend } from "./backend.ts";
import * as commands from "./commands.ts";
import { importLegacySnapshot } from "./importer.ts";
import { isDomainMethod, MUTATING_METHODS, type DomainDispatch } from "./operations.ts";
import { DOMAIN_CHANNEL, DOMAIN_OWNER_LEASE, DOMAIN_PROTOCOL_VERSION, type OwnerStamp } from "./protocol.ts";

// PGlite resolves its engine files relative to its own module URL, which
// Vite fingerprints into hashed assets (dev serves them from node_modules).
// The backend passes no overrides, so dev and build share one mechanism.

// Owner epoch: random per worker lifetime. Tabs adopt any stamp from an
// epoch they have not seen, so a restarted owner's reset sequence can never
// be suppressed by a stale local version.
const OWNER_EPOCH: string = (() => {
  try {
    return (globalThis as { crypto?: { randomUUID?: () => string } }).crypto?.randomUUID?.() ?? "";
  } catch {
    return "";
  }
})();
const ownerEpoch: string =
  OWNER_EPOCH !== "" ? OWNER_EPOCH : `epoch-${Date.now()}-${Math.floor(Math.random() * 2 ** 31)}`;

let backend: DomainBackend | null = null;
let initializing: Promise<DomainBackend> | null = null;
// Owner write sequence: strictly increasing per worker lifetime (per epoch),
// adopted by every tab so equal local versions can never suppress a real
// remote change.
let writeSeq = 0;

function currentStamp(): OwnerStamp {
  return { epoch: ownerEpoch, seq: writeSeq };
}

let leaseHeld = false;
let leaseAttempt: Promise<void> | null = null;

function busyError(): Error {
  return Object.assign(
    new Error("Another tab already owns the font library. Close other Glypherie tabs, then retry."),
    { code: "blocked" },
  );
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Hold the single-owner lease for this worker's lifetime. Every worker mode
 * takes the same exclusive origin lock before opening the database: the
 * second opener gets an explicit retryable busy error and never launches a
 * second PGlite engine. Without Web Locks there is no safe single-owner
 * primitive, so the engine refuses to start instead of risking split-brain
 * persistence.
 *
 * A plain exclusive request (no try-lock flag: it is not honored across all
 * contexts) queues behind a live holder. A granted request stays pending
 * for the worker's lifetime (the grant callback pends until the worker dies,
 * which releases the lock), so a bounded race tells grant from queue: on
 * timeout this attempt is cancelled and a later grant releases immediately
 * instead of leaving a zombie holder.
 */
async function acquireOwnerLease(): Promise<void> {
  if (leaseHeld) return;
  if (!leaseAttempt) {
    leaseAttempt = (async () => {
      let cancelled = false;
      try {
        const locks = (
          globalThis as {
            navigator?: {
              locks?: {
                request: (
                  name: string,
                  options: { mode: string },
                  callback: () => Promise<unknown>,
                ) => Promise<unknown>;
              };
            };
          }
        ).navigator?.locks;
        if (!locks || typeof locks.request !== "function") {
          throw Object.assign(
            new Error("Web Locks are unavailable in this context, so the domain owner cannot start safely."),
            { code: "unavailable" },
          );
        }
        let granted = false;
        let requestError: unknown = null;
        const request = locks.request(DOMAIN_OWNER_LEASE, { mode: "exclusive" }, async () => {
          // A cancelled attempt releases immediately if it is granted
          // after its timeout, so it never blocks the next opener.
          if (cancelled) return false;
          granted = true;
          // Pend for the worker's lifetime; death releases the lease.
          await new Promise<void>(() => undefined);
          return true;
        });
        // Never let a torn-down worker surface a late rejection.
        request.then(undefined, () => undefined);
        const outcome = await Promise.race([
          request.then(
            () => "settled" as const,
            (error: unknown) => {
              requestError = error;
              return "settled" as const;
            },
          ),
          delay(500).then(() => "wait" as const),
        ]);
        if (outcome === "settled") {
          if (requestError !== null) {
            throw Object.assign(
              new Error(
                `The domain owner lock failed: ${requestError instanceof Error ? requestError.message : String(requestError)}`,
              ),
              { code: "unavailable" },
            );
          }
          throw busyError();
        }
        // A grant keeps the request pending; confirm the grant callback ran
        // before opening the database, and fail closed if it never does.
        for (let attempt = 0; attempt < 20 && !granted; attempt += 1) {
          await delay(100);
        }
        if (!granted) {
          cancelled = true;
          throw busyError();
        }
        leaseHeld = true;
      } catch (error) {
        // A refused lease or failed open must not stick: the next attempt
        // (for example after the owning tab closes) retries from scratch.
        cancelled = true;
        leaseAttempt = null;
        throw error;
      }
    })();
  }
  return leaseAttempt;
}

async function ensureBackend(): Promise<DomainBackend> {
  if (backend) return backend;
  if (!initializing) {
    initializing = (async () => {
      try {
        // Fence before touching IndexedDB: a refused lease never opens PGlite.
        await acquireOwnerLease();
        const created = await createDomainBackend({ dataDir: DOMAIN_DATA_DIR, relaxedDurability: true });
        backend = created;
        return created;
      } catch (error) {
        // A refused lease or failed open must not stick: the next attempt
        // (for example after the owning tab closes) retries from scratch.
        initializing = null;
        throw error;
      }
    })();
  }
  return initializing;
}

// Dispatch agrees with the operation specification by construction: each
// handler's post-backend arguments and result must match its spec entry.
const methods: DomainDispatch = {
  saveFont: commands.saveFont,
  getFont: commands.getFont,
  listFonts: commands.listFonts,
  updateFontMetadata: commands.updateFontMetadata,
  removeFont: commands.removeFont,
  getSeedMarker: commands.getSeedMarker,
  setSeedMarker: commands.setSeedMarker,
  createVariant: commands.createVariant,
  getVariant: commands.getVariant,
  listVariants: commands.listVariants,
  updateVariant: commands.updateVariant,
  deleteVariant: commands.deleteVariant,
  listPalettes: commands.listPalettes,
  createPalette: commands.createPalette,
  updatePalette: commands.updatePalette,
  deletePalette: commands.deletePalette,
  listTextStyles: commands.listTextStyles,
  listOutputProfiles: commands.listOutputProfiles,
  listScenes: commands.listScenes,
  getScene: commands.getScene,
  createScene: commands.createScene,
  ensureDefaultScene: commands.ensureDefaultScene,
  updateScene: commands.updateScene,
  deleteScene: commands.deleteScene,
  addSceneLabel: commands.addSceneLabel,
  updateSceneLabel: commands.updateSceneLabel,
  removeSceneLabel: commands.removeSceneLabel,
  reorderSceneLabels: commands.reorderSceneLabels,
  restoreSceneSnapshot: commands.restoreSceneSnapshot,
  resolveTextStyle: commands.resolveTextStyle,
  resolveTextStyles: commands.resolveTextStyles,
  importLegacySnapshot,
};

type Responder = (message: unknown) => void;

// Every connected SharedWorker port, for commit announcements. A failing or
// closed port is dropped; one bad listener never breaks the write path.
const ports = new Set<{ postMessage: (message: unknown) => void }>();

// Durability gate for the read-after-write boundary: a mutation's response
// already awaits its filesystem flush, but reads run concurrently with an
// in-flight mutation and could present committed-but-not-yet-durable state,
// which a reload in that window loses. Reads therefore wait for every counted
// mutation received before them to finish flushing, and flushes chain so
// overlapping syncs never interleave. Long boot imports never gate reads.
let pendingWrites = 0;
let writesFinished: Promise<void> = Promise.resolve();
let finishWrites = (): void => undefined;
let flushTail: Promise<void> = Promise.resolve();

function chainFlush(work: () => Promise<void>): Promise<void> {
  const next = flushTail.then(work, work);
  flushTail = next.then(
    () => undefined,
    () => undefined,
  );
  return next;
}

let announceChannel: BroadcastChannel | null = null;

function ownerBroadcastChannel(): BroadcastChannel | null {
  if (announceChannel) return announceChannel;
  try {
    announceChannel = new BroadcastChannel(DOMAIN_CHANNEL);
  } catch {
    announceChannel = null;
  }
  return announceChannel;
}

function announceCommit(stamp: OwnerStamp): void {
  const message = {
    type: "glypherie-domain-version",
    epoch: stamp.epoch,
    seq: stamp.seq,
    // `version` keeps pre-stamp tabs in sync; they adopt it numerically.
    version: stamp.seq,
  };
  try {
    ownerBroadcastChannel()?.postMessage(message);
  } catch {
    // No BroadcastChannel here: fall through to the per-port announce below.
  }
  for (const port of [...ports]) {
    try {
      port.postMessage({ commit: { epoch: stamp.epoch, seq: stamp.seq } });
    } catch {
      ports.delete(port);
    }
  }
}

async function handleCall(data: unknown, respond: Responder): Promise<void> {
  const call = data as { id?: unknown; method?: unknown; params?: unknown };
  if (typeof call?.id !== "number" || typeof call.method !== "string" || !Array.isArray(call.params)) return;
  // Handshake: version check, owner fencing, then backend readiness. Runs
  // before any database access so a stale or second owner fails fast with a
  // retryable error instead of hanging or splitting engines.
  if (call.method === "__protocol") {
    const tabProtocol = (call.params as unknown[])[0];
    if (tabProtocol !== DOMAIN_PROTOCOL_VERSION) {
      // Discriminator for a stale owner: the tab reports which generation it
      // rejected (and which scope answered) instead of blaming other tabs.
      // Owner generations that predate these fields answer without them.
      respond({
        id: call.id,
        ok: false,
        error: {
          code: "blocked",
          message: "This tab needs a fresh domain owner. Close other Glypherie tabs, then reload to retry.",
          protocol: DOMAIN_PROTOCOL_VERSION,
          epoch: ownerEpoch,
        },
      });
      return;
    }
    try {
      await ensureBackend();
      respond({ id: call.id, ok: true, protocol: DOMAIN_PROTOCOL_VERSION, epoch: ownerEpoch, result: null });
    } catch (error) {
      const failure = error as { code?: unknown; message?: unknown };
      respond({
        id: call.id,
        ok: false,
        error: {
          code: typeof failure?.code === "string" ? failure.code : "unavailable",
          message: failure instanceof Error ? failure.message : String(error),
        },
      });
    }
    return;
  }
  // Method exposure is owned by the operation specification: non-RPC command
  // exports and object-prototype names never reach dispatch. The handshake
  // above stays the special path for version fencing.
  if (!isDomainMethod(call.method)) {
    respond({
      id: call.id,
      ok: false,
      error: { code: "unavailable", message: `Unknown domain method "${String(call.method)}".` },
    });
    return;
  }
  const method = call.method;
  const target = methods[method];
  // Counted synchronously at receipt so a later-received read always observes
  // every mutation ahead of it, closing the lost-write window deterministically.
  const countedWrite = MUTATING_METHODS.has(method) && method !== "importLegacySnapshot";
  if (countedWrite) {
    if (pendingWrites === 0) {
      writesFinished = new Promise<void>((resolve) => {
        finishWrites = resolve;
      });
    }
    pendingWrites += 1;
  }
  try {
    if (!countedWrite) {
      // Yield until writes settle; polling a resolved flush tail would starve
      // the timer and filesystem callbacks those writes need to finish.
      await writesFinished;
    }
    const active = await ensureBackend();
    // Wire arguments arrive untyped at this boundary; the per-method handler
    // signature above still governs every typed caller of the same command.
    const invoke = target as (backend: DomainBackend, ...args: unknown[]) => Promise<unknown>;
    const result = await invoke(active, ...(call.params as unknown[]));
    // A skipped import changed nothing: report no write so tabs neither bump
    // versions nor rebroadcast.
    const skippedImport =
      method === "importLegacySnapshot" &&
      typeof result === "object" &&
      result !== null &&
      (result as { skipped?: unknown }).skipped === true;
    const mutated = MUTATING_METHODS.has(method) && !skippedImport;
    let stamp: OwnerStamp | undefined;
    if (mutated) {
      // PGlite skips filesystem sync during explicit transactions, including
      // COMMIT, and under relaxed durability per-query results return before
      // the scheduled flush. This awaited filesystem flush is the durable
      // boundary before stamp, announce and response; chained so concurrent
      // mutations never interleave syncs and a failed sync never blocks the
      // next write's persistence attempt.
      await chainFlush(() => active.flush());
      writeSeq += 1;
      stamp = currentStamp();
      // Announce from the owner itself: followers adopt the commit even when
      // the writing tab closes before receiving its own response.
      announceCommit(stamp);
    }
    respond({ id: call.id, ok: true, mutated, epoch: stamp?.epoch, seq: stamp?.seq, result });
  } catch (error) {
    const failure = error as { code?: unknown; message?: unknown };
    respond({
      id: call.id,
      ok: false,
      error: {
        code: typeof failure?.code === "string" ? failure.code : "unavailable",
        message: failure instanceof Error ? failure.message : String(error),
      },
    });
  } finally {
    if (countedWrite && --pendingWrites === 0) finishWrites();
  }
}

const scope = self as unknown as {
  onmessage: ((event: MessageEvent) => void) | null;
  postMessage: (message: unknown) => void;
  onconnect?: ((event: MessageEvent & { ports: readonly MessagePort[] }) => void) | null;
};

if ("onconnect" in self) {
  // SharedWorker: one instance per origin. Every connecting tab gets its own
  // port; commands from all ports share this engine, store and sequence.
  scope.onconnect = (event) => {
    for (const port of event.ports) {
      ports.add(port);
      port.onmessage = (msg: MessageEvent) => {
        void handleCall(msg.data, (response) => {
          try {
            port.postMessage(response);
          } catch {
            ports.delete(port);
          }
        });
      };
      const forget = (): void => {
        ports.delete(port);
      };
      port.addEventListener?.("close", forget);
      try {
        port.start();
      } catch {
        ports.delete(port);
      }
    }
  };
} else {
  scope.onmessage = (event: MessageEvent) => {
    void handleCall(event.data, (response) => scope.postMessage(response));
  };
}
