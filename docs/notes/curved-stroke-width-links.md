# Displaced curve extrema and stroke-width links

Status: experimental correction; visual approval pending.
Reviewed: 2026-09-08

## Confirmed gap

The frozen Literata 14px model has no vertical bow-width features for O and 0.
Their outer and inner extrema differ in height by 15–22 font units. The detector's
0.012em alignment cutoff is 12 units, so it drops those pairs. Independent inner
edge anchors then round separately from the outer placement/width constraints.

| Glyph | Source side widths at extrema | Upstream fit | Candidate |
| --- | --- | --- | --- |
| Literata 14 O | 1.484 / 1.526 px | 1 / 2 px | 2 / 2 px |
| Literata 14 0 | 1.442 / 1.456 px | 2 / 1 px | 1 / 1 px |

This is a missing relationship in feature recognition and construction, rather
than a solver arithmetic failure or merely the source's slight asymmetry.

## Source basis and experimental choices

Shamir 2003 §§3.3–3.5 recognizes bows/arcs and connects their sides through Dist or
PDist, with nearby recurring measurements supplied by global font tables. See the
[paper](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf).
Microsoft's [O tutorial](https://learn.microsoft.com/en-us/typography/truetype/hinting-tutorial/hinting-and-truetype-instructions)
coordinates opposite curve weights and interpolates remaining points. Its
[VTT explanation](https://learn.microsoft.com/en-us/typography/truetype/fixing-rasterization-issues)
uses common control values to control near-equal widths and anchors extrema before
IUP interpolation. These establish the width-link strategy; the following
recognition and integration policies are project interpretations.

- `recognize(..., curved_support=True)` pairs smooth extrema of the same kind
  with opposed tangents. Each extremum must lie in the other's tangent-coordinate
  support interval, bounded by adjacent opposite-axis extrema or corners. Their
  connecting segment must lie inside ink. Mutual unique nearest projected-width
  matching resolves competing partners. The fixed alignment cutoff remains in
  the frozen/default profile; this opt-in replaces it for the experiment.
- A newly recognized pair activates its axis. Recognized widths on that axis
  within the geometry distance tolerance (0.003em total cluster span) share their
  mean and nearest-integer pixel width, with a one-pixel minimum. This local
  clustering is an explicit stand-in for font-wide CVT classification, not a full
  implementation of the paper's global statistics.
- Outer extrema retain their upstream placement. Inner extrema follow by the
  shared width. Additional displacement is interpolated using source coordinates
  and fontTools' IUP routine between anchored extrema and owned points. The other
  coordinate is preserved. This incremental composition retains previous fitting
  work; it is not a claim to reproduce a complete VTT hint program.
- Existing metric/parameter relationships, coordinate ownership, source movement,
  cardinal edge order, counter count and native coordinate reproduction are
  checked. Conflicts remain explicit diagnostics. Disconnected components are
  deferred, preserving the percentage-last review order.

Recognition and fitting receive geometry; glyph identity is used only by the
font adapter, report and specimen selection.

## Coverage and review

The 881-case screen produces 51 changed candidates, 139 already-consistent cases,
521 without new pairs, 110 deferred disconnected cases, 49 upstream rejections,
and 11 held metric/parameter conflicts. All 51 changed panels were visually
inspected. Side-weight imbalance improves in the primary O/0 cases; other changes
include bowl weights and arch thickness. Existing irregularities remain, notably
Literata 16 Q's bowl/tail junction. Numerical admission is not visual approval.

Protected relationship changes were zero in admitted candidates. Native export
error was below 1/128px. The visual page contains all admitted bitmap changes;
held cases are listed separately in diagnostics. The comparison's current column
matches the prior source-balance comparison, including the unapproved isolated
lowercase-o experiment where present. The source-balance fit itself is excluded.

Review: `tools/font_probe/out/curved-width-links-v1/index.html`.

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe tools/font_probe/.venv/bin/python tools/font_probe/compare_curved_width_links.py
```

Twenty-three focused tests pass. A separate full changed-case raster check found
no increases in eight-connected black components (diagonal pixel contacts count
as connected). Focused tests cover displaced extrema, reversed winding, contour start changes,
subdivision invariance, rejection of white-space links, linked widths, retained
outer placement and ownership conflicts. Adoption remains a separate decision.

## Bounded source reconstruction (v2)

User review identified a top-right artifact in Literata 14 zero, a squashed
Literata 14 a, and a bold upper-right pixel in Literata 16 p. Incremental IUP
translated the counter tops by approximately half a pixel while retaining the
old outer curves. For a, the upper width link also pulled its middle stroke down.

`curve_reconstruction.reconstruct` now bounds affected runs at corners and
line/curve tangencies. It retains their junction coordinates, fitted extrema in
the active axis, and previously owned coordinates. It reconstructs intervening
coordinates from source IUP ratios instead of adding interpolated displacement
to an already deformed curve. Outer and inner runs are both reconstructed; the
other axis and unrelated runs retain their upstream values. Source control-edge
order is checked: a width target that folds a curve past its retained junction
is held. This is an opt-in composition experiment with the same width policy.

The 881-case rerun has 43 changed candidates and 19 held cases; other counts are
unchanged. All changed panels were inspected. Zero loses the extra top-right
pixel while retaining 1/1px side widths; p loses the added upper pixel while
retaining its 2px right side. The a change is withheld because its upper-width
target conflicts with the retained curve junction. Its prior shape remains an
open defect, rather than being reported as fixed. Eight additional candidates
are withheld by the source-order check compared with v1.

Twenty-four focused tests pass, including source-proportional round tops,
junction conflict rejection, and exact preservation of an unrelated contour.
All 43 admitted changes preserve protected equations and counter counts, remain
within native export tolerance, and introduce no extra eight-connected black
components. These checks establish implementation properties, not approval of
all curve shapes.

Review: `tools/font_probe/out/curved-width-links-v2/index.html`. Compare the
rightmost bounded-source candidate to the current and previous width candidate.
Withheld changes show the retained current rendering and the conflict reason.

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe tools/font_probe/.venv/bin/python tools/font_probe/compare_curved_width_links.py --reconstruct-curves
```

## Original geometry and coordinate-specific junctions

The v2 rendered candidates were approved. Investigation of the retained Literata
14 a then found that intermediate export changed smooth half-unit curve joins
into 2.91° and 2.59° turns. Reclassifying that exported font created false corners.

The source-junction experiment repeats the original overlap-normalization step,
then retains the prepared source's fractional coordinates and classifications.
It verifies that their rounded coordinates and contour endpoints match the
existing native point layout before attaching source metadata. An initial check
without overlap normalization found incompatible layouts; repeating the canonical
preparation removed that mismatch. No nearest-point guessing is used.

Line/curve attachments remain structural boundaries in both coordinates.
Curve/curve turns follow interpolation, while extrema protect their own axis.
Previously owned coordinates remain protected. Paired smooth extrema also retain
source tangent-coordinate offsets when both sides are in the affected region;
conflicting anchors or coupled dependencies remain explicit failures. These are
experimental composition choices. The original/default profiles are unchanged.

The 881-case comparison against approved v2 has 16 changed bitmaps, 34 identical
bitmaps after reconstruction, 146 already-consistent cases, 514 without new pairs,
110 deferred disconnected cases, 49 inherited rejections and 12 held conflicts.
All 16 changed panels were inspected. Literata 14 a gains one upper-curve pixel
without moving the middle stroke; Literata 14 zero remains identical to approved
v2. However, Literata 16 p reintroduces the upper pixel at (6, -7). Source geometry
and endpoint relationships alone do not preserve the complete fitted upper arc.
This experiment is therefore **unpromoted**, with that regression still open.

Twenty-six focused tests pass. They include a smooth fractional join that becomes
a corner after rounding, source-proportional reconstruction, junction protection,
width links, and explicit conflict handling. Native coordinate checks, protected
relationships, cardinal edge order and counter counts pass for admitted outputs;
these checks do not supersede the known visual regression.

Review: `tools/font_probe/out/source-junctions-v1/index.html`.

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe tools/font_probe/.venv/bin/python tools/font_probe/compare_curved_width_links.py --source-junctions
```
