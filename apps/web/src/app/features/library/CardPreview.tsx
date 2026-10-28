import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import { displayName } from "../../fonts/metadata";
import type { FontVariant } from "../../variants/model.js";
import { SourcePreview } from "./SourcePreview";
import { libraryFrame, type CanvasPaletteId } from "./canvas-palettes.js";
import { SpecimenFrame, SpecimenFooter } from "./SpecimenFrame";
import { VariantPreview } from "./VariantPreview";
import type { LibraryBaseSize } from "./preferences.js";

interface CardPreviewProps {
  font: StoredFont;
  text: string;
  baseSize: LibraryBaseSize;
  zoom: number;
  palette: CanvasPaletteId;
  inverse: boolean;
  loaded: boolean;
  loadError: string;
  variants: FontVariant[] | undefined;
  onOpenVariant: (variant: FontVariant) => void;
  footer?: React.ReactNode;
}

// Source font and generated variant rows share the display frame.
export function CardPreview({ font, text, baseSize, zoom, palette, inverse, loaded, loadError, variants, onOpenVariant, footer }: CardPreviewProps): React.JSX.Element {
  const empty = text.length === 0;
  const frame = libraryFrame(palette, inverse);
  const rows = variants ?? [];
  const rowsPresent = rows.length > 0;
  return (
    <>
      <SpecimenFrame frame={frame} data-card-frame={font.id} className="mx-4">
        <div className="flex min-h-5 w-full min-w-0 items-center gap-2 font-studio text-[9px] leading-4">
          <span className="min-w-0 flex-1 text-left [overflow-wrap:anywhere]" style={{ color: frame.inkCss }}>
            Source
          </span>
          <span className="shrink-0" style={{ color: frame.mutedCss }}>
            {`${baseSize} px`}
          </span>
        </div>
        {!empty && <SourcePreview font={font} text={text} sizePx={baseSize} zoom={zoom} ink={frame.inkCss} />}
        {rowsPresent && (
          <ul data-variant-list={font.id} aria-label={`${displayName(font)} variants`} className="mt-3 mb-0 list-none p-0">
            {rows.map((variant) => (
              <li
                key={variant.id}
                data-library-variant-row={variant.id}
                className="border-t py-1"
                style={{ borderColor: frame.dividerCss }}
              >
                <VariantPreview
                  fontId={font.id}
                  variant={variant}
                  zoom={zoom}
                  palette={palette}
                  inverse={inverse}
                  loaded={loaded}
                  loadError={loadError}
                  onOpen={onOpenVariant}
                />
              </li>
            ))}
          </ul>
        )}
        {footer && (
          <SpecimenFooter frame={frame} bordered={rowsPresent || !empty} className={!rowsPresent ? "mt-3" : undefined}>
            {footer}
          </SpecimenFooter>
        )}
      </SpecimenFrame>
    </>
  );
}
