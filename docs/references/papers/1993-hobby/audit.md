# Focused fitting audit

<!-- cspell:words CSTR Hobby's NumPy KaTeX mathcal -->

This audit covers the fitting algebra in §§2–4 and §6, including §3.1 dependencies. A checked transcription means the
symbols match the source, not that every printed expression is mathematically correct or suitable for our raster. The
[research prototype](../../../../experiments/hobby_fitting/README.md) exercises a limited subset with supplied
correspondences.

## Sources and versions

The unchanged [stored CSTR report](paper.pdf) has SHA-256
`c97bd9a7bcebfeda5ea3d62bce266372f59fbc3c466239e222cf9b8c2465ff87`. Its equation labels are used throughout this audit.
PDF page numbers are one greater than printed body pages. Strict patches in
[review.json](../../../../tools/paper_extract/review.json) reproduce the checked transcription.

The [author-hosted report](https://9p.io/who/hobby/89_2-17.pdf), linked from the author's
[publication list](https://9p.io/who/hobby/pubs.html), was downloaded unchanged on 2026-10-15 as
[author-report.pdf](author-report.pdf). SHA-256: `ed617671e7fe98dca882f4d9e83d543c0853380c07f0ed0a3822db74dd21b4df`. It
also has 43 pages, with different typesetting, equation numbering and some mathematical changes. It is not established
to be the final 47-page journal publication. The [licensing record](LICENSE.txt) applies to both copies. Only the
passages identified below were compared between versions; neither chronology nor blanket superiority of one version is
inferred.

## Equation verification

Every numbered body listed here was visually checked, including signs, bars, subscripts, radical extents and constants.
Unnumbered definitions needed to interpret them were checked too. Selected inline definitions and weights were restored;
the complete prose remains only partially proofread. Section 5 is outside this fitting audit except the coefficient
count discussed below.

| Stored equation | PDF page | Checked relationship and qualification                                                                                                                                                                     |
| --------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| (1)             | 9–10     | Original, scaled and adjusted positions; signed endpoint normal displacements, edge length and exact integrated square. $\alpha_1\approx1000/H^3$.                                                         |
| (2)             | 10       | Tangential component of edge displacement difference divided by original length. $\alpha_2\approx25/H$.                                                                                                    |
| (3)             | 11       | Corresponding normal component; original direction fixed. $\alpha_3\approx25/H$.                                                                                                                           |
| (4)             | 14       | Twice the medial radius, not generally the chord length between the two contact points.                                                                                                                    |
| (5)             | 14       | Signed projected relative width error. $d_{AB}=(A-B)/\|A-B\|$, despite the preceding prose saying “from A to B”; $\alpha_4\approx50/H$.                                                                    |
| (6)             | 15       | Integer adjustment at an important vertical; scaled-coordinate offsets retain the chosen endpoint relation. $\beta_1\approx10^8/H^2$.                                                                      |
| (7)             | 15       | Mean/difference displacement measures normalized by total region arc length; horizontal counterpart swaps coordinates.                                                                                     |
| (8)             | 16       | Sharp-extremum phase penalty with $2.5\Delta x-\Delta y$ under the radical. Applies only in its nonnegative domain, with $\Delta x>0$; $\beta_2\approx5\times10^7/H^2$.                                    |
| (9)             | 16       | Two pixel-center relations, indexed $I_k,I_{k+1}$; $\beta_3\approx10^8/H^2$, $\max(\lvert a\rvert,\lvert b\rvert)=1/2$.                                                                                    |
| (10)            | 17–18    | Direction range bounded by $\gamma_1/w_{\max}$ and width range by $\gamma_2/\sqrt{w_{\max}}$, $\gamma_1\approx\gamma_2\approx0.25$. Direction is in radians.                                               |
| (11)            | 20       | Projected signed integer-offset residual; both integer components enter with plus signs. $\beta_4\approx2\times10^8/H^3$.                                                                                  |
| (12)            | 20       | Direction-lock residual uses $(Y_B-Y_A,X_A-X_B)$; $\beta_5\approx2\times10^6/H^3$.                                                                                                                         |
| (13)            | 21       | Offset perpendicularity uses $(I_{k+1},-I_k)/w_P^2$; $\alpha_5\approx20/H$.                                                                                                                                |
| (14)            | 21       | Reflection $(2x_B-x,y)$; horizontal and shift alternatives are described in prose.                                                                                                                         |
| (15)            | 22       | Adjustable reflection $(F_k-x,y)$ and translation-free linear part $\mathcal M_v$.                                                                                                                         |
| (16)            | 22–23    | Integrated squared symmetry displacement uses $d_{ab}=\|D\|/2$, $\alpha_6\approx5\times10^5/H^3$. Its preceding displacement definitions differ between versions; see below.                               |
| (17)            | 23       | Couples **relative errors** $E(P_i)-E(P_j)$ with $\sqrt{s_i s_j\psi_1}$. Does not demand identical widths from intentionally different source strokes.                                                     |
| (18)            | 24       | Nearby integer-adjustment X positions preserve their source difference.                                                                                                                                    |
| (19)            | 24       | Y counterpart; displacement is outside the radical. $\psi_2(x)=100H^{-2}\exp[-(x/(0.03H))^2]$.                                                                                                             |
| (20)            | 24–25    | Five integer/font-wide parameter relations and their solved substitutions.                                                                                                                                 |
| (21)            | 25–26    | Pairwise font-wide parameter differences and both displayed $\psi_3$ alternatives. Their left sides use subscripts 1/2 while the right sides use i/j, as printed; this is an index-notation inconsistency. |
| (22)            | 29–30    | Width/direction mapping and $\gamma_1/3$ by $\gamma_2/3$ buckets. Its preceding derivative differs between copies.                                                                                         |
| (31)            | 39       | Cubic Bernstein basis, control indices $3i$ through $3i+3$.                                                                                                                                                |
| (32)            | 40       | Midpoint quadrature $t=(j+1/2)/k_i$, distinct from the earlier one-third correspondence example.                                                                                                           |
| (33)            | 40–41    | Signed normal displacement times $\sqrt{\alpha_1 s_{ij}}$; unit normal $(v,-u)/\sqrt{u^2+v^2}$. Normals and arc lengths must be fixed coefficients for linear least squares.                               |

Section 2's integer-offset discussion explicitly assumes turning on pixels whose **centers** are inside the outline. Its
pixel-density claim cites Hobby's earlier work [8,9]; this audit does not re-prove that theorem or extend it to coverage
conversion. Section 4.1's height interval, weights and stopping symbols were checked against pages 26–29;
$\gamma_3\approx0.5/\sigma_{\rm hi}$, $\gamma_4\approx10$, $\gamma_5=0.65$. These are suggested heuristics, not a
complete feature classifier specification.

## Source discrepancies and interpretation

### Symmetry normal: supported alternative in the author copy

Stored page 22 defines the mean direction $D$ along matching segments, but its two displacement numerators use $D\cdot$
the positional mismatch. That measures tangential sliding rather than normal separation. The author copy, page 22,
explicitly uses $(D_y,-D_x)\cdot$ the mismatch for both endpoints (its subsequent equation is (15)). This agrees with
the normal-component construction in §3.1 and the curved symmetry expression on stored page 41. The stored transcription
retains $D\cdot$ faithfully; use the author-supported rotated normal when implementing this relationship. Reject a
zero-length mean direction rather than divide by zero. Symmetry fitting is outside the first prototype.

### Width mapping derivative: supported alternative in the author copy

Stored page 29 prints $\partial v/\partial w=\sqrt\theta$. Its own (22), $v=\frac23 w^{3/2}$, differentiates to
$\sqrt w$. The author copy, page 29, explicitly prints $\sqrt w$ before its (21). This also gives
$\Delta v\approx\sqrt w\,(\gamma_2/\sqrt w)=\gamma_2$, the stated local bucket correspondence. The stored transcription
retains $\sqrt\theta$; an implementation should use the verified mapping and its derivative. The mapping is only
approximate for finite rectangles: $u$ depends on $w$ as well as $\theta$.

### Width matching weight: surprising, but faithfully printed

Both copies, PDF page 23, print

$$\psi_1=\frac{500}{H^2}\exp\left[-\left(\frac{w_1-w_2}{0.7}\right)^2-\left(\frac{\Delta\theta}{9}\right)^2\right]$$

and explicitly say radians. No source here supports replacing 9 by degrees or another constant. At $\pi/2$ the
orientation factor is approximately 0.970, so this is a weak directional preference. The prototype keeps the printed
constant and reports this consequence. The 0.7 width scale also needs an explicit unit convention: unlike $H$-normalized
terms, it does not automatically rescale when input coordinate units change. The prototype uses pixel units and exposes
that width scale, without tuning it to glyph pixels.

### Curves: correspondence, fixed coefficients and a coordinate inconsistency

Stored page 40 and author page 40 both use **one third** as an example of mapping a point on a polygon segment to the
same fraction of its curve-parameter interval. This is correct and separate from the **midpoint** rule (32). For $k_i$
intervals the prototype uses $j=0,\ldots,k_i-1$.

The prose calls $(u_{ij},v_{ij})$ the derivative of adjusted-curve (31), yet also requires every measure to be linear in
adjusted control points. Recomputing a normalized derivative from unknown adjusted controls makes (33) nonlinear. The
prototype freezes derivatives and quadrature arc lengths from the input curve, consistent with §3.1's fixed original
directions. This is an explicit project interpretation of that linearity requirement, not a quoted algorithm detail. It
approximates normal displacement, not exact closest-point distance or curvature preservation. Zero tangents are
unsupported and rejected.

Stored page 41 says to replace $(u,v)$ by $(1,0)$ to measure horizontal displacement. In (33) this selects $-\Delta Y$;
horizontal displacement requires $(0,1)$, up to overall sign. Preserve the printed source and flag this before extending
(7) to curves. This passage has not been compared against the author copy. The first prototype does not implement it.

### Coefficient count (26): derived correction, not an author-confirmed erratum

Stored page 33 and author page 33 (its (25)) both print

$$(N_V-2)^2+\left(N_V-\frac{N_V-1}{2}\right)=\frac32(N_V-2)(N_V-1).$$

The preceding Step 4 count is

$$\sum_{k=1}^{N_V-2}(N_V-k)=N_V(N_V-2)-\frac{(N_V-1)(N_V-2)}2.$$

Adding the Step 5 count $(N_V-2)^2$ therefore gives the project-derived correction

$$(N_V-2)^2+(N_V-2)\left(N_V-\frac{N_V-1}{2}\right)=\frac32(N_V-2)(N_V-1).$$

The source's $N_V=15$ example gives 104 + 169 = 273, consistent with this derivation. Both retrieved versions contain
the discrepancy; the final journal typesetting and any author erratum remain unverified. This is an encoding storage
count, not a fitting constraint, and does not block the prototype.

## Disposition

Transcription corruptions are corrected through strict regeneration patches. The version differences above are
**confirmed source discrepancies**; the original text is preserved and supported alternatives are labeled separately.
The width-weight behavior and derivative linearity interpretation are **pending model assessment**, not optical
acceptance. The prototype's geometric tests establish algebraic relationships only. Automatic feature recognition,
font-wide grouping, integer selection, topology guards and compatibility with the delivered raster remain separate
implementation and evaluation work.
