<!-- cspell:words Hersch Hu scanlines Bétrisey -->

# Shared-target density calibration

Audit and calibration policy for the Hu/Hersch optical spacing model. The
[owning design](../designs/text-layout/contextual-spacing-and-healing.md#hu-hersch-delivered-bitmap-candidate) and
[delivered model note](hu-hersch-delivered-model.md) specify delivered candidate scoring. This note examines reference
target density calibration.

## Published foundations

[Hersch et al. 1995, pp. 85–88](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf#page=9) defines "ideal
visual space" as the whitespace between optimally spaced design reference pairs: `nn` for lowercase, `HH` for uppercase.
Transformations A–D bound exterior cavities and normalize by character height.

[Hu 1998, §4.4, pp. 88–91](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf#page=94) measures discrete bitmap
walls using ±45° slope filtering and solves Kerning Adjustment Space $\text{KAS} = \text{IOS} - \text{PES}$, where
$\text{IOS}$ (Ideal Optical Space) represents the benchmark straight-stem design standard.

[Hersch and Bétrisey, US5768490A](https://patents.google.com/patent/US5768490A/en) specifically addresses spacing
distortions induced when continuous outlines are grid-fitted to low-resolution rasters. The patent explicitly states
that the ideal optical inter-character space is extracted from _by design optimally spaced character pairs_ (`nn` and
`HH`). Grid-fitted character positions are adjusted to reproduce this typographic benchmark.

## Original method versus project adaptation

The primary literature motivates a target derived from designed reference pairs. It does not establish parity for this
project's source-curve sampler, delivered-cell cavity extraction or retained raster-derived integration window.
Measuring continuous source reference outlines and source metrics is the candidate evaluated here, rather than an exact
reproduction of the published implementation.

In this project's initial delivered adaptation (`hu_calibration.py`), target density was measured directly on _delivered
raster bitmaps_ at _finalized integer advances_. In Literata 16 px (wght=400, opsz=16):

- Source `n` advance is 10.406 px; finalized raster advance is snapped to 11.0 px (+0.594 px).
- Measuring the delivered raster `nn` at step 11.0 px produces a target score of **3.625 px**.
- Measuring the source `nn` at its designed step (10.406 px) yields **3.166 px**.
- Measuring the source lowercase corpus mean (Lynx preset, 1,297 occurrences of 506 distinct pairs) yields **2.805 px**.
- Driving delivered pairs to the 3.625 px raster target yields an output mean of **3.628 px** (+0.822 px looser than
  source corpus mean).

The +0.822 px discrepancy decomposes into:

1. **+0.459 px** raster-reference shift (`target_px` 3.625 vs source `nn` 3.166), including both outline-to-bitmap
   geometry and metric quantization; this is not advance rounding alone.
2. **+0.361 px** reference representativeness (straight-stem `nn` 3.166 vs curved/open corpus mean 2.805).
3. **+0.003 px** mean rounding residual.

Scoring candidate pairs on delivered raster cells adheres to Hu 1998 and US5768490A; however, anchoring target density
to the rasterized, integer-snapped reference glyph propagates that reference's geometry and metric changes into the
shared density of all eligible pairs.

## Comparison of calibration approaches

1. **Source-measured reference target (candidate)**: Measure target density on continuous source `nn`/`HH` outlines and
   design advances; score delivered candidates on delivered bitmap cells. Follows the patent's designed-reference
   principle. Removes the observed +0.459 px reference shift in Literata without tuning; other typefaces can move in the
   opposite direction.
2. **All-alphabet source mean calibration**: A fixed alphabet average would require a declared repertoire and weighting;
   a requested-text average would make calibration text-dependent. The measured 2.805 px is the Lynx preset's source
   mean, not an all-alphabet mean. Neither average reproduces the papers' `nn`/`HH` reference choice. They remain
   possible separate experiments, not established defects or improvements.
3. **User target offset before rounding/clearance**: Applies an optical density bias inside the solver prior to rounding
   and clearance (`clearance_min_step_px`). Unlike layout-level letter-spacing (which caused 56 contact pairs at -1
   tracking by bypassing the clearance guard), a pre-clearance density control guarantees physical cell separation while
   allowing overall density adjustments.

## Bounds and limitations

- **Reference representativeness**: In the retained Literata measurement, source `nn` scores wider than the source
  corpus mean. This does not establish that forcing every pair toward `nn` is perceptually correct; visual assessment
  remains required.
- **Clearance priority**: The candidate applies its density target before the existing clearance guard. Deliberate
  tracking remains a separate layout control applied afterward; negative tracking can create contacts and is not the
  candidate correction.
- **Window consistency**: Source and delivered wall integration must use the identical physical window (tight bounding
  box of `n`/`H`) and midpoint sampling grid. The window still depends on delivered reference bounds. Captured source
  advances and pair adjustments have nearest-1/64 px precision; the retained outline coordinates remain continuous
  design units.
