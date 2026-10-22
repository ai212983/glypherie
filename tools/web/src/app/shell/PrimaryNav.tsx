import { NavLink } from "../../components/NavLink";

interface PrimaryNavProps {
  active: "fonts" | "palettes";
  fontsHref: string;
  palettesHref: string;
  onFonts: () => void;
  onPalettes: () => void;
}

// Top-level app navigation. Real anchors keep native behaviors (new tabs,
// direct loads); the active section is exposed through aria-current.
export function PrimaryNav({ active, fontsHref, palettesHref, onFonts, onPalettes }: PrimaryNavProps): React.JSX.Element {
  return (
    <nav aria-label="Primary" className="site-header__navlinks">
      <NavLink
        href={fontsHref}
        data-primary-nav="fonts"
        onNavigate={onFonts}
        aria-current={active === "fonts" ? "page" : undefined}
      >
        Fonts
      </NavLink>
      <NavLink
        href={palettesHref}
        data-primary-nav="palettes"
        onNavigate={onPalettes}
        aria-current={active === "palettes" ? "page" : undefined}
      >
        Palettes
      </NavLink>
    </nav>
  );
}
