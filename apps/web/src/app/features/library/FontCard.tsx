import * as React from "react";
import { TooltipHint } from "../../../components/TooltipHint";
import { Trash2Icon } from "lucide-react";
import type { StoredFont } from "../../fonts/storage.js";
import { displayName } from "../../fonts/metadata";
import type { FontVariant } from "../../variants/model.js";
import { CardPreview } from "./CardPreview";
import { FontInfoBoxes } from "./FontInfoBoxes";
import { AddVariantButton } from "./AddVariantButton";
import { Button } from "../../../components/ui/button";
import { Badge } from "../../../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../../components/ui/card";
import type { FontLibrary } from "../../fonts/useFontLibrary";
import type { CanvasPaletteId } from "./canvas-palettes";
import type { LibraryBaseSize } from "./preferences";

interface FontCardProps {
  font: StoredFont;
  text: string;
  baseSize: LibraryBaseSize;
  zoom: number;
  palette: CanvasPaletteId;
  inverse: boolean;
  library: FontLibrary;
  variants: FontVariant[] | undefined;
  onAddVariant: (font: StoredFont) => Promise<void>;
  onOpenVariant: (font: StoredFont, variant: FontVariant) => void;
  onDeleteFont: (font: StoredFont) => void;
}

// Plain container: the card itself is not clickable. Saved variants are the
// clickable child rows; Add variant creates a default saved variant first and
// navigates only after the write commits.
export function FontCard({ font, text, baseSize, zoom, palette, inverse, library, variants, onAddVariant, onOpenVariant, onDeleteFont }: FontCardProps): React.JSX.Element {
  const load = library.loadStatus(font.id);
  return (
    <Card variant="plain" data-font-card={font.id} className="min-w-0 rounded-[16px] border-studio-border bg-font-card py-0 shadow-studio-card">
      <CardHeader className="gap-0 px-4 pt-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
            <CardTitle className="min-w-0 font-display text-[16px] leading-6 font-bold tracking-[0.4px] text-studio-foreground" data-font-name={font.id}>
              {displayName(font)}
            </CardTitle>
            {font.source === "bundled" && <Badge variant="outline" className="shrink-0 border-studio-border bg-studio-inset px-2 py-0.5 font-studio text-[9px] leading-4 font-bold text-studio-muted shadow-studio-inset">
              Bundled
            </Badge>}
          </div>
          <Button
            variant="ghost"
            size="icon"
            data-delete-font={font.id}
            aria-label={`Delete font ${displayName(font)}`}
            onClick={() => onDeleteFont(font)}
            className="shrink-0 text-studio-muted hover:text-destructive"
          >
            <Trash2Icon className="size-4" aria-hidden="true" />
          </Button>
        </div>

        {typeof font.metadata.names.description === "string" && font.metadata.names.description.trim() !== "" && (
          <TooltipHint content={font.metadata.names.description.trim()}>
            <CardDescription
              className="wrap-anywhere font-studio text-[11px] leading-4 font-normal text-studio-muted line-clamp-2"
            >
              {font.metadata.names.description.trim()}
            </CardDescription>
          </TooltipHint>
        )}
      </CardHeader>
      <CardPreview
        font={font}
        text={text}
        baseSize={baseSize}
        zoom={zoom}
        palette={palette}
        inverse={inverse}
        loaded={library.loadedIds.has(font.id)}
        loadError={load.state === "error" ? load.error : ""}
        variants={variants}
        onOpenVariant={(variant) => onOpenVariant(font, variant)}
        footer={<AddVariantButton font={font} onAdd={onAddVariant} />}
      />
      <CardContent className="px-4 pb-4 text-[.8rem] text-soft">
        <FontInfoBoxes font={font} />

      </CardContent>
    </Card>
  );
}
