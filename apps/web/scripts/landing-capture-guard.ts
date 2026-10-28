// Validate active landing packages against current case inputs and renderer policy.
// Builds check existing artifacts; capture regeneration remains a separate command.
import { promises as fs } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import {
  canonicalPreviewPolicyJson,
  resolveWorkingPreviewPolicy,
  type PreviewPolicyInput,
} from "../src/app/renderer/preview-policy.ts";
import { fingerprintPreviewPolicy } from "./policy-fingerprint.ts";

export const REGENERATE_COMMAND =
  "just landing-samples --config apps/web/scripts/landing-samples/main-page.json --publish-matrix";

export interface LandingCaptureGuardOptions {
  assetsDir?: string;
  matrixFile?: string;
  configFile?: string;
}

const RENDERER_KEYS = [
  "fitting",
  "rasterization",
  "diagonal_fitting",
  "dropout",
  "include_stubs",
  "font_instructions",
] as const;

type DeclaredRenderer = Partial<Record<(typeof RENDERER_KEYS)[number], string | boolean>>;

function fail(caseId: string, why: string): never {
  throw new Error(
    `landing capture ${caseId}: ${why}. Regenerate captures with \`${REGENERATE_COMMAND}\` then rebuild.`,
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isBooleanKey(key: string): boolean {
  return key === "diagonal_fitting" || key === "include_stubs" || key === "font_instructions";
}

// Config null means inherit; recorded declarations must be explicit.
function declaredFromConfig(entry: Record<string, unknown>, caseId: string): DeclaredRenderer {
  const declared: Record<string, string | boolean> = {};
  for (const key of RENDERER_KEYS) {
    if (!(key in entry)) continue;
    const value: unknown = entry[key];
    if (value === undefined || value === null) continue;
    if (isBooleanKey(key) ? typeof value !== "boolean" : typeof value !== "string") {
      fail(caseId, `owning configuration declares ${key} with an invalid type`);
    }
    declared[key] = value as string | boolean;
  }
  return declared;
}

function declaredFromRecord(inputs: unknown, caseId: string): DeclaredRenderer {
  if (!isRecord(inputs)) {
    fail(caseId, "capture.json lacks renderer_inputs from the shared preview policy");
  }
  for (const key of Object.keys(inputs)) {
    if (!(RENDERER_KEYS as readonly string[]).includes(key)) {
      fail(caseId, `renderer_inputs holds unknown field ${JSON.stringify(key)}`);
    }
  }
  const declared: Record<string, string | boolean> = {};
  for (const key of RENDERER_KEYS) {
    if (!(key in inputs)) continue;
    const value: unknown = inputs[key];
    if (value === undefined || value === null) {
      fail(caseId, `renderer_inputs holds ${key} as absent data`);
    }
    if (isBooleanKey(key) ? typeof value !== "boolean" : typeof value !== "string") {
      fail(caseId, `renderer_inputs holds ${key} with an invalid type`);
    }
    declared[key] = value as string | boolean;
  }
  return declared;
}

function toPolicyInput(declared: DeclaredRenderer): PreviewPolicyInput {
  return {
    ...(typeof declared.fitting === "string" ? { fitting: declared.fitting } : {}),
    ...(typeof declared.rasterization === "string" ? { rasterization: declared.rasterization } : {}),
    ...(typeof declared.diagonal_fitting === "boolean" ? { diagonalFitting: declared.diagonal_fitting } : {}),
    ...(typeof declared.dropout === "string" ? { dropout: declared.dropout } : {}),
    ...(typeof declared.include_stubs === "boolean" ? { includeStubs: declared.include_stubs } : {}),
    ...(typeof declared.font_instructions === "boolean"
      ? { fontInstructions: declared.font_instructions }
      : {}),
  };
}

function validateCaptureInputs(
  caseId: string, entry: Record<string, unknown>, owner: Record<string, unknown>, capture: Record<string, unknown>,
): void {
  const inputs = capture.inputs;
  if (!isRecord(inputs) || !isRecord(entry.axes)
    || inputs.family_id !== entry.family_id || inputs.size_px !== entry.size_px
    || canonicalPreviewPolicyJson(inputs.source_axes) !== canonicalPreviewPolicyJson(entry.axes)
    || entry.family_id !== owner.family_id || entry.size_px !== owner.size_px) {
    fail(caseId, "capture inputs do not match the configured matrix case");
  }
  const axes = entry.axes as Record<string, unknown>;
  if (owner.axes !== undefined) {
    if (!isRecord(owner.axes)
      || Object.entries(owner.axes).some(([tag, value]) => axes[tag] !== value)) {
      fail(caseId, "capture inputs do not match configured axes");
    }
  }
  if (owner.text !== undefined && inputs.text !== owner.text) {
    fail(caseId, "capture inputs do not match configured text");
  }
}

async function validateSampleAssets(
  caseId: string, assetsDir: string, samples: unknown[], capture: Record<string, unknown>,
): Promise<void> {
  if (!Array.isArray(capture.samples) || capture.samples.length !== samples.length) {
    fail(caseId, "sample package membership does not match the capture");
  }
  const first = samples[0] as Record<string, unknown>;
  const packageDir = path.posix.dirname(first.file as string);
  const ids = new Set<string>();
  for (const sample of samples) {
    if (!isRecord(sample) || typeof sample.id !== "string" || typeof sample.file !== "string"
      || !/^samples\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+\.png$/.test(sample.file)
      || path.posix.dirname(sample.file) !== packageDir || ids.has(sample.id)) {
      fail(caseId, "invalid sample package membership");
    }
    ids.add(sample.id);
    const recorded = capture.samples.find((item: unknown) => isRecord(item) && item.id === sample.id);
    if (!isRecord(recorded) || sample.file !== `${packageDir}/${recorded.file}`) {
      fail(caseId, "sample package does not match its capture manifest");
    }
    let bytes: Buffer;
    try {
      bytes = await fs.readFile(path.join(assetsDir, sample.file));
    } catch {
      fail(caseId, `cannot read sample image ${sample.file}`);
    }
    if (createHash("sha256").update(bytes).digest("hex") !== recorded.display_sha256) {
      fail(caseId, `image checksum mismatch for ${sample.id}`);
    }
  }
}

/** Validate selected captures without changing assets. */
export async function validateLandingCaptures(
  repoRoot: string,
  options: LandingCaptureGuardOptions = {},
): Promise<{ checked: number }> {
  const assetsDir = options.assetsDir
    ?? path.join(repoRoot, "apps/web/src/app/features/landing/assets/rasterizers");
  const matrixFile = options.matrixFile ?? path.join(assetsDir, "matrix.json");
  const configFile = options.configFile
    ?? path.join(repoRoot, "apps/web/scripts/landing-samples/main-page.json");
  let matrix: unknown;
  try {
    matrix = JSON.parse(await fs.readFile(matrixFile, "utf8"));
  } catch (error) {
    throw new Error(
      `landing capture guard: cannot read matrix ${matrixFile} (${error instanceof Error ? error.message : String(error)}).`,
    );
  }
  if (!isRecord(matrix) || !Array.isArray(matrix.cases)) {
    throw new Error(`landing capture guard: ${matrixFile} has no cases array.`);
  }
  let config: unknown;
  try {
    config = JSON.parse(await fs.readFile(configFile, "utf8"));
  } catch (error) {
    throw new Error(
      `landing capture guard: cannot read owning configuration ${configFile} (${error instanceof Error ? error.message : String(error)}).`,
    );
  }
  if (!Array.isArray(config)) {
    throw new Error(`landing capture guard: ${configFile} is not a case array.`);
  }
  const owning = new Map<string, Record<string, unknown>>();
  for (const entry of config) {
    if (!isRecord(entry) || typeof entry.id !== "string" || owning.has(entry.id)) {
      throw new Error("landing capture guard: malformed or duplicate configured case.");
    }
    owning.set(entry.id, entry);
  }
  let checked = 0;
  const seen = new Set<string>();
  for (const entry of matrix.cases) {
    if (!isRecord(entry) || typeof entry.id !== "string" || !Array.isArray(entry.samples)) {
      throw new Error(`landing capture guard: ${matrixFile} holds a malformed case entry.`);
    }
    const caseId = entry.id;
    if (seen.has(caseId)) fail(caseId, "duplicate matrix case");
    seen.add(caseId);
    const first = entry.samples[0];
    if (!isRecord(first) || typeof first.file !== "string"
      || !/^samples\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+\.png$/.test(first.file)) {
      fail(caseId, "matrix entry has no sample file");
    }
    const owner = owning.get(caseId);
    if (!owner) {
      fail(caseId, `matrix case has no owning entry in ${path.basename(configFile)}`);
    }
    const captureFile = path.join(assetsDir, path.dirname(first.file), "capture.json");
    let capture: unknown;
    try {
      capture = JSON.parse(await fs.readFile(captureFile, "utf8"));
    } catch (error) {
      fail(caseId, `cannot read ${path.relative(repoRoot, captureFile)} (${error instanceof Error ? error.message : String(error)})`);
    }
    if (!isRecord(capture)) fail(caseId, "capture.json is not an object");
    const recorded = declaredFromRecord(capture.renderer_inputs, caseId);
    const configured = declaredFromConfig(owner, caseId);
    if (canonicalPreviewPolicyJson(recorded) !== canonicalPreviewPolicyJson(configured)) {
      fail(caseId, `recorded renderer declarations differ from the current ${path.basename(configFile)}`);
    }
    let expected: ReturnType<typeof resolveWorkingPreviewPolicy>;
    try {
      expected = resolveWorkingPreviewPolicy(toPolicyInput(configured));
    } catch (error) {
      fail(caseId, `declared renderer inputs are invalid (${error instanceof Error ? error.message : String(error)})`);
    }
    validateCaptureInputs(caseId, entry, owner, capture);
    const pipeline = capture.glypherie_pipeline;
    const expectedPipeline = {
      fitting: expected.fitting,
      rasterization: expected.rasterization,
      diagonal_fitting: expected.diagonal_fitting,
    };
    if (!isRecord(pipeline)
      || canonicalPreviewPolicyJson(pipeline) !== canonicalPreviewPolicyJson(expectedPipeline)) {
      fail(caseId, "recorded Glypherie pipeline does not match the resolved policy");
    }
    const scan = capture.glypherie_scan;
    if (!isRecord(scan) || canonicalPreviewPolicyJson(scan) !== canonicalPreviewPolicyJson(expected.mono_raster)) {
      fail(caseId, "recorded Glypherie scan does not match the resolved policy");
    }
    const expectedJson = canonicalPreviewPolicyJson(expected);
    if (!isRecord(capture.renderer_policy) || canonicalPreviewPolicyJson(capture.renderer_policy) !== expectedJson) {
      fail(caseId, "renderer_policy no longer matches the shared working-preview policy for its declared inputs");
    }
    if (capture.renderer_fingerprint !== fingerprintPreviewPolicy(expected)) {
      fail(caseId, "renderer_fingerprint does not match the shared working-preview policy");
    }
    await validateSampleAssets(caseId, assetsDir, entry.samples, capture);
    checked += 1;
  }
  if (checked === 0) {
    throw new Error("landing capture guard: matrix holds no cases to check.");
  }
  for (const caseId of owning.keys()) {
    if (!seen.has(caseId)) fail(caseId, "missing configured case from matrix");
  }
  return { checked };
}

/** Vite plugin: enforce the guard on every production build, never during dev. */
export function landingCaptureGuardPlugin(
  repoRoot: string,
  options: LandingCaptureGuardOptions = {},
): { name: string; buildStart(): Promise<void> } {
  return {
    name: "landing-capture-guard",
    async buildStart() {
      await validateLandingCaptures(repoRoot, options);
    },
  };
}
