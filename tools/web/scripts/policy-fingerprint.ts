// Node-only hashing keeps the shared policy usable in the browser.
import { createHash } from "node:crypto";
import {
  canonicalPreviewPolicyJson,
  type ResolvedPreviewPolicy,
} from "../src/app/renderer/preview-policy.ts";

export function fingerprintPreviewPolicy(policy: ResolvedPreviewPolicy): string {
  return createHash("sha256").update(canonicalPreviewPolicyJson(policy), "utf8").digest("hex");
}
