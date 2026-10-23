import assert from "node:assert/strict";
import { once } from "node:events";
import { promises as fs } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import test, { type TestContext } from "node:test";
import { servePrefix } from "../helpers/spa-helpers.ts";

test("servePrefix teardown resolves with an unfinished request body", { timeout: 15000 }, async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "font-spa-server-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const cleanups: Array<() => unknown> = [];
  const fake = { after: (fn: () => unknown) => { cleanups.push(fn); } } as Pick<TestContext, "after">;
  const url = await servePrefix(fake as TestContext, root);
  const port = Number(new URL(url).port);
  const client = net.createConnection({ host: "127.0.0.1", port });
  t.after(() => { client.destroy(); });
  await once(client, "connect");
  client.write("POST /preview/ HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 100000\r\nExpect: 100-continue\r\nConnection: keep-alive\r\n\r\n");
  const ack = await once(client, "data");
  assert.match(String(ack), /100 Continue/);
  const limitMs = 5000;
  let timer: NodeJS.Timeout | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`teardown did not resolve within ${limitMs}ms`)), limitMs);
    timer.unref?.();
  });
  try {
    await Promise.race([
      (async () => { for (const cleanup of cleanups) await cleanup(); })(),
      deadline,
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    client.destroy();
  }
  assert.equal(cleanups.length, 1);
});
