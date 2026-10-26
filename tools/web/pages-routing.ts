import type { Plugin } from "vite";

/**
 * GitHub Pages has no SPA rewrite rule. Adapt the 404-to-index round trip from
 * https://github.com/rafgraph/spa-github-pages using the configured Vite base
 * and URI encoding so paths, queries and fragments survive without delimiters.
 */
export function pagesRoutingPlugin(): Plugin {
  let base = "/";
  return {
    name: "pages-routing",
    configResolved(config) {
      base = config.base;
      if (!base.startsWith("/") || base.startsWith("//") || /[?#]/.test(base)) {
        throw new Error("FONT_PREVIEW_BASE must be an absolute hosting path, for example /font_generator/.");
      }
    },
    transformIndexHtml() {
      return [{ tag: "script", injectTo: "head-prepend", children: `
// Restore the clean URL before the app or service worker starts.
(() => {
  const route = new URLSearchParams(location.search).get("__pages_route");
  if (!route || location.pathname !== ${JSON.stringify(base)}) return;
  const target = new URL(route, location.origin);
  if (target.origin === location.origin && target.pathname.startsWith(${JSON.stringify(base)})) {
    history.replaceState(null, "", target.pathname + target.search + target.hash);
  }
})();` }];
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "404.html", source: `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Font preview</title></head>
<body><p>Page not found. <a href="${base}">Open Glypherie</a></p>
<script>
(() => {
  const base = ${JSON.stringify(base)};
  if (location.pathname.startsWith(base) && location.pathname !== base + "404.html") {
    location.replace(base + "?__pages_route=" + encodeURIComponent(location.pathname + location.search + location.hash));
  }
})();
</script></body></html>` });
    },
  };
}
