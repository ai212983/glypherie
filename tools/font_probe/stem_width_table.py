"""Shared stem-width table: our Control Value Table analogue.

Microsoft standardizes each design stem width once per size (one CVT
entry shared by every stem of that design width) instead of rounding
per glyph. This module does the same per face: stem feature widths
(font units) are clustered across the face's glyphs, and each cluster
receives ONE integer pixel target at the requested size.

Cluster target selection: unanimous clusters (every member rounds to
the same integer) keep it. Straddling clusters (members fall on both
sides of a rounding boundary, e.g. Roboto 190u/1.484px vs 193u/1.508px
at 16ppem) snap outward to ``ceil(mean)``: a shared class never renders
thinner than its boundary case, which matches native mono rendering on
the calibrated faces and protects small-size legibility. Every choice
records its reason for the conformance record.

Application is gated by a cut-in (Microsoft ``CUTIN`` analogue): the
shared target applies only when the glyph's own source width is within
``CUT_IN_PX`` of it; otherwise the glyph keeps its own rounded width.
Tables are plain JSON-safe data.

Which equations may take a stem target is decided by the caller: the
joint solver withholds full-height extents and curved arc heights
(see ``joint_stroke_fit._withholds_table``), with cap-band full spans
redirected to the cap anchor below. All other widths match purely by
value, preserving the legacy behavior the repertoire was built
against.

Extent anchors: cap heights standardize like stem widths, but across
glyphs rather than within them. ``vote_cap_anchor`` clusters whole
glyph y-maxima in a tight band around the plurality mode (caps, not
ascenders) and votes one integer pixel target per size with the same
unanimous/straddling rule: Roboto maxima {1456u x123, 1476u x35,
1477u x17} vote {14px: 10, 16px: 12, 18px: 13, 20px: 14}, matching the
native cap grid, where no scalar rounding rule fits all four sizes.
"""

CUT_IN_PX = 1.0
CLUSTER_TOL = 0.20
# Cap-band half-width around the y-maximum mode: overshoot-scale
# differences stay in (Roboto 1476u at 1.4%), ascender gaps stay out
# (Roboto 1536u at 5.5%, shoulders further). Margins verified per
# face in the 14/16/18/20px native grid.
CAP_BAND_TOL = 0.025


def _round_half_up(value):
    import math
    return int(math.floor(value + 0.5))


def build_cap_table(cap_vote, asc_vote=None, ppem=None, em=None):
    """Cap-height CVT: shared extent entries on the spec pattern.

    Spec Fig 1-12 (vendored ``truetype-fundamentals-otspec184.md``)
    stores font-wide heights — flat/round base, x-height,
    flat/round cap, ascenders — as numbered CVT entries consumed
    indirectly with cut-in gating. This table is that shape for
    the heights records actually evidence: the voted cap line,
    plus a voted ascender line when a taller maxima cluster
    exists. Every entry carries the voted per-size integer.
    Round variants are deliberately omitted: measured
    overshoots (8-20u across faces) sit inside the entry
    bands with identical integers, so round entries could
    only overfire at band edges (ss3-18 `°` took a round-only
    redirect both witnesses reject) and never add value —
    structural convergence at these sizes, re-split if an
    overshoot ever exceeds its band or targets diverge.
    x-height, numbers, and baseline entries are omitted: no
    bespoke treatment exists for those rows today, so there
    is nothing to replace (documented extension point — the
    entry list is additive). Returns None when there is no
    cap vote.
    """
    if not cap_vote:
        return None
    try:
        mode = float(cap_vote['mode_units'])
        target = int(cap_vote['target_px'])
    except (TypeError, ValueError, KeyError):
        return None
    if mode == 0:
        return None
    entries = [
        {'name': 'flat_cap', 'design_units': mode,
         'target_px': target,
         'reason': str(cap_vote.get('reason', '')),
         'members': int(cap_vote.get('members', 0) or 0)},
    ]
    if asc_vote:
        try:
            amode = float(asc_vote['mode_units'])
            atarget = int(asc_vote['target_px'])
        except (TypeError, ValueError, KeyError):
            amode, atarget = 0.0, 0
        if amode > mode:
            entries.append(
                {'name': 'flat_ascender', 'design_units': amode,
                 'target_px': atarget,
                 'reason': str(asc_vote.get('reason', '')),
                 'members': int(asc_vote.get('members', 0) or 0)})
    return {'ppem': ppem, 'em': em, 'band_rel': CAP_BAND_TOL,
            'entries': entries}


def cluster_widths(entries):
    """Group ``(char, feature, width_units)`` entries by design width.

    Greedy pass over widths sorted ascending; an entry joins the open
    cluster while within ``CLUSTER_TOL`` relative of the cluster mean,
    else opens a new cluster. Returns a list of clusters (lists).
    """
    clusters = []
    for entry in sorted(entries, key=lambda e: e[2]):
        placed = False
        for cluster in clusters:
            mean = sum(e[2] for e in cluster) / len(cluster)
            if abs(entry[2] - mean) / mean <= CLUSTER_TOL:
                cluster.append(entry)
                placed = True
                break
        if not placed:
            clusters.append([entry])
    return clusters


def build_table(records, ppem, em):
    """One shared table for a face at ``ppem`` from its glyph records.

    ``records`` maps char to record dicts with ``features`` (stem kinds
    carry ``width`` in font units). Returns a JSON-safe dict with one
    entry per cluster: design mean, members, integer target and reason.
    """
    entries = []
    for char, record in records.items():
        for index, feature in enumerate(record.get('features', ())):
            if feature.get('kind') == 'stem':
                entries.append((char, index, float(feature['width'])))
    table = {'ppem': ppem, 'em': em, 'cut_in_px': CUT_IN_PX,
             'clusters': []}
    for cluster in cluster_widths(entries):
        mean_units = sum(e[2] for e in cluster) / len(cluster)
        mean_px = mean_units * ppem / em
        votes = [_round_half_up(e[2] * ppem / em) for e in cluster]
        if len(set(votes)) == 1:
            target, reason = votes[0], 'unanimous rounding'
        else:
            import math
            target = int(math.ceil(mean_px))
            reason = ('straddling class: members round to %s; '
                      'snapped outward to preserve ink' % sorted(set(votes)))
        table['clusters'].append({
            'design_mean_units': mean_units,
            'members': [{'char': c, 'feature': i, 'width_units': w}
                        for c, i, w in cluster],
            'target_px': target,
            'reason': reason,
        })
    return table


def vote_cap_anchor(maxima, ppem, em):
    """One integer cap target per size from whole-glyph y-maxima.

    ``maxima`` maps design y-maximum (font units) to glyph count.
    Takes the plurality mode (the cap line, not ascenders), keeps
    members within ``CAP_BAND_TOL`` of it, and votes with the same
    unanimous/straddling rule as stem clusters. Returns a JSON-safe
    ``{'mode_units', 'target_px', 'reason'}`` dict, or None when there
    is nothing to vote on. Deterministic: mode ties break toward the
    lower height.
    """
    import math
    counts = {float(v): int(n) for v, n in dict(maxima).items()
              if math.isfinite(float(v)) and int(n) > 0}
    if not counts:
        return None
    mode = sorted(counts, key=lambda v: (-counts[v], v))[0]
    members = {v: n for v, n in counts.items()
               if abs(v - mode) / abs(mode) <= CAP_BAND_TOL} if mode != 0 \
        else {v: n for v, n in counts.items() if abs(v - mode) <= 1.0}
    votes = []
    for value, count in members.items():
        votes.extend([_round_half_up(value * ppem / em)] * count)
    if len(set(votes)) == 1:
        target, reason = votes[0], 'unanimous rounding'
    else:
        mean_px = (sum(v * n for v, n in members.items())
                   / sum(members.values()) * ppem / em)
        target = int(math.ceil(mean_px))
        reason = ('straddling cap class: members round to %s; '
                  'snapped outward to preserve ink' % sorted(set(votes)))
    return {'mode_units': mode, 'target_px': target, 'reason': reason,
            'members': sum(members.values())}


def main_stem_target(table, minimum_members=10):
    """Smallest target among well-populated stem clusters.

    Curved bands join the face's main stem weight, never a thin
    detail class and never below it: the minimum target over
    clusters with at least ``minimum_members`` members. Falls back
    to the minimum over all clusters when none qualifies, and to
    None for an empty table.
    """
    clusters = (table or {}).get('clusters', ())
    big = [c for c in clusters if len(c.get('members', ())) >= minimum_members]
    pool = big or list(clusters)
    if not pool:
        return None
    return min(c['target_px'] for c in pool)


def class_of(table, width_units):
    """Nearest cluster whose design band contains ``width_units``.

    Returns None when no cluster matches. Raises on a missing table.
    """
    if table is None:
        raise ValueError('width table required')
    best = None
    for cluster in table['clusters']:
        mean = cluster['design_mean_units']
        if abs(width_units - mean) / mean <= CLUSTER_TOL:
            if best is None or abs(width_units - mean) < abs(
                    width_units - best['design_mean_units']):
                best = cluster
    return best


def rejoin_main(table, width_units, role):
    """Main-stem target for an anchored sub-main width, else None.

    Link-layer decision on the source architecture (spec MIRP
    per-instruction flags; VTT ``Link(parent, child, cvt,
    minDist)`` in TTGenerator.cpp:82): the shared table stays
    geometry-free (see ``lookup``), while the per-link choice —
    which value this width takes — consumes the caller-supplied
    role. An ``anchored`` (``stem_roles``) width within cut-in
    of the face main takes the main; every other role (or a
    main further than cut-in) leaves the shared target alone
    by returning None. ``lookup`` results pass through
    unchanged; callers substitute the main only on non-None.
    """
    from stem_roles import ANCHORED
    if role != ANCHORED:
        return None
    main = main_stem_target(table)
    if main is None:
        return None
    ppem, em = table['ppem'], table['em']
    own_px = float(width_units) * ppem / em
    if abs(own_px - main) <= table.get('cut_in_px', CUT_IN_PX):
        return main
    return None


def lookup(table, width_units):
    """Shared integer target for a design width, with cut-in gating.

    Targets are size-specific, so the table's own ppem/em apply.
    Returns the cluster target when the source width is within the
    cut-in of it; otherwise the glyph's own rounded width. Widths
    matching no cluster also fall back to their own rounding,
    preserving previous behavior.

    Deliberately no single-width floor here: a floor rejoining
    every sub-main width to the face main was tried and rejected
    by oracle adjudication (77 both-witness deltas against, incl.
    literata O/Q/e/u and plus-sign arms the foundry keeps thin,
    vs 17 for). The foundry draws its thin/thick line per glyph,
    which no font-wide width rule reproduces; role-aware
    rejoins belong at the link layer (see ``rejoin_main``),
    not in this choke point.
    """
    best = class_of(table, width_units)
    ppem, em = table['ppem'], table['em']
    own_px = width_units * ppem / em
    if best is None:
        return _round_half_up(own_px)
    target = best['target_px']
    if abs(own_px - target) <= table.get('cut_in_px', CUT_IN_PX):
        return target
    return _round_half_up(own_px)
