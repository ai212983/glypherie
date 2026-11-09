<!-- cspell:words Cozens tensorfont CounterSpace scanlines sidebearings scanline bilevel unoriented monkeypatch countershapes Changyuan Parametrisable André Gürtler -->

# CounterSpace cavity classification and small-raster geometry

## Question and findings

In the Literata 16 px (`opsz=16`, `wght=400`) probe
([`probe.json`](../../out/diagnostics/contextual-spacing/counterspace-repeat-pairs/probe.json),
[`findings.md`](../../out/diagnostics/contextual-spacing/counterspace-repeat-pairs/findings.md)), repeated `ff` widened
from step 6 to 8 px under the fixed-weight byte-intensity repair, but `cc` remained at 8 and `zz` at 9 px (minimum gaps:
1 and 2 px). The classifier reports discontinuity 0.333 on the left and 0.167 on the right of `f`, with reduction 0.833
on both faces. In contrast, the open right face of `c` and both faces of `z` report discontinuity 0.0 and reduction 0.0.

This note determines what is an implementation bug versus an upstream heuristic limitation, examines how 12× replication
interacts with the 5% m-width jump threshold, and evaluates two source-derived classifier comparisons. Per-glyph rules,
assumptions equating counter area with optical rhythm, and unverified classifier patches are excluded.

## Bug versus heuristic limitation

The zero discontinuity for `c` and `z` follows the signed-sum gate in
[tensorfont 0.0.6](https://simoncozens.github.io/tensorfont/). This is confirmed behavior and a limitation for detecting
these recesses. The unused absolute-sum variable alone does not establish that changing the gate is an intended bug fix.
The separately verified intensity-domain mismatch is the confirmed implementation defect.

In `tensorfont.GlyphRendering.discontinuity(contour, tolerance=0.05)`:

```python
steps = c[1:] - c[:-1]
non_edges = ((c[:-1] != -1) & (c[1:] != -1))
jumps = np.abs(steps) > (self._glyph.font.m_width * tolerance)
total = np.abs(np.sum(steps * non_edges * jumps))
total2 = np.sum(np.abs(steps * non_edges * jumps))
return np.clip(total / self.shape[1], 0, 1)
```

Line 390 computes `total` as the absolute value of the signed sum of filtered steps. Line 391 defines `total2` as the
sum of absolute jump magnitudes, but line 393 returns `total`. For entering and returning contours, inward and outward
jumps telescope and cancel:

- `c` right face: Row 140 step is -12; row 164 enters the bowl (+60); row 200 exits (-60); row 212 is +12. The signed
  sum telescopes to $-12 + 60 - 60 + 12 = 0$.
- `z` left face: Row 164 cuts in (+36); rows 176, 188, 200 step back (-12 each). The sum is $36 - 12 - 12 - 12 = 0$.
- `z` right face: Rows 140, 152, 176 step (+12 each); row 188 steps (-36). The sum is $12 + 12 + 12 - 36 = 0$.

Because `total` is 0, `discontinuity` returns 0.0. In
[`CounterSpace.py`](https://github.com/simoncozens/CounterSpace/blob/01b33477225eb5fc7bedf93a090b5cd7dd0c812b/CounterSpace.py#L110-L128),
reduction is gated by `if fg.discontinuity(...) > 0`. Zero discontinuity sets `conc = 0`, bypassing concavity reduction
and leaving the mouth of `c` and diagonal bays of `z` fully integrated into exterior whitespace.

Switching to absolute jump magnitudes does not by itself establish a valid cavity classifier. In his
[reference notebook](https://github.com/simoncozens/CounterSpace/blob/01b33477225eb5fc7bedf93a090b5cd7dd0c812b/Spacing_with_countershapes.ipynb)
(cells 20, 29, 31), author Simon Cozens explicitly treats discontinuity smoothing as an experimental heuristic to
prevent deep recesses (`LT`) from distorting spacing. He acknowledges that "the discontinuity smoothing process is hard
to get right," noting that glyphs like `XX` space too wide. The gate measures net contour change rather than explicitly
testing for a concave bay. It is evaluated on the full glyph before the reference-height clipping used by scoring. The
subsequent reduction interpolates toward the global convex hull; excessive reduction can suppress meaningful diagonal
whitespace. Neither behavior establishes the cause of every reported optical concern without a counterfactual.

## Small-raster stair interaction

Literata 16 px has an `m_width` of 16 delivered pixels, expanded 12× to 192 analysis pixels. The 5% tolerance threshold
is $0.05 \times 192 = 9.6$ analysis pixels.

In a bilevel 1-bit raster, every single-pixel stair step is 12 analysis pixels wide ($12 > 9.6$). Consequently:

1. Every native 1px stair along curves, diagonals or serifs is classified as a macro-jump (`jumps = True`).
2. Continuous slopes do not exist on the replicated grid; diagonals are treated as discrete 12px jumps.
3. On `n` right, terminal steps (-12 and -12) yield discontinuity 0.222 and request an 87.5% blend toward the convex
   hull. On `n` left, opposing steps cancel to 0. This asymmetry is measured behavior; it does not by itself prove which
   filtering is perceptually appropriate.

## Analytic falsifiers and material objections

- **Signed cancellation falsifier**: A rectangular bay whose two qualifying steps are $+\Delta x$ and $-\Delta x$
  returns zero net discontinuity despite nonzero depth. This isolates the gate's cancellation behavior.
- **Raster-stair sensitivity**: The threshold is below one delivered pixel ($9.6 < 12$), so native stairs qualify as
  jumps. Enlarging the bitmap does not recover continuous geometry. Uniformly scaling the same bitmap and metrics
  preserves this ratio; this observation is not a failure of that scaling invariant.
- **Material objection to `total2` patch**: An empirical probe with absolute jump summation (`total2`) causes `n` left
  to report discontinuity 0.222 and reduction 0.750. Because `nn` is the lowercase calibration reference, reducing its
  reference cavity lowers the target score from 3999.35 to 3369.84. This pulls `ff` tighter (step 8 to 7 px) while
  leaving `cc` at 8 and `zz` at 9 px.
- **Optical rhythm objection**: CounterSpace minimizes a Gaussian-weighted exterior area target. The existing guard
  excludes ink contact, but the resulting minimum gaps can still look crowded. Equal area is not an optical acceptance
  test, and a classifier change cannot be assumed to resolve rhythm.

## Bounded classifier comparisons and disposition

Normal refitting after the intensity repair retains the diagnostic `ff` 8 px, `cc` 8 px and `zz` 9 px steps. The
independent host
[classifier probe](../../out/diagnostics/contextual-spacing/counterspace-intensity/classifier-probe.json) compares
signed jumps, absolute jumps and the notebook cell 21 formulation (`conc = 1 - face()` without the gate). All glyphs and
references use each rule consistently, with fixed fitted weights; no reference stem receives an exception.

Both alternatives change the `nn` target to 3369.84 and select `ff` 7 px, `cc` 8 px and `zz` 9 px. They therefore fail
to resolve the reported pair placements in this controlled comparison. This does not establish how a separately refitted
model would behave, but it rules out treating either change as an already demonstrated correction. The author's reported
`XX` over-spacing remains a material objection to increasing convex-hull reduction generally.

Neither classifier alternative is adopted. The confirmed intensity repair remains isolated in the rebuilt preview.
Further classifier or scoring changes need a separate source-backed proposal and held-out optical evidence, including
reference-pair calibration, native raster stairs, open bays, diagonals and serifs. Hu/Hersch remain deferred comparisons
under the user's current CounterSpace scope.

## Bibliography

- Simon Cozens. _CounterSpace: Spacing with countershapes_. Repository and Jupyter notebook, commit
  `01b33477225eb5fc7bedf93a090b5cd7dd0c812b`.
- Simon Cozens. _tensorfont: Font tools using NumPy/TensorFlow arrays_. Version 0.0.6.
- Changyuan Hu. _Synthesis of Parametrisable Fonts by Shape Components_. EPFL thesis 1905, 1998, §4.4.
- Roger D. Hersch, Claude Betrisey, Justin Bur and André Gürtler. _Perceptually Tuned Generation of Grayscale Fonts_.
  IEEE Computer Graphics and Applications 15(6), 1995.
