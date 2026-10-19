import * as React from "react";
import { ThemeToggle } from "../../components/theme/ThemeToggle";

interface SiteHeaderProps {
  eyebrow: React.ReactNode;
  title: string;
  sub?: React.ReactNode;
  controls?: React.ReactNode;
}

export function SiteHeader({ eyebrow, title, sub, controls }: SiteHeaderProps): React.JSX.Element {
  return (
    <header data-site-header className="sticky top-0 z-40 w-full border-b border-line bg-card">
      <div className="mx-auto w-[min(100%-3rem,1440px)] px-6 py-3">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="m-0 mb-[.15rem] text-[.8rem] text-soft">{eyebrow}</div>
            <h1 className="m-0 truncate font-[650] text-[clamp(1.4rem,2.4vw,1.75rem)] tracking-[-.035em]">{title}</h1>
            {sub}
          </div>
          <div className="shrink-0">
            <ThemeToggle />
          </div>
        </div>
        {controls}
      </div>
    </header>
  );
}
