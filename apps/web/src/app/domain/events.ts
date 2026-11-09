// Domain change notifications for useSyncExternalStore hooks. Exactly one
// domain owner executes committed writes; each committed write carries that
// owner's generation stamp (epoch per worker lifetime plus its sequence).
// Tabs track the latest stamp they adopted: a new epoch is always adopted
// (sequence counters restart with the owner, so cross-epoch numbers are
// incomparable), while within one epoch only a higher sequence advances.
// Legacy bare numbers (pre-stamp peers, local Node bumps) carry no epoch and
// are never compared against owner sequences: they always fan out locally.

import { DOMAIN_CHANNEL, isOwnerStamp, type OwnerStamp } from "./protocol.ts";

type Listener = () => void;

const listeners = new Set<Listener>();
let version = 0;
let ownerEpoch: string | null = null;
let ownerSeq = 0;
let channel: BroadcastChannel | null = null;

function ensureChannel(): BroadcastChannel | null {
  if (channel) return channel;
  if (typeof BroadcastChannel === "undefined") return null;
  try {
    channel = new BroadcastChannel(DOMAIN_CHANNEL);
    channel.onmessage = (event: MessageEvent) => {
      const data = event.data as { type?: unknown; epoch?: unknown; seq?: unknown; version?: unknown };
      if (data?.type !== "glypherie-domain-version") return;
      // Owner stamps (direct owner announce or writer relay) adopt by epoch;
      // legacy bare versions (old tabs, local bumps) fan out without compare.
      if (isOwnerStamp({ epoch: data.epoch, seq: data.seq })) {
        adoptOwnerWrite({ epoch: data.epoch as string, seq: data.seq as number });
      } else {
        adoptOwnerWrite(data.version);
      }
    };
  } catch {
    channel = null;
  }
  return channel;
}

function fanOut(): void {
  for (const listener of [...listeners]) {
    try {
      listener();
    } catch {
      // A failing subscriber must not break the write path.
    }
  }
}

/**
 * Adopt a committed write from the single domain owner. A stamp from a new
 * owner epoch is always adopted (its sequence restarts, so it cannot be
 * compared with the previous owner's); within one epoch only a higher
 * sequence advances, so stale duplicates and out-of-order events are ignored.
 * A legacy bare number carries no epoch and always fans out locally instead
 * of risking suppression by an unrelated counter.
 */
export function adoptOwnerWrite(stamp: OwnerStamp | unknown): void {
  if (isOwnerStamp(stamp)) {
    if (ownerEpoch !== stamp.epoch) {
      ownerEpoch = stamp.epoch;
      ownerSeq = stamp.seq;
      version += 1;
      fanOut();
    } else if (stamp.seq > ownerSeq) {
      ownerSeq = stamp.seq;
      version += 1;
      fanOut();
    }
    return;
  }
  if (typeof stamp === "number" && Number.isInteger(stamp)) {
    version += 1;
    fanOut();
    return;
  }
  notifyDomainWrite();
}

export function notifyDomainWrite(): void {
  version += 1;
  fanOut();
}

/**
 * Relay an owner stamp this tab received (the writing tab relays after its
 * response). The owner also announces directly, so followers learn of commits
 * even when the writer closes before its response arrives; both paths carry
 * the same stamp and the adoption above dedupes them.
 */
export function broadcastOwnerWrite(stamp: OwnerStamp | number): void {
  try {
    if (isOwnerStamp(stamp)) {
      // `version` keeps pre-stamp tabs in sync; they adopt it numerically.
      ensureChannel()?.postMessage({
        type: "glypherie-domain-version",
        epoch: stamp.epoch,
        seq: stamp.seq,
        version: stamp.seq,
      });
    } else if (typeof stamp === "number" && Number.isInteger(stamp)) {
      ensureChannel()?.postMessage({ type: "glypherie-domain-version", version: stamp });
    }
  } catch {
    // Cross-tab broadcast is best-effort; the local adopt already applied.
  }
}

export function subscribeDomain(listener: Listener): () => void {
  ensureChannel();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Test seam: release the broadcast channel so the process can exit. */
export function closeDomainChannelForTests(): void {
  listeners.clear();
  if (channel) {
    try {
      channel.close();
    } catch {
      // Best-effort teardown only.
    }
    channel = null;
  }
}

export function getDomainVersion(): number {
  ensureChannel();
  return version;
}

/** Test seam: reset counters between isolated runs. */
export function resetDomainVersionForTests(): void {
  version = 0;
  ownerEpoch = null;
  ownerSeq = 0;
}
