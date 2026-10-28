// cspell:words RLCD reflectivedisplay playdate ECDC RRGGBB paperwhite
// Provider tests for direct device + paper/ink palettes: distinct defaults,
// exact bytes, strict hex validation and immutable opaque results.
import assert from "node:assert/strict";
import test from "node:test";
import {
  REFLECTIVE_DEVICES,
  computeReflectiveDisplay,
  normalizeHexColor,
} from "../../src/app/renderer/reflective-display.ts";

test("each device resolves its own distinct illustrative default", () => {
  const waveshare = computeReflectiveDisplay({ device: "waveshare-esp32-s3-rlcd-4-2" });
  assert.equal(waveshare.paper, "#999999");
  assert.equal(waveshare.ink, "#282828");
  assert.deepEqual([...waveshare.palette[0]], [153, 153, 153, 255]);
  assert.deepEqual([...waveshare.palette[1]], [40, 40, 40, 255]);
  const inkplate = computeReflectiveDisplay({ device: "inkplate-4tempera" });
  assert.equal(inkplate.paper, "#999999");
  assert.equal(inkplate.ink, "#2D2D2D");
  assert.deepEqual([...inkplate.palette[0]], [153, 153, 153, 255]);
  assert.deepEqual([...inkplate.palette[1]], [45, 45, 45, 255]);
  const playdate = computeReflectiveDisplay({ device: "playdate" });
  assert.equal(playdate.paper, "#686868");
  assert.equal(playdate.ink, "#191919");
  assert.deepEqual([...playdate.palette[0]], [104, 104, 104, 255]);
  assert.deepEqual([...playdate.palette[1]], [25, 25, 25, 255]);
});

test("warm paper example colors convert to exact bytes", () => {
  const result = computeReflectiveDisplay({ device: "inkplate-4tempera", paper: "#F4ECDC", ink: "#000000" });
  assert.deepEqual([...result.palette[0]], [244, 236, 220, 255]);
  assert.deepEqual([...result.palette[1]], [0, 0, 0, 255]);
});

test("custom colors apply exactly with per-field origins", () => {
  const both = computeReflectiveDisplay({ device: "playdate", paper: "#FF0000", ink: "#0000FF" });
  assert.equal(both.paper, "#FF0000");
  assert.equal(both.ink, "#0000FF");
  assert.deepEqual([...both.palette[0]], [255, 0, 0, 255]);
  assert.deepEqual([...both.palette[1]], [0, 0, 255, 255]);
  assert.deepEqual({ ...both.origin }, { paper: "custom", ink: "custom" });
  const defaults = computeReflectiveDisplay({ device: "playdate" });
  assert.deepEqual({ ...defaults.origin }, { paper: "device-default", ink: "device-default" });
  const mixed = computeReflectiveDisplay({ device: "playdate", ink: "#0000FF" });
  assert.equal(mixed.paper, "#686868");
  assert.deepEqual({ ...mixed.origin }, { paper: "device-default", ink: "custom" });
});

test("hex colors normalize case consistently", () => {
  assert.equal(normalizeHexColor("paper", "#f4ecdc"), "#F4ECDC");
  const result = computeReflectiveDisplay({ device: "inkplate-4tempera", paper: "#f4ecdc", ink: "#000000" });
  assert.equal(result.paper, "#F4ECDC");
  assert.deepEqual([...result.palette[0]], [244, 236, 220, 255]);
});

test("no brightness order is imposed on paper and ink", () => {
  const inverted = computeReflectiveDisplay({ device: "playdate", paper: "#000000", ink: "#FFFFFF" });
  assert.deepEqual([...inverted.palette[0]], [0, 0, 0, 255]);
  assert.deepEqual([...inverted.palette[1]], [255, 255, 255, 255]);
});

test("strict hex validation rejects malformed colors", () => {
  for (const paper of ["F4ECDC", "#F4ECD", "#F4ECDCC", "#GGGGGG", "", "#F4E CD", 42, null]) {
    assert.throws(
      () => computeReflectiveDisplay({ device: "inkplate-4tempera", paper: paper as never }),
      /must be an opaque #RRGGBB color/,
    );
  }
  assert.throws(
    () => computeReflectiveDisplay({ device: "inkplate-4tempera", ink: "#fff" }),
    /must be an opaque #RRGGBB color/,
  );
});

test("unknown devices and inherited keys are rejected", () => {
  assert.throws(() => computeReflectiveDisplay({ device: "paperwhite" } as never), /unknown device/);
  assert.throws(() => computeReflectiveDisplay({ device: "toString" } as never), /unknown device/);
  assert.throws(() => computeReflectiveDisplay({ device: "constructor" } as never), /unknown device/);
  assert.throws(() => computeReflectiveDisplay({ device: 42 } as never), /unknown device/);
  assert.throws(() => computeReflectiveDisplay(null as never), /expected a config object/);
});

test("palette is opaque, frozen and the config is never mutated", () => {
  const config = Object.freeze({ device: "playdate", paper: "#F4ECDC", ink: "#000000" }) as {
    readonly device: "playdate";
    readonly paper: "#F4ECDC";
    readonly ink: "#000000";
  };
  const result = computeReflectiveDisplay(config);
  assert.deepEqual({ ...config }, { device: "playdate", paper: "#F4ECDC", ink: "#000000" });
  assert.ok(Object.isFrozen(result.palette));
  assert.ok(Object.isFrozen(result.palette[0]));
  assert.ok(Object.isFrozen(result.palette[1]));
  for (const entry of result.palette) {
    assert.equal(entry.length, 4);
    assert.equal(entry[3], 255);
  }
  assert.equal(result.device.id, "playdate");
  assert.ok(REFLECTIVE_DEVICES["playdate"].sources.length > 0);
});
