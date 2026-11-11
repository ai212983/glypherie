// @scena/ruler host: React owns the host div, the library owns its canvas
// child. Structural size/theme/type changes recreate the instance; every
// render repaints scroll/zoom/unit synchronously through draw(). No library
// observers (useResizeObserver stays off); the viewport owns resize.
import * as React from "react";
import Ruler from "@scena/ruler";
import { cleanupRulerHost } from "./ruler-cleanup.js";

export interface PixelRulerOptions {
  type: "horizontal" | "vertical";
  width: number;
  height: number;
  zoom: number;
  scrollPos: number;
  unit: number;
  backgroundColor: string;
  lineColor: string;
  textColor: string;
  font: string;
  // Cross-axis label inset: with direction "end" the text baseline sits at
  // barSize - 17, outside a 22px strip, so each axis shifts its labels back
  // inside without moving the tick origin. Tick coordinates are untouched.
  textOffset?: readonly [number, number];
}

export function formatPixelValue(value: number): string {
  return `${Math.round(value)}`;
}

export function PixelRuler(options: PixelRulerOptions): React.JSX.Element {
  const hostRef = React.useRef<HTMLDivElement | null>(null);
  const rulerRef = React.useRef<Ruler | null>(null);

  React.useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    const ruler = new Ruler(host, {
      type: options.type,
      width: options.width,
      height: options.height,
      zoom: options.zoom,
      scrollPos: options.scrollPos,
      unit: options.unit,
      segment: 5,
      backgroundColor: options.backgroundColor,
      lineColor: options.lineColor,
      textColor: options.textColor,
      font: options.font,
      textFormat: formatPixelValue,
      negativeRuler: true,
      useResizeObserver: false,
      textOffset: options.textOffset ? [...options.textOffset] : [0, 0],
    });
    rulerRef.current = ruler;
    ruler.draw({ scrollPos: options.scrollPos, zoom: options.zoom, unit: options.unit });
    return () => {
      rulerRef.current = null;
      cleanupRulerHost(host, () => ruler.destroy());
    };
    // Hot values (zoom/scrollPos/unit) are intentionally excluded: the layout
    // effect below repaints them every render without recreating the instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    options.type,
    options.width,
    options.height,
    options.backgroundColor,
    options.lineColor,
    options.textColor,
    options.font,
    options.textOffset,
  ]);

  React.useLayoutEffect(() => {
    rulerRef.current?.draw({ scrollPos: options.scrollPos, zoom: options.zoom, unit: options.unit });
  });

  return (
    <div
      ref={hostRef}
      data-pixel-ruler={options.type}
      aria-hidden="true"
      style={{ width: options.width, height: options.height, overflow: "hidden", flexShrink: 0 }}
    />
  );
}
