import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "../ui/button";
import { useTheme } from "./ThemeProvider";

export function ThemeToggle(): React.JSX.Element {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      data-theme-toggle
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={dark}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={toggle}
    >
      {dark ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
    </Button>
  );
}
