import type { Plugin } from "vite";
import { VitePWA, type VitePWAOptions } from "vite-plugin-pwa";

export function fontPwaPlugin(): Plugin[] {
  const options: Partial<VitePWAOptions> = {
    strategies: "generateSW",
    registerType: "prompt",
    injectRegister: false,
    devOptions: { enabled: false },
    manifest: {
      id: "./",
      name: "Inkplate Font Preview",
      short_name: "Font Preview",
      description: "Preview font renderings and inspect type metadata, offline.",
      scope: "./",
      start_url: "./",
      display: "standalone",
      background_color: "#ffffff",
      theme_color: "#111827",
      icons: [
        { src: "icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
        { src: "icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
        { src: "icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        { src: "icons/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      ],
    },
    workbox: {
      globPatterns: ["**/*.{html,js,css,wasm,ttf,otf,woff,woff2,svg,png,webmanifest,txt}"],
      globIgnores: ["content/**", "comparison-content/**"],
      maximumFileSizeToCacheInBytes: 16 * 1024 * 1024,
      navigateFallback: "index.html",
      navigateFallbackDenylist: [/\/[^/?]+\.[^/]+$/],
      cleanupOutdatedCaches: true,
      clientsClaim: false,
      skipWaiting: false,
    },
  };
  return [{
    name: "retire-production-worker-in-dev",
    // A cached production page can still own this origin after switching to
    // Vite. Replace its worker using the documented self-destroying pattern:
    // Keep the existing explicit Update action before retiring the worker.
    // https://vite-pwa-org.netlify.app/guide/unregister-service-worker
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url ?? "/", "http://localhost").pathname;
        if (pathname !== `${server.config.base}sw.js`) return next();
        response.setHeader("Content-Type", "application/javascript");
        response.setHeader("Cache-Control", "no-store");
        response.end(`
self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") event.waitUntil(self.skipWaiting());
});
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    await self.clients.claim();
    await self.registration.unregister();
  })());
});
`);
      });
    },
  }, ...VitePWA(options)];
}
