// Direct-font label render settings: assembled on the client from the
// library font and the scene's output curve, mirroring the domain's
// resolveTextStyle without a saved variant behind the label. The profile
// rule is owned by palettes/model.ts (client-safe), shared with the domain.
import { currentPreviewSettings, defaultVariantSettings, type VariantSettings } from "../../variants/model.ts";
import { profileForCurve } from "../../palettes/model.ts";
import { resolveWorkingPreviewPolicy } from "../../renderer/preview-policy.ts";
import type { StoredFont } from "../../fonts/storage.ts";
import type { GrayCurve } from "../../domain/output-profiles/curve.ts";
import type { FontExportStyleSnapshot } from "../../domain/font-export.ts";

export const DIRECT_LABEL_DEFAULT_SIZE_PX = 16;

export function directLabelProfile(curve: GrayCurve): VariantSettings["profile"] {
  return profileForCurve(curve);
}

export interface DirectWghtAxis {
  min: number;
  default: number;
  max: number;
}

// Usable wght bounds: finite numbers in min <= default <= max order.
function hasOrderedBounds(axis: unknown): axis is DirectWghtAxis {
  if (typeof axis !== "object" || axis === null) return false;
  const bounds = axis as { min?: unknown; default?: unknown; max?: unknown };
  return (
    Number.isFinite(bounds.min) &&
    Number.isFinite(bounds.default) &&
    Number.isFinite(bounds.max) &&
    (bounds.min as number) <= (bounds.default as number) &&
    (bounds.default as number) <= (bounds.max as number)
  );
}

// The font's wght axis from its stored metadata, when the font varies weight
// at all: the OpenType wght axis controls stroke-thickness/design variation
// on 1..1000 and the font's fvar supplies the supported min/default/max
// (https://learn.microsoft.com/en-us/typography/opentype/spec/dvaraxistag_wght).
export function directWghtAxis(font: StoredFont | null | undefined): DirectWghtAxis | null {
  const axes = Array.isArray(font?.metadata?.axes) ? font.metadata.axes : [];
  const axis = axes.find((entry) => entry?.tag === "wght");
  if (!hasOrderedBounds(axis)) return null;
  return { min: axis.min, default: axis.default, max: axis.max };
}

// The effective render weight: the direct override when set, otherwise the
// font's own default. Null when the font cannot vary weight, so callers never
// send an unsupported wght coordinate.
export function effectiveDirectWeight(font: StoredFont | null | undefined, fontWeight: number | null): number | null {
  const axis = directWghtAxis(font);
  if (!axis) return null;
  const wanted = fontWeight ?? axis.default;
  if (!Number.isFinite(wanted)) return axis.default;
  return Math.min(axis.max, Math.max(axis.min, wanted));
}

// Saved-variant resolve carries the same axes defaults, preview pipeline and
// policy; only the size comes from the label and the profile from the scene's
// output curve. No palette identity: the label references no saved variant.
// The effective weight resolves through the font's wght axis, so the default
// and an explicit same-value override produce identical settings.
export function directLabelSettings(
  font: StoredFont,
  fontSize: number,
  curve: GrayCurve,
  fontWeight: number | null = null,
): VariantSettings {
  const policy = resolveWorkingPreviewPolicy();
  const base = defaultVariantSettings(font);
  const effective = effectiveDirectWeight(font, fontWeight);
  // Renderer, rasterization and mono raster come from currentPreviewSettings
  // (pinned identical above), so this call site does not repeat them.
  return currentPreviewSettings({
    ...base,
    axes: effective === null ? base.axes : { ...base.axes, wght: effective },
    sizePx: fontSize,
    letterSpacingPx: 0,
    profile: directLabelProfile(curve),
    kerning: true,
    stemFitting: policy.fitting === "upstream_mono" ? "upstream_mono" : "font_hints_first",
    diagonalFitting: policy.diagonal_fitting,
  });
}

export interface DirectExportPlacement {
  fontId: string | null;
  fontSize: number | null;
  fontWeight: number | null;
}

// One export entry per distinct direct font/size/effective-weight on the
// scene, resolved with the same client settings as the preview. The default
// weight and an explicit same-value override share one entry: only the
// effective coordinate keys the snapshot, never the stored override.
export function directExportSnapshots(
  placements: readonly DirectExportPlacement[],
  fontsById: ReadonlyMap<string, StoredFont>,
  profileCurve: GrayCurve,
): FontExportStyleSnapshot[] {
  const seen = new Set<string>();
  const snapshots: FontExportStyleSnapshot[] = [];
  for (const placement of placements) {
    if (placement.fontId === null || placement.fontSize === null) continue;
    const font = fontsById.get(placement.fontId);
    if (!font) continue;
    const effective = effectiveDirectWeight(font, placement.fontWeight);
    const key = `${placement.fontId}/${placement.fontSize}/${effective ?? "default"}`;
    if (seen.has(key)) continue;
    seen.add(key);
    snapshots.push({
      id: `direct:${placement.fontId}:${placement.fontSize}:${effective ?? "default"}`,
      name: font.name,
      fontId: placement.fontId,
      settings: directLabelSettings(font, placement.fontSize, profileCurve, placement.fontWeight),
    });
  }
  return snapshots;
}
