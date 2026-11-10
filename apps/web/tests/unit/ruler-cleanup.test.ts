// Ruler host cleanup: the pinned core destroy() defect is contained while an
// unrelated destroy failure still surfaces, and the host is cleared either way.
import assert from "node:assert/strict";
import test from "node:test";
import { cleanupRulerHost, isKnownDestroyDefect } from "../../src/app/features/screen/ruler-cleanup.ts";

function fakeHost(): { cleared: number } & Pick<HTMLElement, "replaceChildren"> {
  const host = {
    cleared: 0,
    replaceChildren(): void {
      host.cleared += 1;
    },
  };
  return host;
}

test("the known core destroy TypeError is contained and the host is cleared", () => {
  const host = fakeHost();
  assert.equal(isKnownDestroyDefect(new TypeError("Cannot set properties of null (setting '__CROACT__')")), true);
  cleanupRulerHost(host, () => {
    throw new TypeError("Cannot set properties of null (setting '__CROACT__')");
  });
  assert.equal(host.cleared, 1);
});

test("an unrelated destroy failure propagates after the host is cleared", () => {
  const host = fakeHost();
  assert.equal(isKnownDestroyDefect(new Error("boom")), false);
  assert.equal(isKnownDestroyDefect(new TypeError("boom")), false);
  assert.throws(
    () =>
      cleanupRulerHost(host, () => {
        throw new Error("boom");
      }),
    /boom/,
  );
  assert.equal(host.cleared, 1);
});
