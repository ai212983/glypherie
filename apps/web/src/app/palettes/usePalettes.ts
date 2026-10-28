import * as React from "react";
import { useLiveQuery } from "dexie-react-hooks";
import { listPalettes } from "./repository.ts";
import { MONOCHROME, type PalettePreset } from "./model.ts";

export function usePalettes(): { presets: PalettePreset[]; ready: boolean; error: string; retry: () => void } {
  const [attempt, setAttempt] = React.useState(0);
  const result = useLiveQuery(async () => {
    try { return { presets: await listPalettes(), error: "" }; }
    catch { return { presets: [MONOCHROME], error: "Couldn’t load palettes. Try again." }; }
  }, [attempt]);
  return { presets: result?.presets ?? [MONOCHROME], ready: !!result && !result.error,
    error: result?.error ?? "", retry: () => setAttempt((value) => value + 1) };
}
