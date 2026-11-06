// Canonical domain graph definition. Seven authored nodes; FontBinary lives
// as a relational bytea table beside the graph (domain/backend.ts), never as
// a node. No duplicate bits/levels/mode alongside the curve: depth derives
// from curve length. No PalettePreset graph entity. Coordinates sit on the
// native pixel grid; placement order is a stable integer.
//
// Provenance: node/edge names follow docs/domain-model.md; coverage handling
// mirrors CrossGlyph consecutive-run semantics via domain/coverage.ts.

import { defineEdge, defineGraph, defineNode } from "@nicia-ai/typegraph/core";
import { z } from "zod";
import { normalizeCoverage, type CharacterCoverage } from "./coverage.ts";
import { validateKerningPreference } from "../kerning/model.ts";

// ---- Shared scalars (legacy numeric semantics preserved 1:1) ----

export const FONT_SIZE_MIN = 1;
export const FONT_SIZE_MAX = 512;
export const LETTER_SPACING_MIN = -2;
export const LETTER_SPACING_MAX = 4;
export const STYLE_NAME_MAX_LENGTH = 120;
export const SCENE_NAME_MAX_LENGTH = 120;
export const SCENE_DIMENSION_MIN = 1;
export const SCENE_DIMENSION_MAX = 4096;
export const LABEL_TEXT_MAX_LENGTH = 8192;

const fontSizeSchema = z.number().min(FONT_SIZE_MIN).max(FONT_SIZE_MAX);
const letterSpacingSchema = z.number().min(LETTER_SPACING_MIN).max(LETTER_SPACING_MAX);
const revisionSchema = z.number().int().min(1);
const timestampSchema = z.number().int().min(0);

// ---- Font metadata (tolerant reader: known fields validated, extras kept) ----

const axisMetadataSchema = z.looseObject({
  tag: z.string(),
  name: z.string().nullable(),
  min: z.number(),
  default: z.number(),
  max: z.number(),
  hidden: z.boolean(),
});

export const fontMetadataSchema = z.looseObject({
  names: z.record(z.string(), z.string().nullable()),
  axes: z.array(axisMetadataSchema),
});

export type FontMetadataProps = z.infer<typeof fontMetadataSchema>;

// ---- GrayCurve (bit depth derives from level count; slopes/pins kept) ----

export const GRAY_LEVEL_COUNTS = [2, 4, 8, 16] as const;

const curveLevelSchema = z.object({
  value: z.number(),
  slope: z.number(),
  pinned: z.boolean(),
});

export const grayCurveSchema = z
  .array(curveLevelSchema)
  .min(2)
  .max(16)
  .refine(
    (curve) => {
      if (!(GRAY_LEVEL_COUNTS as readonly number[]).includes(curve.length)) return false;
      const first = curve[0];
      const last = curve[curve.length - 1];
      if (!first?.pinned || !last?.pinned) return false;
      return curve.every(
        (level) =>
          Number.isFinite(level.value) &&
          level.value >= 0 &&
          level.value <= 255 &&
          Number.isFinite(level.slope) &&
          typeof level.pinned === "boolean",
      );
    },
    { message: "GrayCurve needs 2, 4, 8 or 16 pinned-endpoint levels with values 0..255." },
  );

export type GrayCurveProps = z.infer<typeof grayCurveSchema>;

// ---- Kerning preference (validated, shape-preserving; legacy booleans ----
// stay booleans so saved-variant DTOs round-trip exactly). Rendering paths
// normalize through normalizeKerning at the boundary.

const kerningPreferenceObjectSchema = z
  .object({
    method: z.enum(["source", "typefacet", "hu_hersch", "fontforge"]),
    source: z.object({ enabled: z.boolean() }),
    typefacet: z.object({
      normalDistanceEm: z.number(),
      intrusionToleranceEm: z.number(),
      minimumDistanceEm: z.number().optional(),
      maxXExtremaOverlapEm: z.number().optional(),
    }),
    hu_hersch: z.strictObject({
      apertureDepthFactor: z.number().optional(),
      globalDepthFactor: z.number().optional(),
    }).optional(),
    fontforge: z.strictObject({}).optional(),
  })
  .refine(
    (value) => {
      try {
        validateKerningPreference(value);
        return true;
      } catch {
        return false;
      }
    },
    { message: "Kerning settings carry invalid method values." },
  );

export const kerningPreferenceSchema = z.union([z.boolean(), kerningPreferenceObjectSchema]);

export type KerningStateProps = z.infer<typeof kerningPreferenceSchema>;

// ---- CharacterCoverage (numeric intervals canonical; presets by id) ----

const codepointRangeSchema = z.object({ start: z.number().int(), end: z.number().int() });

export const characterCoverageSchema = z
  .object({
    presetIds: z.array(z.enum(["ascii", "latin", "greek", "cyrillic", "symbols", "reading"])),
    extraRanges: z.array(codepointRangeSchema),
  })
  .transform((value): CharacterCoverage => normalizeCoverage(value));

export type CoverageProps = z.infer<typeof characterCoverageSchema>;

// ---- Nodes ----

const Font = defineNode("Font", {
  schema: z.object({
    name: z.string().min(1),
    fileName: z.string().min(1),
    metadata: fontMetadataSchema,
    source: z.enum(["bundled", "uploaded"]),
    addedAt: timestampSchema,
  }),
});

const FontVariant = defineNode("FontVariant", {
  schema: z.object({
    name: z.string().min(1).max(STYLE_NAME_MAX_LENGTH),
    fontSize: fontSizeSchema,
    axes: z.record(z.string(), z.number()),
    revision: revisionSchema,
    createdAt: timestampSchema,
    updatedAt: timestampSchema,
  }),
});

const RenderingProfile = defineNode("RenderingProfile", {
  schema: z.object({
    name: z.string().min(1).max(STYLE_NAME_MAX_LENGTH),
    letterSpacing: letterSpacingSchema,
    kerning: kerningPreferenceSchema,
    useFontHints: z.boolean(),
    fitDiagonals: z.boolean(),
    revision: revisionSchema,
    createdAt: timestampSchema,
    updatedAt: timestampSchema,
  }),
});

const TextStyle = defineNode("TextStyle", {
  schema: z.object({
    name: z.string().min(1).max(STYLE_NAME_MAX_LENGTH),
    revision: revisionSchema,
    createdAt: timestampSchema,
    updatedAt: timestampSchema,
  }),
});

const Label = defineNode("Label", {
  schema: z.object({ text: z.string().max(LABEL_TEXT_MAX_LENGTH) }),
});

const Scene = defineNode("Scene", {
  schema: z.object({
    name: z.string().min(1).max(SCENE_NAME_MAX_LENGTH),
    width: z.number().int().min(SCENE_DIMENSION_MIN).max(SCENE_DIMENSION_MAX),
    height: z.number().int().min(SCENE_DIMENSION_MIN).max(SCENE_DIMENSION_MAX),
    // Selected catalog device for the composition; null (or absent on rows
    // written before this field) means a custom screen with the scene's own
    // dimensions. The domain stores the opaque id only; catalog matching
    // lives in the screen UI.
    deviceId: z.string().min(1).max(80).nullish(),
    exportCoverage: characterCoverageSchema,
    revision: revisionSchema,
    createdAt: timestampSchema,
    updatedAt: timestampSchema,
  }),
});

const OutputProfile = defineNode("OutputProfile", {
  schema: z.object({
    name: z.string().min(1).max(STYLE_NAME_MAX_LENGTH),
    curve: grayCurveSchema,
    // Legacy numeric palette identity for the compatibility facade; new
    // profiles may omit it. Never a graph duplicate of palette rows.
    legacyPaletteId: z.number().int().min(0).optional(),
    revision: revisionSchema,
    createdAt: timestampSchema,
    updatedAt: timestampSchema,
  }),
});

// ---- Typed edges (cardinality caps count; presence enforced by commands) ----

const variantOf = defineEdge("variantOf", { from: [FontVariant], to: [Font] });
const usesVariant = defineEdge("usesVariant", { from: [TextStyle], to: [FontVariant] });
const usesProfile = defineEdge("usesProfile", { from: [TextStyle], to: [RenderingProfile] });
const styledAs = defineEdge("styledAs", { from: [Label], to: [TextStyle] });
const places = defineEdge("places", {
  schema: z.object({ x: z.number().int(), y: z.number().int(), order: z.number().int() }),
  from: [Scene],
  to: [Label],
});
const defaultOutput = defineEdge("defaultOutput", { from: [Scene], to: [OutputProfile] });

export const domainGraph = defineGraph({
  id: "glypherie-domain-v1",
  nodes: {
    Font: { type: Font },
    FontVariant: { type: FontVariant },
    RenderingProfile: { type: RenderingProfile },
    TextStyle: { type: TextStyle },
    Label: { type: Label },
    Scene: { type: Scene },
    OutputProfile: { type: OutputProfile },
  },
  edges: {
    variantOf: { type: variantOf, from: [FontVariant], to: [Font], cardinality: "one" },
    usesVariant: { type: usesVariant, from: [TextStyle], to: [FontVariant], cardinality: "one" },
    usesProfile: { type: usesProfile, from: [TextStyle], to: [RenderingProfile], cardinality: "one" },
    styledAs: { type: styledAs, from: [Label], to: [TextStyle], cardinality: "one" },
    places: { type: places, from: [Scene], to: [Label], cardinality: "many" },
    defaultOutput: { type: defaultOutput, from: [Scene], to: [OutputProfile], cardinality: "one" },
  },
});

export type DomainGraph = typeof domainGraph;
