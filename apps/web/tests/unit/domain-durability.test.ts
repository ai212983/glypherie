// Durability interface pins: the backend exposes an awaited flush, and the
// relaxed option keeps plain read-your-write and file reopen round-trips.
// IndexedDB durability itself is only observable in a real browser (see
// out/diagnostics/pglite-relaxed-durability/20261104/); these Node pins guard
// the interface and the flag plumbing without claiming browser persistence.
import assert from "node:assert/strict";
import test from "node:test";
import {
  createDomainBackend,
  kvGet,
  kvPut,
} from "../../src/app/domain/backend.ts";

test("memory backend exposes a flush that resolves", async () => {
  const backend = await createDomainBackend();
  try {
    await backend.flush();
  } finally {
    await backend.close();
  }
});

test("relaxed backend keeps read-your-write on one handle", async () => {
  const backend = await createDomainBackend({ relaxedDurability: true });
  try {
    await kvPut(backend.db, "durability:probe", "held");
    await backend.flush();
    assert.equal(await kvGet(backend.db, "durability:probe"), "held");
  } finally {
    await backend.close();
  }
});

test("relaxed file backend round-trips a flushed write across reopen", async (t) => {
  const { promises: fs } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { default: path } = await import("node:path");
  const dir = await fs.mkdtemp(path.join(tmpdir(), "glypherie-durability-"));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const dataDir = path.join(dir, "pgdata");
  const writer = await createDomainBackend({ dataDir, relaxedDurability: true });
  try {
    await kvPut(writer.db, "durability:probe", "flushed");
    await writer.flush();
  } finally {
    await writer.close();
  }
  const reader = await createDomainBackend({ dataDir });
  try {
    assert.equal(await kvGet(reader.db, "durability:probe"), "flushed");
  } finally {
    await reader.close();
  }
});
