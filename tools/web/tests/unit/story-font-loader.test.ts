import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
import { fetchFontIntoService } from "../../src/app/renderer/story-font-loader.ts";

// Focused loader checks: an aborted fetch never reaches the worker, bytes
// that arrive after abort are never sent, and HTTP failures surface.
const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
});

function stubService() {
  const loads: Array<{ fontId: string; bytes: ArrayBuffer }> = [];
  return {
    loads,
    service: {
      load: async (fontId: string, bytes: ArrayBuffer): Promise<void> => {
        loads.push({ fontId, bytes });
      },
    },
  };
}

function stubFetch(gate: Promise<void>, ok: boolean, bytes: ArrayBuffer): void {
  (globalThis as Record<string, unknown>).fetch = async (
    _url: unknown,
    init?: { signal?: AbortSignal },
  ): Promise<Response> => {
    await gate;
    init?.signal?.throwIfAborted();
    return { ok, status: ok ? 200 : 404, arrayBuffer: async () => bytes } as Response;
  };
}

test("aborted fetch never loads the worker", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  stubFetch(gate, true, new ArrayBuffer(8));
  const { loads, service } = stubService();
  const cleanup = new AbortController();
  const pending = fetchFontIntoService(service, "storybook/Roboto.ttf", "https://x/Roboto.ttf", cleanup.signal);
  cleanup.abort();
  release();
  await assert.rejects(pending, /abort/i);
  assert.deepEqual(loads, [], "no load is sent after abort");
});

test("bytes arriving after abort are not sent", async () => {
  // Resolves the fetch only after the caller already aborted: the helper
  // observes the signal again past the awaited bytes.
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  (globalThis as Record<string, unknown>).fetch = async (): Promise<Response> => {
    await gate;
    return { ok: true, status: 200, arrayBuffer: async () => new ArrayBuffer(8) } as Response;
  };
  const { loads, service } = stubService();
  const cleanup = new AbortController();
  const pending = fetchFontIntoService(service, "storybook/Roboto.ttf", "https://x/Roboto.ttf", cleanup.signal);
  await new Promise((resolve) => setTimeout(resolve, 50));
  cleanup.abort();
  release();
  await pending;
  assert.deepEqual(loads, [], "late bytes are dropped before service.load");
});

test("completed fetch loads once, failures throw", async () => {
  stubFetch(Promise.resolve(), true, new ArrayBuffer(8));
  const full = stubService();
  await fetchFontIntoService(full.service, "storybook/Roboto.ttf", "https://x/Roboto.ttf", new AbortController().signal);
  assert.equal(full.loads.length, 1, "one load is sent");
  assert.equal(full.loads[0]?.fontId, "storybook/Roboto.ttf");

  stubFetch(Promise.resolve(), false, new ArrayBuffer(0));
  const failed = stubService();
  await assert.rejects(
    fetchFontIntoService(failed.service, "storybook/Roboto.ttf", "https://x/Roboto.ttf", new AbortController().signal),
    /404/,
  );
  assert.deepEqual(failed.loads, [], "failed fetch loads nothing");
});
