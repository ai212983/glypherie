import path from "node:path";
import { readFileSync } from "node:fs";
import { defineConfig, mergeConfig } from "vite";
import { pagesRoutingPlugin } from "./pages-routing.js";
import { fontPwaPlugin } from "./pwa.js";
import { landingCaptureGuardPlugin } from "./scripts/landing-capture-guard.ts";
import uiConfig from "./vite.ui.js";
import { createBuildInfo } from "./scripts/build-info.ts";
import { devicePackagingPlugin } from "./scripts/devices-packaging.ts";
import { pageMetadataPlugin } from "./scripts/page-metadata.ts";

// Assets, history routes and the Pages fallback share the configured hosting prefix.
export default defineConfig(({ command }) =>
  mergeConfig(
    uiConfig,
    defineConfig({
      define: {
        __APP_BUILD__: JSON.stringify(
          createBuildInfo(
            path.resolve(import.meta.dirname, "../.."),
            JSON.parse(readFileSync(path.join(import.meta.dirname, "package.json"), "utf8")).version,
            command === "serve",
          ),
        ),
      },
      base: process.env.FONT_PREVIEW_BASE ?? "/",
      publicDir: "public",
      server: {
        port: 8903,
        strictPort: true,
        // Use fs.watch: fsevents can miss changes on macOS.
        watch: process.platform === "darwin" ? { useFsEvents: false, usePolling: false } : undefined,
        fs: {
          allow: [
            import.meta.dirname,
            path.resolve(import.meta.dirname, "..", "..", "fonts"),
            path.resolve(import.meta.dirname, "..", "..", "out", "diagnostics"),
          ],
        },
      },
      preview: {
        port: 8904,
        strictPort: true,
      },
      build: {
        outDir: "../../out/web",
        emptyOutDir: true,
        assetsInlineLimit: 0,
      },
      optimizeDeps: {
        exclude: ["@electric-sql/pglite"],
      },
      worker: {
        format: "es",
        rollupOptions: {
          output: {
            // Stable domain-owner entry URL across deployments. The SharedWorker
            // joins by (name, URL): a hashed URL would reject a new tab while an
            // old tab lives, while versioning the name instead would run two
            // engines on the same persistent path. Mixed app/owner generations
            // are fenced by the versioned handshake, not by the URL.
            entryFileNames: (chunk) =>
              chunk.name === "worker" ? "assets/domain-worker.js" : "assets/[name]-[hash].js",
          },
        },
      },
      plugins: [
        pagesRoutingPlugin(),
        fontPwaPlugin(),
        pageMetadataPlugin(),
        // Production only: dev/preview serve the checked-in captures as-is.
        ...(command === "build"
          ? [
              landingCaptureGuardPlugin(path.resolve(import.meta.dirname, "../..")),
              devicePackagingPlugin(path.resolve(import.meta.dirname)),
            ]
          : []),
        {
          name: "hmr-status-handshake",
          configureServer(server) {
            server.hot.on("glypherie:hmr-ping", (_data, client) => {
              client.send("glypherie:hmr-pong");
            });
          },
        },
        {
          name: "renderer-license",
          generateBundle() {
            const license = readFileSync(
              path.resolve(import.meta.dirname, "../../crates/generator/vendor/freetype-mono/FTL.TXT"),
              "utf8",
            );
            const scanLicense = readFileSync(
              path.resolve(import.meta.dirname, "../../crates/generator/vendor/skrifa-scan/LICENSE-MIT"),
              "utf8",
            );
            const normLicense = readFileSync(
              path.resolve(import.meta.dirname, "../../crates/generator/vendor/cpython-math/LICENSE"),
              "utf8",
            );
            const typefacetLicense = readFileSync(
              path.resolve(import.meta.dirname, "../../crates/generator/src/kerning/typefacet/LICENSE-APACHE-2.0.txt"),
              "utf8",
            );
            const typefacetNotice = readFileSync(
              path.resolve(import.meta.dirname, "../../crates/generator/src/kerning/typefacet/NOTICE.txt"),
              "utf8",
            );
            const fontforgeLicense = readFileSync(
              path.resolve(
                import.meta.dirname,
                "../../crates/generator/src/kerning/fontforge/LICENSE-BSD-3-Clause.txt",
              ),
              "utf8",
            );
            const fontforgeNotice = readFileSync(
              path.resolve(import.meta.dirname, "../../crates/generator/src/kerning/fontforge/NOTICE.txt"),
              "utf8",
            );
            this.emitFile({
              type: "asset",
              fileName: "renderer-license.txt",
              source:
                "This software uses FreeType 2.15.0, copyright 1996-2026 The FreeType Project (www.freetype.org). All rights reserved.\n\n" +
                license +
                "\n\nSkrifa 0.48.0 scan metadata adaptation (MIT):\n\n" +
                scanLicense +
                "\n\nCPython 3.14 compensated norm adaptation (PSF):\n\n" +
                normLicense +
                "\n\n" +
                typefacetNotice +
                "\n\n" +
                typefacetLicense +
                "\n\n" +
                fontforgeNotice +
                "\n\n" +
                fontforgeLicense,
            });
          },
        },
      ],
    }),
  ),
);
