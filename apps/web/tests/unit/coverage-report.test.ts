import assert from "node:assert/strict";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { keepAppSource, parseTapSummary, validateLcovText } from "../../scripts/coverage-merge.ts";

const webRoot = path.resolve(fileURLToPath(import.meta.url), "..", "..", "..");
const repoRoot = path.resolve(webRoot, "..", "..");

test("TAP summary counts passes, failures, and skips", () => {
  const tap = [
    "TAP version 13",
    "ok 1 - first passes",
    "not ok 2 - second fails",
    "ok 3 - third skipped # SKIP no browser",
    "1..3",
    "# pass 2",
    "# fail 1",
  ].join("\n");
  assert.deepEqual(parseTapSummary(tap), { pass: 2, fail: 1, skipped: 1 });
  assert.deepEqual(parseTapSummary(""), { pass: 0, fail: 0, skipped: 0 });
});

test("valid LCOV resolves every SF against the repo and counts hits", () => {
  const text = [
    "TN:",
    "SF:apps/web/package.json",
    "FN:1,load",
    "FNF:1",
    "FNH:1",
    "FNDA:3,load",
    "DA:1,2",
    "DA:2,0",
    "BRDA:1,0,0,2",
    "BRDA:1,0,1,0",
    "BRF:2",
    "BRH:1",
    "LF:2",
    "LH:1",
    "end_of_record",
    "TN:",
    "SF:apps/web/package-lock.json",
    "FN:1,empty",
    "FNF:1",
    "FNH:0",
    "FNDA:0,empty",
    "DA:1,0",
    "LF:1",
    "LH:0",
    "end_of_record",
  ].join("\n");
  const validity = validateLcovText(text, repoRoot);
  assert.deepEqual(validity.files, ["apps/web/package.json", "apps/web/package-lock.json"]);
  assert.equal(validity.records, 2);
  assert.equal(validity.totalHits, 1);
  assert.deepEqual(validity.zeroHitFiles, ["apps/web/package-lock.json"]);
  assert.equal(validity.branchRecords, 2);
});

test("LCOV validation rejects empty, missing, and hitless reports", () => {
  assert.throws(() => validateLcovText("", repoRoot), /no SF records/);
  assert.throws(
    () => validateLcovText("SF:apps/web/no-such-file.ts\nDA:1,1\nend_of_record\n", repoRoot),
    /missing from the repo/,
  );
  assert.throws(
    () => validateLcovText("SF:apps/web/package.json\nDA:1,0\nend_of_record\n", repoRoot),
    /zero executed lines/,
  );
});

test("only original app sources are kept for the report", () => {
  const src = (rest: string): string => path.join(webRoot, "src", rest);
  assert.equal(
    keepAppSource(src("app/features/screen/device-resolution.ts"), webRoot),
    src("app/features/screen/device-resolution.ts"),
  );
  assert.equal(
    keepAppSource(src("app/features/screen/SceneWorkspace.tsx"), webRoot),
    src("app/features/screen/SceneWorkspace.tsx"),
  );
  assert.equal(keepAppSource(src("app/renderer/wasm/font_wasm_bg.js"), webRoot), undefined);
  assert.equal(keepAppSource(path.join(webRoot, "tests/unit/x.test.ts"), webRoot), undefined);
  assert.equal(keepAppSource(path.join(webRoot, "node_modules/react/index.js"), webRoot), undefined);
  assert.equal(keepAppSource(src("components/ui/assets/device.svg"), webRoot), undefined);
  assert.equal(keepAppSource(path.join(repoRoot, "README.md"), webRoot), undefined);
});

test("TAP totals retain nested skips even when the parent passes", async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-tap-skip-"));
  try {
    const fixture = path.join(dir, "nested.test.mjs");
    await fs.writeFile(
      fixture,
      `import test from "node:test";
       test("parent", async (t) => {
         await t.test("skipped child", { skip: "unavailable input" }, () => {});
         await t.test("passing child", () => {});
       });`,
    );
    const env = { ...process.env };
    delete env.NODE_TEST_CONTEXT;
    const tap = execFileSync(process.execPath, ["--test", "--test-reporter=tap", fixture], {
      env,
      encoding: "utf8",
    });
    assert.match(tap, /^ok 1 - parent$/m);
    assert.deepEqual(parseTapSummary(tap), { pass: 2, fail: 0, skipped: 1 });
    assert.equal(parseTapSummary(tap.split(/^# tests /m)[0]!).skipped, 1, "incomplete TAP retains nested skips");
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});
