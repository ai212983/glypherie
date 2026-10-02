# Revision 001

Starting point: pinned upstream Skrifa 0.46.2 reference rendering, with optional custom fitting developed alongside it.
Revisions can contain several problems; each iteration is dedicated to a specific problem identified by user feedback.
See the [iteration lifecycle guidance](../README.md#iteration-lifecycle).

## Iterations

- [001.01 — diagonal weight](01-diagonal-weight.md): closed and accepted for production on 2026-10-02. Straight, curved
  and mixed diagonal fitting includes coherent terminal preparation and source-relative thickness. The user accepted all
  current published quality, including the six remaining Attention cases. No further correction is required in this
  iteration. Broader diagnostic observations that have not been reviewed remain documented for future investigation;
  they are not demonstrated contract failures or blockers to this promotion.

The web index retains `reference → 001.01` at the agreed 14/16/18/20 px sizes. Production automatic 1-bit generation
uses this accepted model; the upstream renderer remains the independent reference. See the
[acceptance record](01-diagonal-weight.md#acceptance-and-production-promotion-2026-10-02).

## Validation

[Evaluation rules](../../evaluation.md) require model-first assessment and separate hard invariants from quality
signals. Pixel additions/removals alone establish neither improvement nor regression. The Rust evaluator reports
diagnostics without an optical score.

The tests cover reported border thickness, terminal-curve dependencies and protected junctions, preservation of original
Roboto 14/16 px fixes, source contrast, layout/grayscale equality, determinism, disabled parity, and no additional join
failures compared with historical captures within 001.01. Broader diagnostic sizes remain outside the normal preview.
Mechanical checks establish implementation and publication behavior. Optical acceptance and closure are recorded
separately from the user's explicit decision on 2026-10-02.
