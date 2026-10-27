import { createRoot } from "react-dom/client";
import { SiteFooter } from "./app/shell/SiteFooter";
import { ThemeProvider } from "./components/theme/ThemeProvider";
import { TooltipProvider } from "./components/ui/tooltip";
import { RendererProvider } from "./app/renderer/renderer-context";
import { createWorkerRendererService } from "./app/renderer/worker-service";
import { App } from "./app/App";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("App root element is missing.");
// Transfer the static fallback to React's single metadata owner.
document.head.querySelectorAll("[data-page-metadata]").forEach((element) => element.remove());
createRoot(root).render(
  <ThemeProvider>
    <TooltipProvider>
      <div className="app-shell">
        <div className="app-shell__page">
          <RendererProvider createService={createWorkerRendererService}>
            <App />
          </RendererProvider>
        </div>
        <SiteFooter />
      </div>
    </TooltipProvider>
  </ThemeProvider>,
);
