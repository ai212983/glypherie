// Compile-time regression for the operation specification: valid method
// calls typecheck through the real typed path, and invalid methods or
// arguments are rejected. Invalid examples never execute: they sit in an
// uncalled function so tsc checks them without running them.
import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { callDomain } from "../../src/app/domain/runtime.ts";
import type { PalettePreset } from "../../src/app/palettes/model.ts";

beforeEach(async () => {
  await resetDomainForTests();
});

after(async () => {
  await closeDomainForTests();
});

test("typed calls carry argument and result types end to end", async () => {
  const palettes: PalettePreset[] = await callDomain("listPalettes", []);
  assert.ok(Array.isArray(palettes));
  const id: number = await callDomain("createPalette", []);
  assert.equal(typeof id, "number");
  const marker: string | undefined = await callDomain("getSeedMarker", []);
  assert.ok(marker === undefined || typeof marker === "string");
});

// Never called: tsc still checks every line, so a mistyped call or a
// weakened signature fails the build without executing anything.
function invalidOperationExamples(): void {
  // @ts-expect-error unknown methods are rejected
  void callDomain("noSuchMethod", []);
  // @ts-expect-error scene creation needs its dimensions and profile
  void callDomain("createScene", [{ name: "Card" }]);
  // @ts-expect-error gray levels are numbers, not strings
  void callDomain("updatePalette", [1, { kind: "setLevel", index: 1, value: "10", depth: 4 }]);
  void (async (): Promise<void> => {
    // @ts-expect-error palette listings are presets, not counts
    const count: number = await callDomain("listPalettes", []);
    void count;
  })();
}

assert.equal(typeof invalidOperationExamples, "function");
