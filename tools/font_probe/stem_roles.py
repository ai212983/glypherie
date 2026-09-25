"""Per-link stem roles: our analogue of VTT link color.

VTT classifies every link geometrically (``TrueTypeGlyph::TheColor``,
``docs/reference/VisualTrueType/src/TTFont.cpp:145``: ray parity on
the outline sorts spans into black/white/grey) and consumes the
role per link as a flag (``TTGenerator.cpp:736``: black links take
minimum-distance protection, white links do not). This module is
the same pattern for a second role axis VTT color does not cover:
both plus-sign arms and n stems span ink, so color cannot split
them. The axis here is zone attachment: a stem stood on (or hung
from) a shared horizontal zone is ``anchored``; one floating
between zones is ``floating``.

DRAFT, not consumed anywhere: no caller reads roles yet, so this
changes no pixels and needs no census/oracle gate. Wiring roles
into ``lookup``/``standardize_hard_widths`` is the scoreboard OPEN
item and gets its own regen + dual-witness gate when it happens.

Inputs are plain design-unit numbers (endpoint heights, zone
heights, tolerance), mirroring how ``TheColor`` takes point
indices plus the glyph and returns a role. Adapting record
features (``a``/``b`` endpoints, ``cap_anchor`` mode) to these
inputs belongs to the wiring step, not here.

Calibration note (WHY, provisional): the zone list starts at
baseline 0 plus the voted cap line when known; x-height is
deliberately absent (no record carries it — only a raster
diagnostic in ``calibrate.py``). Tolerance is caller-supplied
in design units; overshoot scale (~1% of em, the ``CAP_BAND_TOL``
family) is the expected magnitude, to be confirmed against
witnesses at wiring time.
"""

ANCHORED = 'anchored'
FLOATING = 'floating'


def zones_for_face(cap_mode_units=None):
    """Shared horizontal zones for a face in design units.

    Baseline 0 always; the voted cap line (``vote_cap_anchor``
    ``mode_units``) appended when known. Returns a list, possibly
    just ``[0.0]``.
    """
    zones = [0.0]
    if cap_mode_units is None:
        return zones
    try:
        mode = float(cap_mode_units)
    except (TypeError, ValueError):
        return zones
    if mode != 0 and all(mode != z for z in zones):
        zones.append(mode)
    return zones


def role_of(endpoint_ys, zones, tol_units):
    """Role of one stem from its endpoint heights.

    ``anchored`` when an endpoint stands on (or hangs from) a
    shared zone within ``tol_units``; otherwise ``floating``.
    Span-crossing alone does not anchor: oracle adjudication
    (arch-probe-v19, 2026-09-15) rejected span-cover semantics
    on source-sans-3 brackets at 18/20px — the widened
    candidate sat 14/21px from settled (W=0) witnesses that
    keep the full-height ``[`` thin — so a stem merely
    passing through zones floats. Empty zones or empty
    endpoints float: with nothing to attach to, no attachment
    can be claimed.
    """
    try:
        tol = float(tol_units)
    except (TypeError, ValueError):
        return FLOATING
    if tol < 0:
        return FLOATING
    try:
        ends = [float(y) for y in endpoint_ys]
        bounds = [float(z) for z in zones]
    except (TypeError, ValueError):
        return FLOATING
    if not ends or not bounds:
        return FLOATING
    for y in ends:
        for z in bounds:
            if abs(y - z) <= tol:
                return ANCHORED
    return FLOATING


ZONE_TOL_PX = 0.5


def tol_for_scale(scale):
    """Zone slack in design units for a ppem/em ``scale``.

    Half a pixel each side: attachment is a zone relation, not
    a rounding decision, so the slack is generous by design.
    Provisional calibration (see module note).
    """
    try:
        scale = float(scale)
    except (TypeError, ValueError):
        return None
    if not scale > 0:
        return None
    return ZONE_TOL_PX / scale


def role_for_feature(feature, zones, tol_units):
    """Role of a record feature, or None to abstain (legacy path).

    Vertical ``stem`` features read their endpoints from the
    extremes of ``support_intervals`` (stations along the
    vertical support direction, same design-unit space as the
    outline — see ``joint_stroke_fit`` bounds reconstruction).
    Horizontal ``bar`` features read their station height from
    the ``a``/``b`` endpoints. Slants, curves, and features
    without geometry abstain: the curved branch and the
    withhold path are separate ledger items and keep legacy
    behavior here.
    """
    kind = (feature or {}).get('kind')
    try:
        if kind == 'stem':
            direction = [float(v) for v in
                         (feature.get('support_direction') or ())]
            if len(direction) != 2 or abs(direction[1]) < abs(
                    direction[0]):
                return None
            bounds = []
            for interval in feature.get('support_intervals') or ():
                bounds.extend(float(v) for v in interval)
            if len(bounds) < 2:
                return None
            return role_of([min(bounds), max(bounds)], zones,
                           tol_units)
        if kind == 'bar':
            a = feature.get('a')
            b = feature.get('b')
            if a is None or b is None:
                return None
            return role_of([float(a[1]), float(b[1])], zones,
                           tol_units)
    except (TypeError, ValueError, IndexError):
        return None
    return None
