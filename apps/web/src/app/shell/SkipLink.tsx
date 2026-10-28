import * as React from "react";

// Targets the page's <main id="main">, which lives in the page components
// below, not beside this link.
export function SkipLink(): React.JSX.Element {
  return (
    <button
      type="button"
      data-skip-link
      className="absolute -top-16 left-4 z-50 cursor-pointer bg-card p-3 underline focus:top-4"
      onClick={() => {
        const main = document.getElementById("main");
        if (main) {
          if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1");
          main.focus({ preventScroll: true });
          main.scrollIntoView();
        }
      }}
    >
      Skip to content
    </button>
  );
}
