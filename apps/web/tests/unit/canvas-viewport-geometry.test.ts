// Centered-viewport geometry: asymmetric bezels center the aperture (not the
// shell), ruler origins convert scroll to native px, and centered points
// survive zoom through the scroll round-trip.
import assert from "node:assert/strict";
import test from "node:test";
import {
  VIEWPORT_MARGIN,
  centeredContent,
  centerNative,
  centeringOffset,
  rulerScrollPos,
  rulerUnitForScale,
  scrollToCenterNative,
} from "../../src/app/features/screen/canvas-viewport-geometry.ts";

test("an asymmetric bezel centers the aperture in the content", () => {
  const content = centeredContent({
    bodyWidth: 100,
    bodyHeight: 200,
    apertureX: 5,
    apertureY: 30,
    apertureWidth: 80,
    apertureHeight: 120,
  });
  assert.equal(content.contentWidth, 100 + VIEWPORT_MARGIN * 2);
  assert.equal(content.canvasX + 80 / 2, content.contentWidth / 2);
  assert.equal(content.canvasY + 120 / 2, content.contentHeight / 2);
});

test("a centered aperture leaves the body on the plain margin", () => {
  const content = centeredContent({
    bodyWidth: 100,
    bodyHeight: 100,
    apertureX: 10,
    apertureY: 10,
    apertureWidth: 80,
    apertureHeight: 80,
  });
  assert.equal(content.bodyX, VIEWPORT_MARGIN);
  assert.equal(content.bodyY, VIEWPORT_MARGIN);
});

test("a hidden body centers the bare canvas", () => {
  const content = centeredContent({
    bodyWidth: 80,
    bodyHeight: 120,
    apertureX: 0,
    apertureY: 0,
    apertureWidth: 80,
    apertureHeight: 120,
  });
  assert.equal(content.canvasX, VIEWPORT_MARGIN);
  assert.equal(content.canvasX + 40, content.contentWidth / 2);
  assert.equal(content.canvasY + 60, content.contentHeight / 2);
});

test("ruler scroll position folds the aperture origin into native px", () => {
  assert.equal(rulerScrollPos(300, 800, 580, 250, 1), -60);
  assert.equal(rulerScrollPos(0, 800, 580, 250, 2), -180);
});

test("centering offset absorbs free space only while the content fits", () => {
  assert.equal(centeringOffset(800, 580), 110);
  assert.equal(centeringOffset(400, 580), 0);
});

test("the centered native point round-trips through scroll", () => {
  const native = centerNative(300, 800, 580, 250, 1);
  assert.equal(scrollToCenterNative(native, 800, 580, 250, 1, 1000), 300);
  assert.equal(scrollToCenterNative(native, 800, 580, 250, 2, 10000), 640);
});

test("scroll clamps at the content edges", () => {
  assert.equal(scrollToCenterNative(-1000, 800, 580, 250, 1, 500), 0);
  assert.equal(scrollToCenterNative(10000, 800, 580, 250, 1, 500), 500);
});

test("tick units stay in the 1/2/5 series and near readable density", () => {
  assert.equal(rulerUnitForScale(1), 50);
  assert.equal(rulerUnitForScale(4), 20);
  assert.equal(rulerUnitForScale(2), 50);
  for (const scale of [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4]) {
    const unit = rulerUnitForScale(scale);
    assert.ok([1, 2, 5].includes(unit / 10 ** Math.floor(Math.log10(unit))), `${scale}: ${unit}`);
    const px = unit * scale;
    assert.ok(px >= 48 && px < 130, `${scale}: ${unit} -> ${px}px`);
  }
});
