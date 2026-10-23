import * as React from "react";
import { TooltipHint } from "../../components/TooltipHint";
import { Button } from "../../components/ui/button";
import { PwaStatus } from "./PwaStatus";
import { useHmrStatus, type HmrStatus } from "./useHmrStatus";
import "./SiteFooter.css";

const HMR_STATE: Record<HmrStatus, { dot: string; label: string; hint: string; text: string }> = {
  connecting: {
    dot: "bg-amber-500",
    label: "Live updates connecting",
    hint: "Connecting to the dev server for live updates.",
    text: "Connecting…",
  },
  connected: {
    dot: "bg-green-500",
    label: "Live updates connected",
    hint: "Live updates connected. Vite applies edits automatically.",
    text: "Connected",
  },
  disconnected: {
    dot: "bg-red-500",
    label: "Live updates disconnected",
    hint: "Dev server connection lost. Vite reconnects automatically.",
    text: "Disconnected",
  },
};

function DevHmrStatus(): React.JSX.Element {
  const status = useHmrStatus();
  const state = HMR_STATE[status];
  return (
    <span className="site-footer__development">
      <TooltipHint content={state.hint}>
        <span role="img" aria-label={state.label}
          data-hmr-status={status}
          className={`site-footer__connection ${state.dot}`} />
      </TooltipHint>
      <span>Dev server · Live updates · {state.text}</span>
    </span>
  );
}

function BuildDetails({ info }: { info: typeof __APP_BUILD__ }): React.JSX.Element {
  const [copyStatus, setCopyStatus] = React.useState("");
  const detailsRef = React.useRef<HTMLDetailsElement>(null);
  React.useEffect(() => {
    const dismissOutside = (event: PointerEvent): void => {
      const popup = detailsRef.current;
      if (popup?.open && event.target instanceof Node && !popup.contains(event.target)) {
        popup.open = false;
      }
    };
    document.addEventListener("pointerdown", dismissOutside, true);
    return () => document.removeEventListener("pointerdown", dismissOutside, true);
  }, []);
  const fullInfo = [
    `Glypherie ${info.version}`, `Build ${info.build} UTC`,
    `${info.devServer ? "Started" : "Built"}: ${info.builtAt}`,
    `Commit: ${info.commit ?? "unavailable"}`,
    `Local changes: ${info.localFingerprint ?? "none"}`,
    `Renderer SHA-256: ${info.renderer ?? "unavailable"}`,
  ].join("\n");
  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(fullInfo);
      setCopyStatus("Copied.");
    } catch { setCopyStatus("Could not copy build info."); }
  };
  return (
    <details ref={detailsRef} className="site-footer__details" onKeyDown={(event) => {
      if (event.key === "Escape") {
        event.currentTarget.open = false;
        event.currentTarget.querySelector("summary")?.focus();
      }
    }}>
      <TooltipHint content={`${info.devServer ? "Started" : "Built"} ${info.builtAt} (UTC)`}>
        <summary aria-label="Build details">
          <span>Build <time dateTime={info.builtAt}>{info.build}</time></span>
        </summary>
      </TooltipHint>
      <div className="site-footer__info">
        <dl>
          <dt>Version</dt><dd>{info.version}</dd>
          <dt>{info.devServer ? "Started" : "Built"} (UTC)</dt><dd>{info.builtAt}</dd>
          <dt>Commit</dt><dd>{info.commit?.slice(0, 12) ?? "Unavailable"}</dd>
          <dt>Local changes</dt><dd>{info.localFingerprint ?? "None"}</dd>
          <dt>Renderer</dt><dd>{info.renderer?.slice(0, 12) ?? "Unavailable"}</dd>
        </dl>
        <Button type="button" size="xs" variant="outline" onClick={() => { void copy(); }}>Copy build info</Button>
        <span role="status">{copyStatus}</span>
      </div>
    </details>
  );
}

export function SiteFooter(): React.JSX.Element {
  const [online, setOnline] = React.useState(navigator.onLine);
  React.useEffect(() => {
    const changed = (): void => setOnline(navigator.onLine);
    window.addEventListener("online", changed);
    window.addEventListener("offline", changed);
    return () => {
      window.removeEventListener("online", changed);
      window.removeEventListener("offline", changed);
    };
  }, []);
  const info = __APP_BUILD__;
  return (
    <footer className="site-footer" data-site-footer>
      <div className="site-footer__identity">
        {import.meta.env.PROD && !online && (
          <TooltipHint content="Offline. Your library and previews still work on this device.">
            <span role="img" aria-label="Offline"
              data-connection="offline"
              className="site-footer__connection bg-red-500" />
          </TooltipHint>
        )}
        {import.meta.env.PROD ? <PwaStatus version={info.version} online={online}><BuildDetails info={info} /></PwaStatus> : (
          <><span data-app-version>{info.version}</span><BuildDetails info={info} /></>
        )}
      </div>
      {import.meta.env.DEV && <DevHmrStatus />}
    </footer>
  );
}
