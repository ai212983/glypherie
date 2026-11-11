import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("owner reads await durable writes and recover from failed flushes without starving timers", () => {
  const worker = new URL("../../src/app/domain/worker.ts", import.meta.url).href;
  const script = `
    import assert from 'node:assert/strict';
    import { registerHooks } from 'node:module';
    const worker = ${JSON.stringify(worker)};
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    const state = { value: 'original', durable: false };
    let activeFlushes = 0;
    let maxFlushes = 0;
    let reads = 0;
    globalThis.fixture = {
      failNext: false,
      failFlush: false,
      commits: [],
      backend: { flush: async () => {
        maxFlushes = Math.max(maxFlushes, ++activeFlushes);
        await pause(10);
        if (fixture.failFlush) { activeFlushes--; throw new Error('quota failure'); }
        state.durable = true;
        activeFlushes--;
      } },
      update: async () => {
        await pause(10);
        if (fixture.failNext) { fixture.failNext = false; throw new Error('rejected write'); }
        state.value = 'edited'; state.durable = false;
        return state.value;
      },
      read: async () => { reads++; return { ...state }; }
    };
    const sources = {
      './backend.ts': 'export const DOMAIN_DATA_DIR = "memory://"; export const createDomainBackend = async () => globalThis.fixture.backend;',
      './commands.ts': 'export const updateVariant = globalThis.fixture.update; export const getVariant = globalThis.fixture.read;',
      './importer.ts': 'export const importLegacySnapshot = async () => ({skipped: true});'
    };
    registerHooks({ resolve(specifier, context, next) {
      if (context.parentURL === worker && specifier in sources)
        return { url: 'data:text/javascript,' + encodeURIComponent(sources[specifier]), shortCircuit: true };
      return next(specifier, context);
    }});
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {
      locks: { request: (_name, _options, callback) => { void callback(); return new Promise(() => {}); } }
    }});
    globalThis.BroadcastChannel = class { postMessage(message) { fixture.commits.push(message); } };
    const pending = new Map();
    globalThis.self = { postMessage: response => pending.get(response.id)(response) };
    await import(worker);
    const call = (id, method, params = []) => new Promise(resolve => {
      pending.set(id, resolve);
      self.onmessage({data: {id, method, params}});
    });
    const { DOMAIN_PROTOCOL_VERSION } = await import(new URL('protocol.ts', worker));
    assert.equal((await call(1, '__protocol', [DOMAIN_PROTOCOL_VERSION])).ok, true);
    const [write, read] = await Promise.all([call(2, 'updateVariant'), call(3, 'getVariant')]);
    assert.equal(write.ok, true);
    assert.deepEqual(read.result, { value: 'edited', durable: true });
    fixture.failNext = true;
    const [failed, afterFailure] = await Promise.all([call(4, 'updateVariant'), call(5, 'getVariant')]);
    assert.equal(failed.ok, false);
    assert.deepEqual(afterFailure.result, { value: 'edited', durable: true });
    const parallel = await Promise.all([call(6, 'updateVariant'), call(7, 'updateVariant'), call(8, 'getVariant')]);
    assert.equal(parallel[0].ok, true);
    assert.equal(parallel[1].ok, true);
    assert.deepEqual(parallel[2].result, { value: 'edited', durable: true });
    fixture.failFlush = true;
    const readsBeforeFailure = reads;
    const commitsBeforeFailure = fixture.commits.length;
    const [flushFailed, blockedRead] = await Promise.all([call(9, 'updateVariant'), call(10, 'getVariant')]);
    assert.equal(flushFailed.ok, false);
    assert.equal(blockedRead.ok, false, 'a failed flush cannot expose the in-memory edit');
    assert.equal(reads, readsBeforeFailure, 'the failed durability gate never invokes a read');
    assert.equal((await call(11, 'getVariant')).ok, false, 'later reads remain gated while storage fails');
    assert.equal(fixture.commits.length, commitsBeforeFailure);
    fixture.failFlush = false;
    const [recovered, concurrentRead] = await Promise.all([call(12, 'getVariant'), call(13, 'getVariant')]);
    assert.equal(recovered.ok, true, 'retrying a read can recover once persistence succeeds');
    assert.deepEqual(recovered.result, { value: 'edited', durable: true });
    assert.equal(recovered.mutated, false);
    assert.deepEqual(concurrentRead.result, { value: 'edited', durable: true });
    assert.equal(fixture.commits.length, commitsBeforeFailure + 1, 'recovered persistence announces the edit');
    fixture.failFlush = true;
    assert.equal((await call(14, 'updateVariant')).ok, false);
    fixture.failFlush = false;
    const [recoveredWrite, afterRecovery] = await Promise.all([call(15, 'updateVariant'), call(16, 'getVariant')]);
    assert.equal(recoveredWrite.ok, true, 'a later mutation can also recover persistence');
    assert.deepEqual(afterRecovery.result, { value: 'edited', durable: true });
    assert.equal(maxFlushes, 1);
  `;
  // A blocked worker cannot run its own timeout, so bound it from outside.
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
    encoding: "utf8",
    timeout: 3000,
  });
  assert.equal(result.error, undefined, `owner did not complete: ${String(result.error)}\n${result.stderr}`);
  assert.equal(result.status, 0, result.stderr);
});
