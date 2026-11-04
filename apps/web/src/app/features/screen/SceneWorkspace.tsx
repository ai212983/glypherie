// Scene workspace: one saved composition on its screen with freely
// positioned WASM-rendered labels. Device association persists through the
// domain scene (deviceId plus exact geometry); an explicit custom choice
// (null device) always stays a custom screen with its own size, even when
// the dimensions match a catalog device, never silently resized. Label
// positions are native device pixels; moves keep those coordinates while
// clipping surfaces through the stage bounds.
import * as React from "react";
import { ArrowLeft, Plus, Redo2, Undo2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { TooltipHint } from "../../../components/TooltipHint";
import { linearCurve, type GrayCurve } from "../grayscale/response-curve.js";
import { useDisplayPreferences } from "../../shell/DisplayPreferences.js";
import { profileBits } from "../../renderer/render-spec.js";
import type { RGBA } from "../../renderer/renderer-types.js";
import type { FontLibrary } from "../../fonts/useFontLibrary.js";
import type { VariantSettings } from "../../variants/model.js";
import { DEFAULT_CHARACTER_COVERAGE, type CharacterCoverage } from "../../domain/coverage.js";
import { CoverageControl } from "../preview/CoverageControl.js";
import type { FontCanvasDiagnostics } from "../../renderer/FontCanvas.js";
import { DEVICE_CATALOG } from "../../devices/catalog.js";
import { DeviceShell } from "../../devices/DeviceShell.js";
import { referenceSizeCssScale } from "../../renderer/display-scaling.js";
import { sceneLabelPalette, scenePaperCss } from "../scenes/scene-palette.js";
import { SceneExportPanel } from "../scenes/SceneExportPanel.js";
import { isConflict } from "../scenes/conflict.js";
import type {
  DomainOutputProfileView,
  DomainSceneView,
  DomainTextStyleView,
} from "../scenes/service.js";
import {
  addSceneLabel,
  getScene,
  listOutputProfiles,
  listTextStyles,
  removeSceneLabel,
  resolveTextStyle,
  restoreSceneSnapshot as restoreSceneDomain,
  subscribeDomain,
  updateScene,
  updateSceneLabel,
} from "../scenes/service.js";
import { resolveSceneScreen } from "./device-resolution.js";
import { SceneStage, type StagePaint } from "./SceneStage.js";
import { LabelInspector } from "./LabelInspector.js";
import { useSceneHistory } from "./useSceneHistory.js";

function domainError(error: unknown, fallback: string): { message: string; conflict: boolean } {
  if (isConflict(error)) return { message: "The composition changed in another tab; it was reloaded.", conflict: true };
  return { message: error instanceof Error ? error.message : fallback, conflict: false };
}

export function SceneWorkspace({ sceneId, library, sizePercent, onBack }: {
  sceneId: string;
  library: FontLibrary;
  sizePercent: number;
  onBack: () => void;
}): React.JSX.Element {
  const [saved, setSaved] = React.useState<DomainSceneView | null | undefined>(undefined);
  const [styles, setStyles] = React.useState<DomainTextStyleView[] | null>(null);
  const [profiles, setProfiles] = React.useState<DomainOutputProfileView[] | null>(null);
  const [error, setError] = React.useState("");
  const [conflict, setConflict] = React.useState(false);
  const [pendingRemote, setPendingRemote] = React.useState<DomainSceneView | null>(null);
  const [previewStatus, setPreviewStatus] = React.useState("");
  const [renderError, setRenderError] = React.useState("");
  const [name, setName] = React.useState("");
  const [coverage, setCoverage] = React.useState<CharacterCoverage>(DEFAULT_CHARACTER_COVERAGE);
  const [newLabel, setNewLabel] = React.useState({ text: "", styleId: "" });
  const [resolved, setResolved] = React.useState<Record<string, { fontId: string; settings: VariantSettings }>>({});
  const [resolveDone, setResolveDone] = React.useState(false);
  // saving gates unrelated controls for blocking mutations only. pending
  // tracks every queued write (including background placement persistence)
  // so undo/redo stay honestly disabled while a write is in flight.
  const [saving, setSaving] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const savedRef = React.useRef(saved);
  const editingIdRef = React.useRef(editingId);
  const conflictRef = React.useRef(conflict);
  const sceneIdRef = React.useRef(sceneId);
  const fetchSeqRef = React.useRef(0);
  // Serial mutation queue: fast nudges and blur-save races enqueue against
  // the latest saved base instead of issuing stale-revision commands.
  // pendingRef tracks the depth synchronously so key repeats are never lost.
  const queueRef = React.useRef<Promise<void>>(Promise.resolve());
  const pendingRef = React.useRef(0);
  const history = useSceneHistory();
  const { canvas: { palette: appearance, inverse } } = useDisplayPreferences();

  React.useEffect(() => {
    savedRef.current = saved;
  });
  editingIdRef.current = editingId;
  conflictRef.current = conflict;

  const draftsClean = React.useCallback((base: DomainSceneView): boolean => {
    if (name !== base.name) return false;
    if (JSON.stringify(coverage) !== JSON.stringify(base.exportCoverage)) return false;
    // An open in-place draft must survive a remote update behind the banner.
    if (editingIdRef.current !== null) return false;
    return true;
  }, [name, coverage]);

  const adopt = React.useCallback((
    scene: DomainSceneView,
    nextStyles: DomainTextStyleView[],
    nextProfiles: DomainOutputProfileView[],
  ) => {
    savedRef.current = scene;
    setSaved(scene);
    setStyles(nextStyles);
    setProfiles(nextProfiles);
    setName(scene.name);
    setCoverage(scene.exportCoverage);
    setNewLabel((current) => ({ ...current, styleId: current.styleId || nextStyles[0]?.id || "" }));
    setSelectedId((current) => (current && scene.placements.some((placement) => placement.id === current) ? current : null));
    setEditingId(null);
    setPendingRemote(null);
    setConflict(false);
    setError("");
    // A remote adoption (or an explicit discard through force reload) drops
    // stale local history: past snapshots predate the adopted revision.
    history.reset();
  }, [history]);

  const reload = React.useCallback(async (options?: { force?: boolean }) => {
    const seq = (fetchSeqRef.current += 1);
    try {
      const [scene, nextStyles, nextProfiles] = await Promise.all([
        getScene(sceneId), listTextStyles(), listOutputProfiles(),
      ]);
      if (sceneIdRef.current !== sceneId) return;
      const base = savedRef.current;
      // A superseded force reload still adopts when its data is not older
      // than the current base: an interleaved non-force fetch (a blur commit
      // racing the reload click) must not silently drop the explicit discard.
      const supersededForceFresh = options?.force === true
        && (!base || (scene !== undefined && scene.revision >= base.revision));
      if (fetchSeqRef.current !== seq && !supersededForceFresh) return;
      setStyles(nextStyles);
      setProfiles(nextProfiles);
      if (!scene) {
        savedRef.current = null;
        setSaved(null);
        setPendingRemote(null);
        return;
      }
      if (options?.force || !base) {
        adopt(scene, nextStyles, nextProfiles);
        return;
      }
      if (scene.revision === base.revision) {
        savedRef.current = scene;
        setSaved(scene);
        return;
      }
      if (scene.revision < base.revision) return;
      if (draftsClean(base)) {
        adopt(scene, nextStyles, nextProfiles);
      } else {
        setPendingRemote(scene);
        setConflict(true);
      }
    } catch (failure) {
      if (sceneIdRef.current !== sceneId || fetchSeqRef.current !== seq) return;
      setError(failure instanceof Error ? failure.message : "Couldn’t load the composition.");
    }
  }, [sceneId, adopt, draftsClean]);

  const reloadRef = React.useRef(reload);
  reloadRef.current = reload;

  React.useEffect(() => {
    sceneIdRef.current = sceneId;
    savedRef.current = undefined;
    setSaved(undefined);
    setPendingRemote(null);
    setConflict(false);
    setResolveDone(false);
    setResolved({});
    setSelectedId(null);
    setEditingId(null);
    history.reset();
    void reloadRef.current({ force: true });
    return subscribeDomain(() => { void reloadRef.current(); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneId]);

  // Single-flight executor: runs against the latest saved base and applies
  // the result. Saving state is owned by the queue below, not by this step.
  const runCommands = React.useCallback(async (
    run: (scene: DomainSceneView) => Promise<DomainSceneView>,
  ): Promise<DomainSceneView | null> => {
    const base = savedRef.current;
    if (!base) return null;
    setError("");
    try {
      const next = await run(base);
      savedRef.current = next;
      setSaved(next);
      setSelectedId((current) => (current && next.placements.some((placement) => placement.id === current) ? current : null));
      setPendingRemote(null);
      setConflict(false);
      return next;
    } catch (failure) {
      if (isConflict(failure)) {
        setConflict(true);
        void reloadRef.current();
      } else {
        setError(failure instanceof Error ? failure.message : "Couldn’t save the composition.");
      }
      return null;
    }
  }, []);

  // Serial queue: every mutation waits for the previous one, so fast nudges
  // and blur-save races issue against the fresh revision instead of racing
  // on a stale one. The depth counter moves synchronously with the event, so
  // rapid key repeats enqueue instead of being dropped. Background placement
  // persistence serializes through the same queue and revision guards but
  // leaves unrelated controls enabled while it catches up: the pending UI
  // stays usable while the authoritative write completes
  // (https://react.dev/reference/react/useOptimistic).
  const runQueued = React.useCallback(async (
    run: (scene: DomainSceneView) => Promise<DomainSceneView>,
    options?: { background?: boolean },
  ): Promise<boolean> => {
    pendingRef.current += 1;
    setPending(true);
    if (!options?.background) setSaving(true);
    const task = queueRef.current.then(() => runCommands(run)).then((next) => next !== null);
    queueRef.current = task.then(() => undefined, () => undefined);
    try {
      return await task;
    } finally {
      pendingRef.current -= 1;
      if (pendingRef.current === 0) {
        setPending(false);
        setSaving(false);
      }
    }
  }, [runCommands]);

  // Local edits checkpoint the pre-image seen when the queued operation
  // executes. Only successful commands checkpoint; failed commands leave
  // past and future intact.
  const mutate = React.useCallback(async (
    run: (scene: DomainSceneView) => Promise<DomainSceneView>,
    options?: { background?: boolean },
  ): Promise<boolean> => {
    return runQueued(async (scene) => {
      const before = scene;
      const next = await run(scene);
      if (next.revision !== before.revision) history.checkpoint(before);
      return next;
    }, options);
  }, [history, runQueued]);

  // Undo/redo restore through one atomic revision-guarded domain command
  // carrying an id-free content snapshot, so re-created placement ids from an
  // earlier cycle never confuse the match. A rejection leaves the scene and
  // both history stacks untouched.
  const restoreSnapshot = React.useCallback(async (target: DomainSceneView): Promise<boolean> => {
    const base = savedRef.current;
    if (!base || base.id !== target.id) return false;
    return runQueued(async (scene) => {
      const restored = await restoreSceneDomain(scene.id, scene.revision, {
        name: target.name,
        width: target.width,
        height: target.height,
        deviceId: target.deviceId,
        outputProfileId: target.outputProfileId,
        exportCoverage: target.exportCoverage,
        placements: target.placements.map((placement) => ({
          text: placement.text,
          textStyleId: placement.textStyleId,
          x: placement.x,
          y: placement.y,
          order: placement.order,
        })),
      });
      // Id-free restores may reuse a placement id for different content.
      // Release selection and keyboard ownership before publishing it.
      const focused = document.activeElement;
      if (focused instanceof HTMLElement && focused.hasAttribute("data-scene-label-frame")
        && focused.closest("[data-screen-workspace]")?.getAttribute("data-screen-workspace") === scene.id) {
        focused.blur();
      }
      setSelectedId(null);
      return restored;
    });
  }, [runQueued]);

  // Undo/redo stay disabled while an in-place draft is open, while a
  // conflict banner waits, or while a mutation is still queued: the stacks
  // commit only after a successful restore.
  const onUndo = React.useCallback(async (): Promise<void> => {
    const base = savedRef.current;
    if (!base || pendingRef.current > 0 || editingIdRef.current !== null || conflictRef.current) return;
    const target = history.peekUndo(base.id);
    if (!target) return;
    setEditingId(null);
    const ok = await restoreSnapshot(target);
    if (ok) {
      history.takeUndo(base.id);
      history.stashForRedo(base);
    }
  }, [history, restoreSnapshot]);

  const onRedo = React.useCallback(async (): Promise<void> => {
    const base = savedRef.current;
    if (!base || pendingRef.current > 0 || editingIdRef.current !== null || conflictRef.current) return;
    const target = history.peekRedo(base.id);
    if (!target) return;
    setEditingId(null);
    const ok = await restoreSnapshot(target);
    if (ok) {
      history.takeRedo(base.id);
      history.stashForUndo(base);
    }
  }, [history, restoreSnapshot]);

  // Undo/redo keyboard: never steal keys from text fields or an open draft
  // (the native textarea keeps its own edit history).
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (!event.metaKey && !event.ctrlKey) return;
      if (event.isComposing) return;
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)) return;
      if (editingIdRef.current !== null || conflictRef.current || pendingRef.current > 0) return;
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey) {
        event.preventDefault();
        void onUndo();
      } else if (key === "y" || (key === "z" && event.shiftKey)) {
        event.preventDefault();
        void onRedo();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onUndo, onRedo]);

  const styleIds = React.useMemo(
    () => [...new Set((saved?.placements ?? []).map((placement) => placement.textStyleId))],
    [saved],
  );
  const styleNameById = React.useMemo(
    () => new Map((styles ?? []).map((style) => [style.id, style.name])),
    [styles],
  );
  const fontLoadStatus = library.loadStatus;
  // Each style resolves independently: one broken style keeps its failed
  // label while successful previews stay. Resolutions merge over the
  // previous set and never clear it: every committed edit bumps the scene
  // revision, and blanking the set on each bump would unmount every painted
  // label, drop focus and discard layout state. Entries for styles that left
  // the scene are pruned on completion instead.
  React.useEffect(() => {
    if (!saved || styleIds.length === 0) {
      setResolved({});
      setResolveDone(true);
      if (!saved) setPreviewStatus("");
      return;
    }
    const sceneKey = saved.id;
    const profileId = saved.outputProfileId;
    let live = true;
    void (async () => {
      const settled = await Promise.all(styleIds.map(async (styleId): Promise<{
        styleId: string;
        view?: { fontId: string; settings: VariantSettings };
        error?: unknown;
      }> => {
        try {
          const view = await resolveTextStyle(styleId, profileId);
          return { styleId, view: { fontId: view.fontId, settings: view.settings } };
        } catch (error) {
          return { styleId, error };
        }
      }));
      if (!live || sceneIdRef.current !== sceneId) return;
      const base = savedRef.current;
      if (!base || base.id !== sceneKey || base.outputProfileId !== profileId) return;
      const currentIds = new Set(base.placements.map((placement) => placement.textStyleId));
      const failures: string[] = [];
      const fresh: Record<string, { fontId: string; settings: VariantSettings }> = {};
      for (const entry of settled) {
        if (!currentIds.has(entry.styleId)) continue;
        if (entry.view !== undefined) {
          fresh[entry.styleId] = { fontId: entry.view.fontId, settings: entry.view.settings };
        } else {
          failures.push(styleNameById.get(entry.styleId) ?? entry.styleId);
        }
      }
      setResolved((current) => {
        const merged: Record<string, { fontId: string; settings: VariantSettings }> = {};
        for (const styleId of currentIds) {
          if (fresh[styleId] !== undefined) merged[styleId] = fresh[styleId]!;
          else if (current[styleId] !== undefined) merged[styleId] = current[styleId]!;
        }
        return merged;
      });
      setResolveDone(true);
      const fontProblems: string[] = [];
      for (const styleId of currentIds) {
        const fontId = fresh[styleId]?.fontId;
        if (!fontId) continue;
        const status = fontLoadStatus(fontId);
        if (status.state === "error") {
          fontProblems.push(`${styleNameById.get(styleId) ?? styleId}: ${status.error}`);
        }
      }
      const parts: string[] = [];
      if (failures.length > 0) parts.push(`Couldn’t resolve ${failures.join(", ")}.`);
      parts.push(...fontProblems);
      setPreviewStatus(parts.join(" "));
    })();
    return () => { live = false; };
  }, [saved, styleIds, styleNameById, sceneId, fontLoadStatus]);

  const paintFonts = React.useMemo(
    () => [...new Set(Object.values(resolved).map((entry) => entry.fontId))],
    [resolved],
  );
  const ensureFontsLoaded = library.ensureLoaded;
  React.useEffect(() => {
    ensureFontsLoaded(paintFonts);
  }, [ensureFontsLoaded, paintFonts]);

  const profileCurve = profiles?.find((profile) => profile.id === saved?.outputProfileId)?.curve;

  const paints = React.useMemo((): Map<string, StagePaint> => {
    const map = new Map<string, StagePaint>();
    if (!saved) return map;
    for (const placement of saved.placements) {
      const entry = resolved[placement.textStyleId];
      if (!entry) continue;
      const effective: GrayCurve = profileCurve?.length === 1 << profileBits(entry.settings.profile)
        ? profileCurve
        : linearCurve(1 << profileBits(entry.settings.profile));
      map.set(placement.textStyleId, {
        fontId: entry.fontId,
        settings: entry.settings,
        ready: library.loadedIds.has(entry.fontId),
        palette: sceneLabelPalette(effective, appearance, inverse),
      });
    }
    return map;
  }, [saved, resolved, profileCurve, library.loadedIds, appearance, inverse]);

  // Position-only patches persist in the background like drag releases;
  // style and order changes stay blocking.
  const commitLabelPatch = React.useCallback(async (
    placementId: string,
    patch: { text?: string; textStyleId?: string; x?: number; y?: number; order?: number },
  ): Promise<boolean> => {
    const background = patch.textStyleId === undefined && patch.order === undefined
      && (patch.x !== undefined || patch.y !== undefined);
    return mutate(
      (scene) => updateSceneLabel(scene.id, placementId, patch, scene.revision),
      background ? { background: true } : undefined,
    );
  }, [mutate]);

  // Blur-save and inspector edits enqueue too: each resolves against the
  // latest saved base when it executes, so concurrent edits cannot issue
  // against the same stale revision.
  const commitText = React.useCallback(async (placementId: string, text: string): Promise<boolean> => {
    const ok = await mutate(async (scene) => {
      const placement = scene.placements.find((candidate) => candidate.id === placementId);
      if (!placement) {
        setEditingId(null);
        return scene;
      }
      if (placement.text === text) {
        setEditingId(null);
        return scene;
      }
      return updateSceneLabel(scene.id, placementId, { text }, scene.revision);
    });
    // A conflict keeps the draft open for recovery instead of discarding it.
    if (ok) setEditingId(null);
    return ok;
  }, [mutate]);

  // Returns the queued revisioned outcome so the stage holds its released
  // preview until the saved coordinates render, rolling back only on
  // rejection. Undo checkpoints, conflict recovery and the serial queue are
  // unchanged; the write persists in the background so the release never
  // disables unrelated controls.
  const commitMove = React.useCallback((placementId: string, x: number, y: number): Promise<boolean> => {
    return mutate(async (scene) => {
      const placement = scene.placements.find((candidate) => candidate.id === placementId);
      if (!placement || (placement.x === x && placement.y === y)) return scene;
      return updateSceneLabel(scene.id, placementId, { x, y }, scene.revision);
    }, { background: true });
  }, [mutate]);

  const duplicateLabel = React.useCallback(async (placementId: string): Promise<void> => {
    await mutate(async (scene) => {
      const placement = scene.placements.find((candidate) => candidate.id === placementId);
      if (!placement) return scene;
      const next = await addSceneLabel(scene.id, {
        text: placement.text,
        textStyleId: placement.textStyleId,
        x: placement.x + 8,
        y: placement.y + 8,
      }, scene.revision);
      const added = next.placements.find((candidate) => !scene.placements.some((before) => before.id === candidate.id));
      if (added) setSelectedId(added.id);
      return next;
    });
  }, [mutate]);

  const deleteLabel = React.useCallback(async (placementId: string): Promise<void> => {
    const ok = await mutate(async (scene) => {
      if (!scene.placements.some((candidate) => candidate.id === placementId)) return scene;
      return removeSceneLabel(scene.id, placementId, scene.revision);
    });
    if (ok) {
      setSelectedId((current) => (current === placementId ? null : current));
      setEditingId((current) => (current === placementId ? null : current));
    }
  }, [mutate]);

  // Relative moves compute from the latest saved base when the queued
  // operation executes, so rapid key repeats accumulate instead of replaying
  // one stale coordinate.
  const nudgeLabel = React.useCallback((placementId: string, dx: number, dy: number): void => {
    void mutate(async (scene) => {
      const placement = scene.placements.find((candidate) => candidate.id === placementId);
      if (!placement) return scene;
      return updateSceneLabel(scene.id, placementId, { x: placement.x + dx, y: placement.y + dy }, scene.revision);
    }, { background: true });
  }, [mutate]);

  const addLabel = React.useCallback(async (): Promise<void> => {
    if (!newLabel.text.trim()) {
      setError("Label text must be non-empty.");
      return;
    }
    if (!newLabel.styleId) {
      setError("Choose a text style for the label.");
      return;
    }
    const styleId = newLabel.styleId;
    const text = newLabel.text;
    const ok = await mutate(async (scene) => {
      const next = await addSceneLabel(scene.id, { text, textStyleId: styleId, x: 8, y: 8 }, scene.revision);
      const added = next.placements.find((candidate) => !scene.placements.some((before) => before.id === candidate.id));
      if (added) setSelectedId(added.id);
      return next;
    });
    if (ok) {
      setNewLabel((current) => ({ ...current, text: "" }));
    }
  }, [mutate, newLabel]);

  const changeDevice = React.useCallback((deviceId: string): void => {
    const base = savedRef.current;
    if (!base) return;
    if (deviceId === "custom") {
      if (base.deviceId !== null) void mutate((scene) => updateScene(scene.id, { deviceId: null }, scene.revision));
      return;
    }
    const device = DEVICE_CATALOG.devices.find((entry) => entry.id === deviceId);
    if (!device) return;
    // Device changes preserve native label coordinates; labels outside the
    // new frame keep their positions and surface clipping instead of being
    // rescaled or moved.
    void mutate((scene) => updateScene(scene.id, {
      deviceId: device.id, width: device.widthPx, height: device.heightPx,
    }, scene.revision));
  }, [mutate]);

  const saveName = React.useCallback((): void => {
    const base = savedRef.current;
    if (!base || !name.trim() || name === base.name) return;
    void mutate((scene) => updateScene(scene.id, { name: name.trim() }, scene.revision));
  }, [mutate, name]);

  const saveCoverage = React.useCallback((): void => {
    void mutate((scene) => updateScene(scene.id, { exportCoverage: coverage }, scene.revision));
  }, [mutate, coverage]);

  const saveDimensions = React.useCallback((width: number, height: number): void => {
    void mutate((scene) => updateScene(scene.id, { width, height }, scene.revision));
  }, [mutate]);

  const onSelect = React.useCallback((id: string | null): void => {
    if (editingIdRef.current !== null) return;
    setSelectedId(id);
  }, []);

  const onBeginEdit = React.useCallback((id: string): void => {
    setSelectedId(id);
    setEditingId(id);
  }, []);

  const onCancelEdit = React.useCallback((): void => {
    setEditingId(null);
  }, []);

  const onRenderError = React.useCallback((message: string): void => {
    setRenderError(message);
  }, []);

  const onRenderOk = React.useCallback((): void => {
    setRenderError("");
  }, []);

  if (saved === undefined) {
    return <p role="status" className="m-0 text-xs" data-screen-workspace>Loading composition…</p>;
  }
  if (saved === null) {
    return (
      <div className="flex min-w-0 flex-col gap-3" data-screen-workspace>
        <p role="alert" className="m-0 text-xs">Composition not found.</p>
        <div>
          <Button variant="ghost" onClick={onBack}><ArrowLeft aria-hidden="true" className="size-3 shrink-0" />All compositions</Button>
        </div>
      </div>
    );
  }

  const { device, width, height } = resolveSceneScreen(saved, DEVICE_CATALOG.devices);
  // An explicit custom choice (null device) always renders the custom screen
  // below, even when the dimensions match a catalog device. A stored hint
  // that no longer matches the geometry (or names nothing the catalog
  // carries) also resolves to custom, keeping the exact saved dimensions
  // instead of adopting a lookalike device.
  const deviceValue = device ? device.id : "custom";
  const cssScale = (device ? referenceSizeCssScale(device.ppi) : 1) * sizePercent / 100;
  const paper = scenePaperCss(appearance, inverse);
  const selected = saved.placements.find((placement) => placement.id === selectedId) ?? null;
  const profileName = profiles?.find((profile) => profile.id === saved.outputProfileId)?.name ?? saved.outputProfileId;

  return (
    <div className="flex min-w-0 flex-col gap-4" data-screen-workspace={saved.id} data-screen-revision={saved.revision}>
      <div className="flex flex-wrap items-center gap-2">
        <TooltipHint content="Back to the composition list">
          <Button type="button" variant="ghost" size="icon-xs" data-screen-workspace-back
            aria-label="Back to compositions" onClick={onBack}>
            <ArrowLeft aria-hidden="true" />
          </Button>
        </TooltipHint>
        <h2 className="m-0 min-w-0 flex-1 truncate text-base">{saved.name}</h2>
        <TooltipHint content="Undo the last editor change">
          <Button type="button" variant="ghost" size="icon-xs" data-screen-undo
            aria-label="Undo" disabled={!history.canUndo || saving || pending || editingId !== null || conflict} onClick={() => void onUndo()}>
            <Undo2 aria-hidden="true" />
          </Button>
        </TooltipHint>
        <TooltipHint content="Redo the undone change">
          <Button type="button" variant="ghost" size="icon-xs" data-screen-redo
            aria-label="Redo" disabled={!history.canRedo || saving || pending || editingId !== null || conflict} onClick={() => void onRedo()}>
            <Redo2 aria-hidden="true" />
          </Button>
        </TooltipHint>
      </div>
      {conflict && (
        <section role="alert" className="content-state leading-[1.6]" data-screen-conflict>
          <h2>Composition changed in another tab.</h2>
          <p>Reloading discards your unsaved changes.{pendingRemote ? ` Saved revision ${pendingRemote.revision} is waiting.` : ""}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" data-screen-reload onClick={() => void reloadRef.current({ force: true })}>Reload saved composition</Button>
          </div>
        </section>
      )}
      {error && <p role="alert" className="m-0 text-xs" data-screen-workspace-error>{error}</p>}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-44 flex-col gap-1">
          <Label htmlFor="workspace-device">Device</Label>
          <Select value={deviceValue} disabled={saving} onValueChange={changeDevice}>
            <SelectTrigger id="workspace-device" data-screen-device className="w-52">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DEVICE_CATALOG.devices.map((entry) => (
                <SelectItem key={entry.id} value={entry.id}>{entry.label}</SelectItem>
              ))}
              <SelectItem value="custom">
                {device ? "Custom…" : `Custom ${width} × ${height}`}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p data-screen-device-meta className="m-0 text-xs text-soft">
          {device
            ? `${device.label} · ${width} × ${height} px · ${device.ppi} PPI`
            : `Custom screen · ${width} × ${height} px · no catalog shell`}
        </p>
      </div>
      {!resolveDone && saved.placements.length > 0 && (
        <p role="status" className="m-0 text-xs text-soft" data-screen-preview-loading>Resolving text styles…</p>
      )}
      {(previewStatus || renderError) && (
        <p role="alert" className="m-0 text-xs" data-screen-preview-error>
          {[previewStatus, renderError].filter(Boolean).join(" ")}
        </p>
      )}
      <div className="overflow-x-auto py-2" data-screen-stage-scroll>
        {device ? (
          <DeviceShell key={device.id} device={device} cssScale={cssScale}>
            {(layout) => (
              <div
                data-screen-aperture
                style={{
                  position: "absolute",
                  left: layout.screenX,
                  top: layout.screenY,
                  width: layout.screenWidth,
                  height: layout.screenHeight,
                }}
              >
                <SceneStage
                  sceneWidth={width}
                  sceneHeight={height}
                  placements={saved.placements}
                  paints={paints}
                  cssScale={cssScale}
                  paperCss={paper}
                  selectedId={selectedId}
                  editingId={editingId}
                  onSelect={onSelect}
                  onBeginEdit={onBeginEdit}
                  onCommitText={commitText}
                  onCancelEdit={onCancelEdit}
                  onCommitMove={commitMove}
                  onNudge={nudgeLabel}
                  onDeleteKey={deleteLabel}
                  onRenderError={onRenderError}
                  onRenderOk={onRenderOk}
                />
              </div>
            )}
          </DeviceShell>
        ) : (
          <div
            data-screen-custom-frame
            style={{ width: Math.max(1, width * cssScale), height: Math.max(1, height * cssScale), border: "1px solid var(--color-line)" }}
          >
            <SceneStage
              sceneWidth={width}
              sceneHeight={height}
              placements={saved.placements}
              paints={paints}
              cssScale={cssScale}
              paperCss={paper}
              selectedId={selectedId}
              editingId={editingId}
              onSelect={onSelect}
              onBeginEdit={onBeginEdit}
              onCommitText={commitText}
              onCancelEdit={onCancelEdit}
              onCommitMove={commitMove}
              onNudge={nudgeLabel}
              onDeleteKey={deleteLabel}
              onRenderError={onRenderError}
              onRenderOk={onRenderOk}
            />
          </div>
        )}
      </div>
      {selected && (
        <LabelInspector
          placement={selected}
          styles={styles ?? []}
          saving={saving}
          onPatch={(patch) => void commitLabelPatch(selected.id, patch)}
          onDuplicate={() => void duplicateLabel(selected.id)}
          onDelete={() => void deleteLabel(selected.id)}
          onBeginEdit={() => onBeginEdit(selected.id)}
        />
      )}
      <Card>
        <CardHeader>
          <CardTitle asChild><h2>Add label</h2></CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-2" data-screen-label-add>
            <div className="flex min-w-44 flex-1 flex-col gap-1">
              <Label htmlFor="new-screen-label-text">Text</Label>
              <Input id="new-screen-label-text" data-screen-new-text value={newLabel.text} maxLength={512}
                autoComplete="off" spellCheck={false} disabled={saving}
                onChange={(event) => setNewLabel((current) => ({ ...current, text: event.target.value }))} />
            </div>
            <div className="flex min-w-44 flex-1 flex-col gap-1">
              <Label htmlFor="new-screen-label-style">Text style</Label>
              <Select value={newLabel.styleId} disabled={saving || !styles}
                onValueChange={(styleId) => setNewLabel((current) => ({ ...current, styleId }))}>
                <SelectTrigger id="new-screen-label-style" data-screen-new-style>
                  <SelectValue placeholder="Choose a text style" />
                </SelectTrigger>
                <SelectContent>
                  {(styles ?? []).map((style) => (
                    <SelectItem key={style.id} value={style.id}>{style.name} — {style.fontSize}px</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button size="sm" data-screen-add-label disabled={saving || !styles} onClick={() => void addLabel()}>
              <Plus aria-hidden="true" className="size-3 shrink-0" />Add label
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle asChild><h2>Composition settings</h2></CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="workspace-name">Name</Label>
            <div className="flex gap-2">
              <Input id="workspace-name" data-screen-name value={name} maxLength={120} autoComplete="off"
                spellCheck={false} disabled={saving} onChange={(event) => setName(event.target.value)} />
              <Button size="sm" data-screen-save-name disabled={saving || !name.trim() || name === saved.name}
                onClick={saveName}>
                Save
              </Button>
            </div>
          </div>
          {!device && (
            <CustomDimensions width={width} height={height} saving={saving} onSave={saveDimensions} />
          )}
          <div className="flex min-w-44 max-w-72 flex-col gap-1">
            <Label htmlFor="workspace-profile">Output profile</Label>
            <Select value={saved.outputProfileId} disabled={saving || !profiles}
              onValueChange={(outputProfileId) => void mutate((scene) => updateScene(scene.id, { outputProfileId }, scene.revision))}>
              <SelectTrigger id="workspace-profile" data-screen-profile className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(profiles ?? []).map((profile) => (
                  <SelectItem key={profile.id} value={profile.id}>{profile.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <CoverageControl coverage={coverage} onCoverage={setCoverage} disabled={saving} />
            <div>
              <Button size="sm" data-screen-save-coverage disabled={saving} onClick={saveCoverage}>
                Save coverage
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle asChild><h2>Export ({profileName})</h2></CardTitle>
        </CardHeader>
        <CardContent>
          <SceneExportPanel scene={saved} textStyles={styles ?? []} library={library} />
        </CardContent>
      </Card>
    </div>
  );
}

function CustomDimensions({ width, height, saving, onSave }: {
  width: number;
  height: number;
  saving: boolean;
  onSave: (width: number, height: number) => void;
}): React.JSX.Element {
  const [draft, setDraft] = React.useState({ width: String(width), height: String(height) });
  const [localError, setLocalError] = React.useState("");
  React.useEffect(() => {
    setDraft({ width: String(width), height: String(height) });
  }, [width, height]);
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="flex flex-col gap-1">
        <Label htmlFor="workspace-width">Width (px)</Label>
        <Input id="workspace-width" data-screen-width type="number" min={1} max={4096}
          value={draft.width} disabled={saving} className="w-28"
          onChange={(event) => setDraft((current) => ({ ...current, width: event.target.value }))} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="workspace-height">Height (px)</Label>
        <Input id="workspace-height" data-screen-height type="number" min={1} max={4096}
          value={draft.height} disabled={saving} className="w-28"
          onChange={(event) => setDraft((current) => ({ ...current, height: event.target.value }))} />
      </div>
      <Button size="sm" data-screen-save-dimensions disabled={saving} onClick={() => {
        const parsedWidth = Math.round(Number(draft.width));
        const parsedHeight = Math.round(Number(draft.height));
        if (!Number.isInteger(parsedWidth) || parsedWidth < 1 || parsedWidth > 4096
          || !Number.isInteger(parsedHeight) || parsedHeight < 1 || parsedHeight > 4096) {
          setLocalError("Custom size must be whole numbers within 1..4096.");
          return;
        }
        setLocalError("");
        onSave(parsedWidth, parsedHeight);
      }}>
        Save size
      </Button>
      {localError && <p role="alert" className="m-0 w-full text-xs" data-screen-dimensions-error>{localError}</p>}
      <p className="m-0 w-full text-xs text-soft">Custom screens keep their own size; matching a catalog device exactly offers it in the Device list.</p>
    </div>
  );
}
