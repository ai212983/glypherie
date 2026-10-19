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
just web                 # Build the app into out/web/
just web-test            # Run tests
just web-typecheck       # Typecheck the app, scripts, and tests
just web-storybook       # Storybook dev server on port 6006
just web-storybook-build # Build Storybook into out/storybook/
```

Direct npm equivalents inside `tools/web`:

```sh
npm run dev             # Vite dev server (default port 8903; --port overrides)
npm run build           # Vite production build into out/web/
npm run typecheck       # Strict tsc over the app, scripts, and tests
npm test                # Node --test over tests/unit, tests/browser, tests/build
npm run storybook       # Component explorer (default port 6006; --port overrides)
npm run build-storybook # Static component explorer into out/storybook/
```

Storybook uses the dependencies installed by `just web-setup` plus the staged preview renderer (`just
wasm-build-preview`); the FontCanvas stories render real glyphs through it. Use its theme toolbar to switch between
light and dark previews.

Browser tests use `/opt/google/chrome/chrome` or `WEB_TEST_BROWSER`; they skip when the browser is unavailable.

## Configuration

- `FONT_PREVIEW_BASE`: hosting URL prefix for the app build (default `./`).
- `FONT_WASM_PREVIEW_DIR`: preview renderer package (default `tools/wasm/pkg-web-preview`).
- `WEB_TEST_BROWSER`: browser binary for integration tests.
- `STORYBOOK_TEST_HARNESSES=1`: include the opt-in lifecycle test fixtures under `tests/fixtures/` in Storybook (used by
  `renderer-harness.test.ts`); normal Storybook never loads them.
- `STORYBOOK_ALLOWED_HOSTS`: comma-separated host names allowed through a reverse proxy, such as a Tailscale Serve host
  name. Run `tailscale serve --bg --https=6007 http://127.0.0.1:6006` to proxy the running Storybook over Tailscale;
  remove the proxy with `tailscale serve --https=6007 off`.
- shadcn components live in `src/components/ui/` (`new-york`, CSS variables in `src/index.css`); add more with `npx
  shadcn add <component>`. `@/*` resolves to `src/*` and the bare `utils` specifier resolves to `src/utils.ts` (the `cn`
  helper) via `tsconfig.json`, `vite.ui.ts`, and `components.json`.
