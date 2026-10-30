import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import { createHash } from "node:crypto";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  landingCaptureGuardPlugin,
  REGENERATE_COMMAND,
  validateLandingCaptures,
} from "../../scripts/landing-capture-guard.ts";
import {
  canonicalPreviewPolicyJson,
  resolveWorkingPreviewPolicy,
  type PreviewPolicyInput,
} from "../../src/app/renderer/preview-policy.ts";
import { fingerprintPreviewPolicy } from "../../scripts/policy-fingerprint.ts";

interface Fixture {
  repoRoot: string;
  assetsDir: string;
  matrixFile: string;
  configFile: string;
  captureFile: string;
}

const SNAKE_TO_CAMEL: Record<string, string> = {
  fitting: "fitting",
  rasterization: "rasterization",
  diagonal_fitting: "diagonalFitting",
  dropout: "dropout",
  include_stubs: "includeStubs",
  font_instructions: "fontInstructions",
};

function toPolicyInput(declared: Record<string, string | boolean>): PreviewPolicyInput {
  const input: Record<string, string | boolean> = {};
  for (const [key, value] of Object.entries(declared)) input[SNAKE_TO_CAMEL[key]!] = value;
  return input as PreviewPolicyInput;
}

// A capture exactly as the generator would record it for these declarations.
function recordedCapture(declared: Record<string, string | boolean>): Record<string, unknown> {
  const policy = resolveWorkingPreviewPolicy(toPolicyInput(declared));
  return {
    renderer_inputs: { ...declared },
    renderer_policy: JSON.parse(canonicalPreviewPolicyJson(policy)) as unknown,
    renderer_fingerprint: fingerprintPreviewPolicy(policy),
    glypherie_pipeline: {
      fitting: policy.fitting,
      rasterization: policy.rasterization,
      diagonal_fitting: policy.diagonal_fitting,
    },
    glypherie_scan: { ...policy.mono_raster },
  };
}

async function writeFixture(
  t: { after(callback: () => unknown): void },
  configCases: Array<Record<string, unknown>>,
  captures: Record<string, Record<string, unknown>>,
): Promise<Fixture> {
  const repoRoot = await fs.mkdtemp(path.join(os.tmpdir(), "landing-guard-"));
  t.after(() => fs.rm(repoRoot, { recursive: true, force: true }));
  const assetsDir = path.join(repoRoot, "assets");
  const configFile = path.join(repoRoot, "config.json");
  const matrixFile = path.join(assetsDir, "matrix.json");
  const owners: Array<Record<string, unknown>> = configCases.map((entry) => ({ family_id: "roboto", size_px: 16, axes: {}, ...entry }));
  await fs.writeFile(configFile, JSON.stringify(owners));
  const matrixCases = [];
  for (const [caseId, capture] of Object.entries(captures)) {
    const owner = owners.find((entry) => entry.id === caseId) ?? owners[0]!;
    const sampleDir = path.join(assetsDir, "samples", `${caseId}-abc123`);
    await fs.mkdir(sampleDir, { recursive: true });
    const captureFile = path.join(sampleDir, "capture.json");
    const bytes = Buffer.from("fixture image");
    await fs.writeFile(path.join(sampleDir, "repo.png"), bytes);
    await fs.writeFile(captureFile, JSON.stringify({
      inputs: { family_id: owner.family_id, size_px: owner.size_px, source_axes: owner.axes, text: owner.text, source_kerning: true },
      ...capture,
      samples: [{ id: "repo", file: "repo.png", display_sha256: createHash("sha256").update(bytes).digest("hex") }],
    }));
    matrixCases.push({
      id: caseId,
      family_id: owner.family_id,
      size_px: owner.size_px,
      axes: owner.axes,
      samples: [{ id: "repo", file: `samples/${caseId}-abc123/repo.png` }],
    });
  }
  await fs.writeFile(matrixFile, JSON.stringify({ cases: matrixCases }));
  const firstId = Object.keys(captures)[0]!;
  return {
    repoRoot,
    assetsDir,
    matrixFile,
    configFile,
    captureFile: path.join(assetsDir, "samples", `${firstId}-abc123`, "capture.json"),
  };
}

function optionsOf(fixture: Fixture): { assetsDir: string; matrixFile: string; configFile: string } {
  return { assetsDir: fixture.assetsDir, matrixFile: fixture.matrixFile, configFile: fixture.configFile };
}

async function readBytes(file: string): Promise<Buffer> {
  return fs.readFile(file);
}

test("a capture matching the current config and policy validates without rewriting files", async (t) => {
  const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": recordedCapture({}) });
  const before = await readBytes(fixture.captureFile);
  assert.deepEqual(await validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)), { checked: 1 });
  assert.deepEqual(await readBytes(fixture.captureFile), before, "validation never regenerates captures");
});

test("key order in the stored policy does not matter", async (t) => {
  const capture = recordedCapture({});
  capture.renderer_policy = Object.fromEntries(
    Object.entries(capture.renderer_policy as Record<string, unknown>).reverse(),
  );
  const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": capture });
  assert.deepEqual(await validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)), { checked: 1 });
});

test("captures with source kerning disabled or missing require regeneration", async (t) => {
  for (const sourceKerning of [false, undefined]) {
    const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": recordedCapture({}) });
    const capture = JSON.parse(await fs.readFile(fixture.captureFile, "utf8"));
    capture.inputs.source_kerning = sourceKerning;
    await fs.writeFile(fixture.captureFile, JSON.stringify(capture));
    await assert.rejects(() => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)), /enable source kerning/);
  }
});

test("capture identity and declared text must match the current matrix and case", async (t) => {
  for (const inputs of [
    { family_id: "rouge-script", size_px: 20, source_axes: {}, text: "two lines" },
    { family_id: "roboto", size_px: 16, source_axes: { wght: 900 }, text: "two lines" },
    { family_id: "roboto", size_px: 16, source_axes: {}, text: "stale third line" },
  ]) {
    const fixture = await writeFixture(t, [{ id: "roboto-16", text: "two lines" }], {
      "roboto-16": { ...recordedCapture({}), inputs },
    });
    await assert.rejects(() => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)), /capture inputs/);
  }
});

test("referenced PNG bytes and package membership are checked", async (t) => {
  const corrupted = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": recordedCapture({}) });
  await fs.writeFile(path.join(path.dirname(corrupted.captureFile), "repo.png"), "corrupt image");
  await assert.rejects(() => validateLandingCaptures(corrupted.repoRoot, optionsOf(corrupted)), /image checksum/);

  const mixed = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": recordedCapture({}) });
  const matrix = JSON.parse(await fs.readFile(mixed.matrixFile, "utf8"));
  matrix.cases[0].samples.push({ id: "foreign", file: "samples/other-abc123/foreign.png" });
  await fs.writeFile(mixed.matrixFile, JSON.stringify(matrix));
  await assert.rejects(() => validateLandingCaptures(mixed.repoRoot, optionsOf(mixed)), /sample package/);
});

test("every configured case appears exactly once in the matrix", async (t) => {
  const missing = await writeFixture(t, [{ id: "roboto-16" }, { id: "roboto-20", size_px: 20 }], {
    "roboto-16": recordedCapture({}),
  });
  await assert.rejects(() => validateLandingCaptures(missing.repoRoot, optionsOf(missing)), /missing configured case/);
  const duplicate = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": recordedCapture({}) });
  const matrix = JSON.parse(await fs.readFile(duplicate.matrixFile, "utf8"));
  matrix.cases.push(matrix.cases[0]);
  await fs.writeFile(duplicate.matrixFile, JSON.stringify(matrix));
  await assert.rejects(() => validateLandingCaptures(duplicate.repoRoot, optionsOf(duplicate)), /duplicate matrix case/);
});

test("a capture recorded under older defaults fails after the shared defaults move on", async (t) => {
  // The configuration declares nothing, so the current shared defaults
  // apply; the capture below was recorded as if include_stubs defaulted to
  // false. Resolution uses the current defaults, never the capture's
  // values, so the stale policy is rejected.
  const stale = resolveWorkingPreviewPolicy({ includeStubs: false });
  const capture = {
    renderer_inputs: {},
    renderer_policy: JSON.parse(canonicalPreviewPolicyJson(stale)) as unknown,
    renderer_fingerprint: fingerprintPreviewPolicy(stale),
    glypherie_pipeline: {
      fitting: stale.fitting,
      rasterization: stale.rasterization,
      diagonal_fitting: stale.diagonal_fitting,
    },
    glypherie_scan: { ...stale.mono_raster },
  };
  const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": capture });
  await assert.rejects(
    () => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)),
    /recorded Glypherie scan does not match/,
  );
});

test("a stale non-scan setting fails at the policy check", async (t) => {
  // Same pipeline and scan as today, but a setting the resolver changed
  // (here a threshold bump standing in for any future default change):
  // the recorded policy and fingerprint no longer match the recompute.
  const current = resolveWorkingPreviewPolicy();
  const stale = { ...current, mono_threshold: 129 };
  const capture = {
    ...recordedCapture({}),
    renderer_policy: JSON.parse(canonicalPreviewPolicyJson(stale)) as unknown,
    renderer_fingerprint: fingerprintPreviewPolicy(stale as typeof current),
  };
  const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": capture });
  await assert.rejects(
    () => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)),
    /renderer_policy no longer matches/,
  );
});

test("a tampered scan fails beside a valid policy and fingerprint", async (t) => {
  const capture = recordedCapture({});
  (capture.glypherie_scan as Record<string, unknown>).include_stubs = false;
  const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": capture });
  await assert.rejects(
    () => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)),
    /recorded Glypherie scan does not match/,
  );
});

test("a tampered pipeline fails beside a valid policy and fingerprint", async (t) => {
  for (const change of [{ fitting: "upstream_mono" }, { unknown_field: true }]) {
    const capture = recordedCapture({});
    Object.assign(capture.glypherie_pipeline as Record<string, unknown>, change);
    const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": capture });
    await assert.rejects(
      () => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)),
      /recorded Glypherie pipeline does not match/,
    );
  }
});

test("recorded declarations must match the current configuration", async (t) => {
  const configured = await writeFixture(
    t,
    [{ id: "roboto-16", dropout: "simple" }],
    { "roboto-16": recordedCapture({}) },
  );
  await assert.rejects(
    () => validateLandingCaptures(configured.repoRoot, optionsOf(configured)),
    /recorded renderer declarations differ/,
  );
  const recorded = await writeFixture(
    t,
    [{ id: "roboto-16" }],
    { "roboto-16": recordedCapture({ dropout: "simple" }) },
  );
  await assert.rejects(
    () => validateLandingCaptures(recorded.repoRoot, optionsOf(recorded)),
    /recorded renderer declarations differ/,
  );
});

test("explicit configuration overrides are honored", async (t) => {
  const declared = { dropout: "simple" };
  const fixture = await writeFixture(
    t,
    [{ id: "roboto-16", ...declared }],
    { "roboto-16": recordedCapture(declared) },
  );
  assert.deepEqual(await validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)), { checked: 1 });
});

test("missing renderer metadata fails with the regenerate command", async (t) => {
  const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": { samples: [] } });
  await assert.rejects(() => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)), (error: unknown) => {
    assert.match((error as Error).message, /renderer_inputs/);
    assert.ok((error as Error).message.includes(REGENERATE_COMMAND.slice(0, 40)));
    return true;
  });
});

test("corrupt declarations fail loudly instead of coercing to absent", async (t) => {
  const base = recordedCapture({});
  for (const [name, inputs] of [
    ["unknown key", { ...base.renderer_inputs as object, fontInstructionz: true }],
    ["null value", { dropout: null }],
    ["wrong type", { fitting: 42 }],
  ] as const) {
    const fixture = await writeFixture(t, [{ id: "roboto-16" }], {
      "roboto-16": { ...base, renderer_inputs: inputs },
    });
    await assert.rejects(
      () => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)),
      /unknown field|absent data|invalid type/,
      `${name} rejected`,
    );
  }
  const wrongTypeConfig = await writeFixture(t, [{ id: "roboto-16", dropout: 42 }], {
    "roboto-16": recordedCapture({}),
  });
  await assert.rejects(
    () => validateLandingCaptures(wrongTypeConfig.repoRoot, optionsOf(wrongTypeConfig)),
    /declares dropout with an invalid type/,
  );
});

test("a combination the resolver rejects fails with its declaration error", async (t) => {
  const declared = { fitting: "source_relative", diagonal_fitting: true };
  const fixture = await writeFixture(t, [{ id: "roboto-16", ...declared }], {
    "roboto-16": {
      renderer_inputs: { ...declared },
      renderer_policy: {},
      renderer_fingerprint: "0".repeat(64),
      glypherie_pipeline: {},
      glypherie_scan: {},
    },
  });
  await assert.rejects(
    () => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)),
    /declared renderer inputs are invalid/,
  );
});

test("a matrix case without an owning configuration entry fails", async (t) => {
  const fixture = await writeFixture(t, [{ id: "other-case" }], { "roboto-16": recordedCapture({}) });
  await assert.rejects(
    () => validateLandingCaptures(fixture.repoRoot, optionsOf(fixture)),
    /no owning entry/,
  );
});

test("the build hook revalidates on every build", async (t) => {
  const fixture = await writeFixture(t, [{ id: "roboto-16" }], { "roboto-16": recordedCapture({}) });
  const plugin = landingCaptureGuardPlugin(fixture.repoRoot, optionsOf(fixture));
  assert.equal(plugin.name, "landing-capture-guard");
  await plugin.buildStart();
  const capture = JSON.parse(await fs.readFile(fixture.captureFile, "utf8")) as Record<string, unknown>;
  capture.renderer_fingerprint = "0".repeat(64);
  await fs.writeFile(fixture.captureFile, JSON.stringify(capture));
  await assert.rejects(() => plugin.buildStart(), /fingerprint does not match/);
});
