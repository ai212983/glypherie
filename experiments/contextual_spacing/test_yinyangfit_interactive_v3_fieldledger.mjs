import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("./yinyangfit_interactive_v3_wiring.js", import.meta.url), "utf8");
const posts = [];
const context = vm.createContext({
  window: {},
  fieldSeq: 2,
  fieldWorkerJobs: { f1: { batchId: "b1" } },
  fieldBatches: { b1: { id: "b1", gen: 1, jobId: "f1", dispatched: true } },
  worker: { postMessage: (message) => posts.push(message) },
  finishFieldBatch: () => {
    throw new Error("Stopped batches cannot paint");
  },
  /* Pool score registry (empty here): onWorkerMessage routes pool jobIds
   * before field batches, so the stub must define it. */
  poolJobs: {},
  poolProbe: null,
});
vm.runInContext(
  source.slice(source.indexOf("function fieldLedger()"), source.indexOf("function cancelPendingFieldWork()")),
  context,
);
vm.runInContext(
  source.slice(source.indexOf("function onWorkerMessage(msg)"), source.indexOf("function showEngineError(message)")),
  context,
);
context.recordFieldBatch({ id: "b1", gen: 1 }, 46, 78);
context.window.__yyFieldBatches[0].jobId = "f1";
context.cancelDispatchedFieldJobs();
context.cancelDispatchedFieldJobs();
assert.equal(posts.length, 1);
assert.ok(context.fieldWorkerJobs.f1);
assert.equal(context.window.__yyFieldBatches[0].status, "pending");
context.onWorkerMessage({ kind: "fields-stopped", jobId: "f1", executedSlates: 46, executedMaps: 7 });
assert.equal(context.fieldWorkerJobs.f1, undefined);
assert.equal(context.fieldBatches.b1, undefined);
const entry = context.window.__yyFieldBatches[0];
assert.equal(entry.status, "cancelled");
assert.equal(entry.executedSlates, 46);
assert.equal(entry.executedMaps, 7);
assert.equal(entry.source, "worker");
assert.equal(entry.painted, false);
context.onWorkerMessage({ kind: "fields-stopped", jobId: "f1", executedMaps: 99 });
assert.equal(entry.executedMaps, 7);
console.log("field cancellation ledger passed");
