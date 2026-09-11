# font_generator

Host-side font research and glyph generation, extracted from the
Meditamer firmware working tree into its own repository. No firmware
build depends on anything here; the production LVGL font compiler
stays with the firmware.

## Layout

- `tools/font_generator/` — standalone Rust crate: configurable glyph
  generation from outline fonts, JSON command-line adapter.
  See `tools/font_generator/README.md`.
- `tools/font_probe/` — measurement and panel-specimen experiments.
  See `tools/font_probe/README.md`.
- `assets/fonts/` — test input faces only (IBM Plex Sans Variable,
  Ark Pixel 16px, plus OFL texts), pinned by SHA-256 in the example
  job files. These are copies for standalone testing, not firmware
  build inputs.
- `docs/` — the font legibility plan, methodology reference, and
  experiment notes, copied over with the tooling.

## Reproduce the calibration outputs

```bash
mkdir -p tools/font_generator/out
cargo +stable run --locked --manifest-path tools/font_generator/Cargo.toml -- \
  tools/font_generator/examples/roboto.json tools/font_generator/out/roboto-glyphs.json
cargo +stable test --locked --manifest-path tools/font_generator/Cargo.toml
```

## Provenance

Font sources, licenses, and expected SHA-256 hashes are declared in
each `tools/font_generator/examples/*.json` job file; the generator
verifies font bytes, not legal provenance. Per-face embedded
name-table readings are recorded in
`tools/font_generator/README.md`.
