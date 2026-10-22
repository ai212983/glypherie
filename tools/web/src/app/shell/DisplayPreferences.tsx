import * as React from "react";
import {
  GLOBAL_ZOOM_KEY, readGlobalZoom, validPreviewZoom, writeGlobalZoom,
  GLOBAL_CANVAS_KEY, readCanvasAppearance, writeCanvasAppearance, type CanvasAppearance,
} from "./display-preferences";

interface DisplayPreferencesValue {
  zoom: number;
  onZoom: (zoom: number) => void;
  canvas: CanvasAppearance;
  onCanvas: (patch: Partial<CanvasAppearance>) => void;
}
const DisplayPreferences = React.createContext<DisplayPreferencesValue | null>(null);

export function DisplayPreferencesProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [zoom, setZoom] = React.useState(readGlobalZoom);
  const [canvas, setCanvas] = React.useState(readCanvasAppearance);
  const onCanvas = React.useCallback((patch: Partial<CanvasAppearance>) => {
    const next = { ...canvas, ...patch };
    setCanvas(next);
    writeCanvasAppearance(next);
  }, [canvas]);
  React.useEffect(() => { writeCanvasAppearance(canvas); }, [canvas]);
  const onZoom = React.useCallback((next: number) => {
    if (!validPreviewZoom(next)) return;
    setZoom(next);
    writeGlobalZoom(next);
  }, []);
  React.useEffect(() => { writeGlobalZoom(zoom); }, [zoom]);
  React.useEffect(() => {
    const onStorage = (event: StorageEvent): void => {
      if (event.key === GLOBAL_ZOOM_KEY || event.key === null) setZoom(readGlobalZoom());
      if (event.key === GLOBAL_CANVAS_KEY || event.key === null) {
        const next = readCanvasAppearance();
        setCanvas((current) => current.palette === next.palette && current.inverse === next.inverse ? current : next);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  return <DisplayPreferences.Provider value={{ zoom, onZoom, canvas, onCanvas }}>{children}</DisplayPreferences.Provider>;
}

export function useDisplayPreferences(): DisplayPreferencesValue {
  const value = React.useContext(DisplayPreferences);
  if (!value) throw new Error("Display preferences provider is missing.");
  return value;
}
