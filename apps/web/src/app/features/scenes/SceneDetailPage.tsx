// Scene detail: saved name, dimensions, output profile and export
// coverage, placed labels with their text styles and positions, a real
// bitmap preview and the ZIP export. Every mutation carries the saved
// revision; a stale revision surfaces visibly with a reload action.
import * as React from "react";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { TooltipHint } from "../../../components/TooltipHint";
import type { FontLibrary } from "../../fonts/useFontLibrary";
import type { VariantSettings } from "../../variants/model";
import { DEFAULT_CHARACTER_COVERAGE, type CharacterCoverage } from "../../domain/coverage";
import { CoverageControl } from "../preview/CoverageControl";
import { ScenePreview, type SceneLabelPaint } from "./ScenePreview";
import { SceneExportPanel } from "./SceneExportPanel";
import { isConflict } from "./conflict";
import type {
  DomainOutputProfileView,
  DomainPlacementView,
  DomainSceneView,
  DomainTextStyleView,
} from "./service";
import {
  addSceneLabel,
  getScene,
  listOutputProfiles,
  listTextStyles,
  removeSceneLabel,
  resolveTextStyle,
  subscribeDomain,
  updateScene,
  updateSceneLabel,
} from "./service";

function styleLabel(style: DomainTextStyleView): string {
  return `${style.name} — ${style.fontSize}px`;
}

function LabelRow({ placement, styles, onSave, onDelete, onDirty, disabled }: {
  placement: DomainPlacementView;
  styles: DomainTextStyleView[];
  onSave: (patch: { text?: string; textStyleId?: string; x?: number; y?: number; order?: number }) => Promise<void>;
  onDelete: () => Promise<void>;
  onDirty: (placementId: string, dirty: boolean) => void;
  disabled: boolean;
}): React.JSX.Element {
  const [text, setText] = React.useState(placement.text);
  const [styleId, setStyleId] = React.useState(placement.textStyleId);
  const [x, setX] = React.useState(String(placement.x));
  const [y, setY] = React.useState(String(placement.y));
  const [order, setOrder] = React.useState(String(placement.order));
  const [saving, setSaving] = React.useState(false);
  const [rowError, setRowError] = React.useState("");
  const dirty = text !== placement.text || styleId !== placement.textStyleId
    || x !== String(placement.x) || y !== String(placement.y) || order !== String(placement.order);
  const dirtyRef = React.useRef(dirty);
  // A clean row adopts remote placement changes; a dirty row keeps its edits
  // so a sibling save or a held remote update never overwrites local input.
  // The parent reset token remounts every row on explicit reload instead.
  React.useEffect(() => {
    if (dirtyRef.current) return;
    setText(placement.text);
    setStyleId(placement.textStyleId);
    setX(String(placement.x));
    setY(String(placement.y));
    setOrder(String(placement.order));
  }, [placement]);
  React.useEffect(() => {
    dirtyRef.current = dirty;
    onDirty(placement.id, dirty);
    return () => { onDirty(placement.id, false); };
  }, [placement.id, dirty, onDirty]);

  const save = async (): Promise<void> => {
    if (saving || !dirty) return;
    const parsedX = Number(x);
    const parsedY = Number(y);
    const parsedOrder = Math.round(Number(order));
    setRowError("");
    try {
      if (!text.trim()) throw new Error("Label text must be non-empty.");
      if (!Number.isFinite(parsedX) || !Number.isFinite(parsedY)) throw new Error("Label positions must be numbers.");
      if (!Number.isInteger(parsedOrder)) throw new Error("Label order must be a whole number.");
      setSaving(true);
      try {
        await onSave({ text, textStyleId: styleId, x: parsedX, y: parsedY, order: parsedOrder });
      } finally {
        setSaving(false);
      }
    } catch (failure) {
      setRowError(failure instanceof Error ? failure.message : "Couldn’t save the label.");
    }
  };

  return (
    <li>
      <Card data-scene-label-row={placement.id}>
        <CardContent className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor={`label-text-${placement.id}`}>Text</Label>
            <Input id={`label-text-${placement.id}`} data-scene-label-text={placement.id} value={text}
              disabled={disabled || saving} maxLength={512} autoComplete="off" spellCheck={false}
              onChange={(event) => setText(event.target.value)} />
          </div>
          <div className="flex flex-wrap gap-2">
            <div className="flex min-w-44 flex-1 flex-col gap-1">
              <Label htmlFor={`label-style-${placement.id}`}>Text style</Label>
              <Select value={styleId} disabled={disabled || saving || styles.length === 0} onValueChange={setStyleId}>
                <SelectTrigger id={`label-style-${placement.id}`} data-scene-label-style={placement.id}>
                  <SelectValue placeholder="Choose a text style" />
                </SelectTrigger>
                <SelectContent>
                  {styles.map((style) => (
                    <SelectItem key={style.id} value={style.id}>{styleLabel(style)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={`label-x-${placement.id}`}>X</Label>
              <Input id={`label-x-${placement.id}`} data-scene-label-x={placement.id} type="number" value={x}
                disabled={disabled || saving} onChange={(event) => setX(event.target.value)} className="w-24" />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={`label-y-${placement.id}`}>Y</Label>
              <Input id={`label-y-${placement.id}`} data-scene-label-y={placement.id} type="number" value={y}
                disabled={disabled || saving} onChange={(event) => setY(event.target.value)} className="w-24" />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={`label-order-${placement.id}`}>Order</Label>
              <Input id={`label-order-${placement.id}`} data-scene-label-order={placement.id} type="number" value={order}
                disabled={disabled || saving} onChange={(event) => setOrder(event.target.value)} className="w-24" />
            </div>
          </div>
          {rowError && <p role="alert" className="m-0 text-xs" data-scene-label-error={placement.id}>{rowError}</p>}
          <div className="flex gap-2">
            <Button size="sm" data-scene-label-save={placement.id} disabled={disabled || saving || !dirty}
              onClick={() => { void save(); }}>
              {saving ? "Saving…" : "Save label"}
            </Button>
            <TooltipHint content="Remove this label">
              <Button type="button" variant="ghost" size="icon-xs" data-scene-label-delete={placement.id}
                aria-label={`Delete label ${placement.text}`} disabled={disabled || saving}
                onClick={() => void onDelete()}>
                <Trash2 aria-hidden="true" />
              </Button>
            </TooltipHint>
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

export function SceneDetailPage({ sceneId, library, onScenes }: {
  sceneId: string;
  library: FontLibrary;
  onScenes: () => void;
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
  const [dimensions, setDimensions] = React.useState({ width: "", height: "" });
  const [coverage, setCoverage] = React.useState<CharacterCoverage>(DEFAULT_CHARACTER_COVERAGE);
  const [newLabel, setNewLabel] = React.useState({ text: "", styleId: "", x: "0", y: "0" });
  const [resolved, setResolved] = React.useState<Record<string, { fontId: string; settings: VariantSettings }>>({});
  const [resolveDone, setResolveDone] = React.useState(false);
  const [generation, setGeneration] = React.useState(0);
  const [saving, setSaving] = React.useState(false);
  const savedRef = React.useRef(saved);
  const labelDirtyRef = React.useRef(new Map<string, boolean>());
  const resolveKeyRef = React.useRef("");
  const sceneIdRef = React.useRef(sceneId);
  const fetchSeqRef = React.useRef(0);

  React.useEffect(() => {
    savedRef.current = saved;
  });

  const onLabelDirty = React.useCallback((placementId: string, dirty: boolean) => {
    if (dirty) labelDirtyRef.current.set(placementId, true);
    else labelDirtyRef.current.delete(placementId);
  }, []);

  const draftsClean = React.useCallback((base: DomainSceneView): boolean => {
    if (name !== base.name) return false;
    if (dimensions.width !== String(base.width) || dimensions.height !== String(base.height)) return false;
    if (JSON.stringify(coverage) !== JSON.stringify(base.exportCoverage)) return false;
    return labelDirtyRef.current.size === 0;
  }, [name, dimensions, coverage]);

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
    setDimensions({ width: String(scene.width), height: String(scene.height) });
    setCoverage(scene.exportCoverage);
    labelDirtyRef.current.clear();
    setNewLabel((current) => ({ ...current, styleId: current.styleId || nextStyles[0]?.id || "" }));
    setPendingRemote(null);
    setConflict(false);
    setError("");
  }, []);

  // Remote state replaces local drafts only when they hold no edits; a newer
  // remote revision with dirty drafts is held behind the conflict banner and
  // every save keeps the revision its drafts were based on. Explicit reload
  // discards all drafts and remounts every label row coherently.
  const reload = React.useCallback(async (options?: { force?: boolean }) => {
    const seq = (fetchSeqRef.current += 1);
    try {
      const [scene, nextStyles, nextProfiles] = await Promise.all([
        getScene(sceneId), listTextStyles(), listOutputProfiles(),
      ]);
      if (sceneIdRef.current !== sceneId || fetchSeqRef.current !== seq) return;
      setStyles(nextStyles);
      setProfiles(nextProfiles);
      if (!scene) {
        savedRef.current = null;
        setSaved(null);
        setPendingRemote(null);
        return;
      }
      const base = savedRef.current;
      if (options?.force || !base) {
        adopt(scene, nextStyles, nextProfiles);
        if (options?.force) setGeneration((value) => value + 1);
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
      setError(failure instanceof Error ? failure.message : "Couldn’t load the scene.");
    }
  }, [sceneId, adopt, draftsClean]);

  const reloadRef = React.useRef(reload);
  reloadRef.current = reload;

  React.useEffect(() => {
    sceneIdRef.current = sceneId;
    savedRef.current = undefined;
    labelDirtyRef.current.clear();
    resolveKeyRef.current = "";
    setSaved(undefined);
    setPendingRemote(null);
    setConflict(false);
    setResolveDone(false);
    setResolved({});
    void reloadRef.current({ force: true });
    return subscribeDomain(() => { void reloadRef.current(); });
  }, [sceneId]);

  const mutate = React.useCallback(async (run: (scene: DomainSceneView) => Promise<DomainSceneView>): Promise<void> => {
    const base = savedRef.current;
    if (!base) return;
    setSaving(true);
    setError("");
    try {
      const next = await run(base);
      savedRef.current = next;
      setSaved(next);
      setPendingRemote(null);
      setConflict(false);
    } catch (failure) {
      if (isConflict(failure)) {
        setConflict(true);
        void reloadRef.current();
      } else {
        setError(failure instanceof Error ? failure.message : "Couldn’t save the scene.");
      }
    } finally {
      setSaving(false);
    }
  }, []);

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
  // label while successful previews stay, and a newer scene revision or
  // profile discards the stale set instead of painting it.
  React.useEffect(() => {
    if (!saved) {
      resolveKeyRef.current = "";
      setResolved({});
      setResolveDone(true);
      return;
    }
    if (styleIds.length === 0) {
      resolveKeyRef.current = "";
      setResolved({});
      setResolveDone(true);
      setPreviewStatus("");
      return;
    }
    const sceneKey = saved.id;
    const revision = saved.revision;
    const profileId = saved.outputProfileId;
    const key = `${sceneKey}:${revision}:${profileId}:${[...styleIds].sort().join(",")}`;
    if (resolveKeyRef.current !== key) {
      resolveKeyRef.current = key;
      setResolved({});
      setResolveDone(false);
      setRenderError("");
    }
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
      if (!base || base.id !== sceneKey || base.revision !== revision || base.outputProfileId !== profileId) return;
      const next: Record<string, { fontId: string; settings: VariantSettings }> = {};
      const failures: string[] = [];
      for (const entry of settled) {
        if (entry.view !== undefined) {
          next[entry.styleId] = { fontId: entry.view.fontId, settings: entry.view.settings };
        } else {
          failures.push(styleNameById.get(entry.styleId) ?? entry.styleId);
        }
      }
      setResolved(next);
      setResolveDone(true);
      const fontProblems: string[] = [];
      for (const styleId of styleIds) {
        const fontId = next[styleId]?.fontId;
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

  if (saved === undefined) {
    return <p role="status" className="m-0 text-xs" data-scene-detail>Loading scene…</p>;
  }
  if (saved === null) {
    return (
      <div className="flex min-w-0 flex-col gap-3" data-scene-detail>
        <p role="alert" className="m-0 text-xs">Scene not found.</p>
        <div>
          <Button variant="ghost" onClick={onScenes}><ArrowLeft aria-hidden="true" className="size-3 shrink-0" />All scenes</Button>
        </div>
      </div>
    );
  }

  const profileName = profiles?.find((profile) => profile.id === saved.outputProfileId)?.name ?? saved.outputProfileId;
  const profileCurve = profiles?.find((profile) => profile.id === saved.outputProfileId)?.curve;
  const paints: SceneLabelPaint[] = saved.placements.map((placement) => {
    const entry = resolved[placement.textStyleId];
    return {
      placement,
      fontId: entry?.fontId ?? "",
      settings: entry?.settings as VariantSettings,
      ready: !!entry && library.loadedIds.has(entry.fontId),
    };
  }).filter((paint) => paint.settings !== undefined);

  const addLabel = async (): Promise<void> => {
    const parsedX = Number(newLabel.x);
    const parsedY = Number(newLabel.y);
    if (!newLabel.text.trim()) throw new Error("Label text must be non-empty.");
    if (!newLabel.styleId) throw new Error("Choose a text style for the label.");
    if (!Number.isFinite(parsedX) || !Number.isFinite(parsedY)) throw new Error("Label positions must be numbers.");
    await mutate((scene) => addSceneLabel(
      scene.id,
      { text: newLabel.text, textStyleId: newLabel.styleId, x: parsedX, y: parsedY },
      scene.revision,
    ));
    setNewLabel((current) => ({ ...current, text: "", x: "0", y: "0" }));
  };

  return (
    <div className="flex min-w-0 flex-col gap-4" data-scene-detail={saved.id}>
      <div>
        <Button variant="ghost" size="sm" data-scene-back onClick={onScenes}>
          <ArrowLeft aria-hidden="true" className="size-3 shrink-0" />All scenes
        </Button>
      </div>
      {conflict && (
        <section role="alert" className="content-state leading-[1.6]" data-scene-conflict>
          <h2>Scene changed in another tab.</h2>
          <p>Reloading discards your unsaved changes.{pendingRemote ? ` Saved revision ${pendingRemote.revision} is waiting.` : ""}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" data-scene-reload onClick={() => void reloadRef.current({ force: true })}>Reload saved scene</Button>
          </div>
        </section>
      )}
      {error && <p role="alert" className="m-0 text-xs" data-scene-error>{error}</p>}
      <Card>
        <CardHeader>
          <CardTitle asChild><h2>Scene settings</h2></CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="detail-scene-name">Name</Label>
            <div className="flex gap-2">
              <Input id="detail-scene-name" data-scene-name value={name} maxLength={120} autoComplete="off"
                spellCheck={false} disabled={saving} onChange={(event) => setName(event.target.value)} />
              <Button size="sm" data-scene-save-name disabled={saving || !name.trim() || name === saved.name}
                onClick={() => void mutate((scene) => updateScene(scene.id, { name: name.trim() }, scene.revision))}>
                Save
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="detail-scene-width">Width (px)</Label>
              <Input id="detail-scene-width" data-scene-width type="number" min={1} max={4096}
                value={dimensions.width} disabled={saving}
                onChange={(event) => setDimensions((current) => ({ ...current, width: event.target.value }))} className="w-28" />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="detail-scene-height">Height (px)</Label>
              <Input id="detail-scene-height" data-scene-height type="number" min={1} max={4096}
                value={dimensions.height} disabled={saving}
                onChange={(event) => setDimensions((current) => ({ ...current, height: event.target.value }))} className="w-28" />
            </div>
            <Button size="sm" data-scene-save-dimensions disabled={saving}
              onClick={() => {
                const parsedWidth = Math.round(Number(dimensions.width));
                const parsedHeight = Math.round(Number(dimensions.height));
                if (!Number.isInteger(parsedWidth) || parsedWidth < 1 || parsedWidth > 4096) {
                  setError("Scene width must be a whole number within 1..4096.");
                  return;
                }
                if (!Number.isInteger(parsedHeight) || parsedHeight < 1 || parsedHeight > 4096) {
                  setError("Scene height must be a whole number within 1..4096.");
                  return;
                }
                void mutate((scene) => updateScene(scene.id, { width: parsedWidth, height: parsedHeight }, scene.revision));
              }}>
              Save size
            </Button>
            <div className="flex min-w-44 flex-1 flex-col gap-1">
              <Label htmlFor="detail-scene-profile">Output profile</Label>
              <Select value={saved.outputProfileId} disabled={saving || !profiles}
                onValueChange={(outputProfileId) => void mutate((scene) => updateScene(scene.id, { outputProfileId }, scene.revision))}>
                <SelectTrigger id="detail-scene-profile" data-scene-profile className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(profiles ?? []).map((profile) => (
                    <SelectItem key={profile.id} value={profile.id}>{profile.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <CoverageControl coverage={coverage} onCoverage={setCoverage} disabled={saving} />
            <div>
              <Button size="sm" data-scene-save-coverage disabled={saving}
                onClick={() => void mutate((scene) => updateScene(scene.id, { exportCoverage: coverage }, scene.revision))}>
                Save coverage
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle asChild><h2>Labels</h2></CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-2" data-scene-label-add>
            <div className="flex min-w-44 flex-1 flex-col gap-1">
              <Label htmlFor="new-label-text">Text</Label>
              <Input id="new-label-text" data-scene-new-text value={newLabel.text} maxLength={512}
                autoComplete="off" spellCheck={false} disabled={saving}
                onChange={(event) => setNewLabel((current) => ({ ...current, text: event.target.value }))} />
            </div>
            <div className="flex min-w-44 flex-1 flex-col gap-1">
              <Label htmlFor="new-label-style">Text style</Label>
              <Select value={newLabel.styleId} disabled={saving || !styles}
                onValueChange={(styleId) => setNewLabel((current) => ({ ...current, styleId }))}>
                <SelectTrigger id="new-label-style" data-scene-new-style>
                  <SelectValue placeholder="Choose a text style" />
                </SelectTrigger>
                <SelectContent>
                  {(styles ?? []).map((style) => (
                    <SelectItem key={style.id} value={style.id}>{styleLabel(style)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-label-x">X</Label>
              <Input id="new-label-x" data-scene-new-x type="number" value={newLabel.x} disabled={saving}
                onChange={(event) => setNewLabel((current) => ({ ...current, x: event.target.value }))} className="w-24" />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-label-y">Y</Label>
              <Input id="new-label-y" data-scene-new-y type="number" value={newLabel.y} disabled={saving}
                onChange={(event) => setNewLabel((current) => ({ ...current, y: event.target.value }))} className="w-24" />
            </div>
            <Button size="sm" data-scene-add-label disabled={saving || !styles}
              onClick={() => { void addLabel().catch((failure: unknown) => {
                if (isConflict(failure)) { setConflict(true); void reloadRef.current(); }
                else setError(failure instanceof Error ? failure.message : "Couldn’t add the label.");
              }); }}>
              <Plus aria-hidden="true" className="size-3 shrink-0" />Add label
            </Button>
          </div>
          {saved.placements.length === 0 ? (
            <p className="m-0 text-xs text-soft" data-scene-labels-empty>No labels yet. Add one above.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0" data-scene-labels>
              {saved.placements.map((placement) => (
                <LabelRow
                  key={`${placement.id}:${generation}`}
                  placement={placement}
                  styles={styles ?? []}
                  disabled={saving || !styles}
                  onDirty={onLabelDirty}
                  onSave={(patch) => mutate((scene) => updateSceneLabel(scene.id, placement.id, patch, scene.revision))}
                  onDelete={() => mutate((scene) => removeSceneLabel(scene.id, placement.id, scene.revision))}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle asChild><h2>Preview</h2></CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {!resolveDone && saved.placements.length > 0 && (
            <p role="status" className="m-0 text-xs text-soft" data-scene-preview-loading>Resolving text styles…</p>
          )}
          {saved.placements.length > 0 && paints.length > 0 && (
            <ScenePreview width={saved.width} height={saved.height} labels={paints} curve={profileCurve}
              onRenderError={(message) => setRenderError(message)} />
          )}
          {(previewStatus || renderError) && (
            <p role="alert" className="m-0 text-xs" data-scene-preview-error>
              {[previewStatus, renderError].filter(Boolean).join(" ")}
            </p>
          )}
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
