# Web

Local-first font preview as a static React app (`out/web/`). See the [web contract](CONTRACT.md) and the
[WASM interface](../wasm/README.md).

## Setup

From the repository root, using [mise](https://mise.jdx.dev/):

```sh
mise install --locked just
just web-setup
just wasm-build-preview
```

## Commands

```sh
just dev                 # Dev server with hot reload on port 8903
just dev 8910            # Explicitly use a different dev server port
just web                 # Build the app into out/web/
just web-serve           # Serve out/web/ on port 8904
just web-test            # Run tests
just web-typecheck       # Typecheck the app, scripts, and tests
just web-storybook       # Storybook dev server on port 6006
just web-storybook-build # Build Storybook into out/storybook/
```

`just dev` (also `just preview`), `just web` and `just web-serve` use Node.js (22.18 or newer) and npm from your PATH;
they do not require mise. Build with `just web` before running `just web-serve`.

Reserve `http://localhost:8903` for development and `http://localhost:8904` for the built app so their service workers
and browser-local libraries stay separate. Both servers fail if their port is occupied instead of selecting another.

Direct npm equivalents inside `tools/web`:

```sh
npm run dev             # Vite dev server (default port 8903; --port overrides)
npm run build           # Vite production build into out/web/
npm run preview         # Serve out/web/ on port 8904
npm run typecheck       # Strict tsc over the app, scripts, and tests
npm test                # Node --test over tests/unit, tests/browser, tests/build
npm run storybook       # Component explorer (default port 6006; --port overrides)
npm run build-storybook # Static component explorer into out/storybook/
```

Storybook uses the dependencies installed by `just web-setup` plus the staged preview renderer (`just
wasm-build-preview`); the FontCanvas stories render real glyphs through it. Use its theme toolbar to switch between
light and dark previews.

On macOS, install the test browsers from `tools/web` with `npx --no-install playwright-core install chromium`. Browser
tests then use Playwright's headless shell, avoiding Chrome's temporary Dock icons. Leave `WEB_TEST_BROWSER` unset for
this default; pointing it at regular Chrome can bring back the Dock flashes. Other platforms default to
`/opt/google/chrome/chrome`. Tests skip when the browser installation is unavailable.

## Configuration

- `FONT_PREVIEW_BASE`: hosting URL prefix for the app build (default `./`).
- `FONT_WASM_PREVIEW_DIR`: preview renderer package (default `tools/wasm/pkg-web-preview-simd128`, built by `just
  wasm-build-preview`). The default requires browser WebAssembly SIMD support. For a scalar build, run `WASM_SIMD128=0
  tools/wasm/build.sh web preview`, then set this variable to that package's absolute path
  (`tools/wasm/pkg-web-preview`) when building or serving the app.
- `WEB_TEST_BROWSER`: browser binary for integration tests.
- `STORYBOOK_TEST_HARNESSES=1`: include the opt-in lifecycle test fixtures under `tests/fixtures/` in Storybook (used by
  `renderer-harness.test.ts`); normal Storybook never loads them.
- `STORYBOOK_ALLOWED_HOSTS`: comma-separated host names allowed through a reverse proxy, such as a Tailscale Serve host
  name. Run `tailscale serve --bg --https=6007 http://127.0.0.1:6006` to proxy the running Storybook over Tailscale;
  remove the proxy with `tailscale serve --https=6007 off`.
- shadcn components live in `src/components/ui/` (`new-york`, CSS variables in `src/index.css`); add more with `npx
  shadcn add <component>`. `@/*` resolves to `src/*` and the bare `utils` specifier resolves to `src/utils.ts` (the `cn`
  helper) via `tsconfig.json`, `vite.ui.ts`, and `components.json`.
