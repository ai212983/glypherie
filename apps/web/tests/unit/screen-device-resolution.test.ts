// Scene-to-device resolution: an explicit custom choice (null device) always
// stays a custom screen with the scene's own dimensions, never remapped to a
// catalog device. New compositions default to the first catalog device.
// The device list rides in as fixture data; production passes the shipped catalog.
import assert from "node:assert/strict";
import test from "node:test";
import {
  defaultNewSceneDevice,
  resolveSceneScreen,
} from "../../src/app/features/screen/device-resolution.ts";
import type { DeviceDefinition } from "../../src/app/devices/catalog.ts";

function device(id: string, width: number, height: number): DeviceDefinition {
  return {
    id,
    label: id,
    widthPx: width,
    heightPx: height,
    ppi: 200,
    ppiBasis: "advertised",
    shell: { src: "shells/fixture.svg", viewBox: [0, 0, 10, 10], screenRect: [0, 0, 10, 10] },
  };
}

const catalog = [device("playdate-like", 400, 240), device("shell-a", 480, 800), device("shell-b", 480, 800)];

test("an exact hint plus matching geometry resolves to that device", () => {
  const resolved = resolveSceneScreen({ width: 400, height: 240, deviceId: "playdate-like" }, catalog);
  assert.equal(resolved.device?.id, "playdate-like");
  assert.deepEqual([resolved.width, resolved.height], [400, 240]);
});

test("a hint with mismatched geometry falls back to custom without resizing", () => {
  const resolved = resolveSceneScreen({ width: 400, height: 241, deviceId: "playdate-like" }, catalog);
  assert.equal(resolved.device, null);
  assert.deepEqual([resolved.width, resolved.height], [400, 241]);
});

test("an unknown hint stays custom", () => {
  const resolved = resolveSceneScreen({ width: 400, height: 240, deviceId: "retired-device" }, catalog);
  assert.equal(resolved.device, null);
  assert.deepEqual([resolved.width, resolved.height], [400, 240]);
});

test("an explicit custom choice never maps back to the catalog", () => {
  // Even when the dimensions match exactly one catalog device, null means
  // the user picked custom, so the screen keeps its own size and no shell.
  const single = resolveSceneScreen({ width: 400, height: 240, deviceId: null }, catalog);
  assert.equal(single.device, null);
  assert.deepEqual([single.width, single.height], [400, 240]);
  // Ambiguous and unknown geometries stay custom too, keeping exact dimensions.
  const ambiguous = resolveSceneScreen({ width: 480, height: 800, deviceId: null }, catalog);
  assert.equal(ambiguous.device, null);
  assert.deepEqual([ambiguous.width, ambiguous.height], [480, 800]);
  const custom = resolveSceneScreen({ width: 123, height: 456, deviceId: null }, catalog);
  assert.equal(custom.device, null);
  assert.deepEqual([custom.width, custom.height], [123, 456]);
});

test("new compositions default to the first device", () => {
  assert.equal(defaultNewSceneDevice(catalog)?.id, "playdate-like");
  assert.equal(defaultNewSceneDevice([]), null);
});
