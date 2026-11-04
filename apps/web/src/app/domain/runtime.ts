// Ambient domain access. The browser main thread talks to a single domain
// owner through a SharedWorker proxy with the command surface; Node/tests use
// a direct backend from node-backend. One SharedWorker instance exists per
// origin, so exactly one PGlite engine and one TypeGraph store serve every
// tab: tabs never hold stale in-memory engines and cross-tab CAS stays
// race-free. The engine (backend/commands/importer) stays out of this
// module's static imports so the main-thread chunk never pays for PGlite:
// the worker bundle imports it directly, Node reaches it through lazy imports
// below. Every command result is structured-cloneable, so the worker boundary
// never serializes store callbacks.

import type { DomainBackend } from "./backend.ts";
import { adoptOwnerWrite, broadcastOwnerWrite } from "./events.ts";
import {
  DOMAIN_PROTOCOL_VERSION,
  DOMAIN_WORKER_NAME,
  isOwnerStamp,
} from "./protocol.ts";

export type DomainMethod =
  | "saveFont" | "getFont" | "listFonts" | "updateFontMetadata" | "removeFont"
  | "getSeedMarker" | "setSeedMarker"
  | "createVariant" | "getVariant" | "listVariants" | "updateVariant" | "deleteVariant"
  | "listPalettes" | "createPalette" | "updatePalette" | "deletePalette"
  | "listTextStyles" | "listOutputProfiles" | "listScenes" | "getScene"
  | "createScene" | "updateScene" | "deleteScene"
  | "addSceneLabel" | "updateSceneLabel" | "removeSceneLabel" | "restoreSceneSnapshot"
  | "resolveTextStyle" | "resolveTextStyles"
  | "importLegacySnapshot";

/** Writes bump the domain version; reads never do (or subscribers loop). */
export const MUTATING_METHODS: ReadonlySet<DomainMethod> = new Set([
  "saveFont",
  "updateFontMetadata",
  "removeFont",
  "setSeedMarker",
  "createVariant",
  "updateVariant",
  "deleteVariant",
  "createPalette",
  "updatePalette",
  "deletePalette",
  "createScene",
  "updateScene",
  "deleteScene",
  "addSceneLabel",
  "updateSceneLabel",
  "removeSceneLabel",
  "restoreSceneSnapshot",
  "importLegacySnapshot",
]);

export interface DomainTransport {
  call(method: DomainMethod, params: unknown[]): Promise<unknown>;
}

/**
 * Bounded transport lifecycle. Every owner handshake and call carries a
 * deadline: a silent owner (hung startup, dead worker, lost response) fails
 * the transport and rejects everything pending with a retryable error instead
 * of hanging callers. Importing a legacy snapshot moves far more data than a
 * normal call, so it gets its own longer deadline.
 */
const OWNER_HANDSHAKE_TIMEOUT_MS = 60_000;
const OWNER_CALL_TIMEOUT_MS = 30_000;
const OWNER_IMPORT_TIMEOUT_MS = 180_000;
/**
 * A worker that reports a startup error (its script failed to evaluate)
 * poisons every reconstruction against the same asset: the replacement
 * joins a dead scope that never errors and never answers, so each attempt
 * would burn the full cold-boot budget. Attempts within this window after
 * such a failure use a short probe instead; a fixed asset answers well
 * within it, and its success clears the latch.
 */
const STARTUP_FAILURE_WINDOW_MS = 60_000;
const STARTUP_RETRY_TIMEOUT_MS = 8_000;

let handshakeTimeoutMs = OWNER_HANDSHAKE_TIMEOUT_MS;
let callTimeoutMs = OWNER_CALL_TIMEOUT_MS;
let importTimeoutMs = OWNER_IMPORT_TIMEOUT_MS;
let startupRetryTimeoutMs = STARTUP_RETRY_TIMEOUT_MS;
let lastStartupFailureAt = 0;

/** Test seam: shorten deadlines for lifecycle tests. */
export function setTransportTimeoutsForTests(next: { handshakeMs?: number; callMs?: number; importMs?: number; startupRetryMs?: number }): void {
  if (next.handshakeMs !== undefined) handshakeTimeoutMs = next.handshakeMs;
  if (next.callMs !== undefined) callTimeoutMs = next.callMs;
  if (next.importMs !== undefined) importTimeoutMs = next.importMs;
  if (next.startupRetryMs !== undefined) startupRetryTimeoutMs = next.startupRetryMs;
}

let transport: DomainTransport | null = null;
let initializing: Promise<DomainTransport> | null = null;
let owner: SharedWorker | Worker | null = null;
let ownerPort: MessagePort | null = null;
/** Owner generation: bumped on every (re)connect so late responses from a
 * dead transport can never settle a new transport's calls. */
let generation = 0;
let pending = new Map<number, {
  generation: number;
  resolve: (value: unknown) => void;
  reject: (error: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
}>();
let nextCallId = 1;

export function isNodeContext(): boolean {
  return typeof window === "undefined";
}

function wrapError(error: unknown): Error {
  if (error instanceof Error) return error;
  const failure = error as { code?: unknown; message?: unknown };
  const code = typeof failure?.code === "string" ? failure.code : "unavailable";
  const message = typeof failure?.message === "string" ? failure.message : String(error);
  const wrapped = new Error(message);
  (wrapped as { code?: unknown }).code = code;
  return wrapped;
}

function errorWithCode(code: string, message: string): Error {
  const error = new Error(message);
  (error as { code?: unknown }).code = code;
  return error;
}

/** Test seam: forget worker state so the next test starts isolated. */
export function resetDomainTransportForTests(): void {
  for (const entry of pending.values()) {
    clearTimeout(entry.timer);
    entry.reject(new Error("Domain transport reset for tests."));
  }
  pending = new Map();
  teardownOwner();
  generation += 1;
  transport = null;
  initializing = null;
  handshakeTimeoutMs = OWNER_HANDSHAKE_TIMEOUT_MS;
  callTimeoutMs = OWNER_CALL_TIMEOUT_MS;
  importTimeoutMs = OWNER_IMPORT_TIMEOUT_MS;
  startupRetryTimeoutMs = STARTUP_RETRY_TIMEOUT_MS;
  lastStartupFailureAt = 0;
  nextCallId = 1;
}

function teardownOwner(): void {
  try {
    ownerPort?.close();
  } catch {
    // Best-effort teardown only.
  }
  ownerPort = null;
  if (typeof Worker !== "undefined" && owner instanceof Worker) {
    try {
      owner.terminate();
    } catch {
      // Best-effort teardown only.
    }
  }
  owner = null;
}

/** A worker that fires an async startup error joins a poisoned scope:
 * latch the moment so a reconstruction against the same broken asset probes
 * briefly instead of hanging a full cold-boot budget per boot stage. */
function noteStartupFailure(error: unknown, ownerGeneration: number): void {
  if (ownerGeneration !== generation) return;
  lastStartupFailureAt = Date.now();
  failOwner(error, ownerGeneration);
}

/** Startup error text without assuming DOM error globals (unit tests run
 * the transport in Node, where ErrorEvent does not exist). */
function startupErrorMessage(event: unknown): string {
  if (
    typeof ErrorEvent !== "undefined"
    && event instanceof ErrorEvent
    && typeof event.message === "string"
    && event.message !== ""
  ) {
    return event.message;
  }
  return "Domain worker failed.";
}

/** A dead or failed owner must never strand callers: reject everything
 * pending and drop the transport so the next call re-establishes the owner
 * and retries. Mutations are never retried automatically: a rejected mutation
 * may still have committed, so the caller decides (CAS guards make a manual
 * retry safe to surface). */
function failOwner(error: unknown, ownerGeneration: number): void {
  if (ownerGeneration !== generation) return;
  const failure = error instanceof Error ? error : new Error(String(error));
  teardownOwner();
  generation += 1;
  transport = null;
  initializing = null;
  for (const entry of pending.values()) {
    clearTimeout(entry.timer);
    entry.reject(failure);
  }
  pending = new Map();
}

function settlePending(id: number, generationAtSend: number, settle: (entry: {
  resolve: (value: unknown) => void;
  reject: (error: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
}) => void): void {
  const entry = pending.get(id);
  // A response from a dead generation never settles the new transport.
  if (!entry || entry.generation !== generationAtSend) return;
  pending.delete(id);
  clearTimeout(entry.timer);
  settle(entry);
}

function handleMessage(ownerGeneration: number, event: MessageEvent): void {
  if (ownerGeneration !== generation) return;
  const data = event.data as {
    id?: unknown;
    ok?: unknown;
    mutated?: unknown;
    epoch?: unknown;
    seq?: unknown;
    commit?: unknown;
    result?: unknown;
    error?: { code?: unknown; message?: unknown };
  };
  // Owner commit announcements on the RPC port (BroadcastChannel fallback):
  // adopt without settling any call.
  if (data?.commit !== undefined && data?.commit !== null) {
    adoptOwnerWrite(data.commit);
    return;
  }
  if (typeof data?.id !== "number") return;
  const entry = pending.get(data.id);
  // A response from a dead generation never settles the new transport.
  if (!entry || entry.generation !== ownerGeneration) return;
  pending.delete(data.id);
  clearTimeout(entry.timer);
  if (data.ok) {
    if (data.mutated === true) {
      // The owner orders every committed write; adopt its stamp so equal
      // local versions can never suppress a real remote change. The owner
      // announces directly and the writer relays: both carry the same stamp
      // and adoption dedupes them, so followers learn of the commit even if
      // the writing tab closes before receiving this response.
      const stamp = isOwnerStamp({ epoch: data.epoch, seq: data.seq })
        ? { epoch: data.epoch as string, seq: data.seq as number }
        : data.seq;
      adoptOwnerWrite(stamp);
      if (isOwnerStamp(stamp) || typeof stamp === "number") broadcastOwnerWrite(stamp);
    }
    entry.resolve(data.result);
  } else {
    entry.reject(wrapError(data.error));
  }
}

function rejectAfterTimeout(id: number, timeoutMs: number, method: string): ReturnType<typeof setTimeout> {
  return setTimeout(() => {
    const entry = pending.get(id);
    if (!entry) return;
    // A hung owner is suspect as a whole: fail the transport so every
    // pending call rejects cleanly and the next call reconnects. The mutation
    // itself is not retried: its commit outcome is unknown to this tab.
    failOwner(errorWithCode(
      "unavailable",
      `The domain owner did not answer "${method}" in time. Retry the action.`,
    ), entry.generation);
  }, timeoutMs);
}

function ownerTransport(
  send: (message: unknown) => void,
  ownerGeneration: number,
): DomainTransport {
  return {
    call(method: DomainMethod, params: unknown[]): Promise<unknown> {
      if (ownerGeneration !== generation) {
        return Promise.reject(errorWithCode("unavailable", "The domain connection has closed. Retry the action."));
      }
      const id = nextCallId++;
      const timeoutMs = method === "importLegacySnapshot" ? importTimeoutMs : callTimeoutMs;
      return new Promise<unknown>((resolve, reject) => {
        const timer = rejectAfterTimeout(id, timeoutMs, method);
        pending.set(id, { generation: ownerGeneration, resolve, reject, timer });
        try {
          send({ id, method, params });
        } catch (error) {
          settlePending(id, ownerGeneration, (entry) => entry.reject(wrapError(error)));
        }
      });
    },
  };
}

/**
 * Map a handshake rejection from a pre-protocol owner (it answers the
 * version probe with unknown-method): the live owner belongs to an older app
 * generation, so closing the other tabs and retrying is the recovery — the
 * same remedy as a refused single-owner lease.
 */
function mapHandshakeError(error: unknown): Error {
  // Only the pre-protocol unknown-method answer maps here: a timeout on the
  // handshake itself is a dead owner, not a stale one, and keeps its
  // unavailable code so the UI reports plainly instead of naming tabs.
  if (
    error instanceof Error
    && (error as { code?: unknown }).code === "unavailable"
    && error.message.includes('"__protocol"')
    && error.message.includes("Unknown domain method")
  ) {
    return errorWithCode(
      "blocked",
      "This tab needs a fresh domain owner. Close other Glypherie tabs, then reload to retry.",
    );
  }
  return error instanceof Error ? error : new Error(String(error));
}

/**
 * Map a synchronous owner-construction failure. The spec rejects
 * same-name/different-URL SharedWorkers with InvalidAccessError: that means a
 * live owner from another app version holds the name, so closing the other
 * tabs and retrying is the recovery. Any other construction failure means
 * the owner never started.
 */
function constructionError(error: unknown): Error {
  if (error instanceof Error && error.name === "InvalidAccessError") {
    return errorWithCode(
      "blocked",
      "Another app version still owns the font library. Close other Glypherie tabs, then retry.",
    );
  }
  return wrapError(error);
}

function createOwner(): { transport: DomainTransport; generation: number } {
  teardownOwner();
  const ownerGeneration = ++generation;
  const handle = (event: MessageEvent): void => handleMessage(ownerGeneration, event);
  // Single database owner across tabs: the browser runs one SharedWorker per
  // origin under a stable entry URL, so every tab's commands execute on the
  // same PGlite engine and the same TypeGraph store. The stable URL survives
  // deployments (the name plus URL join the live owner); a versioned
  // handshake below rejects mixed app/owner pairs explicitly. Tab close needs
  // no handover protocol (the worker outlives any one tab) and simultaneous
  // cold boots share the instance. Contexts without SharedWorker (older
  // engines, some embedded views) fall back to a dedicated worker fenced by
  // the same origin lock: only the first opener runs the engine.
  try {
    if (typeof SharedWorker !== "undefined") {
      const shared = new SharedWorker(new URL("./worker.ts", import.meta.url), {
        type: "module",
        name: DOMAIN_WORKER_NAME,
      });
      owner = shared;
      const port = shared.port;
      ownerPort = port;
      port.onmessage = handle;
      port.onmessageerror = (event) => failOwner(event instanceof Error ? event : new Error("Domain channel failed."), ownerGeneration);
      shared.onerror = (event) => noteStartupFailure(new Error(startupErrorMessage(event)), ownerGeneration);
      port.start();
      return { transport: ownerTransport((message) => port.postMessage(message), ownerGeneration), generation: ownerGeneration };
    }
  } catch (error) {
    throw constructionError(error);
  }
  const active = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
  owner = active;
  active.onmessage = handle;
  active.onerror = (event) => noteStartupFailure(new Error(`Domain worker failed: ${event.message}`), ownerGeneration);
  active.onmessageerror = () => failOwner(new Error("Domain channel failed."), ownerGeneration);
  return { transport: ownerTransport((message) => active.postMessage(message), ownerGeneration), generation: ownerGeneration };
}

async function startBrowserDomain(): Promise<DomainTransport> {
  const { transport: candidate, generation: candidateGeneration } = createOwner();
  const handshakeId = nextCallId++;
  // A recent startup failure means this construction likely joins the same
  // poisoned scope: probe briefly instead of burning the full cold-boot
  // budget again. A fixed asset answers well within the probe.
  const probingPoisonedScope = Date.now() - lastStartupFailureAt < STARTUP_FAILURE_WINDOW_MS;
  const handshakeBudgetMs = probingPoisonedScope ? startupRetryTimeoutMs : handshakeTimeoutMs;
  try {
    // Handshake: version check, single-owner fencing, then backend readiness.
    // The transport publishes only after this succeeds, so a stale, busy or
    // failed owner surfaces a retryable error instead of hanging the tab.
    await new Promise<unknown>((resolve, reject) => {
      const timer = rejectAfterTimeout(handshakeId, handshakeBudgetMs, "__protocol");
      pending.set(handshakeId, { generation: candidateGeneration, resolve, reject, timer });
      try {
        if (!ownerPort && !(owner instanceof Worker)) throw new Error("Domain owner has no channel.");
        const send = ownerPort ? (message: unknown): void => ownerPort?.postMessage(message) : (message: unknown): void => (owner as Worker).postMessage(message);
        send({ id: handshakeId, method: "__protocol", params: [DOMAIN_PROTOCOL_VERSION] });
      } catch (error) {
        settlePending(handshakeId, candidateGeneration, (entry) => entry.reject(constructionError(error)));
      }
    });
    // An answered handshake proves the scope is healthy: clear any startup
    // latch so later attempts get the full cold-boot budget again.
    if (candidateGeneration !== generation) throw errorWithCode("unavailable", "The domain connection has closed. Retry the action.");
    lastStartupFailureAt = 0;
    return candidate;
  } catch (error) {
    // A failed handshake owns nothing usable: drop it so the next call
    // reconnects from scratch (for example after the owning tab closes).
    const mapped = mapHandshakeError(error);
    failOwner(mapped, candidateGeneration);
    throw mapped;
  }
}

/**
 * Browser main-thread path: a shared worker owns PGlite and the graph
 * commands. Concurrent callers await the same readiness; a failed handshake
 * resets it so the next caller retries. The proxy below exposes the same
 * command surface; results are structured-cloned and every committed write
 * adopts the owner's stamp.
 */
export async function initBrowserDomain(): Promise<DomainTransport> {
  if (transport) return transport;
  if (initializing) return initializing;
  if (isNodeContext()) throw new Error("initBrowserDomain() needs a browser window; use node-backend in Node.");
  const attempt = startBrowserDomain().then(
    (ready) => {
      if (initializing !== attempt) throw errorWithCode("unavailable", "The domain connection has closed. Retry the action.");
      transport = ready;
      initializing = null;
      return ready;
    },
    (error: unknown) => {
      if (initializing === attempt) {
        initializing = null;
        teardownOwner();
      }
      throw error;
    },
  );
  initializing = attempt;
  return attempt;
}

export function getTransport(): DomainTransport | null {
  return transport;
}

export function isBrowserTransport(): boolean {
  return transport !== null;
}

/**
 * Dispatch one domain call: worker proxy in the browser, direct backend in
 * Node/tests. Mutating calls adopt the owner's stamp; reads stay silent.
 */
export async function callDomain(method: DomainMethod, params: unknown[]): Promise<unknown> {
  const active = transport ?? (!isNodeContext() ? await initBrowserDomain() : null);
  if (active) return active.call(method, params);
  const [{ ensureNodeBackend }, commands, { importLegacySnapshot }] = await Promise.all([
    import("./node-backend.ts"),
    import("./commands.ts"),
    import("./importer.ts"),
  ]);
  const table: Record<string, (backend: DomainBackend, ...args: unknown[]) => Promise<unknown>> = {
    ...(commands as unknown as Record<string, (backend: DomainBackend, ...args: unknown[]) => Promise<unknown>>),
    importLegacySnapshot: importLegacySnapshot as unknown as (
      backend: DomainBackend,
      ...args: unknown[]
    ) => Promise<unknown>,
  };
  const target = table[method];
  if (typeof target !== "function") throw new Error(`Unknown domain method "${method}".`);
  try {
    const result = await target(await ensureNodeBackend(), ...params);
    if (MUTATING_METHODS.has(method)) {
      const skippedImport = method === "importLegacySnapshot"
        && typeof result === "object" && result !== null
        && (result as { skipped?: unknown }).skipped === true;
      if (!skippedImport) {
        const { notifyDomainWrite } = await import("./events.ts");
        notifyDomainWrite();
      }
    }
    return result;
  } catch (error) {
    throw wrapError(error);
  }
}
