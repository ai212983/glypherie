import type { Plugin } from "vite";
import { PUBLIC_PAGES } from "../src/app/shell/page-metadata.ts";

const escapeAttribute = (value: string): string => value
  .replaceAll("&", "&amp;")
  .replaceAll('"', "&quot;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;");

export function pageMetadataPlugin(): Plugin {
  let siteUrl = "";
  let base = "/";
  const head = (page: typeof PUBLIC_PAGES[keyof typeof PUBLIC_PAGES]): string => {
    const title = escapeAttribute(page.title);
    const description = escapeAttribute(page.description);
    const url = siteUrl ? escapeAttribute(new URL(page.path, siteUrl).href) : "";
    return `<title data-page-metadata>${title}</title>
<meta data-page-metadata name="description" content="${description}">
<meta data-page-metadata name="robots" content="index,follow">
<meta data-page-metadata property="og:title" content="${title}">
<meta data-page-metadata property="og:description" content="${description}">
${url ? `<link data-page-metadata rel="canonical" href="${url}">\n<meta data-page-metadata property="og:url" content="${url}">` : ""}`;
  };
  return {
    name: "page-metadata",
    enforce: "post",
    config(config) {
      base = config.base ?? "/";
      const configured = process.env.FONT_PREVIEW_SITE_URL;
      if (configured) {
        const parsed = new URL(configured);
        if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash) {
          throw new Error("FONT_PREVIEW_SITE_URL must be a public HTTP(S) URL without credentials, query or fragment.");
        }
        parsed.pathname = `${parsed.pathname.replace(/\/+$/, "")}/`;
        if (parsed.pathname !== base) throw new Error("FONT_PREVIEW_SITE_URL path must match FONT_PREVIEW_BASE.");
        siteUrl = parsed.href;
      }
      return { define: { __APP_SITE_URL__: JSON.stringify(siteUrl) } };
    },
    transformIndexHtml(html, context) {
      const page = context.path === `${base}fonts/` || context.path === "/fonts/" ? PUBLIC_PAGES.fonts
        : context.path === `${base}palettes/` || context.path === "/palettes/" ? PUBLIC_PAGES.palettes
        : PUBLIC_PAGES.home;
      const image = siteUrl ? `<meta property="og:image" content="${escapeAttribute(new URL("icons/icon-512.png", siteUrl).href)}">\n<meta property="og:image:alt" content="Glypherie bitmap font app icon">` : "";
      return html.replace("<!-- page-metadata -->", `${head(page)}
<meta property="og:type" content="website">
<meta property="og:site_name" content="Glypherie">
<meta name="twitter:card" content="summary">
${image}`);
    },
    generateBundle(_options, bundle) {
      const entry = bundle["index.html"];
      if (!entry || entry.type !== "asset" || typeof entry.source !== "string") throw new Error("Missing HTML entry for page metadata.");
      for (const page of [PUBLIC_PAGES.fonts, PUBLIC_PAGES.palettes]) {
        const html = entry.source.replace(/<(title|meta|link)\b[^>]*\bdata-page-metadata\b[^>]*>(?:[^<]*<\/title>)?\s*/g, "");
        this.emitFile({ type: "asset", fileName: `${page.path}index.html`, source: html.replace("</head>", `${head(page)}\n</head>`) });
      }
    },
  };
}
