// Device zoom view state: presets default to 100%, the shell shows only at
// 100% with the body preference on, and the toggle is unavailable for
// custom screens or while zoomed (the stored preference is preserved).
import assert from "node:assert/strict";
import test from "node:test";
import {
  DEVICE_ZOOM_DEFAULT,
  DEVICE_ZOOM_PRESETS,
  isDeviceBodyToggleDisabled,
  isDeviceZoomPercent,
  resolveDeviceBodyVisible,
} from "../../src/app/features/screen/device-zoom.ts";

test("zoom presets default to 100% and validate membership", () => {
  assert.equal(DEVICE_ZOOM_DEFAULT, 100);
  assert.ok((DEVICE_ZOOM_PRESETS as readonly number[]).includes(100));
  assert.ok(isDeviceZoomPercent(25) && isDeviceZoomPercent(400));
  assert.equal(isDeviceZoomPercent(90), false);
});

test("the shell shows only for a catalog device at 100% with the preference on", () => {
  assert.equal(resolveDeviceBodyVisible({ hasDevice: true, bodyPreference: true, zoomPercent: 100 }), true);
  assert.equal(resolveDeviceBodyVisible({ hasDevice: true, bodyPreference: false, zoomPercent: 100 }), false);
  assert.equal(resolveDeviceBodyVisible({ hasDevice: true, bodyPreference: true, zoomPercent: 200 }), false);
  assert.equal(resolveDeviceBodyVisible({ hasDevice: false, bodyPreference: true, zoomPercent: 100 }), false);
});

test("the body toggle is disabled for custom screens and while zoomed", () => {
  assert.equal(isDeviceBodyToggleDisabled({ hasDevice: true, zoomPercent: 100 }), false);
  assert.equal(isDeviceBodyToggleDisabled({ hasDevice: true, zoomPercent: 50 }), true);
  assert.equal(isDeviceBodyToggleDisabled({ hasDevice: false, zoomPercent: 100 }), true);
});
