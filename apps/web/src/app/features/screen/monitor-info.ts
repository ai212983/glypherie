// Detectable monitor metrics: pure snapshot math for the Screen page
// disclosure. The browser exposes CSS screen dimensions and device pixel
// ratio; physical monitor size and true PPI stay unknowable without native
// access, so this module never produces them.
import { sanitizeDevicePixelRatio } from "../../renderer/display-scaling.ts";

export interface MonitorSnapshot {
  screenWidth: unknown;
  screenHeight: unknown;
  devicePixelRatio: unknown;
}

export interface MonitorSize {
  width: number;
  height: number;
}

export interface MonitorReading {
  // window.screen area in CSS px; null when the browser withholds it.
  screen: MonitorSize | null;
  // Live device pixel ratio, sanitized to a positive finite number.
  dpr: number;
}

function sizeOf(width: unknown, height: unknown): MonitorSize | null {
  const w = Number(width);
  const h = Number(height);
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
  return { width: Math.round(w), height: Math.round(h) };
}

export function resolveMonitorReading(snapshot: MonitorSnapshot): MonitorReading {
  return {
    screen: sizeOf(snapshot.screenWidth, snapshot.screenHeight),
    dpr: sanitizeDevicePixelRatio(snapshot.devicePixelRatio),
  };
}
