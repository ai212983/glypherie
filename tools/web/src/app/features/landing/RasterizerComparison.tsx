import * as React from "react";
import { useDisplayPreferences } from "../../shell/DisplayPreferences";
import { libraryFrame } from "../library/canvas-palettes";
import { SpecimenFrame } from "../library/SpecimenFrame";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "../../../components/ui/toggle-group";
import matrix from "./assets/rasterizers/matrix.json";
import familyChevron from "./assets/family-chevron.svg";

const images = import.meta.glob<string>("./assets/rasterizers/samples/*/*.png", {
  eager: true, query: "?url", import: "default",
});
const defaultSample = matrix.cases.find((entry) => entry.family_id === "roboto" && entry.size_px === 16) ?? matrix.cases[0]!;

export function RasterizerComparison(): React.JSX.Element {
  const [family, setFamily] = React.useState(defaultSample.family_id);
  const [size, setSize] = React.useState(defaultSample.size_px);
  const capture = matrix.cases.find((entry) => entry.family_id === family && entry.size_px === size)!;
  const [sampleWidth, sampleHeight] = capture.display_size as [number, number];
  const sampleDescription = `${capture.family_label} · ${capture.size_px} px`;
  const { zoom, canvas: { palette, inverse } } = useDisplayPreferences();
  const frame = libraryFrame(palette, inverse);
  const filterId = `landing-colors-${React.useId().replace(/:/g, "")}`;
  return (
    <section className="landing__comparison" aria-labelledby="rasterizer-comparison-title">
      <div className="landing__comparison-heading">
        <div className="landing__section-heading">
          <h2 id="rasterizer-comparison-title">Compare font converters</h2>
          <p className="landing__active-specimen" role="status">Active specimen: <strong>{sampleDescription}</strong></p>
        </div>
        <div className="landing__specimen-controls">
          <Select value={family} onValueChange={setFamily}>
            <SelectTrigger aria-label="Sample font family" className="landing__family-select"
              icon={<img src={familyChevron} width="19.5" height="19.5" alt="" />}>
              <span className="landing__family-label" aria-hidden="true">Family:</span>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {matrix.families.map((entry) => <SelectItem key={entry.id} value={entry.id}>{entry.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <ToggleGroup type="single" value={String(size)} aria-label="Sample font size" className="landing__size-switcher"
            onValueChange={(value) => { if (value) setSize(Number(value)); }}>
            {matrix.sizes.map((sizePx) => <ToggleGroupItem key={sizePx} value={String(sizePx)} aria-label={`${sizePx} pixels`}
              onFocus={() => setSize(sizePx)}>
              {sizePx}px
            </ToggleGroupItem>)}
          </ToggleGroup>
        </div>
      </div>
      {/* Map binary ink coverage to the shared palette.
          https://drafts.csswg.org/filter-effects/#feColorMatrixElement */}
      <svg width="0" height="0" className="absolute pointer-events-none" aria-hidden="true" focusable="false">
        <defs>
          <filter id={filterId} colorInterpolationFilters="sRGB" x="0" y="0" width="100%" height="100%">
            <feColorMatrix in="SourceGraphic" type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -1 0 0 0 1" result="ink-mask" />
            <feFlood floodColor={frame.inkCss} result="ink" />
            <feComposite in="ink" in2="ink-mask" operator="in" result="glyphs" />
            <feFlood floodColor={frame.paperCss} result="paper" />
            <feMerge><feMergeNode in="paper" /><feMergeNode in="glyphs" /></feMerge>
          </filter>
        </defs>
      </svg>
      <div className="landing__comparison-grid" data-rasterizer-comparison data-family={family} data-size={size} data-expanded={zoom > 1}>
        {capture.samples.map((sample) => (
          <figure key={sample.id} data-rasterizer={sample.id} className="landing__comparison-sample">
            <SpecimenFrame frame={frame} data-rasterizer-frame={sample.id}>
              <div className="landing__preview-label">
                <h3 style={{ color: frame.inkCss }}><a href={sample.source_url}>{sample.label}</a></h3>
              </div>
              <div className="landing__comparison-scroll" role="region" aria-label={`${sample.label} sample`} tabIndex={0}>
                <div data-rasterizer-lines className="landing__comparison-lines"
                  style={{ width: sampleWidth * zoom, rowGap: capture.display_line_gap * zoom }}>
                  {capture.display_lines.map((line, index) => (
                    <div key={line.top} className="landing__comparison-line" style={{ height: line.height * zoom }}>
                      <img src={images[`./assets/rasterizers/${sample.file}`]} width={sampleWidth * zoom} height={sampleHeight * zoom}
                        style={{ width: sampleWidth * zoom, height: sampleHeight * zoom, top: -line.top * zoom, filter: `url(#${filterId})` }}
                        alt={index === 0 ? `${sampleDescription}, monochrome output from ${sample.label}.` : ""} />
                    </div>
                  ))}
                </div>
              </div>
            </SpecimenFrame>
          </figure>
        ))}
      </div>
    </section>
  );
}
