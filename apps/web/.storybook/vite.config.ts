import path from "node:path";
import { defineConfig, mergeConfig } from "vite";
import uiConfig from "../vite.ui.js";

export default mergeConfig(uiConfig, defineConfig({
  publicDir: false,
  server: {
    fs: {
      // Real rendering stories fetch the canonical font binaries through
      // ?url asset imports outside the web root, mirroring the app build.
      allow: [
        path.resolve(import.meta.dirname, ".."),
        path.resolve(import.meta.dirname, "..", "..", "..", "fonts"),
      ],
    },
  },
}));
