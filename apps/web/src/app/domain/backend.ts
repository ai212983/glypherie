// Domain backend: caller-owned PGlite plus the TypeGraph store over it.
// The managed createLocalPgliteStore helper hides its engine, so the binary
// and keyed-preference tables use this explicit adapter-backed path instead:
// one PGlite engine, graph tables plus app-owned relational tables, with the
// Drizzle handle available for the non-graph tables. Font binaries stay
// content-addressed and idempotent, and preview preferences fall back to
// defaults when absent, so auxiliary writes outside a graph transaction stay
// self-healing; operations that must commit atomically (legacy import) run
// graph and auxiliary writes through one Drizzle transaction instead.

import { PGlite } from "@electric-sql/pglite";
import { drizzle, type PgliteDatabase } from "drizzle-orm/pglite";
import { createPostgresBackend } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { createStore, createStoreWithSchema, MigrationError } from "@nicia-ai/typegraph";
import { and, eq, sql } from "drizzle-orm";
import { nodes } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { domainGraph, type DomainGraph } from "./graph.ts";
import { linearCurve } from "./output-profiles/curve.ts";
import { MONOCHROME_ID } from "../palettes/model.ts";
import { IMPORT_MARKER_KEY } from "./storage-keys.ts";

export type DomainStore = ReturnType<typeof createStore<DomainGraph>>;

export interface DomainBackend {
  store: DomainStore;
  db: PgliteDatabase;
  /** Awaited filesystem flush: the acknowledged-write boundary. */
  flush: () => Promise<void>;
  close: () => Promise<void>;
}

export interface DomainWasmAssets {
  pgliteWasmModule: WebAssembly.Module;
  initdbWasmModule: WebAssembly.Module;
  fsBundle: Blob;
}

export interface DomainBackendOptions {
  // Browser persistence. Omit (or pass "memory://") for in-memory stores
  // used by unit tests. Production uses "idb://glypherie-domain-v1", never
  // the legacy Dexie "font-library" name.
  dataDir?: string;
  // Browser bundling: PGlite resolves its engine files relative to its own
  // module URL, which Vite fingerprints. Compile the ?url-emitted assets
  // and pass them here instead. Node resolves from disk and needs none.
  wasmAssets?: DomainWasmAssets;
  // Relaxed durability: per-query results return before the IndexedDB flush,
  // and flush() stays the acknowledged-write boundary. Scoped to the
  // browser-persisted owner; unit/Node stores keep strict per-query flushes.
  relaxedDurability?: boolean;
}

export const DOMAIN_DATA_DIR = "idb://glypherie-domain-v1";
export const MONOCHROME_OUTPUT_ID = "output-monochrome";

async function ensureTables(db: AuxDb): Promise<void> {
  await db.execute(sql`
    CREATE TABLE IF NOT EXISTS font_binaries (
      content_id TEXT PRIMARY KEY,
      bytes BYTEA NOT NULL
    )`);
  await db.execute(sql`
    CREATE TABLE IF NOT EXISTS app_kv (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    )`);
}

// Retired `strength` cleanup (2026-11-06 hard cut): earlier builds stored a
// `strength` blend under kerning.hu_hersch/fontforge, which current admission
// rejects. One atomic UPDATE per open strips both keys (Postgres `#-`, per
// https://www.postgresql.org/docs/current/functions-json.html) and bumps row
// and props revisions; only affected rows are touched, so reruns are no-ops.
async function discardRetiredKerningStrength(db: PgliteDatabase, stamp: number): Promise<number> {
  const cleaned = await db
    .update(nodes)
    .set({
      props: sql`jsonb_set(jsonb_set((${nodes.props} #- '{kerning,hu_hersch,strength}') #- '{kerning,fontforge,strength}', '{revision}', to_jsonb(COALESCE((${nodes.props} ->> 'revision')::integer, 0) + 1), true), '{updatedAt}', to_jsonb(${stamp}::bigint), true)`,
      version: sql`${nodes.version} + 1`,
      updatedAt: new Date(stamp),
    })
    .where(
      and(
        eq(nodes.graphId, domainGraph.id),
        eq(nodes.kind, "RenderingProfile"),
        sql`(((${nodes.props} -> 'kerning' -> 'hu_hersch') ? 'strength') OR ((${nodes.props} -> 'kerning' -> 'fontforge') ? 'strength'))`,
      ),
    )
    .returning({ id: nodes.id });
  return cleaned.length;
}

async function ensureMonochromeSeed(backend: DomainBackend): Promise<void> {
  const existing = await backend.store.nodes.OutputProfile.getById(MONOCHROME_OUTPUT_ID as never).catch(
    () => undefined,
  );
  if (existing) return;
  const now = Date.now();
  await backend.store.transaction(async (tx) => {
    const seen = await tx.nodes.OutputProfile.getById(MONOCHROME_OUTPUT_ID as never).catch(() => undefined);
    if (seen) return;
    await tx.nodes.OutputProfile.create(
      {
        name: "Monochrome",
        curve: linearCurve(2).map((level) => ({ ...level })),
        legacyPaletteId: MONOCHROME_ID,
        revision: 1,
        createdAt: now,
        updatedAt: now,
      },
      { id: MONOCHROME_OUTPUT_ID },
    );
  });
}

async function openProvisionedBackend(db: PgliteDatabase, client: PGlite): Promise<DomainBackend> {
  await ensureTables(db);
  // Schema provisioning runs here (not createStore alone): hard deletes and
  // other contribution-gated writes refuse an uninitialized store. The gate
  // is idempotent across reopens of the same data directory.
  const [store] = await createStoreWithSchema(
    domainGraph,
    createPostgresBackend(db, { vector: false, fulltext: false }),
  );
  // Retained `strength` keys fail strict reads, so clean them before any
  // consumer read.
  const retiredCleaned = await discardRetiredKerningStrength(db, Date.now());
  const backend: DomainBackend = {
    store: store as DomainStore,
    db,
    flush: async () => {
      // The filesystem flush is the durable boundary: it awaits the full
      // IndexedDB sync, while PGlite.syncToFs under relaxed durability only
      // schedules that sync and returns. A missing filesystem fails closed
      // instead of acknowledging an unflushed write.
      const fs = client.fs;
      if (!fs) throw new Error("Domain store has no filesystem to flush; refusing to acknowledge the write.");
      await fs.syncToFs();
    },
    close: async () => {
      try {
        await (store as unknown as { close?: () => Promise<void> }).close?.();
      } finally {
        await client.close();
      }
    },
  };
  // The cleanup is an acknowledged write: the fail-closed flush is the
  // durable boundary before the backend is published.
  if (retiredCleaned > 0) await backend.flush();
  await ensureMonochromeSeed(backend);
  return backend;
}

// Only a confirmed incompatible admission for this graph authorizes a fresh
// start: the exported MigrationError carrying a structured breaking-change
// reason for the current graph id. Message text, unrelated failures (storage,
// quota, permissions) and other graphs never qualify, so compatible stores
// are never discarded.
function isIncompatibleSchemaError(error: unknown): boolean {
  if (!(error instanceof MigrationError)) return false;
  const { reason, graphId } = error.details;
  return reason === "breaking-change" && graphId === domainGraph.id;
}

// Discard the incompatible database and re-seed defaults on the same handle:
// transactional DROP SCHEMA removes graph rows, committed schema metadata and
// stale auxiliaries (binaries, preferences, scenes, labels) together; the
// auxiliary tables are recreated and the legacy import is marked complete in
// the same transaction so old Dexie snapshots cannot repopulate the library.
// The TypeGraph schema is reprovisioned afterwards on the root handle, never
// on a transaction-bound store.
async function resetIncompatibleDatabase(db: PgliteDatabase): Promise<void> {
  await db.transaction(async (tx) => {
    const aux = tx as unknown as AuxDb;
    await aux.execute(sql`DROP SCHEMA public CASCADE`);
    await aux.execute(sql`CREATE SCHEMA public`);
    await ensureTables(aux);
    const stamp = Date.now();
    await kvPut(
      aux,
      IMPORT_MARKER_KEY,
      JSON.stringify({
        status: "complete",
        fingerprint: "incompatible-schema-reset",
        tabId: `reset-${stamp}`,
        startedAt: stamp,
        finishedAt: stamp,
      }),
    );
  });
}

export async function createDomainBackend(options: DomainBackendOptions = {}): Promise<DomainBackend> {
  const durability = options.relaxedDurability === true ? { relaxedDurability: true as const } : {};
  const client =
    options.wasmAssets === undefined
      ? new PGlite(options.dataDir ? { dataDir: options.dataDir, ...durability } : { ...durability })
      : new PGlite({
          dataDir: options.dataDir,
          ...durability,
          pgliteWasmModule: options.wasmAssets.pgliteWasmModule,
          initdbWasmModule: options.wasmAssets.initdbWasmModule,
          fsBundle: options.wasmAssets.fsBundle,
        });
  try {
    await client.waitReady;
    const db = drizzle({ client });
    try {
      return await openProvisionedBackend(db, client);
    } catch (error) {
      // A persisted schema the current admission rejects incompatibly has no
      // migration path the user could run, so discard it once and open fresh
      // on the same engine. Anything else propagates with data intact, and a
      // second failure after the reset is never reset again.
      if (!isIncompatibleSchemaError(error)) throw error;
      await resetIncompatibleDatabase(db);
      const backend = await openProvisionedBackend(db, client);
      await backend.flush();
      return backend;
    }
  } catch (error) {
    // A failed open (provisioning, reset, or seed) must not leak a live
    // PGlite engine; the next attempt reopens from the same data directory.
    await client.close().catch(() => undefined);
    throw error;
  }
}

// ---- Durable palette identity sequence (never-reused numeric preset IDs) ----

// Highest issued legacy palette ID. Atomic reservations preserve Dexie's
// non-reuse guarantee across deletion, reopening and concurrent creation.
export const PALETTE_SEQ_KEY = "palette:next-legacy-id";

/** Atomically reserve a never-before-issued palette ID (>= neededMin). */
export async function reserveLegacyPaletteId(db: AuxDb, neededMin: number): Promise<number> {
  const floor = String(Math.max(1, Math.floor(neededMin)));
  const result = await db.execute(sql`INSERT INTO app_kv (key, value) VALUES (${PALETTE_SEQ_KEY}, ${floor})
    ON CONFLICT (key) DO UPDATE
    SET value = GREATEST((app_kv.value)::bigint + 1, (EXCLUDED.value)::bigint)::text
    RETURNING value`);
  const row = (result.rows as Array<{ value: string }>)[0];
  const id = Number(row?.value);
  if (!Number.isInteger(id) || id < 1) {
    throw new Error(`Palette identity sequence returned an unusable value for floor ${floor}.`);
  }
  return id;
}

/**
 * Raise the sequence to at least the given highest-issued ID without
 * consuming an ID (legacy import). Never lowers a higher stored value.
 */
export async function ensureLegacyPaletteIdFloor(db: AuxDb, floor: number): Promise<void> {
  // The stored value is the highest issued ID, and 0 (Monochrome alone)
  // means nothing custom was ever issued: the next reservation then yields 1.
  const value = String(Math.max(0, Math.floor(floor)));
  await db.execute(sql`INSERT INTO app_kv (key, value) VALUES (${PALETTE_SEQ_KEY}, ${value})
    ON CONFLICT (key) DO UPDATE
    SET value = CASE WHEN (app_kv.value)::bigint < (EXCLUDED.value)::bigint THEN EXCLUDED.value ELSE app_kv.value END`);
}

// ---- Keyed app storage (preview preferences, seed/import markers) ----

/**
 * Minimal Drizzle surface for the auxiliary tables. Satisfied by the root
 * database and by transaction handles (drizzle transactions expose the same
 * `execute`), so one outer transaction can cover graph and auxiliary writes
 * atomically; nested `store.transaction` calls then ride savepoints.
 */
export type AuxDb = Pick<PgliteDatabase, "execute">;

export async function kvGet(db: AuxDb, key: string): Promise<string | undefined> {
  const result = await db.execute(sql`SELECT value FROM app_kv WHERE key = ${key}`);
  const row = (result.rows as Array<{ value: string }>)[0];
  return row?.value;
}

export async function kvPut(db: AuxDb, key: string, value: string): Promise<void> {
  await db.execute(
    sql`INSERT INTO app_kv (key, value) VALUES (${key}, ${value})
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value`,
  );
}

// ---- Font binaries (content-addressed; insert skips identical rows) ----

export async function binaryLength(db: AuxDb, contentId: string): Promise<number | undefined> {
  const result = await db.execute(sql`SELECT length(bytes) AS n FROM font_binaries WHERE content_id = ${contentId}`);
  const row = (result.rows as Array<{ n: number | string }>)[0];
  return row === undefined ? undefined : Number(row.n);
}

export async function readBinary(db: AuxDb, contentId: string): Promise<Uint8Array | undefined> {
  const result = await db.execute(sql`SELECT bytes FROM font_binaries WHERE content_id = ${contentId}`);
  const row = (result.rows as Array<{ bytes: Uint8Array | string }>)[0];
  if (row === undefined) return undefined;
  if (row.bytes instanceof Uint8Array) return row.bytes;
  // Hex-encoded fallback for drivers that return bytea as text.
  const text = String(row.bytes);
  const hex = text.startsWith("\\x") ? text.slice(2) : text;
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i += 1) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16)!;
  return out;
}

export async function writeBinaryIfAbsent(db: AuxDb, contentId: string, bytes: Uint8Array): Promise<void> {
  const existing = await binaryLength(db, contentId);
  if (existing !== undefined) {
    if (existing !== bytes.byteLength) {
      throw new Error(`Font binary "${contentId}" exists with ${existing} bytes, refusing ${bytes.byteLength}.`);
    }
    return;
  }
  await db.execute(
    sql`INSERT INTO font_binaries (content_id, bytes) VALUES (${contentId}, ${bytes})
        ON CONFLICT (content_id) DO NOTHING`,
  );
}

export async function deleteBinary(db: AuxDb, contentId: string): Promise<void> {
  await db.execute(sql`DELETE FROM font_binaries WHERE content_id = ${contentId}`);
}
