import * as React from "react";
import { MAX_TEXT_LENGTH, TEXT_DEFAULT } from "../../renderer/render-spec";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";

export const INDEX_ZOOM_MIN = 1;
export const INDEX_ZOOM_MAX = 4;

interface LibrarySidebarProps {
  sampleText: string;
  sampleZoom: number;
  importStatus: string;
  onSampleText: (text: string) => void;
  onSampleZoom: (zoom: number) => void;
  onImport: (files: FileList | null) => void;
}

// Library control panel: sample text, zoom, and font import moved out of the
// sticky header into a named aside beside the cards. All selectors, labels,
// and callbacks are unchanged so existing tests keep working.
export function LibrarySidebar({
  sampleText, sampleZoom, importStatus, onSampleText, onSampleZoom, onImport,
}: LibrarySidebarProps): React.JSX.Element {
  return (
    <aside
      aria-labelledby="library-controls-heading"
      className="w-full shrink-0 lg:w-64"
    >
      <h2 id="library-controls-heading" className="m-0 text-[1rem] font-[650] tracking-[-.02em]">
        Library controls
      </h2>
      <div className="mt-4 flex flex-col gap-5">
        <div className="flex w-full flex-col gap-[.35rem] text-[.8rem]">
          <Label htmlFor="index-sample">Sample text</Label>
          <Input
            id="index-sample"
            data-index-text
            type="text"
            autoComplete="off"
            spellCheck={false}
            maxLength={MAX_TEXT_LENGTH}
            placeholder={TEXT_DEFAULT}
            value={sampleText}
            onChange={(event) => onSampleText(event.target.value.slice(0, MAX_TEXT_LENGTH))}
          />
        </div>
        <div className="flex w-full flex-col gap-[.35rem] text-[.8rem]">
          <div className="flex items-baseline justify-between gap-2">
            <Label htmlFor="index-zoom">Zoom</Label>
            <output id="index-zoom-value" htmlFor="index-zoom">{`${sampleZoom}×`}</output>
          </div>
          <input
            id="index-zoom"
            data-index-zoom
            type="range"
            min={INDEX_ZOOM_MIN}
            max={INDEX_ZOOM_MAX}
            step={1}
            value={sampleZoom}
            aria-valuetext={`${sampleZoom}×`}
            onChange={(event) => {
              const zoom = Number(event.target.value);
              if (Number.isFinite(zoom)) onSampleZoom(Math.min(INDEX_ZOOM_MAX, Math.max(INDEX_ZOOM_MIN, zoom)));
            }}
            className="mx-0 my-[.35rem] block w-full cursor-pointer accent-brand"
          />
        </div>
        <div className="font-import m-0 flex flex-col items-start gap-[.6rem] text-[.875rem]">
          <Input
            type="file"
            accept=".ttf,.otf"
            data-import-font
            aria-label="Import a font file"
            className="w-full text-[.8rem] font-normal"
            onChange={(event) => { onImport(event.target.files); event.target.value = ""; }}
          />
          {importStatus && <span className="font-normal text-soft" role="status" data-import-status>{importStatus}</span>}
        </div>
      </div>
    </aside>
  );
}
