# Stem fitting comparison

<!-- cspell:words Skrifa unhinted -->

Diagnostic comparing the default font-instruction-first Mono policy and registry Skrifa's forced Mono autohinter using
the same candidate raster and source linear advances. It returns to the uneven-stem concern described in
[iteration 001.03](../../docs/revisions/001/03-spacing-kerning.md#binary-stem-weight-and-source-phase). This comparison
covers only the two Mono runtime strategies. Classified findings are recorded in the iteration; see
[experiment guidance](../AGENTS.md).

From the repository root:

```sh
cargo run --locked --manifest-path tools/generator/Cargo.toml --example stem_fitting_compare -- \
  out/diagnostics/stem-fitting/captures.json
python experiments/stem_policy_comparison/view.py out/diagnostics/stem-fitting/captures.json \
  out/diagnostics/stem-fitting/web
python -m http.server 8905 --bind 127.0.0.1 --directory out/diagnostics/stem-fitting/web
```

Configuration: the isolated matrix covers Roboto at 13–16 px and Roboto Italic, Source Sans 3, Literata and slanted
Roboto Flex at 14 px, all at weight 400. Each captures `m/u/t/A/v/o`, effective axes, source identity, unhinted source
geometry, independent upstream Mono geometry, and both candidate strategies' fitted outlines, coverage and final
bitmaps. No specimen selections or active publication pointers are written. Both fitting columns use the same
coverage/overlap/dropout implementation; the source capture is a separate unhinted geometry control.
