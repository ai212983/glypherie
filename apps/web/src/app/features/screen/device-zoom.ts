// Device-header view preferences: presentation zoom presets and the
// effective device-body visibility rule. Zoom multiplies the presentation
// scale only; native scene dimensions, labels and export are untouched.
export const DEVICE_ZOOM_PRESETS = [25, 50, 75, 100, 125, 150, 200, 300, 400] as const;

export const DEVICE_ZOOM_DEFAULT = 100;

export type DeviceZoomPercent = (typeof DEVICE_ZOOM_PRESETS)[number];

export function isDeviceZoomPercent(value: number): value is DeviceZoomPercent {
  return (DEVICE_ZOOM_PRESETS as readonly number[]).includes(value);
}

// The shell (and its reserved bezel footprint) shows only for a catalog
// device at 100% with the body preference on. Any other zoom shows the
// scaled canvas alone; the caller's stored preference is kept so returning
// to 100% restores the chosen visibility.
export function resolveDeviceBodyVisible({
  hasDevice,
  bodyPreference,
  zoomPercent,
}: {
  hasDevice: boolean;
  bodyPreference: boolean;
  zoomPercent: number;
}): boolean {
  return hasDevice && bodyPreference && zoomPercent === DEVICE_ZOOM_DEFAULT;
}

export function isDeviceBodyToggleDisabled({
  hasDevice,
  zoomPercent,
}: {
  hasDevice: boolean;
  zoomPercent: number;
}): boolean {
  return !hasDevice || zoomPercent !== DEVICE_ZOOM_DEFAULT;
}
