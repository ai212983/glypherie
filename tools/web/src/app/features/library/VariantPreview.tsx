import { userError } from "../../user-error";
import * as React from "react";
import type { FontVariant } from "../../variants/model.js";
import { deleteVariant, VariantStorageError } from "../../variants/repository.js";
import { variantPath } from "../../navigation/router.js";
import { NavLink } from "../../../components/NavLink";
import { SpecimenRow } from "./SpecimenRow";
import { FontCanvas } from "../../renderer/FontCanvas.js";
import { libraryFrame, type CanvasPaletteId } from "./canvas-palettes.js";

import { usePalettes } from "../../palettes/usePalettes";
import { resolvePalette } from "../../palettes/model";
import { paletteProfile, presetColors } from "../../palettes/render";
import { currentPreviewSettings } from "../../variants/model";

interface VariantPreviewProps {
  fontId: string;
  variant: FontVariant;
  zoom: number;
  palette: CanvasPaletteId;
  inverse: boolean;
  loaded: boolean;
  loadError: string;
  onOpen: (variant: FontVariant) => void;
  selected?: boolean;
  sampleText?: string;
  onDeleted?: (variant: FontVariant) => void;
}

export function VariantPreview({
  fontId, variant, zoom, palette, inverse, loaded, loadError, onOpen, selected = false, sampleText, onDeleted,
}: VariantPreviewProps): React.JSX.Element {
  const [error, setError] = React.useState("");
  const [missing, setMissing] = React.useState(0);
  const [truncated, setTruncated] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState("");
  const { presets } = usePalettes();
  const preset = resolvePalette(presets, variant.settings.paletteId);
  const settings = currentPreviewSettings({ ...variant.settings, profile: paletteProfile(preset) });
  const colors = React.useMemo(() => presetColors(preset, palette, inverse), [preset, palette, inverse]);
  const text = sampleText ?? variant.sampleText;
  const empty = text.length === 0;
  const frame = libraryFrame(palette, inverse);
  const onDelete = (): void => {
    if (deleting) return;
    setDeleting(true);
    setDeleteError("");
    void deleteVariant(variant.id, variant.revision)
      .then(() => onDeleted?.(variant))
      .catch((failure: unknown) => {
        setDeleteError(
          failure instanceof VariantStorageError && failure.code === "conflict"
            ? "This variant changed in another tab. Review it before trying again."
            : userError(failure, "Couldn’t delete variant."),
        );
      })
      .finally(() => setDeleting(false));
  };

  React.useEffect(() => {
    if (empty) {
      setError("");
      setMissing(0);
      setTruncated(false);
    }
  }, [empty]);

  return (
    <SpecimenRow
      frame={frame}
      selected={selected}
      name={variant.name}
      caption={<span data-library-variant-caption={variant.id}>{`${settings.sizePx} px / ${Math.log2(preset.curve.length)}-bit`}</span>}
      tintAttributes={{ "data-library-variant-tint": variant.id }}
      action={
        <NavLink
          href={variantPath(fontId, variant.id)}
          data-variant-link={variant.id}
          data-variant-font={fontId}
          aria-label={variant.name}
          aria-current={selected ? "page" : undefined}
          onNavigate={() => onOpen(variant)}
        />
      }
      deleteButton={{
        "data-delete-variant": variant.id,
        "aria-label": deleting ? `Deleting variant ${variant.name}…` : `Delete variant ${variant.name}`,
        onClick: onDelete,
        disabled: deleting,
      }}
      deleteError={deleteError && (
        <p className="m-0 pt-2 text-right font-studio text-[10px] leading-4 text-destructive" role="alert" data-delete-variant-error={variant.id}>{deleteError}</p>
      )}
    >
      {!empty && (
        <div className="pt-1">
          <FontCanvas
            fontId={fontId}
            text={text}
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
            mode="exact"
            palette={colors}
            ready={loaded && !loadError}
            debounceMs={0}
            clearOnError
            viewportProps={{ "data-library-variant-preview": variant.id, "aria-hidden": true, className: "block min-w-0 overflow-hidden" }}
            canvasProps={{ "data-library-variant-canvas": variant.id, className: "block [image-rendering:pixelated]" }}
            debugIdentity={(width) => ({
              variant: variant.id,
              width,
              size: settings.sizePx,
              zoom,
              text,
              palette,
              inverse,
              profile: settings.profile,
              axes: settings.axes,
              spacing: settings.letterSpacingPx,
              kerning: settings.kerning,
              stemFitting: settings.stemFitting,
              diagonalFitting: settings.diagonalFitting,
              monoRaster: settings.monoRaster,
              rasterization: settings.rasterization,
              role: settings.renderer,
            })}
            exposeFullHeight
            onPaint={(diagnostics) => {
              setMissing(diagnostics.missing);
              setTruncated(diagnostics.truncated);
              setError("");
            }}
            onError={(message) => {
              setMissing(0);
              setTruncated(false);
              console.warn("Variant preview failed", message);
              setError("Couldn’t render preview.");
            }}
          />
        </div>
      )}
      {(loadError || error) && (
        <p data-library-variant-error={variant.id} className="px-0 pt-2 font-studio text-[10px] leading-4" style={{ color: frame.mutedCss }}>{loadError || error}</p>
      )}
      {!loadError && !error && !empty && truncated && (
        <p data-library-variant-limit={variant.id} className="px-0 pt-2 font-studio text-[10px] leading-4" style={{ color: frame.mutedCss }}>
          Preview truncated. Shorten the text or reduce zoom.
        </p>
      )}
      {!loadError && !error && !empty && missing > 0 && (
        <p data-library-variant-glyphs={variant.id} className="px-0 pt-2 font-studio text-[10px] leading-4" style={{ color: frame.mutedCss }}>
          {`${missing} character${missing === 1 ? "" : "s"} not in this font.`}
        </p>
      )}
    </SpecimenRow>
  );
}
