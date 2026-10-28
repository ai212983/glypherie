import * as React from "react";
import { Layers } from "lucide-react";
import type { StoredFont } from "../../fonts/storage";
import type { FontLibrary } from "../../fonts/useFontLibrary";
import { useFontVariants } from "../../variants/useFontVariants";
import { useDisplayPreferences } from "../../shell/DisplayPreferences";
import { libraryFrame } from "../library/canvas-palettes";
import { SpecimenListCard, SpecimenListItem } from "../library/SpecimenListCard";
import { VariantPreview } from "../library/VariantPreview";
import { AddVariantButton } from "../library/AddVariantButton";
import { SourcePreview } from "../library/SourcePreview";
import type { LibraryBaseSize } from "../library/preferences";
import { Button } from "../../../components/ui/button";

interface VariantListProps {
  font: StoredFont;
  variantId: string;
  library: FontLibrary;
  text: string;
  baseSize: LibraryBaseSize;
  onText: (text: string) => void;
  onAdd: (font: StoredFont) => Promise<void>;
  onOpen: (fontId: string, variantId: string) => void;
  onLastDeleted: (name: string) => void;
}

export function VariantList({ font, variantId, library, text, baseSize, onText, onAdd, onOpen, onLastDeleted }: VariantListProps): React.JSX.Element {
  const live = useFontVariants(font.id);
  const { zoom, canvas: { palette, inverse } } = useDisplayPreferences();
  const frame = libraryFrame(palette, inverse);
  const load = library.loadStatus(font.id);
  return (
    <SpecimenListCard title={<><Layers aria-hidden="true" className="size-3" />Variants</>}
      label="Variants" frame={frame} text={text} onText={onText}
      footer={<AddVariantButton font={font} onAdd={onAdd} />}>
      <SpecimenListItem frame={frame}>
        <div className="flex min-h-5 w-full min-w-0 items-center gap-2 font-studio text-[9px] leading-4">
          <span className="min-w-0 flex-1 text-left [overflow-wrap:anywhere]" style={{ color: frame.inkCss }}>Source</span>
          <span className="shrink-0" style={{ color: frame.mutedCss }}>{`${baseSize} px`}</span>
        </div>
        {text.length > 0 && <SourcePreview font={font} text={text} sizePx={baseSize} zoom={zoom} ink={frame.inkCss} />}
      </SpecimenListItem>
      {live.status !== "ready" ? (
        <SpecimenListItem frame={frame}>
          {live.status === "loading" ? <p role="status">Loading variants…</p> : (
            <div role="alert">
              <p>{live.message}</p>
              <Button size="sm" variant="outline" onClick={live.retry}>Retry</Button>
            </div>
          )}
        </SpecimenListItem>
      ) : live.variants.map((variant) => (
        <SpecimenListItem key={variant.id} frame={frame}>
          <VariantPreview fontId={font.id} variant={variant} selected={variant.id === variantId}
            zoom={zoom} palette={palette} inverse={inverse} sampleText={text}
            loaded={library.loadedIds.has(font.id)} loadError={load.state === "error" ? load.error : ""}
            onOpen={(next) => onOpen(font.id, next.id)}
            onDeleted={(removed) => {
              if (removed.id !== variantId) return;
              const next = live.variants.find((entry) => entry.id !== removed.id);
              if (next) onOpen(font.id, next.id);
              else onLastDeleted(removed.name);
            }} />
        </SpecimenListItem>
      ))}
    </SpecimenListCard>
  );
}
