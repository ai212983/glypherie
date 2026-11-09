import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { nodes } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { and, eq, sql } from "drizzle-orm";
import { createDomainBackend, readBinary, writeBinaryIfAbsent } from "../../src/app/domain/backend.ts";
import { domainGraph } from "../../src/app/domain/graph.ts";
import { defaultKerningState } from "../../src/app/kerning/model.ts";
import { toRenderSpec } from "../../src/app/renderer/render-spec.ts";

test("opening stored profiles discards retired strengths before strict reads and rendering", async (t) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-kerning-cutover-"));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const options = { dataDir: path.join(directory, "pgdata"), relaxedDurability: true };
  const current = defaultKerningState();
  current.hu_hersch = { apertureDepthFactor: 0.3, globalDepthFactor: 0.4 };
  const ids = ["source", "hu_hersch", "fontforge"] as const;
  const writer = await createDomainBackend(options);
  try {
    await writeBinaryIfAbsent(writer.db, "kept-font", new Uint8Array([1, 2, 3]));
    for (const method of ids) {
      await writer.store.nodes.RenderingProfile.create(
        {
          name: method,
          letterSpacing: 1,
          kerning: { ...current, method },
          useFontHints: true,
          fitDiagonals: true,
          revision: 7,
          createdAt: 5,
          updatedAt: 6,
        },
        { id: method },
      );
    }
    await writer.store.nodes.RenderingProfile.create(
      {
        name: "Current",
        letterSpacing: 0,
        kerning: true,
        useFontHints: true,
        fitDiagonals: true,
        revision: 2,
        createdAt: 5,
        updatedAt: 6,
      },
      { id: "current" },
    );
    // Recreate bytes written by the retired schema, bypassing today's strict admission.
    await writer.db
      .update(nodes)
      .set({
        props: sql`jsonb_set(jsonb_set(${nodes.props},
      '{kerning,hu_hersch,strength}', '0'), '{kerning,fontforge,strength}', 'null')`,
      })
      .where(and(eq(nodes.graphId, domainGraph.id), eq(nodes.kind, "RenderingProfile"), sql`${nodes.id} <> 'current'`));
    await writer.flush();
  } finally {
    await writer.close();
  }

  const reader = await createDomainBackend(options);
  let afterCutover: unknown;
  try {
    for (const method of ids) {
      const profile = await reader.store.nodes.RenderingProfile.getById(method as never);
      assert.ok(profile);
      assert.deepEqual(profile.kerning, { ...current, method });
      assert.equal(profile.revision, 8, "discarding persisted parameters advances the revision");
      assert.equal(profile.letterSpacing, 1);
      assert.equal(profile.createdAt, 5);
      assert.ok(profile.updatedAt > 6);
      assert.doesNotThrow(() =>
        toRenderSpec({
          text: "Ag",
          sizePx: 16,
          axes: {},
          profile: "mono_1bit",
          width: 120,
          height: 60,
          rasterization: "free_type_mono",
          kerning: profile.kerning,
        }),
      );
    }
    const untouched = await reader.store.nodes.RenderingProfile.getById("current" as never);
    assert.equal(untouched?.revision, 2);
    assert.equal(untouched?.updatedAt, 6);
    assert.deepEqual(await readBinary(reader.db, "kept-font"), new Uint8Array([1, 2, 3]));
    afterCutover = await reader.db.select().from(nodes).orderBy(nodes.id);
  } finally {
    await reader.close();
  }
  const reopened = await createDomainBackend(options);
  try {
    assert.deepEqual(
      await reopened.db.select().from(nodes).orderBy(nodes.id),
      afterCutover,
      "the cutover is durable and repeat opens do not rewrite profiles",
    );
  } finally {
    await reopened.close();
  }
});
