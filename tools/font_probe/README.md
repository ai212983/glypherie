# Font probe

Host experiments and panel specimens for the
[font legibility plan](../../docs/plans/font-legibility-improvements.md).
Research and measurement limits live in the
[methodology reference](../../docs/reference/font-legibility.md).
This standalone crate is outside the firmware workspace and is not the production
LVGL font compiler.

The reusable [font generator](../font_generator/README.md) now provides configurable
glyph generation and a JSON command-line adapter. This directory retains the
measurement and panel-specimen experiments.

The [native VTT diagonal experiment](../../docs/notes/vtt-compiler-diagonals.md)
compares Microsoft-generated instructions with the frozen model.

The [shared-stem experiment in our own hinter](../../docs/notes/shared-stem-hinter.md)
uses the existing point solver and retains VTT output only as a visual reference.

## Active outline-fitting experiment

The current integrated Python specimen includes the
[approved whole curved-stroke and bar correction](../../docs/notes/bar-and-curved-terminal-recovery.md#cumulative-integration).
Regenerate it from source fonts and configuration with:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe tools/font_probe/.venv/bin/python tools/font_probe/build_source_bitmap.py
```

The output directory `tools/font_probe/out/source-bitmap-v1/` must be empty.
It contains full per-face specimens, `changes.html`, `diagnostics.html`,
input hashes and tool versions in `report.json`, combined `*-candidate.ttf`
fonts, and `*-bitmap.json` pixels and metrics. Each glyph has native-size and
enlarged PNG specimens. The current driver covers the three calibration faces
at 14/16/18/20px. Unsupported cases are excluded from exported
Unicode maps. The stage order, newest-wins branch merges, and admission
behavior are explicit in `build_source_bitmap.py`; the runtime generator
reads no historical output checkpoints. The frozen
`out/cumulative-hinter-v7/` specimen remains as a test reference: all 832
admitted bitmaps, advances, and native coordinates reproduce exactly, and
the 49 excluded cases are tracked identically (`test_build_source_bitmap.py`).
The [uniform geometry boundary](../../docs/reference/font-candidate-pipeline.md)
still separates glyph selection from correction logic.

The [research note](../../docs/notes/font-grid-fitting-research.md) maps the method
to Hersch's grid-fitting rules and documents its limits. This Python backend fits
outlines before mono scan conversion; it applies no bitmap repairs or emboldening.
It remains experimental, pending image review and reusable-generator integration.

```bash
tools/font_probe/.venv/bin/python -m pip install 'numpy==2.5.3' 'shapely==2.1.2'
tools/font_probe/.venv/bin/python tools/font_probe/run_paper_gridfit.py
tools/font_probe/.venv/bin/python tools/font_probe/run_paper_gridfit.py --stems
tools/font_probe/.venv/bin/python tools/font_probe/run_paper_gridfit.py --bowls
tools/font_probe/.venv/bin/python tools/font_probe/review_bowl_exceptions.py
tools/font_probe/.venv/bin/python tools/font_probe/run_paper_gridfit.py --source-aware
tools/font_probe/.venv/bin/python tools/font_probe/review_source_constraints.py
tools/font_probe/.venv/bin/python tools/font_probe/run_paper_gridfit.py --curves
tools/font_probe/.venv/bin/python tools/font_probe/review_curve_constraints.py
tools/font_probe/.venv/bin/python -m unittest discover -s tools/font_probe -p test_paper_gridfit.py
```

Outputs in `out/paper-gridfit/` contain the diagonal/symmetry baseline. The
`--stems` extension writes `out/paper-stems/`, including paired 16/18px glyph sheets,
vertical-stem constraints, curve interpolation and topology flags. The `--bowls` extension writes
`out/paper-bowls/`, fitting curved side supports to the shared stem targets. It
retains whole baseline glyphs for conflicting anchors or changed topology, with
rejected candidates in diagnostics. All outputs include per-glyph diagnostics and
summaries. Run the stem stage first to include the prior-topology review sheet.
The active `--source-aware` experiment writes `out/paper-source-aware/`: it matches
counters to the source and tests bounded vertical outline phases when features
mismatch. Its review compares the previously preferred experiments with the new
output; the research note records the remaining limits. The `--curves` experiment adds
sampled normal-width constraints for glyphs without long straight stems or
diagonals, writing `out/paper-curves/` and a focused `6`/`g` A/B review. Review the five flagged topology
changes before promoting the stem extension. The earlier experiments
below remain comparison evidence. Their local pixel-repair rules are superseded.

## Calibrate and generate specimens

From the repository root, with the Python dependencies below available:

```bash
python3 tools/font_probe/calibrate.py
python3 tools/font_probe/render_specimens.py \
  tools/font_probe/out/calibration/manifest.json \
  tools/font_probe/out/calibration/specimens
python3 tools/font_probe/contact.py \
  tools/font_probe/out/calibration/specimens/manifest.json \
  tools/font_probe/out/calibration/contacts
```

[calibration.json](calibration.json) selects fonts, sizes, weights, axis probes,
and threshold follow-ups. The runner calls the reusable `font_generator` CLI;
[render_specimens.py](render_specimens.py) composes its glyph pixels and metrics.
The old Rust `specimen` binary is a standalone historical experiment.

The calibration manifest records settings, checksums, measurements, and exact
artifact paths. `report.md` summarizes the matrix; `failures/` retains magnified
flagged glyphs. The [calibration findings](../../docs/notes/font-calibration-2026-09-07.md)
interpret those flags and identify the pending user image review and later board checks.

The renderer creates a native page per case, with labels and normal/inverse
samples, and writes a specimen manifest. Contact sheets consume only that manifest.
Existing output directories can contain older files; use the manifest to identify
current results. The new pipeline does not require Plex artifacts.

## Review images with the user

For a focused hinting comparison, build the generator and run:

```bash
cargo +stable build --release --locked --manifest-path tools/font_generator/Cargo.toml
tools/font_probe/.venv/bin/python tools/font_probe/compare_hinting.py \
  tools/font_generator/examples/roboto.json \
  tools/font_probe/out/hinting-review/roboto16
```

This compares `auto_fallback`, explicit `auto`, and FreeType monochrome on `bhmnpu`
at the job's size and axes. Generator paths use threshold 128; FreeType uses true
monochrome scan conversion. The JSON retains glyphs, font checksum, FreeType version
and flags; accompanying generator artifacts retain their configuration and identity.
The image shows 8× pixels and 1× samples with aligned origins/baselines. This compares
complete rendering paths; isolating hinting from scan conversion takes another test.

Run `tools/font_probe/.venv/bin/python tools/font_probe/outline_experiment.py` for
the bounded Roboto 16px alignment/growth experiment. It holds FreeType mono fixed
and applies each setting to all seven glyphs (`bhmnpdq`): horizontal outline growth
0–0.5px and grid shifts −0.375–0.375px. Results and images go to
`out/outline-experiment/`. The experiment checks connectivity, counters, and stroke
runs in explicitly selected bands. Its two-pixel target is a diagnostic hypothesis
for this sample; contour quality and source-design fidelity require separate review.
Advances stay fixed, so text spacing also needs validation before adopting a setting.

Run `tools/font_probe/.venv/bin/python tools/font_probe/join_experiment.py` to test
preserving narrow exterior notches during that thickening step. Output in
`out/join-experiment/` compares the baseline, thickened glyphs, constrained glyphs,
and unhinted source outlines at 7× size. The geometry rule protects 1px/2px gaps
found in the baseline bitmap; details already lost there remain outside its scope.
It is an experimental constraint, pending broader validation and user review.

For analysis-only source-feature annotations:

```bash
tools/font_probe/.venv/bin/python -m pip install 'shapely==2.1.2'
tools/font_probe/.venv/bin/python tools/font_probe/analyze_features.py
```

Run the join experiment first. The analyzer combines overlapping source contours
using nonzero winding, then detects inward boundary turns with a 0.4px reach and
45° threshold. It samples each source curve at 64 intervals, resamples arc length
at about 0.04px, and merges nearby detections within 0.7px. These approximations
are recorded with results under `out/feature-analysis/`. Orange boxes identify
candidate junctions; local ink-area differences include hinting displacement and
are diagnostic measurements. The tool performs no rendering corrections or
semantic stem/bowl classification. Review detection coverage before using it to
judge losses or select rendering settings.

Run `tools/font_probe/.venv/bin/python tools/font_probe/track_features.py` after
the analyzer to track its source IDs through FreeType hinting, outline growth,
and bitmap conversion. Corresponding curve segments predict movement; detected
junctions are matched within 0.75px, with ambiguous or colliding matches left
uncertain. The report combines stroke-band checks with remaining white area in a
small exterior wedge at each junction. This is a local survival diagnostic whose
acceptance thresholds still require review. Outputs are in `out/feature-tracking/`.

Run `tools/font_probe/.venv/bin/python tools/font_probe/correct_pixels.py` after
tracking for the bounded pixel-removal experiment. Starting with the shared
thickened bitmap, it tries one or two removals per tracked junction, targeting 25%
remaining white wedge area. It protects repeated stroke runs and component/counter
counts, and rejects new diagonal-only connections. Candidates use the fewest edits,
then the least removed source ink. Output in `out/pixel-correction/` records edits,
rejection reasons, and before/after images. The target and stroke proxy are
experimental; unresolved junctions remain unchanged for review.

Run `tools/font_probe/.venv/bin/python tools/font_probe/compare_join_repairs.py` to
compare two follow-ups on the unresolved junctions. The thinning arm permits local
stroke changes and diagonal-only contact, removing at most two pixels. The relocation
arm removes one pixel and adds one within two pixels, preserving edge connectivity.
Both preserve ink/counter topology and existing junction scores. Results in
`out/join-repairs/` show the tradeoffs; neither arm is a production setting.

Run `tools/font_probe/.venv/bin/python tools/font_probe/check_transfer.py` to apply
the preferred thinning arm unchanged to Roboto A–Z, a–z, and 0–9 at 14/16/18/20px.
`out/transfer-check/` contains before/after sheets, source-topology flags, uncertain
matches, unresolved junctions, and exact reproduction checks for the seven seed glyphs.
Add `--classify` to test curved-entry filtering; output goes to `out/classified-transfer/`.
Use `--protect-stems` to add paired-outline-edge protection, with results in
`out/stem-protected-transfer/`. It protects pixels at least half covered by a detected
straight stem strip; rejected joins remain unresolved for review.

`tools/font_probe/.venv/bin/python tools/font_probe/diagonal_experiment.py` compares
growth, grid phase, and hinting on `XxKVWY` at 14/16/18/20px. The five fixed variants
and their metrics are in `out/diagonal-experiment/`; renderer defaults stay unchanged.

`tools/font_probe/.venv/bin/python tools/font_probe/offset_experiment.py` compares
mono scan conversion, single coverage thresholding, and a symmetric nine-offset
coverage average at five horizontal grid phases. Results are in `out/offset-experiment/`.

Present labelled contact sheets and individual specimen PNGs before loading board
viewers. Use native-pixel views for text and nearest-neighbour enlargements for
glyph details. Record feedback by case ID, revise settings, and regenerate affected
comparisons. The user's image approval selects the cases for board verification;
physical reading comfort is evaluated in that later step.

## Select a board session after image approval

Add repeated `--case ID` arguments to render a chosen subset. To install one to a
viewer, also pass `--panel waveshare` or `--panel inkplate` and
`--install-module targets/<target>/specimens/calibration.rs`. For example:

```bash
python3 tools/font_probe/render_specimens.py \
  tools/font_probe/out/calibration/manifest.json \
  tools/font_probe/out/calibration/specimens/waveshare \
  --case roboto-waveshare-caption-w400-b1-t96 \
  --panel waveshare \
  --install-module targets/medinote-waveshare/specimens/calibration.rs
```

A session contains 1–8 explicitly selected pages. The exporter writes a genuine
Rust module and `session.json` beside the selected frame files. Regenerating that
module changes the next viewer build; choose all intended IDs in one command.

- [Waveshare viewer](../../targets/medinote-waveshare/src/bin/specimen_probe.rs)
  embeds the selected 400x300 raw binary frames. Rebuild after changing the session.
- [Inkplate gallery](../../targets/meditamer-inkplate/src/bin/gallery_probe.rs)
  reads selected 600x600 MDFR frames from the SD card. Upload exactly the `.BIN`
  filenames named in its generated module to the device directory `/assets/spec`.
  Content-derived short filenames prevent old SD files entering the session.
  Rebuild after changing its configured list.

Use the [build/flash workflow](../../docs/guides/build-and-flash.md) and
[asset upload workflow](../../docs/guides/wifi-asset-upload.md). These viewers show
host-rendered frames; physical LVGL layouts and interaction refreshes belong to
phase 3. The first review sessions and observation questions are in the findings.

## Host measurements

Python scripts run from `tools/font_probe/`. Setup:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install freetype-py uharfbuzz fonttools pillow
mkdir -p out
```

Python dependencies are not pinned; FreeType must be loadable by freetype-py.
Record actual versions with results rather than assuming the historical survey's
versions. `Cargo.lock` captures Rust dependencies; also record the Rust toolchain.

| Script | Scope |
| --- | --- |
| `sizes.py` | Per-face angular sizing using measured ratios; includes Plex as a historical comparator |
| `faces.py` | Exploratory face metrics; includes proprietary macOS system fonts as benchmarks and requires those files |
| `proposal.py`, `geometry.py`, `scale.py` | Earlier half-em sizing models; not the current face-specific specimen table |
| `contact.py` | Manifest-based native-scale contact sheets |
| `scorecard.py`, `joins.py` | Plex-only structural diagnostics, not acceptance tests for the selected faces |
| `complexity.py`, `applicability.py` | Exploratory perceptual-model work, not validated readability gates |

Run `.venv/bin/python sizes.py` to inspect the current sizing calculation. Its
ratios are measurements at a reference size, not proof of actual x-height at each
hinted size/axis location. `calibration.json` selects the current generated size table.

## Compare prototype pipelines

From the repository root:

```bash
tools/font_probe/.venv/bin/python tools/font_probe/compare_paper_prototypes.py
tools/font_probe/.venv/bin/python tools/font_probe/review_prototype_concerns.py
tools/font_probe/.venv/bin/python tools/font_probe/compare_shamir_pipeline.py
tools/font_probe/.venv/bin/python tools/font_probe/trace_shamir_cases.py
tools/font_probe/.venv/bin/python tools/font_probe/review_shamir_features.py
```

Comparisons use Roboto, Literata and Source Sans 3 at 14/16/18/20px, weight 400,
with optical size following size. Keep the width-statistics repertoire fixed.

`out/paper-prototypes/` compares Hobby and Shamir over ASCII letters/digits.
Its concerns sheet also needs retained `paper-source-aware` and `paper-curves`
reports; those historical columns retain their original scan settings.
`out/shamir-controlled/index.html` compares **A: our source-aware pipeline** and
**B: Shamir**, adding punctuation and text with source kerning and actual advances.
Composite markers indicate missing composite-level constraints; component hints
can execute. Native text uses one CSS pixel per image pixel at browser zoom 100%.

`out/shamir-controlled/focused/index.html` isolates `e`, `X`, punctuation and
related glyphs. **A: Shamir** preserves the baseline; **B: opposed sides** tests
contour direction in stroke recognition. The gallery shows source, A and B.
Axis ablations remain in diagnostic code and reports for targeted debugging. The script
requires saved baseline artifacts and verifies their default font bytes.

`out/shamir-controlled/features/` reviews prepared geometry and typed feature
candidates for the 2003 method. Select individual pairs in the overlay. This stage
uses the 1996 extraction prerequisite and leaves raster output unchanged.

Reports record hashes, settings, versions, constraints and diagnostics. Controlled
runs share outlines and dropout-off FreeType MONO, including selection trials.
Shamir executes native instructions. Modules document paper departures; structural
flags guide inspection. See the [research notes](../../docs/notes/font-grid-fitting-research.md).

## Reproduce the historical Plex comparison

For investigating the [archived survey](../../docs/archive/fonts/font-generator-options-2026-09-04.md),
not for selecting Plex again. Run after Python setup, from `tools/font_probe/`:

```bash
.venv/bin/python - <<'PY'
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
font = TTFont('../../assets/fonts/IBMPlexSans-Variable.ttf')
instancer.instantiateVariableFont(font, {'wght': 400, 'wdth': 100}, inplace=True)
font.save('out/Plex400.ttf')
PY
cargo +stable run --locked --release --bin dump
cargo +stable run --locked --release --bin dump1
cargo +stable run --locked --release --bin hr
.venv/bin/python compare.py
.venv/bin/python onebit.py
.venv/bin/python onebit_img.py
.venv/bin/python scorecard.py
cargo +stable run --locked --release --bin joins
.venv/bin/python joins.py
```

`dump` writes `out/rasters.json`; `dump1` writes `out/rasters1.json`; the join
experiment writes `out/joins.json`. The scorecard uses a 4x unhinted FreeType raster
as its topology reference despite older comments saying 8x or renderer-independent.
Its pixel-distance “confusability” and stem-run counts are diagnostic proxies.
Symmetry output survives in the script even though the survey rejected that metric.
Some Python routines repeatedly copy FreeType bitmap buffers and can be slow.

Keep these limitations with any reused result. The historical >=128 Plex scorecard
and the current size-dependent specimen threshold are different experiments.

Prepared-segment rendering comparison:

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_shamir_segments.py
```

Open `out/shamir-controlled/segments/index.html` for native text and enlarged
source / A saved Shamir / B segment candidate images. B connects prepared geometry,
recurring measurements, segment constraints and explicit interpolation. It remains
experimental, with visible regressions and incomplete serif/junction/counter rules.
The report records baseline hashes and preparation-only raster differences.
Recognition overlays are internal diagnostics; user review uses these rendered images.

Combined-model conformance checks:

```sh
tools/font_probe/.venv/bin/python tools/font_probe/check_shamir_model.py
```

This writes internal fonts and constraint residuals to `out/shamir-model/`.
See the [conformance review](../../docs/notes/shamir-model-conformance.md) for the
published contract, explicit implementation choices and remaining recognition
coverage. Existing review galleries retain their saved candidates.

Render the checked combined model beside the saved baseline:

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_shamir_model.py
```

Open `out/shamir-controlled/combined/index.html`. A is the saved Shamir baseline;
B is the combined model, with visible regressions. The script verifies model
source, input and checked output font hashes, exact baseline reproduction, and
image bounds. The `audit` group highlights cases with larger measured movement;
`combined-before-fix` preserves the earlier candidate.

Internal model-construction gate (preserves the published comparison):

```sh
tools/font_probe/.venv/bin/python -m pip install 'skia-pathops==0.9.2'
tools/font_probe/.venv/bin/python tools/font_probe/check_shamir_model.py --output tools/font_probe/out/shamir-construction
```

This performs filled-boundary normalization and template-port binding before
hinting. Current coverage failures and primary-source limitations are recorded
in the conformance review. Human image review follows this internal gate.

Rejected-relationship audit (also measures preserved nonzero offsets):

```sh
tools/font_probe/.venv/bin/python tools/font_probe/check_shamir_model.py --output tools/font_probe/out/shamir-alignment
tools/font_probe/.venv/bin/python tools/font_probe/audit_shamir_alignments.py tools/font_probe/out/shamir-alignment/conformance.json
```

`alignment-audit.json` binds its input report hash, validates model and font hashes,
and records each displaced relationship with its surviving target constraints.
Confirm image-review findings with individual enlarged glyphs and native bitmap
comparisons before classifying a regression. Contact sheets locate suspects;
measured pixels and traced constraints establish the finding.

The Ratio-precision build uses `--output tools/font_probe/out/shamir-ratio` with
these same commands. Ordinary and shared Ratio coefficients execute at 14-bit
precision; `test_shamir_ratio_precision.py` covers narrow reference intervals,
endpoints, translation fallback and signed extrapolation. This numerical fix
retains the direction-conditioning policy and does not close the three junction
shape findings in the conformance review.

### Scheduler comparison

The experimental whole-point scheduler shares the scalar backend's feature
construction, priorities, defaults, conditioning and native translation:

```sh
tools/font_probe/.venv/bin/python tools/font_probe/check_shamir_model.py --scheduler scalar --output tools/font_probe/out/shamir-scheduler-scalar
tools/font_probe/.venv/bin/python tools/font_probe/check_shamir_model.py --scheduler point --output tools/font_probe/out/shamir-scheduler-point
tools/font_probe/.venv/bin/python tools/font_probe/compare_shamir_schedulers.py
```

The comparison checks source/font hashes and identical extracted features, and
writes coordinate, relation and pixel differences plus individual crops and an
HTML index to `out/shamir-scheduler-comparison/`. Scalar remains the default.
See the [conformance review](../../docs/notes/shamir-model-conformance.md#controlled-point-scheduler-comparison)
for results and the scope of the paper comparison.

### Researched baseline

`build_font(..., profile="baseline", ppem=14)` selects the documented baseline
model independently of the experimental scalar/point profiles. It uses a
requested-size native adapter: exported hints apply only at the requested integer
ppem under isotropic axis-aligned loading. Other sizes receive no adapter hints.
The [conformance decisions](../../docs/notes/shamir-model-conformance.md#implemented-baseline-decisions)
identify the source rules, conservative assumptions and translation substitution.

Use a new empty output directory for each verification; the command freezes Python
sources, paper, settings, inputs, generated fonts and independent equation results:

From the repository root:

```sh
tools/font_probe/.venv/bin/python tools/font_probe/check_shamir_baseline.py --output tools/font_probe/out/shamir-baseline-next
tools/font_probe/.venv/bin/python tools/font_probe/render_shamir_baseline.py tools/font_probe/out/shamir-baseline-next/baseline-verification.json
```

The current frozen baseline is `out/shamir-baseline-v6/`; prior snapshots remain
available. Its `gallery/index.html` contains all 972 enlarged glyph pairs and
native text. Numerical checks pass. Conformance review remains open: the revised
member and contour-reference assumptions resolve several reported defects, while
V distortion and G anchor differences remain. See the conformance review for
case-specific evidence before treating this as a baseline ready for acceptance.

The correction pass adds segment dominance, source-defined cardinal tests,
projected feature measurements and actual straight-run boundaries. Shared links
use reduced-graph priorities; ordinary members use final point ordering. M/5 and
other visible defects remain open despite numerical and construction checks.

Run `tools/font_probe/.venv/bin/python tools/font_probe/compare_shamir_tolerances.py`
from the repository root to reproduce the explicitly labeled Roboto 14px alignment
experiment at .012/.024/.048em in a new empty output directory (`--output`).
The resulting `out/shamir-tolerance-comparison/index.html` includes all reported
cases and full native text; wider settings remain unpromoted.

The v6 correction preserves metric priority on exact horizontal baseline member
links. Roboto A right-foot endpoints remain at y0 at 14/16/18/20px. The full 972
native/construction cases and 163 focused tests pass; wider shape approval remains open.

### Coordinated representative experiment

The subsequent [whole-point reorientation prototype](../../docs/notes/shamir-model-conformance.md#whole-point-reorientation-prototype)
is available via `compare_shamir_reorientation.py --output <new-directory>`.
Run it with this directory's virtualenv Python. Its H/F/A comparison is frozen in
`out/shamir-reorientation-v2/index.html`; the fourth column is the new prototype.
V2 adds compatible frozen coordinate defaults and exact-projection substitution;
all 36 H/F/A cases pass, and all 16 supported v1 cases retain identical coordinates
and pixels. Pass `--previous out/shamir-reorientation-v1` (from this directory)
to enforce those regressions. See the conformance record for assumptions.
Supported cases preserve every restored member equation, with explicit unsupported
results for systems outside the bounded construction. Baseline generation remains
unchanged.

Run `tools/font_probe/.venv/bin/python tools/font_probe/compare_shamir_representatives.py`
from the repository root. The default compares all 972 cases against frozen v6
in `out/shamir-representative-comparison/`; use `--output` for a new empty directory.
The graph-only search changes existing representative choices after statistics,
with `--budget 256` evaluations per glyph. It preserves the baseline implementation
and labels all outputs as experimental. Contour-order sensitivity remains open;
see the [conformance record](../../docs/notes/shamir-model-conformance.md#coordinated-representative-prototype).
