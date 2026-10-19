import type { RenderPixels } from "./client";

export function layoutHeight(pixels: RenderPixels): number {
  const lines = pixels.layout?.lines;
  if (Array.isArray(lines)) return lines.reduce((sum, line) => sum + (line.height_px || 0), 0);
  return 0;
}
