import type { RGBA } from "../../renderer/renderer-types.js";

function decodeGray(value: number): number {
  const x = Math.min(255, Math.max(0, value)) / 255;
  return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
}

// Map browser text coverage to the nearest palette entry in linear light:
// decode the sRGB levels, blend paper toward ink by alpha, and write the
// nearest entry verbatim with opaque alpha. Nearest minimizes squared error,
// so region boundaries are midpoints; the browser raster mask is preserved
// and its grays are never blended with paper a second time.
// https://www.w3.org/TR/css-color-4/#color-conversion-code
// See docs/references/papers/2006-gallager-quantization/paper.md, section 3.2.1.
export function paletteCoverage(rgba: Uint8ClampedArray, levels: readonly number[]): Uint8ClampedArray<ArrayBuffer> {
  const pixels = new Uint8ClampedArray(rgba.length);
  const decoded = levels.map(decodeGray);
  const paper = decoded[0] ?? 0;
  const ink = decoded[decoded.length - 1] ?? paper;
  // Endpoints are exact; interior ties keep the first index.
  const nearest = new Uint8Array(256);
  nearest[0] = 0;
  nearest[255] = Math.max(0, levels.length - 1);
  for (let alpha = 1; alpha < 255; alpha += 1) {
    const target = (1 - alpha / 255) * paper + (alpha / 255) * ink;
    let best = 0;
    let bestDistance = Math.abs((decoded[0] ?? 0) - target);
    for (let index = 1; index < decoded.length; index += 1) {
      const distance = Math.abs((decoded[index] ?? 0) - target);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = index;
      }
    }
    nearest[alpha] = best;
  }
  for (let offset = 0; offset < pixels.length; offset += 4) {
    const gray = levels[nearest[rgba[offset + 3] ?? 0] ?? 0] ?? 0;
    pixels[offset] = gray;
    pixels[offset + 1] = gray;
    pixels[offset + 2] = gray;
    pixels[offset + 3] = 255;
  }
  return pixels;
}

// Display-only colorization for preset specimens: the quantized gray byte g
// selects a position between the display paper (g=255) and ink (g=0),
// generalizing the library's 8-step sRGB ramp (canvas-palettes buildGrayRamp:
// per-channel ink + (paper - ink) * share) to arbitrary gray codes.
// Quantization always runs first; this never reblends coverage, and the
// neutral 255/0 pair maps every byte to itself.
export function tintCoverage(pixels: Uint8ClampedArray, paper: RGBA, ink: RGBA): Uint8ClampedArray<ArrayBuffer> {
  const tinted = new Uint8ClampedArray(pixels.length);
  for (let offset = 0; offset < pixels.length; offset += 4) {
    const share = (pixels[offset] ?? 0) / 255;
    tinted[offset] = Math.round((ink[0] ?? 0) + ((paper[0] ?? 0) - (ink[0] ?? 0)) * share);
    tinted[offset + 1] = Math.round((ink[1] ?? 0) + ((paper[1] ?? 0) - (ink[1] ?? 0)) * share);
    tinted[offset + 2] = Math.round((ink[2] ?? 0) + ((paper[2] ?? 0) - (ink[2] ?? 0)) * share);
    tinted[offset + 3] = 255;
  }
  return tinted;
}
