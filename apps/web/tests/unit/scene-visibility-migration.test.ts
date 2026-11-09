import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";
import { createStoreWithSchema, defineEdge, defineGraph } from "@nicia-ai/typegraph";
import { createPostgresBackend } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { drizzle } from "drizzle-orm/pglite";
import { createDomainBackend, kvGet } from "../../src/app/domain/backend.ts";
import { domainGraph } from "../../src/app/domain/graph.ts";
import { getScene, updateSceneLabel } from "../../src/app/domain/scene-commands.ts";
import { DEFAULT_CHARACTER_COVERAGE } from "../../src/app/domain/coverage.ts";
import { linearCurve } from "../../src/app/features/grayscale/response-curve.ts";

test("adding optional placement visibility preserves a populated pre-visibility database", async (t) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-visibility-"));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const options = { dataDir: path.join(directory, "pgdata") };
  const legacyPlaces = defineEdge("places", {
    schema: domainGraph.edges.places.type.schema.omit({ visible: true }),
    from: [domainGraph.nodes.Scene.type],
    to: [domainGraph.nodes.Label.type],
  });
  const legacyGraph = defineGraph({
    id: domainGraph.id,
    nodes: domainGraph.nodes,
    edges: { ...domainGraph.edges, places: { ...domainGraph.edges.places, type: legacyPlaces } },
  });
  const previous = new PGlite(options);
  let sceneId = "";
  try {
    const [store] = await createStoreWithSchema(
      legacyGraph,
      createPostgresBackend(drizzle({ client: previous }), { vector: false, fulltext: false }),
    );
    const profile = await store.nodes.OutputProfile.create({
      name: "Retained",
      curve: [...linearCurve(2)],
      revision: 1,
      createdAt: 1,
      updatedAt: 1,
    });
    const scene = await store.nodes.Scene.create({
      name: "Kept scene",
      width: 400,
      height: 300,
      deviceId: null,
      exportCoverage: {
        presetIds: [...DEFAULT_CHARACTER_COVERAGE.presetIds],
        extraRanges: [...DEFAULT_CHARACTER_COVERAGE.extraRanges],
      },
      revision: 1,
      createdAt: 1,
      updatedAt: 1,
    });
    sceneId = String(scene.id);
    await store.edges.defaultOutput.create(scene, profile, {});
    const label = await store.nodes.Label.create({
      text: "Kept label",
      fontId: "legacy-font",
      fontSize: 16,
      width: 200,
    });
    await store.edges.places.create(scene, label, { x: 8, y: 8, order: 0 });
    await previous.exec(
      "CREATE TABLE app_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL); INSERT INTO app_kv VALUES ('visibility:sentinel', 'kept');",
    );
  } finally {
    await previous.close();
  }
  const current = await createDomainBackend(options);
  try {
    assert.equal(
      await kvGet(current.db, "visibility:sentinel"),
      "kept",
      "schema admission must not reset existing data",
    );
    const scene = await getScene(current, sceneId);
    assert.equal(scene?.name, "Kept scene");
    assert.equal(scene?.placements[0]?.text, "Kept label");
    assert.equal(scene?.placements[0]?.visible, true);
    await updateSceneLabel(current, sceneId, scene!.placements[0]!.id, { visible: false }, scene!.revision);
    await current.flush();
  } finally {
    await current.close();
  }
  const reopened = await createDomainBackend(options);
  try {
    assert.equal((await getScene(reopened, sceneId))?.placements[0]?.visible, false);
    assert.equal(await kvGet(reopened.db, "visibility:sentinel"), "kept");
  } finally {
    await reopened.close();
  }
});
