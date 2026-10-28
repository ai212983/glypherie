// Reads renderer overrides as JSON on stdin; writes { policy, fingerprint }.
// Usage: node preview-policy-bridge.ts < request.json
import { resolveWorkingPreviewPolicy } from "../../src/app/renderer/preview-policy.ts";
import { fingerprintPreviewPolicy } from "../policy-fingerprint.ts";

const raw = await new Promise<string>((resolve, reject) => {
  let text = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => { text += chunk; });
  process.stdin.on("end", () => resolve(text));
  process.stdin.on("error", reject);
});

let input: Record<string, unknown>;
try {
  input = JSON.parse(raw || "{}");
} catch {
  console.error("preview-policy-bridge: stdin is not valid JSON.");
  process.exit(1);
}

function booleanField(value: unknown, name: string): boolean | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "boolean") {
    console.error(`preview-policy-bridge: ${name} must be a boolean.`);
    process.exit(1);
  }
  return value;
}

function stringField(value: unknown, name: string): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string") {
    console.error(`preview-policy-bridge: ${name} must be a string.`);
    process.exit(1);
  }
  return value;
}

try {
  const policy = resolveWorkingPreviewPolicy({
    fitting: stringField(input.fitting, "fitting"),
    rasterization: stringField(input.rasterization, "rasterization"),
    diagonalFitting: booleanField(
      input.diagonalFitting ?? input.diagonal_fitting,
      "diagonal_fitting",
    ),
    dropout: stringField(input.dropout, "dropout"),
    includeStubs: booleanField(input.includeStubs ?? input.include_stubs, "include_stubs"),
    fontInstructions: booleanField(
      input.fontInstructions ?? input.font_instructions,
      "font_instructions",
    ),
  });
  process.stdout.write(JSON.stringify({
    policy,
    fingerprint: fingerprintPreviewPolicy(policy),
  }) + "\n");
} catch (error) {
  console.error(`preview-policy-bridge: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
