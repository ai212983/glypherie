# YinYang oriented engine (experimental Rust/WASM runtime)

<!-- cspell:words rustfft bindgen rustup yinyang predeclared -->

Experimental Rust port of the frozen YinYang oriented-field stages plus the
corrected SCORE-v2 interpreter, with a Node/browser WASM target. No maintained
crate depends on this; the reviewed page is untouched by this leaf.

## Setup

```sh
rustup target add wasm32-unknown-unknown   # once; WASM only
cargo build --manifest-path experiments/contextual_spacing/oriented_engine/Cargo.toml
```

`cargo` fetches pinned crates into this leaf's own `Cargo.lock`; no global install.

## Commands

```sh
# Native parity vs the frozen Python corrected corpus (writes under out/...):
python3 experiments/contextual_spacing/oriented_engine/reference_adapter.py \
  out/diagnostics/contextual-spacing/yinyang-browser-integration/runtime/adapter
cargo run --manifest-path experiments/contextual_spacing/oriented_engine/Cargo.toml \
  --bin parity -- ADAPTER_DIR
cargo test --manifest-path experiments/contextual_spacing/oriented_engine/Cargo.toml

# WASM build (browser ESM + Node CJS packages under oriented_engine/pkg-*):
sh experiments/contextual_spacing/oriented_engine/build-wasm.sh web
sh experiments/contextual_spacing/oriented_engine/build-wasm.sh nodejs
node experiments/contextual_spacing/oriented_engine/smoke/parity_node.mjs ADAPTER_DIR

# Benchmark TRUE workload (86 pairs x 5 candidates, cold + cohesion re-derive):
cargo run --manifest-path experiments/contextual_spacing/oriented_engine/Cargo.toml \
  --release --bin bench -- ADAPTER_DIR
```

## Layout

- `src/`: `lib.rs` (`params`, `fft`, `bessel`, `fields`, `score`, `engine`,
  `capture`), `bindings.rs` (`wasm` feature), `bin/parity.rs`, `bin/bench.rs`.
- `reference_adapter.py`: separate harness importing the frozen modules
  read-only; dumps covers, metrics and expected `G2` for the parity corpus.
- `smoke/parity_node.mjs`: Node check of the built WASM package vs adapter.
- `build-wasm.sh`: `cargo build --locked` + `wasm-bindgen 0.2.129`.
- `CONTRACT.md`: predeclared API, cache, validation and perf gates.
