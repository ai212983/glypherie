# Hobby geometric prototype

<!-- cspell:words Hobby's NumPy strokestyles fonttools itfl Inhkyxzv CGAL MPFR -->

Isolated research prototypes and diagnostics for the coupled geometric system described in the
[Hobby fitting model](../../docs/hobby-fitting.md). The
[equation audit](../../docs/references/papers/1993-hobby/audit.md) records checked notation, report-version
discrepancies and remaining source uncertainties. See [experiment guidance](../AGENTS.md) for placement and verification
routing.

## Run

Compose a text comparison from the existing frozen joint and attached-diagonal packets:

```sh
python3 experiments/hobby_fitting/combined_text_review.py \
  --out out/diagnostics/combined-stroke-text/review
python3 -m http.server --bind 127.0.0.1 --directory out/diagnostics/combined-stroke-text/review 8126
```

The output directory must not already exist. Optional `--combined` and `--joint` paths select the input packet roots.

Assess source and fitted crossing geometry from those packets, with independent variable-font outlines:

```sh
uv run --with fonttools==4.53.1 python experiments/hobby_fitting/crossing_assessment.py \
  --out out/diagnostics/source-sans-crossings/review
python3 -m unittest experiments.hobby_fitting.tests.test_crossing_assessment
python3 -m http.server --bind 127.0.0.1 --directory out/diagnostics/source-sans-crossings/review 8127
```

This output directory must also be new; the native adapter and frozen comparison packets must already exist.

Python 3.12 and the pinned NumPy dependency in [requirements.txt](requirements.txt) suffice. From the repository root,
with `uv`:

```sh
uv run --with-requirements experiments/hobby_fitting/requirements.txt python experiments/hobby_fitting/prototype.py
uv run --with-requirements experiments/hobby_fitting/requirements.txt python -m unittest discover -s experiments/hobby_fitting/tests -p 'test_*.py'
```

The first command emits diagnostic JSON with source/projected widths, relative width errors, movement, rank and squared
residuals by group. Redirect it to an ignored location such as `out/diagnostics/hobby-prototype.json` to retain a run.
It does not produce specimen packages or publish a preview.

## Direct diagonal evaluation

The explicit opt-in evaluator lives in [direct_diagonal_run.py](direct_diagonal_run.py); design in
[docs/hobby-fitting.md](../../docs/hobby-fitting.md#direct-diagonal-grid-fitting-experiment). Default runs are identity
controls (upstream render only, no solver import); `--enable-direct-diagonals` adds the width-only and grid arms:

```sh
CARGO_TARGET_DIR=crates/generator/target cargo build --locked --offline \
  --manifest-path experiments/strokestyles_fitting/native/Cargo.toml
mkdir -p out/diagnostics/direct-diagonal
crates/generator/target/debug/strokestyles-fit-adapter capture \
  --font fonts/Roboto.ttf --size 16 --axes '{"wght":400,"wdth":100}' \
  --chars itflInhkyxzvAVW --out out/diagnostics/direct-diagonal/captures.json
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 \
  python3 experiments/hobby_fitting/direct_diagonal_run.py \
  --captures out/diagnostics/direct-diagonal/captures.json \
  --out out/diagnostics/direct-diagonal/run-01
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 \
  python3 experiments/hobby_fitting/direct_diagonal_run.py \
  --captures out/diagnostics/direct-diagonal/captures.json \
  --out out/diagnostics/direct-diagonal/run-01-enabled --enable-direct-diagonals
python3 -m http.server --directory out/diagnostics/direct-diagonal/run-01-enabled 8123
```

The capture CLI writes one case object; the evaluator also accepts that single object directly (it wraps it into a
one-case list).

Exact-join checking needs the CGAL 6.1.1 headers plus a Boost/GMP/MPFR/CMake toolchain (no global install; verify the
archive hash before unpacking):

```sh
curl --fail --location -o /tmp/CGAL-6.1.1.tar.xz \
  https://github.com/CGAL/cgal/releases/download/v6.1.1/CGAL-6.1.1.tar.xz
echo '52506935f70e247ed2777e3c65f20e86f79208c2a2d0e180ae7475daf11c96ef  /tmp/CGAL-6.1.1.tar.xz' | shasum -a 256 -c -
mkdir -p out/diagnostics/direct-diagonal/exact-topology/reference
tar -xJf /tmp/CGAL-6.1.1.tar.xz -C out/diagnostics/direct-diagonal/exact-topology/reference
CGAL_DIR=$PWD/out/diagnostics/direct-diagonal/exact-topology/reference/CGAL-6.1.1/lib/cmake/CGAL \
  CMAKE_PREFIX_PATH=/opt/homebrew \
  sh experiments/hobby_fitting/exact_topology/build.sh
```

Standalone exact-join comparison of existing captures (optional; needs the enabled run and the built helper):

```sh
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 \
  python3 experiments/hobby_fitting/direct_diagonal_run.py \
  --captures out/diagnostics/direct-diagonal/captures.json \
  --out out/diagnostics/direct-diagonal/joins-evaluation \
  --enable-direct-diagonals --exact-joins \
  --topology-binary out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology
python3 -m http.server --directory out/diagnostics/direct-diagonal/joins-evaluation 8124
```

Open [http://localhost:8124/index.html](http://localhost:8124/index.html) for the exact-join comparison.

Text-level width-only review (frozen donors, ASCII repertoire, exact native layout required):

```sh
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 \
  python3 experiments/hobby_fitting/text_review.py \
  --captures out/diagnostics/direct-diagonal/captures.json \
  --out out/diagnostics/direct-diagonal/text-review \
  --adapter crates/generator/target/debug/strokestyles-fit-adapter \
  --topology-binary out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology
python3 -m http.server --directory out/diagnostics/direct-diagonal/text-review 8125
```

Reduced smoke (one config, full pipeline including native layout):

```sh
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 \
  python3 experiments/hobby_fitting/text_review.py \
  --captures out/diagnostics/direct-diagonal/captures.json \
  --out out/diagnostics/direct-diagonal/text-review-smoke \
  --family Roboto --size 16 --weight 400
python3 -m unittest discover -s experiments/hobby_fitting/tests -p 'test_text_review.py'
```

Resume an interrupted full run (validated hint cells are recomposed, missing configs run fresh):

```sh
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 \
  python3 experiments/hobby_fitting/text_review.py \
  --captures out/diagnostics/direct-diagonal/captures.json \
  --out out/diagnostics/direct-diagonal/text-review \
  --adapter crates/generator/target/debug/strokestyles-fit-adapter \
  --topology-binary out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology \
  --resume
```

Border-interval coverage review (upstream, frozen width-only and candidate arms):

```sh
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 \
  python3 experiments/hobby_fitting/coverage_review.py \
  --family Roboto --size 16 --weight 400 \
  --out out/diagnostics/direct-diagonal/coverage-review \
  --adapter crates/generator/target/debug/strokestyles-fit-adapter \
  --topology-binary out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology
python3 -m http.server --directory out/diagnostics/direct-diagonal/coverage-review 8126
```

The full matrix repeats the frozen 72 hint cells and ASCII repertoire from `text-review` without rewriting it;
`--family`, `--size` and `--weight` stage one config and `--resume` reuses validated coverage cells. Focused harness
tests:

```sh
python3 -m unittest discover -s experiments/hobby_fitting/tests -p 'test_coverage_review.py'
```

Open [http://localhost:8123/index.html](http://localhost:8123/index.html) to review source/upstream/width-only/grid
canvases with mechanical metrics. Unit wiring tests use a synthetic fake core only:

```sh
python3 -m unittest discover -s experiments/hobby_fitting/tests -p 'test_direct_diagonal_run.py'
```

## Native port parity

The native check consumes the existing `coverage-review/cells` and `text-review/ascii-captures` packets under
`out/diagnostics/direct-diagonal/`:

```sh
CARGO_TARGET_DIR=crates/generator/target cargo build --release --locked --offline \
  --manifest-path experiments/strokestyles_fitting/native/Cargo.toml --example diagonal_parity
python3 experiments/hobby_fitting/native_parity.py \
  --binary crates/generator/target/release/examples/diagonal_parity
cargo test --manifest-path crates/generator/Cargo.toml --test diagonal_parity
```

`--focus` selects default Roboto in both hint modes. `--out` overrides the default
`out/diagnostics/direct-diagonal/native-port-verification/` output directory. The
[fitting design](../../docs/hobby-fitting.md#native-width-only-adoption) owns the verification gates.

## Shape balance comparison

Uses the frozen coverage-review cells and matching ASCII captures above. Design and assessment:
[symmetry placement and curved-stroke study](../../docs/hobby-fitting.md#symmetry-placement-and-curved-stroke-study).

```sh
python3 experiments/hobby_fitting/shape_balance_review.py --focus --curves \
  --out out/diagnostics/shape-balance-review
python3 experiments/hobby_fitting/shape_balance_review.py --curves \
  --out out/diagnostics/shape-balance-review
python3 -m unittest experiments.hobby_fitting.tests.test_symmetry_placement \
  experiments.hobby_fitting.tests.test_curved_width \
  experiments.hobby_fitting.tests.test_curve_contacts \
  experiments.hobby_fitting.tests.test_shape_balance_review
python3 -m http.server 8127 --directory out/diagnostics/shape-balance-review
```

`--focus` selects Roboto 400/16 in both hint modes; omission selects the full matrix. `--placement-arm strict-quantum`
selects the strict symmetry control instead of the experimental `phase-range` arm. Omit `--curves` for three arms.
`--resume` reuses cells only when their inputs, code, binary and content hashes match. `--adapter` and
`--topology-binary` select the local adapter and independent topology checker.

## Joint fitting comparison

Uses the same frozen coverage cells and ASCII captures. Model scope and assessment:
[joint placement and smooth curves](../../docs/hobby-fitting.md#joint-placement-and-smooth-curve-continuation).

```sh
python3 experiments/hobby_fitting/joint_review.py --model diagonal --matrix \
  --out out/diagnostics/shape-balance-next/diagonal-matrix
python3 experiments/hobby_fitting/joint_review.py --model curve --matrix --jobs 8 \
  --out out/diagnostics/shape-balance-next/curve-matrix-scoped
python3 experiments/hobby_fitting/joint_comparison.py \
  out/diagnostics/shape-balance-next/diagonal-matrix \
  out/diagnostics/shape-balance-next/curve-matrix-scoped \
  --out out/diagnostics/shape-balance-next/review
```

Omit `--matrix` to select one cell with `--family`, `--size`, `--weight` and `--hint`. `--glyphs` restricts diagnostic
probes; other text glyphs retain the preferred packet. `--jobs` bounds concurrent cell processes. The combiner requires
both complete matrices, matching source/layout records and current input hashes.

## Attached diagonal comparison

The [owning study](../../docs/hobby-fitting.md#attached-diagonal-and-curve-constraints) uses the existing captures,
upright references and preceding joint comparison packets:

```sh
uv venv out/diagnostics/attached-diagonal/venv --python 3.14
uv pip install --python out/diagnostics/attached-diagonal/venv/bin/python \
  -r experiments/hobby_fitting/requirements.txt
out/diagnostics/attached-diagonal/venv/bin/python experiments/hobby_fitting/attached_review.py \
  --out out/diagnostics/attached-diagonal/default
out/diagnostics/attached-diagonal/venv/bin/python experiments/hobby_fitting/attached_review.py --matrix --jobs 8 \
  --out out/diagnostics/attached-diagonal/review
python3 -m http.server --bind 127.0.0.1 --directory out/diagnostics/attached-diagonal/review 8128
```

## Curved crossing comparison

The [owning study](../../docs/hobby-fitting.md#curved-crossing-prototype) reuses the frozen attached-diagonal packet and
native captures, with independently instantiated source outlines:

```sh
uv venv out/diagnostics/curved-crossing/venv --python 3.14
uv pip install --python out/diagnostics/curved-crossing/venv/bin/python \
  -r experiments/hobby_fitting/requirements.txt fonttools==4.53.1
out/diagnostics/curved-crossing/venv/bin/python -m unittest experiments.hobby_fitting.tests.test_curved_crossing
out/diagnostics/curved-crossing/venv/bin/python experiments/hobby_fitting/curved_crossing_review.py \
  --family SourceSans3 --weight 400 --size 16 --hint selective_default --glyphs xX \
  --out out/diagnostics/curved-crossing/default
out/diagnostics/curved-crossing/venv/bin/python experiments/hobby_fitting/curved_crossing_review.py \
  --matrix --jobs 4 --out out/diagnostics/curved-crossing/review
python3 -m http.server --bind 127.0.0.1 --directory out/diagnostics/curved-crossing/review 8129
```

Omit `--glyphs` to evaluate all ASCII glyphs in a cell. `--jobs` limits concurrent cell processes.

## Curve candidate ordering census

The native capture adapter also accepts `CAPTURE_OUTPUT_DIR` to select another experiment directory. Freeze its `before`
executable before changing maintained source, then build `after` from that experiment's prototype.

Curve candidate ordering census:

```sh
python3 experiments/hobby_fitting/curve_ordering_census.py
CAPTURE_OUTPUT_DIR=out/diagnostics/curve-ordering-optimization python3 experiments/hobby_fitting/stage_capture.py build-before
CAPTURE_OUTPUT_DIR=out/diagnostics/curve-ordering-optimization python3 experiments/hobby_fitting/stage_capture.py before
CAPTURE_OUTPUT_DIR=out/diagnostics/curve-ordering-optimization python3 experiments/hobby_fitting/stage_capture.py build-after
CAPTURE_OUTPUT_DIR=out/diagnostics/curve-ordering-optimization python3 experiments/hobby_fitting/stage_capture.py after
CAPTURE_OUTPUT_DIR=out/diagnostics/curve-ordering-optimization python3 experiments/hobby_fitting/stage_capture.py compare
```

## Stage prerequisite census

Run the diagnostic copy and capture commands from the repository root. Freeze `before` before changing the renderer;
build and capture `after` from the prototype. The generated Cargo adapters resolve pinned dependencies offline and write
under `out/diagnostics/stage-eligibility-optimization/`.

```sh
python3 experiments/hobby_fitting/stage_census.py
python3 experiments/hobby_fitting/stage_capture.py build-before
python3 experiments/hobby_fitting/stage_capture.py before
python3 experiments/hobby_fitting/stage_capture.py build-after
python3 experiments/hobby_fitting/stage_capture.py after
python3 experiments/hobby_fitting/stage_capture.py compare
```

Existing frozen capture executables are preserved; capture and comparison commands reuse them.

## Certificate duplicate census

Certificate duplicate census (native diagnostic copy, Cargo dependencies resolved offline):

```sh
python3 experiments/hobby_fitting/certificate_census.py
```

The command consumes current generator sources and writes its isolated build and results beneath
`out/diagnostics/certificate-reuse-optimization/`. An existing instrumented copy is reused when rerunning.

## Terminal reference-height comparison

The [owning study](../../docs/hobby-fitting.md#terminal-reference-height-constraints) reuses the frozen curved-crossing
packet, native captures and upright references. Use the pinned curved-crossing environment above:

```sh
out/diagnostics/curved-crossing/venv/bin/python -m unittest experiments.hobby_fitting.tests.test_terminal_fitting
out/diagnostics/curved-crossing/venv/bin/python experiments/hobby_fitting/terminal_fitting_review.py \
  --family SourceSans3 --weight 400 --size 16 --hint selective_default --glyphs Ay \
  --out out/diagnostics/terminal-fitting/default
out/diagnostics/curved-crossing/venv/bin/python experiments/hobby_fitting/terminal_fitting_review.py \
  --matrix --jobs 4 --out out/diagnostics/terminal-fitting/review
python3 -m http.server --bind 127.0.0.1 --directory out/diagnostics/terminal-fitting/review 8130
```

## Interval diagnostic allocation experiment

From the repository root, freeze the current `intervals.rs` and `curve_model.rs` under
`out/diagnostics/interval-diagnostics-optimization/before/`, then run the census before changing runtime sources. The
commands create isolated Cargo adapters with offline dependency resolution. Existing instrumented copies are preserved;
select a new label for a new capture.

```sh
python3 experiments/hobby_fitting/interval_allocation_census.py
CENSUS_LABEL=after python3 experiments/hobby_fitting/interval_allocation_census.py
python3 experiments/hobby_fitting/interval_diagnostic_replay.py \
  out/diagnostics/medial-interval-optimization/queries.json
```

`CENSUS_LABEL` defaults to `before`; it labels the current source capture and does not select an implementation. Run
`after` with the prototype sources installed. The replay defaults to the archived `candidate-source/intervals.rs`; an
optional second argument selects another candidate file. It consumes an explicit JSON query capture containing
normalized pair setups, competitors and fill loops. Capture adapters and results are written beneath
`out/diagnostics/interval-diagnostics-optimization/`. The
[owning study](../../docs/hobby-fitting.md#interval-search-diagnostic-allocation-experiment) defines inputs and decision
criteria. Use `CAPTURE_OUTPUT_DIR` with `stage_capture.py` for full native comparisons.

## Equality-event census

Freeze `crates/generator/src/diagonal_fitting/intervals.rs` as
`out/diagnostics/equality-filter-optimization/before/intervals.rs`, then supply an explicit normalized-query JSON
capture:

```sh
python3 experiments/hobby_fitting/equality_filter_census.py \
  out/diagnostics/medial-interval-optimization/queries.json
```

The adapter resolves Cargo dependencies offline and writes generated sources, per-query counters and a summary beneath
`out/diagnostics/equality-filter-optimization/`. Existing census sources are preserved. Query rows contain `cell` and
`queries`; each query contains `setup`, `others` and `loops`. The
[owning study](../../docs/hobby-fitting.md#partition-preserving-equality-filter-experiment) defines scope and
assessment.
