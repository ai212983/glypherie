# Web

<!-- cspell:words Adafruit pdfontconv Tophat -->

Local-first font preview as a static React app (`out/web/`). See the [web contract](CONTRACT.md) and the
[WASM interface](../wasm/README.md).

## Setup

Prerequisites: Node.js (>= 22.18) with npm; the recommended version is pinned in the repository
[.node-version](../../.node-version). Building the preview renderer additionally needs the
[WASM prerequisites](../wasm/README.md#build).

From `tools/web`:

```sh
npm ci --ignore-scripts
```

Then build the preview renderer from the repository root:

```sh
WASM_SIMD128=1 tools/wasm/build.sh web preview
```

## Commands

Inside `tools/web`:

```sh
npm run dev             # Vite dev server (default port 8903; --port overrides)
npm run build           # Vite production build into out/web/
npm run preview         # Serve out/web/ on port 8904
npm run typecheck       # Strict tsc over the app, scripts, and tests
npm test                # Node --test over tests/unit, tests/browser, tests/build
npm run storybook       # Component explorer (default port 6006; --port overrides)
npm run build-storybook # Static component explorer into out/storybook/
```

Build with `npm run build` before running `npm run preview`.

Reserve `http://localhost:8903` for development and `http://localhost:8904` for the built app so their service workers
and browser-local libraries stay separate. Both servers fail if their port is occupied instead of selecting another.

The development server also serves generated pages under `out/diagnostics/` through
`http://localhost:8903/@fs/<absolute-file-path>`. Use a generated comparison's `site/index.html` path to open it
alongside the regular app.

Storybook uses the dependencies installed by `npm ci --ignore-scripts` plus the staged preview renderer (`WASM_SIMD128=1
tools/wasm/build.sh web preview` from the repository root); the FontCanvas stories render real glyphs through it. Use
its theme toolbar to switch between light and dark previews.

On macOS, install the test browsers from `tools/web` with `npx --no-install playwright-core install chromium`. Browser
tests then use Playwright's headless shell, avoiding Chrome's temporary Dock icons. Leave `WEB_TEST_BROWSER` unset for
this default; pointing it at regular Chrome can bring back the Dock flashes. Other platforms default to
`/opt/google/chrome/chrome`. Tests skip when the browser installation is unavailable.

## Configuration

- `FONT_PREVIEW_BASE`: absolute hosting URL prefix for the app build (default `/`), for example `/font_generator/`. The
  GitHub Pages workflow sets it from the Pages configuration.
- `FONT_WASM_PREVIEW_DIR`: preview renderer package (default `tools/wasm/pkg-web-preview-simd128`, built by
  `WASM_SIMD128=1 tools/wasm/build.sh web preview` from the repository root). The default requires browser WebAssembly
  SIMD support. For a scalar build, run `WASM_SIMD128=0 tools/wasm/build.sh web preview`, then set this variable to that
  package's absolute path (`tools/wasm/pkg-web-preview`) when building or serving the app.
- `WEB_TEST_BROWSER`: browser binary for integration tests.
- `STORYBOOK_TEST_HARNESSES=1`: include the opt-in lifecycle test fixtures under `tests/fixtures/` in Storybook (used by
  `renderer-harness.test.ts`); normal Storybook never loads them.
- `STORYBOOK_ALLOWED_HOSTS`: comma-separated host names allowed through a reverse proxy, such as a Tailscale Serve host
  name. Run `tailscale serve --bg --https=6007 http://127.0.0.1:6006` to proxy the running Storybook over Tailscale;
  remove the proxy with `tailscale serve --https=6007 off`.
- shadcn components live in `src/components/ui/` (`new-york`, CSS variables in `src/index.css`); add more with `npx
  shadcn add <component>`. `@/*` resolves to `src/*` and the bare `utils` specifier resolves to `src/utils.ts` (the `cn`
  helper) via `tsconfig.json`, `vite.ui.ts`, and `components.json`.

## Front page samples

Requires Python 3.10+, Node with the web dependencies above and its Playwright Chromium installation, Rust/Cargo, a C
compiler, `pkg-config` and FreeType development files (`brew install pkg-config freetype` on macOS). From the repository
root:

```sh
python3 -m venv out/diagnostics/landing-samples/.venv
source out/diagnostics/landing-samples/.venv/bin/activate
python -m pip install -r tools/web/scripts/landing-samples/requirements.txt
just landing-samples --font fonts/Roboto.ttf --size 16 --axis wght=300 --axis wdth=100
```

The first run downloads pinned LVGL and Adafruit converter sources into `out/diagnostics/landing-samples/_tools/` and
builds the adapters. Every run uses the hosted pdfontconv and Tophat apps, requiring internet access. The comparison
supports fonts covering printable ASCII and monochrome output; text may contain printable ASCII and line feeds. All
converters receive the same static font instance. Each output directory contains a browser gallery, original exports,
capture settings, source identities, logs and verification results. Open the printed gallery URL with `npm run dev`
running. Runs write fresh directories by default; `--output PATH` must name a new directory.

```sh
# Repeat --size for a size sweep; --text-file reads UTF-8 sample text.
just landing-samples --font fonts/Roboto.ttf --size 14 --size 18 --text-file sample.txt
# Different fonts, axes and settings in one run; font paths are relative to the config.
just landing-samples --config tools/web/scripts/landing-samples/cases.example.json
# Regenerate the main-page family/size matrix, then rebuild the app.
just landing-samples --config tools/web/scripts/landing-samples/main-page.json --publish-matrix
npm --prefix tools/web run build
# Run the script's checks in the activated environment.
python -m unittest discover -s tools/web/scripts/landing-samples -p 'test_*.py'
```

Run `just landing-samples --help` for settings. JSON cases accept `id`, `font`, `size_px`, `axes`, `text`, `threshold`,
`fitting`, `rasterization`, `diagonal_fitting`, `dropout`, `include_stubs`, `font_instructions`, `width`, `line_step`,
`family_id`, `family_label` and `stem_target_px`. Omitted case settings inherit command-line values. Set
`stem_target_px` (or `--stem-target-px`) without an explicit `wght` coordinate to select the family-wide weight from
source stem geometry; other axes remain explicit or use font defaults. Native horizontal body-run measurements are saved
separately in each capture. `--publish-matrix` requires every family at every size; `--publish` updates only the legacy
single-case assets. `--threshold` affects the two hosted converters; Glypherie's selected FreeType scanner, LVGL and
Adafruit retain their native monochrome settings. Source kerning is disabled; each converter retains its own advances,
and Glypherie retains its exported fitted pair corrections. `--no-diagonal-fitting` is required with `--fitting
font_hints_first` or `source_relative`. Generation checks do not establish optical acceptance; follow the
[evaluation rules](../../docs/evaluation.md).
