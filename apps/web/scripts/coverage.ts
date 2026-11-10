import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  convertBrowserEntries,
  keepAppSource,
  mergeMapData,
  parseTapSummary,
  validateLcovText,
  writeLcov,
  type IstanbulMapData,
  type SavedScript,
} from "./coverage-merge.ts";

const webRoot = path.resolve(fileURLToPath(import.meta.url), "..", "..");
const repoRoot = path.resolve(webRoot, "..", "..");
const coverageDir = path.join(webRoot, "coverage");
const lcovPath = path.join(coverageDir, "lcov.info");
const summaryPath = path.join(coverageDir, "summary.json");

interface Selection {
  unit: string[];
  browser: string[];
}

async function defaultSelection(): Promise<Selection> {
  async function tests(dir: string): Promise<string[]> {
    const names = await fs.readdir(path.join(webRoot, "tests", dir));
    return names
      .filter((name) => name.endsWith(".test.ts"))
      .sort()
      .map((name) => path.join("tests", dir, name));
  }
  return { unit: await tests("unit"), browser: await tests("browser") };
}

function resolveSelection(args: string[]): Selection {
  const unit: string[] = [];
  const browser: string[] = [];
  for (const arg of args) {
    const absolute = path.resolve(webRoot, arg);
    const relative = path.relative(webRoot, absolute);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
      throw new Error(`Selection must stay inside apps/web: ${arg}`);
    }
    const slash = relative.split(path.sep).join("/");
    if (slash.startsWith("tests/unit/") && slash.endsWith(".test.ts")) unit.push(relative);
    else if (slash.startsWith("tests/browser/") && slash.endsWith(".test.ts")) browser.push(relative);
    else throw new Error(`Select tests under tests/unit or tests/browser (build tests excluded): ${arg}`);
  }
  unit.sort();
  browser.sort();
  return { unit, browser };
}

interface RunResult {
  tap: string;
  exitCode: number;
}

function runTests(label: string, files: string[], extraEnv: NodeJS.ProcessEnv): Promise<RunResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ["--test", "--test-reporter=tap", ...files], {
      cwd: webRoot,
      env: { ...process.env, ...extraEnv },
      stdio: ["ignore", "pipe", "inherit"],
    });
    let tap = "";
    child.stdout.on("data", (chunk: Buffer) => {
      tap += chunk.toString("utf8");
    });
    child.on("error", reject);
    child.on("close", (code) => resolve({ tap, exitCode: code ?? 1 }));
    console.log(`[coverage] ${label}: ${files.length} file(s)`);
  });
}

async function runUnitC8(files: string[], c8dir: string, env: NodeJS.ProcessEnv): Promise<RunResult> {
  const c8 = path.join(webRoot, "node_modules", "c8", "bin", "c8.js");
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [c8, "--reporter=json", "--reports-dir", c8dir, process.execPath, "--test", "--test-reporter=tap", ...files],
      { cwd: webRoot, env: { ...process.env, ...env }, stdio: ["ignore", "pipe", "inherit"] },
    );
    let tap = "";
    child.stdout.on("data", (chunk: Buffer) => {
      tap += chunk.toString("utf8");
    });
    child.on("error", reject);
    child.on("close", (code) => resolve({ tap, exitCode: code ?? 1 }));
    console.log(`[coverage] unit: ${files.length} file(s) under c8`);
  });
}

function fail(message: string): never {
  console.error(`[coverage] FAIL: ${message}`);
  process.exit(1);
}

async function readSavedScripts(dir: string): Promise<SavedScript[]> {
  const names = await fs.readdir(dir).catch(() => []);
  const saved: SavedScript[] = [];
  for (const name of names.sort()) {
    if (!name.startsWith("v8-") || !name.endsWith(".json")) continue;
    const parsed = JSON.parse(await fs.readFile(path.join(dir, name), "utf8")) as SavedScript[];
    saved.push(...parsed);
  }
  return saved;
}

/** Refuse to publish when any page failed collection; partial is not valid. */
async function rejectCollectionFailures(dir: string): Promise<void> {
  const names = await fs.readdir(dir).catch(() => []);
  const failed = names.filter((name) => name.startsWith("failed-")).sort();
  if (failed.length === 0) return;
  const details = await Promise.all(failed.slice(0, 5).map((name) => fs.readFile(path.join(dir, name), "utf8")));
  fail(`${failed.length} page(s) failed coverage collection; report not published: ${details.join("; ")}`);
}

async function check(): Promise<void> {
  const text = await fs
    .readFile(lcovPath, "utf8")
    .catch(() => fail("no report at apps/web/coverage/lcov.info; run `npm run coverage` first."));
  const summary = JSON.parse(
    await fs.readFile(summaryPath, "utf8").catch(() => fail("report summary is missing; the report is incomplete.")),
  ) as {
    createdAt: string;
    selection: Selection;
  };
  const validity = validateLcovText(text, repoRoot);
  const reportTime = (await fs.stat(lcovPath)).mtimeMs;
  // Selections are web-relative, SF records repo-relative: resolve each
  // coordinate from its actual root.
  const selected = [...summary.selection.unit, ...summary.selection.browser].map((relative) =>
    path.join(webRoot, relative),
  );
  const stale: string[] = [];
  for (const absolute of [...selected, ...validity.files.map((file) => path.join(repoRoot, file))]) {
    try {
      if ((await fs.stat(absolute)).mtimeMs > reportTime) stale.push(path.relative(repoRoot, absolute));
    } catch {
      stale.push(`${path.relative(repoRoot, absolute)} (missing)`);
    }
  }
  console.log(
    `[coverage] report: ${validity.records} file(s), ${validity.totalHits} executed line(s), ${validity.branchRecords} branch record(s), created ${summary.createdAt}`,
  );
  console.log(
    `[coverage] selection: ${summary.selection.unit.length} unit + ${summary.selection.browser.length} browser file(s)`,
  );
  if (stale.length > 0)
    fail(`stale report: ${stale.length} source/test file(s) changed since collection: ${stale.slice(0, 5).join(", ")}`);
  console.log("[coverage] OK: report is valid and newer than its sources.");
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  if (args.includes("--check")) {
    await check();
    return;
  }
  const selection = args.length > 0 ? resolveSelection(args) : await defaultSelection();
  if (selection.unit.length + selection.browser.length === 0) fail("no test files selected.");
  if (args.length === 0) console.log("[coverage] default: all unit + browser tests (build tests excluded).");

  const runStart = Date.now();
  await fs.rm(coverageDir, { recursive: true, force: true });
  await fs.mkdir(coverageDir, { recursive: true });
  const work = await fs.mkdtemp(path.join(os.tmpdir(), "glypherie-coverage-"));
  const c8dir = path.join(work, "c8");
  const v8dir = path.join(work, "v8");
  await fs.mkdir(v8dir, { recursive: true });
  const childEnv = { GLYPHERIE_COVERAGE: "1", GLYPHERIE_COVERAGE_DIR: v8dir };

  let pass = 0;
  let skipped = 0;
  const parts: IstanbulMapData[] = [];

  if (selection.unit.length > 0) {
    const result = await runUnitC8(selection.unit, c8dir, childEnv);
    const summary = parseTapSummary(result.tap);
    pass += summary.pass;
    skipped += summary.skipped;
    if (result.exitCode !== 0 || summary.fail > 0)
      fail(`unit tests failed (${summary.fail} failing, exit ${result.exitCode}); report not published.`);
    const final = JSON.parse(
      await fs
        .readFile(path.join(c8dir, "coverage-final.json"), "utf8")
        .catch(() => fail("c8 wrote no coverage-final.json.")),
    ) as IstanbulMapData;
    parts.push(final);
  }
  if (selection.browser.length > 0) {
    const result = await runTests("browser", selection.browser, childEnv);
    const summary = parseTapSummary(result.tap);
    pass += summary.pass;
    skipped += summary.skipped;
    if (result.exitCode !== 0 || summary.fail > 0)
      fail(`browser tests failed (${summary.fail} failing, exit ${result.exitCode}); report not published.`);
  }
  if (skipped > 0)
    fail(`${skipped} selected test(s) skipped (a missing browser skips every browser test); report not published.`);

  await rejectCollectionFailures(v8dir);
  const saved = await readSavedScripts(v8dir);
  const unreadable = saved.filter((entry) => (entry.mapStatus ?? "unreadable") === "unreadable");
  if (unreadable.length > 0) {
    fail(
      `${unreadable.length} served script(s) named an unreadable sourcemap; mappings would be silently lost: ${unreadable
        .slice(0, 5)
        .map((entry) => entry.url)
        .join(", ")}`,
    );
  }
  const converted = await convertBrowserEntries(saved, webRoot);
  if (selection.browser.length > 0 && Object.keys(converted.data).length === 0) {
    fail(
      `browser collection mapped zero app sources (${converted.unmappedScripts.length} unmapped script(s)); check sourcemaps.`,
    );
  }
  if (converted.unmappedScripts.length > 0) {
    console.log(`[coverage] note: ${converted.unmappedScripts.length} script(s) without usable sourcemaps excluded.`);
  }
  parts.push(converted.data);

  const kept: IstanbulMapData = {};
  for (const [key, fileCoverage] of Object.entries(mergeMapData(parts))) {
    if (keepAppSource(key, webRoot) !== undefined) kept[key] = fileCoverage;
  }
  if (Object.keys(kept).length === 0) fail("merged coverage mapped zero app sources; report not published.");
  writeLcov(kept, work, repoRoot);
  const text = await fs.readFile(path.join(work, "lcov.info"), "utf8");
  const validity = validateLcovText(text, repoRoot);

  const staging = path.join(coverageDir, "lcov.info.tmp");
  await fs.writeFile(staging, text);
  await fs.rename(staging, lcovPath);
  await fs.writeFile(
    summaryPath,
    JSON.stringify(
      {
        createdAt: new Date(runStart).toISOString(),
        selection,
        tests: { pass, skipped },
        files: validity.records,
        totalLineHits: validity.totalHits,
        zeroHitFiles: validity.zeroHitFiles.length,
        branchRecords: validity.branchRecords,
        unmappedScripts: converted.unmappedScripts.length,
        scope:
          "main-thread Node unit + Chromium page execution; SharedWorker/WASM/asset sources excluded, unlisted files unmeasured (not zero).",
      },
      null,
      2,
    ),
  );
  await fs.rm(work, { recursive: true, force: true });
  console.log(
    `[coverage] OK: ${validity.records} file(s), ${validity.totalHits} executed line(s) in ${path.relative(repoRoot, lcovPath)} from ${pass} passing test(s).`,
  );
}

main().catch((error: unknown) => fail(error instanceof Error ? error.message : String(error)));
