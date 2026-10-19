import * as React from "react";
import type { RendererService } from "./renderer-types.js";

// This module stays free of the worker bundle so non-WASM surfaces
// (Storybook, unit tests) never pull it in.
export type { RendererService } from "./renderer-types.js";

export interface RendererContextValue {
  service: RendererService | null;
  // Unique per created worker. Consumers key caches and request identity on
  // it so a recreated worker never serves stale readiness or results.
  session: number;
  available: boolean | null;
  availabilityError: string;
}

const RendererContext = React.createContext<RendererContextValue | null>(null);

export function useRenderer(): RendererContextValue {
  const value = React.useContext(RendererContext);
  if (!value) throw new Error("useRenderer must be used inside <RendererProvider>.");
  return value;
}

let sessionCounter = 0;

interface RendererProviderProps {
  children: React.ReactNode;
  createService: () => RendererService;
}

// Owns the single active worker. Creation and termination happen inside this
// effect (never during render), so StrictMode setup-cleanup-setup cannot leak
// a worker or leave a terminated one active. A changed factory is deliberate
// replacement: the active worker is terminated and a new session starts, so
// exactly one worker is ever live. A synchronously throwing factory marks the
// renderer unavailable instead of crashing the tree.
export function RendererProvider({ children, createService }: RendererProviderProps): React.JSX.Element {
  const [service, setService] = React.useState<RendererService | null>(null);
  const [session, setSession] = React.useState(0);
  const [available, setAvailable] = React.useState<boolean | null>(null);
  const [availabilityError, setAvailabilityError] = React.useState("");

  React.useEffect(() => {
    let next: RendererService | null = null;
    try {
      next = createService();
    } catch (error) {
      setService(null);
      setAvailable(false);
      setAvailabilityError(error instanceof Error ? error.message : String(error ?? ""));
      return;
    }
    const active = next;
    sessionCounter += 1;
    const nextSession = sessionCounter;
    let live = true;
    setService(active);
    setSession(nextSession);
    setAvailable(null);
    setAvailabilityError("");
    active.ping().then(
      () => { if (live) setAvailable(true); },
      (error: unknown) => {
        if (!live) return;
        setAvailable(false);
        setAvailabilityError(error instanceof Error ? error.message : String(error ?? ""));
      },
    );
    return () => {
      live = false;
      active.terminate();
      setService((current) => (current === active ? null : current));
    };
  }, [createService]);

  const value = React.useMemo(
    () => ({ service, session, available, availabilityError }),
    [service, session, available, availabilityError],
  );
  return <RendererContext.Provider value={value}>{children}</RendererContext.Provider>;
}
