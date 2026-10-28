import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import test from "node:test";
import { resolveWorkingPreviewPolicy } from "../../src/app/renderer/preview-policy.ts";
import { fingerprintPreviewPolicy } from "../../scripts/policy-fingerprint.ts";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const bridge = path.join(webRoot, "scripts/landing-samples/preview-policy-bridge.ts");

function resolveThroughBridge(input: unknown): { policy: unknown; fingerprint: string } {
  const stdout = execFileSync("node", [bridge], {
    input: JSON.stringify(input),
    encoding: "utf8",
    cwd: webRoot,
  });
  return JSON.parse(stdout);
}

test("the Python bridge resolves the same policy as the live resolver", () => {
  const declared = {
    fitting: "font_hints_auto",
    rasterization: "free_type_mono_terminals",
    diagonal_fitting: true,
    dropout: "smart",
    include_stubs: true,
    font_instructions: true,
  };
  const { policy, fingerprint } = resolveThroughBridge(declared);
  const expected = resolveWorkingPreviewPolicy();
  assert.deepEqual(policy, expected);
  assert.equal(fingerprint, fingerprintPreviewPolicy(expected));
});

test("omitted bridge fields follow the shared defaults", () => {
  const { policy, fingerprint } = resolveThroughBridge({});
  const expected = resolveWorkingPreviewPolicy();
  assert.deepEqual(policy, expected);
  assert.equal(fingerprint, fingerprintPreviewPolicy(expected));
});

test("bridge overrides and rejections match the shared resolver", () => {
  const { policy } = resolveThroughBridge({
    fitting: "source_relative",
    rasterization: "free_type_mono",
    diagonal_fitting: false,
    dropout: "off",
    include_stubs: false,
    font_instructions: false,
  });
  assert.deepEqual(
    policy,
    resolveWorkingPreviewPolicy({
      fitting: "source_relative",
      rasterization: "free_type_mono",
      diagonalFitting: false,
      dropout: "off",
      includeStubs: false,
      fontInstructions: false,
    }),
  );
  assert.throws(
    () => resolveThroughBridge({ fitting: "source_relative", diagonal_fitting: true }),
    /Diagonal fitting requires/,
  );
});
