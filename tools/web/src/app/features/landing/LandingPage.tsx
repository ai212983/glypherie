import * as React from "react";
import { ArrowRight, BookOpen, Code2 } from "lucide-react";
import { NavLink } from "../../../components/NavLink";
import { Button } from "../../../components/ui/button";
import { SiteHeader } from "../../shell/SiteHeader";
import { RasterizerComparison } from "./RasterizerComparison";
import "./LandingPage.css";

const SOURCE = "https://github.com/ai212983/font_generator";

interface LandingPageProps {
  nav: React.ReactNode;
  fontsHref: string;
  onFonts: () => void;
}

export function LandingPage({ nav, fontsHref, onFonts }: LandingPageProps): React.JSX.Element {
  return (
    <div className="landing">
      <SiteHeader title="Glypherie" titleAs="div" variant="brand" nav={nav} />
      <main id="main" className="landing__main" data-landing>
        <div className="landing__intro-row">
          <div>
            <h1 id="landing-title">Bitmap fonts for low-resolution displays.</h1>
            <p className="landing__intro">Convert TTF and OTF fonts for monochrome and grayscale displays.</p>
          </div>
          <div className="landing__actions">
            <Button asChild size="lg">
              <NavLink href={fontsHref} onNavigate={onFonts}>Open font library <ArrowRight aria-hidden="true" /></NavLink>
            </Button>
            <div className="landing__links">
              <a href={`${SOURCE}#documentation`} className="landing__text-link"><BookOpen aria-hidden="true" />Documentation</a>
              <a href={SOURCE} className="landing__text-link"><Code2 aria-hidden="true" />Source on GitHub</a>
            </div>
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

        <section className="landing__details" aria-labelledby="storage-title">
          <h2 id="storage-title">Local storage</h2>
          <p>Your fonts and settings stay in this browser. Clearing site data deletes them.</p>
        </section>
      </main>
    </div>
  );
}
