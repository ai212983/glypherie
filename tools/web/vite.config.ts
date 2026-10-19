import path from "node:path";
import { defineConfig, mergeConfig } from "vite";
import { fontPwaPlugin } from "./pwa.js";
import uiConfig from "./vite.ui.js";

// Primary browser app: static React SPA written to out/web/. Relative base
// keeps navigation and hashed asset URLs working beneath a hosting prefix;
// FONT_PREVIEW_BASE overrides it (e.g. "/font-preview/" for project pages).
export default mergeConfig(uiConfig, defineConfig({
  base: process.env.FONT_PREVIEW_BASE ?? "./",
  publicDir: "public",
  server: {
    fs: {
      allow: [
        import.meta.dirname,
        path.resolve(import.meta.dirname, "..", "..", "fonts"),
      ],
    },
  },
  build: {
    outDir: "../../out/web",
    emptyOutDir: true,
    assetsInlineLimit: 0,
  },
  plugins: [fontPwaPlugin()],
}));
