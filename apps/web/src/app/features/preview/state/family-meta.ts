import type { StoredFont } from "../../../fonts/storage.js";
import { controlAxes, defaultAxesValue } from "../../../fonts/metadata.ts";
import { TEXT_DEFAULT } from "../../../renderer/render-spec.ts";
import { TEXT_PRESETS } from "../presets.ts";
import {
  presetForText,
  type FamilyMeta,
} from "./snapshot-codec.ts";

export function metaForFont(font: StoredFont): FamilyMeta {
  const axes = controlAxes(font.metadata);
  const presets = TEXT_PRESETS.filter((preset) => preset.id !== "custom")
    .map((preset) => ({ id: preset.id, content: preset.content }));
  return {
    id: font.id,
    defaultSize: 16,
    defaultAxes: defaultAxesValue(axes),
    axes: axes.map((axis) => ({
      tag: axis.tag, min: axis.min, max: axis.max, defaultValue: axis.defaultValue, hidden: axis.hidden,
    })),
    sampleText: TEXT_DEFAULT,
    presets,
    defaultPreset: presetForText(presets, TEXT_DEFAULT),
  };
}

export function buildMetas(fonts: StoredFont[]): FamilyMeta[] {
  return fonts.map(metaForFont);
}
