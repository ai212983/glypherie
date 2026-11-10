// Scene workspace: one saved composition on its screen with freely
// positioned WASM-rendered labels. Device association persists through the
// domain scene (deviceId plus exact geometry); an explicit custom choice
// (null device) always stays a custom screen with its own size, even when
// the dimensions match a catalog device, never silently resized. Label
// positions are native device pixels; moves keep those coordinates while
// clipping surfaces through the stage bounds.
import * as React from "react";
import { MousePointer2, Redo2, Type, Undo2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { ScrollArea } from "../../../components/ui/scroll-area";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { TooltipHint } from "../../../components/TooltipHint";
import { linearCurve, type GrayCurve } from "../../domain/output-profiles/curve.js";
import { useDisplayPreferences } from "../../shell/DisplayPreferences.js";
import { profileBits } from "../../renderer/render-spec.js";
import type { FontLibrary } from "../../fonts/useFontLibrary.js";
import type { VariantSettings } from "../../variants/model.js";
import { DEFAULT_CHARACTER_COVERAGE, type CharacterCoverage } from "../../domain/coverage.js";
import { CoverageControl } from "../preview/CoverageControl.js";
import { DEVICE_CATALOG, deviceShownLayout } from "../../devices/catalog.js";
import { DeviceShell } from "../../devices/DeviceShell.js";
import { CanvasViewport } from "./CanvasViewport.js";
import { referenceSizeCssScale } from "../../renderer/display-scaling.js";
import { sceneLabelPalette, scenePaperCss } from "../scenes/scene-palette.js";
import { SceneExportPanel } from "../scenes/SceneExportPanel.js";
import { directExportSnapshots, directLabelSettings } from "./direct-label.js";
import type { DomainPlacementView, DomainSceneView, SceneLabelPatch } from "../scenes/service.js";
import { STALE_OWNER_RECOVERY_MESSAGE } from "../scenes/service.js";
import { resolveTextStyle } from "../scenes/service.js";
import { resolveSceneScreen } from "./device-resolution.js";
import { useSceneSession, useSceneSnapshot } from "./useSceneSession.ts";
import { createSceneIntents } from "./scene-intents.ts";
import { sceneServiceOps } from "./scene-service-ops.ts";
import {
  DEVICE_ZOOM_DEFAULT,
  isDeviceBodyToggleDisabled,
  isDeviceZoomPercent,
  resolveDeviceBodyVisible,
} from "./device-zoom.js";
import { PIXEL_GRID_CELL_PX, SceneStage, type StagePaint, type StagePlacementPreview } from "./SceneStage.js";
import { LabelInspector } from "./LabelInspector.js";
import { SceneLayersPanel } from "./SceneLayersPanel.js";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "../../../components/ui/resizable";
import { DeviceHeader } from "./DeviceHeader.js";

export function SceneWorkspace({
  sceneId,
  library,
  sizePercent,
  pageControls,
}: {
  sceneId: string;
  library: FontLibrary;
  sizePercent: number;
  pageControls?: React.ReactNode;
}): React.JSX.Element {
  // The saved document and edit session own the accepted document, queue,
  // history, adoption and conflict; the workspace reads their stable snapshot
  // and submits meaningful edit intents through the scene-intents controller.
  const session = useSceneSession(sceneId);
  const snapshot = useSceneSnapshot(session);
  const saved = snapshot.document;
  const styles = snapshot.styles;
  const profiles = snapshot.profiles;
  const error = snapshot.error;
  const conflict = snapshot.conflict;
  const pendingRemote = snapshot.pendingRemote;
  // saving gates unrelated controls for blocking mutations only; pending
  // tracks every queued write (including background placement persistence)
  // so undo/redo stay honestly disabled while a write is in flight.
  const saving = snapshot.blocking;
  const pending = snapshot.pending;
  const [previewStatus, setPreviewStatus] = React.useState("");
  const [renderError, setRenderError] = React.useState("");
  const [coverage, setCoverage] = React.useState<CharacterCoverage>(DEFAULT_CHARACTER_COVERAGE);
  const [labelBounds, setLabelBounds] = React.useState<Record<string, { width: number; height: number }>>({});
  const onMeasureLabel = React.useCallback((id: string, width: number, height: number): void => {
    setLabelBounds((current) =>
      current[id]?.width === width && current[id]?.height === height
        ? current
        : { ...current, [id]: { width, height } },
    );
  }, []);
  const [tool, setTool] = React.useState<"select" | "text">("select");
  const newTextIdRef = React.useRef<string | null>(null);
  const lastTypographyRef = React.useRef<DomainPlacementView | null>(null);
  const [resolved, setResolved] = React.useState<Record<string, { fontId: string; settings: VariantSettings }>>({});
  const [resolveDone, setResolveDone] = React.useState(false);
  const [placementPreview, setPlacementPreview] = React.useState<StagePlacementPreview | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  // View-only presentation preferences: zoom multiplies the display scale
  // and the body preference survives temporary zoom changes. Neither writes
  // the domain scene.
  const [zoomPercent, setZoomPercent] = React.useState<number>(DEVICE_ZOOM_DEFAULT);
  const [bodyPreference, setBodyPreference] = React.useState(true);
  // View-only pixel-grid preference: the overlay shows only while zoom is
  // above 100%, so the stored preference survives crossing the threshold
  // and the grid returns when zooming back up. Never writes the domain scene.
  const [gridPreference, setGridPreference] = React.useState(false);
  // Which surface owns the open draft: the stage canvas editor or the layers
  // list editor. Only the owning surface renders its editor, so the two can
  // never activate simultaneously; every guard keys off editingId alone.
  const [editingOrigin, setEditingOrigin] = React.useState<"stage" | "list" | null>(null);
  // Synchronous mirror of the transient editing owner for DOM guards that
  // cannot wait for the next render (selection handoff, keyboard shortcuts).
  const editingIdRef = React.useRef(editingId);
  const {
    canvas: { palette: appearance, inverse },
  } = useDisplayPreferences();

  editingIdRef.current = editingId;

  // Explicit edit-owner transitions: opening, closing and coverage edits
  // inform the session synchronously, so no passive effect window can accept
  // a remote adoption before the open-draft flag arrives.
  const coverageIsDirty = React.useCallback(
    (document: DomainSceneView | null | undefined): boolean => {
      if (!document) return false;
      return JSON.stringify(coverage) !== JSON.stringify(document.exportCoverage);
    },
    [coverage],
  );

  const beginEditTransition = React.useCallback(
    (id: string, origin: "stage" | "list"): void => {
      session.setDraftState({ hasOpenDraft: true, hasUnresolvedChanges: coverageIsDirty(session.snapshot.document) });
      setSelectedId(id);
      setEditingId(id);
      setEditingOrigin(origin);
    },
    [session, coverageIsDirty],
  );

  const endEditTransition = React.useCallback((): void => {
    newTextIdRef.current = null;
    session.setDraftState({
      hasOpenDraft: false,
      hasUnresolvedChanges: coverageIsDirty(session.snapshot.document),
    });
    setEditingId(null);
    setEditingOrigin(null);
  }, [session, coverageIsDirty]);

  const intents = React.useMemo(() => createSceneIntents(session, sceneServiceOps), [session]);

  // Keep the last selected typography even after deselection or deletion.
  // Inspector reference changes also become the next text's defaults.
  const selectedPlacement = saved?.placements.find((placement) => placement.id === selectedId);
  const rememberedPlacement =
    selectedPlacement ?? saved?.placements.find((placement) => placement.id === lastTypographyRef.current?.id);
  React.useEffect(() => {
    if (rememberedPlacement) lastTypographyRef.current = rememberedPlacement;
  }, [rememberedPlacement]);

  React.useEffect(() => {
    if (tool !== "text") return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setTool("select");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [tool]);

  // The inspector follows the pointer in native pixels. Hold the released
  // preview until the revisioned save catches up, so release never flashes
  // the old values. Selection/reference changes discard obsolete previews.
  React.useEffect(() => {
    if (!placementPreview) return;
    const placement = saved?.placements.find((entry) => entry.id === placementPreview.id);
    if (
      !placement ||
      selectedId !== placementPreview.id ||
      placement.visible === false ||
      (placementPreview.fontSize !== undefined && placement.textStyleId !== null) ||
      (placement.x === placementPreview.x &&
        placement.y === placementPreview.y &&
        (placementPreview.fontSize === undefined || placement.fontSize === placementPreview.fontSize) &&
        (placementPreview.width === undefined || placement.width === placementPreview.width))
    )
      setPlacementPreview(null);
  }, [saved, selectedId, placementPreview]);

  // The session is the single informed channel for draft state: unsaved
  // coverage and the open in-place draft refuse remote adoption until they
  // resolve. No competing boolean mirrors.
  const coverageDirty =
    saved === undefined || saved === null ? false : JSON.stringify(coverage) !== JSON.stringify(saved.exportCoverage);
  React.useEffect(() => {
    session.setDraftState({ hasOpenDraft: editingId !== null, hasUnresolvedChanges: coverageDirty });
  }, [session, editingId, coverageDirty]);

  // Adopted documents replace selection and editing ownership: keep a
  // selection only when its placement survives the adopted revision, and
  // resync the coverage draft to the adopted export coverage.
  const adoptedAt = snapshot.adoptedAt;
  React.useEffect(() => {
    const document = session.snapshot.document;
    if (document) setCoverage(document.exportCoverage);
    newTextIdRef.current = null;
    setSelectedId((current) =>
      current && document?.placements.some((placement) => placement.id === current) ? current : null,
    );
    setEditingId(null);
    setEditingOrigin(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, adoptedAt]);

  // Route/scene presentation resets; the session owns the document reset,
  // history drop and reload. Subscribing to the domain lives in the adapter.
  React.useEffect(() => {
    setResolveDone(false);
    setResolved({});
    setSelectedId(null);
    setEditingId(null);
    setEditingOrigin(null);
    newTextIdRef.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneId]);

  // Id-free restores may reuse a placement id for different content. On a
  // successful restore only, release selection and keyboard ownership: a
  // rejection or a blocked action leaves the current document, selection and
  // any open draft intact instead of discarding them.
  const releaseFrameFocus = React.useCallback((sceneId: string): void => {
    const focused = document.activeElement;
    if (
      focused instanceof HTMLElement &&
      focused.hasAttribute("data-scene-label-frame") &&
      focused.closest("[data-screen-workspace]")?.getAttribute("data-screen-workspace") === sceneId
    ) {
      focused.blur();
    }
    setSelectedId(null);
  }, []);

  // Undo/redo stay disabled while an in-place draft is open, while a
  // conflict banner waits, or while a mutation is still queued: the session
  // moves the stacks only after a successful restore.
  const onUndo = React.useCallback(async (): Promise<void> => {
    const document = session.snapshot.document;
    if (!document) return;
    const ok = await intents.undo();
    if (!ok) return;
    endEditTransition();
    releaseFrameFocus(document.id);
  }, [intents, session, endEditTransition, releaseFrameFocus]);

  const onRedo = React.useCallback(async (): Promise<void> => {
    const document = session.snapshot.document;
    if (!document) return;
    const ok = await intents.redo();
    if (!ok) return;
    endEditTransition();
    releaseFrameFocus(document.id);
  }, [intents, session, endEditTransition, releaseFrameFocus]);

  // Undo/redo keyboard: never steal keys from text fields or an open draft
  // (the native textarea keeps its own edit history).
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (!event.metaKey && !event.ctrlKey) return;
      if (event.isComposing) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      )
        return;
      const state = session.snapshot;
      if (state.draftOpen || state.conflict || state.pending) return;
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
  }, [session, onUndo, onRedo]);

  // Direct-font labels resolve on the client and never enter the style batch.
  const styleIds = React.useMemo(
    () => [
      ...new Set(
        (saved?.placements ?? []).map((placement) => placement.textStyleId).filter((id): id is string => id !== null),
      ),
    ],
    [saved],
  );
  const styleNameById = React.useMemo(() => new Map((styles ?? []).map((style) => [style.id, style.name])), [styles]);
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
      const settled = await Promise.all(
        styleIds.map(
          async (
            styleId,
          ): Promise<{
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
          },
        ),
      );
      if (!live) return;
      const base = session.snapshot.document;
      if (!base || base.id !== sceneKey || base.id !== sceneId || base.outputProfileId !== profileId) return;
      const currentIds = new Set(
        base.placements.map((placement) => placement.textStyleId).filter((id): id is string => id !== null),
      );
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
    return () => {
      live = false;
    };
  }, [saved, styleIds, styleNameById, sceneId, fontLoadStatus, session]);

  const fontsById = React.useMemo(() => new Map((library.fonts ?? []).map((font) => [font.id, font])), [library.fonts]);

  const profileCurve = profiles?.find((profile) => profile.id === saved?.outputProfileId)?.curve;

  // Keyed by placement: variant and direct labels paint from different
  // sources, and two placements never share direct settings.
  const paints = React.useMemo((): Map<string, StagePaint> => {
    const map = new Map<string, StagePaint>();
    if (!saved) return map;
    for (const placement of saved.placements) {
      if (placement.textStyleId !== null) {
        const entry = resolved[placement.textStyleId];
        if (!entry) continue;
        const effective: GrayCurve =
          profileCurve?.length === 1 << profileBits(entry.settings.profile)
            ? profileCurve
            : linearCurve(1 << profileBits(entry.settings.profile));
        map.set(placement.id, {
          fontId: entry.fontId,
          settings: entry.settings,
          ready: library.loadedIds.has(entry.fontId),
          palette: sceneLabelPalette(effective, appearance, inverse),
        });
        continue;
      }
      if (placement.fontId === null || placement.fontSize === null || placement.width === null) continue;
      const font = fontsById.get(placement.fontId);
      if (!font || !profileCurve) continue;
      const settings = directLabelSettings(font, placement.fontSize, profileCurve, placement.fontWeight);
      const effective: GrayCurve =
        profileCurve.length === 1 << profileBits(settings.profile)
          ? profileCurve
          : linearCurve(1 << profileBits(settings.profile));
      map.set(placement.id, {
        fontId: placement.fontId,
        settings,
        ready: library.loadedIds.has(placement.fontId),
        palette: sceneLabelPalette(effective, appearance, inverse),
      });
    }
    return map;
  }, [saved, resolved, profileCurve, fontsById, library.loadedIds, appearance, inverse]);

  // One export entry per distinct direct font/size/effective-weight on the
  // scene, resolved with the same client settings as the preview.
  const directSnapshots = React.useMemo(
    () =>
      saved && profileCurve
        ? directExportSnapshots(
            saved.placements.filter(
              (placement) => placement.visible !== false && placement.textStyleId === null && placement.width !== null,
            ),
            fontsById,
            profileCurve,
          )
        : [],
    [saved, profileCurve, fontsById],
  );

  const exportStyles = React.useMemo(() => {
    const hidden = new Set(
      saved?.placements.filter((placement) => placement.visible === false).map((placement) => placement.textStyleId),
    );
    const visible = new Set(
      saved?.placements.filter((placement) => placement.visible !== false).map((placement) => placement.textStyleId),
    );
    return (styles ?? []).filter((style) => !hidden.has(style.id) || visible.has(style.id));
  }, [saved, styles]);

  const paintFonts = React.useMemo(() => [...new Set([...paints.values()].map((paint) => paint.fontId))], [paints]);
  const ensureFontsLoaded = library.ensureLoaded;
  React.useEffect(() => {
    ensureFontsLoaded(paintFonts);
  }, [ensureFontsLoaded, paintFonts]);

  // A direct label whose font left the library cannot paint: the domain pins
  // the reference, so this only fires before the font list loads.
  const directFontError = React.useMemo(() => {
    if (!saved || library.fonts === null) return "";
    const missing = saved.placements.filter(
      (placement) => placement.textStyleId === null && placement.fontId !== null && !fontsById.has(placement.fontId),
    );
    return missing.length === 0
      ? ""
      : `Couldn’t find the font for ${missing.length === 1 ? "a label" : `${missing.length} labels`}.`;
  }, [saved, library.fonts, fontsById]);

  // Position, size, wrap width and weight patches persist in the background
  // like drag releases; text, reference and order changes stay blocking.
  const commitLabelPatch = React.useCallback(
    (placementId: string, patch: SceneLabelPatch): Promise<boolean> => {
      return intents.patchLabel(placementId, patch);
    },
    [intents],
  );

  // Blur-save and inspector edits enqueue too: each resolves against the
  // latest saved base when it executes, so concurrent edits cannot issue
  // against the same stale revision. A rejection keeps the draft open for
  // recovery instead of discarding it.
  const commitText = React.useCallback(
    async (placementId: string, text: string): Promise<boolean> => {
      // Initial typing completes the label's creation undo step.
      const ok = await intents.commitText(placementId, text, { isNewLabel: newTextIdRef.current === placementId });
      if (ok) endEditTransition();
      return ok;
    },
    [intents, endEditTransition],
  );

  // Returns the queued revisioned outcome so the stage holds its released
  // preview until the saved coordinates render, rolling back only on
  // rejection. Undo checkpoints, conflict recovery and the serial queue are
  // unchanged; the write persists in the background so the release never
  // disables unrelated controls.
  const commitMove = React.useCallback(
    (placementId: string, x: number, y: number): Promise<boolean> => {
      return intents.commitMove(placementId, x, y).then((ok) => {
        if (!ok)
          setPlacementPreview((current) =>
            current?.id === placementId && current.x === x && current.y === y ? null : current,
          );
        return ok;
      });
    },
    [intents],
  );

  // Resize releases persist the label's own size and wrap width together with
  // the anchored position in ONE revisioned save through the same path as
  // moves, so the queued save and conflict recovery behave identically.
  // No-op releases skip revision churn.
  const commitResize = React.useCallback(
    (placementId: string, fontSize: number, width: number, x: number, y: number): Promise<boolean> => {
      return intents.commitResize(placementId, fontSize, width, x, y).then((ok) => {
        if (!ok)
          setPlacementPreview((current) =>
            current?.id === placementId &&
            current.x === x &&
            current.y === y &&
            current.fontSize === fontSize &&
            current.width === width
              ? null
              : current,
          );
        return ok;
      });
    },
    [intents],
  );

  const deleteLabel = React.useCallback(
    async (placementId: string): Promise<void> => {
      const ok = await intents.deleteLabel(placementId);
      if (ok) {
        setSelectedId((current) => (current === placementId ? null : current));
        if (editingIdRef.current === placementId) endEditTransition();
        else setEditingId((current) => (current === placementId ? null : current));
      }
    },
    [intents, endEditTransition],
  );

  // Relative moves compute from the latest saved base when the queued
  // operation executes, so rapid key repeats accumulate instead of replaying
  // one stale coordinate.
  const nudgeLabel = React.useCallback(
    (placementId: string, dx: number, dy: number): void => {
      intents.nudgeLabel(placementId, dx, dy);
    },
    [intents],
  );

  const lastTypography = rememberedPlacement ?? lastTypographyRef.current;
  const lastStyle = styles?.find((style) => style.id === lastTypography?.textStyleId);
  const lastFont = library.fonts?.find((font) => font.id === lastTypography?.fontId);
  const addStyle = lastStyle ?? (!lastFont ? styles?.[0] : undefined);
  const addFont = lastFont ?? (!addStyle ? library.fonts?.[0] : undefined);
  const canAddText = styles !== null && library.fonts !== null && Boolean(addStyle || addFont);

  const addLabel = React.useCallback(
    async (x: number, y: number): Promise<void> => {
      if (!canAddText) return;
      const reference = addStyle
        ? { kind: "style" as const, styleId: addStyle.id }
        : addFont
          ? { kind: "direct" as const, fontId: addFont.id }
          : null;
      // The session hands off only a write accepted by the current scene
      // generation, before remote adoption can replace its open draft.
      const addedId = await intents.addLabel({ x, y }, reference, {
        onCreated: (id) => {
          newTextIdRef.current = id;
          session.setDraftState({
            hasOpenDraft: true,
            hasUnresolvedChanges: coverageIsDirty(session.snapshot.document),
          });
          setSelectedId(id);
          setEditingId(id);
          setEditingOrigin("stage");
        },
      });
      if (addedId) setTool("select");
    },
    [intents, canAddText, addStyle, addFont, session, coverageIsDirty],
  );

  const changeDevice = React.useCallback(
    (deviceId: string): void => {
      if (deviceId === "custom") {
        intents.changeDevice({ deviceId: null });
        return;
      }
      const device = DEVICE_CATALOG.devices.find((entry) => entry.id === deviceId);
      if (!device) return;
      intents.changeDevice({ deviceId: device.id, rotation: 0, width: device.widthPx, height: device.heightPx });
    },
    [intents],
  );

  const saveCoverage = React.useCallback((): void => {
    intents.saveCoverage(coverage);
  }, [intents, coverage]);

  const rotateDevice = React.useCallback((): void => {
    intents.rotateDevice();
  }, [intents]);

  const changeZoom = React.useCallback((percent: number): void => {
    if (isDeviceZoomPercent(percent)) setZoomPercent(percent);
  }, []);

  const toggleBody = React.useCallback((): void => {
    setBodyPreference((current) => !current);
  }, []);

  const toggleGrid = React.useCallback((): void => {
    setGridPreference((current) => !current);
  }, []);

  const saveDimensions = React.useCallback(
    (width: number, height: number): void => {
      intents.saveDimensions(width, height);
    },
    [intents],
  );

  const changeOutputProfile = React.useCallback(
    (outputProfileId: string): void => {
      intents.changeOutputProfile(outputProfileId);
    },
    [intents],
  );

  const onSelect = React.useCallback((id: string | null): void => {
    if (editingIdRef.current !== null) return;
    setSelectedId(id);
  }, []);

  // An open draft owns editing until it commits or cancels: a second surface
  // can never steal it, so the stage and layers editors never activate
  // together and neither silently discards the other's draft.
  const moveLayer = React.useCallback(
    (from: number, to: number): Promise<boolean> => {
      return intents.moveLayer(from, to);
    },
    [intents],
  );

  const onBeginEdit = React.useCallback(
    (id: string, origin: "stage" | "list"): void => {
      if (editingIdRef.current !== null) return;
      beginEditTransition(id, origin);
    },
    [beginEditTransition],
  );

  const onCancelEdit = React.useCallback((): void => {
    endEditTransition();
  }, [endEditTransition]);

  const onBeginEditStage = React.useCallback((id: string): void => onBeginEdit(id, "stage"), [onBeginEdit]);
  const onBeginEditList = React.useCallback((id: string): void => onBeginEdit(id, "list"), [onBeginEdit]);
  const stageEditingId = editingOrigin === "stage" ? editingId : null;
  const listEditingId = editingOrigin === "list" ? editingId : null;

  const onRenderError = React.useCallback((message: string): void => {
    setRenderError(message);
  }, []);

  const onRenderOk = React.useCallback((): void => {
    setRenderError("");
  }, []);

  if (saved === undefined) {
    return (
      <p role="status" className="m-0 text-xs" data-screen-workspace>
        Loading composition…
      </p>
    );
  }
  if (saved === null) {
    // Unreachable through the UI (the page guarantees the default), but a
    // deleted record behind a live workspace must stay recoverable without
    // composition management.
    return (
      <div className="flex min-w-0 flex-col items-start gap-2" data-screen-workspace>
        <p role="alert" className="m-0 text-xs">
          Composition not found.
        </p>
        <Button variant="ghost" size="sm" data-screen-workspace-retry onClick={() => void session.discardRemote()}>
          Retry
        </Button>
      </div>
    );
  }

  const { device, width, height } = resolveSceneScreen(saved, DEVICE_CATALOG.devices);
  // An explicit custom choice (null device) always renders the custom screen
  // below, even when the dimensions match a catalog device. A stored hint
  // that no longer matches the geometry (or names nothing the catalog
  // carries) also resolves to custom, keeping the exact saved dimensions
  // instead of adopting a lookalike device.
  // Zoom multiplies the presentation scale only: native dimensions,
  // labels and export are unchanged.
  const cssScale = ((device ? referenceSizeCssScale(device.ppi) : 1) * sizePercent * zoomPercent) / 10000;
  const showBody = resolveDeviceBodyVisible({ hasDevice: device !== null, bodyPreference, zoomPercent });
  const bodyToggleDisabled = isDeviceBodyToggleDisabled({ hasDevice: device !== null, zoomPercent });
  const bodyToggleHint =
    device === null
      ? "Custom screens have no device body"
      : zoomPercent !== DEVICE_ZOOM_DEFAULT
        ? `Device body is hidden at ${zoomPercent}% zoom`
        : showBody
          ? "Hide the device body"
          : "Show the device body";
  // Enabled strictly above 100% zoom (by preset, not the effective CSS
  // scale); the overlay hides at or below 100% while the preference stays.
  const gridVisible = gridPreference && zoomPercent > 100;
  const gridToggleDisabled = zoomPercent <= 100;
  const gridToggleHint = gridToggleDisabled
    ? `Grid needs zoom above 100% (currently ${zoomPercent}%)`
    : gridVisible
      ? `Hide the grid (${PIXEL_GRID_CELL_PX} px cells)`
      : `Show the grid (${PIXEL_GRID_CELL_PX} px cells)`;
  const paper = scenePaperCss(appearance, inverse);
  // Single-sourced body/aperture presentation for the shell and the centered
  // viewport: the same layout drives DeviceShell and the ruler origin.
  const rotation = saved.rotation ?? 0;
  const bodyBox = device
    ? deviceShownLayout(device, cssScale, rotation, showBody)
    : {
        svgWidth: Math.max(1, width * cssScale),
        svgHeight: Math.max(1, height * cssScale),
        screenX: 0,
        screenY: 0,
        screenWidth: Math.max(1, width * cssScale),
        screenHeight: Math.max(1, height * cssScale),
      };
  // One stage element serves every frame so canvas props stay
  // single-sourced across shell and bare-canvas swaps.
  const stage = (
    <SceneStage
      sceneWidth={width}
      sceneHeight={height}
      placements={saved.placements}
      paints={paints}
      cssScale={cssScale}
      paperCss={paper}
      showGrid={gridVisible}
      selectedId={selectedId}
      editingId={stageEditingId}
      onMeasureLabel={onMeasureLabel}
      onPlacementPreview={setPlacementPreview}
      tool={tool}
      onAddText={(x, y) => void addLabel(x, y)}
      onSelect={onSelect}
      onBeginEdit={onBeginEditStage}
      onCommitText={commitText}
      onCancelEdit={onCancelEdit}
      onCommitMove={commitMove}
      onCommitResize={commitResize}
      onNudge={nudgeLabel}
      onDeleteKey={deleteLabel}
      onRenderError={onRenderError}
      onRenderOk={onRenderOk}
    />
  );
  const selected = saved.placements.find((placement) => placement.id === selectedId) ?? null;
  const inspected = selected && placementPreview?.id === selected.id ? { ...selected, ...placementPreview } : selected;
  const profileName = profiles?.find((profile) => profile.id === saved.outputProfileId)?.name ?? saved.outputProfileId;

  return (
    <div
      className="grid h-full min-h-0 min-w-0 grid-cols-1 grid-rows-[minmax(0,3fr)_minmax(0,2fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,21rem)] lg:grid-rows-[minmax(0,1fr)]"
      data-screen-workspace={saved.id}
      data-screen-revision={saved.revision}
    >
      <ResizablePanelGroup orientation="horizontal" data-screen-layers-group className="min-h-0 min-w-0">
        <ResizablePanel id="scene-layers" defaultSize={256} minSize={200} maxSize={420}>
          <SceneLayersPanel
            placements={saved.placements}
            bounds={labelBounds}
            onToggleVisibility={(id, visible) => void commitLabelPatch(id, { visible })}
            revision={saved.revision}
            selectedId={selectedId}
            onDelete={(id) => void deleteLabel(id)}
            deleteDisabled={pending || editingId !== null}
            editingId={listEditingId}
            saving={saving}
            conflict={conflict}
            onSelect={onSelect}
            onBeginEdit={onBeginEditList}
            onCommitText={commitText}
            onCancelEdit={onCancelEdit}
            onReorder={moveLayer}
          />
        </ResizablePanel>
        <ResizableHandle withHandle appearance="pane" aria-label="Resize layers panel" />
        <ResizablePanel id="scene-main" minSize={280}>
          <div className="relative flex h-full min-h-0 min-w-0 flex-col overflow-hidden" data-screen-center-panel>
            <DeviceHeader
              device={device}
              width={width}
              height={height}
              rotation={saved.rotation ?? 0}
              disabled={saving || pending || editingId !== null || conflict}
              onDevice={changeDevice}
              onRotate={rotateDevice}
              zoomPercent={zoomPercent}
              onZoom={changeZoom}
              showBody={showBody}
              bodyToggleDisabled={bodyToggleDisabled}
              bodyToggleHint={bodyToggleHint}
              onToggleBody={toggleBody}
              gridVisible={gridVisible}
              gridToggleDisabled={gridToggleDisabled}
              gridToggleHint={gridToggleHint}
              onToggleGrid={toggleGrid}
            />
            <CanvasViewport
              bodyWidth={bodyBox.svgWidth}
              bodyHeight={bodyBox.svgHeight}
              apertureX={bodyBox.screenX}
              apertureY={bodyBox.screenY}
              apertureWidth={bodyBox.screenWidth}
              apertureHeight={bodyBox.screenHeight}
              cssScale={cssScale}
              centerKey={`${device?.id ?? "custom"}|${saved.rotation ?? 0}|${width}x${height}`}
              body={
                device ? (
                  <DeviceShell
                    key={device.id}
                    device={device}
                    cssScale={cssScale}
                    rotation={saved.rotation ?? 0}
                    bodyVisible={showBody}
                  >
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
                        {stage}
                      </div>
                    )}
                  </DeviceShell>
                ) : (
                  <div
                    data-screen-custom-frame
                    style={{
                      width: Math.max(1, width * cssScale),
                      height: Math.max(1, height * cssScale),
                      border: "1px solid var(--color-line)",
                    }}
                  >
                    {stage}
                  </div>
                )
              }
            />
            <div
              className="absolute bottom-4 left-1/2 z-10 flex w-fit -translate-x-1/2 gap-1 rounded-xl border border-line bg-card p-1.5 shadow-lg"
              role="toolbar"
              aria-label="Canvas tools"
              data-screen-tools
            >
              <TooltipHint content="Select and move text">
                <Button
                  type="button"
                  size="sm"
                  variant={tool === "select" ? "default" : "ghost"}
                  aria-pressed={tool === "select"}
                  data-screen-tool="select"
                  aria-label="Select"
                  onClick={() => setTool("select")}
                >
                  <MousePointer2 aria-hidden="true" className="size-4" />
                  <span className="max-lg:sr-only">Select</span>
                </Button>
              </TooltipHint>
              <TooltipHint
                content={canAddText ? "Click the device canvas to add text" : "Add a font in the font library first"}
              >
                <Button
                  type="button"
                  size="sm"
                  variant={tool === "text" ? "default" : "ghost"}
                  aria-pressed={tool === "text"}
                  data-screen-tool="text"
                  aria-label="Add text"
                  disabled={!canAddText || saving || editingId !== null || conflict}
                  onClick={() => setTool("text")}
                >
                  <Type aria-hidden="true" className="size-4" />
                  <span className="max-lg:sr-only">Add text</span>
                </Button>
              </TooltipHint>
            </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
      <ScrollArea className="h-full min-h-0" data-screen-right-scroll role="region" aria-label="Screen properties">
        <div className="flex min-w-0 flex-col gap-4 pr-3 pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <TooltipHint content="Undo the last editor change">
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                data-screen-undo
                aria-label="Undo"
                disabled={!snapshot.canUndo || saving || pending || editingId !== null || conflict}
                onClick={() => void onUndo()}
              >
                <Undo2 aria-hidden="true" />
              </Button>
            </TooltipHint>
            <TooltipHint content="Redo the undone change">
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                data-screen-redo
                aria-label="Redo"
                disabled={!snapshot.canRedo || saving || pending || editingId !== null || conflict}
                onClick={() => void onRedo()}
              >
                <Redo2 aria-hidden="true" />
              </Button>
            </TooltipHint>
          </div>
          {conflict && (
            <section role="alert" className="content-state leading-[1.6]" data-screen-conflict>
              <h2>Composition changed in another tab.</h2>
              <p>
                Reloading discards your unsaved changes.
                {pendingRemote ? ` Saved revision ${pendingRemote.revision} is waiting.` : ""}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" data-screen-reload onClick={() => void session.discardRemote()}>
                  Reload saved composition
                </Button>
              </div>
            </section>
          )}
          {/* Invisible sizing row reserves the recovery footprint so the alert never shifts layout; aria-hidden and never focused. */}
          <div data-screen-workspace-status aria-live="polite" className="grid min-h-8">
            <p aria-hidden="true" className="invisible col-start-1 row-start-1 m-0 text-xs">
              {STALE_OWNER_RECOVERY_MESSAGE}{" "}
              <span className="bg-transparent p-0 text-[.8rem] text-soft underline">Retry</span>
            </p>
            {error ? (
              <p role="alert" className="col-start-1 row-start-1 m-0 text-xs" data-screen-workspace-error>
                {error}{" "}
                <button
                  type="button"
                  data-screen-workspace-retry
                  className="cursor-pointer bg-transparent p-0 text-[.8rem] text-soft underline"
                  onClick={() => void session.discardRemote()}
                >
                  Retry
                </button>
              </p>
            ) : null}
          </div>
          {!resolveDone && saved.placements.length > 0 && (
            <p role="status" className="m-0 text-xs text-soft" data-screen-preview-loading>
              Resolving text styles…
            </p>
          )}
          {(previewStatus || renderError || directFontError) && (
            <p role="alert" className="m-0 text-xs" data-screen-preview-error>
              {[previewStatus, renderError, directFontError].filter(Boolean).join(" ")}
            </p>
          )}
          {pageControls}
          {selected && inspected && (
            <LabelInspector
              placement={inspected}
              styles={styles ?? []}
              fonts={library.fonts ?? []}
              variantSettings={selected.textStyleId !== null ? resolved[selected.textStyleId]?.settings : undefined}
              sceneWidth={width}
              saving={saving}
              onPatch={(patch) => void commitLabelPatch(selected.id, patch)}
            />
          )}
          <Card>
            <CardHeader>
              <CardTitle asChild>
                <h2>Screen settings</h2>
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {!device && <CustomDimensions width={width} height={height} saving={saving} onSave={saveDimensions} />}
              <div className="flex min-w-44 max-w-72 flex-col gap-1">
                <Label htmlFor="workspace-profile">Output profile</Label>
                <Select
                  value={saved.outputProfileId}
                  disabled={saving || !profiles}
                  onValueChange={(outputProfileId) => changeOutputProfile(outputProfileId)}
                >
                  <SelectTrigger id="workspace-profile" data-screen-profile className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(profiles ?? []).map((profile) => (
                      <SelectItem key={profile.id} value={profile.id}>
                        {profile.name}
                      </SelectItem>
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
              <CardTitle asChild>
                <h2>Export ({profileName})</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <SceneExportPanel
                scene={saved}
                textStyles={exportStyles}
                directFonts={directSnapshots}
                library={library}
              />
            </CardContent>
          </Card>
        </div>
      </ScrollArea>
    </div>
  );
}

function CustomDimensions({
  width,
  height,
  saving,
  onSave,
}: {
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
        <Input
          id="workspace-width"
          data-screen-width
          type="number"
          min={1}
          max={4096}
          value={draft.width}
          disabled={saving}
          className="w-28"
          onChange={(event) => setDraft((current) => ({ ...current, width: event.target.value }))}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="workspace-height">Height (px)</Label>
        <Input
          id="workspace-height"
          data-screen-height
          type="number"
          min={1}
          max={4096}
          value={draft.height}
          disabled={saving}
          className="w-28"
          onChange={(event) => setDraft((current) => ({ ...current, height: event.target.value }))}
        />
      </div>
      <Button
        size="sm"
        data-screen-save-dimensions
        disabled={saving}
        onClick={() => {
          const parsedWidth = Math.round(Number(draft.width));
          const parsedHeight = Math.round(Number(draft.height));
          if (
            !Number.isInteger(parsedWidth) ||
            parsedWidth < 1 ||
            parsedWidth > 4096 ||
            !Number.isInteger(parsedHeight) ||
            parsedHeight < 1 ||
            parsedHeight > 4096
          ) {
            setLocalError("Custom size must be whole numbers within 1..4096.");
            return;
          }
          setLocalError("");
          onSave(parsedWidth, parsedHeight);
        }}
      >
        Save size
      </Button>
      {localError && (
        <p role="alert" className="m-0 w-full text-xs" data-screen-dimensions-error>
          {localError}
        </p>
      )}
      <p className="m-0 w-full text-xs text-soft">
        Custom screens keep their own size; matching a catalog device exactly offers it in the Device list.
      </p>
    </div>
  );
}
