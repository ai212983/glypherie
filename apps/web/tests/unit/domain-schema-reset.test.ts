import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";
import { createStoreWithSchema, defineGraph, defineNode } from "@nicia-ai/typegraph";
import { createPostgresBackend } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { drizzle } from "drizzle-orm/pglite";
import { z } from "zod";
import { createDomainBackend, kvGet, kvPut, readBinary, MONOCHROME_OUTPUT_ID } from "../../src/app/domain/backend.ts";
import { domainGraph } from "../../src/app/domain/graph.ts";
import { IMPORT_MARKER_KEY, importLegacySnapshot } from "../../src/app/domain/importer.ts";
import { defaultKerningState } from "../../src/app/kerning/model.ts";

test("an incompatible persisted schema resets the local library before opening it", async (t) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-schema-reset-"));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const options = {
    dataDir: path.join(directory, "pgdata"),
    relaxedDurability: true,
  };
  const legacyProfile = defineNode("RenderingProfile", {
    schema: domainGraph.nodes.RenderingProfile.type.schema.extend({
      kerning: z.object({
        method: z.literal("hu_hersch"),
        hu_hersch: z.object({ strength: z.number() }),
        fontforge: z.object({ strength: z.number() }),
      }),
    }),
  });
  const legacyGraph = defineGraph({
    id: domainGraph.id,
    nodes: { ...domainGraph.nodes, RenderingProfile: { type: legacyProfile } },
    edges: domainGraph.edges,
  });
  const previous = new PGlite({ dataDir: options.dataDir });
  try {
    const db = drizzle({ client: previous });
    const [store] = await createStoreWithSchema(
      legacyGraph,
      createPostgresBackend(db, { vector: false, fulltext: false }),
    );
    await store.nodes.RenderingProfile.create(
      {
        name: "Obsolete",
        letterSpacing: 1,
        kerning: {
          method: "hu_hersch",
          hu_hersch: { strength: 0 },
          fontforge: { strength: 1 },
        },
        useFontHints: true,
        fitDiagonals: true,
        revision: 1,
        createdAt: 1,
        updatedAt: 1,
      },
      { id: "obsolete-profile" },
    );
    await previous.exec(
      "CREATE TABLE font_binaries (content_id TEXT PRIMARY KEY, bytes BYTEA NOT NULL); CREATE TABLE app_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL); INSERT INTO font_binaries VALUES ('obsolete-font', decode('010203', 'hex')); INSERT INTO app_kv VALUES ('old-setting', 'obsolete');",
    );
  } finally {
    await previous.close();
  }
  const fresh = await createDomainBackend(options);
  try {
    assert.equal(await fresh.store.nodes.RenderingProfile.getById("obsolete-profile" as never), undefined);
    assert.equal(await readBinary(fresh.db, "obsolete-font"), undefined);
    assert.equal(await kvGet(fresh.db, "old-setting"), undefined);
    assert.ok(await fresh.store.nodes.OutputProfile.getById(MONOCHROME_OUTPUT_ID as never));
    assert.equal(
      JSON.parse((await kvGet(fresh.db, IMPORT_MARKER_KEY)) ?? "{}").status,
      "complete",
      "the legacy source must not restore discarded data",
    );
    assert.equal(
      (
        await importLegacySnapshot(fresh, {
          fonts: [],
          variants: [],
          palettes: [],
          variantCount: 0,
        })
      ).skipped,
      true,
    );
    await kvPut(fresh.db, "new-setting", "kept");
    await fresh.flush();
  } finally {
    await fresh.close();
  }
  const reopened = await createDomainBackend(options);
  try {
    assert.equal(await kvGet(reopened.db, "new-setting"), "kept", "a compatible reopen does not reset again");
  } finally {
    await reopened.close();
  }
});

test("a compatible persisted schema never triggers the fresh-start reset", async (t) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-schema-compatible-"));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const options = {
    dataDir: path.join(directory, "pgdata"),
    relaxedDurability: true,
  };
  const writer = await createDomainBackend(options);
  try {
    await writer.store.nodes.RenderingProfile.create(
      {
        name: "Kept",
        letterSpacing: 0,
        kerning: defaultKerningState(),
        useFontHints: true,
        fitDiagonals: false,
        revision: 1,
        createdAt: 1,
        updatedAt: 1,
      },
      { id: "kept-profile" },
    );
    await kvPut(writer.db, "kept-setting", "kept");
    await writer.flush();
  } finally {
    await writer.close();
  }
  const reopened = await createDomainBackend(options);
  try {
    assert.ok(await reopened.store.nodes.RenderingProfile.getById("kept-profile" as never));
    assert.equal(await kvGet(reopened.db, "kept-setting"), "kept");
    assert.equal(await kvGet(reopened.db, IMPORT_MARKER_KEY), undefined);
  } finally {
    await reopened.close();
  }
});
