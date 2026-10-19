# Hobby fitting model

<!-- cspell:words Hobby's NumPy SVD lstsq Zeno Bernstein Sutherland Hodgman -->

This document owns the design and findings for the isolated Hobby geometric experiment in
[experiments/hobby_fitting/](../experiments/hobby_fitting/README.md). The experiment assembles and solves a small,
coupled geometric system from [Hobby's fitting model](references/papers/1993-hobby/README.md). It operates on synthetic
supplied features, without loading fonts or changing the generator. Read the
[equation audit](references/papers/1993-hobby/audit.md) for checked notation, report-version discrepancies and remaining
source uncertainties. Classification and optical assessment follow the [evaluation rules](evaluation.md).

## Source model and adaptation

The coordinate unknowns are displacements of source endpoints and cubic controls at nominal scale one. All feature
correspondences and normals remain fixed coefficients. A `Sample` is a supplied affine combination of those controls;
its cubic constructor uses the Bernstein weights from (31). A shared vertex has one pair of unknowns, including when
several features refer to it.

| Prototype operation      | Source and relationship                                                                                                                                                                                                                                                                                          |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `edge`                   | (1) integrates squared normal displacement exactly for a straight segment; (2),(3) penalize relative stretching and bending in its original frame.                                                                                                                                                               |
| `pair`, `preserve_width` | (4),(5) use twice the supplied medial radius and signed projected relative width error. Ink and white-space features are explicit inputs, as in §3.2. The midpoint default is only for constructed synthetic contacts.                                                                                           |
| `match_width`            | (17) couples changes relative to source widths, preserving intended contrast rather than forcing identical widths. Caller supplies eligible feature pairs; mixed ink/white matching is unsupported.                                                                                                              |
| `offset`                 | (11)–(13) evaluate caller-supplied signed integer offsets with the finite printed weights. Their components remain in the absolute pixel grid. No rounding or offset search occurs.                                                                                                                              |
| `curve`                  | (31)–(33) sample normal displacement at parameter midpoints; source tangents and midpoint-speed arc weights are frozen.                                                                                                                                                                                          |
| `solve`                  | Continuous least squares with caller-frozen controls eliminated. [NumPy `lstsq`](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html) supplies a minimum-displacement-norm solution when the system is deficient; rank is reported. This does not implement Hobby's integer/lattice solver. |

**Project adaptation for curve shape:** apply (2),(3)'s stretching/bending construction to the cubic derivative at each
sample. With original derivative $q'$, derivative displacement $\delta q'$, speed $s=\|q'\|$ and midpoint arc weight
$\Delta\ell=s/k$, the residuals are

$$\sqrt{\alpha_2\Delta\ell}\frac{q'\cdot\delta q'}{s^2},\qquad
\sqrt{\alpha_3\Delta\ell}\frac{(q'_y,-q'_x)\cdot\delta q'}{s^2}.$$

This follows the local relative-strain construction of (2),(3) and §6's linear control-point representation. It is not a
verbatim formula from the report, an exact curvature constraint or a nonlinear closest-point calculation. It reduces to
the original edge measures for a linear cubic. The supplied examples use 16 midpoint intervals; a convergence test
checks the quadrature separately. Automatic adaptive subdivision and medial-axis extraction are outside this tool. Using
$25/H$ for both derivative measures transfers the straight-edge weights as a project hypothesis; the report does not
independently establish their balance against curved-stroke width changes. The normal sign differs between `edge` and
`curve`, following their source expressions; it is inert for those squared shape terms. Offset signs remain fixed.

The normal-only curve negative control remains in the JSON: it demonstrates why (33) alone is insufficient for this
experiment. The concentric cubic correspondences are supplied radial approximations, not claimed exact medial contacts
on arbitrary curves. Positive projected sampled widths do not prove the whole curves remain valid or nested.

The source weight $\psi_1$ retains its printed denominator **9 radians**, giving a 90°/parallel weight ratio of about
0.970. Its width difference scale is explicitly 0.7 pixels. Changing coordinate units requires changing this scale and
$H$ together; geometric unit-rescaling tests do so. Integer targets and the absolute pixel grid intentionally break
arbitrary rotation and size invariance. The rotated examples use integer offsets supplied in each example's absolute
grid, not rotated fractional offsets.

## Experiments and findings

The deterministic examples use the source's suggested weights, $H=14$, and supplied targets. They are algebraic
experiments, not font-specific fitting policies or optical acceptance:

- Two straight stems: one supplied offset and a coupled width-change measure move both stems, including at 30° and 45°.
  At 0°, the source widths 1.265625 become approximately 1.000015 and 1.040643. Finite penalties permit residual error;
  the second stem has no independently supplied integer target. Arbitrary-angle projection can also increase width.
- Curved paired borders: the derivative-shape adaptation limits maximum control movement to about 0.189 px, compared
  with 39.714 px for the normal-only negative control. This demonstrates missing shape control in the incomplete model,
  not proof of safe general curve fitting. Both achieve approximately 0.97950 px at the constrained sample, from 1.26588
  px. The sampled widths still vary appreciably near the supplied target.
- Square ring: both supplied ink widths become approximately 1.000008 px while the white feature grows from 3.6 to
  3.756027 px. The counter stays open in this construction; no general counter-preservation guarantee follows.
- A shared T-junction fixture keeps its caller-frozen vertex exact while adjacent geometry moves. A completely frozen
  incompatible width reports nonzero offset residuals. The solver does not label that outcome successful fitting.

Tests cover the exact displacement integral, stretching/bending, relative contrast, radius versus chord, coupled width
response, geometric translations/rotations/unit changes, fixed-grid projection, curved shape and quadrature, supplied
counter relationships, frozen junctions and invalid inputs. There is no automatic feature ownership, movement bound,
self-intersection check, topology guard, fallback policy or source-font corpus comparison yet. Residuals are evidence
per constraint group, not a quality or acceptance score.

The remaining audited equations are also outside this prototype: (6)–(10) integer-adjustment recognition and
feasibility, (14)–(16) symmetry, (18)–(22) alignment and font-wide parameters/clustering, and all §5 solver/encoding
machinery.

## Raster controls

`strip_area` clips a pixel square against two straight-strip half-planes using
[Sutherland–Hodgman clipping](https://juliageometry.github.io/MeshesDocs/dev/algorithms/clipping/), then computes
polygon area. This is an analytic control with no curves, contour overlaps or dropout. `strip_pixel` compares a
half-open center-fill rule, exact area compared with 128/255, and an **analytic 4× analogue**. The analogue rounds each
exact subcell area to 8 bits and applies the current generator's reduction arithmetic: sum `(sample+8)//16`, saturated
at 255, then threshold 128. It does not substitute for Zeno captures or establish native/WASM parity.

A width-one vertical strip from X=0.5 to 1.5 has one center-fill column under the stated boundary convention, but each
of its two half-covered columns receives analytic 4× coverage 128 and becomes black. Exact area at 128/255 would select
neither column. Thus even this integer-offset construction does not carry a center-fill guarantee through quantization,
reduction and binary conversion. Tests also check exact diagonal areas and conservation across a rational slope's
repeat. The project's real coverage path and optically assessed font corpus remain necessary before adoption.

## Next implementation boundary

This prototype establishes a reproducible geometric experiment. Before renderer integration, resolve feature extraction
and confidence, supported black/white groupings, integer target selection, movement and junction ownership, curve
validity, counter guards and raster-aware evaluation. Those decisions need their own source-backed models; they must not
be inferred from the successful synthetic assertions or tuned to reported glyph pixels.
