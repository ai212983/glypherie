<!-- cspell:words AutoKern Hersch Hu unicodedata titlecase maxx -->

# Optical pair-spacing target

Research for placing unchanged glyph forms. The
[design](../designs/text-layout/contextual-spacing-and-healing.md#optical-spacing-experiment) owns the selected model;
[iteration 001.03](../revisions/001/03-spacing-kerning.md#proposed-optical-pair-spacing-experiment) owns assessment.
Texture healing is deferred. This note describes the retained FontForge calibration comparison; the
[filtered-wall audit](filtered-wall-spacing.md) covers the current candidate measurement.

## Published foundations

[FontForge's documentation](https://fontforge.org/docs/ui/dialogs/autowidth.html) describes a linear separation model:
combine facing-envelope space measured at adjacent bounding boxes with the actual bounding-box gap, then solve toward a
requested separation. The
[pinned implementation](https://github.com/fontforge/fontforge/blob/c41bdb922285f35defd1e1385adfd13bde1ab32a/fontforge/autowidth2.c)
uses inverse-square weights, rounding the weighted distance in design units. Its `0.15 em` fallback is a default when
lookup/font separation is absent, rather than a typeface-specific density calibration. The experiment independently
checks the estimator's source-operation semantics.

[Hersch et al., 1995](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf), pp. 85–88, derives ideal optical
space from designed reference pairs, including lowercase `nn` and uppercase `HH`, and uses a mean ideal for mixed case.
It transforms measurement contours to limit cavity contributions, distinguishes six stem/curve combinations and
normalizes visual-space quantities by character height. Its collision and rounding policies also differ from ours.

[Hu, 1998](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf), §4.4, pp. 88–91, instead filters bitmap walls
before measuring visual area and converts an area deficit to a positioning distance. This technique can measure
unchanged delivered glyphs; it does not require texture healing.

Neither source establishes that equal values under FontForge's simpler estimator imply equal perceived whitespace.
Applying the reference-pair principle to this estimator is a project adaptation.

## FontForge calibration comparison

Use the font's continuous source outlines and maintained source advances/full pair kerning at the requested size and
axes. For a repeated reference glyph `g`:

```text
T(g) = source_advance_px(g) + source_pair_adjustment_px(g,g)
       + (source_minx(g) - source_maxx(g) + source_adjacent_separation(g,g)) * size_px / em
```

Source advances and pair adjustments are already in pixels, quantized to the maintained nearest-1/64-pixel policy; only
the design-unit geometry term is scaled. The reference pair always uses full source kerning, independently of the
runtime kerning slider. Targets do not depend on the current text, produced raster, request order or cache history.

FontForge returns a linear distance. It therefore needs no area-to-distance height division. Normalizing a distance by
height and later restoring a height factor would be dimensionally possible, but would define another target policy. The
selected mixed-case target is the arithmetic mean of two linear targets. This adapts Hersch's reference principle; it
does not reproduce the paper's area/height normalization or six shape classes. Those remain possible refinements.

| Pair class                                | Reference and target                           |
| ----------------------------------------- | ---------------------------------------------- |
| Latin lowercase + lowercase               | Source `nn`                                    |
| Latin uppercase + uppercase               | Source `HH`                                    |
| Latin uppercase + lowercase, either order | Arithmetic mean of the `nn` and `HH` targets   |
| ASCII numeral + numeral                   | Source `00`, an experimental numeral extension |

The numeral reference extends the same designed-reference principle to retain optical numeric comparisons. It is not a
published prescription from Hersch or Hu, nor a claim that `00` is optimal for every figure style. Assess numeric rhythm
and tabular alignment separately. No pair-specific adjustment for `12`, `23` or `re` enters the solver.

Eligibility uses Unicode General Category `Ll`/`Lu` plus names beginning `LATIN `, and the ASCII digit range. Python's
[Unicode data API](https://docs.python.org/3/library/unicodedata.html) supplies names/categories; its data version is
recorded. The naming filter is a conservative experiment boundary, not a complete Unicode Script classifier. Titlecase,
non-Latin letters, punctuation, symbols and mixed numeral/letter pairs retain metric placement with an explicit
unsupported-class reason. They require their own supported calibration policy before expansion.

## Coverage, fallback and provenance

Capture auxiliary source-only reference records separately from the requested output glyph repertoire. Missing
references remain individually unavailable; they do not fail an otherwise valid capture or enlarge the full pair domain.
Older captures can use matching source glyphs and pair data already present in their repertoire, with that origin
recorded. Calibration measurements do not alter glyph forms, bitmap offsets or finalized advances.

An absent or unusable reference, including a target at or below zero, leaves its dependent classes unavailable. Missing
`n` need not prevent an available uppercase or numeral class from working. The solver retains metric placement and
records the reason; there is no silent fixed-target or per-pair source fallback. Non-finite input is an error. Existing
fixed-pitch, requested tabular, empty-geometry, no-shared-band and disabled-optical protections remain independent.

The default model becomes font-calibrated. Source-relative placement retains each pair's own source relationship as a
comparison. The former `0.15 em` model remains an explicitly labelled fixed-target diagnostic with configured-target
provenance. Controls, reference identities, class targets, Unicode version, coordinate policy, estimator settings and
implementation identity accompany results.

## Limits and verification

The Literata 16 px/400 default-axis `re` report motivates separating overall density from estimator/rounding
sensitivity. Its former fixed target is above its source reference density; that observation does not establish a
universal ranking between methods. Calibrated targets can still misrepresent cavities or overhangs, and binary
boundaries can change a whole-pixel rounding decision. Filtering measurement walls remains a separate research question.

Verify target derivation, units, mixed/reference selection, numeral coverage, independent missing references, input
immutability, full-strength kerning independence, metric-disabled identity, reference capture outside the output
repertoire, preview/full agreement and cache determinism. At full optical strength, solved pairs should meet their
selected estimated target within half a pixel before deliberate spacing. Corpus positivity is an observation rather than
a requirement that every font's references be usable or that uppercase targets exceed lowercase targets.

Broader size/axis coverage and native-size optical assessment remain open. Tests establish mechanical relationships;
they do not establish perceived balance or adoption into production layout.
