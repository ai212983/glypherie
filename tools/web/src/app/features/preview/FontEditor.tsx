import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import type { VariantSettings } from "../../variants/model.js";
import { useRenderer } from "../../renderer/renderer-context.js";
import { classificationLabel, displayName } from "../../fonts/metadata";
import { bundledLicense } from "../../fonts/bundled-fonts";
import { RendererControls } from "./controls/RendererControls";
import { AxisControls } from "./controls/AxisControls";
import { SpecimenControls } from "./controls/SpecimenControls";
import { PreviewCanvas } from "./PreviewCanvas";
import { KerningPanel } from "./KerningPanel";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../../components/ui/card";

export interface FontEditorProps {
  font: StoredFont;
  settings: VariantSettings;
  sampleText: string;
  onSettings: (settings: VariantSettings) => void;
  onSampleText: (text: string) => void;
  onReset: () => void;
  zoom: number;
  pixelAccurate: boolean;
  onZoom: (zoom: number) => void;
  onPixelAccurate: (pixelAccurate: boolean) => void;
  fontReady: boolean;
  fontLoadError: string;
  ratio: number;
  previewStatus: string;
  onStatus: (message: string) => void;
}

// Shared native editor: persisted domain (settings + sample text) flows in as
// direct props while zoom, pixel accuracy, and panel state stay host-owned or
// local view state. Both the saved-variant editor and the legacy unsaved
// preview render through this component.
export function FontEditor({
  font, settings, sampleText, onSettings, onSampleText, onReset,
  zoom, pixelAccurate, onZoom, onPixelAccurate,
  fontReady, fontLoadError, ratio, previewStatus, onStatus,
}: FontEditorProps): React.JSX.Element {
  const { available: rendererAvailable } = useRenderer();
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const [kerningOpen, setKerningOpen] = React.useState(false);
  const [kerningFilter, setKerningFilter] = React.useState("");
  const license = font.source === "bundled" ? bundledLicense(font.fileName) : null;

  const patch = (next: Partial<VariantSettings>): void => {
    onSettings({ ...settings, ...next });
  };

  return (
    <>
      <div className="mt-5">
        <RendererControls
          profile={settings.profile}
          role={settings.renderer}
          stemFitting={settings.stemFitting}
          zoom={zoom}
          pixelAccurate={pixelAccurate}
          rendererAvailable={rendererAvailable}
          ratio={ratio}
          onProfile={(profile) => patch({ profile })}
          onRole={(renderer) => patch({ renderer })}
          onStemFitting={(stemFitting) => patch({ stemFitting })}
          onZoom={onZoom}
          onPixelAccurate={onPixelAccurate}
        />
      </div>
      {rendererAvailable === false && (
        <section className="content-state my-12 max-w-[45rem] leading-[1.6]" role="alert">
          <h2>Preview renderer unavailable.</h2>
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
            License: <a href={license.url}>{license.name}</a> (SIL Open Font License 1.1).
          </p>
        )}
        <KerningPanel
          ready={fontReady}
          fontId={font.id}
          fontName={displayName(font)}
          sizePx={settings.sizePx}
          axes={settings.axes}
          open={kerningOpen}
          filter={kerningFilter}
          onToggle={setKerningOpen}
          onFilter={(value) => setKerningFilter(value.slice(0, 64))}
        />
        <section className="interactive-specimen mt-0 mb-7">
          <AxisControls
            font={font}
            axes={settings.axes}
            advancedOpen={advancedOpen}
            onAxes={(axes) => patch({ axes })}
            onAdvancedOpen={setAdvancedOpen}
          />
          <Card className="interactive-preview gap-0 overflow-hidden py-0">
            <CardHeader className="px-4 pt-[.85rem]">
              <CardTitle className="pb-[.35rem] text-[1rem]">Interactive specimen</CardTitle>
              <CardDescription data-status role="status" hidden={!previewStatus && !fontLoadError}>
                {previewStatus || fontLoadError}
              </CardDescription>
            </CardHeader>
            <CardContent className="px-4">
              <SpecimenControls
                font={font}
                sizePx={settings.sizePx}
                spacingPx={settings.letterSpacingPx}
                kerning={settings.kerning}
                text={sampleText}
                onSize={(sizePx) => patch({ sizePx })}
                onSpacing={(letterSpacingPx) => patch({ letterSpacingPx })}
                onKerning={(kerning) => patch({ kerning })}
                onText={onSampleText}
                onReset={onReset}
              />
            </CardContent>
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
                zoom={zoom}
                pixelAccurate={pixelAccurate}
                onStatus={onStatus}
              />
            ) : (
              <p className="mx-4 mb-4 text-[.8rem] text-soft" role="status">Loading font into the renderer…</p>
            )}
          </Card>
        </section>
      </section>
    </>
  );
}
