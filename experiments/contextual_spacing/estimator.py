# Portions adapted from FontForge's aw2_findedges/IterateSplineSolve:
# Copyright (C) 2009-2012 by George Williams
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# The name of the author may not be used to endorse or promote products
# derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Isolated FontForge AutoWidth-style outline separation, in design units.

Reference: FontForge c41bdb922285f35defd1e1385adfd13bde1ab32a,
fontforge/autowidth2.c, aw2_findedges and aw2_bbox_separation. Geometry is a
project adapter: command curves are split at x/y derivative roots, then native
cached-parameter traversal measures each closed band. A portion finished at a
boundary restarts from its minimum when the next band touches its maximum,
matching the source even at internal maxima. No curve flattening or pixel-space
flooring is used. Native comparison pins separate binary64 operations with
-ffp-contract=off -fno-fast-math, rather than default compiler contraction.
Native AutoWidth/AutoKern select integer chunk_height = em / 100 or em / 200.
This adapter therefore uses floor(em_size / subdivisions), not fractional
bands. Noninteger em_size is an explicit project extension using the same floor;
native fonts express the em as the integer ascent-plus-descent sum.

analyze(commands, em_size, subdivisions=100) accepts FittedCommand dictionaries
with op move_to/line_to/quad_to/curve_to/close and x/y/x1/y1/x2/y2 as applicable.
Extra diagnostic fields (such as *_bits) are ignored. Coordinates must already
be in design units on a common baseline. For produced pixel coordinates callers
must explicitly apply em_size / size_px first; that is a project adaptation.

separation(left, right, em_size) returns integer-design-unit separation at
adjacent tight bounding boxes, or reason='no_shared_bands'. Python round uses
ties to even, matching C rint under its default FE_TONEAREST mode. Unit flooring
means arbitrary uniform scaling need not preserve the integer result exactly.
"""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


class GeometryError(ValueError):
    """Invalid or nonfinite geometry/settings."""


class WorkLimitExceeded(GeometryError):
    """The declared isolated-experiment work budget was exceeded."""


class UnsupportedGeometry(GeometryError):
    """Geometry cannot be represented by the reference's short edge arrays."""


@dataclass(frozen=True)
class Bounds:
    minx: float
    miny: float
    maxx: float
    maxy: float


@dataclass(frozen=True)
class Band:
    index: int
    left: int | None
    right: int | None


@dataclass(frozen=True)
class Envelope:
    bounds: Bounds | None
    band_height: int
    imin_y: int
    imax_y: int
    bands: tuple[Band, ...]
    em_size: float
    subdivisions: int


@dataclass(frozen=True)
class Separation:
    estimate: int | None
    shared_bands: int
    reason: str | None = None


# Solver limits are fixed experiment configuration, not fitted glyph heuristics.
MAX_COMMANDS = 100_000
MAX_BANDS = 20_000
MAX_BAND_VISITS = 2_000_000


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GeometryError(f"{label} must be a finite number")
    try:
        result = float(value)
    except OverflowError as error:
        raise GeometryError(f"{label} must be finite") from error
    if not math.isfinite(result):
        raise GeometryError(f"{label} must be finite")
    return result


def _point(command, suffix=""):
    try:
        return (_finite(command["x" + suffix], "x" + suffix),
                _finite(command["y" + suffix], "y" + suffix))
    except KeyError as error:
        raise GeometryError(f"missing coordinate {error.args[0]}") from error


def _segments(commands):
    current = start = None
    result = []
    for count, command in enumerate(commands, 1):
        if count > MAX_COMMANDS:
            raise WorkLimitExceeded("command limit exceeded")
        if not isinstance(command, Mapping):
            raise GeometryError("command must be a dictionary")
        op = command.get("op")
        if op == "move_to":
            current = start = _point(command)
        elif op == "close":
            if current is None or start is None:
                raise GeometryError("close requires an active contour")
            if current != start:
                result.append((current, start))
            current = start
        elif op in ("line_to", "quad_to", "curve_to"):
            if current is None:
                raise GeometryError(f"{op} requires move_to")
            end = _point(command)
            controls = ()
            if op != "line_to":
                controls = (_point(command, "1"),)
            if op == "curve_to":
                controls += (_point(command, "2"),)
            result.append((current, *controls, end))
            current = end
        else:
            raise GeometryError(f"unsupported command {op!r}")
    return result


def _evaluate(points, t):
    if t == 0:
        return points[0]
    if t == 1:
        return points[-1]
    values = points
    while len(values) > 1:
        values = tuple(tuple(_finite((1 - t) * a + t * b, "curve evaluation")
                             for a, b in zip(p, q))
                       for p, q in zip(values, values[1:]))
    return values[0]


def _roots(points, axis):
    """Interior derivative roots; Bernstein differences avoid absolute offsets."""
    p = [v[axis] for v in points]
    differences = [_finite(b - a, "curve derivative") for a, b in zip(p, p[1:])]
    if len(differences) == 1:
        return ()
    if len(differences) == 2:
        scale = max(map(abs, differences))
        if scale == 0:
            return ()
        c, end = (d / scale for d in differences)
        a = end - c
        roots = () if a == 0 else (-c / a,)
    else:
        # Scale before forming the quadratic to avoid squaring large coordinates.
        scale = max(map(abs, differences))
        if scale == 0:
            return ()
        c, mid, end = (d / scale for d in differences)
        b = 2 * (mid - c)
        a = c - 2 * mid + end
        if a == 0:
            roots = () if b == 0 else (-c / b,)
        else:
            discriminant = b * b - 4 * a * c
            if discriminant < 0:
                return ()
            q = -0.5 * (b + math.copysign(math.sqrt(discriminant), b))
            roots = (-b / (2 * a),) if q == 0 else (q / a, c / q)
    return tuple(t for t in roots if math.isfinite(t) and 0 < t < 1)


def _coefficients(points, axis):
    """Power basis, in the operation order of native SplineRefigure2/3."""
    p = [point[axis] for point in points]
    d = p[0]
    if len(p) == 2:
        a, b, c = 0.0, 0.0, p[1] - d
    elif len(p) == 3:
        c = 2 * (p[1] - d)
        a, b = 0.0, p[2] - d - c
    else:
        c = 3 * (p[1] - d)
        b = 3 * (p[2] - p[1]) - c
        a = p[3] - d - c - b
    return tuple(_finite(v, "spline coefficient") for v in (a, b, c, d))


def _polynomial(coefficients, t):
    a, b, c, d = coefficients
    return _finite(((a * t + b) * t + c) * t + d, "polynomial evaluation")


def _solve(coefficients, lo, hi, target):
    """Pinned IterateSplineSolve, including its sourced .0001 endpoint rule."""
    a, b, c, d = coefficients
    coefficients = (a, b, c, _finite(d - target, "solver target"))
    if a == 0 and b == 0 and c != 0:
        t = -coefficients[3] / c
        return t if lo <= t <= hi else -1.0
    low, high = _polynomial(coefficients, lo), _polynomial(coefficients, hi)
    if low == 0:
        return lo
    if high == 0:
        return hi
    if (low < 0 < high) or (high < 0 < low):
        # Native loops until adjacent binary64 values. 1,100 bisections bound
        # the entire binary64 exponent range and make work limits explicit.
        for _ in range(1100):
            t = (hi + lo) / 2
            if t == lo or t == hi:
                return t
            test = _polynomial(coefficients, t)
            if test == 0:
                return t
            if (low < 0 and test < 0) or (low > 0 and test > 0):
                lo = t
            else:
                hi = t
        raise WorkLimitExceeded("native root solver iteration limit exceeded")
    if -0.0001 < low < 0.0001:
        return lo
    if -0.0001 < high < 0.0001:
        return hi
    return -1.0


def analyze(commands: Sequence[Mapping], em_size: float,
            subdivisions: int = 100) -> Envelope:
    """Analyze finite line/quadratic/cubic commands without changing geometry.

    Bands are indexed from floor(miny / band_height) through ceil(maxy /
    band_height), inclusive, exactly as the reference edge allocation. The
    estimator excludes the upper loop band. Empty bands have None edges. Edge
    evaluation retains native cached-parameter restarts on touching boundaries.
    band_height is the positive integer floor(em_size / subdivisions), matching
    native positive integer chunk_height division. Noninteger em_size inputs
    extend that rule explicitly and do not claim native input parity.
    """
    em_size = _finite(em_size, "em_size")
    if em_size <= 0:
        raise GeometryError("em_size must be positive")
    if isinstance(subdivisions, bool) or not isinstance(subdivisions, int) or subdivisions <= 0:
        raise GeometryError("subdivisions must be a positive integer")
    try:
        band_height = math.floor(em_size / subdivisions)
    except OverflowError as error:
        raise GeometryError("subdivisions exceeds floating-point range") from error
    if band_height <= 0:
        raise GeometryError("integer band height must be positive")
    segments = _segments(commands)
    # Keep the supplied coordinate origin: native Horner arithmetic precedes
    # integer flooring, so recentering could change an edge by one design unit.
    origin_x = origin_y = 0.0
    portions = []
    coordinates = []
    for points in segments:
        ts = sorted({0.0, 1.0, *_roots(points, 0), *_roots(points, 1)})
        vertices = [_evaluate(points, t) for t in ts]
        coordinates.extend(vertices)
        portions.extend((points, a, b, p, q)
                        for a, b, p, q in zip(ts, ts[1:], vertices, vertices[1:])
                        if p[1] != q[1])
    if not coordinates:
        return Envelope(None, band_height, 0, -1, (), em_size, subdivisions)
    local = Bounds(min(p[0] for p in coordinates), min(p[1] for p in coordinates),
                   max(p[0] for p in coordinates), max(p[1] for p in coordinates))
    bounds = Bounds(_finite(local.minx + origin_x, "minimum x"),
                    _finite(local.miny + origin_y, "minimum y"),
                    _finite(local.maxx + origin_x, "maximum x"),
                    _finite(local.maxy + origin_y, "maximum y"))
    imin = math.floor(_finite(bounds.miny / band_height, "minimum band index"))
    imax = math.ceil(_finite(bounds.maxy / band_height, "maximum band index"))
    if imax - imin + 1 > MAX_BANDS:
        raise WorkLimitExceeded("band count limit exceeded")
    # Store absolute geometric extrema until all portions have contributed.
    left = [math.inf] * (imax - imin + 1)
    right = [-math.inf] * len(left)
    visits = 0
    for points, ta, tb, p, q in portions:
        xcoeff = _coefficients(points, 0)
        ycoeff = _coefficients(points, 1)
        ymin, ymax = sorted((p[1], q[1]))
        # Closed intervals include the band immediately below a boundary.
        first = max(imin, math.ceil((ymin + origin_y) / band_height) - 1)
        last = min(imax, math.floor((ymax + origin_y) / band_height))
        visits += last - first + 1
        if visits > MAX_BAND_VISITS:
            raise WorkLimitExceeded("band evaluation limit exceeded")
        previous = -1.0
        initial = imin * band_height - origin_y
        if ymin <= initial:
            previous = _solve(ycoeff, ta, tb, initial)
        increasing = q[1] > p[1]

        def find_y(target, old=-1.0):
            lo, hi = ta, tb
            if old != -1.0:
                if increasing:
                    lo = old
                else:
                    hi = old
            return _solve(ycoeff, lo, hi, target)

        for index in range(first, last + 1):
            bottom = _finite(index * band_height - origin_y, "band boundary")
            top = _finite(bottom + band_height, "band boundary")
            if ymax < bottom or ymin > top:
                continue
            # Native cached-parameter traversal deliberately restarts at miny
            # after finishing a portion. A following band touching its maxy
            # therefore sees the full portion, including at internal maxima.
            # This is source behavior, not an epsilon or glyph-specific rule.
            t = previous if previous != -1.0 else find_y(ymin)
            xs = [] if t == -1.0 else [_polynomial(xcoeff, t)]
            if top < ymax:
                t = previous = find_y(top, t)
            else:
                previous = -1.0
                t = find_y(ymax, t)
            if t != -1.0:
                xs.append(_polynomial(xcoeff, t))
            if not xs:
                continue
            slot = index - imin
            left[slot] = min(left[slot], *xs)
            right[slot] = max(right[slot], *xs)
    bands = []
    for slot, (a, b) in enumerate(zip(left, right)):
        if math.isinf(a):
            bands.append(Band(slot + imin, None, None))
            continue
        l = math.floor(_finite(a - local.minx, "left edge offset"))
        r = math.floor(_finite(b - local.maxx, "right edge offset"))
        if not (-32766 <= l <= 32766 and -32766 <= r <= 32766):
            raise UnsupportedGeometry("edge offset exceeds native short/sentinel range")
        bands.append(Band(slot + imin, l, r))
    return Envelope(bounds, band_height, imin, imax, tuple(bands), em_size, subdivisions)


def separation(left: Envelope, right: Envelope, em_size: float) -> Separation:
    """FontForge weighted adjacent-box separation, with explicit abstention.

    The reference returns zero for missing bands. This adapter returns None and
    no_shared_bands so the resolver can retain metric placement deliberately.
    """
    em_size = _finite(em_size, "em_size")
    if em_size <= 0 or left.em_size != em_size or right.em_size != em_size:
        raise GeometryError("envelopes must use the requested positive em_size")
    if left.subdivisions != right.subdivisions or left.band_height != right.band_height:
        raise GeometryError("envelopes must use identical band settings")
    total = count = 0.0
    shared = 0
    denom = em_size / 50.0
    for index in range(max(left.imin_y, right.imin_y), min(left.imax_y, right.imax_y)):
        a = left.bands[index - left.imin_y].right
        b = right.bands[index - right.imin_y].left
        if a is None or b is None:
            continue
        sep = b - a
        divisor = _finite(sep + denom, "weight divisor")
        if divisor <= 0:
            raise GeometryError("weight divisor must be positive")
        weight = _finite(1.0 / divisor, "weight")
        weight = _finite(weight * weight, "squared weight")
        total = _finite(total + weight * sep, "weighted separation sum")
        count = _finite(count + weight, "weight sum")
        shared += 1
    if not shared:
        return Separation(None, 0, "no_shared_bands")
    if count == 0:
        raise GeometryError("weights underflowed")
    return Separation(round(total / count), shared)
