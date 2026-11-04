import { NavLink } from "../../components/NavLink";

interface PrimaryNavProps {
  active: "fonts" | "palettes" | "screen" | "scenes" | null;
  fontsHref: string;
  palettesHref: string;
  screenHref: string;
  scenesHref: string;
  onFonts: () => void;
  onPalettes: () => void;
  onScreen: () => void;
  onScenes: () => void;
}

// Top-level app navigation. Real anchors keep native behaviors (new tabs,
// direct loads); the active section is exposed through aria-current.
export function PrimaryNav({ active, fontsHref, palettesHref, screenHref, scenesHref, onFonts, onPalettes, onScreen, onScenes }: PrimaryNavProps): React.JSX.Element {
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
      <NavLink
        href={screenHref}
        data-primary-nav="screen"
        onNavigate={onScreen}
        aria-current={active === "screen" ? "page" : undefined}
      >
        Screen
      </NavLink>
      <NavLink
        href={scenesHref}
        data-primary-nav="scenes"
        onNavigate={onScenes}
        aria-current={active === "scenes" ? "page" : undefined}
      >
        Scenes
      </NavLink>
    </nav>
  );
}
