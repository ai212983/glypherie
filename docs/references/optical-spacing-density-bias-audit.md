<!-- cspell:words Hersch Hu scanlines Bétrisey -->

# Optical spacing density bias audit

The
[candidate design](../designs/text-layout/contextual-spacing-and-healing.md#source-designed-shared-density-candidate)
owns behavior. This audit tests whether the reported preference for -1 px tracking exposes an error in the spacing
mechanism. No solver, renderer or preview changes follow from this investigation.

## What the primary sources establish

[Hersch et al. 1995, pp. 85–88](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf#page=9) describes generic
transformed-space calibration using designed `nn`/`HH` pairs. It also describes six source-master stem/curve spacing
standards: `nn`, `HH`, `oo`, `OO`, `no`, `HO`. That specialized path uses vertical borders at stem edges or curve
extrema and corresponding tabulated spacing. It is a separate measurement/reference convention, not six arbitrary
targets for the generic filtered-wall integral. The paper does not state that all generic `nn` calibration is invalid or
inevitably widens every typeface. Its adaptive rounding uses occurrence-weighted fractional-distance distributions.

[Hu 1998, section 4.4, printed pp. 88–91](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf#page=94) computes
spacing for parametric characters without predefined advances. Its bitmap walls, concavity filtering and integrated
space supply the layout, rather than guaranteeing conservation of existing font widths. It additionally names `nn`
stem/stem and `oo` curve/curve standards and depth/minimum-space controls.

[Hersch and Bétrisey, US5768490A, preferred embodiment and claims 1–4](https://patents.google.com/patent/US5768490A/en)
supports a generic shared ideal space obtained by applying the same visual-space transformation to a designed reference
pair and candidate pairs. It discusses grid-fitted outlines, intelligent rounding and subpixel contour clearance. It
does not establish that this project's delivered-reference choice is necessarily a coding defect, nor promise source
text-width conservation. Both the full-cell raster realization and the source-reference/delivered-candidate split remain
project adaptations with disclosed windows and coordinate conventions.

## Current implementation and measured cause

At Literata 400/16 (`opsz=16`), the lowercase Lynx preset contains 1,297 eligible letter-pair occurrences. The latest
`hu_source_calibrated` result expands average origin-to-origin placement by **0.706 px** relative to captured source
metrics. The actual solver decomposes that expansion as follows:

| Contribution                                               | Mean px per occurrence |
| ---------------------------------------------------------- | ---------------------: |
| Replacing designed pair scores with the shared `nn` target |                 +0.361 |
| Source-to-delivered facing-wall geometry difference        |                 +0.292 |
| Whole-pixel rounding                                       |                 +0.042 |
| Active clearance enlargement                               |                 +0.011 |

A source-only counterfactual, without rasterization, rounding or clearance, retains the first **+0.361 px** expansion.
Thus generic equal-target placement already re-spaces this designed font before any raster distortion exists. This
conflicts with the desired density outcome, although its mathematics follows its declared objective. The source `nn`
score is 3.166 px; the source corpus mean is 2.805 px. Neither number alone establishes perceived optical quality.

The **+0.292 px** geometry term is already +0.294 px in raw walls before filtering. Its aggregate filter change is only
-0.002 px; individual filter changes remain significant and can cancel. An independent full-cell oracle finds exact
source/bitmap agreement for 1,080 identical physical shapes. This falsifies a universal one-pixel edge/center mismatch
within the tested representations, without proving author-code parity or perceptual correctness for real glyph shapes.

Normal-browser word widths provide a separate reference: the latest Mono result adds **0.794 px per internal pair**
across 218 ASCII words. This includes final advances and browser shaping; it must not be confused with the origin-step
or filtered-gap measurements. Source-relative compensation preserves each pair's continuous source score, but still
expands the measured mean origin step by 0.359 px after delivered geometry, rounding and clearance. It does not preserve
exact source text density.

## Disposition

The density concern remains unresolved. The main mismatch is treating generic shared-target automatic spacing as though
it preserved the designed font's density. There is no evidence for a universal one-pixel arithmetic addition. Other
families move differently, ruling out a general -1 px correction.

The six published stem/curve standards are a grounded next experiment; their existence does not prove they will fix the
reported pairs. Validate their source-only behavior and overall density before adding delivered bitmap geometry. Any new
classification must have a geometric basis, without glyph exceptions. Do not fit a target offset to the requested text.
Negative tracking can create cell contacts after clearance, and matching an average does not establish optical balance.
No hidden density offset is recommended by this audit.

Detailed decomposition, interventions, original-font browser measurements, identities and the independent coordinate
oracle are retained under `out/diagnostics/contextual-spacing/density-bias-audit/`.
