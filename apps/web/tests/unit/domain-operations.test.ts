// Operation classification regression: the Node direct path derives its
// write behavior from the same specification as the worker dispatch. A
// mutating call through the real command path bumps the domain version; a
// read or a skipped legacy import never does; unexposed names reject.
import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { getDomainVersion } from "../../src/app/domain/events.ts";
import { callDomain, type DomainMethod } from "../../src/app/domain/runtime.ts";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import type { LegacySnapshot } from "../../src/app/legacy-database.ts";

beforeEach(async () => {
  await resetDomainForTests();
});

after(async () => {
  await closeDomainForTests();
});

test("mutating calls notify while reads stay silent on the real command path", async () => {
  const before = getDomainVersion();
  await callDomain("setSeedMarker", ["probe"]);
  assert.equal(getDomainVersion(), before + 1);
  assert.equal(await callDomain("getSeedMarker", []), "probe");
  assert.equal(getDomainVersion(), before + 1);
  const palettes = (await callDomain("listPalettes", [])) as Array<{ name?: unknown }>;
  assert.deepEqual(
    palettes.map((preset) => preset.name),
    ["Monochrome"],
  );
  assert.equal(getDomainVersion(), before + 1);
});

test("a skipped legacy import reports no write on the real command path", async () => {
  const empty: LegacySnapshot = { fonts: [], variants: [], palettes: [], variantCount: 0 };
  const before = getDomainVersion();
  const first = await callDomain("importLegacySnapshot", [empty]);
  assert.equal((first as { skipped?: unknown }).skipped, false);
  assert.equal(getDomainVersion(), before + 1);
  const second = await callDomain("importLegacySnapshot", [empty]);
  assert.equal((second as { skipped?: unknown }).skipped, true);
  assert.equal(getDomainVersion(), before + 1);
});

test("unexposed names reject without touching state", async () => {
  const before = getDomainVersion();
  // Unknown methods, callable-but-never-exposed command exports
  // (curveProfile) and object-prototype names all fail closed at dispatch.
  for (const name of ["noSuchMethod", "curveProfile", "toString", "constructor"]) {
    await assert.rejects(callDomain(name as unknown as DomainMethod, []), /Unknown domain method/);
  }
  assert.equal(getDomainVersion(), before);
});
