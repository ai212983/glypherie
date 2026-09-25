"""Experimental constrained least squares: hard metrics, soft stroke goals.

Source point and contour-edge displacement penalties each have weight 1;
each whole-side width/alignment residual has weight 4. These are explicit
experimental choices, not recovered Shamir or Microsoft policies.
"""
import re as _re

import numpy as np
from cross_section_widths import section, system
from shamir_baseline_solver import (_extent_sense, _is_y_extent, _round_pixel,
                                    evaluate_baseline)


def mirror_phase_ok(axis, pairs, p, record):
    """Grid-phase invariant for a mirror candidate axis.

    A mirrored pair whose source distance belongs to a shared width
    class must land on grid phase: ``2*axis - target`` even, so even
    targets get integer edges and odd targets half-integer edges.
    Pairs outside any class are unconstrained. Without a table every
    axis passes, preserving previous behavior. ``p`` and the table
    are both in font units.

    Provenance: project-invented gate, ledger WHY. Nearest source
    kin is VTT re-centering the median after asymmetric linking
    (TTEngine.cpp:1218), which repairs rather than gates — cited
    here as weak kin only, not a parent.
    """
    table = record.get('width_table')
    if table is None:
        return True
    from stem_width_table import class_of
    for pair in pairs:
        try:
            a, b = pair
        except (TypeError, ValueError):
            continue
        if not isinstance(a, (int, np.integer)) or not isinstance(
                b, (int, np.integer)):
            continue  # distributed curve weights, not point indices
        a, b = int(a), int(b)
        if not (0 <= a < len(p) and 0 <= b < len(p)):
            continue
        cluster = class_of(table, abs(float(p[a][0] - p[b][0])))
        if cluster is None:
            continue
        if abs(round(2 * axis - cluster['target_px'])
               - (2 * axis - cluster['target_px'])) > 1e-6:
            return False
        if (round(2 * axis - cluster['target_px']) % 2) != 0:
            return False
    return True


def _withholds_table(constraint, feature, yrange):
    """Whether a hard width equation keeps the solver value.

    Microsoft CVT entries standardize stem widths; two shapes never
    take a stem target even inside a cluster band by value. Vertical
    extents spanning the whole glyph height determine the raster
    extent itself (roboto H/I caps: the solver's outward rounding
    stands, unless the cap anchor below redirects them). Full-span
    arc extents keep the solver's protective rounding for the same
    reason; partial-span arc bands share the stem target like any
    other width (literata O/Q sides, roboto e/c apex bands): Shamir
    2003 section 3.5 converts arcs with the same Dist/PDist
    mechanism as stems, and section 5 requires width uniformity of
    stems and arcs. Everything else keeps legacy value matching:
    partial vertical bars and counters place interior edges
    cap-relatively (roboto T, literata B), pending zone-alignment
    research.

    Full-span detection is exact equality (relative 1e-6 dust
    tolerance). A 1px cut-in band was tried here
    (arch-probe-v22, 2026-09-15) and reverted: absolute-px
    bands are category-wrong on small glyphs (ss3-14 `-`
    thickness-vs-height mismatch is bearings-scale, and the
    band withheld it — REJECTED, both witnesses hold the
    1px hyphen), and no observed case needs absorption
    beyond dust. Any future band must be relative, motivated
    by an observed mis-shared span, and oracle-gated.
    """
    normal = constraint.get('normal', [])
    try:
        vertical = abs(float(normal[1])) >= abs(float(normal[0]))
        span = abs(float(constraint.get('value', 0)))
    except (TypeError, IndexError, ValueError):
        return (feature or {}).get('kind') == 'arc'
    if (feature or {}).get('kind') == 'arc':
        # Span, not direction, decides: a partial-span band (e apex
        # 151u of ~1000u height) shares; only a full-axis span keeps
        # protective rounding. Horizontal arc rows never span the
        # glyph width (width features are stroke thicknesses), so
        # they always share when in band.
        if not vertical:
            return False
        return bool(yrange and yrange > 0
                    and abs(span - yrange) <= 1e-6 * yrange)
    if (vertical and _is_y_extent(constraint)
            and yrange is not None and yrange > 0
            and abs(abs(float(constraint.get('value', 0))) - yrange)
            <= 1e-6 * yrange):
        return True
    return False


def _cap_endpoints_units(cs, constraint, design_points=None):
    """(source, point) design heights of an extent row, else (None, None).

    Mirrors the solver convention: the point sits one span above its
    source's Abs row (same normal, later rows winning like the
    solver's keyed lookup). Bound rows without an Abs source (e.g.
    roboto-14 '1' tip, sourced at an align row) fall back to the
    source outline coordinate when the caller passes it. Multi-source
    and reversed rows abstain.
    """
    if constraint['kind'] not in ('Dist', 'PDist'):
        return None, None
    if constraint.get('reversed'):
        return None, None
    sources = constraint.get('sources', [])
    if len(sources) != 1:
        return None, None
    normal = list(constraint.get('normal', []))
    axis = max(range(len(normal)), key=lambda a: abs(normal[a])) \
        if normal else 1
    design = None
    if design_points is not None:
        try:
            design = float(
                np.asarray(design_points, float)[sources[0]][axis])
        except (TypeError, ValueError, IndexError):
            design = None
    if design is None:
        for row in cs:
            if row['kind'] in ('Abs', 'PAbs') \
                    and row.get('point') == sources[0] \
                    and list(row.get('normal', [])) == normal:
                try:
                    design = float(row['value'])
                except (TypeError, ValueError):
                    return None, None
    if design is None:
        return None, None
    try:
        return design, design + float(constraint.get('value', 0))
    except (TypeError, ValueError):
        return None, None


def _cap_table_lookup(cap_table, design_value):
    """Nearest cap-table entry whose band contains a design height.

    One consumption path for every cap-height row (the CVT
    architecture: shared entries, per-row matching): returns
    the nearest entry within the table's relative band, else
    None. Ascender tops match ascender entries, cap tops cap
    entries — routing replaces the old whole-glyph
    eligibility stand-down. Near-cap non-cap tops (ss3 `t`
    at -18u) match nothing: zone identity is design-relative
    (overshoot-scale family), which absolute-px cut-in cannot
    express — see the ledger's cap-CVT entry.
    """
    from stem_width_table import CAP_BAND_TOL
    try:
        y = float(design_value)
    except (TypeError, ValueError):
        return None
    table = cap_table or {}
    try:
        band_rel = float(table.get('band_rel', CAP_BAND_TOL))
    except (TypeError, ValueError):
        band_rel = CAP_BAND_TOL
    best, best_dist = None, None
    for entry in table.get('entries', ()):
        try:
            design = float(entry['design_units'])
        except (TypeError, ValueError, KeyError):
            continue
        if design == 0:
            continue
        dist = abs(y - design)
        if dist <= band_rel * abs(design) and (
                best_dist is None or dist < best_dist):
            best, best_dist = entry, dist
    return best


def _cap_redirect(constraint, cs, cap_table, yrange, feature, scale,
                  design_points=None):
    """Cap-relative span placing a height-ladder point on its entry.

    Full-height ladder rows and curved ladder apex rows take a
    span of ``entry target - round(source)`` instead of the
    solver's outward rounding or any stem target, so the point
    lands on the voted per-size integer (roboto-14 '0' apex to
    10px, H-20 caps to 14px, '1' tip bound to 10px). Overshoot
    dots past the band keep natural rounding (roboto-20 'j'
    dot, via the contour-size guard in the Abs path).
    Partial vertical bars keep legacy value matching (their
    table values place interior edges cap-relatively already),
    and rows outside every band, without a table, or resolving
    below one pixel abstain. Returns (span, entry) or None;
    the caller pins the point on the entry target (VTT
    ResYAnchor attachment pattern).
    """
    if not cap_table:
        return None
    if constraint['kind'] not in ('Dist', 'PDist'):
        return None
    if _extent_sense(constraint) != 'max':
        return None
    kind = (feature or {}).get('kind')
    try:
        span = abs(float(constraint.get('value', 0)))
    except (TypeError, ValueError):
        return None
    fullspan = bool(yrange and yrange > 0
                    and abs(span - yrange) <= 1e-6 * yrange)
    if kind != 'arc' and not fullspan:
        return None
    source, point = _cap_endpoints_units(cs, constraint, design_points)
    if source is None or point is None:
        return None
    from stem_width_table import _round_half_up
    entry = _cap_table_lookup(cap_table, point)
    if entry is None:
        return None
    target = _round_half_up(source * scale) if scale else 0
    return float(entry['target_px']) - target, entry


def _cap_table_eligible(cap_table, design_points):
    """Whether a glyph takes any height-ladder treatment.

    Zone attachment at glyph level (the ``stem_roles`` pattern
    applied to whole tops): treatment applies when the glyph
    top attaches to a table entry band — cap crowns to cap
    entries, ascender tops to ascender entries. Glyphs
    floating between lines (brackets) or below them keep
    natural rounding everywhere. Without design points every
    table is eligible. Refines the old cap-only stand-down:
    dropping stand-down entirely was rejected on tall
    brackets (ss3-14 `(`/`)`, settled witnesses), while
    ascender treatment was approved (ss3-14 `f`, `l`).
    """
    if not cap_table:
        return False
    if design_points is None:
        return True
    arr = np.asarray(design_points, float)
    if arr.size == 0:
        return True
    return _cap_table_lookup(cap_table,
                             float(np.max(arr[:, 1]))) is not None


def _contour_range_units(design_points, ends, point):
    """Design y-range of a point's contour in outline units."""
    arr = np.asarray(design_points, float)
    start = 0
    try:
        for end in ends:
            if start <= point <= end:
                col = arr[start:end + 1, 1]
                return float(np.max(col) - np.min(col))
            start = end + 1
    except (TypeError, ValueError, IndexError):
        pass
    return None


def _cap_abs_redirect(constraint, cap_table, scale, design_points=None,
                      ends=None):
    """Entry integer for a ladder maximum Abs row, else None.

    Curved apexes and flat tops pinned by their own Abs equation
    (e.g. literata-20 'C' segment apex, H-20 bar tops) take the
    matched entry integer instead of the solver's outward
    ceiling; ascender tops route to ascender entries the same
    way. Band membership reads the source design, never a
    lifted equation value. Contours below cap-crown size
    (dots, tittles) keep natural rounding — carried over from
    the bespoke guard, same threshold — as does every other
    Abs row. Returns (target, entry) or None; the caller pins
    the point on the entry target.
    """
    if not cap_table:
        return None
    if constraint['kind'] not in ('Abs', 'PAbs'):
        return None
    if _extent_sense(constraint) != 'max':
        return None
    value = None
    if design_points is not None:
        try:
            value = float(
                np.asarray(design_points, float)[constraint['point']][1])
        except (TypeError, ValueError, IndexError):
            value = None
    if value is None:
        try:
            value = float(constraint.get('value', 0))
        except (TypeError, ValueError):
            return None
    entry = _cap_table_lookup(cap_table, value)
    if entry is None:
        return None
    if ends is not None and design_points is not None and scale:
        span = _contour_range_units(design_points, ends,
                                    constraint['point'])
        if span is not None and span * scale < _CAP_PULL_MIN_RANGE_PX:
            return None
    return float(entry['target_px']), entry


# Relative band above a glyph's own flat top inside which an arch apex
# counts as its overshoot (literata m/n arch 521u over stem-flat 507u
# is 2.76%; cap/ascender gaps stay out at 5.5%+, same scale argument
# as CAP_BAND_TOL). WHY-calibrated, oracle-gated; no source gives a
# number, only the collapse rule itself (GF VTT variable guide, MS
# VTT autohinting guide).
FLAT_TOP_BAND_REL = 0.03


def _flat_top_collapse(constraint, cs, scale):
    """Same-glyph flat-top integer for an overshoot Abs row, else None.

    VTT overshoot-inheritance shape in miniature: an arch apex
    overshooting the glyph's own flat top takes the flat's integer
    instead of the solver's outward ceiling — at these sizes the
    overshoot cannot show. No font-wide vote: the zone is the
    glyph's own flat, so round crowns without a flat (ss3-18 'o')
    and rows already standardized to table entries keep their
    values by construction. Returns the integer target, or None
    when there is no in-band flat, the flat is unrounded, or the
    collapse equals the natural ceiling (no-op).
    """
    import math
    if constraint.get('kind') not in ('Abs', 'PAbs'):
        return None
    if _extent_sense(constraint) != 'max':
        return None
    if constraint.get('width_standardized'):
        return None
    try:
        design = float(constraint.get('value', 0))
    except (TypeError, ValueError):
        return None
    flat = None
    for row in cs:
        if row.get('kind') not in ('Abs', 'PAbs'):
            continue
        if list(row.get('normal', [])) != [0.0, 1.0]:
            continue
        if not row.get('round', True):
            continue
        if row.get('width_standardized'):
            # Rewritten entry integers, not source flats.
            continue
        try:
            f = float(row.get('value', 0))
        except (TypeError, ValueError):
            continue
        if f <= 0 or f >= design:
            continue
        if (design - f) / f > FLAT_TOP_BAND_REL:
            continue
        if flat is None or f > flat:
            flat = f
    if flat is None:
        return None
    target = int(_round_pixel(flat * scale))
    if target == math.ceil(design * scale - 1e-9):
        return None
    return target


def standardize_hard_widths(record, cs, protected, hard_values, scale,
                             yrange, pins=None, design_points=None,
                             ends=None):
    """Supersede hard width-* Dist values with shared class targets.

    Microsoft CVT analogue at the joint solver: a hard width equation
    carries the shared integer target instead of the per-glyph rounded
    source distance, subject to the table's cut-in. Height-ladder
    rows (full spans, curved apexes) take an entry-relative span
    from the per-size cap table instead, and the redirected point
    itself is reported in ``pins`` so the caller can hold it on
    the entry integer (otherwise the joint splits the difference
    with the upstream soft goal and the apex floats half a pixel
    high) — VTT ResYAnchor attachment pattern. Metric
    maximum-bound rows (glyph top bounds without a width
    feature) redirect the same way when full-height; bound rows
    without an Abs source read it from ``design_points``. Other
    withheld shapes (ascender full heights, mid-glyph arc heights)
    keep the solver value;
    see ``_cap_redirect`` and ``_withholds_table``. Plain arc and
    bow band rows additionally never keep a raw design width: a
    shared target applies only when it thins, otherwise the honest
    half-up rounding hardens, so near-boundary designs cannot
    split by grid phase. Nothing hardens below the face's main
    stem target (span rows and sub-main targets keep the solver
    value as before). Every substitution is recorded. Without a
    width table only cap-table redirects apply. Returns the
    change list. Mutates ``hard_values`` and the deep-copied
    ``cs`` in place.
    """
    import math
    table = record.get('width_table')
    ctable = record.get('cap_table')
    if not _cap_table_eligible(ctable, design_points):
        ctable = None
    changes = []
    bound = {}
    if table is None and not ctable:
        return changes
    from stem_width_table import lookup as _table_lookup
    for pos, i in enumerate(protected):
        c = cs[i]
        if c['kind'] in ('Abs', 'PAbs'):
            redirected = _cap_abs_redirect(c, ctable, scale,
                                           design_points, ends)
            if redirected is None:
                # No table entry matched: same-glyph overshoot
                # collapse before natural rounding.
                collapsed = _flat_top_collapse(c, cs, scale)
                if collapsed is None:
                    continue
                target = collapsed
            else:
                target, _entry = redirected
            new_value = math.copysign(
                target, float(hard_values[pos]) or 1.0)
            if abs(hard_values[pos] - new_value) < 1e-9:
                continue
            changes.append(dict(constraint=c.get('id'), point=c['point'],
                                from_px=float(hard_values[pos]),
                                to_px=float(new_value)))
            hard_values[pos] = new_value
            cs[i] = dict(c, value=new_value / scale,
                         width_standardized=True)
            bound[c['point']] = (new_value, 1)
            continue
        name = c.get('feature', '')
        if c['kind'] not in ('Dist', 'PDist'):
            continue
        f = None
        if name.startswith('width-'):
            f = record['features'][int(name.split('-')[1])]
        elif not (c.get('metric') and _extent_sense(c) == 'max'):
            continue
        redirect = _cap_redirect(c, cs, ctable, yrange, f, scale,
                                 design_points)
        if redirect is not None and redirect[0] >= 1.0:
            new_value = math.copysign(redirect[0],
                                      float(c.get('value', 0)) or 1.0)
            pin = None
            if pins is not None:
                normal = list(c.get('normal', []))
                axis = max(range(len(normal)),
                           key=lambda a: abs(normal[a]))
                pin = dict(point=c['point'], axis=axis,
                           value_px=math.copysign(
                               float(redirect[1]['target_px']),
                               normal[axis] or 1.0),
                           span_constraint=c.get('id'))
        else:
            pin = None
            if f is None:
                continue
            if (f or {}).get('kind') in ('arc', 'bow'):
                # Curved bands always harden to an integer width.
                # Hardening a raw design width near a half-pixel
                # boundary leaves ink to grid phase, so symmetric
                # pairs split (literata-16 O renders 1px left but
                # 2px right from 1.70/1.74px designs). A shared
                # target applies only when it thins (Shamir 2003
                # §3.5); otherwise the honest half-up rounding
                # stands, and full-span extents keep the solver's
                # outward rounding, hardened explicitly. Faces
                # above 14px opt out (``arc_sharing``) and keep the
                # legacy advisory widths, which already match the
                # scaler there.
                if table is None:
                    continue
                # Span and extent rows keep the solver value on every
                # face: the withhold predates the sharing scope and
                # v1 honors it (literata-16 0 apex, roboto-20 O).
                if _withholds_table(c, f, yrange):
                    continue
                # Above 14px the plain shared target broke the frozen
                # v1 balance both ways, so this face keeps a narrow
                # widen-only rule: side widths (horizontal rows)
                # widen up to the shared target but never narrow
                # (roboto-16 8 sides 1.0 to 2.0px; roboto-20 O keeps
                # its solver 3px), while vertical spans keep the
                # solver value outright (source-sans-3-18 o apex
                # 1.36px unmoved). Spans are not stems: only side
                # widths standardize, matching the per-point
                # three-way (v1/v12/gated) evidence on 0/o/8.
                if not table.get('arc_sharing', True):
                    normal = list(c.get('normal', []))
                    vertical = len(normal) == 2 and abs(
                        normal[1]) >= abs(normal[0])
                    if vertical:
                        continue
                    target = _table_lookup(table, abs(float(f['width'])))
                    widened = max(abs(float(hard_values[pos])), target)
                    new_value = math.copysign(
                        widened, float(c.get('value', 0)) or 1.0)
                    if abs(hard_values[pos] - new_value) < 1e-9:
                        continue
                    changes.append(dict(
                        constraint=c.get('id'), point=c['point'],
                        from_px=float(hard_values[pos]),
                        to_px=float(new_value)))
                    hard_values[pos] = new_value
                    cs[i] = dict(c, value=new_value / scale,
                                 width_standardized=True)
                    continue
                design_px = abs(float(f['width']))*scale
                target = _table_lookup(table, abs(float(f['width'])))
                if not (abs(target) < design_px - 1e-9):
                    target = math.floor(design_px + 0.5)
                from stem_width_table import main_stem_target as _main
                main = _main(table)
                if main is not None and target < main - 1e-9:
                    # Never hint a curved band below the face's
                    # main stem target: roboto-16 O keeps its
                    # solver 2px apex while roboto-14 e takes 1px,
                    # each uniform with its size's stems.
                    continue
                new_value = math.copysign(target,
                                          float(c.get('value', 0)) or 1.0)
            else:
                if _withholds_table(c, f, yrange):
                    continue
                if table is None:
                    continue
                target = _table_lookup(table, abs(float(f['width'])))
                # Role-aware rejoin tried here (arch-probe-v19/v20,
                # 2026-09-15) and reverted: two predicates
                # (span-cover, endpoint-touch) each fired only on
                # source-sans-3 brackets at 18/20px, REJECTED
                # under absolute witness judgment (candidate far
                # from settled witnesses). The thin classes hold
                # only foundry-thin strokes; the repeater (n/m/p)
                # is already main-class. See ledger + scoreboard.
                new_value = math.copysign(target,
                                          float(c.get('value', 0)) or 1.0)
        if abs(hard_values[pos] - new_value) < 1e-9:
            continue
        if pin is not None:
            pins.append(pin)
            bound[c['point']] = (pin['value_px'], pin['axis'])
        changes.append(dict(constraint=c.get('id'), point=c['point'],
                            from_px=float(hard_values[pos]),
                            to_px=float(new_value)))
        hard_values[pos] = new_value
        cs[i] = dict(c, value=new_value / scale, width_standardized=True)
    if pins is not None and bound:
        _pin_zero_twins(cs, protected, bound, pins)
    return changes


def _pin_zero_twins(cs, protected, bound, pins):
    """Pin rigid twins of anchor-bound cap points.

    A cap point held on the anchor drags points rigidly linked to it
    by a zero-valued soft align row (e.g. literata-20 'C' apex twin);
    without the twin pin the apex dents (one point at the anchor,
    its twin floating half a pixel above). Twins share the design
    coordinate by construction, so the anchor value fits them
    exactly, subject to the same overshoot cut-in. One hop, soft
    Dist rows only; hard rows already enforce themselves.
    """
    import math
    guarded = set(protected)
    for j, r in enumerate(cs):
        if j in guarded or r['kind'] != 'Dist':
            continue
        if (r.get('feature') or '').startswith('width-'):
            continue
        try:
            if abs(float(r.get('value', 0))) > 1e-9:
                continue
        except (TypeError, ValueError):
            continue
        normal = list(r.get('normal', []))
        if len(normal) != 2:
            continue
        axis = max(range(2), key=lambda a: abs(normal[a]))
        if abs(normal[axis]) < 1e-9:
            continue
        sources = r.get('sources', [])
        if len(sources) != 1:
            continue
        pt = r.get('point')
        if pt in bound and sources[0] not in bound:
            twin, (value, twin_axis) = sources[0], bound[pt]
        elif sources[0] in bound and pt not in bound:
            twin, (value, twin_axis) = pt, bound[sources[0]]
        else:
            continue
        if axis != twin_axis:
            continue
        pins.append(dict(point=twin, axis=axis,
                         value_px=math.copysign(value,
                                                normal[axis] or 1.0),
                         span_constraint=r.get('id')))


def constrained_fit(hard, values, goals, targets):
    hard = np.asarray(hard, float); values = np.asarray(values, float)
    goals = np.asarray(goals, float); targets = np.asarray(targets, float)
    count = goals.shape[1]
    if len(hard):
        _, s, vt = np.linalg.svd(hard, full_matrices=True)
        rank = int(np.sum(s > max(hard.shape)*np.finfo(float).eps*s[0]))
        origin = np.linalg.lstsq(hard, values, rcond=None)[0]
        if np.max(abs(hard @ origin-values)) > 1e-8:
            raise ValueError('incompatible metric/global constraints')
        null = vt[rank:].T
    else:
        origin = np.zeros(count); null = np.eye(count)
    q = origin + null @ np.linalg.lstsq(goals @ null, targets-goals @ origin, rcond=None)[0]
    if not np.isfinite(q).all() or (len(hard) and np.max(abs(hard @ q-values)) > 1e-7):
        raise ValueError('joint metric residual failed')
    return q


def terminal_competitor(points, feature, features):
    """A broad, short pair can be the ends of an intersecting longer bar."""
    if feature.get('length', float('inf')) >= feature['width']:
        return None
    p = np.asarray(points, float)
    def bounds(f):
        n = np.asarray(f['normal']); d = np.asarray(f['support_direction'])
        normal = p[f['points']] @ n
        corners = [n*a+d*b for a in (min(normal),max(normal))
                   for interval in f['support_intervals'] for b in interval]
        return np.min(corners,axis=0), np.max(corners,axis=0)
    lo,hi = bounds(feature)
    for i, other in enumerate(features):
        if other['kind'] not in ('stem','bar') or abs(np.dot(feature['normal'],other['normal'])) > 1e-8:
            continue
        if other.get('length',0) <= other['width'] or other['width'] >= feature['width'] or other['length'] <= feature['length']:
            continue
        a,b = bounds(other)
        if np.all(np.minimum(hi,b)-np.maximum(lo,a) > 1e-8):
            return i
    return None


def stem_relations(points, ends, record):
    """Exact cardinal contour runs belonging to detected stem/bar sides."""
    p = np.asarray(points, float); cs = record['graph']['constraints']
    rows, audit, width_ids = [], [], []
    for c in cs:
        name = c.get('feature', '')
        if not name.startswith('width-') or c['kind'] not in ('Dist', 'PDist'):
            continue
        f = record['features'][int(name.split('-')[1])]
        n = np.asarray(f['normal'])
        if f['kind'] not in ('stem', 'bar') or not np.any(abs(n) == 1):
            continue
        competing = terminal_competitor(p, f, record['features'])
        if competing is not None:
            audit.append(dict(id=c['id'], status='excluded-terminal-length', competing_feature=competing))
            continue
        sides = []
        for rep in f['points']:
            start = 0
            for end in ends:
                if start <= rep <= end:
                    break
                start = end+1
            members = {rep}
            for direction in (-1, 1):
                j = rep
                while True:
                    j = start+(j-start+direction) % (end-start+1)
                    if j in members or abs(float((p[j]-p[rep]) @ n)) > 1e-8:
                        break
                    members.add(j)
            sides.append(sorted(members))
        if any(len(side) < 2 for side in sides):
            audit.append(dict(id=c['id'], status='held', reason='incomplete straight-side support'))
            continue
        width_ids.append(c['id'])
        for side, rep in zip(sides, f['points']):
            for j in side:
                if j == rep:
                    continue
                row = np.zeros(p.size); row[2*j:2*j+2] += n; row[2*rep:2*rep+2] -= n
                rows.append(row)
        audit.append(dict(id=c['id'], status='protected', sides=sides, normal=n.tolist()))
    return rows, width_ids, audit


def continuation_relations(points, ends, flags, constraints, stems):
    """One adjoining straight segment within 5 degrees of a protected side.

    Preserve an existing unrounded alignment in its own direction. No recursive
    propagation, new point links, or glyph identities participate in selection.
    """
    p = np.asarray(points, float); adjacent = set(); start = 0
    for end in ends:
        for a in range(start, end+1):
            b = a+1 if a < end else start
            adjacent.add(frozenset((a,b)))
        start = end+1
    selected = {}
    for stem in stems:
        if stem['status'] != 'protected':
            continue
        normal = np.asarray(stem['normal'])
        for side in stem['sides']:
            members = set(side)
            for c in constraints:
                if c['kind'] != 'Dist' or c.get('round', True) or not c.get('feature','').startswith('align-'):
                    continue
                if len(c['sources']) != 1 or abs(c['value']) > 1e-8:
                    continue
                a, b = c['point'], c['sources'][0]
                if (a in members) == (b in members) or frozenset((a,b)) not in adjacent:
                    continue
                if not (flags[a] & 1 and flags[b] & 1):
                    continue
                n = np.asarray(c['normal']); cosine = abs(float(n @ normal))
                if not np.cos(np.deg2rad(5.)) <= cosine < 1-1e-12:
                    continue
                if abs(float((p[a]-p[b]) @ n)-c['value']) > 1e-6:
                    continue
                selected[c['id']] = dict(id=c['id'], points=[a,b], normal=n.tolist(),
                    angle_degrees=float(np.rad2deg(np.arccos(min(1.,cosine)))), stem_id=stem['id'])
    return list(selected.values())


_ALIGN_FEATURE = _re.compile(r'align-\d+\Z')
_CARDINAL_NORMALS = ((1., 0.), (-1., 0.), (0., 1.), (0., -1.))


def select_member_alignments(points, flags, constraints):
    """Select existing declared source-exact cardinal zero-alignment rows.

    Returns (selected_ids, skipped) where selected_ids lists constraint ids
    and skipped lists dicts {id, reason}. Geometry/constraints only: no
    glyph, family, or size identities participate. No new pairs are invented,
    no coordinate merging, no weight/metric changes, no new thresholds.
    """
    p = np.asarray(points, float)
    selected, skipped = [], []
    for c in constraints:
        cid = c.get('id')
        if c.get('kind') != 'Dist':
            skipped.append(dict(id=cid, reason='non-Dist-kind'))
            continue
        if not isinstance(c.get('feature', ''), str) or not _ALIGN_FEATURE.match(c.get('feature', '')):
            skipped.append(dict(id=cid, reason='non-align-feature'))
            continue
        if c.get('round', True) is not False:
            skipped.append(dict(id=cid, reason='rounded-or-missing-round-flag'))
            continue
        if c.get('value') != 0:
            skipped.append(dict(id=cid, reason='nonzero-value'))
            continue
        sources = c.get('sources', [])
        if not isinstance(sources, list) or len(sources) != 1:
            skipped.append(dict(id=cid, reason='not-exactly-one-source'))
            continue
        a, b = c.get('point'), sources[0]
        if not isinstance(a, int) or not isinstance(b, int) or isinstance(a, bool) or isinstance(b, bool):
            skipped.append(dict(id=cid, reason='non-integer-index'))
            continue
        if not (0 <= a < len(p) and 0 <= b < len(p)):
            skipped.append(dict(id=cid, reason='index-out-of-range'))
            continue
        try:
            n = (float(c['normal'][0]), float(c['normal'][1]))
        except (KeyError, TypeError, IndexError, ValueError):
            skipped.append(dict(id=cid, reason='invalid-normal'))
            continue
        if not np.isfinite(n[0]) or not np.isfinite(n[1]):
            skipped.append(dict(id=cid, reason='non-finite-normal'))
            continue
        if n not in _CARDINAL_NORMALS:
            skipped.append(dict(id=cid, reason='non-cardinal-normal'))
            continue
        try:
            fa, fb = flags[a], flags[b]
        except (IndexError, TypeError):
            skipped.append(dict(id=cid, reason='missing-flags'))
            continue
        if not (fa & 1 and fb & 1):
            skipped.append(dict(id=cid, reason='off-curve-endpoint'))
            continue
        if float((p[a]-p[b]) @ np.asarray(n)) != 0.:
            skipped.append(dict(id=cid, reason='source-projected-distance-nonzero'))
            continue
        selected.append(cid)
    return selected, skipped


# Contours shorter than this never join cap uniformity: dots, tittles
# and small diacritics keep legacy rounding (holding their tops and
# bottoms together would squash them onto the entry). Dots run
# ~2px tall at 20ppem, cap crowns belong to full-height contours.
# (Carried over from the bespoke cap-anchor guard, same threshold.)
_CAP_PULL_MIN_RANGE_PX = 3.0
# Soft-pull window above the cap integer: geometric ceiling lifts
# cap-band crowns at most ~1px over the entry target.
_CAP_PULL_PX = 1.5


def _cap_soft_pulls(record, reference, ends, targets, design_points,
                    flags):
    """Retarget soft identity goals for cap overshoots to the entry.

    Points on text-height contours whose upstream position sits
    just above the flat_cap integer are rendering overshoots
    (the geometric stage ceilings them, e.g. roboto-14 crown
    points flat at 11.0); their soft goals pull to the entry
    instead of upstream so the whole crown settles with the
    hard-pinned apex. One-sided (down only), contour-size
    gated, flat-cut aware — unchanged from the bespoke
    version except the target/mode/ceiling now read the
    flat_cap entry and tall glyphs stand down by zone
    attachment (see ``_cap_table_eligible``).

    WHY retained, not sourced: soft-goal retargeting has no
    VTT parent (VTT leaves unlinked points to IUP), and the
    IUP-contradiction theory argued for deletion — but
    deleting it was rejected 6x on settled glyphs
    (literata-16 P/S, roboto-14 j, ss3-14 8, ss3-20 9/O),
    so the pulls are load-bearing soft-goal corrections
    pending conversion to explicit links. Pulls retarget to
    flat_cap only; ascender crowns keep upstream goals (no
    ascender pulls — future extension iff gated). Returns
    the pulled point list. Mutates ``targets``.
    """
    from stem_width_table import CAP_BAND_TOL
    ctable = record.get('cap_table')
    if not _cap_table_eligible(ctable, design_points):
        return []
    flat = next((e for e in (ctable or {}).get('entries', ())
                 if e.get('name') == 'flat_cap'), None)
    if flat is None:
        return []
    target = float(flat['target_px'])
    mode = float(flat['design_units'])
    ceiling = mode + CAP_BAND_TOL * abs(mode) if mode else None
    up_y = np.asarray(reference, float).ravel()[1::2]
    design = np.asarray(design_points, float)
    pulled = []
    start = 0
    for end in ends:
        lo = float(np.min(up_y[start:end + 1]))
        hi = float(np.max(up_y[start:end + 1]))
        big = hi - lo >= _CAP_PULL_MIN_RANGE_PX
        idx = list(range(start, end + 1))
        for k, a in enumerate(idx):
            if not big:
                continue
            if not target < up_y[a] <= target + _CAP_PULL_PX:
                continue
            if ceiling is not None and design[a][1] > ceiling:
                continue
            prev = idx[k - 1]
            nxt = idx[(k + 1) % len(idx)]
            try:
                flat_cut = ((flags[prev] & 1)
                            and abs(design[prev][1]
                                    - design[a][1]) <= 1e-9) \
                    or ((flags[nxt] & 1)
                        and abs(design[nxt][1]
                                - design[a][1]) <= 1e-9)
            except (IndexError, TypeError):
                flat_cut = False
            if flat_cut and design[a][1] <= mode:
                continue
            targets[2 * a + 1] = target
            pulled.append(a)
        start = end + 1
    return pulled


def fit(points, ends, flags, record, scale, complete_stems=False, continuations=False, reflection_em=None, reflection_ink=None, upstream=None, ownership=(), order_relations=(), curve_reflection=False, preserve_member_alignments=False):  # noqa: PLR0913
    """Experimental constrained least squares with optional Shamir-style link preservation.

    Preserves existing declared source-exact cardinal member links throughout
    the solve when enabled. Default behavior is unchanged. This is a diagnostic
    constraint-preservation pass inside an experimental solver, not a claim of
    whole-model conformance with Shamir or Microsoft.
    """
    p = np.asarray(points, float); source = p.ravel()*scale; count = p.size
    original, values = system(record['graph'], len(p), scale)
    # Advisory standardization rewrites span values below; work on
    # copies so a second fit with the same record (reflection re-fit)
    # recomputes redirects and pins instead of inheriting them.
    cs = [dict(c) for c in record['graph']['constraints']]
    protected = [i for i, c in enumerate(cs) if c.get('metric') or c['kind'].startswith('P')]
    # Curved width rows solve exactly like stem widths (roboto e/c
    # apex bands): an unprotected width equation is advisory only,
    # so its edges float to solver rounding. Conflicts still hold
    # safely downstream. Slants keep their soft-goal path below.
    for i, c in enumerate(cs):
        name = c.get('feature', '') or ''
        if not name.startswith('width-') or c['kind'] != 'Dist':
            continue
        try:
            f = (record.get('features', []) or [])[int(name.split('-')[1])]
        except (ValueError, IndexError):
            continue
        if (f or {}).get('kind') in ('arc', 'bow'):
            # Sharing protection needs the shared table: without one
            # (legacy sizes) arc rows stay advisory exactly as before.
            table = record.get('width_table')
            if table is not None and table.get('arc_sharing', True):
                protected.append(i)
    protected = sorted(set(protected))
    extra, stem_audit = [], []
    if complete_stems:
        extra, ids, stem_audit = stem_relations(p, ends, record)
        protected = sorted(set(protected) | {i for i,c in enumerate(cs) if c['id'] in ids})
    continuation_audit = continuation_relations(p, ends, flags, cs, stem_audit) if continuations else []
    continuation_ids = {c['id'] for c in continuation_audit}
    protected = sorted(set(protected) | {i for i,c in enumerate(cs) if c['id'] in continuation_ids})
    member_audit, member_skipped, member_ids = [], [], []
    member_rows = []
    if preserve_member_alignments:
        member_ids, member_skipped = select_member_alignments(p, flags, cs)
        member_audit = [dict(id=i, status='protected', reason='existing-zero-alignment-preserved') for i in member_ids]
        member_rows = sorted(i for i, c in enumerate(cs) if c['id'] in member_ids)
    if preserve_member_alignments:
        protected = sorted(set(protected) | set(member_rows))
    reference = source if upstream is None else np.asarray(upstream, float).ravel()
    goals = list(np.eye(count)); targets = list(reference)
    start = 0
    for end in ends:
        for a in range(start, end+1):
            b = a+1 if a < end else start
            for axis in (0, 1):
                row = np.zeros(count); row[2*b+axis] = 1; row[2*a+axis] -= 1
                goals.append(row); targets.append(float(row @ reference))
        start = end+1
    audit = []
    for c in cs:
        name = c.get('feature', '')
        if not name.startswith('width-') or c['kind'] not in ('Dist', 'PDist'):
            continue
        f = record['features'][int(name.split('-')[1])]
        if f['kind'] != 'slant':
            continue
        if c['kind'] == 'PDist':
            audit.append(dict(id=c['id'], status='held', reason='font-wide target retained'))
            continue
        try:
            weights = section(p, ends, flags, f)
        except ValueError as exc:
            audit.append(dict(id=c['id'], status='held', reason=str(exc)))
            continue
        sides = [[i for i,w in weights.items() if w < 0], [i for i,w in weights.items() if w > 0]]
        n = np.asarray(f['normal']); width = _round_pixel(f['width']*scale)
        if width <= 0:
            raise ValueError('joint width target collapses')
        pairs = [(*side, 0.) for side in sides] + [(a, b, width) for a,b in zip(*sides)]
        indices = []
        for a,b,target in pairs:
            row = np.zeros(count); row[2*b:2*b+2] += n; row[2*a:2*a+2] -= n
            indices.append(len(goals)); goals.append(2*row); targets.append(2*target)
        audit.append(dict(id=c['id'], status='soft-goal', sides=sides, target_px=width, goal_indices=indices))
    if upstream is None and not any(a['status']=='soft-goal' for a in audit):
        q,_ = evaluate_baseline(record['graph'], p, scale, 1.)
        return q, dict(relations=audit, candidate_status='no-match', released_equations=[])
    hard = list(original[protected])+extra
    hard_values = list(values[protected])+[0.]*len(extra)
    yrange = float(np.max(p[:, 1]) - np.min(p[:, 1])) if len(p) else 0.0
    base_n = len(hard)
    hv_backup = list(hard_values)
    cs_backup = list(cs)
    point_pins = []
    width_standardized = standardize_hard_widths(
        record, cs, protected, hard_values, scale, yrange, point_pins, p,
        ends)
    for pin in point_pins:
        row = np.zeros(count)
        row[2*pin['point']+pin['axis']] = 1
        hard.append(row)
        hard_values.append(pin['value_px'])
    targets_backup = list(targets)
    cap_pulls = _cap_soft_pulls(record, reference, ends, targets, p,
                                flags)
    for c in order_relations:
        row=np.zeros(count);row[2*c['b']+c['axis']]=1;row[2*c['a']+c['axis']]=-1
        hard.append(row);hard_values.append(c['value'])
    for owner in ownership:
        row = np.zeros(count); row[2*owner['point']+owner['axis']] = 1
        hard.append(row); hard_values.append(owner['value'])
    cap_retry = False
    while True:
        try:
            q = constrained_fit(hard, hard_values, goals, targets)
        except ValueError:
            if (width_standardized or point_pins or cap_pulls) \
                    and not cap_retry:
                # Advisory cap treatment conflicted with hard
                # geometry: restore the legacy joint system and solve
                # once more instead of discarding the whole fit.
                # Pins sit between the protected rows and the
                # order/ownership rows, so excise exactly that span.
                n_pins = len(point_pins)
                cs[:] = cs_backup
                del hard[base_n:base_n + n_pins]
                hard_values[:len(hv_backup)] = hv_backup
                del hard_values[base_n:base_n + n_pins]
                targets[:] = targets_backup
                width_standardized = []
                point_pins = []
                cap_pulls = []
                cap_retry = True
                continue
            if upstream is not None or not complete_stems:
                raise
            # Preserve the previous joint candidate on an incompatible proposal.
            q, audit = fit(points, ends, flags, record, scale, complete_stems=complete_stems if continuations else False, preserve_member_alignments=preserve_member_alignments)
            audit.update(candidate_status='held-continuation-conflict' if continuations else 'held-stem-conflict',
                         stem_relations=stem_audit, continuation_relations=continuation_audit)
            return q, audit
        break
    reflection = dict(status='disabled')
    if reflection_em is not None:
        if reflection_ink is None:
            raise ValueError('reflection requires the current rendered bitmap')
        ink = set(reflection_ink)
        if not ink or ink == {(min(x for x,y in ink)+max(x for x,y in ink)-x,y) for x,y in ink}:
            reflection = dict(status='already-symmetric')
            reflection_em = None
    if reflection_em is not None:
        from feature_coordination import reflected_outline
        _, match = reflected_outline(p, q.reshape(-1,2), ends, flags, reflection_em)
        weighted_reflection = False
        if curve_reflection and match['status'] not in ('coordinated','ambiguous'):
            from outline_relationships import curve_correspondence
            match=curve_correspondence(p,ends,flags,reflection_em)
            weighted_reflection = True
        reflection = dict(status=match['status'], method='curve' if weighted_reflection else 'point', source_error_units=match.get('source_error_units'))
        if match['status']=='coordinated':
            pairs = match['pairs'] if weighted_reflection else sorted({tuple(sorted(pair)) for pair in match['pairs']})
            center = (p[:,0].min()+p[:,0].max())*scale/2
            nearest = _round_pixel(2*center)/2
            candidates = []
            phase_rejected = []
            for axis in [nearest+d/2 for d in (-2,-1,0,1,2)]:
                if not mirror_phase_ok(axis, pairs, p, record):
                    phase_rejected.append(axis)
                    continue
                mirror_rows, mirror_values = [], []
                for a,b in pairs:
                    row = np.zeros(count)
                    if weighted_reflection:
                        row[::2]=a+b
                        mirror_rows.append(row);mirror_values.append(2*axis)
                        row=np.zeros(count);row[1::2]=a-b
                        mirror_rows.append(row);mirror_values.append(0.)
                    else:
                        row[2*a] += 1; row[2*b] += 1
                        mirror_rows.append(row); mirror_values.append(2*axis)
                        if a != b:
                            row = np.zeros(count); row[2*a+1] += 1; row[2*b+1] -= 1
                            mirror_rows.append(row); mirror_values.append(0.)
                try:
                    candidate = constrained_fit(hard+mirror_rows, hard_values+mirror_values, goals, targets)
                except ValueError:
                    continue
                score = float(np.sum((np.asarray(goals) @ candidate-targets)**2))
                candidates.append((score,abs(axis-center),axis,candidate))
            if candidates:
                score,_,axis,q = min(candidates,key=lambda c:c[:3])
                reflection = dict(status='fitted',method='curve' if weighted_reflection else 'point',axis_px=axis,source_residual_units=match['source_residual_units'],
                                  candidate_scores=[dict(axis_px=c[2],score=c[0]) for c in candidates],
                                  phase_rejected_axes=phase_rejected)
            else:
                reflection = dict(status='held-phase-conflict' if phase_rejected else 'held-conflict',
                                  phase_rejected_axes=phase_rejected)
    for a in audit:
        if a['status']=='soft-goal':
            a['alignment_and_width_errors_px'] = [float((goals[i] @ q-targets[i])/2) for i in a['goal_indices']]
    changes = [dict(c, residual_px=float(original[i] @ q-values[i])) for i,c in enumerate(cs)
               if i not in protected and abs(original[i] @ q-values[i]) > 1e-7]
    result = dict(relations=audit, candidate_status='joint-fit',
        protected_ids=[cs[i]['id'] for i in protected], released_equations=changes,
        width_standardized=width_standardized,
        cap_point_pins=point_pins,
        cap_soft_pulls=sorted(cap_pulls),
        cap_conflict_retry=cap_retry,
        stem_relations=stem_audit,
        continuation_relations=continuation_audit,
        reflection=reflection,
        max_hard_residual_px=float(np.max(abs(np.asarray(hard) @ q-hard_values))) if hard else 0.)
    if preserve_member_alignments:
        result.update(member_alignment_relations=member_audit,
                      member_alignment_skipped=member_skipped,
                      experimental_status='member-alignment-preservation')
    return q.reshape(-1,2), result
