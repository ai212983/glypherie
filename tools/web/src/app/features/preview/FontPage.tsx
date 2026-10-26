import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import type { RendererRole } from "../../renderer/renderer-types.js";
import type { VariantSettings } from "../../variants/model.js";
import { defaultFamilySnapshot, previewVariantSettings, type FamilyMeta, type PreviewSnapshot } from "./state/snapshot-codec.js";
import { presetForText } from "./presets";
import { displayName } from "../../fonts/metadata";
import type { FontLibrary } from "../../fonts/useFontLibrary";
import { FontEditor } from "./FontEditor";
import { Button } from "../../../components/ui/button";
import { Label } from "../../../components/ui/label";
import { Select, SelectContent, SelectDisplay, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { indexPath } from "../../navigation/router.js";
import { readRouteSearch } from "../../navigation/snapshot";
import { NavLink } from "../../../components/NavLink";
import { SiteHeader } from "../../shell/SiteHeader";

interface FontPageProps {
  nav?: React.ReactNode;
  font: StoredFont;
  meta: FamilyMeta;
  snapshot: PreviewSnapshot;
  role: RendererRole;
  previewStatus: string;
  notice: string;
  library: FontLibrary;
  onSnapshot: (next: PreviewSnapshot, immediate?: boolean) => void;
  onPatch: (patch: Partial<PreviewSnapshot>, immediate?: boolean) => void;
  onRole: (role: RendererRole) => void;
  onStatus: (message: string) => void;
  onOpenFont: (id: string) => void;
  onIndex: () => void;
  onDelete: () => void;
  onSaveAsVariant: () => void;
  savingVariant: boolean;
  saveVariantError: string;
}

// Legacy unsaved URL preview host.
export function FontPage({
  nav, font, meta, snapshot, role, previewStatus, notice, library,
  onSnapshot, onPatch, onRole, onStatus, onOpenFont, onIndex, onDelete,
  onSaveAsVariant, savingVariant, saveVariantError,
}: FontPageProps): React.JSX.Element {
  const family = snapshot.families[font.id];
  const ready = library.rendererAvailable === true && library.loadedIds.has(font.id);
  const fontLoadError = library.loadStatus(font.id).state === "error"
    ? library.loadStatus(font.id).error
    : "";
  const base = readRouteSearch() || window.location.search;
  const indexHref = indexPath(base);
  if (!family) return (
    <main id="main" className="mx-auto my-12 w-[min(100%-3rem,1440px)] max-w-[45rem] leading-[1.6]">
      <section className="content-state" role="alert">
        <h2>This font has no preview settings yet.</h2>
        <p><NavLink href={indexHref} data-all-fonts onNavigate={onIndex}>All fonts</NavLink></p>
      </section>
    </main>
  );
  const settings: VariantSettings = previewVariantSettings(family, snapshot, role);
  const { axes: defaultAxes, ...defaultFields } = defaultFamilySnapshot(meta);
  const { axes, ...fields } = family;
  const singleFont = (library.fonts?.length ?? 0) <= 1;
  const resetDisabled = snapshot.kerning
    && Object.entries(defaultFields).every(([key, value]) => fields[key as keyof typeof fields] === value)
    && Object.keys({ ...defaultAxes, ...axes }).every((tag) => axes[tag] === defaultAxes[tag]);
  const onSettings = (next: VariantSettings): void => {
    if (next.renderer !== role) {
      onRole(next.renderer);
    }
    onPatch({
      profile: next.profile,
      paletteId: next.paletteId,
      kerning: next.kerning,
      stemFitting: next.stemFitting,
      diagonalFitting: next.diagonalFitting,
      monoRaster: next.monoRaster,
      rasterization: next.rasterization,
      families: {
        ...snapshot.families,
        [font.id]: { ...family, size: next.sizePx, axes: next.axes, spacing: next.letterSpacingPx },
      },
    }, true);
  };
  return (
    <>
      <SiteHeader
        title={displayName(font)}
        nav={nav}
      />
      <main id="main" className="mx-auto w-[min(100%-3rem,1440px)]">
      <section className="content-state my-6 max-w-[45rem] leading-[1.6]" aria-label="Unsaved preview" data-unsaved-preview>
        <h2 className="text-[1rem]">Unsaved preview.</h2>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button data-save-variant size="sm" onClick={onSaveAsVariant} disabled={savingVariant}>
            {savingVariant ? "Saving…" : "Save as variant"}
          </Button>
          {saveVariantError && (
            <span className="text-[.8rem]" role="alert" data-save-variant-error>{saveVariantError}</span>
          )}
        </div>
      </section>
      {notice && (
        <p className="mt-5 max-w-[45rem] text-[.875rem] leading-[1.55]" role="status" data-import-status>
          {notice}
        </p>
      )}
      <div className="font-picker m-0 mt-5 flex flex-wrap items-center gap-[.6rem] text-[.875rem] font-semibold">
        <Label asChild={singleFont} id="font-select-label" htmlFor={singleFont ? undefined : "font-select"}>
          {singleFont ? <span>Font</span> : "Font"}
        </Label>
        {singleFont ? (
          <SelectDisplay id="font-select" role="group" aria-labelledby="font-select-label">{displayName(font)}</SelectDisplay>
        ) : <Select
          value={font.id}
          onValueChange={onOpenFont}
        >
          <SelectTrigger id="font-select">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(library.fonts ?? []).map((entry) => (
              <SelectItem key={entry.id} value={entry.id}>{displayName(entry)}</SelectItem>
            ))}
          </SelectContent>
        </Select>}
        <Button data-delete-font variant="destructive" size="sm" onClick={onDelete}>
          Delete
        </Button>
      </div>
      <FontEditor
        key={font.id}
        font={font}
        settings={settings}
        sampleText={family.text}
        resetDisabled={resetDisabled}
        onSettings={onSettings}
        onSampleText={(text) => onPatch({
          families: { ...snapshot.families, [font.id]: { ...family, text, preset: presetForText(text) } },
        })}
        onReset={() => onSnapshot({
          ...snapshot,
          kerning: true,
          families: { ...snapshot.families, [font.id]: defaultFamilySnapshot(meta) },
        }, true)}
        fontReady={ready}
        fontLoadError={fontLoadError}
        previewStatus={previewStatus}
        onStatus={onStatus}
      />
      </main>
    </>
  );
}
