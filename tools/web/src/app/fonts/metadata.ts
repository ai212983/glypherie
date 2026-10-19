// Font-metadata views for the library UI. Field names follow the actual
// WASM metadata contract (names, axes, kerning, style, classification,
// coverage); axis control ranges reuse the legacy rules (integer steps when
// min/default/max are all integers, name falls back to the tag).
import type { FontMetadata, StoredFont } from "./storage.js";

export interface AxisControl {
  tag: string;
  name: string;
  min: number;
  max: number;
  defaultValue: number;
  hidden: boolean;
  step: number;
}

const AXIS_TAG = /^[\x20-\x7e]{4}$/;

interface RawAxis {
  tag: unknown;
  name: unknown;
  min: unknown;
  default: unknown;
  max: unknown;
  hidden: unknown;
}

export function controlAxes(metadata: FontMetadata | null | undefined): AxisControl[] {
  const raw = metadata && Array.isArray((metadata as { axes?: unknown }).axes)
    ? (metadata as { axes: RawAxis[] }).axes : [];
  return raw
    .filter((axis) => axis && typeof axis.tag === "string" && AXIS_TAG.test(axis.tag)
      && [axis.min, axis.default, axis.max].every((value) => Number.isFinite(value as number))
      && (axis.min as number) <= (axis.default as number) && (axis.default as number) <= (axis.max as number))
    .map((axis) => ({
      tag: axis.tag as string,
      name: typeof axis.name === "string" && axis.name.trim() ? axis.name : axis.tag as string,
      min: axis.min as number,
      defaultValue: axis.default as number,
      max: axis.max as number,
      hidden: axis.hidden === true,
      step: [axis.min, axis.default, axis.max].every((value) => Number.isInteger(value as number)) ? 1 : 0.1,
    }));
}

export function defaultAxesValue(axes: AxisControl[]): Record<string, number> {
  return Object.fromEntries(axes.map((axis) => [axis.tag, axis.defaultValue]));
}

export function classificationLabel(metadata: FontMetadata | null | undefined): string | null {
  if (!metadata) return null;
  const names = (metadata as { names?: Record<string, string | null> }).names ?? {};
  const parts: string[] = [];
  const family = names.family;
  void family;
  const style = (metadata as { style?: { slope?: string; weight_class?: number } }).style;
  if (style && typeof style.slope === "string" && style.slope !== "upright") parts.push(style.slope);
  const kerning = (metadata as { kerning?: { horizontal?: boolean; sources?: string[] } }).kerning;
  const sources = Array.isArray(kerning?.sources)
    ? kerning.sources.filter((source) => typeof source === "string" && source.trim())
    : [];
  parts.push(kerning && kerning.horizontal === true
    ? sources.length ? `Source kerning available (${sources.join(", ")}).` : "Source kerning available."
    : "No horizontal source kerning.");
  const coverage = (metadata as { coverage?: { character_count?: number } }).coverage;
  if (coverage && Number.isFinite(coverage.character_count)) {
    parts.push(`${coverage.character_count} encoded characters.`);
  }
  return parts.length ? parts.join(" ") : null;
}

export function displayName(font: StoredFont): string {
  const names = font.metadata?.names as Record<string, string | null> | undefined;
  const full = names && typeof names.full === "string" ? names.full : null;
  if (full && full.trim()) return full;
  const family = names && typeof names.family === "string" ? names.family : null;
  if (family && family.trim()) return family;
  return font.name || font.fileName;
}
