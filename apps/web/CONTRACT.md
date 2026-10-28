# Web output contract

Paths below are relative to the repository root.

- `just web` writes a self-contained static app to `out/web/`, independent of `out/specimens` and generator
  configuration. It serves from `out/web/` beneath the configured hosting URL prefix and exposes no font-upload
  endpoint: fonts stay in the browser-local library.
- The build consumes the candidate-enabled standard SIMD preview renderer at `crates/wasm/pkg-web-preview-simd128/`
  through the [WASM interface](../../crates/wasm/README.md) and the canonical font bytes in `fonts/`; both inputs arrive
  unchanged. Missing preview renderer artifacts fail the production build. The default renderer requires WebAssembly
  SIMD support; `FONT_WASM_PREVIEW_DIR` may select a scalar preview package for a separate compatible build.
- Published files include `index.html`, `404.html`, hashed JS/CSS/renderer/font/license assets, `manifest.webmanifest`,
  and the service worker (`sw.js`, scope `./`). `/fonts/` and `/palettes/` also have static HTML entries with public
  page metadata. `FONT_PREVIEW_SITE_URL`, when set, must have the configured hosting prefix as its path.
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
- Landing captures and the live working preview share the [renderer policy](src/app/renderer/preview-policy.ts).
  Captures record explicit renderer overrides, the resolved policy, its fingerprint and the Glypherie pipeline/scan.
  Production builds resolve the current [case configuration](scripts/landing-samples/main-page.json) through that policy
  and reject missing or mismatched capture declarations, pipeline, scan, policy or fingerprint with a regeneration
  command. Recorded family, size and axes must match the matrix and configured inputs; explicit sample text must match
  its configuration. Referenced images must belong to the same package and match their capture checksums. Builds require
  no network access or native rendering for these checks.
- Unsaved preview snapshots encode optional diagonal fitting as `diagonals=1`; omission means disabled. Saved variants
  store the same preference in their settings. Rendering and export forward it through the shared pipeline contract.
