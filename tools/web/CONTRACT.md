# Web output contract

Paths below are relative to the repository root.

- `just web` writes a self-contained static app to `out/web/`, independent of `out/specimens` and generator
  configuration. It serves from `out/web/` beneath any hosting URL prefix and exposes no font-upload endpoint: fonts
  stay in the browser-local library.
- The build consumes the candidate-enabled preview renderer at `tools/wasm/pkg-web-preview/` through the
  [WASM interface](../wasm/README.md) and the canonical font bytes in `fonts/`; both inputs arrive unchanged. Missing
  preview renderer artifacts fail the production build.
- Published files include `index.html`, hashed JS/CSS/renderer/font/license assets, `manifest.webmanifest`, and the
  service worker (`sw.js`, scope `./`).
- Routes live in the URL fragment under the one static document, so no server rewrites are needed: `#/` shows the font
  library, `#/font/<content-id>/?v=1…` shows that font's unsaved preview with its versioned settings, and
  `#/font/<content-id>/variant/<variant-id>/` shows one saved variant whose settings live in the browser-local database,
  never in the URL. Legacy `?font=<content-id>` snapshots and `#family-<content-id>` links migrate to the hash route. An
  unknown font id or route shows the library with a recovery notice.
