# Hu/Hersch reference fixtures

`full-fitted.json` contains the complete retained input geometry, bitmap cells, source metrics and independent Python
results for Literata, Roboto, Roboto Flex and Source Sans 3 at 16 px. The fixture records font/capture identities, axes
and SHA-256 identities of the Python source files. It covers all 11,216 supported ordered ASCII class pairs, including
the experimental proportional-digit class. Tabular preservation is disabled only in this numerical fixture.

The reference invocation is `HuDensityModel(capture, 64, candidate_geometry="fitted_outline",
construction_policy="full_outline", target_policy="source_origin")`. It uses the unmodified experiment implementation of
the published [Hu/Hersch transformations](https://patents.google.com/patent/US5768490A/en), followed by the experiment's
signed adjustment rounding and `clearance_min_step_no_overlap` bitmap safeguard. This establishes parity with the
declared experiment adaptation, not original-author implementation parity or optical acceptance. Gray's continuous
feasibility adapter has separate analytic and dense-oracle tests and is not represented as Python bitmap parity.

Run the maintained checks from the repository root:

```sh
cargo test --locked --manifest-path crates/generator/Cargo.toml --lib kerning::hu_hersch
cargo test --locked --manifest-path crates/generator/Cargo.toml --lib kerning::outline
```

The original reference inputs came from `out/diagnostics/contextual-spacing/preset-preview/captures/`. They are fully
embedded in the fixture so the Rust tests require neither those diagnostics nor Python or experiment imports.
