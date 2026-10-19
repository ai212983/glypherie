import assert from "node:assert/strict";
import test from "node:test";
import { kerningQueryKey } from "../../src/app/features/preview/kerning.ts";

test("kerning cache identity separates fonts sharing a size/axes coordinate", () => {
  const axes = { wght: 400, wdth: 100 };
  assert.notEqual(
    kerningQueryKey("roboto", 16, axes),
    kerningQueryKey("roboto-italic", 16, axes),
    "same coordinate on another font is a different entry",
  );
  assert.equal(
    kerningQueryKey("roboto", 16, axes),
    kerningQueryKey("roboto", 16, { wdth: 100, wght: 400 }),
    "axis key order does not matter",
  );
  assert.notEqual(
    kerningQueryKey("roboto", 16, axes),
    kerningQueryKey("roboto", 18, axes),
    "size separates entries",
  );
});
