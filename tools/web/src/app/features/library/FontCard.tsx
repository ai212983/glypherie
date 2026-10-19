import * as React from "react";
import type { StoredFont } from "../../fonts/storage.js";
import { classificationLabel, displayName } from "../../fonts/metadata";
import type { FontVariant } from "../../variants/model.js";
import { variantHash } from "../../navigation/router.js";
import { NavLink } from "../../../components/NavLink";
import { CardPreview } from "./CardPreview";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../../components/ui/card";
import type { FontLibrary } from "../../fonts/useFontLibrary";

interface FontCardProps {
  font: StoredFont;
  text: string;
  zoom: number;
  library: FontLibrary;
  variants: FontVariant[] | undefined;
  onAddVariant: (font: StoredFont) => Promise<void>;
  onOpenVariant: (font: StoredFont, variant: FontVariant) => void;
  onDeleteFont: (font: StoredFont) => void;
}

// Plain container: the card itself is not clickable. Saved variants are the
// clickable child rows; Add variant creates a default saved variant first and
// navigates only after the write commits.
export function FontCard({ font, text, zoom, library, variants, onAddVariant, onOpenVariant, onDeleteFont }: FontCardProps): React.JSX.Element {
  const [adding, setAdding] = React.useState(false);
  const [addError, setAddError] = React.useState("");
  const load = library.loadStatus(font.id);
  const onAdd = (): void => {
    if (adding) return;
    setAdding(true);
    setAddError("");
    void onAddVariant(font)
      .catch((error: unknown) => {
        setAddError(error instanceof Error ? error.message : String(error ?? ""));
      })
      .finally(() => setAdding(false));
  };
  return (
    <Card data-font-card={font.id} className="min-w-0">
      <CardHeader className="px-4 pt-4">
        <CardTitle className="text-[1.05rem]" data-font-name={font.id}>
          {displayName(font)}
        </CardTitle>
        {classificationLabel(font.metadata) && (
          <CardDescription className="wrap-anywhere">
            {classificationLabel(font.metadata)}
          </CardDescription>
        )}
      </CardHeader>
      <CardPreview
        font={font}
        text={text}
        zoom={zoom}
        loaded={library.loadedIds.has(font.id)}
        loadError={load.state === "error" ? load.error : ""}
      />
      <CardContent className="px-4 pb-4 text-[.8rem] text-soft">
        <p className="m-0">{font.source === "uploaded" ? "Imported font" : "Bundled font"}</p>
        <ul className="m-0 mt-2 list-none p-0" data-variant-list={font.id} aria-label={`${displayName(font)} variants`}>
          {(variants ?? []).map((variant) => (
            <li key={variant.id} className="min-w-0">
              <NavLink
                href={`${window.location.pathname}${variantHash(font.id, variant.id)}`}
                data-variant-link={variant.id}
                data-variant-font={font.id}
                aria-label={variant.name}
                onNavigate={() => onOpenVariant(font, variant)}
              >
                {variant.name}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button
            data-add-variant={font.id}
            size="sm"
            onClick={onAdd}
            disabled={adding}
          >
            {adding ? "Adding…" : variants === undefined ? "Add variant" : `Add variant${variants.length > 0 ? ` (${variants.length})` : ""}`}
          </Button>
          <Button data-delete-font={font.id} variant="destructive" size="sm" onClick={() => onDeleteFont(font)}>
            Delete font
          </Button>
        </div>
        {addError && (
          <p className="m-0 mt-2" role="alert" data-add-variant-error={font.id}>{addError}</p>
        )}
      </CardContent>
    </Card>
  );
}
