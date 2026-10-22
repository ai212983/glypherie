import * as React from "react";
import { ALargeSmall, FileText, MoveHorizontal, Palette, ScanLine, SlidersHorizontal, type LucideIcon } from "lucide-react";
import { useDisplayPreferences } from "../../shell/DisplayPreferences";
import type { StoredFont } from "../../fonts/storage.js";
import { currentPreviewSettings, type VariantSettings } from "../../variants/model.js";
import { useRenderer } from "../../renderer/renderer-context.js";
import { classificationLabel, displayName } from "../../fonts/metadata";
import { bundledLicense } from "../../fonts/bundled-fonts";
import { FittingControls } from "./controls/FittingControls";
import { OutputControls } from "./controls/OutputControls";
import { LayoutControls } from "./controls/LayoutControls";
import { FontSizeControl } from "../../../components/FontSizeControl";
import { AxisControls } from "./controls/AxisControls";
import { SpecimenBlock } from "./SpecimenBlock";
import { PreviewCanvas } from "./PreviewCanvas";
import { PlaydateExport } from "./PlaydateExport";
import { libraryFrame } from "../library/canvas-palettes";
import { Badge } from "../../../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../../components/ui/card";

import { usePalettes } from "../../palettes/usePalettes";
import { resolvePalette } from "../../palettes/model";
import { paletteProfile, presetColors } from "../../palettes/render";

export interface FontEditorProps {
  font: StoredFont;
  settings: VariantSettings;
  sampleText: string;
  specimenInheritance?: React.ComponentProps<typeof SpecimenBlock>["inheritance"];
  onSettings: (settings: VariantSettings) => void;
  onSampleText: (text: string) => void;
  onReset: () => void;
  resetDisabled: boolean;
  fontReady: boolean;
  fontLoadError: string;
  previewStatus: string;
  onStatus: (message: string) => void;
  appearance?: "classic" | "studio";
  sidebarHead?: React.ReactNode;
  sidebarStart?: React.ReactNode;
}

function ControlSection({ title, icon: Icon, layer, appearance, children }: {
  title: string;
  icon: LucideIcon;
  layer: string;
  appearance: "classic" | "studio";
  children: React.ReactNode;
}): React.JSX.Element {
  const headingId = React.useId();
  const studio = appearance === "studio";
  return (
    <Card variant={studio ? "default" : "plain"} className={studio ? undefined : "min-w-0 gap-3 py-4"}
      role="group" aria-labelledby={headingId} data-control-layer={layer}>
      <CardHeader className={studio ? undefined : "px-4"}>
        <CardTitle asChild className={studio ? undefined : "flex items-center gap-[6px] text-[.875rem] text-studio-heading"}>
          <h2 id={headingId}>
            <Icon aria-hidden="true" className="size-3 shrink-0" />
            {title}
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent className={`flex min-w-0 flex-col gap-3 ${studio ? "" : "px-4"}`}>
        {children}
      </CardContent>
    </Card>
  );
}

function RenderingSection({ title, id, layer, children }: {
  title: string;
  id: string;
  layer: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section aria-labelledby={id} data-control-layer={layer} className="flex min-w-0 flex-col gap-4 not-first:border-t not-first:border-border/80 not-first:pt-6 xl:not-first:border-t-0 xl:not-first:border-l xl:not-first:pt-0 xl:not-first:pl-6">
      <h3 id={id} className="m-0 text-xs font-semibold">{title}</h3>
      {children}
    </section>
  );
}

// Shared native editor: persisted domain (settings + sample text) flows in as
// direct props while zoom is a global display preference and panel state is
// local view state. Both the saved-variant editor and the legacy unsaved
// preview render through this component.
export function FontEditor({
  font, settings: storedSettings, sampleText, onSettings, onSampleText, onReset, resetDisabled,
  fontReady, fontLoadError, previewStatus, onStatus,
  appearance = "classic", sidebarHead, sidebarStart, specimenInheritance,
}: FontEditorProps): React.JSX.Element {
  const { zoom, canvas: { palette: paletteId, inverse } } = useDisplayPreferences();
  const { available: rendererAvailable } = useRenderer();
  const { presets, ready: palettesReady, error: paletteError, retry: retryPalettes } = usePalettes();
  const preset = resolvePalette(presets, storedSettings.paletteId);
  const settings = currentPreviewSettings({ ...storedSettings, profile: paletteProfile(preset) });
  const colors = React.useMemo(() => presetColors(preset, paletteId, inverse), [preset, paletteId, inverse]);
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const license = font.source === "bundled" ? bundledLicense(font.fileName) : null;

  const patch = (next: Partial<VariantSettings>): void => {
    onSettings(currentPreviewSettings({ ...settings, ...next }));
  };

  const exportControl = <PlaydateExport key={font.id} fontId={font.id} name={displayName(font)} settings={settings} ready={fontReady} />;
  const disabled = rendererAvailable !== true;
  const specimenProps = {
    controlId: font.id,
    legend: `${displayName(font)} interactive controls`,
    text: sampleText,
    onText: onSampleText,
    inheritance: specimenInheritance,
    onReset,
    resetDisabled,
  };
  const fontControls = (
    <ControlSection title="Font" icon={ALargeSmall} layer="font" appearance={appearance}>
      <FontSizeControl id={`size-${font.id}`} sizePx={settings.sizePx} onSize={(sizePx) => patch({ sizePx })} />
      <AxisControls appearance="embedded" font={font} axes={settings.axes} advancedOpen={advancedOpen}
        onAxes={(axes) => patch({ axes })} onAdvancedOpen={setAdvancedOpen} />
    </ControlSection>
  );
  const fittingControls = <FittingControls profile={settings.profile} stemFitting={settings.stemFitting}
    diagonalFitting={settings.diagonalFitting} disabled={disabled}
    hasFontHints={font.metadata.font_hints === true}
    onStemFitting={(stemFitting) => patch({ stemFitting })}
    onDiagonalFitting={(diagonalFitting) => patch({ diagonalFitting })} />;
  const outputControls = <>
    <OutputControls presets={presets} paletteId={preset.id}
      disabled={disabled || !palettesReady} onPalette={(id) => patch({ paletteId: id, profile: paletteProfile(resolvePalette(presets, id)) })} />
    {paletteError && <p role="alert">{paletteError} <button onClick={retryPalettes}>Retry</button></p>}
  </>;
  const layoutControls = <LayoutControls fontId={font.id} spacingPx={settings.letterSpacingPx}
    kerning={settings.kerning} onSpacing={(letterSpacingPx) => patch({ letterSpacingPx })}
    onKerning={(kerning) => patch({ kerning })} />;
  const pipelineControls = (
    <>
      <ControlSection title="Fitting" icon={ScanLine} layer="fitting" appearance={appearance}>
        {fittingControls}
      </ControlSection>
      <ControlSection title="Output" icon={Palette} layer="output" appearance={appearance}>
        {outputControls}
      </ControlSection>
      <ControlSection title="Layout" icon={MoveHorizontal} layer="layout" appearance={appearance}>
        {layoutControls}
      </ControlSection>
    </>
  );

  if (appearance === "studio") {
    const frame = libraryFrame(paletteId, inverse);
    const statusText = previewStatus || fontLoadError;
    return (
      <>
        <aside aria-label="Font" className="studio-card flex w-full shrink-0 flex-col gap-5 border-b border-studio-border bg-font-card p-4 lg:h-full lg:min-h-0 lg:w-96 lg:overflow-y-auto lg:border-r lg:border-b-0">
          {sidebarStart}
          {fontControls}
        </aside>
        <section id={`family-${font.id}`} aria-label="Variant preview" aria-labelledby={`heading-${font.id}`} className="family min-w-0 flex-1 bg-studio-inset p-4 sm:p-6 lg:h-full lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain">
          <div aria-label="Variant controls" role="group" className="mx-auto flex w-full max-w-[60rem] flex-col gap-6">
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <h2 id={`heading-${font.id}`} className="m-0 min-w-0 font-display text-[16px] leading-6 font-bold tracking-[0.4px] text-studio-foreground">
                {displayName(font)}
              </h2>
              {font.source === "bundled" && <Badge variant="outline" className="shrink-0 border-studio-border bg-studio-inset px-2 py-0.5 font-studio text-[9px] leading-4 font-bold text-studio-muted shadow-studio-inset">
                Bundled
              </Badge>}
            </div>
            {rendererAvailable === false && (
              <section className="content-state my-6 max-w-[45rem] leading-[1.6]" role="alert">
                <h3>Preview unavailable.</h3>
              </section>
            )}
            {sidebarHead}
            <SpecimenBlock {...specimenProps} appearance={appearance} title="Preview" hideTextLabel inlinePreset insetSampleText>
              <CardContent className="min-w-0">
                <div
                  data-variant-paper
                  className="interactive-preview rounded-[12px] border p-4 shadow-[inset_0_2px_4px_rgb(0_0_0/5%)]"
                  style={{ backgroundColor: frame.paperCss, borderColor: frame.borderCss }}
                >
                  <div className="flex w-full min-w-0 items-center justify-between gap-3 font-studio text-[9px] leading-4">
                    <span data-status role="status" className="min-w-0 flex-1 text-left [overflow-wrap:anywhere]" style={{ color: frame.mutedCss }}>
                      {statusText}
                    </span>
                    <span className="shrink-0" style={{ color: frame.mutedCss }}>
                      {`${settings.sizePx} px / ${Math.log2(preset.curve.length)}-bit`}
                    </span>
                  </div>
                  <div className="pt-1">
                    {fontReady ? (
                      <PreviewCanvas
                        key={font.id}
                        fontId={font.id}
                        text={sampleText}
                        sizePx={settings.sizePx}
                        axes={settings.axes}
                        profile={settings.profile}
                        role={settings.renderer}
                        spacing={settings.letterSpacingPx}
                        kerning={settings.kerning}
                        stemFitting={settings.stemFitting}
                        diagonalFitting={settings.diagonalFitting}
                        monoRaster={settings.monoRaster}
                        rasterization={settings.rasterization}
                        zoom={zoom}
                        palette={colors}
                        framed
                        onStatus={onStatus}
                      />
                    ) : (
                      <p className="m-0 text-[.8rem]" role="status" style={{ color: frame.mutedCss }}>Loading preview…</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </SpecimenBlock>
            <Card role="group" aria-labelledby={`rendering-${font.id}`}>
              <CardHeader>
                <CardTitle asChild>
                  <h2 id={`rendering-${font.id}`}><SlidersHorizontal aria-hidden="true" className="size-3 shrink-0" />Rendering &amp; spacing</h2>
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-6 xl:grid-cols-3">
                <RenderingSection title="Rendering" id={`rendering-options-${font.id}`} layer="output">
                  {outputControls}
                </RenderingSection>
                <RenderingSection title="Fitting" id={`fitting-options-${font.id}`} layer="fitting">
                  {fittingControls}
                </RenderingSection>
                <RenderingSection title="Spacing" id={`spacing-options-${font.id}`} layer="layout">
                  {layoutControls}
                </RenderingSection>
              </CardContent>
            </Card>
            {exportControl}
            {license && (
              <Card>
                <CardHeader>
                  <CardTitle asChild>
                    <h3><FileText aria-hidden="true" className="size-3 shrink-0" />License</h3>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="m-0 text-[.8rem] text-soft">
                    <a href={license.url}>SIL Open Font License 1.1</a>
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </section>
      </>
    );
  }

  return (
    <>
      <div className="mt-5 grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
        {fontControls}
        {pipelineControls}
      </div>
      {rendererAvailable === false && (
        <section className="content-state my-12 max-w-[45rem] leading-[1.6]" role="alert">
          <h2>Preview unavailable.</h2>
        </section>
      )}
      <section className="family py-8" id={`family-${font.id}`} aria-labelledby={`heading-${font.id}`}>
        <h2 id={`heading-${font.id}`} className="mb-[.65rem] text-[1.5rem] font-[650] tracking-[-.02em]">
          {displayName(font)}
        </h2>
        {classificationLabel(font.metadata) && (
          <p className="font-metadata mb-6 text-[.8rem] leading-[1.5] text-soft [overflow-wrap:anywhere]">
            {classificationLabel(font.metadata)}
          </p>
        )}
        {license && (
          <p className="m-0 mb-6 text-[.8rem] text-soft">
            License: <a href={license.url}>SIL Open Font License 1.1</a>
          </p>
        )}
        <section className="interactive-specimen mt-0 mb-7">
          <SpecimenBlock {...specimenProps} appearance={appearance} title="Interactive specimen" status={
            <CardDescription data-status role="status" hidden={!previewStatus && !fontLoadError}>
              {previewStatus || fontLoadError}
            </CardDescription>
          }>
            {fontReady ? (
              <PreviewCanvas
                key={font.id}
                fontId={font.id}
                text={sampleText}
                sizePx={settings.sizePx}
                axes={settings.axes}
                profile={settings.profile}
                role={settings.renderer}
                spacing={settings.letterSpacingPx}
                kerning={settings.kerning}
                stemFitting={settings.stemFitting}
                diagonalFitting={settings.diagonalFitting}
                monoRaster={settings.monoRaster}
                rasterization={settings.rasterization}
                zoom={zoom}
                palette={colors}
                onStatus={onStatus}
              />
            ) : (
              <p className="mx-4 mb-4 text-[.8rem] text-soft" role="status">Loading preview…</p>
            )}
          </SpecimenBlock>
        </section>
        {exportControl}
      </section>
    </>
  );
}
