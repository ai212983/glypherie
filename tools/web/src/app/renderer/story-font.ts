// Shared Storybook font hook: fetches the selected bundled font once per
// renderer session and loads it into the worker outside the render path. No
// library or storage writes: bytes go straight from the bundled asset URL to
// the worker cache.
import * as React from "react";
import type { RendererService } from "./renderer-types.js";
import { fetchFontIntoService } from "./story-font-loader.js";
import { BUNDLED_FONTS, relativeFontUrl } from "../fonts/bundled-fonts.js";

export function useStoryFont(
  service: RendererService | null,
  session: number,
  available: boolean | null,
  enabled: boolean,
  fontName: string,
): { fontId: string; ready: boolean; loadError: string } {
  const descriptor = BUNDLED_FONTS.find((entry) => entry.name === fontName) ?? BUNDLED_FONTS[0];
  const active = descriptor ?? BUNDLED_FONTS[0];
  const fontId = `storybook/${active?.fileName ?? "Roboto.ttf"}`;
  const [loadedKey, setLoadedKey] = React.useState("");
  const [loadError, setLoadError] = React.useState("");
  React.useEffect(() => {
    if (!enabled || !service || available !== true || !active) return;
    const cleanup = new AbortController();
    const key = `${session}:${fontId}`;
    setLoadError("");
    fetchFontIntoService(service, fontId, relativeFontUrl(active.url), cleanup.signal).then(
      () => {
        if (!cleanup.signal.aborted) setLoadedKey(key);
      },
      (error: unknown) => {
        if (!cleanup.signal.aborted) {
          setLoadError(error instanceof Error ? error.message : String(error ?? ""));
        }
      },
    );
    return () => { cleanup.abort(); };
  }, [enabled, service, session, available, active, fontId]);
  return { fontId, ready: !enabled || loadedKey === `${session}:${fontId}`, loadError };
}
