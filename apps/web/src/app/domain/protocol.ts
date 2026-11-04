// Shared domain-owner contract. The browser main thread (runtime.ts) and the
// domain worker (worker.ts) agree on these constants; the handshake rejects a
// tab whose protocol differs so mixed app/owner versions fail visibly instead
// of splitting engines or silently misreading state.

/** Single SharedWorker name per origin: joining, never a second engine. */
export const DOMAIN_WORKER_NAME = "glypherie-domain-v1";

/** Cross-tab commit announcements (owner direct + writer relay). */
export const DOMAIN_CHANNEL = "glypherie-domain-v1";

/**
 * Lifetime origin lease fencing the single PGlite engine. Every worker mode
 * holds this exclusive lock before opening the database, so a second opener
 * gets an explicit retryable busy error instead of a split-brain engine.
 */
export const DOMAIN_OWNER_LEASE = "glypherie-domain-owner-v1";

/**
 * Tab/worker wire version. Bump when the handshake or response shape changes
 * incompatibly; the handshake then forces old/new pairs to fail with an
 * explicit reload/close-tabs error instead of misbehaving. Baked at build
 * time from VITE_DOMAIN_PROTOCOL (tests build two generations to prove the
 * mismatch path); the default keeps every existing deployment on version 2.
 */
function configuredProtocolVersion(): number {
  const fromEnv = (import.meta as unknown as { env?: Record<string, string | undefined> })
    .env?.VITE_DOMAIN_PROTOCOL;
  const parsed = fromEnv === undefined || fromEnv === "" ? NaN : Number(fromEnv);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 2;
}

export const DOMAIN_PROTOCOL_VERSION = configuredProtocolVersion();

/** Owner generation stamp: an epoch per worker lifetime plus its sequence. */
export interface OwnerStamp {
  epoch: string;
  seq: number;
}

export function isOwnerStamp(value: unknown): value is OwnerStamp {
  if (typeof value !== "object" || value === null) return false;
  const { epoch, seq } = value as { epoch?: unknown; seq?: unknown };
  return typeof epoch === "string" && epoch !== ""
    && typeof seq === "number" && Number.isInteger(seq) && seq > 0;
}
