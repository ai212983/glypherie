<!-- cspell:words unhinted counterspace Hersch yinyangfit yinyang TypeFacet electricbubble fullfield stdlib dtype dtypes tfjs Thrtnnoo Toalrise ppem multiscale rescored -->

# Contextual spacing experiment

Requires Python 3.10+, a C compiler for the independent weighting tests, and the repository's Rust toolchain. The
[design](../../docs/designs/text-layout/contextual-spacing-and-healing.md) owns the model and gates;
[iteration 001.03](../../docs/revisions/001/03-spacing-kerning.md#proposed-optical-pair-spacing-experiment) owns
assessment.

Hu/Hersch is the default model and uses only the Python standard library. Captures for that model must include delivered
`n` and `H` glyphs for reference density; include `0` for the experimental numeral reference. These must be requested
output characters: source-only auxiliary references cannot supply delivered bitmaps. Missing required calibration
geometry retains metric placement with an explicit diagnostic.

CounterSpace is optional and uses a separate numerical environment, tested with Python 3.14. Install its pinned
dependencies without changing the system environment:

```sh
python3 -m venv out/diagnostics/contextual-spacing/counterspace-preview/venv
out/diagnostics/contextual-spacing/counterspace-preview/venv/bin/python -m pip install \
  -r experiments/contextual_spacing/requirements-counterspace.txt
```

The vendored reference and compatibility setup are documented in
[reference/counterspace](reference/counterspace/README.md). Use that environment's Python for CounterSpace commands and
tests. Source font files must remain available at the captured path with the same SHA-256. CounterSpace captures must
include its reference glyphs `A`, `E`, `H`, `O`, `V`, `n`; spaces and all preset characters must also be captured for
the reading page.

Run mechanical checks:

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -v
cargo test --locked --manifest-path experiments/contextual_spacing/native/Cargo.toml
```

Build the pinned independent native reference and require envelope parity (otherwise these native tests skip when its
executable is absent):

```sh
python3 experiments/contextual_spacing/reference/build-native.py
CONTEXTUAL_SPACING_REQUIRE_NATIVE=1 python3 -m unittest discover -s experiments/contextual_spacing/tests -v
```

The reference build needs Python 3.12+, CMake, C/C++ compilers, pkg-config, FreeType, gettext, GLib, libxml2 and zlib
development files. It builds locally under diagnostics without installing FontForge. It pins `-ffp-contract=off` and
`-fno-fast-math`; parity targets those source-operation semantics. The build retains source, compiler and license
identities.

Capture a request containing `font_path`, `size_px`, `characters`, optional `axes`, optional explicit `pipeline`, and
optional `mono_raster`:

```sh
cargo run --locked --manifest-path experiments/contextual_spacing/native/Cargo.toml -- \
  out/diagnostics/contextual-spacing/request.json out/diagnostics/contextual-spacing/capture.json
```

The native default is selective fitting with the terminal scanner and the diagonal overlay enabled. Its produced scan
settings match the working preview: `{"dropout":"smart","include_stubs":true,"font_instructions":true}`. Pass an
explicit `mono_raster` object to override these settings; fields within that object use the maintained generator's
defaults when omitted. Source diagnostic settings remain unchanged. Omitted axes use font defaults. To match the current
Literata preview samples, explicitly set `axes.opsz` to `size_px`; capture does not automatically select optical size.

Capture is Mono only. Source metrics use the maintained generator's nearest-1/64-pixel policy; source outline
coordinates remain in design units. The capture records its settings and dependency identity. Request characters exclude
line breaks; include ordinary space explicitly when needed. Text supplied to the solver may contain line breaks.

Resolve a preview, or omit `--text` for all ordered pairs including repeated glyphs:

```sh
python3 experiments/contextual_spacing/run.py \
  out/diagnostics/contextual-spacing/capture.json out/diagnostics/contextual-spacing/preview.json \
  --text 'AV To lmi' --benchmark
```

`--source-kerning` and `--optical` range from 0 to 1. `--letter-spacing` and `--word-spacing` accept finite pixels,
rounded once by placement. `--width` enables greedy scalar wrapping. `--subdivisions` selects 100 or 200 for the
FontForge comparison models; their native integer band step is `floor(em / subdivisions)` design units. The Hu/Hersch
and retained filtered-wall models use a uniform 64-samples-per-pixel reference-height grid; `--filtered-samples-per-px`
changes their numerical sampling resolution in the solver CLI. Page export uses the default resolution. `--geometry
bitmap` measures delivered binary ink; `fitted_outline` is a separate diagnostic alternative for the FontForge
comparisons; Hu/Hersch and filtered-wall spacing abstain under that geometry policy. `--work-limit` bounds ordered pairs
(default 10,000); geometry limits are declared in `estimator.py`. Interrupted or limited results retain incomplete
status and cannot be laid out.

`--spacing-model hu_hersch` is the default. It measures depth-limited delivered walls with published depth parameters
and reference density at full maintained metric placements. Results include parameter provenance, reference mechanisms
and clearance. Select `--spacing-model filtered_walls` for the earlier slope-only/source-reference comparison. At full
calibrated strength, the kerning slider no longer contributes to solved pairs. Select `--spacing-model font_calibrated`
for the FontForge calibrated comparison, `--spacing-model source_relative` for source-preserving comparison, or
`--spacing-model balanced` for the fixed-target diagnostic. `--target-separation-em` sets only that diagnostic's
positive finite em target (default `0.15`). Results retain model, targets and provenance.

Select `--spacing-model hu_source_calibrated` for shared targets from source-designed `nn`/`HH` outlines and full source
metrics, measured against delivered bitmap walls. It requires those captured source references; missing or unsupported
references retain metric placement. This mode keeps the current rounding and clearance composition. `hu_hersch` retains
delivered-reference calibration.

Select `--spacing-model hu_alphabet_source_target` for a fixed-alphabet source-score target, or `--spacing-model
hu_density_conserved` for continuous source-origin mean conservation on the fixed calibration domain. These opt-in
experiments require complete captured `a–z`, `A–Z` or experimental `0–9` repertoires for each class, plus the matching
body-window references. Missing calibration glyphs retain metric placement with a reason. Rounding, clearance and
evaluation-text frequency can leave final density residuals. The
[density experiment](../../docs/designs/text-layout/contextual-spacing-and-healing.md#fixed-alphabet-density-experiment)
owns the scope and limits; neither mode changes the default.

Select `--spacing-model hu_density_conserved_touch` for the same fixed-alphabet density target with face and corner
contact permitted and occupied-cell overlap forbidden. Export `--models hu_density_conserved hu_density_conserved_touch
--default-spacing-model hu_density_conserved_touch` to compare strict and touching-permitted clearance. This opt-in
candidate retains the other model's targets, rounding and glyph bitmaps.

Select `--spacing-model hu_fitted_density_conserved_touch` to measure the captured fitted outline while retaining the
same delivered bitmaps and their no-overlap clearance. Keep the CLI's `--geometry bitmap` setting; the named model
selects its internal measurement geometry. Export `--models hu_density_conserved_touch hu_fitted_density_conserved_touch
--default-spacing-model hu_fitted_density_conserved_touch` for the bitmap-wall versus fitted-wall comparison. The fitted
target is recalculated with the same fixed-alphabet formula. Captures must contain valid pixel-coordinate
`produced_commands`.

Select `--spacing-model hu_source_relative` to compare source-preserving Hu compensation with the shared-target model.
It requires delivered `n`/`H` body-window references (`0` for numerals) and captured continuous source outlines. The
source-kerning control applies to its pair target at every optical strength. Results retain source and delivered
offsets, source targets and rounding/clearance residuals.

Select `--spacing-model counterspace` using the numerical environment for delivered-bitmap calibration and closest
feasible integer-score placement. Select `counterspace_delivered_first` to retain first-crossing placement with that
calibration, or `counterspace_source_first` for the previous source-raster calibration and first-crossing control.
Captured axes identify the source instance. Delivered calibration uses captured reference bitmaps at the maintained
full-kerning metric placements. Weighted-score diagnostics use analysis-cell units rather than pixel distances. Optical
zero does not load the optional dependencies. Earlier comparison models remain available without those dependencies.

New captures retain auxiliary source-only `n`, `H` and `0` references without adding them to the requested output
repertoire. Older captures can supply these references from their existing repertoire. The native adapter may internally
render additional unhinted diagnostic strikes for missing references; timings include that work.

The solver CLI preserves source-tabular digit spacing by default. Pass `--no-preserve-tabular-spacing` to apply optical
correction to those pairs; `--preserve-tabular-spacing` explicitly retains their metric placement. Fixed-pitch spacing
remains protected in both cases.

Plan the full design matrix, then run the bounded four-family native smoke comparison:

```sh
python3 experiments/contextual_spacing/matrix.py out/diagnostics/contextual-spacing/plan
python3 experiments/contextual_spacing/matrix.py out/diagnostics/contextual-spacing/smoke-matrix --run-smoke
```

The smoke command retains requests, captures, results, errors and a manifest. The planned matrix separates automatic,
selective and overlay paths, with independent optical-size endpoints. Full execution, Gray boundary selection and real
fixed-pitch corpus expansion follow the design's gates. Timings are native diagnostics; `run.py --benchmark` also
reports Python peak traced allocation, excluding native capture and browser/WASM memory.

## Source-only reference probe

Run the source-only stem/curve reference probe on retained captures:

```sh
python3 experiments/contextual_spacing/stem_curve_probe.py \
  out/diagnostics/contextual-spacing/stem-curve-source-run \
  out/diagnostics/contextual-spacing/preset-preview/captures/Literata-reading/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/Roboto/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/RobotoFlex/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/SourceSans3/capture.json
```

The output directory must be new. `--presets PATH` selects the evaluation text configuration; the default is this
component's `presets.json`. It must contain `lynx-lowercase`, `lynx-uppercase` and `aaron-abraham` preset IDs. The
[source-only design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#stemcurve-reference-experiment)
owns the model and its integration gate.

## Interactive comparison page

Run both fixed-alphabet calibration arms and their source/bitmap/fitted-outline controls:

```sh
python3 experiments/contextual_spacing/density_probe.py \
  out/diagnostics/contextual-spacing/density-probe-run \
  out/diagnostics/contextual-spacing/preset-preview/captures/Literata-reading/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/Roboto/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/RobotoFlex/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/SourceSans3/capture.json
```

The probe output directory must be new. `--presets PATH` selects held-out evaluation texts; it does not select
calibration alphabets or weights. The default is this component's `presets.json`.

Export a new, self-contained HTML page from complete Mono captures:

```sh
python3 \
  experiments/contextual_spacing/page.py out/diagnostics/contextual-spacing/comparison/site \
  out/diagnostics/contextual-spacing/preset-preview/captures/Literata-reading/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/Roboto/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/RobotoFlex/capture.json \
  out/diagnostics/contextual-spacing/preset-preview/captures/SourceSans3/capture.json \
  --work-limit 12000
```

Open the generated `site/index.html` directly in a browser; it works offline. With the existing web development server,
the same file is available at `http://localhost:8903/@fs/<absolute-site-path>/index.html`. The output directory must be
new. Export retains a manifest and full data alongside the HTML.

New exports embed the captured source font for a browser-native text reference at the same size and axes. It uses normal
browser shaping, antialiasing, kerning, ligatures and fractional placement, with ordinary word wrapping. This reference
does not use bitmap spacing or the optical controls. The source font must remain available and match its captured
SHA-256. Adjacent `OFL-<font-stem>.txt` licenses are included when present. The shared enlargement control scales a
second browser view after layout, retaining its original wrapping, font size and axes.

Add the optional custom 3-bit grayscale diagnostic by capturing each matching request with:

```sh
cargo run --locked --manifest-path experiments/contextual_spacing/native/Cargo.toml -- \
  --grayscale REQUEST.json GRAYSCALE.json
```

Pass `--grayscale-captures GRAYSCALE.json ...` to `page.py`, in the same order as the Mono captures. Size, axes, source
identity and repertoire must match. The collapsed diagnostic retains the default coverage renderer and uses vanilla
`generate` source-linear advances and full kerning in 26.6 pixels. These accumulate fractionally; only drawing origins
round to pixels, as in the native source-layout surface. Optical strength and deliberate spacing controls apply only to
the Mono views. Earlier v1 Gray captures used bitmap spacing and must be regenerated.

Every new page also includes a Mono reference with vanilla source spacing from the existing capture. It needs no new
render: the captured binary cells use source advances and full kerning, accumulated fractionally like the Gray
reference. The pair inspector retains native black-ink alternatives and adds enlarged contact overlays for the selected
pair.

The page provides Hu/Hersch shared-target and source-relative modes, filtered-wall, FontForge calibrated,
source-preserving and fixed-target diagnostic models, five completed source-kerning and optical-strength settings,
independent whole-pixel letter and word spacing, scalar wrapping and native/enlarged comparisons. Editable text is
limited to the captured repertoire, listed on the page. To compare another size, axes, pipeline or repertoire, capture
those settings first and export a new page.

Use `--models hu_hersch hu_source_calibrated` to generate only the two shared-density comparisons. The initial
`--default-spacing-model` must be included in that selection. All tables are computed with the current solver identity.

Add `--neighbor-review REVIEW.json` for an optional focused diagnostic panel. Its JSON selects captured pairs and words
and an exported model, for example:

```json
{
  "pairs": ["nx", "hx", "mx", "dx", "ux", "kx"],
  "words": ["lynx", "lynx lynx", "jinx", "auxiliary", "xn"],
  "spacingModel": "hu_fitted_density_conserved_touch",
  "deltaPx": -1,
  "mode": "text"
}
```

`mode: "text"` compares the entire selected preset or custom text, with independent wrapping and shared tracking
controls. All text remains available through the native/enlarged scroll panes. Contact markers start off. Omit `mode` or
set it to `"pairs"` for the earlier pair/word panel with zero deliberate tracking and no wrapping. Alternatives are
unclamped one-pixel-tighter diagnostics in either mode. Verify its Python fixtures, pixel contacts and browser reference
with:

```sh
node experiments/contextual_spacing/test_neighbor_review_browser.mjs PAGE/index.html
node experiments/contextual_spacing/test_neighbor_review_browser.mjs INLINE/index.html PAGE/page-data.json
```

Use `--default-spacing-model hu_source_relative` to start a diagnostic page with the new comparison selected. The
exporter default remains `hu_hersch`; the chosen initial model must be included in that export.

Set `--target-separation-em` on the page export command to configure the fixed-target diagnostic. Calibrated targets
come from the active model's reference geometry. The page displays the active target and its basis; new settings require
a new export.

Page export loads text presets from `presets.json`; use `--presets PATH` for another catalogue (a JSON array of
`{id,label,text}` objects). Every capture must contain all preset characters except line breaks. Include those
characters in native capture requests before exporting. Use `--work-limit N` when the enlarged repertoire requires more
than the default 10,000 ordered pairs per table.

Create a bounded inline page from an existing complete export. Install the pinned packaging dependencies in a virtual
environment first:

```sh
python -m pip install -r experiments/contextual_spacing/requirements-inline.txt
python experiments/contextual_spacing/inline.py FULL_PAGE/index.html NEW_INLINE_DIRECTORY
node experiments/contextual_spacing/test_inline_browser.mjs NEW_INLINE_DIRECTORY/index.html REPORT.json
node experiments/contextual_spacing/tests/test_page_helpers.mjs
```

For pages containing a browser reference, the inline font is a subset retaining nondefault variation axes, layout
features, hint programs and license records. Check its source geometry and browser layout against the original:

```sh
python experiments/contextual_spacing/test_browser_font.py FULL_PAGE_DIRECTORY NEW_INLINE_DIRECTORY/index.html REPORT.json
node experiments/contextual_spacing/test_browser_reference.mjs FULL_PAGE_DIRECTORY NEW_INLINE_DIRECTORY/index.html
```

Use `--text-file PATH` to select the initial inline sample without changing the preset catalogue. For the two-Hu-mode
reading comparison, verify both fixed model columns with:

```sh
node experiments/contextual_spacing/test_two_modes_browser.mjs PAGE/index.html
```

The inline exporter keeps the first captured font and, by default, the two Hu comparisons plus FontForge source-relative
comparison. Use `--models MODEL ...` to choose explicitly. All supplied presets are retained. The exporter fails if the
losslessly packed document exceeds the inline limit or the output directory already exists.

The page starts with Hu/Hersch selected and retains seven models in schema version 9. Add `--include-counterspace` using
the optional numerical environment to include its three comparison variants, for ten models total. **Preserve tabular
spacing** starts off for reading comparisons; enable it to retain source-tabular digit placement. **Inspect pair** shows
the active model's diagnostics, including CounterSpace weighted scores and fit provenance, or the wall models'
separation/area measurements. Native pair examples show the emitted placement and its one-pixel neighbors, with
feasibility determined by the retained clearance minimum. Both tabular policies are retained. Deliberate spacing
suppresses the viewer's CounterSpace realized-score claim because the nonlinear score must be recomputed offline for
that placement.

Verify the generated page with the web component's installed Playwright browser:

```sh
node experiments/contextual_spacing/test_page_browser.mjs out/diagnostics/contextual-spacing/comparison/site
```

The check opens the offline file without a server, compares browser placements with Python fixtures, exercises controls
and retains desktop/mobile captures and its verification report beside the page.

## Masked complete-cell comparison

Export the isolated two-arm geometry assessment from the four retained capture directories:

```sh
python3 experiments/contextual_spacing/blind_review.py \
  out/diagnostics/contextual-spacing/blinded-wall-review/site
node experiments/contextual_spacing/test_blind_review_browser.mjs \
  out/diagnostics/contextual-spacing/blinded-wall-review/site/index.html
```

The output directory must be new. `--capture-root PATH` selects the parent of the four family capture directories;
`--seed TEXT` reproduces the initial A/B assignment. The self-contained HTML retains all four fonts and seven presets,
with the retained full fitted-outline model and a complete-binary-cell ablation at fixed full strength and zero
tracking. The manifest and model audit retain identities separately from displayed A/B labels. The initial view is a
short Literata passage; other fonts and full presets are optional. Feedback is given in chat, with no page rating,
storage or download workflow. A/B meanings stay fixed across selections; method disclosure is optional. The
[design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#complete-cell-geometry-assessment) owns the
assessment protocol and limits.

## YinYangFit reference probe

Check the pinned source without importing its GPU/font initialization:

```sh
git clone --no-checkout https://github.com/skosch/YinYangFit.git \
  out/diagnostics/contextual-spacing/yinyangfit/source
git -C out/diagnostics/contextual-spacing/yinyangfit/source \
  checkout --detach 609d17e8a6446ec4413a1b02a0768b8214d73333
out/diagnostics/contextual-spacing/counterspace-preview/venv/bin/python \
  experiments/contextual_spacing/yinyangfit_probe.py \
  out/diagnostics/contextual-spacing/yinyangfit/source \
  out/diagnostics/contextual-spacing/yinyangfit/probe.json
```

The probe requires NumPy; the existing numerical environment above supplies it. The output must be new. It verifies
source bytes against the pinned commit and executes only the extracted penalty/selection method bodies. This does not
run the full engine or notebook. The
[feasibility design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-feasibility-experiment)
owns the reproduction gate.

## YinYangFit historical scorer recovery

Requires `uv`, Python 3.11 and macOS arm64 for the tested compatibility environment. Install only into the isolated
environment, then prepare the hash-checked historical inputs:

```sh
uv venv --python 3.11 out/diagnostics/contextual-spacing/yinyangfit/recovery-env
RECOVERY_PY=out/diagnostics/contextual-spacing/yinyangfit/recovery-env/bin/python
uv pip sync --python "$RECOVERY_PY" --require-hashes experiments/contextual_spacing/requirements-yinyangfit.txt
"$RECOVERY_PY" experiments/contextual_spacing/yinyangfit_inputs.py \
  out/diagnostics/contextual-spacing/yinyangfit/recovery-inputs
```

Run the bounded CPU recovery with fresh input/output directory names:

```sh
"$RECOVERY_PY" experiments/contextual_spacing/yinyangfit_recovery.py \
  out/diagnostics/contextual-spacing/yinyangfit/recovery-sources/YinYangFit.ipynb \
  out/diagnostics/contextual-spacing/yinyangfit/recovery-inputs \
  out/diagnostics/contextual-spacing/yinyangfit/recovery-reference \
  --noise-policy reference_seeded_per_pair --max-seconds 240 --max-rss-gib 24
```

The input command downloads immutable source/font files into its default diagnostics cache; `--sources-cache` changes
that path. `--pairs` selects only the fixed `nn`, `oo`, `av` probes. `--noise-policy noise_off` selects the separately
named evaluation arm. `--gradient-pair nn` adds one upstream-loss gradient census, without an optimizer update. Use a
new output directory and an explicit time budget for each arm; `--threads`, `--seed`, `--max-seconds` and
`--max-rss-gib` configure the bounded run. Reports, logs, adapter source and untrained checkpoint state are written
under its output.

Run the light provenance, input and loss checks without executing another full scorer:

```sh
YINYANGFIT_INPUTS=out/diagnostics/contextual-spacing/yinyangfit/recovery-inputs \
  "$RECOVERY_PY" -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyangfit_recovery.py' -v
```

The
[recovery design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-feasibility-experiment)
owns the stage, numerical gates and limits.
[Training requirements](../../docs/references/yinyangfit-training-requirements.md) describe the distinct historical
model and intended training domain.

## YinYangFit short training probe

Use the isolated environment and prepared inputs above. Run the fixed three-update CPU protocol in a new output
directory:

```sh
"$RECOVERY_PY" experiments/contextual_spacing/yinyangfit_train.py \
  out/diagnostics/contextual-spacing/yinyangfit/recovery-sources/YinYangFit.ipynb \
  out/diagnostics/contextual-spacing/yinyangfit/recovery-inputs \
  out/diagnostics/contextual-spacing/yinyangfit/training-smoke \
  --max-seconds 1200 --max-rss-gib 24
```

The schedule is fixed to `nn`, `oo`, `av`, with Adam learning rate `0.0011`. The command evaluates those pairs before
and after the three main updates, writes state-complete checkpoints after each update, then replays the last two updates
from checkpoint one. Its report counts three main updates and two replay updates separately. `--seed`, `--threads`,
`--max-seconds` and `--max-rss-gib` configure the bounded run; there is no epoch or learning-rate search.

Run both recovery and training checks without executing the full scorer:

```sh
YINYANGFIT_INPUTS=out/diagnostics/contextual-spacing/yinyangfit/recovery-inputs \
  "$RECOVERY_PY" -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyangfit*.py' -v
```

The
[experiment design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-feasibility-experiment)
owns the objective, numerical stops and assessment boundary.

## YinYangFit pair holdout trial

Use the same isolated environment and prepared inputs. The maintained plan supplies the training/evaluation split,
schedule, seed, optimizer settings and resource budget:

```sh
"$RECOVERY_PY" experiments/contextual_spacing/yinyangfit_pair_trial.py \
  out/diagnostics/contextual-spacing/yinyangfit/recovery-sources/YinYangFit.ipynb \
  out/diagnostics/contextual-spacing/yinyangfit/recovery-inputs \
  out/diagnostics/contextual-spacing/yinyangfit/pair-trial \
  --plan experiments/contextual_spacing/reference/yinyangfit-recovery/pair-trial.lock.json
```

The output directory must be new. The command retains its plan, source snapshots, reports and checkpoints there.
`--plan` selects a manifest path; incompatible or altered protocol declarations fail validation. Run the light checks
with the `test_yinyangfit*.py` command above. The
[owning design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-feasibility-experiment)
defines the comparison and the limits of pair-identity holdouts.

## YinYangFit interactive spacing feasibility

Run the focused checks without captures (uses retained Mono/Gray captures):

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyangfit_interactive.py' -v
```

The focused suite pins the near-tie minimizing set (global valid minimum, then tolerance), the captured-source Hamburg
draw origins from capture arithmetic on both 24 px Gray captures, the metric-rounded versus fractional word split, and
Mono agreement of both word policies.

Evaluate frozen settings (defaults plus each control endpoint) on Mono/Gray at two sizes and two families:

```sh
python3 experiments/contextual_spacing/yinyangfit_interactive_evidence.py OUTPUT \
  --mono16 MONO16.json --mono16b MONO16B.json --gray16 GRAY16.json --gray16b GRAY16B.json \
  --mono24 MONO24.json --mono24b MONO24B.json --gray24 GRAY24.json --gray24b GRAY24B.json
```

Capture 24 px inputs with the native tool first when needed:

```sh
cargo run --locked --manifest-path experiments/contextual_spacing/native/Cargo.toml -- REQUEST.json CAPTURE.json
cargo run --locked --manifest-path experiments/contextual_spacing/native/Cargo.toml -- --grayscale REQUEST.json GRAY.json
```

Export the self-contained interactive page (offline `file://` use; output must be new):

```sh
python3 experiments/contextual_spacing/yinyangfit_interactive_page.py SITE \
  --spec LABEL mono|gray CAPTURE.json [--spec ...]
```

Verify the export without a browser server (defaults to the current versioned site; pass another site directory to check
that export instead):

```sh
node experiments/contextual_spacing/test_yinyangfit_interactive_page.mjs [SITE]
```

With the web component's Playwright dependency installed, drive the rendered page:

```sh
node experiments/contextual_spacing/test_yinyangfit_interactive_browser.mjs [SITE]
```

The three sliders present target cohesion, interaction reach in pixels (stored as `feature_scale`) and proximity falloff
(radial decay shape); each snaps to exactly evaluated grid points. The page embeds per-setting costs and the browser
rechecks every choice against them, including an independent near-tie fixture and a captured-source word baseline
recomputed from the raw captures. Words show the experiment's cumulative whole-pixel layout beside the captured-source
fractional draws. The
[interactive design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-interactive-spacing-feasibility)
owns the model, sources, explicit hypotheses and pending assessment scope. Optical acceptance stays pending.

## YinYang oriented field stage

Run the focused numerics/representation suite (NumPy only, no captures needed except the real-glyph smoke test):

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyang_oriented_fields.py' -v
```

Compute per-glyph single-scale V1C oriented fields and declared pair diagnostics on synthetics plus the retained
Roboto/Literata 16/24 px Mono/Gray captures (output directory must be new):

```sh
python3 experiments/contextual_spacing/yinyang_oriented_fields_evidence.py \
  out/diagnostics/contextual-spacing/yinyang-oriented-fields/implementation
```

The run writes raw field arrays plus `provenance.json` (parameters, capture SHAs, implementation SHA, timings).
The [stage design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyang-oriented-field-stage)
owns the frozen parameters, adaptations and gates; this stage produces fields only (no scalar placement score).
Optical assessment stays pending.

## YinYang stage-1 reconciliation

Cross-check the stage-1 writer module against the frozen independent oracle on identical declared inputs
(output directory must be new; reads the frozen `reference-review/` oracle read-only and never rewrites it):

```sh
python3 experiments/contextual_spacing/yinyang_stage1_reconciliation.py \
  out/diagnostics/contextual-spacing/yinyang-oriented-fields/reconciliation
```

The run writes `reconciliation.json` plus raw arrays (mask permutation, identical-input estimator parity with a
matched-support control, independent derivative-of-Gaussian verification, support-floor ladder, real-glyph Mono/Gray
support, fractional-phase parity, gap-width probe).

## YinYang multiscale field stage

Run the focused numerics/representation suite (NumPy only, no captures needed except the real-glyph smoke test):

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyang_multiscale_fields.py' -v
```

Compute per-glyph multiscale direct-path V1C fields and declared pair diagnostics on synthetics plus the retained
Roboto/Literata 16/24 px Mono/Gray captures (output directory must be new):

```sh
python3 experiments/contextual_spacing/yinyang_multiscale_fields_evidence.py \
  out/diagnostics/contextual-spacing/yinyang-oriented-fields/multiscale
```

The run writes raw field arrays plus `provenance.json` (parameters, per-scale gains, capture SHAs, implementation
SHAs, gate values, B2 side-by-side diagnostics, timings). The
[stage design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyang-multiscale-field-stage)
owns the frozen progression/weights, adaptations and gates; this stage produces fields only (no scalar placement
score, no UI knobs). Optical assessment stays pending.

## YinYang stage-3 SCORE-v2 hypothesis

Run the focused score suite (NumPy only; frozen field modules untouched):

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyang_oriented_score.py' -v
```

Run the full 64-case study plus synthetics and validation (output directory must be new):

```sh
python3 experiments/contextual_spacing/yinyang_oriented_score_evidence.py \
  out/diagnostics/contextual-spacing/yinyang-oriented-fields/score-experiment
```

The run writes per-step maps, `report.json` and `provenance.json` (parameters, capture SHAs, implementation SHAs,
timings, peak RSS). The
[stage design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyang-stage-3-score-v2-hypothesis-experiment)
owns the candidate, ablation, domains and gates; this stage is mechanical/model-coherence only, never optical
approval or live promotion.

Build the isolated native ink comparison page from the corrected corpus (output directory must be new):

```sh
python3 experiments/contextual_spacing/yinyang_oriented_score_preview.py \
  out/diagnostics/contextual-spacing/yinyang-oriented-fields/visual-comparison
```

Check the page without a server, using the web component's Playwright dependency (`file://` works):

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyang_oriented_score_preview.py'
node experiments/contextual_spacing/test_yinyang_oriented_score_preview_browser.mjs
```

### v3 sample-gallery page (oriented engine, all 13 root samples)

Capture all catalogue cases with the native tool (one request per case in
`out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/requests/`, literata requests omit U+0060, which the font
cannot shape as an isolated scalar):

```sh
TOOL=experiments/contextual_spacing/native/target/debug/contextual-spacing-capture
$TOOL out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/requests/<case>.json \
  out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/captures/<case>-mono.json
$TOOL --grayscale out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/requests/<case>.json \
  out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/captures/<case>-gray.json
```

Export the gallery page (output must be new; per-dataset tables lazy-load from `data/`; the live reviewed page
stays byte-frozen and is never a build input). Build input is the frozen source catalogue
(`yinyangfit_interactive_v3_source/catalogue.json`, pinned by hash; generated pages are never read).
Tables come from the pinned Class-L calibration curves
(pair domains re-verified, missing pinned pairs rescored through the production runtime):

```sh
python3 experiments/contextual_spacing/yinyangfit_interactive_v3.py SITE [--only <case-id>] [--source-site DIR]
```

To re-derive the frozen source catalogue from captures plus the root catalogue plus fonts
(must reproduce the frozen bytes exactly):

```sh
python3 experiments/contextual_spacing/yinyangfit_interactive_v3.py --write-source-catalogue /tmp/catalogue.json
```

Shipped tables carry exhaustive ordered-domain Class-L curves under search policy
`yinyangfit-search-v2` (recorded per pair and per table); the page rejects
stale-policy or non-Class-L tables and recomputes them on demand.

Verify without a browser server, then with Playwright Chromium over `file://` for
the rendered page:

```sh
node experiments/contextual_spacing/test_yinyangfit_interactive_v3_stage.mjs
node experiments/contextual_spacing/test_yinyangfit_interactive_v3_stage_browser.mjs [SITE]
node experiments/contextual_spacing/test_yinyangfit_interactive_v3_visual.mjs [SITE]
node experiments/contextual_spacing/test_yinyangfit_interactive_v3_explain.mjs [SITE]
node experiments/contextual_spacing/test_yinyangfit_interactive_v3_extended.mjs [SITE]
node experiments/contextual_spacing/test_yinyangfit_interactive_v3_browser.mjs [SITE]
```

Build the self-contained editable demo (single file under
`out/diagnostics/contextual-spacing/yinyang-editable-preview/`, editable preview text over the full captured
Roboto 16 repertoire in both profiles, same engine and shared modules):

```sh
python3 experiments/contextual_spacing/yinyangfit_interactive_demo.py
```

Sliders use the approved numeric bands (interaction target `0..20/0.02`, reach `4..24/1` px, falloff `0.5..10/0.5`,
defaults `8.0/12/2.0` with the target an exploration start, not an optical recommendation); each control also takes
an exact numeric entry inside wider guardrails (target finite `>= 0` with no upper clamp, reach integer `[1, 32]` px
with fractional input rejected, falloff `[0.25, 16]`). The `0.02` step is navigation precision only.
The shipped default-geometry column answers instantly; other settings are scored exactly in the page WASM worker
running the same engine, never interpolated; the normalizer stays frozen at 12 and is never user-controlled.
See the settings policy module (`yinyangfit_interactive_v3_ranges.py`) for the versioned bands.

Focused checks without captures use the retained v1/v2 captures; catalogue coverage and the v3 site need the v3 captures
and site:

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyangfit_interactive_v3.py' -v
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_yinyangfit_interactive_ranges.py' -v
```

### Frozen prerequisites archive (v3 gallery clean-clone inputs)

The staged v3 build reads 26 captures named by the frozen source catalogue (13 cases x Mono/Gray), 26 Class-L
calibration curves, and the 4 shipped runtime files (`pkg-web` and `pkg-nodejs` glue plus WASM bytes). Captures,
curves, and both WASM packages are ignored build outputs. Fonts stay in their owning locations and are never
archived: `fonts/` is tracked with pins in its README, and the Rouge Script font is fetched per the root catalogue
entry (`apps/web/scripts/landing-samples/main-page.json`, URL plus SHA-256). `frozen-inputs.lock.json` pins all 56
member hashes with the catalogue and WASM pins.

Setup is Python 3.10+ with the standard library only; no install step. The NumPy numerical environment above is
needed only for evidence and score commands, Torch only for the historical recovery and training probes, and Docker
only for the TypeFacet probe. None is needed for the archive commands.

The retained archive is local and ignored:
`out/diagnostics/contextual-spacing/input-archives/v3-frozen-1/` (`frozen-inputs.tar.gz` plus `manifest.json`).
A clean clone does not fetch it automatically; carry the directory in by hand and check it where it lands.

```sh
python3 experiments/contextual_spacing/frozen_inputs.py export --archive out/diagnostics/contextual-spacing/input-archives/<new-dir>
python3 experiments/contextual_spacing/frozen_inputs.py verify --archive <archive-dir>
python3 experiments/contextual_spacing/frozen_inputs.py restore --archive <archive-dir> --dest <dir>
```

Export writes a new directory under `input-archives/` and refuses any other location. Verify checks member hashes,
rejects duplicate, corrupt, or unexpected content, and accepts a carried copy at any location. Restore checks first,
then refuses to overwrite differing files or write through existing symbolic links. Run the focused checks from the
owning experiment tests directory:

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_frozen_inputs.py' -v
```

The scale-weighting evidence records the optional pinned notebook identity as provenance only; it never enters
scoring. The default is the repo-relative `experiments/contextual_spacing/yinyangfit_pinned.ipynb` (not supplied):
pass an explicit path as second argument or set `YINYANG_PINNED_NOTEBOOK` when the notebook lives elsewhere. A
missing file records no hash and keeps the existing mismatch gate.

### Predictable spacing-control prototype (optical correction plus letter spacing)

Build the two-control page from the frozen v3 captures (output must be new; per-dataset tables lazy-load from `data/`):

```sh
python3 experiments/contextual_spacing/predictable_spacing.py \
  out/diagnostics/contextual-spacing/predictable-spacing/site
```

Verify the shipped page (defaults to that site):

```sh
node experiments/contextual_spacing/test_predictable_spacing_page.mjs [SITE]
node experiments/contextual_spacing/test_predictable_spacing_browser.mjs [SITE]
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_predictable_spacing.py' -v
```

The
[prototype design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#predictable-spacing-control-prototype)
owns the endpoint, controls and Gray adapter; optical assessment remains pending.

## YinYang oriented engine (experimental Rust/WASM runtime)

Native + WASM port of the frozen oriented-field stages and the corrected
SCORE-v2 interpreter for the browser integration. No maintained crate depends
on it. Leaf docs: [oriented engine](oriented_engine/README.md) (setup and
commands) and [contract](oriented_engine/CONTRACT.md) (API, cache, gates).

```sh
python3 experiments/contextual_spacing/oriented_engine/reference_adapter.py \
  out/diagnostics/contextual-spacing/yinyang-browser-integration/runtime/adapter
cargo test --manifest-path experiments/contextual_spacing/oriented_engine/Cargo.toml --release
cargo run --manifest-path experiments/contextual_spacing/oriented_engine/Cargo.toml \
  --release --bin parity -- ADAPTER_DIR REPO_ROOT
cargo run --manifest-path experiments/contextual_spacing/oriented_engine/Cargo.toml \
  --release --bin bench -- ADAPTER_DIR REPO_ROOT
sh experiments/contextual_spacing/oriented_engine/build-wasm.sh web
sh experiments/contextual_spacing/oriented_engine/build-wasm.sh nodejs
node experiments/contextual_spacing/oriented_engine/smoke/parity_node.mjs ADAPTER_DIR REPO_ROOT
```

Reports land under
`out/diagnostics/contextual-spacing/yinyang-browser-integration/runtime/`
(`REPORT.md` owns the handoff). Optical assessment stays pending.

## Electric Bubble full-field reproduction

Compare the frozen nearest-distance proxy against the author's full-support field mechanism on frozen captures. The
[owner design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#electric-bubble-full-field-reproduction)
states the question and gates; the [report](../../docs/references/electricbubble-full-field-reproduction.md) owns the
verdict. Outputs stay under `out/diagnostics/contextual-spacing/electricbubble-fullfield/`; the pinned reference
checkout is never modified.

Run the Python port (stdlib plus NumPy; no installs) on frozen captures:

```sh
python3 experiments/contextual_spacing/electricbubble_fullfield.py compare OUT \
  --capture out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/captures/roboto-16-mono.json \
  --profile mono --chars "ogThrtnnooHHavToalrise"
python3 out/diagnostics/contextual-spacing/electricbubble-fullfield/summarize_comparison.py OUT/comparison.json
```

`--chars` selects consecutive pairs (`og`, `Th`, …); `--dtype float32` selects the separately named numerical
diagnostic. `kernels` dumps the author kernels; `cells` writes the anchor exchange payload.

Run the independent original-code anchor (pinned tfjs 0.15.3, isolated `js-anchor/node_modules`; first install fails its
native image binding and retries with `--ignore-scripts`, stubbed for the computation path):

```sh
node out/diagnostics/contextual-spacing/electricbubble-fullfield/js-anchor/snapshot_src.mjs
cd out/diagnostics/contextual-spacing/electricbubble-fullfield/js-anchor
node --import ./register_hooks.mjs run_original.mjs --cells ../roboto16mono/cells.json --out ../roboto16mono/anchor.json
```

The anchor runs from its own directory. `snapshot_src.mjs` fails loudly if the reference bytes drift.

Run the focused suite (16 tests; skips nothing):

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_electricbubble_fullfield.py' -v
```

## Electric Bubble scale adaptation

Test the single declared coordinate normalization (`ppem / 72` length/covariance rescaling) with the full-field port
frozen as the raw baseline. The [owner design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#electric-bubble-scale-adaptation)
states the rule, mapping and gates; the [report](../../docs/references/electricbubble-scale-adaptation.md) owns the
verdict. Outputs stay under `out/diagnostics/contextual-spacing/electricbubble-scale/`.

Run the normalized arm on frozen captures (same `--chars`/`--profile` convention; `--dtype float32` is the separately
named numerical diagnostic; `ppem` comes from the capture):

```sh
python3 experiments/contextual_spacing/electricbubble_scale.py compare OUT \
  --capture out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/captures/roboto-16-mono.json \
  --profile mono --chars "ogThrtnnooHHavToalrise"
```

Regenerate the synthetics, paired-domain and dtype evidence from the stored comparisons:

```sh
python3 experiments/contextual_spacing/electricbubble_scale_evidence.py
```

Run the focused suite (12 tests; skips nothing):

```sh
python3 -m unittest discover -s experiments/contextual_spacing/tests -p 'test_electricbubble_scale.py' -v
```

## TypeFacet reference and cell probe

With Docker running, prepare the original source and Python 2 image:

```sh
git clone https://github.com/charlesmchen/typefacet.git \
  out/diagnostics/contextual-spacing/yinyang-alternatives/typefacet
git -C out/diagnostics/contextual-spacing/yinyang-alternatives/typefacet \
  checkout --detach 8c6db26d0c599ece16f3704696811275120a4044
docker pull python@sha256:6c1ffdff499e29ea663e6e67c9b6b9a3b401d554d2c9f061f9a45344e3992363
python3 experiments/contextual_spacing/typefacet_probe.py \
  out/diagnostics/contextual-spacing/typefacet-experiment/run
```

The output directory must be new. `--reference PATH` selects the clean pinned checkout; `--capture PATH` selects the
retained Literata 400/16 capture with `opsz=16`. The probe uses bundled upstream dependencies and writes requests, logs,
profiles, actual input/output UFOs and a comparison summary. Its author-example parameters are diagnostic, not fitted
font defaults. The
[feasibility design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#typefacet-feasibility-experiment)
owns the scope and decision gates.

Run the separate reference-family calibration against the same source checkout and frozen capture:

```sh
python3 experiments/contextual_spacing/typefacet_calibrate.py \
  out/diagnostics/contextual-spacing/typefacet-calibration/run
python3 -m unittest discover -s experiments/contextual_spacing/tests -p test_typefacet_calibrate.py
```

The output directory must be new. The same `--reference` and `--capture` options apply. The run retains its protocol
before evaluation, two fits, leave-one-family-out diagnostics, near-optimal predictions, precision/unit sensitivity and
full UFO parity evidence. It does not add a selectable solver model or update a preview. `--reuse-fits PATH` re-scores
compatible retained searches before reusing them. All near-optimal reference fits are retained; full-alphabet
sensitivity probes use their parameter extrema and the omitted-family fits, avoiding an exhaustive full-alphabet run for
every near-equal grid point.

Generate the separate density-controlled Literata reading comparison from the retained original output:

```sh
python3 experiments/contextual_spacing/typefacet_density_review.py \
  out/diagnostics/contextual-spacing/typefacet-density-review/site
node experiments/contextual_spacing/test_blind_review_browser.mjs \
  out/diagnostics/contextual-spacing/typefacet-density-review/site/index.html
```

The output directory must be new. `--capture`, `--reference` and `--baseline` select the pinned capture, original
TypeFacet output and retained control-page data. Parameters stay frozen. The trial changes only ASCII lowercase pairs
and retains the previous table for every other pair; all seven presets remain available. Its
[design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#typefacet-density-controlled-comparison) owns
the normalization and assessment scope.

Run the separate constrained integer experiment and its reading comparison:

```sh
python3 experiments/contextual_spacing/typefacet_integer.py \
  out/diagnostics/contextual-spacing/typefacet-integer/fit
python3 experiments/contextual_spacing/typefacet_integer_review.py \
  out/diagnostics/contextual-spacing/typefacet-integer/review \
  --fit out/diagnostics/contextual-spacing/typefacet-integer/fit
node experiments/contextual_spacing/test_blind_review_browser.mjs \
  out/diagnostics/contextual-spacing/typefacet-integer/review/index.html
```

Fit and review output directories must be new. The fitter accepts `--reference` and `--capture`; the review accepts
`--fit` and `--baseline`. It automatically runs the full original UFO path and independently checks every selected
integer against those original profiles. The exporter requires that proof to match its inputs. Source and Docker setup
are the same as above. The
[integer experiment design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#typefacet-constrained-integer-experiment)
owns the changed placement policy, calibration and assessment gates.

## Construction-order comparison

Generate fresh tables from the retained captures, selecting both the control and candidate:

```sh
python3 experiments/contextual_spacing/page.py OUTPUT CAPTURE.json \
  --models hu_fitted_density_conserved_touch hu_fitted_full_density_conserved_touch \
  --default-spacing-model hu_fitted_full_density_conserved_touch
```

The construction comparison uses `comparisonModels` in that order and omits `neighborReview`. The default preset
catalogue remains available; `--grayscale-captures` accepts matching default Gray capture paths. For an assembled
four-font comparison, retain `wholeTextVerification` in authoritative `page-data.json` and run:

```sh
node experiments/contextual_spacing/test_construction_browser.mjs OUTPUT/index.html
node experiments/contextual_spacing/test_construction_browser.mjs INLINE/index.html OUTPUT/page-data.json
```

The [design](../../docs/designs/text-layout/contextual-spacing-and-healing.md#construction-order-candidate) defines the
model and its assessment scope.
