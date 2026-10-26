import { NavLink } from "../../components/NavLink";
import { navigateTo, readRouteSearch } from "../navigation/location";
import * as React from "react";
import { CanvasControls } from "./CanvasControls";
import { ZoomControl } from "../renderer/ZoomControl";
import { useDisplayPreferences } from "./DisplayPreferences";
import { cn } from "utils";
import { ThemeToggle } from "../../components/theme/ThemeToggle";
import { indexPath } from "../navigation/router";
import "./SiteHeader.css";

interface SiteHeaderProps {
  eyebrow?: React.ReactNode;
  title: string;
  variant?: "default" | "brand";
  sub?: React.ReactNode;
  controls?: React.ReactNode;
  search?: React.ReactNode;
  actions?: React.ReactNode;
  nav?: React.ReactNode;
  displayControls?: boolean;
}

export function SiteHeader({ eyebrow, title, sub, controls, search, actions, nav, displayControls = true, variant = "default" }: SiteHeaderProps): React.JSX.Element {
  const { zoom, onZoom } = useDisplayPreferences();
  const brand = variant === "brand";
  return (
    <header data-site-header className={cn("site-header sticky top-0 z-40 w-full border-b", brand
      ? "studio-card border-studio-border bg-font-card shadow-studio-card"
      : "border-line bg-card", !displayControls && "site-header--no-display")}>
      <div className="site-header__inner">
        <div className="site-header__identity">
          {eyebrow && <div className="site-header__eyebrow">{eyebrow}</div>}
          <h1 className={cn("m-0 truncate", brand
            ? "font-display text-[16px] leading-6 font-bold tracking-[1.6px] text-studio-foreground uppercase"
            : "font-[650] text-[clamp(1.2rem,2.4vw,1.5rem)] tracking-[-.035em]")}>
            {title === "Glypherie" ? (
              <NavLink href={indexPath(readRouteSearch())} onNavigate={() => navigateTo(indexPath(readRouteSearch()))} className="text-inherit no-underline">
                {title}
              </NavLink>
            ) : title}
          </h1>
          {sub}
        </div>
        {nav && <div className="site-header__nav">{nav}</div>}
        {search && <div className="site-header__search">{search}</div>}
        {actions && <div className="site-header__actions">{actions}</div>}
        {displayControls && (
          <div className="site-header__display" aria-label="Preview display">
            <CanvasControls />
            <div data-global-zoom><ZoomControl zoom={zoom} onZoom={onZoom} /></div>
            <span className="site-header__divider" aria-hidden="true" />
          </div>
        )}
        <div className="site-header__theme">
          <ThemeToggle className="size-8 rounded-md border-transparent bg-transparent text-muted-foreground shadow-none hover:bg-accent hover:text-foreground dark:border-transparent dark:bg-transparent dark:hover:bg-accent" />
        </div>
      </div>
      {controls}
    </header>
  );
}
