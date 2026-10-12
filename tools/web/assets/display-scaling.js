// Pure display-scaling math for the optional pixel-accurate preview mode.
//
// Source foundation: CSS `devicePixelRatio` (device pixels per CSS pixel,
// including browser zoom and OS display scaling) combined with integer
// nearest-pixel magnification: each rendered source pixel maps to exactly
// M x M physical screen pixels. This is an explicit user display policy with
// size adjustment, not a font-fitting hypothesis: the font request (size,
// axes, hinting) is unchanged; only the request bounds and the canvas
// backing/CSS sizes adapt. No DOM access here; units are explicit in names.
export const NATIVE_WIDTH_MIN = 1;
export const NATIVE_WIDTH_MAX = 4096;
// Browser canvas backing limit shared with the normal paint path.
export const BACKING_HEIGHT_MAX = 16384;
// Renderer texture bound shared with the normal native-cap computation.
export const RENDER_TEXELS_MAX = 16777216;

// Integer screen pixels per source pixel: nearest integer to the requested
// zoom measured in physical pixels. Always >= 1.
export function magnification(requestedZoom, devicePixelRatio) {
  const zoom = Number(requestedZoom);
  const ratio = Number(devicePixelRatio);
  if (!Number.isFinite(zoom) || zoom <= 0) return 1;
  if (!Number.isFinite(ratio) || ratio <= 0) return Math.max(1, Math.round(zoom));
  return Math.max(1, Math.round(zoom * ratio));
}

// Actual on-screen magnification in CSS px per source px. Fractional by
// design: the transformed canvas extent is physical backing / ratio.
export function effectiveZoom(mag, devicePixelRatio) {
  const ratio = Number(devicePixelRatio);
  if (!Number.isInteger(mag) || mag < 1) return 1;
  if (!Number.isFinite(ratio) || ratio <= 0) return mag;
  return mag / ratio;
}

// Native (source-pixel) request width for the available CSS layout width.
// floor() avoids a partial trailing block at the viewport's right edge.
export function nativeWidthFor(cssWidth, mag, devicePixelRatio) {
  const css = Number(cssWidth);
  const ratio = Number(devicePixelRatio);
  if (!Number.isFinite(css) || css <= 0) return NATIVE_WIDTH_MIN;
  if (!Number.isInteger(mag) || mag < 1) return NATIVE_WIDTH_MIN;
  if (!Number.isFinite(ratio) || ratio <= 0) return NATIVE_WIDTH_MIN;
  return Math.min(NATIVE_WIDTH_MAX, Math.max(NATIVE_WIDTH_MIN, Math.floor((css * ratio) / mag)));
}

// Native request-height cap for pixel-accurate mode: the renderer texel
// bound at this width, the published 4096 px side limit, and the browser
// backing limit (shown rows * M must fit BACKING_HEIGHT_MAX device px).
// Callers show the existing overflow message when layout exceeds the cap
// instead of silently clipping.
export function nativeHeightCap(nativeWidth, mag) {
  const width = Number.isFinite(Number(nativeWidth)) ? Math.max(1, Number(nativeWidth)) : 1;
  const m = Number.isInteger(mag) && mag >= 1 ? mag : 1;
  return Math.min(
    NATIVE_WIDTH_MAX,
    Math.max(1, Math.floor(RENDER_TEXELS_MAX / width)),
    Math.max(1, Math.floor(BACKING_HEIGHT_MAX / m)),
  );
}

// Device-pixel backing extent for a native width and shown logical height.
export function backingSize(nativeWidth, shownHeight, mag) {
  return { width: nativeWidth * mag, height: shownHeight * mag };
}

// CSS layout extent for a device-pixel backing extent.
export function cssSize(backingExtent, devicePixelRatio) {
  return backingExtent / devicePixelRatio;
}

// Fractional part of a device-pixel coordinate in [0, 1): how far the
// coordinate sits past the last whole physical pixel.
export function devicePhase(cssCoordinate, devicePixelRatio) {
  const scaled = Number(cssCoordinate) * Number(devicePixelRatio);
  if (!Number.isFinite(scaled)) return 0;
  return scaled - Math.floor(scaled);
}

// CSS translation that snaps a painted origin onto the physical pixel grid.
// Ceil-snap toward the viewport interior: returns {dx, dy} in CSS px, each
// in [0, 1/D). The canvas shifts right/down by less than one device pixel,
// so the first painted row/column is never pushed outside the viewport
// origin (a general clip bound: no glyph- or font-specific phase tuning).
// The caller reserves a one-device-pixel end gutter (right/bottom) for
// this shift, plus the separate CSS-layout alignment allowance. Pure: callers measure the *untransformed* layout origin
// once and set the transform from it without re-rendering (no feedback loop).
export function snapTranslation(rectLeft, rectTop, devicePixelRatio) {
  const ratio = Number(devicePixelRatio);
  if (!Number.isFinite(ratio) || ratio <= 0) return { dx: 0, dy: 0 };
  const snap = (css) => {
    const phase = devicePhase(css, ratio);
    if (phase === 0) return 0;
    return (1 - phase) / ratio;
  };
  return { dx: snap(rectLeft), dy: snap(rectTop) };
}

// Short human-readable effective zoom, e.g. 1.78x. Whole values stay whole.
export function formatEffectiveZoom(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "1×";
  const rounded = Math.round(number * 100) / 100;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(2)}×`;
}
