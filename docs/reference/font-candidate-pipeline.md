# Geometric font candidate boundary

The current experimental candidate uses one fixed correction sequence for every
requested outline: reorientation, complementary parent placement, half-serif
fitting, coordinated opposing-terminal fitting, then paired terminal fitting. This is an experimental interpretation,
separate from the paper baseline and the production font generator.

[geometric_candidate.py](../../tools/font_probe/geometric_candidate.py) owns the
sequence. Its `Geometry` input carries outline coordinates, contour ends, flags,
scale and constraint equations. It accepts no glyph name, character, codepoint,
font family, callback, correction overrides or per-stage repertoire. Equation
metadata is filtered at entry; only numeric segment/alignment provenance and the
required dependency-cycle marker survive. Geometry determines applicability.

[build_geometric_candidate.py](../../tools/font_probe/build_geometric_candidate.py)
owns identity, font I/O and the review repertoire. It invokes the same correction
entry point for every available record. Missing records and unsupported equations
are explicit outcomes. Numerical diagnostic failures are distinguished from
unsupported constructions. Candidate fonts contain only verified character
mappings; inherited programs never stand in for a failed candidate.
Review fonts omit inherited layout substitutions so shaping cannot select an
uncorrected alternate. They are single-outline review artifacts, not release fonts.

The adapter currently consumes frozen representative-experiment models. It does
not recover missing records or claim that all requested characters are supported.
The repertoire is printable ASCII without space, plus the degree sign. Every
available record receives the entire sequence; image focus may select examples
only after construction.

Run from the repository root, with an empty output directory:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/build_geometric_candidate.py
```

The report and gallery are in `tools/font_probe/out/geometric-candidate-v2/`.
Coordinate checks cover every exported candidate. Terminal checks additionally
verify equal extension lengths and preservation of unrelated points. Source and
input hashes bind the report to the build.

`tools/font_probe/check_geometric_integration.py` verifies all 880 supported cases
against the previous candidate or the reviewed coordinated-terminal experiment.
It checks exact native coordinates, pixels and unchanged coverage outcomes, and
creates `changes.html` plus `integration-check.json` in the output directory.
Opposing terminal spans that overlap another correction are explicitly unsupported.

Architecture tests in
[test_geometric_candidate.py](../../tools/font_probe/test_geometric_candidate.py)
check the identity-free interface, metadata filtering, fixed stage list and
restricted dependencies/I/O access. These guard against accidental architectural
regression; they are not a sandbox against deliberately concealed exceptions.
Changes to the stage boundary require corresponding tests and review.

Glyph-specific corrections remain a possible future design decision. Supporting
them would require an explicit architecture change with provenance, scope and
validation. The current correction interface provides no such facility.

Historical `compare_*` scripts preserve isolated experiment reproduction. Their
outputs must not serve as successive correction inputs for this candidate path.
