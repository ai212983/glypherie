<!-- cspell:words Hersch Hu -->

# Fixed-alphabet spacing density

The [owning design](../designs/text-layout/contextual-spacing-and-healing.md#fixed-alphabet-density-experiment) defines
the experiment. It tests overall density separately from relative pair balance, following the density audit and the
failed provisional stem/curve classification gate. It does not claim optical acceptance or a new published Hu formula.

## Foundation and project constraint

[Hu 1998, section 4.4](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf#page=94) and
[Hersch and Betrisey, US5768490A](https://patents.google.com/patent/US5768490A/en) ground the shape-dependent wall
measurement and shared ideal-space solve. Their generic reference rule does not ensure conservation of a designed font's
mean origin spacing. The papers' intelligent/adaptive rounding is also separate from the experiment's retained rounding
policy; it is not evidence that this new normalization is an author-prescribed method.

[OpenType horizontal metrics](https://learn.microsoft.com/en-us/typography/opentype/spec/hmtx) distinguish advance
widths from ink bounds. Source advances and pair adjustments therefore provide a meaningful independent layout
reference. The captured values reflect the selected variation axes, with nearest-1/64 px metric precision.
[Turner and Lemberg's metric fitting](papers/2003-turner-lemberg/paper.md) adjusts advances in response to fitted edges;
it does not prescribe conserving an alphabet mean. The latter is the explicit project constraint evaluated here.

## Two controlled calibrations

Let `d_source` be the designed pair step and `c_geometry` the mean wall intercept, so a pair at step `d` measures `d +
c_geometry`. Over a declared complete alphabet pair set:

```text
source-alphabet arm: T = mean(d_source + c_source)
source-origin arm:   T = mean(d_source + c_candidate)
both arms:          d_ideal(pair) = T - c_candidate(pair)
```

The second arm has mean `d_ideal = mean(d_source)` by linearity on exactly that calibration set. On source geometry,
both arms coincide. On delivered geometry the first arm retains the source-to-delivered wall response, while the second
removes its effect on the calibration-domain average origin step. Both retain the same relative generic wall balancing.

The uniform weighting is over fixed ASCII repertoires, not supplied preview text or whichever letters happen to be
captured. A missing required glyph makes the class unavailable. Mixed-case calibration must state both ordered products
and its common physical window. Numeral calibration is experimental and does not override tabular/fixed-pitch
safeguards.

## Necessary limits and controls

- The identity applies before pixel rounding and clearance. Their residuals, and a source-width budget below minimum
  permitted placement under the retained conservative bitmap guard, must be exposed rather than hidden with another
  target offset. This does not establish impossibility under every interlocking or clearance policy.
- A uniform alphabet average does not conserve each word or an arbitrary language-frequency distribution. Held-out text
  is evaluated without entering calibration.
- Equal modeled gaps do not prove equal perception. A globally narrower result can still have poor relative pair rhythm.
- Bitmap cells are the delivered geometry. Fitted-outline measurement is an orthogonal diagnostic using retained
  pixel-coordinate commands; actual bitmap clearance is enforced in either measurement control.
- Source geometry supplies a mathematical identity control. Old single-reference and source-relative results supply
  distinct spacing controls. The normal browser reference retains its own vanilla shaping and spacing.

The initial experiment keeps published wall coefficients, source metrics, glyphs, the signed adjustment rounding rule
and the strict no-touch guard unchanged. It adds no learned classifier, glyph exceptions, corpus-fit offset or default
tracking. Any later rounding or constraint-aware normalization would be a separate intervention requiring its own basis
and verification.
