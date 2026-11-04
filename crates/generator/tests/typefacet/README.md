# TypeFacet independent reference fixture

<!-- cspell:words typefacet Autokern -->

`literata.json` retains binary cells and 89 parameter settings with all 676 lowercase pair origins from the unchanged
TypeFacet Python 2 predicates, via the integer adapter. Its provenance records the pinned revision and source artifact
SHA-256 hashes. Runtime code does not read this fixture or import experiments.

Source artifacts: `out/diagnostics/contextual-spacing/typefacet-integer/fit-02/` (`all-settings.json`,
`original-full/capture.json`, `protocol.json`) and the frozen capture identified by the protocol. Extract glyph
bitmap/identity/finalized advance fields from that capture; extract parameter pairs and ordered `step_px` arrays from
all settings. The retained original profiles include raw, zero-radius and maximum-radius profiles at the selected
setting.

`numerical_profiles` additionally captures the original full process at normal distance .0625 em, zero intrusion, on
glyph `a`, using the same reference and `typefacet_capture.py`. Its retained artifact lives under
`out/diagnostics/contextual-spacing/typefacet-port-numerical-oracle/a-0625/`. This setting exercises the original's
one-decimal inflation rounding, which `Autokern.py:103-104` overrides from the helper library's default precision.

Tests require exact pair-origin agreement for every retained setting and exact missing-row agreement for profiles.
Numeric profile comparisons allow 1e-10 font units for floating arithmetic evaluation; selected pixel origins permit no
tolerance. This is mechanical evidence, not optical acceptance.

Upstream attribution and license are in `../../src/kerning/typefacet/NOTICE.txt` and `LICENSE-APACHE-2.0.txt` beside it.

`literata-geometry.json` retains the original full-process request's closed font-unit contours and metrics, with its
request SHA-256, for the method-only profile/predicate checks. The composed geometry-adapter/placement checks continue
to use `literata.json`; the method has no bitmap or placement dependency.

`curves.json` captures the unchanged original full process on line, quadratic and cubic fixtures, opposite contour
directions and a repeated cubic endpoint control. Its independently captured full/ascender predicates cover 64 ordered
pairs at font-unit origins, including fractional positions around contact and original selected advances. Glyph
identities include Greek scalars. Request, capture, predicate-driver and predicate-output hashes are retained.

Reproduction artifacts are in `out/diagnostics/contextual-spacing/typefacet-port-curve-oracle/`:
`curves-supported.json`, `curves-supported/capture.json`, `capture-predicates.py` and `curve-predicates.json`. The
original reference also fails on a collinear quadratic with parallel endpoint tangents; `curves.log` retains that
failure. The method reports this unsupported case explicitly.
