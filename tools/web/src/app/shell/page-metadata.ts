export const PUBLIC_PAGES = {
  home: {
    path: "",
    title: "Glypherie — Bitmap fonts for low-resolution displays",
    description: "Generate small bitmap fonts for monochrome and grayscale displays. Configure TrueType and OpenType rendering, compare rasterizers and export Playdate fonts.",
  },
  fonts: {
    path: "fonts/",
    title: "Font library — Glypherie",
    description: "Import and compare fonts, create bitmap font variants, and manage your browser-local font library in Glypherie.",
  },
  palettes: {
    path: "palettes/",
    title: "Palettes — Glypherie",
    description: "Create and compare monochrome and grayscale palettes with 2, 4, 8 or 16 levels for bitmap font previews in Glypherie.",
  },
} as const;

export const PREVIEW_DESCRIPTION = "Configure bitmap font rendering, compare the preview, and export a font in Glypherie. Fonts and settings stay in this browser.";
export const VARIANT_DESCRIPTION = "Edit a saved bitmap font variant and preview its rendering in Glypherie. Fonts and variants stay in this browser.";
