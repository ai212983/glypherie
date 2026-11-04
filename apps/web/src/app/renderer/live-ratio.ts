// Live devicePixelRatio tracking for pixel-exact previews.
//
// The browser only fires a `resolution` media query change once per query, so
// watching `(resolution: <current>dppx)` goes stale after the first DPR
// transition: without re-arming, later display, zoom or OS-scaling changes
// never reach the listener. This module re-subscribes on every transition,
// mirroring the render canvas subscription. Pure except for the thin React
// wrapper at the bottom; units stay explicit numbers.
import * as React from "react";

// Sanitize a raw devicePixelRatio reading: non-finite and non-positive values
// never reach layout math.
export function liveRatioOf(value: unknown): number {
  const ratio = Number(value);
  return Number.isFinite(ratio) && ratio > 0 ? ratio : 1;
}

export interface RatioMediaQuery {
  addEventListener(type: "change", listener: () => void): void;
  removeEventListener(type: "change", listener: () => void): void;
}

export interface LiveRatioWatcher {
  // Current raw devicePixelRatio; read fresh on every transition.
  current: () => number;
  matchMedia: (query: string) => RatioMediaQuery;
  onChange: (ratio: number) => void;
}

// Subscribe to successive DPR transitions without resize. Each transition
// re-arms the resolution query for the new ratio and drops the stale one, so
// repeated or fractional changes (1 -> 2 -> 1.5 ...) all propagate exactly
// once; firing a stale query after re-arming is a no-op. Returns cleanup.
export function watchLiveRatio(watcher: LiveRatioWatcher): () => void {
  let ratio: number | null = null;
  let query: RatioMediaQuery | null = null;
  const watch = (): void => {
    const next = liveRatioOf(watcher.current());
    if (next === ratio) return;
    query?.removeEventListener("change", watch);
    ratio = next;
    query = watcher.matchMedia(`(resolution: ${next}dppx)`);
    query.addEventListener("change", watch);
    watcher.onChange(next);
  };
  watch();
  return () => {
    query?.removeEventListener("change", watch);
  };
}

// Track the physical pixel grid so Pixel 1:1 stays exact across display,
// browser-zoom and OS-scaling changes.
export function useLiveRatio(): number {
  const [ratio, setRatio] = React.useState(() => liveRatioOf(window.devicePixelRatio));
  React.useEffect(() => {
    const stop = watchLiveRatio({
      current: () => window.devicePixelRatio,
      matchMedia: (query) => window.matchMedia(query),
      onChange: setRatio,
    });
    const onResize = (): void => setRatio(liveRatioOf(window.devicePixelRatio));
    window.addEventListener("resize", onResize);
    return () => {
      stop();
      window.removeEventListener("resize", onResize);
    };
  }, []);
  return ratio;
}
