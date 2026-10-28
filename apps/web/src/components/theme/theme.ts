export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "font-preview.theme";
export const LIGHT_THEME_COLOR = "#f6f7f5";
export const DARK_THEME_COLOR = "#121516";

function storage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function readStoredTheme(): Theme | null {
  try {
    const value = storage()?.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

export function writeStoredTheme(theme: Theme): void {
  try {
    storage()?.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* explicit choice stays in memory for this session */
  }
}

export function systemTheme(): Theme {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "dark" ? DARK_THEME_COLOR : LIGHT_THEME_COLOR);
}
