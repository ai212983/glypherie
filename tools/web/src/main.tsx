import { createRoot } from "react-dom/client";
import { PwaStatus } from "./app/shell/PwaStatus";
import { ThemeProvider } from "./components/theme/ThemeProvider";
import { RendererProvider } from "./app/renderer/renderer-context";
import { createWorkerRendererService } from "./app/renderer/worker-service";
import { App } from "./app/App";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("App root element is missing.");
createRoot(root).render(
  <ThemeProvider>
    {import.meta.env.PROD && <PwaStatus />}
    <RendererProvider createService={createWorkerRendererService}>
      <App />
    </RendererProvider>
  </ThemeProvider>,
);
