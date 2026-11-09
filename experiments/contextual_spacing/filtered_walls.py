"""Hu-inspired midpoint wall integration, in floating pixels on a y-up baseline.

Hu (1998), section 4.4, supplies bitmap walls, opposite-edge substitution for
empty rows, and a +/-45 degree concavity filter. The min/max distance transform
below is this experiment's explicit discrete formalization, not a reproduction
of unavailable original code. Source Beziers and full bitmap-cell edges share a
fixed class window and midpoint grid. Increasing sampling density approximates
the continuous cell envelope; row-center filtering alone is a different model.

The closed-cell clearance bound adapts Hersch et al. (1995), pp. 85-88's minimum
clearance principle. It includes diagonal contact and all ink outside the window,
and conservatively preserves facing wall order rather than permitting interlocks.
See docs/references/filtered-wall-spacing.md and the owning design for limits.

Bezier parsing, derivative roots and polynomial primitives are imported from
estimator.py, whose George Williams / FontForge BSD attribution remains there.
Its floored bands, cached root traversal and weighted estimator are not used.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import math
from typing import Mapping

from estimator import (Bounds, GeometryError, UnsupportedGeometry, WorkLimitExceeded,
                       _coefficients, _evaluate, _finite, _roots, _segments)


MAX_SAMPLES = 8192
MAX_SCANLINE_VISITS = 2_000_000
MAX_BITMAP_PIXELS = 2_000_000
POLICY = "hu-midpoint-45-walls-v1"


@dataclass(frozen=True)
class Profile:
    bounds: Bounds | None
    window: tuple[float, float]
    ys: tuple[float, ...]
    left: tuple[float, ...]
    right: tuple[float, ...]
    occupied: tuple[bool, ...]
    filtered_left: tuple[float, ...]
    filtered_right: tuple[float, ...]


def _grid(window, samples_per_px):
    if not isinstance(window, (tuple, list)) or len(window) != 2:
        raise GeometryError("window must contain minimum and maximum y")
    lo, hi = (_finite(v, "window coordinate") for v in window)
    height = _finite(hi - lo, "window height")
    density = _finite(samples_per_px, "samples_per_px")
    if height <= 0 or density <= 0:
        raise GeometryError("window height and samples_per_px must be positive")
    count = math.ceil(_finite(height * density, "sample count"))
    if count > MAX_SAMPLES:
        raise WorkLimitExceeded("filtered-wall sample limit exceeded")
    dy = height / count
    ys = tuple(_finite(lo + (i + 0.5) * dy, "sample y") for i in range(count))
    if any(a >= b for a, b in zip(ys, ys[1:])) or not lo < ys[0] <= ys[-1] < hi:
        raise UnsupportedGeometry("midpoint grid is not representable at this coordinate scale")
    return (lo, hi), ys, dy


def filter_45(left, right, dy):
    """O(n) min/max unit-slope envelopes on a uniform physical-distance grid."""
    dy = _finite(dy, "sample spacing")
    if dy <= 0 or len(left) != len(right):
        raise GeometryError("wall arrays must match and sample spacing must be positive")
    if len(left) > MAX_SAMPLES:
        raise WorkLimitExceeded("filtered-wall sample limit exceeded")
    lo = [_finite(v, "left wall") for v in left]
    hi = [_finite(v, "right wall") for v in right]
    for i in range(1, len(lo)):
        lo[i] = min(lo[i], lo[i - 1] + dy)
        hi[i] = max(hi[i], hi[i - 1] - dy)
    for i in range(len(lo) - 2, -1, -1):
        lo[i] = min(lo[i], lo[i + 1] + dy)
        hi[i] = max(hi[i], hi[i + 1] - dy)
    return tuple(lo), tuple(hi)


def _profile(bounds, window, ys, dy, left, right, occupied):
    if bounds is None:
        left = [0.0] * len(ys)
        right = [0.0] * len(ys)
    else:
        for i, ink in enumerate(occupied):
            if not ink:
                # Hu's opposite bbox edge, without an invented depth constant.
                left[i], right[i] = bounds.maxx, bounds.minx
    filtered_left, filtered_right = filter_45(left, right, dy)
    return Profile(bounds, window, ys, tuple(left), tuple(right), tuple(occupied),
                   filtered_left, filtered_right)


def _source_geometry(commands, scale_px):
    scale = _finite(scale_px, "source scale")
    if scale <= 0:
        raise GeometryError("source scale must be positive")
    segments = [tuple(tuple(_finite(v * scale, "scaled coordinate") for v in p)
                      for p in points) for points in _segments(commands)]
    vertices = []
    portions = []
    for points in segments:
        ts = sorted({0.0, 1.0, *_roots(points, 0), *_roots(points, 1)})
        evaluated = [_evaluate(points, t) for t in ts]
        vertices.extend(evaluated)
        xcoef, ycoef = _coefficients(points, 0), _coefficients(points, 1)
        portions.extend((xcoef, ycoef, a, b, p, q)
                        for a, b, p, q in zip(ts, ts[1:], evaluated, evaluated[1:]))
    if not vertices:
        return None, portions
    return Bounds(min(p[0] for p in vertices), min(p[1] for p in vertices),
                  max(p[0] for p in vertices), max(p[1] for p in vertices)), portions


def source_bounds(commands, scale_px=1.0):
    """Exact derivative-extremum bounds of finite line/quadratic/cubic paths."""
    return _source_geometry(commands, scale_px)[0]


def _horner(coef, t):
    a, b, c, d = coef
    return ((a * t + b) * t + c) * t + d


def _intersection(xcoef, ycoef, lo, hi, p, q, y):
    if y == p[1]:
        return p[0]
    if y == q[1]:
        return q[0]
    if ycoef[0] == 0 and ycoef[1] == 0:
        return _finite(_horner(xcoef, (y - ycoef[3]) / ycoef[2]), "intersection x")
    increasing = q[1] > p[1]
    # No FontForge endpoint epsilon or previous-band state. Binary bisection
    # terminates when no representable parameter remains between the bounds.
    for _ in range(1100):
        t = lo + (hi - lo) / 2
        if t == lo or t == hi:
            return _finite(_horner(xcoef, t), "intersection x")
        value = _horner(ycoef, t)
        if value == y:
            return _finite(_horner(xcoef, t), "intersection x")
        if (value < y) == increasing:
            lo = t
        else:
            hi = t
    raise WorkLimitExceeded("filtered-wall root iteration limit exceeded")


def source_profile(commands, scale_px, window, samples_per_px=64):
    window, ys, dy = _grid(window, samples_per_px)
    return _sample_source_profile(commands, scale_px, window, ys, dy)


def _sample_source_profile(commands, scale_px, window, ys, dy):
    """Sample an already validated grid, preserving its phase when extended.

    Full-outline construction extends a body grid by whole sample intervals.
    Recomputing its density from enlarged bounds can change ceil() and phase
    through floating-point arithmetic, so both consumers share this sampler.
    """
    bounds, portions = _source_geometry(commands, scale_px)
    left, right = [math.inf] * len(ys), [-math.inf] * len(ys)
    occupied = [False] * len(ys)
    visits = 0
    for xcoef, ycoef, ta, tb, p, q in portions:
        ymin, ymax = sorted((p[1], q[1]))
        start, end = bisect_left(ys, ymin), bisect_right(ys, ymax)
        visits += end - start
        if visits > MAX_SCANLINE_VISITS:
            raise WorkLimitExceeded("filtered-wall scanline evaluation limit exceeded")
        for i in range(start, end):
            if ymin == ymax:
                xs = (p[0], q[0])
            else:
                xs = (_intersection(xcoef, ycoef, ta, tb, p, q, ys[i]),)
            left[i], right[i] = min(left[i], *xs), max(right[i], *xs)
            occupied[i] = True
    return _profile(bounds, window, ys, dy, left, right, occupied)


def _bitmap_rows(bitmap):
    if not isinstance(bitmap, Mapping):
        raise GeometryError("bitmap must be a dictionary")
    try:
        width, height = bitmap["width"], bitmap["height"]
        left, top, pixels = bitmap["left"], bitmap["top"], bitmap["pixels"]
    except KeyError as error:
        raise GeometryError(f"missing bitmap field {error.args[0]}") from error
    if any(type(v) is not int or v < 0 for v in (width, height)):
        raise GeometryError("bitmap dimensions must be nonnegative integers")
    if width * height > MAX_BITMAP_PIXELS:
        raise WorkLimitExceeded("filtered-wall bitmap pixel limit exceeded")
    if any(type(v) is not int for v in (left, top)):
        raise GeometryError("bitmap offsets must be integers")
    _finite(left, "bitmap left")
    _finite(top, "bitmap top")
    if not isinstance(pixels, (tuple, list)) or len(pixels) != width * height:
        raise GeometryError("bitmap pixel count must match dimensions")
    if any(type(p) is not int or p not in (0, 1) for p in pixels):
        raise GeometryError("bitmap pixels must be binary integers")
    rows = {}
    if width:
        for row in range(height):
            ink = [col for col in range(width) if pixels[row * width + col]]
            if ink:
                rows[top + row] = (left + ink[0], left + ink[-1] + 1)
    return rows


def bitmap_profile(bitmap, window, samples_per_px=64):
    window, ys, dy = _grid(window, samples_per_px)
    rows = _bitmap_rows(bitmap)
    bounds = (Bounds(min(v[0] for v in rows.values()), -max(rows) - 1,
                     max(v[1] for v in rows.values()), -min(rows)) if rows else None)
    left, right, occupied = [], [], []
    for y in ys:
        # A full cell spans [-row-1,-row]. At boundaries include both closed
        # adjacent rows, mirroring source contour intersections. Such samples
        # have measure zero in the continuous integral.
        candidates = [rows[r] for r in {math.floor(-y), math.ceil(-y) - 1} if r in rows]
        occupied.append(bool(candidates))
        left.append(min((v[0] for v in candidates), default=0.0))
        right.append(max((v[1] for v in candidates), default=0.0))
    return _profile(bounds, window, ys, dy, left, right, occupied)


def _compatible(left, right):
    if left.window != right.window or left.ys != right.ys:
        raise GeometryError("pair profiles must use the same window and midpoint grid")


def pair_offset(left, right):
    """Mean facing-wall gap at zero origin step; add d for translated gap."""
    _compatible(left, right)
    if left.bounds is None or right.bounds is None:
        raise GeometryError("pair offset requires nonempty geometry")
    return _finite(math.fsum(b - a for a, b in
                            zip(left.filtered_right, right.filtered_left)) / len(left.ys),
                   "pair mean gap")


def shared_ink_rows(left, right):
    """Number of common occupied midpoint samples before concavity filtering."""
    _compatible(left, right)
    return sum(a and b for a, b in zip(left.occupied, right.occupied))


def clearance_min_step(left_bitmap, right_bitmap):
    """Conservative integer step excluding all closed-cell face/corner touches.

    For row pairs within one baseline row, require translated right glyph's
    left edge strictly beyond the left glyph's right edge. Integer cell edges
    make the least allowed step max(right_A-left_B)+1. No shared nearby rows
    yields None. Holes/interlocking placements can make this bound conservative.
    """
    left, right = _bitmap_rows(left_bitmap), _bitmap_rows(right_bitmap)
    differences = [r - right[other][0]
                   for row, (_, r) in left.items()
                   for other in (row - 1, row, row + 1) if other in right]
    return max(differences) + 1 if differences else None


def clearance_min_step_no_overlap(left_bitmap, right_bitmap):
    """Least step preserving ink order on shared rows, allowing cell contact.

    Occupied-cell interiors cannot overlap when the right glyph starts at or
    beyond the left glyph's right cell edge on every shared row. Face and
    corner contact, including contact across adjacent rows, are permitted.
    This monotonic bound intentionally excludes placing ink inside a counter;
    it is not an enumeration of every disjoint placement. See the owning
    design's touching-clearance adaptation of Hu's MinSpace safeguard.
    """
    left, right = _bitmap_rows(left_bitmap), _bitmap_rows(right_bitmap)
    differences = [edge - right[row][0] for row, (_, edge) in left.items() if row in right]
    return max(differences) if differences else None
