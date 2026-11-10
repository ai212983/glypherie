// Scene-to-device resolution for the unified Screen page. A scene names a
// catalog device by opaque id (the domain stores the hint), but the screen
// is only that device when the stored geometry matches its rotation. An
// explicit custom choice (null hint) always stays a custom screen with the
// scene's own dimensions, even when those dimensions match a catalog device:
// the user picked custom, so mapping it back would make custom impossible.
// Anything else — an unknown id or a hint whose geometry the catalog no
// longer carries — also stays custom, never silently resized or discarded.
// The device list rides in as a parameter so this stays a pure,
// unit-testable module; call sites pass the shipped catalog.
import type { DeviceDefinition } from "../../devices/catalog.js";

export interface ResolvedScreen {
  device: DeviceDefinition | null;
  width: number;
  height: number;
}

// Resolution order: an exact hint plus matching oriented geometry wins; a hint with
// mismatched geometry (a renamed catalog, a resized scene) falls back to a
// custom screen instead of adopting a lookalike device. The store keeps the
// hint untouched; mapping is display-only until the user picks.
export function resolveSceneScreen(
  scene: { width: number; height: number; deviceId: string | null; rotation?: number },
  devices: readonly DeviceDefinition[],
): ResolvedScreen {
  if (scene.deviceId !== null) {
    const device = devices.find((candidate) => candidate.id === scene.deviceId) ?? null;
    const sideways = scene.rotation === 90 || scene.rotation === 270;
    if (
      device &&
      (sideways ? device.heightPx : device.widthPx) === scene.width &&
      (sideways ? device.widthPx : device.heightPx) === scene.height
    ) {
      return { device, width: scene.width, height: scene.height };
    }
    return { device: null, width: scene.width, height: scene.height };
  }
  return { device: null, width: scene.width, height: scene.height };
}

// New compositions default to the catalog's first device and its geometry.
export function defaultNewSceneDevice(devices: readonly DeviceDefinition[]): DeviceDefinition | null {
  return devices[0] ?? null;
}
