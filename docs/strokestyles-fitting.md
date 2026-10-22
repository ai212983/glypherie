# StrokeStyles-assisted diagonal fitting (prototype)

Owning design for `experiments/strokestyles_fitting/`. Read with the [evaluation rules](evaluation.md) (research before
implementation, sourced models, no per-glyph tuning, tests are not optical acceptance), the
[experiment rules](../experiments/AGENTS.md) and the [Hobby fitting model](hobby-fitting.md). Verification runs through
the evaluation rules; nothing here authorizes renderer adoption or publication changes.

## Question

The current source-relative policy couples straight strokes to a fitted upright anchor only for wholly straight
single-contour shapes with rectilinear anchors
([valid straight medial intervals](hobby-fitting.md#valid-straight-medial-intervals)). On Roboto 16 px
(`font_hints_auto`), the upright stem of `i` shrinks 1.453125 px to 1 px while diagonals `k`/`y`/`x`/`v` stay near
1.3-1.4 px and `z` grows 1.342 px to 1.653 px.

Can pinned upstream StrokeStyles structural analysis supply the missing stroke/junction structure (spine paths P, width
profiles W, stroke regions, connectivity and junctions) so that diagonal normal-width changes couple conservatively to
already-fitted upright standards, while crossings, joins, tips and attachments stay safe? This document owns the
extraction and experimental fitting stages. Neither stage is selected by the maintained renderer or web app.

## Sources and what each one owns

- Stroke decomposition: Berio, Leymarie, Asente and Echevarria, "StrokeStyles: Stroke-Based Segmentation and Stylization
  of Fonts" (ACM Trans. Graph., 2022), canonical project page
  <https://doc.gold.ac.uk/autograff/post/papers/strokestyles_2022/>. Interior/exterior medial axes (section 4.1),
  curvilinear shape features (4.2), concavity links (section 5), seven junction types (section 6: half, T, Y, L, stroke
  end, protuberance, null), iterative junction identification (section 7), spine plus variable-width stroke
  representation with connectivity (section 8). The prototype consumes structural analysis only (paths P, width profiles
  W, stroke regions, connectivity, junctions), never stylization or reconstruction.
- Upstream implementation pins (verified by direct clone, full SHAs): `strokestyles`
  3a74c98df66e9053aabf2a0299bbba188d270153, `autograff` 9352fcccad9950149fe96eb0d88f40dbb8bf99d9, `csfs`
  d24f33e3f0bb0508852131c62bf9bcc7c6c2ed5c, `cautograff` 4566a3741c0008c4b555f41e8e9ffc9ecd7bc70f, `scikit-geometry`
  e4a25c0cde054a3a4bd6b21d3ca30db8e7e6a178. Compatibility-only container patches are retained beside the runner with
  provenance; upstream sources themselves are unmodified.
- Width coupling (consumer stage): Hobby (4)/(5) and (17) via the existing `experiments/hobby_fitting` solver; the
  anchor remains an upstream-fitted rectilinear pair (Hobby section 3.3), never a pixel-selected target.
- Placement continuity: Hersch 1993, sections 5-6, and the VTT `DStroke` diagonal primitive motivate freezing
  junction-owned coordinates; the consumer preserves native-owned coordinates, advances, contour order and outline
  operators exactly.

StrokeStyles is structural analysis, not proven grid fitting. Its sampled polylines are annotations over the source
outline, never replacement geometry.

## Extraction records

`runner/run_extract.py` (explicit CLI only; nothing runs by default) writes one JSON per run under
`out/diagnostics/strokestyles-fitting/`. Top-level provenance carries `font_sha256_original`,
`font_sha256_instantiated`, `axes_resolved`, `units_per_em`, extractor and sibling repo commits, runner version and file
hash, schema version, shape size, curve sampling, seed, full package versions, native binding hashes, pinned base digest
and runtime image id. Glyphs are keyed by char; each holds strokes (`P` spines and `W`/`Wv` radii in font units y-up,
`W_full` as 2r), `connectivity`, `junctions`, `original_contours`, `unioned_contours`, `union` ink check, the full
`identity` record, `cache_key` and per-stage `timing_ms`. Per-char provenance is deep-copied so glyph metadata cannot
mutate across chars.

- Coordinates: upstream returns spines in original font units, y-up (its resampler divides by its own ratio); the runner
  maps to pixels by `size_px / units_per_em` only, retaining ratio, bbox and upm as provenance.
- Analysis shape: the upstream TTF loader (`common.load_glyph`) unions with nonzero fill before resampling, so list
  input receives the identical single-union treatment; the original contours stay in the record beside the union
  actually analyzed, with summed/unioned areas and overlap fraction.
- Variations are instantiated with the complete resolved axis set before analysis; static fonts pass through;
  out-of-range or unknown axes fail.
- The cache key hashes one canonical identity: font bytes (original and instantiated), resolved axes, char, outline
  flavor, shape size, curve sampling, seed, extractor and sibling repo commits, runner version and file hash, full
  package versions, native binding hashes, pinned base digest and runtime image id. A hit must equal the full identity;
  any drift re-extracts. Two uncached runs must agree ignoring `timing_ms`.

## Adaptation boundaries

1. Only pinned upstream output counts as StrokeStyles structure. No substitute recognizer lives in this experiment;
   fabricated or hand-drawn strokes must never be presented as StrokeStyles output.
2. Flattening expands implied on-curves at segment midpoints and wraps all-offcurve contours through the end midpoint;
   triple joints are exact and subdivision stays inside the control hull (tested against actual glyf).
3. No per-glyph, per-row or per-pixel parameters. No thresholds selected from reported glyph pixels.
4. The consumer stage (separate ownership) decides eligibility, abstention and fitting; extraction records alone
   authorize no renderer change.

## Decision gate

Extraction succeeds when real pinned-code runs on the corpus produce machine-readable records with validated provenance,
timings and ink checks. Consumer fitting needs its own applied/abstained evidence; geometry or raster damage rejects the
candidate. Closure follows the [iteration lifecycle](revisions/README.md#iteration-lifecycle): open questions stay in
this document's limitations until reviewed.

## Experimental fitting

`native` captures source, automatic and selective-font-hint reports through the maintained generator APIs. Its raster
adapter uses the maintained FreeType mono scanner, scan metadata and terminal policy; unchanged captures must reproduce
their recorded frame, coverage and pixels before candidate raster comparisons.

`fit.py` leaves captures unchanged unless `--enable-strokestyles` is supplied. Disabled execution neither loads analyses
nor imports the fitting solver. Enabled execution matches analysis to the original font hash and complete resolved axes;
the same font-unit analysis can serve different pixel sizes. Source outlines, rather than fitted or raster outlines,
determine correspondence.

The adaptation uses imported stroke annotations to identify opposing straight borders, then the existing Hobby
medial-interval model to certify width stations. Fitted upright pairs from the same font, axes and size supply the
relative width standard. The least-squares fit couples diagonal stations to that standard while retaining
source-relative position, stretch and bend terms. This extension of StrokeStyles annotations to the Hobby model is a
project hypothesis, not a capability demonstrated by the StrokeStyles paper.

Native-owned coordinates, upright anchors and junction-owned vertices remain at their upstream positions. Uncertain
native ownership reserves both axes. Movement is bounded by retained stroke width with 26.6 headroom; quantized
candidates must reduce the coupling residual and preserve winding, crossings and containment. Unsupported curves,
uncertain border assignments, missing medial intervals and invalid candidates keep the upstream outline with an explicit
abstention reason. Synthetic straight-stroke fixtures test algebra and ownership only and are tagged separately from
upstream extraction data.

The station-coherence guard is a conservative project hypothesis over Hobby's relative-width functional and common
anchor target. It rejects achieved station disagreement larger than the movement budget divided by a representative
source width. This bar is not derived or validated by Hobby; its purpose is to abstain when a single coupled pair
narrows at one station and widens at another. The budget uses the narrowest retained width, so wider pairs face a
stricter bar. It requires broader geometric assessment before adoption and gives no optical guarantee.

## Prototype assessment

The independent control matrix contains Roboto and SourceSans3, weights 300/400/700 and sizes 12/16/20, with 15 glyphs
per case and both hint modes: 540 fitted records. Unchanged native raster reproduction matches all 540 frames, coverage
arrays and delivered bitmaps. Disabled fitting preserves all commands and recorded metrics in both modes. The capture
CLI also reproduces the independently captured Roboto 16 px default case exactly.

Real analyses match 108 records per mode: Roboto 400's 15 glyphs and seven glyphs each for Roboto 300/700 and
SourceSans3 400. The other 162 records per mode abstain because matching analyses are absent. Of the matched cases,
seven selective and eight automatic fits apply; all affect `k`, except automatic Roboto 400 `A` at 20 px. Fifteen
applied outlines produce eight changed delivered bitmaps and seven identical bitmaps through the captured raster policy.
These are mechanical activity counts, not a quality score.

- **Unchanged reported concern:** Roboto 400 at 16 px leaves `k/y/x/z/v` unchanged. Curves, uncertain dominance
  intervals, crossing structure and the straight-run classifier still prevent the intended intervention. The prototype
  does not resolve the reported default diagonal weight. The applied Roboto 400 cases at 12/20 px also retain identical
  delivered bitmaps, despite outline movement.
- **Pending assessment:** Roboto 700 `k` narrows at 16 px and widens at 12/20 px toward the upright's relative change.
  SourceSans3 400 `k` widens at 12 px and narrows at 16/20 px. Its 16 px bitmap stays identical; the 12/20 px outputs
  have both added and removed pixels, requiring assessment of placement, joins and retained shape as well as weight. No
  browser optical acceptance has been performed, and these outputs are not published app candidates.
- **Rejected internal candidates:** the station-coherence guard rejects contradictory width changes in `A` at 12 px. The
  topology guard rejects selective `A` at 20 px, where bounded movement alone did not preserve crossings and
  containment. Both emit the exact upstream fallback; the invalid candidates are not delivered.

Detailed measurements remain under `out/diagnostics/strokestyles-fitting/verification/host-final-native.json` and the
per-mode fitting outputs. The prototype stays separate from the
[current iteration's renderer scope](revisions/001/03-spacing-kerning.md).

## Limitations

- Extraction requires the host-built image (native `cautograff` plus `skgeom` arrangement); the runner reuses that image
  without rebuilding for code edits.
- First extraction (image `sha256:7b3d…077fa3`, runner mounted read-only): 15/15 glyphs of `lIitfnhkyxzvAVW` extracted
  cold into `out/diagnostics/strokestyles-fitting/extraction/roboto-cold-01.json`. Per-glyph cold extract 318–2966 ms;
  process wall 28.1 s cold, 2.0 s warm with ~1 ms cache reads. Cold==warm ignoring `timing_ms`, and two uncached `x`
  runs are identical with the same cache key.
- Structural findings (evidence for the consumer, not acceptance): `k` yields 3 strokes with 2 T-junctions; `x` yields 2
  strokes with 2 crossings; `z` yields 1 stroke with 2 elbows; `v` yields 1 stroke with 1 elbow. Union merges were `k`
  3→1 overlap 0.045, `y` 2→1 overlap 0.040, `v` 2→1 overlap 0.044, `z` 3→1 overlap 0.065, `x`/`i` unchanged at 0.000.
  Stem `W_full` ≈ 186 font units, i.e. 1.45 px at 16 px, consistent with the reported 1.453125 px upright source width.
  These describe this corpus only.
- Requested weight controls on the exact baseline font (original SHA `d7598e12…` confirmed, resolved axes exactly
  `wght`/`wdth`): `extraction/roboto-wght300-wdth100.json` and `extraction/roboto-wght700-wdth100.json`, chars
  `lIkyxzv`, 7/7 each, no errors, walls 10 s each, extracts 241–1069 ms. Families agree with the default-axis run (`k`
  T, `x` crossing, `z`/`v` elbow); at wght 700, `y` labels Y-branching instead of T and `v` gains a second elbow, and
  `z` overlap rises 0.044→0.125 — weight-dependent labeling/ink, assessment material for the consumer, not a verdict.
- Additional diagnostics (same frozen setup), kept as labeled; no deletion: RobotoFlex `wght=300/wdth=100` and
  `wght=700/wdth=100` plus SourceSans3 `wght=400`, chars `lIkyxzv` (21 glyphs, all extracted, no errors) in
  `extraction/robotoflex-wght300-wdth100.json`, `robotoflex-wght700-wdth100.json` and `sourcesans3-wght400.json`.
  Instantiated SHAs differ per axis set while the original file SHA is stable; SourceSans3 upm is 1000
  (Roboto/​Flex 2048) and its font default is `wght=200`, so the run records requested 400 against resolved defaults.
  Junction families agree across weights and families for `k` (T), `x` (crossing) and `z`/`v` (elbow), except RobotoFlex
  700 `y`, which labels Y-branching plus null instead of T — assessment material for the consumer, not a verdict. `x`
  overlap grows with weight (0.054 at 300, 0.099 at 700). Cold per-glyph `extract_ms` excludes shaping I/O; the 0.4–0.8
  s/glyph re-instantiation inside `_reopen` is counted in `flatten_ms`, and consolidating it is a deferred follow-up
  that would alter the runner hash during verification.
- Width coupling reuses the least-squares Hobby prototype: residuals are evidence per constraint group, not an
  acceptance score.
