import * as React from "react";
import { useDisplayPreferences } from "../../shell/DisplayPreferences";
import { libraryFrame } from "../library/canvas-palettes";
import { SpecimenFrame } from "../library/SpecimenFrame";
import capture from "./assets/rasterizers/capture.json";
import pdfontconv from "./assets/rasterizers/pdfontconv.png";
import tophat from "./assets/rasterizers/tophat.png";
import lvgl from "./assets/rasterizers/lvgl.png";
import adafruit from "./assets/rasterizers/adafruit.png";
import repo from "./assets/rasterizers/repo.png";

const images: Record<string, string> = { repo, pdfontconv, tophat, lvgl, adafruit };
const [sampleWidth, sampleHeight] = capture.display_size as [number, number];

export function RasterizerComparison(): React.JSX.Element {
  const { zoom, canvas: { palette, inverse } } = useDisplayPreferences();
  const frame = libraryFrame(palette, inverse);
  const filterId = `landing-colors-${React.useId().replace(/:/g, "")}`;
  return (
    <section className="landing__comparison" aria-labelledby="rasterizer-comparison-title">
      <div className="landing__section-heading">
        <h2 id="rasterizer-comparison-title">Compare font converters</h2>
        <p className="landing__section-intro">Roboto · 16 px · Light</p>
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
      <div className="landing__comparison-grid" data-rasterizer-comparison data-expanded={zoom > 1}>
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
                      <img src={images[sample.id]} width={sampleWidth * zoom} height={sampleHeight * zoom}
                        style={{ width: sampleWidth * zoom, height: sampleHeight * zoom, top: -line.top * zoom, filter: `url(#${filterId})` }}
                        alt={index === 0 ? `Roboto, 16 px, weight 300, width 100%, monochrome output from ${sample.label}.` : ""} />
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
