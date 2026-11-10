// Cohesive saved-document/edit-session owner for one scene composition.
//
// The session privately owns the latest accepted document, the serialized
// revisioned write queue, background-vs-blocking pending status, remote
// adoption/refusal against the UI's draft state, successful-only history and
// undo/redo, stale request/scene identity and conflict recovery. Consumers
// see a stable document/status/conflict snapshot plus meaningful intents;
// queue, revision, history and ref mechanics never leak into presentation.
//
// Framework-free and DOM-free: the React adapter (`useSceneSession.ts`)
// wires domain service functions and mirrors the snapshot. No dependency on
// FontLibrary, viewport preferences, renderer scheduling or JSX: drafts and
// typography stay with their UI owners and reach the session only through
// the single setDraftState channel and explicit intent arguments. View types
// arrive as type-only imports; the scenes service boundary stays intact.
import type {
  DomainOutputProfileView,
  DomainSceneView,
  DomainTextStyleView,
  SceneSnapshotInput,
} from "../../domain/types.js";

export interface SceneBundle {
  scene: DomainSceneView | null;
  styles: DomainTextStyleView[];
  profiles: DomainOutputProfileView[];
}

export type SceneIntent = (scene: DomainSceneView) => Promise<DomainSceneView>;

export interface SceneSubmitOptions {
  // Background placement persistence serializes through the same queue and
  // revision guards but leaves unrelated controls enabled while it catches
  // up; only undo/redo stay honestly disabled.
  background?: boolean;
  // Local edits checkpoint their pre-image; the label-creation step opts out
  // so initial typing completes the creation undo step.
  checkpoint?: boolean;
  // Synchronous UI handoff only after the current generation accepts a write,
  // before listeners can fetch and adopt over its newly opened draft.
  onAccepted?: () => void;
}

export interface SceneDraftState {
  // An open in-place draft (stage or list editor) survives remote updates
  // behind the banner until explicit resolution; it is never auto-replaced.
  hasOpenDraft: boolean;
  // Unresolved local edits (e.g. unsaved coverage) also refuse adoption.
  hasUnresolvedChanges: boolean;
}

export interface SceneSessionSnapshot {
  // undefined while the scene loads, null when the record is gone.
  document: DomainSceneView | null | undefined;
  styles: DomainTextStyleView[] | null;
  profiles: DomainOutputProfileView[] | null;
  // Counts adoptions (initial load, force reload, clean remote adoption) so
  // the UI can release selection and open drafts exactly when the accepted
  // document is replaced.
  adoptedAt: number;
  error: string;
  conflict: boolean;
  pendingRemote: DomainSceneView | null;
  // pending tracks every queued write; blocking only non-background ones.
  pending: boolean;
  blocking: boolean;
  // An in-place draft is open: selection/keyboard transitions own it, and
  // layer intents must not run until it settles.
  draftOpen: boolean;
  // Actionable undo/redo: stacks are non-empty and no write, draft or
  // conflict blocks the restore.
  canUndo: boolean;
  canRedo: boolean;
}

export interface SceneSessionDeps {
  loadBundle: (sceneId: string) => Promise<SceneBundle>;
  restore: (sceneId: string, revision: number, snapshot: SceneSnapshotInput) => Promise<DomainSceneView>;
  isConflict: (error: unknown) => boolean;
}

const HISTORY_LIMIT = 50;

function snapshotOf(target: DomainSceneView): SceneSnapshotInput {
  return {
    name: target.name,
    width: target.width,
    height: target.height,
    deviceId: target.deviceId,
    rotation: target.rotation ?? 0,
    outputProfileId: target.outputProfileId,
    exportCoverage: target.exportCoverage,
    // Id-free content: re-created placement ids from an earlier cycle never
    // confuse the match; duplicates stay stable through content order.
    placements: target.placements.map((placement) => ({
      text: placement.text,
      textStyleId: placement.textStyleId,
      fontId: placement.fontId,
      fontSize: placement.fontSize,
      width: placement.width,
      fontWeight: placement.fontWeight,
      x: placement.x,
      y: placement.y,
      order: placement.order,
      visible: placement.visible !== false,
    })),
  };
}

export class SceneDocumentSession {
  private readonly deps: SceneSessionDeps;
  private readonly listeners = new Set<() => void>();
  private document: DomainSceneView | null | undefined = undefined;
  private styles: DomainTextStyleView[] | null = null;
  private profiles: DomainOutputProfileView[] | null = null;
  private error = "";
  private conflict = false;
  private pendingRemote: DomainSceneView | null = null;
  private pendingCount = 0;
  private blockingCount = 0;
  private past: DomainSceneView[] = [];
  private future: DomainSceneView[] = [];
  private draft: SceneDraftState = { hasOpenDraft: false, hasUnresolvedChanges: false };
  private queue: Promise<void> = Promise.resolve();
  private sceneId = "";
  private epoch = 0;
  private fetchSeq = 0;
  private adoptedAt = 0;
  private revision = 0;
  // Creation lease owner, by generation epoch. A gated creation in the old
  // scene never blocks the new scene, and a late old-scene finalizer never
  // clears a newer claim. Not part of the snapshot: admission only.
  private creationOwner: number | null = null;

  constructor(deps: SceneSessionDeps) {
    this.deps = deps;
  }

  // Monotonic subscription version for useSyncExternalStore: the snapshot
  // object itself is rebuilt on every read, so consumers key off this.
  get version(): number {
    return this.revision;
  }

  get snapshot(): SceneSessionSnapshot {
    const blocked = this.pendingCount > 0 || this.draft.hasOpenDraft || this.conflict;
    return {
      document: this.document,
      styles: this.styles,
      profiles: this.profiles,
      adoptedAt: this.adoptedAt,
      error: this.error,
      conflict: this.conflict,
      pendingRemote: this.pendingRemote,
      pending: this.pendingCount > 0,
      blocking: this.blockingCount > 0,
      draftOpen: this.draft.hasOpenDraft,
      canUndo: this.past.length > 0 && !blocked,
      canRedo: this.future.length > 0 && !blocked,
    };
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private emit(): void {
    this.revision += 1;
    for (const listener of this.listeners) listener();
  }

  // The single informed channel for draft state: coverage dirtiness and open
  // in-place drafts refuse remote adoption. No competing boolean mirrors.
  setDraftState(draft: SceneDraftState): void {
    if (
      this.draft.hasOpenDraft === draft.hasOpenDraft &&
      this.draft.hasUnresolvedChanges === draft.hasUnresolvedChanges
    )
      return;
    this.draft = { ...draft };
    this.emit();
  }

  // Route/scene switch: never publishes a stale async result, never leaks
  // history or queued status into the new scene. The queue, counters and
  // draft view are generation-owned: the switch detaches them coherently, so
  // the new scene never waits behind a gated or hung old write, and an old
  // task settling late decrements nothing and publishes nothing.
  openScene(sceneId: string): Promise<void> {
    this.sceneId = sceneId;
    this.epoch += 1;
    this.creationOwner = null;
    this.queue = Promise.resolve();
    this.pendingCount = 0;
    this.blockingCount = 0;
    this.draft = { hasOpenDraft: false, hasUnresolvedChanges: false };
    this.document = undefined;
    this.styles = null;
    this.profiles = null;
    this.error = "";
    this.conflict = false;
    this.pendingRemote = null;
    this.past = [];
    this.future = [];
    this.emit();
    return this.fetch(sceneId, this.epoch, {});
  }

  reload(options?: { force?: boolean }): Promise<void> {
    if (!this.sceneId) return Promise.resolve();
    return this.fetch(this.sceneId, this.epoch, options ?? {});
  }

  // Explicit remote discard: the conflict banner's reload adopts the saved
  // revision and drops stale local history.
  discardRemote(): Promise<void> {
    return this.reload({ force: true });
  }

  private fetch(sceneId: string, epoch: number, options: { force?: boolean }): Promise<void> {
    const seq = (this.fetchSeq += 1);
    return this.deps
      .loadBundle(sceneId)
      .then((bundle) => {
        if (epoch !== this.epoch || this.sceneId !== sceneId) return;
        const base = this.document;
        // A superseded force reload still adopts when its data is not older
        // than the base: an interleaved non-force fetch racing the explicit
        // discard must not silently drop it.
        const forceFresh =
          options.force === true &&
          bundle.scene !== null &&
          bundle.scene !== undefined &&
          base !== null &&
          base !== undefined
            ? bundle.scene.revision >= base.revision
            : false;
        if (seq !== this.fetchSeq && !forceFresh) return;
        this.styles = bundle.styles;
        this.profiles = bundle.profiles;
        if (bundle.scene === null || bundle.scene === undefined) {
          this.document = bundle.scene ?? null;
          this.pendingRemote = null;
          this.emit();
          return;
        }
        if (options.force === true || base === undefined || base === null) {
          this.adopt(bundle.scene, bundle.styles, bundle.profiles);
          return;
        }
        if (bundle.scene.revision === base.revision) {
          this.document = bundle.scene;
          this.emit();
          return;
        }
        if (bundle.scene.revision < base.revision) return;
        if (!this.draft.hasOpenDraft && !this.draft.hasUnresolvedChanges) {
          this.adopt(bundle.scene, bundle.styles, bundle.profiles);
        } else {
          this.pendingRemote = bundle.scene;
          this.conflict = true;
          this.emit();
        }
      })
      .catch((failure: unknown) => {
        if (epoch !== this.epoch || this.sceneId !== sceneId || seq !== this.fetchSeq) return;
        this.error = failure instanceof Error ? failure.message : "Couldn’t load the composition.";
        this.emit();
      });
  }

  private adopt(scene: DomainSceneView, styles: DomainTextStyleView[], profiles: DomainOutputProfileView[]): void {
    this.document = scene;
    this.styles = styles;
    this.profiles = profiles;
    this.pendingRemote = null;
    this.conflict = false;
    this.error = "";
    this.adoptedAt += 1;
    // Adopting remote state drops stale local history: past snapshots predate
    // the adopted revision.
    this.past = [];
    this.future = [];
    this.emit();
  }

  // Serial queue: every mutation waits for the previous one, so fast nudges
  // and blur-save races resolve against the latest scene at execution time
  // instead of racing on a stale revision. Relative moves accumulate; a
  // queued intent from a previous scene never runs against the new one.
  //
  // Creation admission is generation-scoped: tryClaimCreation hands the
  // current epoch a lease, and releaseCreation honors only the owning epoch,
  // so a late old-scene finalizer never clears a newer scene's claim.
  tryClaimCreation(): number | null {
    if (this.creationOwner !== null) return null;
    this.creationOwner = this.epoch;
    return this.epoch;
  }

  releaseCreation(token: number): void {
    if (this.creationOwner === token) this.creationOwner = null;
  }

  // Private execution seam and test control: product code submits meaningful
  // edit intents through the scene-intents controller, never raw callbacks.
  submit(intent: SceneIntent, options?: SceneSubmitOptions): Promise<boolean> {
    const epoch = this.epoch;
    this.pendingCount += 1;
    if (!options?.background) this.blockingCount += 1;
    this.emit();
    const task = this.queue.then(() => this.execute(intent, options, epoch)).then((next) => next !== null);
    this.queue = task.then(
      () => undefined,
      () => undefined,
    );
    return task.finally(() => {
      // A task from a previous scene generation settles detached: the
      // switch already reset its counters, so decrementing here would drive
      // the new generation negative and emit stale status into it.
      if (epoch !== this.epoch) return;
      this.pendingCount -= 1;
      if (!options?.background) this.blockingCount -= 1;
      this.emit();
    });
  }

  private async execute(
    intent: SceneIntent,
    options: SceneSubmitOptions | undefined,
    epoch: number,
  ): Promise<DomainSceneView | null> {
    if (epoch !== this.epoch) return null;
    const base = this.document;
    if (!base) return null;
    try {
      const next = await intent(base);
      if (epoch !== this.epoch) return null;
      this.document = next;
      this.pendingRemote = null;
      this.conflict = false;
      this.error = "";
      // Only successful commands checkpoint, and only when the revision moved:
      // no-op edits avoid unwanted checkpoints, failed commands leave past
      // and future intact.
      if (next.revision !== base.revision && options?.checkpoint !== false) {
        this.past = [...this.past.slice(-(HISTORY_LIMIT - 1)), base];
        this.future = [];
      }
      options?.onAccepted?.();
      this.emit();
      return next;
    } catch (failure) {
      if (epoch !== this.epoch) return null;
      if (this.deps.isConflict(failure)) {
        this.conflict = true;
        this.emit();
        void this.fetch(this.sceneId, this.epoch, {});
      } else {
        this.error = failure instanceof Error ? failure.message : "Couldn’t save the composition.";
        this.emit();
      }
      return null;
    }
  }

  // Undo/redo restore through one atomic revision-guarded domain command
  // carrying an id-free content snapshot. Restores never create a normal
  // edit checkpoint: the stacks transition exactly once below, only after a
  // successful restore. A rejection leaves the scene and both stacks
  // untouched.
  private restoreSnapshot(target: DomainSceneView): Promise<boolean> {
    const base = this.document;
    if (!base || base.id !== target.id) return Promise.resolve(false);
    return this.submit(async (scene) => this.deps.restore(scene.id, scene.revision, snapshotOf(target)), {
      // Restores always block, but checkpoint nothing: undo/redo move the
      // existing entries instead of recording the pre-image as a new edit.
      checkpoint: false,
    });
  }

  undo(): Promise<boolean> {
    const base = this.document;
    if (!base || this.pendingCount > 0 || this.draft.hasOpenDraft || this.conflict) return Promise.resolve(false);
    const candidate = this.past.length > 0 ? this.past[this.past.length - 1]! : null;
    if (!candidate || candidate.id !== base.id) {
      if (candidate && candidate.id !== base.id) {
        this.past = [];
        this.emit();
      }
      return Promise.resolve(false);
    }
    return this.restoreSnapshot(candidate).then((ok) => {
      if (!ok) return false;
      this.past = this.past.slice(0, -1);
      this.future = [...this.future.slice(-(HISTORY_LIMIT - 1)), base];
      this.emit();
      return true;
    });
  }

  redo(): Promise<boolean> {
    const base = this.document;
    if (!base || this.pendingCount > 0 || this.draft.hasOpenDraft || this.conflict) return Promise.resolve(false);
    const candidate = this.future.length > 0 ? this.future[this.future.length - 1]! : null;
    if (!candidate || candidate.id !== base.id) {
      if (candidate && candidate.id !== base.id) {
        this.future = [];
        this.emit();
      }
      return Promise.resolve(false);
    }
    return this.restoreSnapshot(candidate).then((ok) => {
      if (!ok) return false;
      this.future = this.future.slice(0, -1);
      this.past = [...this.past.slice(-(HISTORY_LIMIT - 1)), base];
      this.emit();
      return true;
    });
  }
}
