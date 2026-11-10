import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { convertEntry, mergeMapData, type IstanbulMapData } from "../../scripts/coverage-merge.ts";

interface V8Result {
  functionName: string;
  ranges: Array<{ startOffset: number; endOffset: number; count: number }>;
  isBlockCoverage: boolean;
}

const FIXTURE = `function pick(x) {
  if (x) {
    return "yes";
  }
  return "no";
}
if (process.argv[2] !== "skip") {
  process.stdout.write(String(pick(process.argv[2] === "yes")));
}
`;

async function collect(fixture: string, arg: string): Promise<V8Result[]> {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-v8-"));
  try {
    execFileSync(process.execPath, [fixture, arg], {
      env: { ...process.env, NODE_V8_COVERAGE: dir },
      stdio: "pipe",
    });
    const names = await fs.readdir(dir);
    assert.equal(names.length, 1, "one V8 profile per execution");
    const parsed = JSON.parse(await fs.readFile(path.join(dir, names[0]!), "utf8")) as {
      result: Array<{ url: string; functions: V8Result[] }>;
    };
    const entry = parsed.result.find((script) => script.url.endsWith("/pick.js"));
    assert.ok(entry, "profile covers the fixture script");
    return entry.functions;
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}

function byLoc(data: IstanbulMapData): Map<string, { hits: number[]; kind: "branch" | "statement" }> {
  const found = new Map<string, { hits: number[]; kind: "branch" | "statement" }>();
  const key = Object.keys(data)[0]!;
  const cov = data[key]!;
  for (const [id, meta] of Object.entries(cov.branchMap)) {
    const loc = JSON.stringify(meta.loc);
    assert.ok(!found.has(`branch:${loc}`), "converter emits one branch identity per location");
    // Snapshot: Istanbul merge mutates hit arrays in place, so the oracle
    // must own its numbers before any merge runs.
    found.set(`branch:${loc}`, { hits: [...cov.b[id]!], kind: "branch" });
  }
  for (const [id, meta] of Object.entries(cov.statementMap)) {
    found.set(`statement:${JSON.stringify(meta.start)}`, { hits: [cov.s[id]!], kind: "statement" });
  }
  return found;
}

test("two executions merge by location: A hits survive, B adds nothing, one identity", async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-v8-merge-"));
  try {
    const fixture = path.join(dir, "pick.js");
    await fs.writeFile(fixture, FIXTURE);
    const source = await fs.readFile(fixture, "utf8");
    // Execution A takes the if-branch; execution B never calls pick.
    const convertedA = await convertEntry({
      url: fixture,
      scriptPath: fixture,
      source,
      functions: await collect(fixture, "yes"),
    });
    const convertedB = await convertEntry({
      url: fixture,
      scriptPath: fixture,
      source,
      functions: await collect(fixture, "skip"),
    });
    // Snapshot before merging: Istanbul merge updates hit counts in place.
    const a = byLoc(convertedA);
    const b = byLoc(convertedB);
    const merged = mergeMapData([convertedA, convertedB]);
    assert.deepEqual(Object.keys(merged), Object.keys(convertedA), "no duplicated file records");
    const m = byLoc(merged);
    assert.equal(
      m.size,
      new Set([...a.keys(), ...b.keys()]).size,
      "merge coalesces identities instead of duplicating them",
    );
    // Line 3 (`return "yes"`) runs only in A: shared identity, B contributes
    // zero. A shared-converter overwrite bug would zero this to B's count.
    assert.deepEqual(m.get('statement:{"line":3,"column":0}')?.hits, [1], "A statement hit survives B's zero");
    // Whole-file branch runs once in each execution: one coalesced identity
    // whose hits sum both runs.
    assert.deepEqual(
      m.get('branch:{"start":{"line":1,"column":0},"end":{"line":9,"column":1}}')?.hits,
      [2],
      "shared branch identity sums both executions",
    );
    assert.ok(
      (m.get('statement:{"line":3,"column":0}')?.hits ?? [0])[0]! > 0,
      "at least one A-only hit survives the merge",
    );
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});
