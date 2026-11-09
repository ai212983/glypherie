"""Depth-limited delivered walls for the isolated Hu/Hersch experiment.

Hu (1998), §4.4, grounds bitmap walls and unit-slope filtering. Hersch et al.
(1995), pp. 86–87 and Fig. 19, ground aperture-relative depth and a separate
body-height depth measured from the exterior bounding-box edge. Neither paper
supplies arbitrary-font classification code. The associated Hersch/Betrisey
patent US5768490A, description of transformations B–D and Fig. 2, supplies
DepthFactor=.21, GlobalDepthParameter=.25 and asymmetric depth construction.
The bounded-bay unit-slope envelope and midpoint integral are explicit raster
adaptations, not recovered author code. The global envelope and hull-chord
helpers below remain only for retained diagnostic comparisons. Shapes and
production metrics remain untouched. See the owning design for calibration.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import math

import filtered_walls as walls
from estimator import GeometryError, WorkLimitExceeded, _evaluate, _finite, _roots, _segments


POLICY = "hu-hersch-patent-bounded-cell-walls-v2"
SOURCE_POLICY = "hu-hersch-patent-sampled-continuous-source-walls-v1"
CLASSIFIER_POLICY = "source-midline-exact-facing-elements-v1"
PUBLISHED_RELATIVE_DEPTH = .21
PUBLISHED_VISUAL_DEPTH_FACTOR = .25


@dataclass(frozen=True)
class Settings:
    relative_depth: float
    visual_depth_factor: float
    samples_per_px: int = 64

    def __post_init__(self):
        for name in ("relative_depth", "visual_depth_factor"):
            if _finite(getattr(self, name), name) < 0:
                raise GeometryError(f"{name} must be nonnegative")
        if type(self.samples_per_px) is not int or not 1 <= self.samples_per_px <= 1024:
            raise GeometryError("samples_per_px must be an integer in [1, 1024]")


@dataclass(frozen=True)
class Cavity:
    bottom_px: float
    top_px: float
    opening_px: float
    aperture_depth_px: float
    raw_max_depth_px: float
    bottom_outward_x_px: float
    top_outward_x_px: float


@dataclass(frozen=True)
class Profile:
    bounds: walls.Bounds | None
    window: tuple[float, float]
    ys: tuple[float, ...]
    left: tuple[float, ...]
    right: tuple[float, ...]
    occupied: tuple[bool, ...]
    slope_left: tuple[float, ...]
    slope_right: tuple[float, ...]
    filtered_left: tuple[float, ...]
    filtered_right: tuple[float, ...]
    left_cavities: tuple[Cavity, ...]
    right_cavities: tuple[Cavity, ...]
    settings: Settings
    construction_window: tuple[float, float] | None = None

    @property
    def rawleft(self):
        return self.left

    @property
    def rawright(self):
        return self.right


def _upper_hull(points):
    """Upper hull in (physical y, outward x), retaining collinear supports."""
    merged = {}
    for y, x in points:
        merged[y] = max(x, merged.get(y, -math.inf))
    result = []
    for point in sorted(merged.items()):
        while len(result) >= 2:
            a, b = result[-2:]
            cross = (b[0] - a[0]) * (point[1] - b[1]) - (b[1] - a[1]) * (point[0] - b[0])
            if cross <= 0:
                break
            result.pop()
        result.append(point)
    return tuple(result)


def _supports(rows, bounds, window, side):
    lo, hi = window
    ys = {lo, hi}
    for row in rows:
        for y in (-row - 1, -row):
            if lo < y < hi:
                ys.add(y)
    sign = 1 if side == "right" else -1
    index = 1 if side == "right" else 0
    opposite = bounds.minx if side == "right" else bounds.maxx
    result = []
    for y in sorted(ys):
        candidates = [rows[r][index] for r in {math.floor(-y), math.ceil(-y) - 1} if r in rows]
        value = (max(candidates) if side == "right" else min(candidates)) if candidates else opposite
        result.append((y, sign * value))
    return _upper_hull(result)


def _aperture_caps(ys, raw, hull, relative_depth):
    """Retained hull-chord comparison helper; not the production patent C."""
    caps = [-math.inf] * len(ys)
    cavities = []
    for (y0, x0), (y1, x1) in zip(hull, hull[1:]):
        start, stop = bisect_left(ys, y0), bisect_right(ys, y1)
        opening = y1 - y0
        if not opening or start == stop:
            continue
        mouth = [x0 + (y - y0) * (x1 - x0) / opening for y in ys[start:stop]]
        depth = max((x - raw[i] for i, x in enumerate(mouth, start)), default=0)
        if depth <= 0:
            continue
        limit = _finite(relative_depth * opening, "aperture depth")
        cavities.append(Cavity(y0, y1, opening, limit, depth, x0, x1))
        for i, x in enumerate(mouth, start):
            caps[i] = max(caps[i], x - limit)
    return tuple(caps), tuple(cavities)


@dataclass(frozen=True)
class _Bay:
    bottom_px: float
    top_px: float
    bottom_outward_x_px: float
    top_outward_x_px: float


def _wall(ys, values, window):
    if len(ys) != len(values) or not ys:
        raise GeometryError("wall samples must be nonempty and match coordinates")
    if len(ys) > walls.MAX_SAMPLES:
        raise WorkLimitExceeded("wall sample limit exceeded")
    if not isinstance(window, (tuple, list)) or len(window) != 2:
        raise GeometryError("wall window requires two coordinates")
    lo, hi = (_finite(v, "wall window") for v in window)
    if not lo < hi:
        raise GeometryError("wall window must have positive height")
    ys = tuple(_finite(y, "wall y") for y in ys)
    values = tuple(_finite(v, "outward wall") for v in values)
    if not lo < ys[0] <= ys[-1] < hi or any(a >= b for a, b in zip(ys, ys[1:])):
        raise GeometryError("wall samples must increase strictly inside window")
    return ys, values, (lo, hi)


def _local_bays(ys, values):
    """Adjacent local exterior maxima bound valleys; monotone shoulders do not.

    Equal-valued runs are plateau supports. Mouths are the cell-interval edges
    nearest the intervening valley, rather than plateau centers or hull chords.
    This is an exact plateau operation on the sampled piecewise-constant wall.
    """
    runs = []
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[start]:
            runs.append((start, i - 1, values[start]))
            start = i
    peaks = [v for i, v in enumerate(runs)
             if (i == 0 or v[2] > runs[i-1][2]) and (i == len(runs)-1 or v[2] > runs[i+1][2])]
    bays = []
    for a, b in zip(peaks, peaks[1:]):
        if a[1] + 1 >= b[0] or min(values[a[1]+1:b[0]]) >= min(a[2], b[2]):
            continue
        y0 = (ys[a[1]] + ys[a[1]+1]) / 2
        y1 = (ys[b[0]-1] + ys[b[0]]) / 2
        if y0 < y1:
            bays.append(_Bay(y0, y1, a[2], b[2]))
    return tuple(bays)


def _bounded_45(ys, raw, bays):
    result = list(raw)
    for bay in bays:
        start, stop = bisect_left(ys, bay.bottom_px), bisect_right(ys, bay.top_px)
        coords = (bay.bottom_px, *ys[start:stop], bay.top_px)
        values = [bay.bottom_outward_x_px, *raw[start:stop], bay.top_outward_x_px]
        for i in range(1, len(values)):
            values[i] = max(values[i], values[i-1] - (coords[i]-coords[i-1]))
        for i in range(len(values)-2, -1, -1):
            values[i] = max(values[i], values[i+1] - (coords[i+1]-coords[i]))
        for i, value in enumerate(values[1:-1], start):
            result[i] = max(result[i], value)
    return tuple(result)


def concavity_filter_45(ys, outward_wall, window):
    """Unit-slope envelope restricted to bounded concave bays.

    Hersch B restricts its tangent replacement to concave outline parts. A
    global Lipschitz envelope also expands convex and monotone exteriors. This
    raster adaptation bounds the envelope by adjacent local-max plateaus; it
    deliberately does not claim to recover every monotone concave source arc
    or author tangent-extension/intersection outside the bay.
    """
    ys, raw, _ = _wall(ys, outward_wall, window)
    return _bounded_45(ys, raw, _local_bays(ys, raw))


def _first_cut_intersection(coords, values, cutoff):
    for ya, yb, xa, xb in zip(coords, coords[1:], values, values[1:]):
        if xa >= cutoff and xb < cutoff:
            return ya + (yb-ya) * (xa-cutoff) / (xa-xb)
    return None


def _aperture_filter(ys, raw, slope, bays, relative_depth):
    result = list(slope)
    cavities = []
    for bay in bays:
        start, stop = bisect_left(ys, bay.bottom_px), bisect_right(ys, bay.top_px)
        opening = bay.top_px - bay.bottom_px
        depth = _finite(relative_depth * opening, "aperture depth")
        exterior = max(bay.bottom_outward_x_px, bay.top_outward_x_px)
        cutoff = exterior - depth
        raw_depth = max((exterior - raw[i] for i in range(start, stop)), default=0.)
        cavities.append(Cavity(bay.bottom_px, bay.top_px, opening, depth, raw_depth,
                               bay.bottom_outward_x_px, bay.top_outward_x_px))
        inner = min(bay.bottom_outward_x_px, bay.top_outward_x_px)
        if inner >= cutoff:
            for i in range(start, stop):
                result[i] = max(result[i], cutoff)
            continue
        # Patent Fig. 2b: a clipped line would lie outside the inner lip. Join
        # its departure (first intersection from the exterior lip) directly to
        # that inner lip, rather than offsetting the entire mouth chord.
        forward = bay.bottom_outward_x_px >= bay.top_outward_x_px
        coords = (bay.bottom_px, *ys[start:stop], bay.top_px)
        values = (bay.bottom_outward_x_px, *slope[start:stop], bay.top_outward_x_px)
        if not forward:
            coords, values = tuple(-y for y in reversed(coords)), tuple(reversed(values))
        departure = _first_cut_intersection(coords, values, cutoff)
        if departure is None:
            continue
        end = coords[-1]
        for i in range(start, stop):
            y = ys[i] if forward else -ys[i]
            if departure <= y <= end:
                connector = cutoff + (y-departure) * (inner-cutoff) / (end-departure)
                result[i] = max(result[i], connector)
    return tuple(result), tuple(cavities)


def aperture_filter(ys, raw_outward_wall, filtered_outward_wall, window, relative_depth):
    """Patent C exterior-maximum cutoff and asymmetric connector on cell bays."""
    ys, raw, _ = _wall(ys, raw_outward_wall, window)
    _, slope, _ = _wall(ys, filtered_outward_wall, window)
    relative_depth = _finite(relative_depth, "relative depth")
    if relative_depth < 0:
        raise GeometryError("relative depth must be nonnegative")
    return _aperture_filter(ys, raw, slope, _local_bays(ys, raw), relative_depth)


def depth_profile(bitmap, window, settings):
    """Immutable cell walls with bounded B, patent C and independent global D."""
    if not isinstance(settings, Settings):
        raise GeometryError("depth profile requires Settings")
    raw = walls.bitmap_profile(bitmap, window, settings.samples_per_px)
    return _depth_profile(raw, settings)


def source_depth_profile(commands, scale_px, window, settings):
    """Continuous source Beziers sampled on the same physical midpoint grid.

    This shares the entire bounded B/patent C/global D pipeline with delivered
    cells. Source contours are intersected directly, never rerasterized. Local
    maxima and bay mouths remain a finite sampled-wall adaptation: unlike cell
    walls, source values vary within a sample interval, requiring convergence
    checks. No source metric or geometry is modified by the measurement.
    """
    if not isinstance(settings, Settings):
        raise GeometryError("source depth profile requires Settings")
    raw = walls.source_profile(commands, scale_px, window, settings.samples_per_px)
    return _depth_profile(raw, settings)


def full_source_depth_profile(commands, scale_px, window, settings):
    """Construct complete walls, then integrate the retained body window.

    US5768490A transforms the modified outline before measuring visual space;
    C intersects the contour obtained by A and B. This candidate therefore
    retains full contour supports, redetects C bays on B, and only then crops
    the sample arrays. The fixed body integration window remains our declared
    adaptation, and D still uses that body's height, not the full ink height.
    The legacy windowed construction remains unchanged in source_depth_profile.
    """
    if not isinstance(settings, Settings):
        raise GeometryError("source depth profile requires Settings")
    body = walls.source_profile(commands, scale_px, window, settings.samples_per_px)
    if body.bounds is None:
        return _depth_profile(body, settings)
    lo, hi = body.window
    dy = (hi-lo) / len(body.ys)
    before = math.ceil(_finite(max(0., lo-body.bounds.miny) / dy, "construction samples before body"))
    after = math.ceil(_finite(max(0., body.bounds.maxy-hi) / dy, "construction samples after body"))
    count = before + len(body.ys) + after
    if count > walls.MAX_SAMPLES:
        raise WorkLimitExceeded("full-outline construction sample limit exceeded")
    construction_window = (lo-before*dy, hi+after*dy)
    ys = (tuple(body.ys[0] - i*dy for i in range(before, 0, -1)) + body.ys +
          tuple(body.ys[-1] + i*dy for i in range(1, after+1)))
    # Validate coordinate representability as well as the declared work bound.
    _wall(ys, (0.,)*count, construction_window)
    full = walls._sample_source_profile(commands, scale_px, construction_window, ys, dy)
    transformed = _depth_profile(full, settings, body_height=hi-lo, post_b_cavities=True)
    end = before + len(body.ys)
    crop = lambda values: values[before:end]
    return Profile(body.bounds, body.window, body.ys, crop(transformed.left), crop(transformed.right),
                   crop(transformed.occupied), crop(transformed.slope_left), crop(transformed.slope_right),
                   crop(transformed.filtered_left), crop(transformed.filtered_right),
                   transformed.left_cavities, transformed.right_cavities, settings, construction_window)


def _depth_profile(raw, settings, *, body_height=None, post_b_cavities=False):
    """Common geometry-independent wall transformation, preserving sample grid."""
    if raw.bounds is None:
        return Profile(raw.bounds, raw.window, raw.ys, raw.left, raw.right, raw.occupied,
                       raw.filtered_left, raw.filtered_right, raw.filtered_left, raw.filtered_right,
                       (), (), settings)
    height = _finite(raw.window[1] - raw.window[0] if body_height is None else body_height, "body height")
    if height <= 0:
        raise GeometryError("body height must be positive")
    global_depth = _finite(settings.visual_depth_factor * height, "visual depth")
    left_outward = tuple(-x for x in raw.left)
    left_bays, right_bays = _local_bays(raw.ys, left_outward), _local_bays(raw.ys, raw.right)
    slope_left = _bounded_45(raw.ys, left_outward, left_bays)
    slope_right = _bounded_45(raw.ys, raw.right, right_bays)
    if post_b_cavities:
        left_bays = _local_bays(raw.ys, slope_left)
        right_bays = _local_bays(raw.ys, slope_right)
    aperture_left, left_cavities = _aperture_filter(raw.ys, left_outward, slope_left, left_bays,
                                                 settings.relative_depth)
    aperture_right, right_cavities = _aperture_filter(raw.ys, raw.right, slope_right, right_bays,
                                                    settings.relative_depth)
    left = tuple(min(-value, raw.bounds.minx + global_depth) for value in aperture_left)
    right = tuple(max(value, raw.bounds.maxx - global_depth) for value in aperture_right)
    return Profile(raw.bounds, raw.window, raw.ys, raw.left, raw.right, raw.occupied,
                   tuple(-x for x in slope_left), slope_right, left, right, left_cavities, right_cavities,
                   settings)


def pair_offset(left, right):
    """Linear mean-gap intercept; add the relative origin step to get mean gap."""
    return walls.pair_offset(left, right)


def depth_limits(bitmap, window, samples_per_px=64):
    """Data-derived coefficients making both caps inactive on this sampled input.

    These are finite search bounds, not proposed perceptual coefficients. A zero
    aperture bound means this input supplies no aperture-depth fitting evidence.
    Left cavity chord x coordinates use the outward coordinate -x.
    """
    profile = depth_profile(bitmap, window, Settings(0, 0, samples_per_px))
    cavities = (*profile.left_cavities, *profile.right_cavities)
    relative = max((v.raw_max_depth_px / v.opening_px for v in cavities), default=0.)
    height = profile.window[1] - profile.window[0]
    visual = (max(profile.bounds.maxx - min(profile.right), max(profile.left) - profile.bounds.minx) / height
              if profile.bounds is not None else 0.)
    return dict(relative_depth_upper=relative, visual_depth_factor_upper=visual,
                cavity_count=len(cavities))


def _source_segments(commands, scale):
    scale = _finite(scale, "source scale")
    if scale <= 0:
        raise GeometryError("source scale must be positive")
    return [tuple(tuple(_finite(v * scale, "source coordinate") for v in p) for p in ps)
            for ps in _segments(commands)]


def _at_y(segments, y):
    result = []
    for index, ps in enumerate(segments):
        ts = sorted({0., 1., *_roots(ps, 1)})
        for ta, tb in zip(ts, ts[1:]):
            a, b = _evaluate(ps, ta), _evaluate(ps, tb)
            if a[1] == b[1]:
                if a[1] == y:
                    result.extend((p[0], index) for p in (a, b))
            elif min(a[1], b[1]) <= y <= max(a[1], b[1]):
                result.append((walls._intersection(walls._coefficients(ps, 0),
                               walls._coefficients(ps, 1), ta, tb, a, b, y), index))
    return result


def _joined_endpoint(segments, index, t, choose):
    ps = segments[index]
    point = ps[0] if t == 0 else ps[-1]
    own = (ps[1][1] - ps[0][1]) if t == 0 else (ps[-1][1] - ps[-2][1])
    for other_index, other in enumerate(segments):
        if index == other_index or len(other) == 2:
            continue
        if t == 0 and other[-1] == point and other[-2][0] == point[0]:
            adjacent = other[-1][1] - other[-2][1]
        elif t == 1 and other[0] == point and other[1][0] == point[0]:
            adjacent = other[1][1] - other[0][1]
        else:
            continue
        if own * adjacent <= 0:
            continue
        extrema = (_evaluate(other, u)[0] for u in (0., 1., *_roots(other, 0)))
        if choose(extrema) == point[0]:
            return True
    return False


def classify_face(source_commands, scale, window, side):
    """Conservative geometric facing-element classifier, with no glyph names.

    The exterior source intersection at body mid-height selects its element.
    Exact vertical segments are stems. A nonlinear segment qualifies as a curve
    only when its own/joined endpoint has a vertical tangent at an exterior
    outward extremum inside the body. Diagonals, inward curves and ambiguous
    multiple elements retain the generic depth-limited wall model.
    """
    if side not in ("left", "right"):
        raise GeometryError("face side must be left or right")
    window, _, _ = walls._grid(window, 1)
    lo, hi = window
    mid = lo + (hi - lo) / 2
    segments = _source_segments(source_commands, scale)
    intersections = _at_y(segments, mid)
    generic = dict(kind="generic", reason="no_supported_facing_element",
                   source_support_x_px=None, source_support_y_px=None)
    if not intersections:
        return dict(generic, reason="no_source_body_intersection")
    choose = min if side == "left" else max
    outer = choose(x for x, _ in intersections)
    selected = {i for x, i in intersections if x == outer}
    if len(selected) * len(segments) > walls.MAX_SCANLINE_VISITS:
        raise WorkLimitExceeded("source facing-element classification limit exceeded")
    kinds = []
    for index in sorted(selected):
        ps = segments[index]
        if all(p[0] == ps[0][0] for p in ps) and min(p[1] for p in ps) < mid < max(p[1] for p in ps):
            kinds.append(dict(kind="stem", reason="exact_vertical_source_body_segment",
                              source_support_x_px=outer, source_support_y_px=mid))
            continue
        if len(ps) == 2:
            continue
        candidates = list(_roots(ps, 0))
        if ps[0][0] == ps[1][0] and ps[0][1] != ps[1][1]:
            candidates.append(0.)
        if ps[-1][0] == ps[-2][0] and ps[-1][1] != ps[-2][1]:
            candidates.append(1.)
        for t in candidates:
            x, y = _evaluate(ps, t)
            if not lo < y < hi:
                continue
            if t in (0., 1.) and not _joined_endpoint(segments, index, t, choose):
                continue
            # Exact segment extrema reject inward-facing inner bowls, without
            # an angle/curvature threshold or confusing control bounds with ink.
            extreme_x = choose(_evaluate(ps, t0)[0] for t0 in (0., 1., *_roots(ps, 0)))
            if extreme_x != x:
                continue
            actual = _at_y(segments, y)
            if actual and choose(v for v, _ in actual) == x:
                kinds.append(dict(kind="curve", reason="outward_source_curve_extremum",
                                  source_support_x_px=x, source_support_y_px=y))
                break
    if not kinds:
        return generic
    if len({v["kind"] for v in kinds}) != 1:
        return dict(generic, reason="ambiguous_source_facing_elements")
    return kinds[0]


def delivered_face(profile, side, classification):
    """Return an actual delivered edge; source support x never supplies spacing."""
    if side not in ("left", "right"):
        raise GeometryError("face side must be left or right")
    if profile.bounds is None:
        return None
    values = profile.left if side == "left" else profile.right
    kind = classification.get("kind")
    if kind == "curve":
        occupied = [x for x, ink in zip(values, profile.occupied) if ink]
        return (min(occupied) if side == "left" else max(occupied)) if occupied else None
    if kind == "stem":
        middle = (profile.window[0] + profile.window[1]) / 2
        # On an even midpoint grid either neighboring row can meet the exact
        # body midline. Both must agree; a raster stair is not silently a stem.
        i = bisect_left(profile.ys, middle)
        indices = {max(0, min(len(values) - 1, i)), max(0, min(len(values) - 1, i - 1))}
        selected = [values[j] for j in indices if profile.occupied[j]]
        return selected[0] if len(selected) == len(indices) and len(set(selected)) == 1 else None
    return None
