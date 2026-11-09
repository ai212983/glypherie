import * as React from "react";
import { getDomainVersion, subscribeDomain } from "../domain/events.ts";
import { listPalettes } from "./repository.ts";
import { MONOCHROME, type PalettePreset } from "./model.ts";

export function usePalettes(): { presets: PalettePreset[]; ready: boolean; error: string; retry: () => void } {
  const [attempt, setAttempt] = React.useState(0);
  const version = React.useSyncExternalStore(subscribeDomain, getDomainVersion);
  const [state, setState] = React.useState<{ presets: PalettePreset[]; error: string; loaded: boolean }>({
    presets: [MONOCHROME],
    error: "",
    loaded: false,
  });
  React.useEffect(() => {
    let live = true;
    void listPalettes().then(
      (presets) => {
        if (live) setState({ presets, error: "", loaded: true });
      },
      () => {
        if (live) setState({ presets: [MONOCHROME], error: "Couldn’t load palettes. Try again.", loaded: true });
      },
    );
    return () => {
      live = false;
    };
  }, [attempt, version]);
  return {
    presets: state.presets,
    ready: state.loaded && state.error === "",
    error: state.error,
    retry: () => setAttempt((value) => value + 1),
  };
}
