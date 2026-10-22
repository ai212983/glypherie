# WASM timing controls

<!-- cspell:words bindgen BINDGEN reassoc -->

Run from the repository root with Node 24 and the web app's installed dependencies. The experiment consumes the frozen
packages in `out/diagnostics/qp-objective-optimization/`; it does not rebuild or stage a renderer. Identity commands use
the dense, sparse and identity package snapshots in `out/diagnostics/font-identity-optimization/`.

```sh
node experiments/wasm_timing/node-matrix.cjs default
node experiments/wasm_timing/node-matrix.cjs fixed
node experiments/wasm_timing/node-matrix.cjs legacy
node experiments/wasm_timing/legacy-replay.cjs
node experiments/wasm_timing/browser.cjs
node experiments/wasm_timing/browser.cjs fixed
python3 experiments/wasm_timing/summarize.py
COMPARE_SHARD=0 COMPARE_SHARDS=6 node experiments/wasm_timing/identity-parity.cjs
python3 experiments/wasm_timing/identity-benchmarks.py
python3 experiments/wasm_timing/identity-summary.py
```

`REPEATS` and `WARMUPS` override 12 measured pairs and three warm-up pairs. `ROUNDS` overrides three default-engine or
two fixed-tier rounds. `WEB_TEST_BROWSER` selects Chrome; the default is the macOS Google Chrome application.
`CASE_FILTER=pangram` limits a run to that specimen. Legacy mode uses the preceding benchmark's loader/order and
defaults to one warm-up, 15 measured pairs and six rounds. Results are written beneath
`out/diagnostics/wasm-timing-investigation/`.

For browser comparisons, `BASELINE_WEB_PACKAGE` and `CANDIDATE_WEB_PACKAGE` select package directories; the historical
label `sparse` denotes the selected candidate package. `OUTPUT_DIR` isolates a new result directory, `COMPARISONS=AB`
selects only baseline/candidate runs, and `VARIED_REQUESTS=1` cycles sizes 12/16/20/24, weights 300/400/700 and Roboto
widths 75/90/100 between paired requests. Each side of a pair receives the same settings.

`COMPARE_OUTPUT_DIFFERENCES=1` records cross-package output differences in each browser result instead of requiring
identity between packages. Repeated output within each package must still be deterministic. Omit this option for normal
identity-gated timing; it is intended for diagnostic arithmetic experiments whose output may change.

`identity-parity.cjs` also accepts `PARITY_OUTPUT_DIR` and `PARITY_PACKAGES` (a JSON object mapping `dense` and
`identity` to package directories) for a two-package comparison with the same matrix and assertions.

`identity-summary.py` accepts `SUMMARY_OUTPUT_DIR` and a comma-separated `SUMMARY_SUITES` list to summarize another
experiment's browser results with the same paired-session statistics. Omitting them retains the identity experiment.

## Standard SIMD build experiment

Use a fresh `out/diagnostics/wasm-simd-optimization/` directory. Freeze the current web and Node preview packages there
as `pkg-web-before/` and `pkg-nodejs-before/` before building. The isolated build commands use locked dependencies and
the current generator sources; output package directories are preserved once created.

```sh
python3 experiments/wasm_timing/simd-build.py scalar
python3 experiments/wasm_timing/simd-build.py simd
python3 experiments/wasm_timing/simd-inspect.py scalar
python3 experiments/wasm_timing/simd-inspect.py simd
python3 experiments/wasm_timing/simd-capture.py scalar
python3 experiments/wasm_timing/simd-capture.py simd
python3 experiments/wasm_timing/simd-capture.py run
python3 experiments/wasm_timing/simd-capture.py compare
```

`WASM_BINDGEN` overrides the CLI path, defaulting to `/tmp/font-generator-wasm-tools/bin/wasm-bindgen`. LLVM tools use
`/opt/homebrew/opt/llvm/bin/`. `simd-build.py` writes separate `pkg-web-scalar/`, `pkg-web-simd/` and matching Node
packages. `simd-inspect.py` counts vector instructions by function and rejects relaxed SIMD instructions.

The capture adapter calls the generator API through a diagnostic WASM interface and compares complete scalar/SIMD
reports separately from actual delivery-package checks. It also records native-reference differences rather than
requiring native and WASM diagnostic reports to match. `SIMD_NATIVE_REFERENCE_DIR` selects a directory containing
`source-before.json` and six `captures-before-N.jsonl` native shards; it defaults to
`out/diagnostics/interval-diagnostics-optimization/`. All referenced generator file hashes must match the current
source. `run` captures and compares; `compare` reuses existing captures. Use the package/summary environment variables
above for browser and delivery comparisons. The
[owning study](../../docs/hobby-fitting.md#standard-wasm-simd-experiment) defines scope and adoption criteria;
maintained SIMD build commands are in the [WASM README](../../tools/wasm/README.md#build).

## Fast-math experiment

Use a fresh `out/diagnostics/fast-math-optimization/` directory with the current standard SIMD web and Node packages
frozen as `pkg-web-app/` and `pkg-nodejs-app/`. Requires the same Rust/Node/bindings tools as above and LLVM 23.1.0
`opt`/`llc` at `/opt/homebrew/opt/llvm/bin/`. The linker uses the current Rust toolchain's bundled linker. The
[owning study](../../docs/hobby-fitting.md#global-fast-math-experiment) defines the experiment's numerical boundary.

```sh
python3 experiments/wasm_timing/fast-math.py strict
python3 experiments/wasm_timing/fast-math.py fast
COMPARE_SHARD=0 COMPARE_SHARDS=6 node experiments/wasm_timing/fast-math-compare.cjs
```

Run the comparison for shards 0–5. The strict build emits and preserves a merged Rust module and complete link inputs;
both modes run the same external LLVM optimization/code generation. Only fast mode adds the documented fast flags to
floating arithmetic/comparisons, direct floating-return calls and floating selection/merge instructions. It leaves
integer operations and separately compiled C objects unchanged. This is a diagnostic pipeline, not a supported app build
flag. Package creation refuses to overwrite a frozen package.

For browser timing, select `pkg-web-strict/` and `pkg-web-fast/` with the package variables above, set
`COMPARE_OUTPUT_DIFFERENCES=1` and isolate each suite with `OUTPUT_DIR`. Also compare `pkg-web-app/` against
`pkg-web-strict/` to measure pipeline effects separately. Identical-build controls should keep the default identity
gate.

Create the static visual-review packet from the frozen delivery packages and six delivery comparison shards:

```sh
COMPARE_SHARD=0 node experiments/wasm_timing/fast-math-review.cjs
node experiments/wasm_timing/fast-math-review.cjs assemble
python3 -m http.server --bind 127.0.0.1 --directory out/diagnostics/fast-math-optimization/review-v1 58953
```

Run the capture command for shards 0–5 before assembling. Existing captures and review packets are preserved. The page
supports `family`, `size`, `weight`, `fitting`, `scanner`, `zoom` and `overlay=1` query settings; defaults show both
fonts at 16 px, weight 400, font hints enabled, FreeType Mono and 8× detail enlargement. The review is separate from app
staging and publication.

## Selective solver arithmetic experiment

Requires the fast-math tools above and the frozen `pkg-web-app/` and `pkg-nodejs-app/` control packages from that
experiment. Use a fresh `out/diagnostics/selective-math-optimization/` directory. The
[owning study](../../docs/hobby-fitting.md#selective-solver-arithmetic-experiment) defines the arithmetic boundary.

```sh
mkdir -p out/diagnostics/selective-math-optimization
python3 experiments/wasm_timing/selective-math.py prepare
python3 experiments/wasm_timing/selective-math.py probe
python3 experiments/wasm_timing/selective-math.py strict
python3 experiments/wasm_timing/selective-math.py fast
MATH_OUTPUT_DIR="$PWD/out/diagnostics/selective-math-optimization" \
  COMPARE_SHARD=0 COMPARE_SHARDS=6 node experiments/wasm_timing/fast-math-compare.cjs
```

Run delivery shards 0–5. Preparation copies the generator/WASM sources and vendors into the output directory, inserts
the experimental solve there and preserves a source manifest. It never edits maintained runtime. The probe checks the
compiled arithmetic against an exact rational oracle and exercises strict compensation and guard abstentions.

`MATH_OUTPUT_DIR` selects another output directory for `fast-math.py` and the delivery comparison; `MATH_SOURCE_ROOT`
selects an isolated build tree. `MATH_KERNEL` restricts inserted permissions to `reassoc` on additions/multiplications
in one named function. Omit it for the historical broad fast-math diagnostic. `MATH_AUDIT_PREFIX` prefixes the selected
function audit filename. Browser comparisons use the same package and output variables described above and keep the
default output-identity gate for this experiment.

## Completed diagonal-fit reuse

Use a fresh `out/diagnostics/glyph-reuse-optimization/` directory. Freeze ordinary standard-SIMD web and Node packages
there as `pkg-web-app/` and `pkg-nodejs-app/`. Requires the locked native/WASM toolchains above and LLVM's WASM archive
tools in `/opt/homebrew/opt/llvm/bin/`. The
[owning study](../../docs/hobby-fitting.md#completed-diagonal-fit-reuse-experiment) defines scope and adoption gates.

```sh
python3 experiments/wasm_timing/glyph-reuse.py census
python3 experiments/wasm_timing/glyph-reuse.py stats
python3 experiments/wasm_timing/glyph-reuse.py cache
```

The census and statistics commands use separate source copies and native diagnostic binaries. The cache build uses the
current implementation with ordinary standard SIMD and writes isolated web/Node packages. Existing source snapshots and
packages are preserved. `WASM_BINDGEN` selects the pinned bindings CLI.

`fast-math-compare.cjs` accepts `MATH_PACKAGES`, a JSON object mapping `app` and candidate labels to Node package
directories, to run its delivery matrix against arbitrary frozen packages. `MATH_OUTPUT_DIR` selects its result
directory. Run all six shards as described above.

`INTERACTION_REPLAY=1` selects scripted editing cases in `browser.cjs`: repeat, resize, spacing, append/delete text,
kerning, new/revisited weights and sizes, and color. New settings are unique throughout warm-up and measurement;
repeat/revisit cases intentionally measure retained fitting. Cases run as separate paired blocks through the actual app
worker. They measure worker rendering and message round-trip time, not mounted UI events or typing debounce.
`CASE_FILTER` can select one interaction; the usual package/output/repeat/order options still apply.
