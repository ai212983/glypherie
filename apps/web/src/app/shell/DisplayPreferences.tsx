import * as React from "react";
import {
  GLOBAL_ZOOM_KEY, readGlobalZoom, validPreviewZoom, writeGlobalZoom,
  GLOBAL_CANVAS_KEY, readCanvasAppearance, writeCanvasAppearance, type CanvasAppearance,
  GLOBAL_DEVICE_KEY, migrateDeviceViewingStorage, readDeviceViewing, writeDeviceViewing, type DeviceViewing,
} from "./display-preferences";

interface DisplayPreferencesValue {
  zoom: number;
  onZoom: (zoom: number) => void;
  canvas: CanvasAppearance;
  onCanvas: (patch: Partial<CanvasAppearance>) => void;
  device: DeviceViewing;
  onDevice: (patch: Partial<DeviceViewing>) => void;
}
const DisplayPreferences = React.createContext<DisplayPreferencesValue | null>(null);

export function DisplayPreferencesProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  // Clean obsolete stored fields once where the app opens; readDeviceViewing
  // also migrates on read, so tabs opened before this runs still converge.
  React.useEffect(() => { migrateDeviceViewingStorage(); }, []);
  const [zoom, setZoom] = React.useState(readGlobalZoom);
  const [canvas, setCanvas] = React.useState(readCanvasAppearance);
  const [device, setDevice] = React.useState(readDeviceViewing);
  const onDevice = React.useCallback((patch: Partial<DeviceViewing>) => {
    setDevice((current) => {
      const next = { ...current, ...patch };
      writeDeviceViewing(next);
      return next;
    });
  }, []);
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
      if (event.key === GLOBAL_DEVICE_KEY || event.key === null) {
        const next = readDeviceViewing();
        setDevice((current) => current.device === next.device && current.scale === next.scale ? current : next);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  return <DisplayPreferences.Provider value={{ zoom, onZoom, canvas, onCanvas, device, onDevice }}>{children}</DisplayPreferences.Provider>;
}

export function useDisplayPreferences(): DisplayPreferencesValue {
  const value = React.useContext(DisplayPreferences);
  if (!value) throw new Error("Display preferences provider is missing.");
  return value;
}
