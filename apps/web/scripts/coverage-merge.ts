import { createRequire } from "node:module";
import path from "node:path";

// Pure merge and validation logic for the coverage producer. The CLI runner
// (scripts/coverage.ts) handles processes and files; the committed
// regression tests import these helpers directly.

const require = createRequire(import.meta.url);

interface V8Range {
  startOffset: number;
  endOffset: number;
  count: number;
}

interface V8Function {
  functionName: string;
  ranges: V8Range[];
  isBlockCoverage: boolean;
}

export interface SavedScript {
  url: string;
  scriptPath: string;
  source: string;
  sourceMap?: unknown;
  /** Set by the harness; absent in hand-built fixtures, treated as unreadable. */
  mapStatus?: "ok" | "no-comment" | "unreadable";
  functions: V8Function[];
}

export interface CoveredLocation {
  line: number;
  column: number;
}

export interface IstanbulFileCoverage {
  path: string;
  statementMap: Record<string, { start: CoveredLocation; end: CoveredLocation }>;
  s: Record<string, number>;
  fnMap: Record<string, { name: string; loc: { start: CoveredLocation; end: CoveredLocation } }>;
  f: Record<string, number>;
  branchMap: Record<string, { type: string; loc: { start: CoveredLocation; end: CoveredLocation } }>;
  b: Record<string, number[]>;
}

export type IstanbulMapData = Record<string, IstanbulFileCoverage>;

interface V8Converter {
  load(): Promise<void>;
  applyCoverage(blocks: V8Function[]): void;
  toIstanbul(): IstanbulMapData;
}

type V8Factory = (
  scriptPath: string,
  wrapperLength?: number,
  sources?: { source: string; sourceMap?: { sourcemap: unknown } },
) => V8Converter;

const V8ToIstanbul = require("v8-to-istanbul") as V8Factory;

const JS_EXTENSIONS = new Set([".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]);

// Generated renderer staging (copied build artifacts, not originals).
const GENERATED_DIRS = ["src/app/renderer/wasm/"];

function posix(absolute: string): string {
  return absolute.split(path.sep).join("/");
}

/**
 * Keep only original app sources: JS-family files under the web src tree,
 * excluding generated staging. Returns the absolute path, or undefined to
 * drop bundler output, vendor code, assets, tests, and harness files.
 */
export function keepAppSource(absolutePath: string, webRoot: string): string | undefined {
  const relative = path.relative(webRoot, absolutePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return undefined;
  const slash = posix(relative);
  if (!slash.startsWith("src/")) return undefined;
  if (GENERATED_DIRS.some((dir) => slash.startsWith(dir))) return undefined;
  if (!JS_EXTENSIONS.has(path.extname(slash))) return undefined;
  return absolutePath;
}

/**
 * Convert one independent V8 execution with a fresh converter. Repeated
 * applyCoverage on a shared converter is not additive (later ranges
 * overwrite earlier line counts), so every execution converts alone and
 * fragments combine through Istanbul merge below.
 */
export async function convertEntry(entry: SavedScript): Promise<IstanbulMapData> {
  const converter = V8ToIstanbul(
    entry.scriptPath,
    0,
    entry.sourceMap === undefined
      ? { source: entry.source }
      : { source: entry.source, sourceMap: { sourcemap: entry.sourceMap } },
  );
  await converter.load();
  converter.applyCoverage(entry.functions);
  return converter.toIstanbul();
}

/**
 * Convert saved Chromium V8 entries to Istanbul data keyed by absolute
 * original paths. Executions that share an original source, across
 * page loads or temp builds, coalesce by source location through
 * Istanbul merge (hit counts sum, identities stay single); scripts without
 * a usable sourcemap are reported as unmapped, never silently dropped
 * into a guess.
 */
export async function convertBrowserEntries(
  saved: SavedScript[],
  webRoot: string,
): Promise<{ data: IstanbulMapData; unmappedScripts: string[]; droppedFiles: string[] }> {
  const fragments: IstanbulMapData[] = [];
  const unmapped = new Set<string>();
  const dropped = new Set<string>();
  for (const entry of saved) {
    if (entry.sourceMap === undefined) {
      unmapped.add(entry.scriptPath);
      continue;
    }
    for (const [key, fileCoverage] of Object.entries(await convertEntry(entry))) {
      if (keepAppSource(key, webRoot) === undefined) {
        dropped.add(key);
        continue;
      }
      fragments.push({ [key]: fileCoverage });
    }
  }
  return { data: mergeMapData(fragments), unmappedScripts: [...unmapped], droppedFiles: [...dropped] };
}

interface CoverageMap {
  merge(data: IstanbulMapData): void;
  files(): string[];
}

type CoverageMapFactory = (data?: IstanbulMapData) => CoverageMap;

export function mergeMapData(parts: IstanbulMapData[]): IstanbulMapData {
  const libCoverage = require("istanbul-lib-coverage") as {
    createCoverageMap: CoverageMapFactory & ((data: IstanbulMapData) => { toJSON(): IstanbulMapData });
  };
  const combined = libCoverage.createCoverageMap({});
  for (const part of parts) combined.merge(part);
  const json = (combined as unknown as { toJSON(): IstanbulMapData }).toJSON();
  return json;
}

/** Write an LCOV report with SF paths relative to the repository root. */
export function writeLcov(data: IstanbulMapData, dir: string, repoRoot: string): void {
  const libCoverage = require("istanbul-lib-coverage") as { createCoverageMap: CoverageMapFactory };
  const libReport = require("istanbul-lib-report") as {
    createContext: (options: { dir: string; coverageMap: unknown }) => unknown;
  };
  const reports = require("istanbul-reports") as {
    create: (name: string, options: { file: string; projectRoot: string }) => { execute(context: unknown): void };
  };
  const map = libCoverage.createCoverageMap(data);
  const context = libReport.createContext({ dir, coverageMap: map });
  reports.create("lcovonly", { file: "lcov.info", projectRoot: repoRoot }).execute(context);
}

const LCOV_DA = /^DA:(\d+),(\d+)$/;
const LCOV_BRDA = /^BRDA:(\d+),([^,]*),([^,]*),(-|\d+)$/;

export interface LcovValidity {
  files: string[];
  records: number;
  totalHits: number;
  zeroHitFiles: string[];
  branchRecords: number;
}

/**
 * Structural validity for a merged report: every SF resolves to an existing
 * repo file, at least one record exists, and at least one line executed.
 * Zero-hit files stay listed (measured zero); they are never removed here.
 */
export function validateLcovText(text: string, repoRoot: string): LcovValidity {
  const files: string[] = [];
  let current: string | undefined;
  let records = 0;
  let totalHits = 0;
  let branchRecords = 0;
  const hitsByFile = new Map<string, number>();
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line.startsWith("SF:")) {
      current = line.slice(3);
      files.push(current);
      records += 1;
      hitsByFile.set(current, 0);
    } else if (line === "end_of_record") {
      current = undefined;
    } else if (current !== undefined) {
      const da = LCOV_DA.exec(line);
      if (da) {
        const hits = Number(da[2]);
        if (hits > 0) {
          totalHits += 1;
          hitsByFile.set(current, (hitsByFile.get(current) ?? 0) + 1);
        }
        continue;
      }
      if (LCOV_BRDA.exec(line)) branchRecords += 1;
    }
  }
  if (records === 0) throw new Error("LCOV has no SF records: nothing was mapped to original sources.");
  const missing = files.filter((file) => {
    try {
      return !require("node:fs").statSync(path.join(repoRoot, file)).isFile();
    } catch {
      return true;
    }
  });
  if (missing.length > 0)
    throw new Error(`LCOV lists ${missing.length} files missing from the repo: ${missing.slice(0, 5).join(", ")}`);
  if (totalHits === 0) throw new Error("LCOV records zero executed lines: collection produced no hits.");
  return {
    files,
    records,
    totalHits,
    zeroHitFiles: files.filter((file) => (hitsByFile.get(file) ?? 0) === 0),
    branchRecords,
  };
}

export interface TapSummary {
  pass: number;
  fail: number;
  skipped: number;
}

/** Machine-readable summary of a `node --test --test-reporter=tap` stream. */
export function parseTapSummary(tap: string): TapSummary {
  let pass = 0;
  let fail = 0;
  let skipped = 0;
  const totals: Partial<TapSummary> = {};
  for (const line of tap.split("\n")) {
    const total = /^# (pass|fail|skipped) (\d+)$/.exec(line);
    if (total) totals[total[1] as keyof TapSummary] = Number(total[2]);
    if (/^not ok\b/.test(line)) fail += 1;
    else if (/^ok\b/.test(line)) pass += 1;
    if (/^\s*ok\b.*# SKIP\b/.test(line)) skipped += 1;
  }
  // Node's final totals include nested tests whose skip never propagates
  // to the parent result. Keep the fallback for incomplete TAP streams.
  if (totals.pass !== undefined && totals.fail !== undefined && totals.skipped !== undefined) {
    return { pass: totals.pass, fail: totals.fail, skipped: totals.skipped };
  }
  return { pass, fail, skipped };
}
