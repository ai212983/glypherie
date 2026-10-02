# Web

Eleventy site builder and HTTP preview for exported font specimens and glyph comparisons. Builds write to `out/web/`.
See [CONTRACT.md](CONTRACT.md) for content and presentation requirements.

## Setup

From the repository root, using [mise](https://mise.jdx.dev/):

```sh
mise install --locked just
just web-setup
```

## Commands

```sh
just web        # Build the static site
just web-watch  # Rebuild when sources change
just web-test   # Run tests
```

To build, watch, and serve existing exports over HTTP:

```sh
mise -C tools/web exec -- npm run dev -- --port=8903
```

## Latest iteration preview

The index `/` always shows the latest iteration of the latest revision, selected numerically from published package
versions. Its comparison is always with the preceding revision's latest iteration; if there is no preceding revision,
compare with reference. Currently this means `001.01` versus reference. A stale active pointer or preview environment
variable cannot select an older iteration on the index. Missing or stale comparison content fails the build.

Use `just preview-build` to regenerate specimens, comparisons, and the index together. Changed symbols open aligned
previous/current/difference pages. All visual communication goes through the web. There is no separate `/reviews/`
folder or endpoint; rebuilding removes obsolete review output.

Each marked family/size section of the index shows its own **Attention** card, grouping that section's symbols by
inspection type, with an optional short hint for each symbol. Sections without marks show no card. Marks are configured
in [attention.json](../generator/attention.json); see the [evaluation guide](../../docs/evaluation.md#attention-card).
Exact marked cases move out of Changed symbols and remain reviewable even when their images match reference. Attention
uses the same published preview scope; debug sizes or axes are rejected, not rendered. Clicking a mark opens its
existing symbol page at the exact case with reference/current/difference images.

## Source layout

```text
tools/web/
  pages/       HTML and Nunjucks templates
  assets/      Browser CSS and JavaScript
  lib/         Content import and validation
  tests/       Import, template, and HTTP/browser checks
```

`just web` reads manifests and PNG images from `out/specimens/` and copies imported content into `out/web/content/`. See
the [specimen generator contract](../generator/CONTRACT.md) for the input format.

Main-page sample cards are configured in the `cards` array of [specimens.json](../generator/specimens.json), using `id`,
`title`, and `content`. See the [card configuration guide](../generator/README.md#configure-preview-cards). Run `just
preview-build` after edits to update the rendered text. Character coverage and changed symbols are generated
automatically.

Browser tests use `/opt/google/chrome/chrome` or the executable specified by `WEB_TEST_BROWSER`; they skip when the
browser is unavailable.
