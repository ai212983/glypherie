# Contour order and curve reflection

Status: Python experiment; broader symmetry remains unresolved.

## Contour repair

Roboto 14px 7 inherits a lower top-bar corner at y=10.547px while the bar is at
10px. The source corner is below the bar. Its vertical alignment and diagonal
intersection constraints produce this local inversion; the displacement remains
below the previous 2px admission threshold.

`outline_relationships.recover_order` identifies reversed, adjacent on-curve
cardinal edges. It restores their source signed separation through a constrained
solve, retaining original metric/global equations and minimizing movement from
upstream geometry. Those source-separation equations remain hard in the later
joint and reflection solves. This is a geometric experimental replacement of an
invalid intersection, not a recovered paper rule. It uses no glyph identity.

Collapsed edges are distinct from reversed edges and are not repaired by this
rule. A conflict with owned geometry rejects the proposal. Exported results are
also checked for cardinal-edge reversal. The rule does not prove arbitrary
curve topology or diagonal intersection correctness.

## Curve correspondence prototype

The exact source-point matcher remains first. If it fails, quadratic contours
are sampled as linear combinations of source points: sixteen samples per segment
and 256 approximately equal arc-length samples per contour. Reversed cyclic
correspondence can pair different contours. Unique, mutual correspondence must
meet the unchanged em/512 source tolerance. Sixteen sample pairs per contour
supply reflection equations to the existing constrained solver.

This tests geometry beyond control-point indexing. Discrete sample phase can
still miss correspondences; the fallback is conservative. Earlier exact matches
are retained. Sampling alone does not justify erasing optical source asymmetry.
Translation/repetition relationships, horizontal-axis reflection and local
component symmetry remain separate capabilities.

## Results

`tools/font_probe/out/cumulative-hinter-v6/changes.html` shows all 18 bitmap
changes. The full screen covers 881 cases: 766 joint fits, 66 holds and 49
rejected baselines. Rejection membership changes even though the totals match v4.
There are 23 admitted cases with source-separation repair claims.

Roboto 14px 7's top artifact is removed. All eighteen changed panels were inspected;
Z/z and 4 silhouettes also change and require user review. Source Sans 3 20px
period and colon are the two additional curve matches. The colon gains a wider
bottom dot, so left/right symmetry alone is insufficient to approve it.

All previously successful exact reflection matches remain successful. No exported
admitted result has a reversed cardinal edge. All 4,681 exported coordinate-owner
claims agree within numerical precision (maximum error approximately 2e-15px).
Twenty-eight focused tests pass, including cross-contour reflection correspondence,
asymmetric-source rejection and metric-preserving inversion recovery.

The reported Literata +, 0, O, T, o, ! and quotes and Roboto 8 remain unmatched
or held. Sampled source mismatch at 16px is approximately 0.08-0.13px for the
reported Literata punctuation/curves, above the 0.03125px cutoff. These measurements
include sampling error; they are not proof that every difference is intentional.
A further experiment needs source-relative component relationships and finer
phase correspondence, not an unreviewed increase in tolerance.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_cumulative_hinter.py
```

The output adapter compares with v4 where available; when v4 rejected a case,
the baseline column is explicitly labeled as geometric context. The provisional
v5 run replaced exact matching and lost existing matches; it is superseded by v6.

The user accepted the rendered v6 changes, including 4 and Z. Literata 14px Z
terminals remain a deferred defect. This is approval of the reviewed changes,
not of rejected cases or the whole hinter. The next isolated experiment is
[repeated-component symmetry](repeated-component-symmetry.md).
