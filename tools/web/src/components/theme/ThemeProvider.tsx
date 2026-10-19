import * as React from "react";
import { applyTheme, readStoredTheme, systemTheme, writeStoredTheme, type Theme } from "./theme.js";

interface ThemeContextValue {
  theme: Theme;
  toggle: () => void;
}

const ThemeContext = React.createContext<ThemeContextValue>({ theme: "light", toggle: () => undefined });

export function ThemeProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [explicit, setExplicit] = React.useState<Theme | null>(() => readStoredTheme());
  const [systemDark, setSystemDark] = React.useState<boolean>(() => systemTheme() === "dark");
  const theme = explicit ?? (systemDark ? "dark" : "light");

  React.useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent): void => setSystemDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  React.useEffect(() => {
    applyTheme(theme);
  }, [theme ]);

  const toggle = React.useCallback(() => {
    const next: Theme = (explicit ?? (systemDark ? "dark" : "light")) === "dark" ? "light" : "dark";
    writeStoredTheme(next);
    setExplicit(next);
  }, [explicit, systemDark]);

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return React.useContext(ThemeContext);
}
