<!-- cspell:words nullspace underdetermined CGAL Shene's Casteljau Forsgren nondegenerate linearization SLSQP nalgebra Ogita Oishi Mattingley autovectorization reassoc stationarity -->

## Completed diagonal-fit reuse experiment

The question is whether editing interactions can avoid repeating completed glyph fitting across renders. Following
[FreeType's memory-bounded glyph caches](https://freetype.org/freetype2/docs/reference/ft2-cache_subsystem.html), first
measure exact repeated fitting inputs during typing, layout/spacing changes, setting changes and revisits. The proposed
adaptation retains completed diagonal outcomes within an immutable loaded font, with bounded least-recently-used
storage. Key the complete original source geometry, upstream commands, reference anchors, size and native-axis ownership
by exact floating bits; a changed input always computes a fresh outcome. Unsupported outcomes can be reused, while
errors remain fresh. No approximate matching, geometry changes, fitting thresholds or glyph rules are included.

Keep request validation, scalar resolution, donor construction, rasterization, metrics, kerning and layout authoritative
on every call. Raw-byte entry points remain uncached. A full request-result cache and intermediate certificate cache are
outside this experiment. Compare the ordinary SIMD baseline with both cold and repeated interactions; count hits,
misses, eviction and retained payload separately from timing. Adoption requires useful interaction gains, controlled
cold overhead and unchanged delivery across request order, settings, eviction, errors and font lifetimes. Record the
census, identities, failures and browser evidence under `out/diagnostics/glyph-reuse-optimization/`; preserve published
preview selections and the approved comparison.

The completed-fit cache is retained after the interaction experiment. In both families, repeat/layout/spacing/kerning
and color changes repeat every default specimen fit; appending a new character repeats 28 of 29. The loaded-font cache
retains up to 2 MiB of key/command/reason payload and 256 entries, with bounded bookkeeping overhead. Full-key equality
authorizes reuse after a digest-assisted lookup. Detailed fit diagnostics were already discarded by this delivery caller
and are not retained; successful abstentions are cached while errors retry. Font destruction releases the cache.

All 563 delivery checks and 593 generator tests pass. Ordinary browser-worker interaction and confirmation batches show
about 88–91% lower warm render time for the default specimen, typically around 9 ms. New sizes and weights still compute
fresh geometry and incur a few percent overhead. Retained settings can be revisited cheaply, while evicted settings
recompute normally. These are worker-render results from scripted requests, not mounted UI latency: the editor's
existing 150 ms text debounce remains separate. The measured four-setting sequence retains about 1.1–1.3 MB per font.
Classification: unchanged delivered output within the verification scope, with no new optical acceptance. No publication
selection or fitting model changes.

## Selective solver arithmetic experiment

The question is whether local reassociation recovers useful rendering time while retaining the diagonal compensation
lost under global fast-math. The adaptation confines LLVM `reassoc` to a separate dot-product proposal kernel in the
least-squares solve. SVD construction, rank selection, compensated norms, geometric predicates, solver acceptance and
all other arithmetic remain strict. Neither finite-value assumptions nor approximate functions are enabled.

[Rump's matrix-product error analysis](https://www.tuhh.de/ti3/paper/rump/Ru14c.pdf) supports an order-independent
rounding bound. This prototype uses the more conservative standard gamma bound, outward-rounded maximum-magnitude
products and an additive underflow allowance. Non-finite inputs, an unbounded estimate, or a result whose sign is not
resolved by that bound trigger the original ordered arithmetic. This is a local arithmetic filter, not a proof of an
unchanged active set or final pixels. Existing strict feasibility and stationarity checks remain authoritative.

Use an isolated source copy and matched strict/selected compiler pipelines, with the ordinary standard-SIMD package as a
third control. Verify effective flag placement and protected compensated arithmetic, exercise cancellation and
exceptional operands, compare the complete delivery matrix, then time ordinary browser workers only after correctness
checks. No fitting thresholds, font-specific rules or published selection change. Retain source/package identities, all
failures and direct-app timing in `out/diagnostics/selective-math-optimization/`. Promotion requires a useful direct
gain and assessment of any delivered differences; mechanical parity alone does not establish optical quality.

The filtered projection prototype is declined at the performance gate. All 563 delivery checks match the ordinary app,
including the 288-cell matrix, default glyphs, general API controls and exports. Compiled-kernel probes retain the
compensation witness and satisfy the tested exact-rational error bounds. Twelve fresh browser sessions show essentially
no matched-pipeline gain: Roboto is 0.06% slower and Source Sans 0.31% faster. The complete experimental package is
17.96% and 10.22% slower than the ordinary SIMD app, respectively. Those direct differences include the compiler
pipeline and filtering overhead; they do not establish that reassociation itself causes that slowdown. This narrow
boundary preserves the tested output but supplies no practical adoption benefit. Broader kernels remain untested.

## Global fast-math experiment

The scoped question is whether broad fast-math changes delivered output or ordinary browser-worker rendering time
relative to standard SIMD. [LLVM fast-math flags](https://llvm.org/docs/LangRef.html#fast-math-flags) supply the
semantics: reassociation, approximate functions, reciprocal substitution, contraction, insignificant signed zeros and
assumptions that values are finite. This is a diagnostic experiment, not an assertion that the geometry satisfies those
assumptions.

The project adaptation processes a single merged Rust LLVM module through the same optimizer/code generator in strict
and fast modes, then retains the ordinary WASM link and bindings. The fast mode marks floating instructions before that
optimization; the strict control uses the same extra pipeline without those flags. Inspect input/output IR and an
arithmetic witness to confirm effective transformations. Compare the strict control with the maintained SIMD package
separately so a compiler-pipeline difference cannot be attributed to fast-math. Standard SIMD stays enabled on all
sides; dependency versions, geometric rules and publication scope stay fixed.

Capture output differences without stopping at the first changed glyph. Cover both families, ASCII, sizes, weights,
fitting/scanner modes, diagonals enabled/disabled, layout, metadata, errors and exports. Time fresh paired ordinary
browser workers with reversed order, identical-build controls and the established pangram/stress requests. Changed
output does not itself establish optical damage, and faster timing does not justify weakening numerical guarantees. No
main-app selection, deployment or optical acceptance is included. Detailed evidence belongs in
`out/diagnostics/fast-math-optimization/`.

The diagnostic build is not promoted. Fast-math removes a compensation term on a finite arithmetic witness and changes
pixels in 140 of 144 diagonal-enabled matrix cases, including 18 default-setting glyphs. All disabled matrix cases,
layout, metadata and general API controls match. The matched strict experimental build agrees with the app throughout
delivery comparisons, separating the observed output changes from compiler-pipeline effects. The user rejected the
visible result because it negates most diagonal compensation; the compensated-arithmetic invariant failure is also
confirmed.

Thirty-four fresh browser sessions show a direct fixed-pangram reduction of about 7.5% for Roboto and 8.9% for Source
Sans versus the maintained app, and about 10% on varied requests. The matched strict/fast comparison shows larger gains,
but its strict pipeline is slower than the app with diagonals enabled. Direct package comparisons therefore supplement
the causal arithmetic comparison; compiler-pipeline effects must not be described as fast-math gains. The timing scope
and all sessions, including identical-build controls, belong to the detailed report. Any future arithmetic adoption must
isolate a kernel and justify its numerical error contract; this experiment supplies no global safety guarantee or new
optical acceptance.

The requested visual review compares frozen maintained SIMD and experimental fast-math delivery packages. It captures
changed ASCII glyphs for the same two families, six sizes, three weights, fitting policies and scanners with diagonals
enabled. Actual text renders retain their common layout; aligned glyph crops and integer enlargement preserve delivered
pixels. The initial page shows both families at 16 px, weight 400, font hints enabled and FreeType Mono. Changed-pixel
overlays are optional inspection aids, not quality scores. The separate review packet and service preserve the main app
and approved comparison. Findings remain pending under the
[iteration assessment](revisions/001/03-spacing-kerning.md#fast-math-visual-assessment).

## Standard WASM SIMD experiment

Standard `simd128` is retained as a compiler target for existing numeric operations. The source foundation is
[V8's SIMD/autovectorization documentation](https://v8.dev/features/simd) and
[Rust's WASM target features](https://doc.rust-lang.org/stable/rustc/platform-support/wasm32-unknown-unknown.html). The
project adaptation enables standard vector instructions across Rust target dependencies, including solver loops, without
enabling fast-math, relaxed SIMD or reassociation. Fitting rules, dependencies and runtime state stay unchanged. The
direct WASM script retains scalar defaults for compatibility; SIMD packages have distinct names and require runtime SIMD
support. Build configuration belongs in the [WASM README](../tools/wasm/README.md#build).

Thirty-six ordinary Chrome browser sessions on an Apple M2 Max cover reversed identical-build controls, paired scalar
and SIMD builds, default pangram/stress and varied size/axis requests. Both confirmation batches pooled, including an
unfavorable session, show about 3.1% less Roboto pangram render time and 4.9% less Source Sans time. Fixed stress gains
are about 5.5% and 8.7%; varied pangram gains are about 5.0% and 4.8%. These are scoped worker-render measurements, not
startup or cross-device guarantees.

Complete scalar/SIMD reports match across 288 cases and 27,360 glyphs; actual delivery packages also match on pixels,
layout, metadata, errors and exports. Native delivery comparisons pass. Four existing native-versus-scalar diagnostic
report differences were reproduced independently and are recorded separately; SIMD does not introduce them. The default
scalar packages and served app remain unchanged. This is a performance result with no new optical acceptance or
iteration closure. Detailed identities, controls, limitations and verification belong in
`out/diagnostics/wasm-simd-optimization/report.md`.

The web build now selects standard SIMD by default: its maintained preview recipe produces the SIMD package, and app
staging consumes that package. Direct WASM script defaults stay scalar; a configured package override permits a separate
scalar app build. This adopts the compiler feature without changing fitting selection or adding runtime fallback. Web
compatibility and input paths belong to the [web contract](../tools/web/CONTRACT.md); adoption checks belong in
`out/diagnostics/wasm-simd-adoption/`.

Global fast-math remains disabled; the [separate diagnostic study](#global-fast-math-experiment) owns its numerical
assessment and performance evidence. Standard SIMD adoption does not relax the fitter's arithmetic guarantees.

## Partition-preserving equality filter experiment

Early filtering of dominance equality-event generation was declined at the diagnostic performance gate. The approach
adapts
[CGAL certified filtering](https://doc.cgal.org/Manual/3.1/doc_html/cgal_manual/Kernel_23_ref/Class_Filtered_predicate.html)
and the [Bernstein convex-hull property](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/spline/bezier-construct.html)
to the existing guarded floating algorithm. Original foot, radius and competitor projection cuts, numerical abstentions,
contact checks and merging stay authoritative. A geometric clearance bound alone cannot justify skipping the current
sample/interpolation/root calculation.

The census finds a large no-root population, but that is only an optimistic ceiling. The tested outward-rounded sample
and coefficient bounds certify about 4.7% of equality calls; their preparation and lookup cost exceeds the avoided work
in native replay. Full query results match on 2,194 captured queries, including complete reasons and floating bits. This
supports the observed cases, not a general proof of every possible floating input. The filter was not promoted to
maintained runtime or WASM, so ordinary browser timing and a fresh full rendering matrix were not warranted. The result
rejects this conservative filter design, not every possible earlier equality certificate. Existing direct equality
calculation remains unchanged. Detailed evidence belongs in `out/diagnostics/equality-filter-optimization/`.

## Interval search diagnostic allocation experiment

Avoiding unused interval explanations in curve-candidate searches was declined. The
[Rust Performance Book](https://nnethercote.github.io/perf-book/heap-allocations.html) grounds borrowing labels/tags and
omitting temporary owned explanations when callers discard them. A lightweight internal search result shared the full
geometric body, preserving cuts, guards, interval bits, candidate order and public diagnostics. The prototype reduced
query allocations by 1.31%, reallocations by 13.37% and cumulative requested bytes by 2.62% across the 72-cell ASCII
census, but did not improve ordinary browser rendering.

Six paired browser sessions put pangram render time 0.44% slower for Roboto and 1.09% slower for Source Sans; stress
results also favored the existing implementation. Identical-build controls show timing drift, so these small differences
do not establish a universal slowdown. They provide no performance basis for retaining the extra result type and
compile-time diagnostic mode. No varied-request or confirmation suite was needed after the failed performance gate. The
frozen implementation and WASM are restored exactly. Native reports, full diagnostic replay and WASM delivery were
unchanged under the prototype; this was a performance experiment, not a new optical assessment. Detailed evidence
belongs in `out/diagnostics/interval-diagnostics-optimization/`.

## Curve candidate ordering investigation

The scoped question is whether evaluating curve-pair candidates in descending certified span-bound order avoids more
full dominance queries than the existing source order. This adapts the bound-based pruning principle of
[Boyd and Mattingley](https://web.stanford.edu/class/ee364b/lectures/bb_notes.pdf) to a finite candidate search. The
existing outward-rounded span bound, strict-less pruning and all per-candidate geometry remain unchanged. Equal actual
spans must retain the original first winner, independently of their bound order; absent or unsafe bounds retain full
evaluation. Scores that are not finite require the original search semantics.

A diagnostic-only copy captures candidate bounds, original query outcomes and their costs, then simulates the new order
and verifies the same winning candidate. It measures ordering cost separately from geometry. Inputs cover both families'
default pangram/stress and the established size, weight, hint and scanner matrix. A prototype is justified only by
material avoided work after ordering/storage overhead, full delivered geometry/selection and output identity, and
reproducible ordinary-browser improvement. No competitor, cut, uncertainty guard, fitting stage or solver changes.
Detailed evidence belongs in `out/diagnostics/curve-ordering-optimization/`.

The bound-order simulation preserves every winner and avoids roughly 5–6% of default dominance queries, but those
queries contribute only about 3–4% of dominance-body time. Whole-render measurements support a small Roboto gain; Source
Sans gains remain below one percent and are not convincingly separated from identical-build drift on varied requests.
The additional candidate storage, ordering and exceptional-score fallback are not retained for that tradeoff.
Source-order evaluation and its existing certified pruning remain unchanged.

## Stage prerequisite scheduling

Crossing and joint fitting evaluate their inexpensive necessary prerequisites before visibility and medial recognition
in the approved selection sequence. The foundation is eliminating computations whose results cannot affect observable
output, as in [LLVM dead-code elimination](https://llvm.org/docs/Passes.html#adce-aggressive-dead-code-elimination).
This is scheduling of the current model, not a new geometric eligibility rule. Standalone stage diagnostics and input
validation retain their existing order; eligible stages retain all recognition, solve and delivery guards.

Selection rejects unsupported crossing structure (multiple contours, cubics or no quadratic attachment) before
recognition. Straight-joint selection checks its existing axis/waist prerequisites first and retains their computed
values for subsequent fitting. This preserves all delivery checks on eligible inputs. Existing prepared source analysis
is already lazy; no further cache or solver change is included. Complete delivered capture/output comparisons and
ordinary-worker confirmation support this scheduling change; no optical change is claimed. Detailed evidence belongs in
`out/diagnostics/stage-eligibility-optimization/`.

Moving the curved-crossing waist test ahead of pair preparation is excluded: it costs more than the preceding work on
many inputs that already abstain without reaching that test. The original curved waist/certificate order therefore
remains intact. Source analysis reuse and candidate reordering are separate opportunities, outside this experiment.

## Immutable certificate reuse investigation

The scoped question is whether repeated curve-substitution and topology certificates can share results within one
approved fit.
[CGAL's lazy exact computation](https://doc.cgal.org/latest/Number_types/classCGAL_1_1Lazy__exact__nt.html) provides the
foundation for retaining immutable results. Measure duplicate calls before selecting a cache: certificate inputs include
complete ordered geometry and subdivision depth, with success and failure kept separate from changed inputs. Source,
upstream and candidate labels alone are not identities. A changed candidate must receive a fresh verdict.

Refresh the profile after sparse objective and font-identity adoption. The census distinguishes duplicate work across
stages from retries, scopes reuse to one fit and excludes observer work from certificate-body timings. Controls cover
Roboto and Source Sans with fixed and varying size/axes, both hint policies and scanners. Any adopted cache must
preserve complete certificate decisions and output and improve ordinary browser-worker rendering after key/lookup
overhead. Detailed evidence belongs in `out/diagnostics/certificate-reuse-optimization/`.

The census does not support a general curve-certificate cache for the default Roboto specimen. Whole-signature
memoization by ordered loop bits inside one fit is declined: ordinary-worker measurements improve Source Sans by about
1.3–1.6% but slow Roboto's pangram by about 0.7%. The mixed small benefit does not justify the added cache state. The
maintained certificate path remains uncached beyond its existing prepared objects; no geometry rule or validation gate
is relaxed.

## WASM timing investigation

The current performance question is whether ordered sparse solver execution improves ordinary browser-worker rendering
once runtime variability is distinguished from arithmetic cost. The isolated experiment follows
[V8's compilation pipeline and fixed-tier controls](https://v8.dev/docs/wasm-compilation-pipeline): fresh-process
baseline/baseline and sparse/sparse controls, reversed module loading and render order, and baseline/sparse comparisons
under default, baseline-only and optimizing-only compilation. Fixed tiers are diagnostic controls, not app settings.

Inputs are the frozen pre-experiment and sparse-trial WASM packages, Roboto and Source Sans at 16 px/weight 400, with
pangram, diagonals-disabled and stress specimens. Font loading and output identity checks stay outside render timing.
Cold calls and warm calls remain separate; complete raw samples and binary identities accompany each result. Browser
checks use the app worker's request handling and record both worker render time and message round-trip time.

The fitting and raster model remain unchanged. A runtime explanation requires reproducible controls; fixed-tier gains
alone do not establish a default-engine improvement. As the [VM warm-up study](https://arxiv.org/abs/1602.00602)
explains, discarding a fixed number of calls does not establish peak steady-state performance; this experiment retains
those calls and repeats fresh processes rather than claiming a warm-up theorem.

Repeated ordinary browser-worker measurements support sparse execution as a performance candidate. Historical negative
Node runs have not been reproduced and their cause remains unresolved; compiler tiering is not established as the
explanation. Ordinary-worker controls support the ordered objective operations described below; they do not establish a
compiler fix. Detailed evidence belongs in `out/diagnostics/wasm-timing-investigation/`.

## Immutable font identity

Loaded fonts retain their byte-derived identity across renders independently of size, axes or text. Rust's
[once-initialized cells](https://doc.rust-lang.org/std/cell/struct.OnceCell.html) provide the foundation: owned
immutable bytes and their lazy hash share one lifetime, and source preparation and capture borrow that identity.
Raw-byte entry points share identity within one request. Validation, metrics and glyph captures remain fresh per
request; [completed diagonal-fit reuse](#completed-diagonal-fit-reuse-experiment) is a separate bounded cache.

The performance-only change preserves output and error behavior across Roboto and Source Sans sizes, weights, both hint
policies and both scanners, including disabled fitting and invalid requests. Ordinary browser-worker comparisons support
the incremental identity benefit with fixed settings and fresh size and axis changes. The SHA profile share is an upper
bound on removable work, not a predicted speedup. Detailed evidence belongs in
`out/diagnostics/font-identity-optimization/`.

<!-- cspell:words Hobby's NumPy SVD lstsq Zeno Bernstein Sutherland Hodgman Vandenberghe collinearity -->

This document owns the design and findings for source-relative geometric fitting based on
[Hobby's model](references/papers/1993-hobby/README.md). The isolated
[experiments](../experiments/hobby_fitting/README.md) separate algebra controls from recognition on captured font
outlines; the restricted native policy uses the same source relationships. Read the
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

### Real-outline straight-stroke experiment

The first real-outline slice tests Hobby (5) and (17) with an existing fitted straight stem as the anchor. Recognize
opposing straight boundary contacts in source and corresponding fitted commands; source-derived normals measure their
widths. The fitted anchor supplies its actual width change, so no new integer-target search or pixel-selected target is
introduced. Couple a related stroke's relative change to that anchor while retaining shared attachment variables, source
direction, contour validity and counters. Automatic recognition, eligibility and conservative abstention are project
adaptations; manually selecting vertices for a reported glyph is not an implementation of this model.

The source coefficients stay fixed when anchor positions are prescribed: substitute the actual nonzero fitted
displacements into the constrained system rather than redefining the source pair after moving its endpoints. A
rectilinear anchor follows the existing upstream grid fit described by Hobby §3.3; least outline movement alone does not
establish anchor ownership. For tapered straight borders, equal-distance line contacts and a boundary-clear medial disk
supply the width as twice its radius (§3.2), which need not equal the chord between contacts. Curved or multiply owned
contacts remain outside this first recognizer.

For a correction applied after upstream fitting, compare two position/shape references explicitly: scaled source and the
existing fitted outline. Using fitted positions as the zero-change target for Hobby's position/shape residuals is a
project adaptation intended to retain the hinter's placement; the width measurements and coupling coefficients still
come from the source. Neither reference may be selected by searching the reported glyph's pixels. Movement and shape
evidence determine whether the adaptation is geometrically feasible before any raster assessment.

Inputs are independently captured source without hinting and upstream Mono outlines at identical axes and size. Controls
include translations, scaling, intentionally different source widths, shared junctions, incompatible frozen controls,
and the Roboto Flex `1` captures over 12–24 px. Unsupported curves or ambiguous ownership retain the upstream result.
Report width relationships, exact fixed points, command correspondence and geometric validity separately from final
raster evidence. The question is whether the source-relative head/stem relationship can be recovered without moving its
attachment or damaging another feature. Geometry or raster damage rejects the candidate; successful algebra alone does
not authorize renderer adoption or establish optical acceptance.

A valid medial portion ends at a third-boundary contact, including adjacent end caps. Sampling the untrimmed border
overlap can miss that distinction and must not be repaired by ignoring the cap. The restricted native policy therefore
uses the interval model below; the original point-probe control remains useful as evidence of why interval extraction is
required.

This prototype establishes a reproducible geometric experiment. Before renderer integration, resolve feature extraction
and confidence, supported black/white groupings, integer target selection, movement and junction ownership, curve
validity, counter guards and raster-aware evaluation. Those decisions need their own source-backed models; they must not
be inferred from the successful synthetic assertions or tuned to reported glyph pixels.

### Valid straight medial intervals

The native correction clips each straight pair's bisector to its actual segment-site dominance intervals before placing
width samples (Hobby §3.2). Along the straight bisector, center and radius are affine. Finite contact parameters,
positive radius and distance to every other segment bound the intervals; projection endpoints split the point/line
distance pieces, whose equality events are quadratic. Sample only open interval interiors and recheck every sampled
disk. This is a restricted segment-diagram construction, not full curve or point/segment branch recognition.

Before resolving a near-tangent equality event, the experimental interval solver bounds the piece-local quadratic in the
Bernstein basis. Coefficients with a certified common sign prove that there is no root in that piece; outward rounding
and the existing relative arithmetic band retain uncertain near-zero cases. This avoids rejecting a clear local interval
because of an almost-double root far outside it. Contact rechecks, opposition pruning and actual local tangency guards
remain separate.

Keep the source width coefficients, upstream-fitted rectilinear anchor and shared attachment fixed. Compare source,
upstream and corrected widths and directions before raster assessment, with interval transforms, caps, third contacts,
ambiguous ownership and sampling convergence as controls. The Roboto Flex `1` case and the isolated existing corpus
provide assessment; no glyph, row, phase or pixel-selected parameter may affect production eligibility. A damaged join,
contrast relationship, invalid outline or movement/ownership failure rejects adoption. The approved baseline, Gray and
publication matrix remain separate.

For interval samples, couple every related sample to every anchor sample with the product of their own arc-length
weights, following the “each i and each j” construction of (17). Index matching between independently divided strokes
has no geometric meaning. Interval extraction precedes pair recognition; segment feet stay in open segment interiors,
and endpoint-dominated branches are unsupported. Coordinate normalization and explicit linear/constant polynomial cases
keep numerical guards independent of input translation and scale; every retained sample still requires a clear disk
against all other boundaries.

The restricted straight recognizer uses the single-stage 157° opposition-angle example in Hobby §3.2, Figure 18b, to
remove corner branches before ownership matching. Its angle is constant on a segment/segment bisector; point and
parabolic branches remain unsupported. This published example is a conservative project choice, not a universal stroke
definition or a value selected against rendered pixels. Preserve ambiguous surviving ownership by abstention.

For a least-squares optimum outside the source movement budget, take the feasible prefix of its step from the upstream
fit. This project adaptation uses convex quadratic descent
([Boyd and Vandenberghe, chapters 2 and 9](https://web.stanford.edu/~boyd/cvxbook/)): along the segment from the
upstream point to the free-variable minimizer, the objective decreases monotonically. The step fraction is computed
directly from half the narrowest retained source sample width, reserving the Euclidean error of nearest 26.6 rounding
(square root of two divided by 128 pixels). It is not a constrained optimum or a pixel-selected line search. Fixed
controls remain exact; post-rounding movement, source width-error reduction and whole-outline validity still gate
adoption. A budget smaller than the rounding reserve abstains.

The native policy keeps a conservative intersection filter: nonadjacent collinearity is unsupported until finite contact
can be certified, even where the experiment can classify it. In the current isolated corpus this declines seven
additional experiment applications while all 34 native applications reproduce the independently solved coordinates. The
reported `1` matches over 12–24 px. Three/six/twelve-station controls differ by at most one 26.6 quantum at 16 px, with
matching rounded results at the other tested sizes. This bounds observed quadrature sensitivity; it does not prove
optical acceptance or justify choosing a station count by pixels. The fitter penalizes direction changes rather than
locking the slanted borders; the source-projected width error is a linearized feature measure, not an exact measurement
of the fitted medial axis.

## Direct diagonal grid-fitting experiment

The next opt-in experiment extends this component rather than using StrokeStyles annotations. It asks whether direct
source-outline border recognition plus explicit diagonal grid placement can correct the reported Roboto weight
imbalance. Compare the unchanged upstream fit, relative-width coupling alone, and relative-width coupling with diagonal
grid placement on identical captures and the captured scanner policy. Maintained renderer selection and published
preview matrices stay separate.

Hersch, sections 5–6 and Figure 25, supplies parallel-border and integer axis-separation control. Microsoft's
[VTT `DStroke` reference](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/doc/VTT%20Language%20Reference/vttlang.html#cmd_DSTROKE)
describes stationary/floating point ownership, parallel borders and matching staircase phase. Hobby sections 3.2–3.4
supplies medial width, source distortion, nearly constant-width offset intervals and integer-offset residuals; section 4
supplies font-wide relationships. None of these sources demonstrates this proposed automatic adaptation to our selective
hinting pipeline. The reported source-derived targets and constrained solve are project adaptations requiring
independent geometric and delivered-raster verification.

Recognition starts from the filled nonzero-winding boundary, preserving correspondence to original outline controls.
Straight border portions are considered across contours and across split portions at crossings; sampled StrokeStyles
spines and longest-edge-per-side selection are not inputs. Opposing borders require a certified ink interval against
competing boundaries. Width and taper come from source geometry. Any curved or numerically uncertain region outside the
supported slice stays unchanged with an explicit reason; a successful result must not depend on the glyph name.

Relative-width targets preserve intentional contrast using fitted upright standards at the same font, axes and size. The
grid arm additionally controls border parallelism and an integer horizontal or vertical separation, selected from
geometric width/distortion rather than rendered pixel counts. Perpendicular thickness is measured separately from that
axis separation. Shared controls are solved jointly, native-owned coordinates and upright anchors remain exact, and
unrelated geometry stays upstream. Feasibility, source-derived movement bounds, winding, intersections and joins gate
delivery; unsupported/conflicting constraints return the exact upstream outline. Curved-border extension is a separate
stage and must not be inferred from straight-stroke success.

Start with straight/tapered synthetic controls (including translations, reflected/slanted geometry, shared joins,
overlaps and conflicting native ownership), then default Roboto `k/y/x/z/v` and `A/V/W` plus SourceSans3 at 12–24 px,
weights 300/400/700 and both font-hint modes. Record recognition, abstention, source/upstream/candidate widths, integer
targets, residuals, movement, ownership, validity, runtime and exact final raster changes. Integer placement is not
established by a lower width residual alone. Inspect changed output through the browser comparison; mechanical success
does not establish optical acceptance or authorize renderer adoption.

Separate the ideal parallel-border constraint from its 26.6 representation. Fixed native coordinates can make exact
parallelism and exact integer separation incompatible after rounding. Record the achieved rounded geometry and the error
bound induced by coordinate rounding; never claim the ideal constant-width/phase theorem merely because a soft penalty
decreased. An approximate representable result still needs delivered-raster assessment; infeasible ownership or excess
representation error abstains.

### Strict-signature control assessment

The isolated direct-outline implementation and opt-in evaluator live in `experiments/hobby_fitting/`; commands are in
its [README](../experiments/hobby_fitting/README.md#direct-diagonal-evaluation). The model couples every retained source
sample to fitted upright samples, solves shared original controls together and freezes native-owned coordinates, upright
anchors and curve-incident endpoints. Uncertain boundaries remain clearance competitors. Curved borders are unsupported.
The constrained solver retains the full nullspace of the hard rows; an analytic underdetermined control checks that
shape fitting can still use every unconstrained direction.

The captured comparison covers Roboto and SourceSans3, weights 300/400/700, sizes 12/14/16/18/20/24, fifteen glyphs and
both automatic and font-hints-first fitting: 1,080 records in 72 reference groups. Every recorded upstream raster
reproduces through the independent native adapter. In the direct run, width-only fitting changes 381 outlines and 344
bitmaps; the grid arm changes 334 outlines and 300 bitmaps. Only 276 grid results actually retain phase constraints; the
remainder explicitly report width-only application. These are activity measurements, not acceptance rates.

For Roboto 400 at 16 px, both hint modes recognize straight diagonal pairs in `k`, `x`, `z` and `v`. The delivered `x`
changes from mean source-projected normal width 1.346 px upstream to 0.904 px with automatic fitting and 0.908 px with
font hints. The automatic grid arm reaches 0.844 px with phase constraints; the hints-first grid arm declines the phase
constraints and delivers its width-only result. Browser inspection at native and enlarged scale confirms visibly lighter
arms. **Pending assessment:** contrast, staircase continuity and size transitions still require broader optical review;
the smaller width residual does not establish a preferred arm or adoption.

In this strict-signature control, `k`, `v` and `z` return the exact upstream outline because their attempted fits fail
the split-boundary comparison. Internal contour segmentation can change without changing filled attachments; sampled
fill checks alone cannot certify that distinction. The exact-join option below assesses those same candidates with a
separate geometric reference. Rejected commands and metrics remain separate from delivered results. `y` remains
unchanged because its relevant curved neighborhood is unsupported.

Mechanical verification checks exact fallback commands and pixels, command correspondence, native-owned coordinates and
stored coordinate bits, bounded movement and delivered validity across the corpus. Rejected-attempt widths never stand
in for delivered widths. No failure was found in those delivery checks. The experiment's 99 tests include analytic
width/separation controls, transformations, conflicting ownership, curves, uncertain boundaries and complete-nullspace
solving; they do not prove optical quality. A single Python/NumPy pass measured median 2.93 ms and 95th percentile 16.67
ms per fit, excluding imports, reference construction and raster subprocesses. This is prototype timing, not a browser
or native-runtime performance claim.

This result supports direct border recognition as a useful alternative to the restricted StrokeStyles consumer. It has
not resolved all reported glyphs or established a production-ready diagonal fitter. Maintained renderer settings, WASM,
the deployed app and approved preview selections were not changed.

### Exact filled-join verification

The exact-join slice keeps width targets, source weights and the joint fitting objective fixed. It checks whether
straight candidates preserve the filled shape's attachments while allowing incidental segment splitting to change. The
offline reference is selected only behind an explicit experimental option; the original split-signature comparison
remains available as the control.

[CGAL 6.1 arrangements](https://doc.cgal.org/6.1/Arrangement_on_surface_2/index.html) supply planar subdivision and
face/edge/vertex incidence; exact predicates and constructions avoid a sampled-grid decision. Classify faces by the
original directed contours' nonzero winding, retaining contour labels. Internal seams between ink faces may change
without changing the filled boundary. Regularized polygon union alone is insufficient: it discards lower-dimensional
features, so point and edge contacts need explicit classification alongside filled components and holes. Preserve the
exact finite input coordinates, including native coordinates off the 26.6 grid; never add a raster tolerance to decide a
join.

The conservative experimental decision compares filled components, counters, labeled attachments and boundary contact
singularities between upstream and attempted output. Source geometry supplies the intended attachments and records any
pre-existing upstream discrepancy separately. Counts alone do not prove feature preservation: retain which contours
participate in components and contacts. Unsupported curves, invalid inputs or reference failures abstain. An exact
geometric decision establishes these measured invariants, not optical quality or a guarantee about all deformations.
This choice of preserved font features is a project adaptation of arrangement topology and the existing source-relative
model; it requires analytic controls and independent review.

The reference labels the dual face graph from the unbounded face using directed contour crossings: crossing from a
segment's right face to its left adds its signed contribution to that contour's winding. Coincident contributions add or
cancel exactly. Merge adjacent ink faces before counting filled components and adjacent white faces before counting
counters; a white component reaching the unbounded face is exterior, even when neutral contour seams subdivide it. For
each contour pair, retain the components and holes of their area intersection, pure edge-contact chains and isolated
point contacts. Include boundary singularities and counter boundary labels. Internal seam-chain counts and exact areas
remain diagnostic evidence, not equality conditions for delivery. Width, movement and source-shape checks remain the
fitter's responsibility; matching these finite topological invariants does not prove optical equivalence.

Construct controls for overlaps with harmless segmentation changes, detached joins, created/closed counters, coincident
or cancelling contours, point-only and edge contacts, subpixel gaps and transformations. Reassess the existing `k/v/z`
candidates and the full captured matrix without changing fitting parameters. If a join is actually damaged, derive
attachment constraints from source geometry and verify them jointly; do not accept it by relaxing the reference. Review
width-only and grid output in the browser at native and enlarged scale, including neighboring sizes. Curved `y`, native
renderer adoption and deployment remain outside this slice.

#### Exact-join assessment

With the exact option, the captured 1,080-record matrix delivers 255 width-only and 259 grid-arm outlines; 226 of the
latter retain phase constraints and 33 explicitly deliver width-only fitting. All delivered results preserve the
reference's source, upstream and candidate topology signatures in this matrix. Curved outlines are unsupported by this
reference and keep upstream output, including cases where the strict-signature control could fit a distant straight
part. These totals describe this narrower eligibility scope, not an optical acceptance rate.

For default Roboto 400 at 16 px with font hints enabled, the source-projected mean diagonal widths are:

| Glyph | Upstream | Width-only |
| ----- | -------- | ---------- |
| `k`   | 1.373 px | 0.918 px   |
| `v`   | 1.292 px | 0.880 px   |
| `x`   | 1.346 px | 0.908 px   |
| `z`   | 1.648 px | 0.922 px   |

Both hint modes retain the measured components, counters, labeled attachments and contact singularities for these
results. **Acceptable deviation, scoped inspection:** browser comparison supports lighter diagonal weight and retained
visible joins for width-only `k/v/z` at the reported defaults. The exact reference resolves the split-signature
rejections for these candidates; no additional attachment constraints were needed for them. `y` stays upstream.

**Pending optical assessment:** grid placement does not establish a consistently preferable arm. At 16 px without font
hints, `k` reaches 0.761 px in the grid arm against 0.920 px with width-only fitting, producing a visibly thinner,
corner-connected staircase. Preserve both arms for review; do not select their targets by counting favored pixels.
Neighboring-size inspection includes hinted `k` at 12 px and `v` at 20 px. At larger sizes the fitted upright can widen,
so the same source-relative model can increase diagonal width; this is not a universal thinning filter. The full
size/weight sweep remains pending optical assessment, and this slice does not adopt either arm in the maintained app.

Analytic controls reject lost welds even when another contour keeps global connectivity unchanged, neutral seams do not
create counters, and a covered point-touch cannot disappear unnoticed inside a pair intersection. The geometry uses
exact rationals without a sampled-grid verdict. The 142 Hobby tests and 20 StrokeStyles compatibility tests pass. Corpus
checks preserve exact upstream commands and pixels on abstention, native-owned coordinates and coordinate bits, layout
metrics and command correspondence. The 2,160 strict-control arm results retain identical commands, decisions and width
measurements with the exact option disabled. These checks establish the measured contracts; finite combinatorial
invariants and passing tests do not prove preservation of every possible font feature or optical quality.

### Text-level width-only review

Freeze the direct-diagonal model, exact checker and original fifteen-glyph reference donors while assessing ordinary
text. Roboto at 12, 14, 16, 18, 20 and 24 px, weights 300, 400 and 700, with font hints enabled and disabled is the
primary matrix. SourceSans3 repeats that matrix as a secondary cross-font regression check; it is not an optical target
for Roboto. The approved preview selection and maintained app remain unchanged.

Capture the printable ASCII repertoire using the existing native policy. Additional text glyphs may receive the same
width-only fit but never become reference donors. Require exact capture and candidate parity for the original donors,
and retain native ownership, recorded raster settings and exact upstream fallback. Compose paired text from identical
finalized native advances, pair adjustments and line placement, preserving overhangs and explicit line breaks. Declare
the specimen text before rendering. Review at native size and integer enlargement, with per-glyph eligibility and
abstention visible. Grid fitting and curved-outline support remain separate questions.

The decision is whether ordinary text supports integrating this frozen width-only candidate into the app, or exposes a
specific defect that needs another experimental slice. Classify concrete findings and their scope; mechanical tests
establish data integrity, while browser inspection supplies the optical assessment. This review does not authorize a
native port, a change to fitting parameters, deployment or replacement of the approved baseline.

#### Text review assessment

The completed matrix contains 72 hint cells and 6,840 glyph decisions. The frozen model delivers 1,086 outlines; 925
delivered bitmaps differ from upstream. The original 1,080 donor instances retain their captured geometry and delivered
exact-join results. Additional ASCII glyphs receive the same model without contributing reference anchors. These counts
describe eligibility and activity, not an optical acceptance rate.

Paired paragraphs use the native finalized advances, pair adjustments and explicit line baselines. Both arms occupy a
common union frame, including negative overhang and the pen origin; leading spaces survive. The browser exposes native
size, integer enlargement, all applied glyphs and the original controls. The independent mechanical packet checks saved
layout and bitmap composition separately from optical judgment.

Browser inspection covers ordinary text, uppercase and the diagonal control line across all 72 cells, with enlarged
Roboto 300/12, 700/12, 400/16, 400/20 and 700/24 controls and SourceSans3 300/12 and 700/24 controls. Numerals and
symbols also receive an isolated 2x inspection across both families, all sizes and weights with font hints enabled.

| Classification                              | Finding and disposition                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Acceptable deviation, scoped browser review | Roboto 400/16 `k/v/x/z` has lighter diagonal weight in sentences while retaining visible joins and legibility in both hint modes. The size/weight sweep supports the width-only tradeoff in the inspected text; no new continuity or legibility defect was demonstrated.                                                                                      |
| Acceptable deviation, mixed weight changes  | This is width normalization, not universal thinning. Roboto 300/12 `x` grows from 0.678 to 0.919 px mean projected width, while Roboto 400/20 `v` grows from 1.617 to 1.757 px. Inspection supports the added weight against the fitted uprights; crossings and staircase terminals remain resolution-dependent. No pixel-specific correction was introduced. |
| Acceptable deviation, secondary control     | SourceSans3 retains readable text and visible attachments in the inspected matrix. Its own source and fitted upright relationships remain authoritative; its appearance supplies no target for Roboto.                                                                                                                                                        |
| Pending assessment, unchanged output        | Curved `y` and other unsupported curved neighborhoods keep upstream output. The reported heavy `y` concern remains unresolved. Grid placement, fonts beyond this two-family matrix and physical e-paper appearance are separate assessments.                                                                                                                  |

### Border-interval coverage study

The text review exposes incomplete intervention at default Roboto 400/16: `W` changes only one of four source contours,
while `y` stays upstream. A mean width over retained pairs describes those pairs, not coverage of the whole letter.
Resolve recognition and ownership coverage before considering a native port; the source-relative width targets and
fitting objective remain fixed.

Hobby section 3.2 supplies local medial intervals and competing-boundary clearance rather than whole-edge ownership.
Investigate whether distinct certified contact intervals can share a border without conflicting point ownership. For
curve-adjacent straight strokes, section 6 motivates keeping original curves while using geometric intermediates;
recognition and deformation must additionally certify clearance from the fixed curves. Any resulting certificate is a
project adaptation, not a demonstrated guarantee from Hobby. Uncertain ownership, clearance or topology keeps exact
upstream output. Curved-border fitting itself is outside this study.

The interval candidate maps each retained medial interval to its affine contact-foot ranges on both borders. Remove the
existing arithmetic guard's neighborhood from the actual medial intervals, recheck the retained core, and require strict
separation between competing cores on a shared border. Comparing eroded ranges while fitting the original interval would
hide uncertain overlap and is insufficient. Shared original controls still belong to one joint solve; the
reference-donor discovery retains its previous ownership rule so this study isolates diagonal coverage.

Intersection-derived sites must retain a common geometric identity. Independently evaluating the two sides of a crossing
can duplicate one junction by a few floating-point units and create a false near-tangent competitor. Construct the
crossing from exact rational input coordinates and transport its common point consistently for diagonal discovery; do
not merge unrelated nearby vertices by tolerance. Existing donor discovery remains the control.

For fixed curves, Bézier convex-hull containment and exact dyadic subdivision supply conservative clearance bounds
([Shene's construction](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/spline/bezier-construct.html) and
[subdivision](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/surface/bezier-sub.html)). A restricted topology
reference may replace curves by a polygonal intermediate only when each piece is strictly monotone along its chord and
its control hull meets every other boundary primitive solely at an incident shared endpoint. The piece is then a simple
graph and can deform to its chord inside an otherwise empty hull. Source, upstream and candidate must certify
independently before the unchanged exact arrangement checker compares their polygonal topology. Curve controls and
incident endpoints stay bit-identical to upstream. Uncertified contacts, loops, degenerate pieces or inexact
intermediate vertices abstain; curve fitting is still unsupported. This sufficient certificate is a project adaptation
of these geometric properties, not a claim of general curve-arrangement support.

Changed straight borders additionally clear the fixed upstream curves throughout their linear sweep. Exact hull
separation may admit an isolated shared endpoint only when it is pinned on both old and new segments; a positive dot
product between their remaining rays excludes collapse or reversal. Tangent-side agreement is unnecessary when the
entire swept hull meets the curve hull solely at that fixed endpoint. Unresolved hull contact abstains.

Use the same Roboto and SourceSans3 size, weight and hint matrix, original reference donors, ASCII captures, text and
native layout as the frozen text review. Preserve that review as a separate comparison baseline. New diagnostics must
show individual retained and rejected border intervals and delivered intervention coverage, alongside source, upstream
and candidate geometry. Include transformed synthetic controls, split and overlapping borders, ambiguous contacts and
fixed nearby curves. Mechanical checks and native-resolution browser assessment remain separate. The decision is whether
coverage can improve without damaging joins, curve attachments, contrast or layout; unresolved cases stay explicit
rather than being hidden by a glyph-wide applied flag.

#### Coverage assessment

At Roboto 400/16 with font hints enabled, the candidate delivers intervals across all four `W` contours and both `y`
arms, while the curved tail stays fixed. The extra short `W` interval belongs to the same source border near its lower
junction; common crossing identity resolves its previous uncertain contact. Browser inspection at native size and
integer enlargement supports lighter diagonal weight and retained visible joins for this default case. This is a scoped
acceptable deviation, not approval to port the experiment into the app.

The model retains source-relative weight rather than universally thinning: bold and larger cases can stay unchanged or
gain weight with their fitted uprights. Inspection includes Roboto 300/12, 700/12, 400/20 and 700/24, plus SourceSans3
300/12 and 700/14. A native-size scan of uppercase, lowercase and diagonal control lines across all 72 cells shows no
new visible continuity or legibility defect; ordinary paragraphs are additionally inspected at both families' 400/16
defaults. This supports the scoped browser tradeoff, while punctuation outside this inspection and physical e-paper
appearance remain pending. Unsupported curve contacts keep upstream output, and renderer adoption remains separate.
Roboto 300 at 12 and 14 px has an inherited merged double-quote contour in both upstream and frozen output; the
candidate's delivered bitmap is identical there, so geometric activity does not resolve that existing concern or
introduce a visible change.

The result supports a bounded native port of **width-only fitting behind an opt-in control**, retaining exact upstream
fallback and native ownership. Native/reference parity and runtime measurements gate app adoption; the experiment
establishes neither browser performance nor default-on suitability. Curved-border fitting and grid fitting remain
separate slices.

### Native width-only adoption

The native candidate carries the preferred coverage model, including its certified fitting of straight borders beside
fixed curves, into the maintained generator. `diagonal_fitting` is an independent, default-off pipeline preference for
automatic or selective-native monochrome fitting. Existing fitting, raster settings, native-owned coordinates, metrics
and layout remain the input authority. The original fifteen reference donors are captured at runtime under the same
font, axes, size and hint policy; additional text never changes their reference set. Missing donors or unsupported
features retain upstream output rather than substituting another font's standards.

Hobby's position, stretching, bending and relative-width equations and all recognition guards stay fixed. The width-only
solve eliminates pinned coordinates before a minimum-norm least-squares solve, using the same singular-value rank rule.
Hard grid-placement rows are outside this port. Exact rational crossing identity, Bézier hull certificates and the
measured filled-join invariants remain delivery gates. The portable topology implementation follows the
[arrangement model](https://doc.cgal.org/6.1/Arrangement_on_surface_2/index.html), splitting directed segments at exact
intersections, retaining coincident contour contributions and deriving face windings and labeled contacts from the
planar subdivision. It must agree with the independent CGAL reference; raster sampling is not a topology oracle. Runtime
work limits may abstain on complex inputs and must not alter accepted geometric thresholds.

Floating-point arithmetic is part of reference reproduction: neighboring boundary events can differ in their last bits,
which affects interval merging and station selection. The native arithmetic follows the reference's compensated
[CPython norm calculation](https://github.com/python/cpython/blob/v3.14.0/Modules/mathmodule.c#L2360), based on
error-free products, compensated sums and a square-root correction, rather than relying on platform-specific library
rounding. The geometric guards, event ordering and merge conditions remain fixed.

Adoption requires exact native command and raster reproduction across the frozen two-family ASCII matrix, unchanged
disabled-path output, runtime donor-reference parity and matching native/WASM text composition. Synthetic rank,
intersection, coincident-boundary, contact, counter and curve controls supplement the corpus. Verification compares
delivered results, including exact upstream fallback, rather than rejected attempts. Numerical differences must be
diagnosed without fitting parameters or pixel-specific exceptions. Browser inspection remains separate from these
mechanical gates, and the existing comparison stays available as the review baseline.

**Native verification, 2026-10-21 — implementation parity.** The native port reproduces all 6,840 delivered outlines,
decisions, recognized-pair counts, raster frames, coverage and pixels in the 72-cell preferred packet. Upright reference
identities agree, with scalar/vector comparisons bounded to relative `1e-12`. Native and WASM text output and layout
agree across 152 render checks; four Playdate exports agree byte-for-byte. The portable topology gate agrees with CGAL
on 5,388 supported corpus comparisons, 41 analytic controls and 1,500 random integer-contour controls. The frozen
comparison packets and Python model sources retain their original hashes.

The app toggle (on by default in new previews, explicit off honored) uses the same fitting in preview and export. A
default Roboto browser check observed a changed preview with the toggle enabled and exact restoration after disabling
it, with font hints still enabled. This records native implementation parity and browser operation; the iteration
remains open for optical assessment. Evidence lives under `out/diagnostics/direct-diagonal/native-port-verification/`
and `native-port-research/`; the repeatable check is `experiments/hobby_fitting/native_parity.py` and the compact frozen
regression packet covers 45 cases.

## Symmetry placement and curved-stroke study

The next isolated prototype asks whether source-derived approximate reflection and curved-width relationships can
resolve the reported asymmetric `x` and heavy `s` without changing the preferred diagonal width targets. Hobby §3.5,
(14)–(16), supplies approximate reflection correspondence; Hersch §5 supplies grid-compatible symmetry-center placement.
Hobby §6 maps medial-width contacts through polygonal intermediates to true Bézier points and extends the distortion
terms to curve controls. The [equation audit](references/papers/1993-hobby/audit.md) qualifies the symmetry normal and
fixed curve coefficients. Automatic recognition and conservative validity certificates are project adaptations.

The placement arm retains source asymmetry and width relationships rather than imposing exact reflection or selecting an
offset from its rendered pixels. The curve arm retains Bézier outlines, source contrast, terminals and joins; it must
establish which widths can change under existing native coordinate ownership. Incompatible native constraints or
uncertified geometry abstain. Integer-width snapping and relaxing native ownership are separate model changes.

Controls include translated/reflected synthetic outlines, asymmetric and curved controls, equivalent contour encodings,
ownership conflicts and nearby scales. Compare unchanged upstream, preferred width-only, placement and curved-width arms
over the existing two-family, 72-cell ASCII matrix, using captured scanner policy and native text layout. Keep the
current app, frozen comparison and approved baseline independently available. New output stays in an isolated browser
comparison; optical assessment precedes any maintained renderer adoption.

**Pending assessment, reported defaults:** Roboto 400/16, width 100, Mono with native hints has unchanged `s` output
because curved borders are unsupported. Its fitted `x` arms measure about 0.893–0.919 px; corresponding reflection-pair
midpoints retain the source values, about 3.938–3.969 px, while the final staircase is visibly asymmetric. Inspect grid
placement separately from source contrast, and investigate curved thickness without silently releasing native Y pins.

### Prototype outcome

The strict one-quantum reflection control is a recognition experiment, not a boundary between intentional and
unintentional asymmetry. The separate phase-range arm derives a locus of reflection-pair midpoints from polygonal
cross-sections and places the fitted locus within the nearest half-pixel centering cell. This is a project adaptation of
Hersch's phase ranges, rather than Hobby's full approximate-symmetry deformation. It admits non-overlapping closed
polygons, preserves all widths by an exactly representable rigid translation and keeps native coordinate bits. Curves
and ambiguous contacts abstain. Computed containment of the midpoint locus does not establish optical symmetry.

The curve arm recognizes a restricted class of opposing quadratic extrema with matching transverse positions. Exact
empty-disk, fill-side and curve-hull checks supply medial contacts on single closed contours. Hobby's relative-width
coupling uses the original mode-specific upright reference; curve position, stretching and bending are measured from the
existing fit. Native coordinates remain fixed. Rounded candidates must retain incident tangent directions and curve
orientation, bounded movement and independently certified finite topology invariants. These conservative gates can
abstain; they do not constitute general curved-stroke recognition or a proof of optical quality.

**Pending assessment, unchanged reported output:** in the default Roboto 400/16 selective case, placement translates `x`
by 3/64 px while leaving its delivered bitmap identical. Curved fitting leaves `s`'s commands and bitmap identical under
its native Y pins. With hints disabled, placement abstains for `x`; the attempted `s` curve deformation fails the
tangent-join gate and returns the exact existing fit. The simple centering and restricted curve-width prototypes
therefore do not resolve either reported default concern. New placements elsewhere require assessment of position,
balance and staircase continuity. They remain isolated from the maintained renderer.

The full 72-cell ASCII comparison contains 6,840 cases. Placement moves 250 outlines and changes 166 delivered bitmaps;
these placement changes remain **pending assessment**. The curve arm changes no delivered commands or pixels anywhere in
this matrix: its supported contacts are already fixed or its attempted deformations abstain. This is a negative result
for the restricted curve model, rather than evidence of a general curve correction. Exact upstream and preferred-raster
reconstruction, native coordinate bits, rigid-placement widths and finalized layout pass throughout; the existing app,
frozen packets and model sources retain their recorded hashes. The focused controls pass 80 tests, and independent Muse
review reports no remaining hard issue within the stated prototype scope. None of these checks establishes optical
acceptance or resolves the reported defaults.

### Joint placement and smooth curve continuation

The subsequent study asks whether width-compatible phase and joint curve constraints can address the unchanged default
output. Hersch §§5–6 distinguishes symmetry centers on pixel centers from centers between pixels, and connects stem
phase with discrete width. The placement hypothesis selects that phase from geometric width before rasterization, while
Hobby §3.5 supplies approximate reflection relationships. It must retain source contrast rather than force each diagonal
to an integer horizontal width. A symmetric outline with a subpixel crossing centered between pixel centers can still
require asymmetric dropout rescue; outline symmetry alone is insufficient.

For curved widths, Hobby §§3.2, 3.6 and 6 supply medial-radius measurements, relative-width coupling and correspondence
from polygonal intermediates to Bézier controls. The continuation expands recognition beyond axis extrema with an
explicit approximation bound. Hersch §2 supplies the endpoint derivative relationships used to retain smooth joins.
Shared tangent rotation is permitted; independently rotating the two sides of a smooth join is not. Native coordinates
remain fixed, and rounding error must be distinguished from deformation introduced by the solve. These adaptations are
project hypotheses, not demonstrated improvements to the reported glyphs.

Inputs remain the existing two-family ASCII packets and mode-specific upright references. Controls cover reflection,
translation, contour encoding, curved contacts, smooth and angular joins, conflicting ownership and nearby sizes. Before
any review candidate is published, compare the actual captured scan policy against the preferred output, check source
contrast, movement, layout, continuity and independent topology, and inspect the reported default glyphs in the browser.
Unchanged or ineffective results stay internal. Maintained adoption and optical acceptance remain separate decisions.

For horizontal phase, the bounded solve retains the existing Y fit and treats the selected reflection phase and X
movement limits as constraints, while relative-width and shape terms remain the objective. A feasible active-set
quadratic solve follows the equality-and-bound formulation of
[Forsgren, Gill and Wong](https://arxiv.org/abs/1503.08349). This numerical adaptation must satisfy the constraints and
optimality conditions before outline gates run; it does not choose a phase by inspecting pixels. Incompatible anchors or
unresolved numerics abstain. Width targets may be missed when phase and movement constraints bind, requiring explicit
optical assessment of that tradeoff.

The restricted placement class recognizes an internal crossing neck: its horizontal section changes from multiple ink
spans to one and back to multiple spans, with an interior minimum width. Exact critical sections distinguish this waist
from a silhouette tip. This geometric classifier is a project adaptation; approximate reflection still supplies the
correspondence and phase axis. Single stems, apexes and unsupported contacts abstain.

For the native-Y curve slice, joint cross products are linear in X and are constrained inside the same bounded solve.
Smooth joins retain zero cross product; other joins retain their upstream signed cross before quantization. The 26.6
conversion has a separately derived cross-product error envelope: an almost-collinear join may become collinear or
change sign inside that envelope, while nondegenerate legs, forward tangents and each quadratic's curvature gates remain
required. Exact closure aliases share a coordinate variable and are synchronized after rounding. The free-Y control
retains conservative linearization and geometry-gated feasible prefixes; it has no equivalent exact joint solve and is
excluded from the review candidate.

The curve recognizer reports polygonal medial diameters with a bounded correspondence error, not exact true-curve medial
contacts. Competitors must clear the upper radius of the full approximation shell; the movement allowance uses the
certified lower radius before reserving rounding headroom. Ambiguous contact ownership abstains rather than assigning a
width to a possibly different feature.

The candidate completes X while retaining the existing Y fit, whether Y came from native hints or automatic fitting.
[Turner and Lemberg §2](references/papers/2003-turner-lemberg/paper.md) separates fitting by axis, while Hersch §5
preserves reference heights and curved extrema. These sources justify preserving existing grid relationships; they do
not prove that coordinate pins preserve every delivered curve-to-stem attachment.

Mixed straight-and-curve outlines retain straight borders and their incident quadratic curves at their existing fitted
positions. Hersch §2's Bernstein representation and endpoint derivatives justify retaining all controls of an attachment
curve: endpoint pins alone preserve neither its interior nor its derivative. Closure aliases share this ownership.
Certified medial contacts elsewhere remain eligible for the existing source-relative width solve, regardless of the
stroke's direction. This local attachment boundary is a conservative project adaptation, not a proof of raster
connectivity. Width, tangent, clearance and exact arrangement gates still apply; unsupported local geometry abstains. No
segment-length threshold or font/glyph exception selects the movable region.

An exact constant line is omitted only from certificate primitives, following the CGAL arrangement's zero-edge winding
rule. This restores adjacency of the incident curves when upstream hinting collapses a source line. The original
operators and coordinates stay in the delivered outline; edges with distinct endpoints remain in the certificate. Source
validity and upstream/candidate finite topology comparison remain mandatory.

Earlier endpoint-only controls damaged Source Sans `h` and `m` attachments even with both stem coordinates pinned. Those
controls remain excluded. The local whole-curve attachment boundary must be assessed against these cases and Roboto
Flex's reported `s`, across nearby sizes and axes. Retaining every Y coordinate also limits normal-width changes where
the stroke runs nearly horizontally; this slice does not introduce a two-dimensional grid-placement solve.

### Source-feature correspondence probe

The source-only correspondence study asks whether geometric events and opposing-border contacts identify the controls
and dependencies needed for mixed straight/curve width fitting without assigning semantic terminal labels. It follows
Shamir's [outline-point and feature classification, section 3.3](references/papers/2003-shamir/) and Hobby sections 3.2
and 6 for boundary contact and curve correspondence. Geometric extrema, corners and tangent transitions describe the
boundary; they do not by themselves distinguish a stroke end from a join. Shared-control dependency reporting is a
project adaptation, not a new terminal detector.

Inputs are source outlines without hinting, with font-byte and axis identity, plus synthetic rectangles, curved ends,
seams, joins, holes and overlapping contours. Roboto and Source Sans `c h m o` supply the initial font controls.
Analytic characteristic events, existing certified width contacts, current attachment pins and ambiguous shared
ownership are reported separately. Reversal, translation, uniform scaling and exact subdivision check whether
correspondence depends on geometry or encoding. Unsupported primitives, ambiguous contacts and representation-dependent
matches remain explicit limitations rather than being repaired with glyph-specific rules.

This probe neither changes coordinates nor authorizes control movement. It uses no StrokeStyles output, fitting solve,
raster target or preview selection. A useful result must expose actual contact provenance and ownership conflicts; empty
or unsupported results cannot establish readiness. Solver continuation requires stable source correspondence and an
independently justified ownership/extent rule. Optical assessment of the reported terminal imbalance remains open.

The initial 2026-10-27 run retains six isolated extrema on Roboto `c` across reversal, changed contour starts,
translation, uniform scaling and exact subdivision. All four Roboto controls retain their isolated extrema under exact
subdivision; Source Sans coordinates require rounding, so that check explicitly abstains. These checks do not establish
complete feature classification: flat regions are reported separately, without a canonical extent, and arithmetic
describes the stored binary coordinates. The certified Roboto `c` curve samples change from eight to twenty-four under
subdivision. Individual measurements remain useful, but raw primitive counts are not stable feature identities or
justified fitting weights. The reused recognizers abstain on the tested multi-contour outlines and fail the substitution
certificate on Source Sans single-contour controls. No automatic ownership rule or moving region has been established;
see the [iteration finding](revisions/001/03-spacing-kerning.md#roboto-c-source-correspondence).

### Coupled whole-outline widths

The adopted model uses shared straight/curve X variables to restore source-relative width balance while retaining
upstream Y, fitted upright references, cap heights, closure and continuous joins. Hobby sections 3.1, 3.2, 3.6 and 6
supply integrated shape distortion, normal width relationships and shared curve variables; Hersch section 2 supplies the
Bernstein and endpoint derivative identities. The model does not require semantic terminal labels. Its broader variable
ownership, exact polynomial reassembly and aperture constraints are project adaptations, not results established by
those papers.

At an angular line/curve corner whose straight border is axis-aligned, retain the upstream curve tangent direction using
Hersch section 2's endpoint derivative. Retaining the cross-product magnitude between the line and curve would instead
couple cap length to fixed vertical coordinates while allowing the curve direction to rotate. The tangent constraint
preserves that direction and leaves width available to the shared solve. Smooth joins retain their existing
shared-tangent equations; other angular joins retain their preceding conservative constraint.

Straight-site white-space features use exterior fill membership and empty-disk clearance against the true source
boundary, following Hobby section 3.2. Their fixed affine projected gaps are hard equalities in the native-Y solve; this
is a stronger project constraint than the paper's finite width penalty. Candidate contacts must still certify outside
the filled shape. These features do not cover every curved aperture or counter. Missing certified white features, failed
source correspondence or incompatible constraints cause abstention.

Equivalent subdivisions must have equivalent fitting influence before any optical comparison. Analytically identical
adjacent quadratic pieces can be reassembled using exact de Casteljau identities, jointly verified on source and
upstream outlines. Shape and width terms operate on that common representation; output is expanded through the original
partition. Nonidentical polynomials, incompatible upstream partitions and reconstructions requiring rounding are
explicit limitations. No tolerance merges distinct curves. The initial slice admits single closed line/quadratic
contours; multi-contour and uncertified geometry retain the preceding result.

Controls cover exact subdivision and reversed/changed contour starts, source contrast, straight-to-curve joins, fixed
uprights, native-axis conflicts, collapsed edges and openings. Roboto `c` at 12/14/16/18/20 px is the initial reported
case; Source Sans `h`/`m`, Roboto Flex `k` and synthetic joins are falsification controls. Existing contact, movement,
curvature and independent topology checks remain required. Aperture relations need explicit geometric correspondence;
topological identity alone does not preserve an opening's width. No coefficient or region is selected from rendered
pixels or glyph identity.

The maintained generator owns the model, shared with WASM. The approved comparison and diagnostic evidence remain under
`out/diagnostics/coupled-outline-20261027/`. Success requires a useful delivered change with retained source contrast
and attachments; unchanged or invalid results are reported as limits rather than a correction.

The initial candidate narrows the reported default Roboto `c` end regions while retaining its fitted upright, end
directions, vertical coordinates and certified opening. The
[iteration assessment](revisions/001/03-spacing-kerning.md#coupled-whole-outline-widths) records visible and unchanged
cases. Reassembly supplies the same normalized source/upstream system under exact paired subdivision, and scanning keeps
that common partition through grid conversion. Expansion into the original partition remains exact-only; unrepresentable
expanded controls abstain. The single-contour and straight-site white-feature limits prevent this model from
establishing general join ownership.

The [revision index](revisions/001/README.md) owns the adopted renderer identity and approval status. Runtime never
imports experiment code or diagnostic data. The adopted slice requires native Y with automatic X, one closed
line/quadratic contour, exact polynomial reconstruction and source values representable without loss in the native
command format. Unsupported cases retain the preceding reviewed sequence. The existing diagonal-fitting preference
controls selection. Verification compares the port against the approved 58-case packet and checks broader native/WASM
behavior; approval does not remove the recorded geometric limits.

### Attached diagonal and curve constraints

This isolated continuation asks whether shared line-and-curve fitting can regularize a diagonal whose endpoint pins
prevent grid control. Hersch §6, Figure 25 supplies straight-border parallelization and integer horizontal separation;
Hobby §6 supplies shared Bézier variables and distortion terms rather than independent endpoint corrections. Hersch §2
supplies endpoint tangent relationships. The adaptation keeps upstream Y, native coordinates, vertical straight-edge X
anchors, closure aliases and finalized text layout fixed. Source-recognized straight border pairs and mode-specific
upright references determine the width target before rasterization. Connected curve controls may move with their
attached endpoints inside one bounded solve; incompatible constraints abstain.

The question is general to opposed straight borders attached to curves. No glyph identity, rendered-pixel count,
coverage threshold or preferred-bitmap lookup selects the fit. The existing width-only model can introduce taper, but
that observation alone does not prove the cause of an already-heavy staircase. Parallelism and joint grid placement are
an experiment to test, not an established correction for the reported numeral.

Inputs are the same Roboto and Source Sans ASCII captures, weights 300/400/700, sizes 12/14/16/18/20/24 and both hint
modes. The separate joint comparison supplies the visual baseline; the solve starts from original upstream coordinates
to avoid accumulating movement allowances. Controls cover affine coordinate encoding, contour reversal, native and
upright pin conflicts, welded endpoints, line-to-curve tangents, untouched geometry, and independent topology. Review
requires a changed delivered default result, intact joins and source contrast, exact layout and native-axis ownership,
then broader matrix inspection. Ineffective or demonstrably damaged variants remain internal; maintained adoption is
outside this prototype.

Hersch's border rotation permits angular line-to-line corners to rotate while retaining their orientation; curve joins
and collinear subdivision points keep their joint equations. With all Y retained, quadratic control-polygon curvature
and source-to-candidate tangent dot products are linear in X. The existing whole-interval curve certificate can
therefore be imposed as inequalities inside the solve. A 26.6 rounding-error reserve plus one cross/dot lattice quantum
preserves strict positivity after quantization; final geometry is checked independently. This adds geometric constraints
rather than relaxing a failed curvature check. The isolated numerical implementation uses SciPy's SLSQP with independent
feasibility and convex KKT checks; its coefficients and constraints remain fixed before rasterization.

Text-level assessment compares the frozen combined joint/curve and attached-diagonal result against the width-only
baseline, using their identical native advances, pair adjustments and line placements. The existing 72-cell Roboto and
Source Sans matrix supplies ordinary sentences, alphabets and numerals at native resolution and integer enlargement;
neither fitting coefficients nor scan conversion change during review. Inspect stroke weight and contrast, crossings,
curve and terminal shape, attachments and reading rhythm across nearby sizes, weights and hint modes. Source Sans
remains a control for changes outside the reported Roboto cases. Record demonstrated defects separately from unresolved
optical tradeoffs; this assessment does not itself authorize renderer adoption.

### Source contrast and crossing assessment

The Source Sans crossing assessment asks whether its non-mirror source geometry explains the delivered `x`/`X` balance,
or whether fitting and scan conversion amplify the difference. Hobby §3.5 treats approximate symmetry as a source
relationship, while §3.6 preserves relative widths; Hersch §§5–6 separates positioning on the grid from diagonal width.
Exact bitmap reflection is therefore not an acceptance requirement.

Compare independent, unrounded variable-font outlines, captured source and automatic outlines, width-only output and the
combined candidate at weight 400 and 12/14/16/20 px in both hint modes. Roboto supplies the existing crossing control.
Analytic horizontal sections at one eighth, one quarter, three quarters and seven eighths of each outline's height
describe the two arms' projected widths, separation and midpoint; these projections are not normal stroke widths.
Sections through a merged crossing have a different role and are not counted as two arms. Replay the captured Mono
scanner policy, retain original text layout, and inspect source contours alongside delivered pixels. Terminal widths
alone, mirror mismatch or ink totals do not establish preserved or damaged contrast. Record source asymmetry separately
from amplification introduced by geometry and scan conversion before deciding whether a model correction is warranted.

At certified straight-arm contacts, also compare separation along the existing fixed source normals, reporting the
individual pairs and their angles rather than a glyph-wide mean. Keep the source medial diameter distinct from this
projection when source borders are not parallel. The unrounded source and captured source can disagree on the sign or
vanishing of very shallow quadratic curvature; capture precision is therefore part of recognition evidence, not an
optical verdict about the font.

The recommended continuation retains unrounded source geometry for feature predicates, with rounded delivered
coordinates and their existing guards treated separately. Hobby §6 recognizes approximate symmetry on polygonal
intermediates and transfers the corresponding distortion terms back to curve controls. Extending that correspondence to
a shared crossing-placement solve, while retaining source contrast, existing Y and native ownership, is a project
hypothesis requiring its own controls and optical review. Preserving source precision does not by itself establish
correct crossing placement, and the curvature gate must not be relaxed to recover a particular glyph.

### Curved crossing prototype

The isolated continuation applies the approved source-preserving crossing hypothesis to one joint X solve from the
original automatic/native fit. Independent unrounded source coordinates supply approximate reflection and relative-width
relationships; the captured source remains a separate reference. Hobby §§3.5–3.6 and §6 supply curve correspondence and
distortion terms, and Hersch §§5–6 supply geometric phase control. The adaptation must retain source asymmetry rather
than seek reflected pixels. Existing Y, native X ownership, upright X anchors, shared closure coordinates, bounded
movement and finalized layout remain constraints. Delivered coordinates cross the existing 26.6 boundary once.

The supported feature is a crossing with recognized straight arm borders and connected quadratic attachments. Stroke
width pairs and opposite-arm reflection matches remain distinct. The arm contacts must establish both diagonal
directions above and below the same source waist; a fork above a separate hook does not establish a crossing at the
hook. Hobby (16) supplies finite reflection distortion around the selected mapping parameter, alongside (17)
relative-width distortion; source mismatch remains in the reflection residual. The selected parameter gives a phase
preference, not an exact delivered-axis guarantee. Requiring every approximate match as a hard equality gives shared
vertices incompatible constraints after automatic Y fitting. Source-smooth joins retain hard tangent continuity;
source-sharp joins retain orientation and non-degeneracy while Hobby's shape terms control angular distortion. Keeping a
quantized upstream kink magnitude is not a source requirement. These adaptations must be checked across contour
encodings and source-asymmetric controls before optical assessment.

Inputs and evaluation retain the two-family ASCII matrix, weights 300/400/700, sizes 12/14/16/18/20/24 and both hint
preferences. Initial falsification uses the reported Source Sans 400/16 `x`, nearby Source Sans crossing cases and
Roboto controls, with the preceding combined packet as the comparison baseline. Curvature signs and forward tangents use
the unrounded source, with independent rounded-output validation, clearance and exact finite-topology checks.
Unsupported correspondence, ownership conflicts or incompatible constraints retain the preceding delivered result.
Synthetic curved crossings, source-asymmetric controls, reflections, translations, contour encodings and native pins
test the geometry without preferred pixel fixtures. A changed bitmap with retained source relationships is required
before visual review; mechanical success alone does not establish optical acceptance or authorize renderer adoption.

The isolated [comparison](https://solitaire.taile005dc.ts.net:8912/) evaluates 72 cells and 6,840 ASCII cases, with 32
changed Source Sans `x`/`X` bitmaps. Native replay, retained coordinates, bounded movement, shared layout and
independent raw/captured topology checks pass; the 427-test suite includes source contrast, captured precision loss,
translation, reflection, contour rotation, reversal and closure aliases. No changed case adds an eight-neighbor ink
component; that census does not establish optical quality. Unsupported inputs retain the preceding combined result.

Default Source Sans 400/16 `x` loses its isolated upper-right row while keeping source contrast: mean arm widths change
from about 1.125/1.186 px in the unrounded source to 0.855/0.915 px. `X` changes from 1.185/1.245 px to 0.897/0.956 px,
with a wider ink extent and redistributed crossing/terminal pixels. Browser inspection includes 400 at 14/16 px, the 16
px hints-disabled case, ordinary text and unchanged Roboto controls. Terminal balance, crossing weight and the wider `X`
footprint remain **pending optical assessment**. The remaining changed weight/size cases are also pending; no renderer
adoption or broader acceptance follows from these checks.

### Terminal reference-height constraints

The next isolated continuation preserves source-horizontal supporting cap edges at their original automatic/native
reference heights inside the width solve. Hersch §§5–6 supply reference-line phase and diagonal-width control; Hobby
§3.3 supplies common displacement of important horizontal regions. The project adaptation recognizes a nonzero
horizontal straight source edge with equal endpoint heights also present upstream. Both endpoints retain those upstream
Y coordinates while eligible X coordinates and other unowned coordinates participate in the existing source-relative
width solve. The height belongs to the preceding fit, rather than to a new rounding target. This includes stroke ends
and horizontal interior reference edges below a taller ascender; control-box extrema classify diagnostics, not
eligibility. Curved extrema, ambiguous fitted heights and source edges that are not horizontal do not create these
constraints. Width recognition still uses opposing stroke borders and source-relative coupling independently of these
height constraints.

Nonzero source-vertical straight edges retain both endpoint X coordinates at their original fitted values. This extends
the existing upright ownership to short upright attachments sharing diagonal vertices; it preserves their reference-line
phase while leaving eligible Y coordinates in the solve. Native ownership and curve anchors still take precedence.

The reported Source Sans 400/16 `A` feet and `y` upper terminal supply initial falsification cases: the preceding
width-only geometry moves their originally flat edges below the baseline or across the x-height. Restoring automatic Y
in a causality control removes the reported pixels, but that coordinate restoration is not the proposed fitted result.
The candidate must solve with the constraints present, keep curve ownership and native coordinates, preserve source
width relationships, respect bounded movement and pass independent topology and scanner replay before optical review.
Use the same two-family, three-weight, six-size and two-hint ASCII matrix, with the curved crossing packet as the
comparison baseline. Existing crossing/curve results remain the delivered fallback outside this feature. Tests cover cap
recognition, source and upstream plane agreement, transformations, closures, native pins and real terminal cases.
Broader terminal balance and any neighboring stroke changes remain optical questions; renderer adoption is separate.

The delivery scope is a geometric constraint violation in the preceding packet: when all recognized cap endpoints
already retain their original fitted heights, keep that packet. This retains existing crossing/curve improvements and
avoids replacing unrelated fitting merely because a source cap exists. Applicability is decided from coordinates before
rasterization, without a glyph list or pixel-dependent selection.

The isolated [terminal comparison](https://solitaire.taile005dc.ts.net:8913/) covers all 72 cells and 6,840 ASCII cases,
with 852 applied fits and 291 changed bitmaps. The 464-test suite, native replay, exact ownership, bounded movement and
independent source/captured topology checks pass. The
[iteration findings](revisions/001/03-spacing-kerning.md#terminal-reference-heights) record the corrected default Source
Sans terminal pixels and pending neighboring stroke, accent and matrix assessment. No changed case adds an
eight-neighbor ink component; this is not an optical acceptance criterion. Unsupported closure ownership retains the
preceding packet. The maintained app and older previews remain separate.

### Approved fitting sequence adoption

On 2026-10-21 the user approved the terminal comparison at port 8913 for the main app. Adoption carries its complete
fallback sequence: width-only fitting, disjoint straight crossing or curved-width fitting, attached diagonals, curved
crossings, then terminal constraints where the preceding result violates recognized cap heights. Later stages use the
same original source/upstream inputs as the reviewed harnesses; they do not blindly stack corrections. The original
fifteen runtime donor glyphs and existing diagonal preference remain authoritative.

The implementation evaluates replacement priorities lazily: a successful later-stage solve makes overwritten earlier
solves unnecessary. Curve completion still receives the width result as its preferred stream; all other replacement
stages retain their original inputs. Terminal applicability is checked against the selected delivery, preserving the
reviewed fallback semantics.

Curve-pair recognition uses [bound-based pruning](https://web.stanford.edu/class/ee364b/lectures/bb_notes.pdf): a
conservative upper bound on a segment pair's returned interval span excludes it only when strictly shorter than the
interval already selected for that curve pair. The bound covers floating-point root transport and endpoint
reconstruction, rather than only ideal overlap. Pair order, tie behavior, recognition diagnostics and selected geometry
remain unchanged; uncertain bounds retain full evaluation.

Exact curve and arrangement construction follows the binary-fraction model of
[CGAL `MP_Float`](https://doc.cgal.org/latest/Number_types/classCGAL_1_1MP__Float.html): checked integer mantissas
promote to arbitrary-size integers, while non-dyadic quotients retain general rationals. This project adaptation
preserves exact input coordinates and existing rational-to-float rounding at output boundaries. Predicate filtering,
source tangency, delivery clearance and subdivision limits retain their existing meaning. Arrangement intersections,
face probes, vertex ordering and winding decisions retain exact rational semantics; their orientation predicates use the
shared scalar-native certified filter.

Runtime preparation follows
[Skrifa's reusable hinting-instance model](https://docs.rs/skrifa/0.48.0/skrifa/outline/struct.HintingInstance.html) and
Rust's [once-initialized cells](https://doc.rust-lang.org/std/cell/struct.OnceCell.html). One request shares identical
source captures without hinting and immutable source analysis; raw font geometry and modified streams remain separate.
Source-only capture retains outline, repertoire and raster-bound validation while omitting discarded coverage and report
assembly. Dependency provenance is prepared at build time. Source preparation and capture share byte identity within a
request; owned loaded fonts retain that identity across requests. This changes work scheduling and representation rather
than feature eligibility, solve order, validation or delivered output.

Exact arrangement construction and canonical visibility splitting use the
[CGAL closed-box broad phase](https://doc.cgal.org/latest/Box_intersection_d/index.html): segment bounds come directly
from finite input endpoints. Only strictly disjoint boxes bypass exact intersection construction; shared endpoints,
zero-width boxes, collinear overlaps and uncertain contacts retain the exact path. Intersection coordinates, exact cut
parameters, segment order, winding classification and computational budgets remain unchanged. Visibility endpoints that
are not finite bypass the rejection, and the legacy floating splitter retains its original path.

The constrained solver follows
[the nalgebra SVD interface](https://docs.rs/nalgebra/0.35.0/nalgebra/linalg/struct.SVD.html) to reuse the nullspace and
reduced-objective decompositions for an unchanged ordered working set. A full step changes only the residual; adding or
releasing a constraint discards both factors. This project adaptation retains the current minimum-norm solution, rank
thresholds, floating-point accumulation order, constraint decisions and delivered output. No factor crosses a
working-set change or a solver invocation.

Ordered objective operations follow [NIST sparse matrix operations](https://math.nist.gov/spblas/): retain exact nonzero
supports in original row/column order, reuse the immutable transposed objective product and the current gradient's
matrix product. Zero or non-finite results and exceptional operands retain the dense arithmetic path. SVD dimensions,
rank decisions, working sets and delivered geometry remain unchanged; no approximate sparsity or QR compression is used.

WASM norm arithmetic replaces software-emulated fused products only where the error-free
[Split/TwoProduct transformations of Ogita, Rump and Oishi, algorithms 3.2–3.5](https://www.tuhh.de/ti3/paper/rump/OgRuOi05.pdf)
prove the same rounded product and correction. Conservative arithmetic-range guards exclude intermediate underflow and
overflow; exceptional ranges retain fused multiplication. This adaptation retains product/correction bits, including
signed zero, and the compensated sum and square-root correction sequence. Interval decisions and delivered output retain
their existing meaning. Native arithmetic remains on the existing fused path.

The maintained implementation must reproduce the reviewed delivery, including exact fallback, retained native
coordinates, source contrast, bounded movement, topology and scanner output. Raw source features must retain unrounded
font geometry independently of the captured 26.6 source. No experiment files or precomputed glyph results may become
runtime dependencies. Native and WASM parity, disabled-path identity and measured runtime gate deployment. The prior app
and isolated comparison remain available until those checks pass. Approval permits adoption of this reviewed sequence;
it does not close iteration 001.03 or resolve unrelated pending curve/aperture findings.

<!-- cspell:words HarfBuzz -->

The native raw-source adapter uses Skrifa's floating-point HarfBuzz outline path in font units, followed by f64 scaling.
The FreeType unscaled path rounds variation coordinates to integers and is unsuitable for these features. This is
continuous source geometry before 26.6 capture, not bit-identical f64 instancing: the font-unit pen and variation
scalars retain Skrifa's f32 precision. Across 3,420 source cases, contour structures agree with the independently
instantiated reference; the largest coordinate difference is about 0.000242 px. Delivered-command comparison and exact
raster parity, including source-curvature and supporting-plane recognition, gate deployment. The
[native adoption verification](revisions/001/03-spacing-kerning.md#native-adoption-verification) classifies the observed
outline differences and retains unrelated pending findings.

The shared native/WASM sequence is adopted by the maintained renderer and deployed in the main app through the existing
diagonal opt-in. The linked verification record owns the corpus, browser and publication evidence; the approved
comparison remains available independently.
