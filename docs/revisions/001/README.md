# Revision 001

Starting point: pinned upstream Skrifa 0.46.2 reference rendering, with optional custom fitting developed alongside it.
Revisions can contain several problems; each iteration is dedicated to a specific problem identified by user feedback.
See the [iteration lifecycle guidance](../README.md#iteration-lifecycle).

## Iterations

- [001.01 — diagonal weight](01-diagonal-weight.md): open. Straight-border constraints for 1-bit fitting, including the
  original Roboto 14/16 px corrections, source-relative width tweak, terminal-curve correction for Literata y, and
  short/curved coverage for x/Q. Literata Q/x/y coverage is implemented and awaits optical assessment. Roboto 18 v/w
  weight/size transitions and three broader topology changes remain pending assessment. These observations are not
  confirmed defects merely because their ink/component counts differ. See the
  [current finding classification](01-diagonal-weight.md#current-finding-classification).

The web index shows `reference → 001.01` at the agreed 14/16/18/20 px sizes. Both the original corrections and the
reported excessive-thinning investigation belong to the same open iteration. The iteration closes only when user and
agent explicitly agree that no further actions remain for its problem.

## Validation

[Evaluation rules](../../evaluation.md) require model-first assessment and separate hard invariants from quality
signals. Pixel additions/removals alone establish neither improvement nor regression. The Rust evaluator reports
diagnostics without an optical score.

The tests cover reported border thickness, terminal-curve dependencies and protected junctions, preservation of original
Roboto 14/16 px fixes, source contrast, layout/grayscale equality, determinism, disabled parity, and no additional join
failures compared with historical captures within 001.01. Broader diagnostic sizes remain outside the normal preview.
These checks establish implementation and publication behavior, not optical acceptance or iteration closure.
