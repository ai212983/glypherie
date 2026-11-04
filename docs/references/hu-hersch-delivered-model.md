<!-- cspell:words Hersch Hu scanlines Bézier Betrisey -->

# Delivered Hu/Hersch optical spacing

The [owning design](../designs/text-layout/contextual-spacing-and-healing.md#hu-hersch-delivered-bitmap-candidate)
specifies adoption; the [iteration](../revisions/001/03-spacing-kerning.md#proposed-optical-pair-spacing-experiment)
records assessment. This note separates primary mechanisms from the raster adaptation.

## Published foundations

[Hersch et al. 1995, pp. 85–88, Figures 18–22](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf#page=9)
transforms exterior whitespace, limits concavity slopes and depths, and compares integrated space with designed
reference pairs. Its six stem/curve standards are an additional specialized path. Mixed-case ideal areas and heights are
averaged separately. Clearance and integer placement follow the geometric solve.

[Hu 1998, §4.4, pp. 88–91](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf#page=94) describes bitmap walls,
opposite-edge substitution for empty scanlines, ±45° filtering and inter-wall integration. Neither this section nor the
1995 paper publishes complete arbitrary-font implementation code.

[Hersch and Betrisey, US5768490A, preferred embodiment, transformations A–D](https://patents.google.com/patent/US5768490A/en)
provides additional detail omitted from the earlier audit:

- B limits concave contour portions; extending a global unit-slope envelope over convex exterior portions is different.
- C uses the vertical aperture between two outward maxima. Its cutoff is measured inward from the more exterior lip,
  rather than from each point of a sloping mouth chord. An inset second lip receives a connector from the cutoff's
  departure point.
- Published relative-depth and global height factors are **0.21** and **0.25** respectively.

These details supersede the earlier conclusion that obtaining numerical factors required a new optimizer. The patent
also supplies a generic transformed-wall reference construction without requiring the six-class shortcut. Its rounding
method is separate from the experiment's retained signed whole-pixel adjustment rounding.

## Raster adaptation

The candidate measures unchanged full binary pixel cells on a uniform physical midpoint grid. Tight nonzero delivered
bounds determine `n`/`H` body windows. Empty rows use opposite bounding edges. This window policy is an explicit
adaptation, not a recovered author implementation. Source outlines do not replace the delivered cells in fitting or
measurement.

Local raster wall recesses supply bounded cavity domains. Their geometry determines aperture and lip positions; no
letter names, serif-size thresholds or fitted depth coefficients select them. Concavity filtering, aperture cutoff and
global depth remain distinct operations. The executable implementation and analytic tests disclose the finite-cell
interpretation, including asymmetric lips. The bounded slope filter omits one-sided monotone concave arcs and tangent
intersections outside the local bay. Raster stairs and clipped body windows remain limitations; mechanical agreement
with those tests does not establish parity with unavailable author code.

Density calibration uses delivered reference cells at finalized advances plus full maintained metric pair adjustments.
Every eligible candidate and its reference use the same transformed-wall integral. Lowercase uses `nn`, uppercase `HH`;
mixed areas and heights are averaged separately. There is no branch from generic area to classified vertical extrema.
ASCII `00` remains an experimental numeral anchor. Missing reference geometry and unsupported categories abstain
explicitly. Calibration is independent of runtime kerning strength and of the supplied sample text.

The fixed coefficients eliminate the earlier moving-target coefficient fit, not font calibration itself: each font's
reference geometry and designed placement still determine its density. The original raster-calibration preference is
preserved. Earlier source-derived pilot targets remain diagnostic evidence rather than a silent default change.

## Source-designed shared density comparison

`hu_source_calibrated` measures the ideal `nn`/`HH` space on continuous source outlines at full source metrics, then
solves against delivered cells. It keeps the shared-target objective. The designed-reference principle is published;
this source/delivered split, common raster-derived window and sampled wall construction are project adaptations. The
[owning design](../designs/text-layout/contextual-spacing-and-healing.md#source-designed-shared-density-candidate)
defines the equation, provenance and abstention policy. Reference representativeness, integer placement and clearance
remain assessment limits; a source reference does not promise the source corpus's mean density.

## Source-relative compensation comparison

The separate `hu_source_relative` mode uses the same filtered-wall measurement on source curves and delivered cells, but
preserves each pair's source value rather than assigning the generic reference area. This combines the existing
source-preserving experiment with Hu/Hersch measurement; it is not the patent's shared ideal-space rule. The
[design](../designs/text-layout/contextual-spacing-and-healing.md#source-relative-hu-comparison) owns its placement
formula and controls.

Source advance and pair adjustment describe the font's intended placement, distinct from contour bounds:
[OpenType horizontal metrics](https://learn.microsoft.com/en-us/typography/opentype/spec/hmtx) and
[pair positioning](https://learn.microsoft.com/en-us/typography/opentype/spec/gpos#lookuptype-2-pair-adjustment-positioning-subtable)
provide the foundations. The capture supplies those values at the selected axes. Continuous source curves are evaluated
on the same physical sampling grid as the delivered walls, without creating another bitmap. Both paths call the same
depth-filter transformation; source sample-based cavity extraction remains an explicit approximation. Sampling
convergence must be checked on continuous steps and emitted placements separately.

Reference glyphs supply only body windows in this mode. The source-kerning control affects its pair target, including at
full compensation strength. A finite signed source separation is meaningful even when the source pair overlaps in
projection; the delivered clearance policy remains a separate constraint. Diagnostics must distinguish a matched source
relationship from residuals introduced by rounding, strict raster clearance or deliberate tracking. Preserving the
source relationships cannot repair uneven spacing already present in the source font.

## Superseded adaptations and evidence

The first candidate used a global unit-slope envelope, convex-hull mouth chords and a deterministic fit against `cu`,
`ov`, `vu`. Its Literata aperture coefficient reached zero. The hull could label a monotone stepped shoulder as a
cavity, and its parallel-chord cutoff differed from transformation C. Specialized curve/stem placement introduced a
second measurement convention. The five-pair investigation separates those mechanisms from rounding and clearance.

The correction adopts primary-source constructions and published coefficients; it does not optimize the reported pairs.
Earlier captures, preview and failed fixed-target/source-calibration probes remain under
`out/diagnostics/contextual-spacing/hu-consistent-calibration/` and `hu-five-pair-investigation/`. Their numerical
results describe those superseded policies, not the current algorithm.

## Assessment boundary

Analytic cavities, convex walls, translation/padding invariance, symmetric and asymmetric lips, sampling convergence,
reference identity and disabled metric identity verify bounded mechanics. Native-size assessment must still cover
reported failures, held-out words, other families and neighboring sizes. Equal transformed area does not establish equal
perceived spacing. Keep clearance-limited residuals and unresolved optical findings visible, and retain the old
filtered-wall, CounterSpace and metric controls. Glyph production and the approved renderer baseline remain unchanged.
