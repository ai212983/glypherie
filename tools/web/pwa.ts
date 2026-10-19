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
  return VitePWA(options);
}
