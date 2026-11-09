// Safe one-way legacy import: Dexie "font-library" rows become graph nodes,
// binaries, palettes and keyed preferences. Reads run against the legacy
// snapshot only; nothing is ever deleted from Dexie. Every write lands in one
// outer Drizzle transaction (graph writes through a transaction-scoped store,
// binaries/preferences/seed/completion marker through the same handle), so a
// failure at any stage rolls back all of it and a retry starts clean. The
// import is one-way and one-time: a complete marker means done, and later
// legacy changes never reapply over newer domain edits.

import { sql } from "drizzle-orm";
import { createPostgresBackend } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { createStore } from "@nicia-ai/typegraph";
import { MONOCHROME } from "../palettes/model.ts";
import { currentPreviewSettings } from "../variants/model.ts";
import { cloneKerning } from "../kerning/model.ts";
import {
  ensureLegacyPaletteIdFloor,
  kvGet,
  kvPut,
  writeBinaryIfAbsent,
  MONOCHROME_OUTPUT_ID,
  type AuxDb,
  type DomainBackend,
} from "./backend.ts";
import { DomainError } from "./commands.ts";
import { IMPORT_MARKER_KEY } from "./storage-keys.ts";
import { linearCurve } from "../features/grayscale/response-curve.ts";
import { domainGraph } from "./graph.ts";
import type { LegacySnapshot } from "../legacy-database.ts";

export { IMPORT_MARKER_KEY };
export const SEED_MARKER_KEY = "seed:bundled-fonts";

interface ImportMarker {
  status: "in-progress" | "complete";
  fingerprint: string;
  tabId: string;
  startedAt: number;
  finishedAt?: number;
}

export interface ImportResult {
  skipped: boolean;
  fonts: number;
  variants: number;
  palettes: number;
  skippedVariantIds: string[];
}

// Change-detection fingerprint (FNV-1a; not a security hash, no node:crypto
// so the browser worker bundle stays node:-clean). Recorded on the completion
// marker for diagnostics; the skip decision keys off the marker alone.
function fingerprintOf(snapshot: LegacySnapshot): string {
  const text = JSON.stringify({
    fonts: snapshot.fonts.map((font) => font.id).sort(),
    variants: snapshot.variants.map((variant) => variant.id).sort(),
    palettes: snapshot.palettes.map((palette) => palette.id).sort(),
    seedMarker: snapshot.seedMarker ?? null,
  });
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

async function readMarker(db: AuxDb): Promise<ImportMarker | undefined> {
  const raw = await kvGet(db, IMPORT_MARKER_KEY);
  if (raw === undefined) return undefined;
  try {
    const parsed = JSON.parse(raw) as Partial<ImportMarker>;
    if (parsed.status !== "in-progress" && parsed.status !== "complete") return undefined;
    if (typeof parsed.fingerprint !== "string") return undefined;
    return parsed as ImportMarker;
  } catch {
    return undefined;
  }
}

function tabId(): string {
  try {
    const id = globalThis.crypto?.randomUUID?.();
    if (typeof id === "string" && id.length > 0) return id;
  } catch {
    // Fall through to the timestamp fallback below.
  }
  return `tab-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

export async function importStatus(backend: DomainBackend, snapshot: LegacySnapshot): Promise<{ imported: boolean }> {
  // The snapshot stays in the signature for call-site compatibility, but the
  // answer keys off the completion marker alone: a completed import never
  // re-runs against a newer legacy snapshot.
  void snapshot;
  const marker = await readMarker(backend.db);
  return { imported: marker?.status === "complete" };
}

interface NormalizedVariant {
  variant: LegacySnapshot["variants"][number];
  settings: ReturnType<typeof currentPreviewSettings>;
  kerning: ReturnType<typeof cloneKerning>;
}

// The 2026-11-06 hard cut retired the `strength` blend: untouched legacy
// snapshots may still carry it (any value, active or inactive block). Drop
// those keys from a copy before current validation so the import neither
// blocks boot nor resurrects the parameter. Presence-based: null/0 values
// are discarded, never blended. The Dexie row itself is never mutated.
type LegacyVariantSettings = LegacySnapshot["variants"][number]["settings"];

function withoutRetiredKerningStrength(settings: LegacyVariantSettings): LegacyVariantSettings {
  const kerning = (settings as { kerning?: unknown }).kerning;
  if (typeof kerning !== "object" || kerning === null || Array.isArray(kerning)) return settings;
  const blocks = kerning as Record<string, unknown>;
  let changed = false;
  const next: Record<string, unknown> = { ...blocks };
  for (const block of ["hu_hersch", "fontforge"] as const) {
    const value = next[block];
    if (typeof value === "object" && value !== null && !Array.isArray(value) && "strength" in value) {
      const cleaned = { ...(value as Record<string, unknown>) };
      delete cleaned.strength;
      next[block] = cleaned;
      changed = true;
    }
  }
  if (!changed) return settings;
  // Only retired keys were removed, so the shape still conforms; current
  // validation below enforces the rest.
  return { ...settings, kerning: next } as unknown as LegacyVariantSettings;
}

function normalizeVariants(snapshot: LegacySnapshot): NormalizedVariant[] {
  return snapshot.variants.map((variant) => {
    const cleaned = withoutRetiredKerningStrength(variant.settings);
    let settings;
    try {
      settings = currentPreviewSettings(cleaned);
    } catch (error) {
      throw new DomainError(
        "invalid-settings",
        `Legacy variant "${variant.id}" carries settings the current policy rejects; refusing to import.`,
        { cause: error },
      );
    }
    let kerning;
    try {
      kerning = cloneKerning(settings.kerning);
    } catch (error) {
      throw new DomainError(
        "invalid-settings",
        `Legacy variant "${variant.id}" carries kerning the current model rejects; refusing to import.`,
        { cause: error },
      );
    }
    return { variant, settings, kerning };
  });
}

async function digestFonts(snapshot: LegacySnapshot): Promise<Array<{ id: string; bytes: Uint8Array }>> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new DomainError("unavailable", "Import needs WebCrypto SHA-256, missing in this context.");
  const digested: Array<{ id: string; bytes: Uint8Array }> = [];
  for (const font of snapshot.fonts) {
    const bytes = new Uint8Array(font.bytes);
    const digest = await subtle.digest("SHA-256", bytes as BufferSource);
    const actual = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    if (actual !== font.id) {
      throw new DomainError(
        "invalid-input",
        `Legacy font "${font.id}" bytes do not match their content id; refusing to import.`,
      );
    }
    digested.push({ id: font.id, bytes });
  }
  return digested;
}

export async function importLegacySnapshot(backend: DomainBackend, snapshot: LegacySnapshot): Promise<ImportResult> {
  const fingerprint = fingerprintOf(snapshot);
  const marker = await readMarker(backend.db);
  // One-way migration: a complete marker means the import ran once. Later
  // legacy changes (including rows the new app can no longer produce) never
  // reapply, so they cannot overwrite newer domain edits. A stale
  // in-progress marker from an older build simply retries.
  if (marker?.status === "complete") {
    return {
      skipped: true,
      fonts: 0,
      variants: 0,
      palettes: 0,
      skippedVariantIds: [],
    };
  }
  // Upfront validation: legacy rows must normalize under the current policy
  // and binaries must match their content ids before anything is written, so
  // a bad row fails the import, not the data.
  const normalized = normalizeVariants(snapshot);
  const binaries = await digestFonts(snapshot);

  // Set when this caller lost a concurrent race: the winner's marker was
  // already complete at recheck, so nothing below wrote and the honest
  // report is a skip, not an import of rows this caller never stored.
  let racedComplete = false;
  await backend.db.transaction(async (txDb) => {
    const tx = txDb as unknown as AuxDb;
    // Serialize simultaneous cold-boot imports at the database: the lock is
    // transaction-scoped, so the loser re-reads the winner's marker below.
    await tx.execute(sql`SELECT pg_advisory_xact_lock(818527, 1)`);
    const raced = await readMarker(tx);
    if (raced?.status === "complete") {
      racedComplete = true;
      return;
    }
    // Transaction-scoped graph store over the same handle: graph writes join
    // this transaction (nested store transactions ride savepoints), so graph,
    // binaries, preferences and markers commit or roll back as one unit.
    const txStore = createStore(
      domainGraph,
      createPostgresBackend(txDb as never, { vector: false, fulltext: false }),
    ) as DomainBackend["store"];
    for (const font of binaries) {
      await writeBinaryIfAbsent(tx, font.id, font.bytes);
    }
    // The profile lookup is loaded once and shared: the graph phase returns
    // its legacy-id map, and the preference phase below reuses it instead of
    // re-querying the table once per variant. No profile writes happen in
    // between, so the map stays exact for this transaction.
    const paletteByLegacy = await txStore.transaction(async (txNodes) => {
      const paletteMap = new Map<number, string>();
      const fontIds = new Set<string>();
      for (const font of snapshot.fonts) {
        const existing = await txNodes.nodes.Font.getById(font.id as never).catch(() => undefined);
        if (!existing) {
          await txNodes.nodes.Font.create(
            {
              name: font.name,
              fileName: font.fileName,
              metadata: font.metadata as never,
              source: font.source,
              addedAt: font.addedAt,
            },
            { id: font.id },
          );
        }
        fontIds.add(font.id);
      }
      const existingProfiles = await txNodes
        .query()
        .from("OutputProfile", "o")
        .select((ctx) => ctx.o)
        .execute();
      for (const row of existingProfiles) {
        const legacyId = (row as unknown as Record<string, unknown>).legacyPaletteId;
        if (typeof legacyId === "number") paletteMap.set(legacyId, String(row.id));
      }
      for (const palette of snapshot.palettes) {
        if (paletteMap.has(palette.id)) continue;
        const profileId = palette.id === MONOCHROME.id ? MONOCHROME_OUTPUT_ID : `palette-${palette.id}`;
        const seen = await txNodes.nodes.OutputProfile.getById(profileId as never).catch(() => undefined);
        if (!seen) {
          await txNodes.nodes.OutputProfile.create(
            {
              name: palette.name,
              curve: palette.curve.map((level) => ({ ...level })),
              legacyPaletteId: palette.id,
              revision: 1,
              createdAt: Date.now(),
              updatedAt: Date.now(),
            },
            { id: profileId },
          );
        }
        paletteMap.set(palette.id, profileId);
      }
      // Monochrome may predate the legacy table (fresh seed on first boot);
      // never treat its absence as an import error.
      if (!paletteMap.has(MONOCHROME.id)) {
        const mono = await txNodes.nodes.OutputProfile.getById(MONOCHROME_OUTPUT_ID as never).catch(() => undefined);
        if (!mono) {
          const stamp = Date.now();
          await txNodes.nodes.OutputProfile.create(
            {
              name: MONOCHROME.name,
              curve: linearCurve(2).map((level) => ({ ...level })),
              legacyPaletteId: MONOCHROME.id,
              revision: 1,
              createdAt: stamp,
              updatedAt: stamp,
            },
            { id: MONOCHROME_OUTPUT_ID },
          );
        }
        paletteMap.set(MONOCHROME.id, MONOCHROME_OUTPUT_ID);
      }
      for (const { variant, settings, kerning } of normalized) {
        if (!fontIds.has(variant.fontId)) {
          // A variant whose font is missing from the snapshot is corrupt
          // input, not a skippable row: fail the whole import atomically so
          // nothing partial commits and a repaired snapshot can retry.
          throw new DomainError(
            "invalid-input",
            `Legacy variant "${variant.id}" references missing font "${variant.fontId}"; refusing to import.`,
          );
        }
        const seen = await txNodes.nodes.TextStyle.getById(variant.id as never).catch(() => undefined);
        if (seen) continue;
        const font = await txNodes.nodes.Font.getById(variant.fontId as never).catch(() => undefined);
        if (!font) {
          throw new DomainError(
            "invalid-input",
            `Legacy variant "${variant.id}" references missing font "${variant.fontId}"; refusing to import.`,
          );
        }
        const fontVariant = await txNodes.nodes.FontVariant.create({
          name: variant.name,
          fontSize: settings.sizePx,
          axes: { ...settings.axes },
          revision: variant.revision,
          createdAt: variant.createdAt,
          updatedAt: variant.updatedAt,
        });
        await txNodes.edges.variantOf.create(fontVariant, font, {});
        const profile = await txNodes.nodes.RenderingProfile.create({
          name: variant.name,
          letterSpacing: settings.letterSpacingPx,
          kerning,
          useFontHints: settings.stemFitting === "font_hints_first",
          fitDiagonals: settings.diagonalFitting ?? false,
          revision: variant.revision,
          createdAt: variant.createdAt,
          updatedAt: variant.updatedAt,
        });
        const style = await txNodes.nodes.TextStyle.create(
          {
            name: variant.name,
            revision: variant.revision,
            createdAt: variant.createdAt,
            updatedAt: variant.updatedAt,
          },
          { id: variant.id },
        );
        await txNodes.edges.usesVariant.create(style, fontVariant, {});
        await txNodes.edges.usesProfile.create(style, profile, {});
      }
      return paletteMap;
    });

    // Later creations must allocate above every imported ID: the sequence
    // stores the highest issued ID, so raise it to cover the legacy range.
    // Imported IDs stay exactly as stored; the sequence only moves forward.
    let importedMax = MONOCHROME.id;
    for (const palette of snapshot.palettes) {
      if (Number.isInteger(palette.id) && palette.id > importedMax) importedMax = palette.id;
    }
    await ensureLegacyPaletteIdFloor(tx, importedMax);

    // Preferences and markers land in the same transaction: a crash or a
    // later validation throw rolls back binaries and graph rows with them.
    for (const { variant, settings } of normalized) {
      const outputId = paletteByLegacy.get(settings.paletteId ?? MONOCHROME.id) ?? MONOCHROME_OUTPUT_ID;
      await kvPut(
        tx,
        `preview:${variant.id}`,
        JSON.stringify({
          sampleText: variant.sampleText,
          inheritSampleText: variant.inheritSampleText ?? false,
          outputProfileId: outputId,
        }),
      );
    }
    if (snapshot.seedMarker !== undefined) {
      await kvPut(tx, SEED_MARKER_KEY, snapshot.seedMarker);
    }
    await kvPut(
      tx,
      IMPORT_MARKER_KEY,
      JSON.stringify({
        status: "complete",
        fingerprint,
        tabId: tabId(),
        startedAt: Date.now(),
        finishedAt: Date.now(),
      } satisfies ImportMarker),
    );
  });
  if (racedComplete) {
    return {
      skipped: true,
      fonts: 0,
      variants: 0,
      palettes: 0,
      skippedVariantIds: [],
    };
  }
  return {
    skipped: false,
    fonts: snapshot.fonts.length,
    variants: normalized.length,
    palettes: snapshot.palettes.length,
    skippedVariantIds: [],
  };
}
