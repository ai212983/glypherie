# Web output contract

Paths below are relative to the repository root.

- `just web` writes a self-contained static app to `out/web/`, independent of `out/specimens` and generator
  configuration. It serves from `out/web/` beneath the configured hosting URL prefix and exposes no font-upload
  endpoint: fonts stay in the browser-local library.
- The build consumes the candidate-enabled standard SIMD preview renderer at `tools/wasm/pkg-web-preview-simd128/`
  through the [WASM interface](../wasm/README.md) and the canonical font bytes in `fonts/`; both inputs arrive
  unchanged. Missing preview renderer artifacts fail the production build. The default renderer requires WebAssembly
  SIMD support; `FONT_WASM_PREVIEW_DIR` may select a scalar preview package for a separate compatible build.
- Published files include `index.html`, `404.html`, hashed JS/CSS/renderer/font/license assets, `manifest.webmanifest`,
  and the service worker (`sw.js`, scope `./`).
- Routes use paths relative to the configured hosting prefix: `/` shows the introduction, `/fonts/` shows the font
  library, `/font/<content-id>/?v=1…` shows that font's unsaved preview with its versioned settings, and
  `/font/<content-id>/variant/<variant-id>/` shows one saved variant whose settings live in the browser-local database,
  never in the URL. `/palettes/` shows the standalone palette lab, independent of the font library with no palette state
  in the URL. Palette presets (including the read-only Monochrome preset) live in the same browser-local database.
  Presets contain 2, 4, 8 or 16 gray levels; saved font settings reference a preset by ID, defaulting to Monochrome when
  absent or unavailable. Unsaved preview snapshots carry this browser-local reference as `palette`; another browser
  without that preset uses Monochrome. Legacy `?font=<content-id>` snapshots and `#family-<content-id>` links migrate to
  the clean path. Existing `#/…` routes also migrate to clean paths, including the former library route `#/` to
  `/fonts/`. GitHub Pages uses `404.html` to redirect direct route requests through `index.html`, preserving the path
  and query; this requires JavaScript and an extra request on a fresh deep link. Hosts with SPA rewrites can serve
  `index.html` directly for route requests. An unknown font id or route shows the library with a recovery notice.
- Unsaved preview snapshots encode optional diagonal fitting as `diagonals=1`; omission means disabled. Saved variants
  store the same preference in their settings. Rendering and export forward it through the shared pipeline contract.
