import type { FontMetadata } from "./storage.ts";

export type FontLoadState = "idle" | "loading" | "ready" | "error";

export interface FontLoadStatus {
  state: FontLoadState;
  error: string;
}

// Narrow inspection/loading surface consumed from the renderer service. The
// readiness owner never creates or terminates workers; RendererProvider keeps
// owning the single worker lifetime and session.
export interface ReadinessService {
  inspect(bytes: ArrayBuffer): Promise<FontMetadata>;
  load(id: string, bytes: ArrayBuffer): Promise<void>;
  unload(id: string): Promise<void>;
}

export interface ReadinessFontData {
  bytes: ArrayBuffer;
  hints: boolean | null | undefined;
}

export interface ReadinessPorts {
  readFont: (id: string) => Promise<ReadinessFontData | null>;
  updateHints: (id: string, metadata: FontMetadata) => Promise<void>;
  service: ReadinessService | null;
}

// Explicit capability preview/variant canvases consume. Loaded fonts are
// exposed as an immutable snapshot so memoized consumers observe every
// admission, completion, failure and invalidation through subscription.
export interface RendererFontReadiness {
  rendererAvailable: boolean | null;
  loadedIds: ReadonlySet<string>;
  ensureLoaded: (ids: string | readonly string[]) => void;
  loadStatus: (id: string) => FontLoadStatus;
  invalidateFont: (id: string) => void;
  removeFont: (id: string, removeData: () => Promise<void>) => Promise<void>;
}

export interface ReadinessSnapshot {
  loadedIds: ReadonlySet<string>;
  statuses: Record<string, FontLoadStatus>;
}

const idleStatus: FontLoadStatus = { state: "idle", error: "" };

// One cache owner for renderer-side font readiness. Framework-free: no React
// and no domain bindings, so the guard semantics (admission visibility,
// session replacement during a held load, deletion during a held load,
// unmount) are directly executable and testable. Late completions are
// suppressed by a per-font generation checked together with the session and
// mount epoch after every await.
export class RendererFontReadinessStore {
  private ports: ReadinessPorts;
  private session = 0;
  private epoch = 0;
  private loaded = new Set<string>();
  private loading = new Set<string>();
  private failed = new Map<string, string>();
  private statuses: Record<string, FontLoadStatus> = {};
  private generation: Record<string, number> = {};
  // Fonts whose domain deletion is still in flight own their id: no new load
  // may re-admit them until the deletion finishes.
  private deletions = new Map<string, { service: ReadinessService | null; session: number }>();
  private listeners = new Set<() => void>();
  // One cached immutable snapshot: useSyncExternalStore requires a stable
  // identity while nothing changed, so it is rebuilt only on emission.
  private cached: ReadinessSnapshot = { loadedIds: new Set<string>(), statuses: {} };

  constructor(ports: ReadinessPorts) {
    this.ports = ports;
  }

  subscribe = (notify: () => void): (() => void) => {
    this.listeners.add(notify);
    return () => {
      this.listeners.delete(notify);
    };
  };

  getSnapshot = (): ReadinessSnapshot => this.cached;

  private emit(): void {
    this.cached = { loadedIds: new Set(this.loaded), statuses: { ...this.statuses } };
    for (const notify of [...this.listeners]) notify();
  }

  updateService(service: ReadinessService | null): void {
    this.ports.service = service;
  }

  loadStatus(id: string): FontLoadStatus {
    return this.statuses[id] ?? idleStatus;
  }

  // A recreated worker starts with an empty worker-side cache, so readiness
  // cached for the previous session is dropped synchronously and in-flight
  // loads for it no longer complete.
  replaceSession(): void {
    this.session += 1;
    this.generation = {};
    this.loading = new Set<string>();
    this.failed = new Map<string, string>();
    this.loaded = new Set<string>();
    this.statuses = {};
    this.emit();
  }

  // Retire every in-flight operation: late completions from the retired mount
  // are dropped, and in-flight entries return to idle so a fresh mount
  // retries them through the normal admission path. Settled readiness stays.
  dispose(): void {
    this.epoch += 1;
    if (this.loading.size === 0) return;
    this.loading = new Set<string>();
    const next = { ...this.statuses };
    for (const [id, status] of Object.entries(next)) {
      if (status.state === "loading") delete next[id];
    }
    this.statuses = next;
    this.emit();
  }

  // Bump the per-font generation before a deletion can complete, so a late
  // old load cannot resurrect readiness for the removed font.
  invalidateFont(id: string): void {
    this.generation[id] = (this.generation[id] ?? 0) + 1;
    this.loading.delete(id);
    this.failed.delete(id);
    this.loaded.delete(id);
    if (this.statuses[id] !== undefined) {
      const next = { ...this.statuses };
      delete next[id];
      this.statuses = next;
    }
    this.emit();
  }

  // Deletion owns the font across the domain await: the originating
  // service/session identity is captured BEFORE the await, so a late old
  // deletion never unloads a newer session's cache, and no new load
  // re-admits the id while the deletion still owns it. On domain failure
  // the error propagates and the id is released, so the next ensureLoaded
  // honestly reloads it; nothing is silently resurrected.
  async removeFont(id: string, removeData: () => Promise<void>): Promise<void> {
    const owner = { service: this.ports.service, session: this.session };
    this.generation[id] = (this.generation[id] ?? 0) + 1;
    this.deletions.set(id, owner);
    this.loading.delete(id);
    this.failed.delete(id);
    this.loaded.delete(id);
    if (this.statuses[id] !== undefined) {
      const next = { ...this.statuses };
      delete next[id];
      this.statuses = next;
    }
    this.emit();
    try {
      await removeData();
    } finally {
      this.deletions.delete(id);
      // Unload only the originating worker while it is still current. After
      // a session switch the old worker is gone and the new session owns its
      // own cache, so unloading there would evict a live font behind a
      // cache that still claims it ready.
      if (owner.session === this.session && owner.service) {
        await owner.service.unload(id).catch(() => undefined);
      }
    }
  }

  ensureLoaded(ids: string | readonly string[], unavailable: boolean): void {
    const service = this.ports.service;
    if (unavailable || !service) return;
    const renderer = service;
    const session = this.session;
    const epoch = this.epoch;
    const targets = [...new Set(Array.isArray(ids) ? ids : [ids])].filter(
      (id) => !this.loaded.has(id) && !this.loading.has(id) && !this.failed.has(id) && !this.deletions.has(id),
    );
    if (targets.length === 0) return;
    for (const id of targets) {
      const generation = this.generation[id] ?? 0;
      const live = (): boolean =>
        this.epoch === epoch && this.session === session && (this.generation[id] ?? 0) === generation;
      this.loading.add(id);
      this.statuses = { ...this.statuses, [id]: { state: "loading", error: "" } };
      // Admission is emitted synchronously so subscribers observe loading
      // during a held load, not only its eventual completion.
      this.emit();
      const pending = this.ports.readFont(id);
      void pending.then(
        async (stored) => {
          try {
            if (!live()) return;
            if (!stored) throw new Error("Font data is missing from the library.");
            if (stored.hints === undefined) {
              // Buffers are copied before crossing to the worker so the
              // cached bytes stay owned here.
              const metadata = await renderer.inspect(stored.bytes.slice(0));
              if (!live()) return;
              await this.ports.updateHints(id, metadata);
              if (!live()) return;
            }
            await renderer.load(id, stored.bytes.slice(0));
            if (!live()) return;
            this.loaded.add(id);
            this.statuses = { ...this.statuses, [id]: { state: "ready", error: "" } };
            this.emit();
          } catch (error) {
            if (!live()) return;
            const message = error instanceof Error ? error.message : "Couldn’t load font.";
            this.failed.set(id, message);
            this.statuses = { ...this.statuses, [id]: { state: "error", error: message } };
            this.emit();
          } finally {
            if (live()) this.loading.delete(id);
          }
        },
        (error: unknown) => {
          if (!live()) return;
          const message = error instanceof Error ? error.message : "Couldn’t load font.";
          this.failed.set(id, message);
          this.statuses = { ...this.statuses, [id]: { state: "error", error: message } };
          this.loading.delete(id);
          this.emit();
        },
      );
    }
  }
}
