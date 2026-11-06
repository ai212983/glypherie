<!-- cspell:words findedges fontforge -->

# FontForge reference fixtures

`native.json` retains source and fitted curve commands for four font instances, exact input scaling, native envelopes
and all ordered pair estimates. It was captured directly by the pinned upstream `aw2_findedges` and
`aw2_bbox_separation` C functions, not by the Rust implementation or Python envelope estimator. Native compilation uses
separate binary64 operations (`-ffp-contract=off -fno-fast-math`); this does not claim default-toolchain binary parity.
The retained identity pins the upstream revision, source, driver and executable hashes.

Regenerate from the repository root after building the pinned native reference driver:

```sh
python3 crates/generator/tests/fontforge/capture.py \
  --native out/diagnostics/contextual-spacing/reference/fontforge-build/bin/contextual-spacing-native-capture \
  --identity out/diagnostics/contextual-spacing/reference/native-build-identity.json \
  --captures out/diagnostics/contextual-spacing/preset-preview/captures \
  --output crates/generator/tests/fontforge/native.json
cargo test --locked --manifest-path crates/generator/Cargo.toml --lib kerning::fontforge::
```

The native estimator fixture does not validate the project's source-relative target or feasibility adaptations. Their
scope belongs to the
[kerning design](../../../../docs/designs/text-layout/contextual-spacing-and-healing.md#interchangeable-kerning-methods).
