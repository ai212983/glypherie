import * as React from "react";
import { Palette, Type } from "lucide-react";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { BUNDLED_FONTS } from "../../fonts/bundled-fonts";
import { Select, SelectContent, SelectItem, SelectValue } from "../../../components/ui/select";
import { SpecimenSelectTrigger } from "../library/SpecimenSelect";
import { SpecimenListCard, SpecimenListItem } from "../library/SpecimenListCard";
import { SpecimenRow } from "../library/SpecimenRow";
import { SpecimenButton } from "../library/SpecimenButton";
import { SpecimenBlock } from "../preview/SpecimenBlock";
import { canvasPaletteById, libraryFrame } from "../library/canvas-palettes.js";
import { DEFAULT_LIBRARY_BASE_SIZE, type LibraryBaseSize } from "../library/preferences.js";
import { useDisplayPreferences } from "../../shell/DisplayPreferences";
import { ResponseCurve } from "./ResponseCurve";
import { RasterPreview } from "./RasterPreview";
import { BitDepthSelector } from "./BitDepthSelector";
import { PaletteDepthLabel, paletteDepthLabel } from "./PaletteDepthLabel";
import { curveLevels, editCurveLevel, linearCurve, pinCurveLevel, resizeCurve, unpinCurveLevel, type GrayCurve } from "./response-curve";

const DEFAULT_TEXT = "The quick brown fox jumps over 0123456789";
import { MONOCHROME } from "../../palettes/model";
import { usePalettes } from "../../palettes/usePalettes";
import { createPalette, updatePalette, deletePalette } from "../../palettes/repository";

function grayColor(value: number): string {
  return `rgb(${value} ${value} ${value})`;
}

function GrayValueEditor({ value, onChange }: { value: number; onChange: (value: number) => void }): React.JSX.Element {
  const id = React.useId();
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [draft, setDraft] = React.useState<string | null>(null);
  const valid = draft === null || (draft !== "" && Number.isInteger(Number(draft)) && Number(draft) >= 0 && Number(draft) <= 255);
  // An external commit (reset, depth change) replaces a stale draft, but
  // never while editing: the focused input keeps its text.
  React.useEffect(() => {
    if (document.activeElement !== inputRef.current) setDraft(null);
  }, [value]);
  return (
    <div className="flex flex-col gap-3">
      <Label htmlFor={id}>Gray value</Label>
      <Input
        ref={inputRef}
        id={id} type="number" min={0} max={255} step={1}
        value={draft ?? value} aria-invalid={!valid} className="bg-background tabular-nums"
        onChange={(event) => {
          setDraft(event.target.value);
          const next = event.target.valueAsNumber;
          if (Number.isInteger(next) && next >= 0 && next <= 255) onChange(next);
        }}
        onBlur={() => setDraft(null)}
      />
    </div>
  );
}

export function GrayscalePage({ embedded = false, baseSize = DEFAULT_LIBRARY_BASE_SIZE }: { embedded?: boolean; baseSize?: LibraryBaseSize }): React.JSX.Element {
  const { zoom, canvas: { palette, inverse } } = useDisplayPreferences();
  const { presets, ready, error: loadError, retry } = usePalettes();
  const [saveError, setSaveError] = React.useState("");
  const [presetId, setPresetId] = React.useState(0);
  const [nameDraft, setNameDraft] = React.useState<string | null>(null);
  // Selections reset only for ids already confirmed present, so a creation
  // still arriving through the live query is never mistaken for a deletion.
  const seenIds = React.useRef(new Set<number>([0]));
  const [selectedLevel, setSelectedLevel] = React.useState(0);
  const [text, setText] = React.useState(DEFAULT_TEXT);
  const [fontFileName, setFontFileName] = React.useState("Roboto.ttf");
  const [presetText, setPresetText] = React.useState("Aa 0123");
  const id = React.useId();
  const active = presets.find((preset) => preset.id === presetId && preset.id !== 0);
  const curve = active?.curve ?? MONOCHROME.curve;
  const levels = React.useMemo(() => curveLevels(curve), [curve]);
  const selected = Math.min(selectedLevel, levels.length - 1);
  const value = levels[selected] ?? 0;
  const frame = libraryFrame(palette, inverse);
  const base = canvasPaletteById(palette);
  const display = React.useMemo(() => ({
    paper: inverse ? base.ink : base.paper,
    ink: inverse ? base.paper : base.ink,
  }), [base, inverse]);
  const rows = presets.map((preset) => ({ ...preset, name: preset.name || "Untitled grayscale", levels: curveLevels(preset.curve) }));
  React.useEffect(() => {
    for (const preset of presets) seenIds.current.add(preset.id);
    if (ready && seenIds.current.has(presetId) && !presets.some((preset) => preset.id === presetId)) {
      setPresetId(0);
      setSelectedLevel(0);
      setNameDraft(null);
    }
  }, [ready, presets, presetId]);
  const save = (operation: () => Promise<unknown>): void => {
    setSaveError("");
    void operation().catch((error: unknown) => {
      setSaveError("Couldn’t save palette changes. Try again.");
      if (error instanceof Error && /deleted/.test(error.message)) {
        setPresetId(0);
        setSelectedLevel(0);
        setNameDraft(null);
      }
    });
  };
  const updatePreset = (patch: { name?: string; curve?: GrayCurve }): void => {
    if (active) save(() => updatePalette(active.id, { name: patch.name, curve: patch.curve ? () => patch.curve! : undefined }));
  };
  // The input renders a local draft so live-query commits never move the
  // caret; edits persist after a pause in typing, or immediately on blur.
  const nameTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => { setNameDraft(null); }, [active?.id]);
  React.useEffect(() => {
    if (active && nameDraft !== null && active.name === nameDraft) setNameDraft(null);
  }, [active, nameDraft]);
  React.useEffect(() => () => { if (nameTimer.current !== null) clearTimeout(nameTimer.current); }, []);
  const commitName = (): void => {
    if (nameTimer.current !== null) { clearTimeout(nameTimer.current); nameTimer.current = null; }
    if (active && nameDraft !== null && nameDraft !== active.name) updatePreset({ name: nameDraft });
    else setNameDraft(null);
  };
  const editName = (value: string): void => {
    setNameDraft(value);
    if (!active) return;
    if (nameTimer.current !== null) clearTimeout(nameTimer.current);
    const target = active.id;
    nameTimer.current = setTimeout(() => {
      nameTimer.current = null;
      save(() => updatePalette(target, { name: value }));
    }, 300);
  };
  const updateCurve = (change: (current: GrayCurve) => GrayCurve): void => {
    if (active) save(() => updatePalette(active.id, { curve: change }));
  };
  const updateLevel = (index: number, gray: number): void => {
    updateCurve((current) => editCurveLevel(current, index, gray));
  };
  const changeCount = (count: number): void => {
    if (!active || !Number.isInteger(count) || ![2, 4, 8, 16].includes(count)) return;
    updateCurve((current) => resizeCurve(current, count));
    setSelectedLevel(Math.round(selected * (count - 1) / (levels.length - 1)));
  };

  const panes = (
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row lg:overflow-hidden">
        <aside aria-label="Grayscale presets" className="studio-card flex w-full shrink-0 flex-col gap-5 border-b border-studio-border bg-font-card p-4 lg:h-full lg:min-h-0 lg:w-96 lg:overflow-y-auto lg:border-r lg:border-b-0">
          <SpecimenListCard
            title={<><Palette aria-hidden="true" className="size-3" />Presets</>}
            label="Presets" frame={frame} text={presetText} onText={setPresetText}
            frameProps={{ "data-preset-frame": true }}
            footer={
              <SpecimenButton data-add-preset disabled={!ready} onClick={() => save(async () => {
                const created = await createPalette();
                setPresetId(created);
                setSelectedLevel(0);
              })}>Add preset</SpecimenButton>
            }
          >
            {rows.map((entry) => {
              const checked = presetId === entry.id;
              return (
                <SpecimenListItem key={entry.id} frame={frame}>
                  <SpecimenRow
                    frame={frame}
                    name={entry.name}
                    caption={<PaletteDepthLabel data-preset-caption={entry.id} count={entry.levels.length} sizePx={baseSize} />}
                    selected={checked}
                    action={
                      <button
                        type="button" aria-pressed={checked}
                        data-preset-row={entry.id} aria-label={`${entry.name}, ${paletteDepthLabel(entry.levels.length, baseSize)}`}
                        onClick={() => { setPresetId(entry.id); setSelectedLevel(0); }}
                      />
                    }
                    deleteButton={entry.id === 0 ? undefined : {
                      "data-delete-preset": entry.id,
                      "aria-label": `Delete preset ${entry.name}`,
                      onClick: () => save(async () => {
                        await deletePalette(entry.id);
                        if (presetId === entry.id) {
                          setPresetId(0);
                          setSelectedLevel(0);
                          setNameDraft(null);
                        }
                      }),
                    }}
                  >
                    <div className="pt-1">
                      <RasterPreview compact fontFileName={fontFileName} zoom={zoom} baseSize={baseSize} display={display} text={presetText} levels={entry.levels} />
                    </div>
                  </SpecimenRow>
                </SpecimenListItem>
              );
            })}
          </SpecimenListCard>
        </aside>
        <section aria-label="Grayscale preview" className="min-w-0 flex-1 bg-studio-inset p-4 sm:p-6 lg:h-full lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain">
          <div className="mx-auto flex w-full max-w-[60rem] flex-col gap-6">
            {(loadError || saveError) && <p role="alert">{loadError || saveError} {loadError && <button onClick={retry}>Retry</button>}</p>}
            {!embedded && <header>
              <p className="m-0 mb-2 font-studio text-[10px] font-bold tracking-[.12em] text-muted-foreground uppercase">Glypherie</p>
            </header>}

            <Card className="gap-5 p-4 sm:p-6" role="group" aria-labelledby={`${id}-parameters-heading`}>
              <CardHeader>
                <CardTitle asChild>
                  <Label id={`${id}-parameters-heading`} htmlFor={`${id}-name`}><Type aria-hidden="true" className="size-3 shrink-0" />Name</Label>
                </CardTitle>
                {!active && <CardAction className="self-center text-[10px] leading-4 text-muted-foreground">Read-only preset</CardAction>}
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <Input id={`${id}-name`} value={nameDraft ?? active?.name ?? "Monochrome"} readOnly={!active} maxLength={80} className="bg-background"
                  onChange={(event) => editName(event.target.value)} onBlur={commitName}
                  onKeyDown={(event) => { if (event.key === "Enter") (event.target as HTMLInputElement).blur(); }} />
              </CardContent>
            </Card>

            <SpecimenBlock controlId={id} legend="Palette specimen controls" title="Preview" hideTextLabel inlinePreset
              text={text} onText={setText} maxLength={512} insetSampleText>
              <CardContent className="min-w-0">
                <RasterPreview fontFileName={fontFileName} text={text} levels={levels} zoom={zoom} baseSize={baseSize} display={display}
                  header={
                    <div className="mx-3 mt-3 flex items-center justify-between gap-3 border-b pb-2 font-studio text-[10px] font-semibold" style={{ color: frame.mutedCss, borderColor: frame.dividerCss }}>
                      <Select value={fontFileName} onValueChange={setFontFileName}>
                        <SpecimenSelectTrigger frame={frame} aria-label="Preview font">
                          <SelectValue />
                        </SpecimenSelectTrigger>
                        <SelectContent>
                          {BUNDLED_FONTS.map((font) => <SelectItem key={font.fileName} value={font.fileName}>{font.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <span className="shrink-0 tabular-nums">{baseSize} px</span>
                    </div>
                  }
                />
              </CardContent>
            </SpecimenBlock>

            <BitDepthSelector levels={levels} selected={selected} onSelect={setSelectedLevel}
              onCountChange={changeCount} readOnly={!active} frame={frame}
              resetDisabled={linearCurve(curve.length).every((level, index) =>
                level.value === curve[index]!.value && level.slope === curve[index]!.slope && level.pinned === curve[index]!.pinned)}
              onReset={active ? () => updatePreset({ curve: linearCurve(levels.length) }) : undefined}>
              <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_12rem]">
                <ResponseCurve key={`${presetId}/${levels.length}`} curve={curve} selected={selected} editable={!!active} onSelect={setSelectedLevel} onChange={updateLevel}
                  onPin={(index) => updateCurve((current) => pinCurveLevel(current, index))}
                  onUnpin={(index) => updateCurve((current) => unpinCurveLevel(current, index))} />
                <div className="flex flex-col gap-4">
                  <div role="img" aria-label={`Level ${selected}: gray value ${value}`} className="h-24 rounded-md border border-border" style={{ backgroundColor: grayColor(value) }} />
                  <p className="m-0 text-sm font-semibold">Level {selected}{selected === 0 ? " · Paper" : selected === levels.length - 1 ? " · Full ink" : ""}</p>
                  {active && <GrayValueEditor key={`${presetId}/${selected}`} value={value} onChange={(gray) => updateLevel(selected, gray)} />}
                </div>
              </div>
            </BitDepthSelector>
          </div>
        </section>
      </div>
  );
  if (embedded) return panes;
  return (
    <main className="studio-card flex min-h-dvh flex-col bg-studio-backdrop text-card-foreground lg:h-dvh lg:overflow-hidden">
      {panes}
    </main>
  );
}
