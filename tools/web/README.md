# Web

Eleventy site builder and HTTP preview. Builds write to `out/web/`. The [web contract](CONTRACT.md) owns presentation
and interaction requirements; the [generator contract](../generator/CONTRACT.md) owns imported package formats and
selection.

## Setup

From the repository root, using [mise](https://mise.jdx.dev/):

```sh
mise install --locked just
just web-setup
```

## Commands

```sh
just web            # Build the static site from existing exports
just web-watch      # Rebuild when sources change
just web-test       # Run tests
just wasm-build     # Build and stage the browser renderer
just preview-build  # Generate specimens/comparisons, stage WASM and build the site
```

To watch and serve existing exports:

```sh
mise -C tools/web exec -- npm run dev -- --port=8903
```

Browser tests use `/opt/google/chrome/chrome` or `WEB_TEST_BROWSER`; they skip when the browser is unavailable. WASM
build prerequisites and standalone targets belong to the [WASM README](../wasm/README.md#build).

## Latest iteration preview

Run `just preview-build` after rendering or preset changes. The
[generator selection rules](../generator/CONTRACT.md#generation-selection) determine active and comparison packages;
current approved/candidate identities are listed in the [revision index](../../docs/revisions/001/README.md#iterations).

On the index, select a font, size, axes and text preset, or enter custom text. Font details offer source-kerning
inspection. Symbol comparison routes show native differences for changed glyphs.
[Interactive requirements](CONTRACT.md#interactive-specimens) define controls, persistence, display and unavailable
states.

## Configure presets

Edit `cards` in [specimens.json](../generator/specimens.json), then rebuild. Use the
[card configuration guide](../generator/README.md#configure-preview-cards); preset text is imported from that
configuration.

## Live spacing control

Use **Spacing (px)**, **Spacing model** and **Kerning** to compare placement at the same font, size, axes and text. Use
**Display scale** and optional **Pixel-accurate display** to inspect physical-pixel magnification. UI behavior is
defined in the [web contract](CONTRACT.md#interactive-spacing); numerical tracking policy belongs to the
[generator API](../generator/README.md#tracking-policy), and model decisions/assessment belong to the
[iteration records](../../docs/revisions/001/README.md#iterations).

See [Spacing models](../../docs/spacing-models.md) for a comparison of the choices, kerning, tracking and saved
preferences.

## Source layout

```text
tools/web/
  pages/       HTML and Nunjucks templates
  assets/      Browser CSS and JavaScript
  lib/         Content import and validation
  tests/       Import, template and HTTP/browser checks
```
