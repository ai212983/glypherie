# Repeated-ring fitting experiment

Status: Awaiting visual review, 2026-09-08.

The percent-sign loops have nearly equal source geometry but acquire different
widths during fitting. This experiment coordinates their geometry and grid
placement. It is separate from the uniform candidate and the paper baseline.

## Basis and experimental choices

[Shamir 2003](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf)
§3.4 supports shared dimensions; §3.5 supports reusable complex-feature recipes.
[Microsoft](https://learn.microsoft.com/en-us/typography/truetype/hinting#alignment)
recommends consistent treatment of similar elements at small sizes.

The following recognition and fitting recipe is our extension:

1. Find isolated outer contours containing exactly one counter. Compare curves
   after translation, with a Hausdorff tolerance of 0.004 em. Quadratic curves are
   sampled at 32 intervals per segment. Ambiguous groups larger than two are held.
2. Average corresponding source bounding dimensions and round to the nearest
   pixel. Require room for a counter and at least one pixel on either side.
3. Round the shared source counter offset, constrained to those one-pixel margins.
4. Affinely scale each original outer and inner contour into its respective
   shared rectangle. This retains each contour's curve structure and proportions;
   separate inner/outer transforms can change stroke contrast.
5. Choose integer rectangle origins nearest the existing fitted centers. Half
   ties round toward positive infinity. Quantize control points to 26.6.

These choices replace the fitting of matched components for the experiment. They
are not derived implementations of Shamir's complex-feature recipe or priority
rules. Existing local constraints may be overridden. Advances remain fixed;
ink bounds and spacing to the diagonal can change. The geometry API receives no
character, family or naming metadata. Unrelated points remain unchanged.

## Reproduction and scope

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_repeated_rings.py
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python -m unittest discover -s tools/font_probe -p test_repeated_rings.py
```

Use an empty `tools/font_probe/out/repeated-rings-v1/` output directory.
Inputs are frozen uniform-v3 fonts and verified outside-in variants where
available. Output contains input/source hashes, fitted coordinate arrays, a
measurement report and a gallery. This is an outline-rendering experiment;
encoding the new rule as font instructions remains future work.

All 881 verified outlines were examined. Eleven matched, all percent signs:
Literata and Roboto at 14/16/18/20px; Source Sans 3 at 14/16/20px. This is coverage
of the available verified inputs, not the full font repertoire.

Checks verify shared outer/inner dimensions, preservation of unrelated points,
unchanged unmatched outlines, and stable input hashes. Four unit tests cover
matching, rejection of different shapes, contour order/winding independence,
and ambiguous groups.

Ink bounds changed in Literata 20px, Roboto 20px and Source Sans 3 14px; the gallery
labels them. At Literata 14px both loops now have 4×5px outer bounds and 2×3px
counters. Visual review must also assess roundness, stroke contrast and spacing
from the diagonal: equality of dimensions alone does not guarantee a good shape
or identical pixels. Initial inspection shows squarer loops and close diagonal
spacing in some cases. No rule has been promoted.

## Joint placement diagnostic

`compare_joint_rings.py` produces `tools/font_probe/out/joint-rings-v1/`.
Its geometry-only helper, `joint_ring_placement.py`, recognizes one isolated,
elongated separator between the rings (point-cloud principal-axis ratio at least
3, opposite-side ring centers, separator center between their projected centers).

Shared ring shapes and dimensions remain fixed. The search considers integer
ring origins within one pixel of their source-relative positions around the
fitted separator center. For each pair of origins, it translates the separator
toward the mean position implied by the two source center vectors. Translations
are quantized to 26.6, preserving the separator shape exactly. Selection minimizes
squared source-relative center-vector error plus 0.05 times squared movement from
the preceding fit. Search limits, recognition thresholds and weights are our
experimental policy. Shape-distance and collision constraints are not included;
spacing and rasterized separator quality require visual evaluation.

The 11 cases all reduce center-vector error. Literata 14px decreases from 1.387px
to 0.145px (Euclidean norm across both vectors). This measures center arrangement,
not visual symmetry, edge spacing or bitmap quality. Exact rigid translations
were checked for every component of all 11 pairs. Three additional tests cover
rigidity, missing separators and whole-arrangement translation invariance.

The user correctly flagged the architectural risk: a geometry-only predicate can
still encode a narrow glyph workaround. This two-ring/separator construction has
only percent-sign evidence so far. Keep it as a diagnostic; promotion requires a
broader repeated-component placement model and evidence beyond these cases.

## General component placement diagnostic

`compare_component_placement.py` produces
`tools/font_probe/out/component-placement-v1/`. The user preferred the narrow
joint-placement result; it remains the visual comparison target.

`component_placement.py` replaces semantic ring/separator recognition with a
complete graph of disconnected components. Each component carries all contours
nested inside its outer boundary. Pairwise center vectors come from the source.
The objective is their summed squared error plus 0.05 times squared translation.
No component has an anchor or separator role.

Near-translated components are detected from their combined contour boundaries
at the existing 0.004 em tolerance. These move by integer pixels, searched within
±1px on each axis, to preserve their current grid phases. Other components use
least-squares translations quantized to 1/64px. This phase distinction, center
measure, regularization and search bound are explicit experimental choices.
The search supports up to eight components and four repeated components;
intersecting roots and invalid contours are held. Single components stay fixed.

All 881 verified outlines receive the rule. It applies to 112 cases; 45 change
pixels, across `!`, `%`, `;`, `=`, `?`, `i`, `j`, and `k`. `changes.html` contains
every pixel change, `percent.html` compares the motivating cases, and `index.html`
includes every applicable case, including unchanged bitmaps. Reports also record
coordinate changes, bounds, source-vector errors and differences from the
preferred narrow result.

Every applicable component passes an exact rigid-translation check. Four tests
cover general repetition, non-repeated components, contour reordering/winding,
and the single-component control. Fractional placement can still change pixel
weight or edge spacing; geometry preservation is not visual approval. The rule
currently has no collision or raster-quality objective.

The upstream repeated-ring **size** experiment remains as a controlled input.
This experiment generalizes placement only; shared sizing still needs a broader
model before adoption. No candidate or production pipeline was changed.

Visual inspection of all 45 changed cases found regressions from fractional
phase movement: Roboto 20px `i` develops a split-looking dot, and several
exclamation/semicolon dots acquire uneven corners. Thus center relationships
alone are insufficient to select placements. Future work needs a general way to
preserve component raster quality while evaluating their joint arrangement.
Literata 16px `k` also exposes a severely distorted input already visible in the
before column; the new placement is not a remedy for that upstream defect.
There are 78 coordinate-changing cases, including 33 with unchanged bitmaps.
The general placement experiment remains unadopted.

## Rejection and acceptance-criterion investigation

The user rejected general component placement after observing regressions,
including unnecessary changes to Roboto 16px `%` and failure of Source Sans 3
18px `%`. Retain the narrow joint experiment as the preferred experimental
reference. The general placement version is rejected for adoption.

Source Sans 3 18px has equal source outer dimensions (298×414 font units) and
counter dimensions (173×312). At 18px/1000 em these round to 5×7 and 3×6 pixels.
The one-pixel-per-side sizing guard rejects the one-pixel total vertical margin,
so the ring-sizing stage returns no pair. General placement nevertheless detects
the source repetition and moves only the separator +0.5625px in x. It changes
13 pixels while preserving the existing unequal loop geometry. This is a sizing
feasibility failure followed by an insufficient placement operation, not a missed
source-repetition match in the placement stage. The earlier ring gallery's missing
18px case was a rule applicability outcome, not missing repertoire coverage.

The general experiment starts from independently placed shared-size output, not
from the preferred joint output. Roboto 16px therefore moves the upper loop down
1px, the lower loop right 1px, and the separator by (+0.0625, −0.109375)px relative
to that earlier input. Its output differs by 25 pixels from the preferred joint
result. A decrease in its center-vector objective does not prove improvement
over the preferred reference.

A simple diagnostic rotates the whole binary bitmap 180 degrees around its ink
bounding-box center and counts symmetric-difference pixels. Roboto 16px has 12
unmatched pixels in the preferred output and 16 in the general output; Literata
14px has zero in both. This catches this regression but is not a universal quality
score: an acceptable bitmap can have nonzero mismatch, and source designs can be
intentionally asymmetric. Requiring perfect symmetry would contradict the user's
acceptance of the Roboto reference.

### Proposed conservative acceptance contract

1. Compare against the current preferred result. Include doing nothing as an
   explicit candidate, independent of the continuous solver's objective.
2. Require a diagnosed failure of a source-supported relation: repeated-component
   dimensions, balance, alignment or clearance. A smaller source-center residual
   alone is insufficient evidence for changing the bitmap.
3. For a placement-only pass, compare each component's raster mask after removing
   integer translation. Preserve that mask, its holes and connectivity. Integer
   translations satisfy phase preservation; fractional translations need the
   actual raster comparison. This conservative requirement will also withhold
   some potentially beneficial changes for separate visual review.
4. Require improvement of the diagnosed relation while preserving other measured
   relations and clearances. Prefer the unchanged bitmap on ties or conflicting
   evidence. Use source symmetry only where source geometry supports it.
5. Report sizing infeasibility explicitly before attempting placement as its
   remedy. Source Sans 3 18px needs a joint outer/counter rounding investigation;
   center movement cannot resolve its unequal sizes.

These are proposed acceptance requirements, not an implemented universal visual
metric. Detection tolerances and acceptable raster asymmetry still need calibration
against human-reviewed examples, including acceptable nonzero asymmetry. Existing
rasterization, candidate code and galleries remain unchanged by this investigation.

[Microsoft's basic hinting tutorial](https://learn.microsoft.com/en-us/typography/truetype/hinting-tutorial/hinting-and-truetype-instructions)
controls corresponding curve widths, grid positions and interpolation explicitly.
It does not specify this automatic no-change gate. Likewise, the shared-feature
mechanisms in Shamir do not supply a bitmap-quality acceptance test. The proposed
contract is our conservative extension, with human review retained.
