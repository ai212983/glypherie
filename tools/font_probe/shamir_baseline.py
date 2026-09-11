"""Reproducible decisions for the researched Shamir baseline profile.

These identify conservative completions as assumptions, separate from the tuned
experimental profile. Source/search evidence belongs to the conformance document.
"""
from copy import deepcopy

DECISIONS = {
    'B01': ('specified + conservative assumption', 'Static quadratic outlines; exact redundant-line removal and extrema insertion; Skia nonzero boundary normalization preserves metrics. Full 1997 preparation algorithm unavailable.'),
    'B02': ('specified + conservative assumption', '1996 epsilon features with 0.003em distance, 0.04rad angle, 0.012em curved alignment; both-side epsilon bounding-box cardinal classification and analytic interior checks; straight runs use actual constituent lines; quadratic run chords remain conservative. Cardinal feature statistics and constraints use projected widths; numeric tolerances are explicit assumptions.'),
    'B03': ('conservative assumption', 'Typed flat/round height and feature-width statistics; Exact font-unit occurrence counts, six-occurrence threshold taken from the published example as an explicit setting; 0.01em nearest-value association. Phantom peaks can link to same-polarity flat/round heights independently of voting. Repertoire dependence and matching settings remain assumptions.'),
    'B04': ('specified + conservative assumption', 'Three or more equal strokes and gaps with epsilon length equality; no twice-width length cutoff. Triple windows represent longer ladders; adjacent pairs are deduplicated before statistics.'),
    'B05': ('specified + conservative assumption', 'Published 1996 sequence/reset recognizers; minimal local original-geometry recipes. No tuned taper recipe or ownership suppression. Library coverage is limited to published examples.'),
    'B06': ('specified + conservative assumption', 'On-curve representatives and attached controls; lowest on-curve index selection; one identity per extracted physical side with its own normal; additional shared side grouping within 1e-12 normal-dot tolerance, one-font-unit tangent/control membership after coordinate rounding; one dominant relation per segment by published priorities precedes representative resolution and member completion.'),
    'B07': ('specified + conservative assumption', 'Projected Abs/Dist/Ratio and parameter variants; explicit signed distances and finite coefficients, geometry-derived when absent; half-away nearest-pixel rounding for rounded relations.'),
    'B08': ('conservative assumption', 'Contour-neighbour representative references and perpendicular free-coordinate completion. Ratio permits extrapolation; single/equal-projection references preserve offsets with unrounded Dist; absent references retain original Abs. Reference selection borrows TrueType contour order, not the full IUP algorithm.'),
    'B09': ('specified + conservative assumption', 'Font parameters before metrics before Dist/Ratio before Abs; deterministic declaration ties with warnings. Exact horizontal baseline membership links retain character-metric priority when endpoints share segment roles.'),
    'B10': ('specified + conservative assumption', 'Select mathematically independent directions; numerical singularity and native range failures are explicit support failures, never a condition-four selection policy.'),
    'B11': ('specified + conservative assumption', 'Dominant segment relations precede the representative whole-point graph. Links targeting existing representatives enter that graph under ordinary priorities and cycle removal: explicit shared-role interpretation. Ordinary members attach later and retain point scheduling. Post-cycle original-position completion remains an assumption.'),
    'B12': ('experimental replacement', 'Size-specific native adapter solves projected point equations then emits cardinal SCFS coordinates. Explicit requested-size translation substitution for paper Table I MDAP/MIAP/MDRP/MIRP/IP; rationale target is bitmap at specified ppem with independent equation/native quantization checks; scalability/interpreter-state equivalence unestablished.'),
    'B13': ('specified + conservative assumption', 'Published priority conflict resolution; no recovered topology-repair rule. Local shape defects are recorded for baseline evaluation.'),
}


def baseline_decisions():
    return deepcopy(dict(version=5,profile='baseline',target='Shamir 2003 with 1996 extraction',
                         claim='researched implementation with explicit conservative assumptions; author-system equivalence unestablished',
                         decisions={key:dict(classification=value[0],implementation=value[1]) for key,value in DECISIONS.items()}))
