import assert from "node:assert/strict";
import test from "node:test";
import { licenseBadge } from "../../src/app/fonts/metadata.ts";
import type { FontMetadata } from "../../src/app/fonts/storage.ts";

function metadata(license: string | null, url: string | null = null): FontMetadata {
  return { names: { license, license_url: url }, axes: [] };
}

test("license badges identify explicit notices and retain the original details", () => {
  const notice = "This Font Software is licensed under the SIL Open Font License, Version 1.1.";
  assert.deepEqual(licenseBadge(metadata(notice)), { label: "SIL OFL", description: notice });
  assert.equal(licenseBadge(metadata(null, "https://openfontlicense.org/")).label, "SIL OFL");
  assert.equal(licenseBadge(metadata("Licensed under the Apache License, Version 2.0")).label, "Apache 2.0");
  assert.equal(licenseBadge(metadata(null, "https://www.apache.org/licenses/LICENSE-2.0")).label, "Apache 2.0");
  assert.equal(licenseBadge(metadata("MIT License")).label, "MIT");
});

test("missing and unfamiliar licenses do not infer usage permissions", () => {
  assert.equal(licenseBadge(metadata(null)).label, "Unknown");
  const notice = "See the purchase agreement for license terms.";
  assert.deepEqual(licenseBadge(metadata(notice)), { label: "Provided", description: notice });
  assert.equal(licenseBadge(metadata(null, "https://example.com/openfontlicense.org/")).label, "Provided");
});
