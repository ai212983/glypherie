import * as React from "react";
import { TooltipHint } from "../../components/TooltipHint";
import { useRegisterSW } from "virtual:pwa-register/react";
import { RefreshCw } from "lucide-react";
import { Button } from "../../components/ui/button";

// https://vite-pwa-org.netlify.app/guide/prompt-for-update
type Activity = "idle" | "checking" | "downloading" | "updating" | "current" | "error";

export function PwaStatus({ version, online, children }: { version: string; online: boolean; children: React.ReactNode }): React.JSX.Element {
  const [registration, setRegistration] = React.useState<ServiceWorkerRegistration>();
  const [activity, setActivity] = React.useState<Activity>("idle");
  const applying = React.useRef(false);
  const busy = React.useRef(false);
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    immediate: false,
    onRegisteredSW(_url, next) { setRegistration(next); },
    onRegisterError(error: unknown) {
      setActivity("error");
      console.warn("Service worker registration failed; the app still works online.", error);
    },
    onNeedReload() {
      if (applying.current) window.location.reload();
      else setNeedRefresh(true);
    },
  });

  const apply = React.useCallback(async (): Promise<void> => {
    if (applying.current) return;
    applying.current = true;
    setActivity("updating");
    try {
      if (registration?.waiting) await updateServiceWorker(true);
      else window.location.reload();
    } catch {
      applying.current = false;
      setActivity("error");
    }
  }, [registration, updateServiceWorker]);

  React.useEffect(() => {
    const controlled = (): void => {
      if (applying.current) {
        applying.current = false;
        window.location.reload();
      }
    };
    navigator.serviceWorker?.addEventListener("controllerchange", controlled);
    return () => {
      navigator.serviceWorker?.removeEventListener("controllerchange", controlled);
    };
  }, []);

  React.useEffect(() => {
    if (!registration) return;
    let worker: ServiceWorker | null = null;
    const stateChanged = (): void => {
      if (worker?.state === "installed") {
        if (registration.active && registration.waiting) setNeedRefresh(true);
        setActivity("idle");
      } else if (worker?.state === "redundant") {
        setActivity("error");
      }
    };
    const found = (): void => {
      worker?.removeEventListener("statechange", stateChanged);
      worker = registration.installing;
      if (worker) {
        setActivity("downloading");
        worker.addEventListener("statechange", stateChanged);
        stateChanged();
      }
    };
    if (registration.active && registration.waiting) setNeedRefresh(true);
    registration.addEventListener("updatefound", found);
    found();
    return () => {
      registration.removeEventListener("updatefound", found);
      worker?.removeEventListener("statechange", stateChanged);
    };
  }, [registration, setNeedRefresh]);

  React.useEffect(() => {
    if (activity !== "current") return;
    const timeout = window.setTimeout(() => setActivity("idle"), 3000);
    return () => window.clearTimeout(timeout);
  }, [activity]);

  const check = async (): Promise<void> => {
    if (!registration || busy.current) return;
    busy.current = true;
    setActivity("checking");
    try {
      await registration.update();
      if (registration.active && registration.waiting) {
        setNeedRefresh(true);
        setActivity("idle");
      } else if (registration.installing) setActivity("downloading");
      else setActivity("current");
    } catch {
      setActivity("error");
    }
    finally { busy.current = false; }
  };

  if (!("serviceWorker" in navigator)) {
    return (
      <div className="site-footer__updates" data-update-state="unsupported">
        <span data-app-version>{version}</span>
        {children}
      </div>
    );
  }

  const pending = activity === "checking" || activity === "downloading" || activity === "updating";
  const message = activity === "updating" ? ""
    : activity === "error" ? "Couldn’t check for updates."
    : needRefresh ? ""
    : !online ? ""
    : activity === "checking" ? "Checking for updates…"
    : activity === "downloading" ? "Downloading update…"
    : activity === "current" ? "Up to date"
    : "";
  return (
    <div className="site-footer__updates" data-update-state={needRefresh ? "ready" : activity}>
      <TooltipHint content={needRefresh ? "Apply downloaded update" : "Check for updates"}>
        <Button type="button" size="xs" variant="ghost"
          className="site-footer__version-button"
          data-app-version
          aria-label={needRefresh ? undefined : `Version ${version}: check for updates`}
          disabled={needRefresh ? activity === "updating" : pending || !online || (!registration && activity !== "error")}
          onClick={() => {
            if (needRefresh) void apply();
            else if (!registration) window.location.reload();
            else void check();
          }}>
          <RefreshCw aria-hidden="true" className={pending ? "motion-safe:animate-spin" : undefined} />
          {needRefresh ? activity === "updating" ? "Updating…" : "Update" : version}
        </Button>
      </TooltipHint>
      {children}
      <span role="status" data-update-success={activity === "current" && message ? true : undefined}>{message}</span>
    </div>
  );
}
