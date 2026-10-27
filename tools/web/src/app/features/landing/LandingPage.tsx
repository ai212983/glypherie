import * as React from "react";
import { NavLink } from "../../../components/NavLink";
import { Button } from "../../../components/ui/button";
import { appBase } from "../../navigation/location";
import { SiteHeader } from "../../shell/SiteHeader";
import { RasterizerComparison } from "./RasterizerComparison";
import localStorageIcon from "./assets/local-storage.svg";
import heroArrow from "./assets/hero-arrow.svg";
import githubIcon from "./assets/github.svg";
import "./LandingPage.css";

const REPOSITORY = "ai212983/glypherie";
const SOURCE = `https://github.com/${REPOSITORY}`;
let starsRequest: Promise<number | null> | undefined;

function loadGitHubStars(): Promise<number | null> {
  starsRequest ??= fetch(`https://api.github.com/repos/${REPOSITORY}`, {
    headers: { Accept: "application/vnd.github+json" },
    credentials: "omit",
    referrerPolicy: "no-referrer",
    cache: "no-cache",
    signal: AbortSignal.timeout(5000),
  }).then(async (response) => {
    if (!response.ok) return null;
    const data: unknown = await response.json();
    const count = data && typeof data === "object" && "stargazers_count" in data ? data.stargazers_count : null;
    return typeof count === "number" && Number.isSafeInteger(count) && count >= 0 ? count : null;
  }).catch(() => null).finally(() => { starsRequest = undefined; });
  return starsRequest;
}

interface LandingPageProps {
  nav: React.ReactNode;
  fontsHref: string;
  onFonts: () => void;
}

export function LandingPage({ nav, fontsHref, onFonts }: LandingPageProps): React.JSX.Element {
  const [stars, setStars] = React.useState<number | null>(null);
  React.useEffect(() => {
    let active = true;
    const refresh = (): void => {
      if (document.visibilityState !== "visible") return;
      void loadGitHubStars().then((count) => { if (active && count !== null) setStars(count); });
    };
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      active = false;
      window.removeEventListener("focus", refresh);
      window.removeEventListener("online", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  const [clearingCache, setClearingCache] = React.useState(false);
  const [cacheMessage, setCacheMessage] = React.useState("");
  const [confirmingReset, setConfirmingReset] = React.useState(false);
  const resetTrigger = React.useRef<HTMLButtonElement>(null);
  const cancelReset = (): void => {
    setConfirmingReset(false);
    setCacheMessage("");
    requestAnimationFrame(() => resetTrigger.current?.focus());
  };
  const cacheBusy = React.useRef(false);
  const clearLocalCache = async (): Promise<void> => {
    if (cacheBusy.current) return;
    if (!navigator.onLine) {
      setCacheMessage("Connect to the internet before resetting Glypherie.");
      return;
    }
    cacheBusy.current = true;
    setClearingCache(true);
    setCacheMessage("");
    try {
      const scope = new URL(appBase, window.location.origin).href;
      const { fontDatabase } = await import("../../database");
      const blocked = (): void => setCacheMessage("Close other Glypherie tabs to finish deleting local data.");
      fontDatabase.on("blocked", blocked);
      try { await fontDatabase.delete(); }
      finally { fontDatabase.on("blocked").unsubscribe(blocked); }
      const registrations = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistrations() : [];
      const registration = registrations.find((entry) => entry.scope === scope);
      // Workbox names caches with the worker scope; leave other apps on this origin alone.
      // https://github.com/GoogleChrome/workbox/blob/v7/packages/workbox-core/src/_private/cacheNames.ts
      const names = "caches" in window
        ? (await caches.keys()).filter((name) => name.startsWith("workbox-") && name.endsWith(`-${scope}`)) : [];
      if (registration) await registration.unregister();
      await Promise.all(names.map((name) => caches.delete(name)));
      for (const storage of [localStorage, sessionStorage]) {
        const keys = Object.keys(storage).filter((key) => key.startsWith("font-preview."));
        for (const key of keys) storage.removeItem(key);
      }
      window.location.reload();
    } catch {
      setCacheMessage("Couldn’t reset all local data. Close other Glypherie tabs and try again.");
    } finally {
      cacheBusy.current = false;
      setClearingCache(false);
    }
  };
  return (
    <div className="landing">
      <SiteHeader title="Glypherie" titleAs="div" variant="brand" nav={nav} />
      <main id="main" className="landing__main" data-landing>
        <div className="landing__intro-row">
          <h1 id="landing-title">Bitmap fonts for low-resolution displays.</h1>
          <p className="landing__intro">Convert TTF and OTF fonts for monochrome and grayscale displays.</p>
          <div className="landing__actions">
            <Button asChild size="lg" className="landing__primary-action">
              <NavLink href={fontsHref} onNavigate={onFonts}>Open font library <img src={heroArrow} width="10.6667" height="10.6667" alt="" /></NavLink>
            </Button>
            <Button asChild size="sm" variant="outline" className="landing__source-action">
              <a href={SOURCE}><img className="landing__github-icon" src={githubIcon} width="16" height="16" alt="" />GitHub
                <span className="landing__github-stars" role="img" aria-label={stars === null ? "Star on GitHub" : `${stars.toLocaleString("en-US")} GitHub stars`}>
                  <span aria-hidden="true">★ {stars === null ? "Star" : new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(stars)}</span>
                </span>
              </a>
            </Button>
          </div>
        </div>

        <RasterizerComparison />

        <section className="landing__workflow" aria-labelledby="landing-start">
          <div className="landing__section-heading"><h2 id="landing-start">Import, configure, export</h2></div>
          <ol className="landing__steps">
            <li><span className="landing__step-number">01</span><h3>Import a font</h3><p>Choose a bundled font or upload your own.</p></li>
            <li><span className="landing__step-number">02</span><h3>Adjust</h3><p>Adjust size, style and spacing. Save your settings as a variant.</p></li>
            <li><span className="landing__step-number">03</span><h3>Export</h3><p>Export your font and test it on your display. For pixel editing, use <a href="https://play.date/caps/">Playdate Caps</a> or <a href="https://github.com/kreativekorp/bitsnpicas">Bits’N’Picas</a>.</p></li>
          </ol>
        </section>

        <section className="landing__details" aria-labelledby="storage-title" data-confirming-reset={confirmingReset}
          onKeyDown={(event) => {
            if (event.key === "Escape" && confirmingReset && !clearingCache) {
              event.preventDefault();
              cancelReset();
            }
          }}>
          <img className="landing__storage-icon" src={localStorageIcon} width="35.3333" height="41.8" alt="" />
          <div className="landing__storage-copy">
            <h2 id="storage-title">{confirmingReset ? "Delete all local data?" : "Your fonts stay private"}</h2>
            <p id="storage-description">{confirmingReset
              ? "This removes all imported fonts, saved variants, palettes, settings, and the app cache. This cannot be undone."
              : "Your fonts never leave your browser. All changes happen on your device, and your settings are saved here too."}</p>
            <p role="status">{cacheMessage}</p>
          </div>
          <div className="landing__storage-actions">
            {confirmingReset ? <>
              <Button type="button" variant="outline" size="sm" className="landing__storage-action landing__storage-cancel"
                autoFocus disabled={clearingCache} onClick={cancelReset}>Cancel</Button>
              <Button type="button" variant="destructive" size="sm" className="landing__storage-action"
                aria-describedby="storage-description" disabled={clearingCache} onClick={() => { void clearLocalCache(); }}>
                {clearingCache ? "Clearing…" : "Delete everything"}
              </Button>
            </> : <Button ref={resetTrigger} type="button" variant="destructive" size="sm" className="landing__storage-action"
              onClick={() => { setCacheMessage(""); setConfirmingReset(true); }}>
              Delete data
            </Button>}
          </div>
        </section>
      </main>
    </div>
  );
}
