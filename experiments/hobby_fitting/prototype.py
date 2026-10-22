"""Isolated Hobby residual experiment; no font loading or renderer integration.

Equation numbers refer to the stored CSTR copy. See docs/hobby-fitting.md and the paper's
audit.md for verified sources, version differences and deliberate omissions.
"""

from dataclasses import dataclass
import json
import math

import numpy as np


@dataclass(frozen=True)
class Sample:
    """A supplied, fixed affine correspondence to outline control points."""

    terms: tuple

    @staticmethod
    def vertex(index):
        return Sample(((index, 1.0),))

    @staticmethod
    def cubic(indices, t):
        if len(indices) != 4 or not 0 <= t <= 1:
            raise ValueError("a cubic needs four indices and t in [0,1]")
        # Hobby (31): this basis stays fixed while the control points move.
        return Sample(tuple(zip(indices, ((1-t)**3, 3*t*(1-t)**2,
                                          3*t*t*(1-t), t**3))))


@dataclass
class Pair:
    a: Sample
    b: Sample
    normal: np.ndarray
    tangent: np.ndarray
    width: float
    length: float
    kind: str
    error: np.ndarray
    chord: np.ndarray


class System:
    """Linear weighted residuals in displacements, at nominal scale one.

    The caller supplies all correspondences, black/white roles, pairings,
    integer offsets and frozen vertices. No recognition or integer search.
    """

    def __init__(self, points, height):
        self.points = np.asarray(points, dtype=float)
        if (self.points.ndim != 2 or self.points.shape[1] != 2
                or not len(self.points) or not np.isfinite(self.points).all()
                or not math.isfinite(height) or height <= 0):
            raise ValueError("finite Nx2 points and positive height required")
        self.height = height
        self.rows = []

    def basis(self, sample):
        row = np.zeros(len(self.points))
        for index, weight in sample.terms:
            if not 0 <= index < len(row) or not math.isfinite(weight):
                raise ValueError("invalid sample correspondence")
            row[index] += weight
        if not np.isclose(row.sum(), 1.0, atol=1e-12, rtol=0):
            raise ValueError("correspondence weights must sum to one")
        return row

    def point(self, sample):
        return self.basis(sample) @ self.points

    def projected(self, a, direction, b=None):
        basis = self.basis(a)
        if b is not None:
            basis = basis - self.basis(b)
        return np.outer(basis, direction).ravel()

    def add(self, group, row, constant=0.0):
        if not np.isfinite(row).all() or not math.isfinite(constant):
            raise ValueError("nonfinite residual")
        self.rows.append((group, row, constant))

    def edge(self, i, j):
        """Hobby (1)-(3), with directions/lengths from input geometry."""
        a, b = Sample.vertex(i), Sample.vertex(j)
        delta = self.point(b) - self.point(a)
        length = np.linalg.norm(delta)
        if length <= 0:
            raise ValueError("zero-length edge")
        tangent = delta / length
        normal = np.array([-tangent[1], tangent[0]])
        ri, rj = self.projected(a, normal), self.projected(b, normal)
        alpha1 = 1000 / self.height**3
        self.add("position", (ri+rj) * math.sqrt(alpha1*length/4))
        self.add("position", (rj-ri) * math.sqrt(alpha1*length/12))
        scale = math.sqrt(25*length/self.height) / length
        self.add("stretch", self.projected(b, tangent, a) * scale)
        self.add("bend", (rj-ri) * scale)

    def curve(self, indices, intervals=16, shape=True):
        """Hobby (31)-(33), with frozen original tangents and midpoint ds.

        Midpoint speed/k approximates arc length. This is explicit quadrature,
        not the paper's adaptive polygon-error feature-recognition algorithm.
        See audit.md for why freezing coefficients is required for linearity.
        """
        if len(indices) != 4 or not isinstance(intervals, int) or intervals < 1:
            raise ValueError("four controls and positive integer intervals required")
        controls = np.array([self.point(Sample.vertex(i)) for i in indices])
        for j in range(intervals):
            t = (j + 0.5) / intervals
            derivative = 3 * (np.array([(1-t)**2, 2*t*(1-t), t*t])
                              @ np.diff(controls, axis=0))
            speed = np.linalg.norm(derivative)
            if speed <= 0:
                raise ValueError("zero curve tangent")
            normal = np.array([derivative[1], -derivative[0]]) / speed
            row = self.projected(Sample.cubic(indices, t), normal)
            self.add("curve-position", row * math.sqrt(
                1000 / self.height**3 * speed / intervals))
            if shape:
                # Project adaptation of Hobby (2),(3) through §6's linear
                # control-point representation: replace an edge vector by
                # the local derivative and integrate strain with frozen ds.
                # This prevents normal-only fitting from hiding large
                # tangential changes. It is not a full curvature constraint.
                weights = np.array([-3*(1-t)**2,
                                    3*(1-t)**2-6*t*(1-t),
                                    6*t*(1-t)-3*t*t, 3*t*t])
                basis = sum((weight*self.basis(Sample.vertex(i))
                             for weight, i in zip(weights, indices)),
                            np.zeros(len(self.points)))
                factor = math.sqrt(25/self.height*speed/intervals)/speed
                self.add("curve-stretch", np.outer(basis, derivative/speed).ravel()*factor)
                self.add("curve-bend", np.outer(basis, normal).ravel()*factor)

    def pair(self, a, b, length, kind="ink", medial=None):
        """Hobby (4),(5): input contacts, medial point and arc-length weight.

        Omitted medial point means the explicit synthetic midpoint case only.
        In real features width is twice the radius, not necessarily |A-B|.
        """
        if kind not in ("ink", "white") or not math.isfinite(length) or length <= 0:
            raise ValueError("positive arc length and ink/white role required")
        pa, pb = self.point(a), self.point(b)
        chord = pa - pb
        distance = np.linalg.norm(chord)
        if distance <= 0:
            raise ValueError("coincident contacts")
        medial = (pa+pb)/2 if medial is None else np.asarray(medial, dtype=float)
        if medial.shape != (2,) or not np.isfinite(medial).all():
            raise ValueError("finite medial point required")
        width = 2*np.linalg.norm(pa-medial)
        if width <= 0 or not np.isclose(width, 2*np.linalg.norm(pb-medial),
                                       rtol=1e-10, atol=1e-12):
            raise ValueError("contacts need equal positive medial radii")
        normal = chord / distance
        tangent = np.array([-normal[1], normal[0]])
        error = -self.projected(a, normal, b) / width
        return Pair(a, b, normal, tangent, width, length, kind, error, chord)

    def preserve_width(self, pair):
        # Hobby (5), applicable to supplied white-space features as in §3.2.
        self.add(pair.kind+"-width", pair.error * math.sqrt(
            50 / self.height * pair.length))

    def match_width(self, first, second, width_scale=0.7):
        if first.kind != second.kind:
            raise ValueError("black/white matching requires an explicit separate model")
        # Hobby (17); the printed 9 is radians, not degrees. No retuned gate.
        weight = width_weight(first.width, second.width, first.tangent,
                              second.tangent, self.height, width_scale)
        self.add(first.kind+"-match", (first.error-second.error) * math.sqrt(
            first.length*second.length*weight))

    def offset(self, pair, integer_offset):
        """Hobby (11)-(13), fixed caller-supplied I; finite source weights.

        With A-B pointing along normal, I approximates B-A (the plus sign
        in (11)). The (13) term is constant for supplied I; a real integer
        search must consider it when comparing offset choices.
        """
        offset = np.asarray(integer_offset, dtype=float)
        if (offset.shape != (2,) or not np.isfinite(offset).all()
                or not np.equal(offset, np.rint(offset)).all()):
            raise ValueError("two integer offset components required")
        normal = pair.normal
        factor = math.sqrt(2e8 / self.height**3 * pair.length)
        self.add("offset-width", self.projected(pair.a, normal, pair.b)*factor,
                 np.dot(normal, pair.chord+offset)*factor)
        perpendicular = np.array([normal[1], -normal[0]])
        factor = math.sqrt(2e6 / self.height**3 * pair.length)
        self.add("offset-direction", self.projected(pair.a, perpendicular, pair.b)*factor,
                 np.dot(perpendicular, pair.chord)*factor)
        constant = (math.sqrt(20/self.height*pair.length)
                    * np.dot(normal, [offset[1], -offset[0]]) / pair.width**2)
        self.add("offset-obliquity", np.zeros(self.points.size), constant)

    def solve(self, frozen=(), fixed_displacements=None):
        """SVD least squares in free displacements; frozen controls stay exact.

        fixed_displacements maps a vertex to its known (dx, dy): the
        variable is eliminated and its matrix contribution joins the
        constants. Coefficients stay fixed per the linearity requirement.
        No arbitrary regularization or acceptance score. Rank deficiency is
        reported; NumPy returns the minimum-norm solution in free modes.
        """
        frozen = set(frozen)
        if any(not isinstance(i, int) or not 0 <= i < len(self.points) for i in frozen):
            raise ValueError("invalid frozen control")
        fixed = {int(i): (float(v[0]), float(v[1]))
                 for i, v in dict(fixed_displacements or {}).items()}
        if any(not 0 <= i < len(self.points) for i in fixed):
            raise ValueError("invalid fixed control")
        if any(not (math.isfinite(dx) and math.isfinite(dy))
               for dx, dy in fixed.values()):
            raise ValueError("nonfinite fixed displacement")
        if set(fixed) & frozen:
            raise ValueError("control cannot be frozen and fixed")
        if not self.rows:
            raise ValueError("no residuals")
        matrix = np.array([row for _, row, _ in self.rows])
        constants = np.array([c for _, _, c in self.rows])
        fixed_cols = np.array([2*i+c for i in fixed for c in (0, 1)],
                              dtype=int)
        fixed_vals = np.array([v[c] for v in
                               [fixed[i] for i in fixed] for c in (0, 1)])
        if len(fixed_cols):
            constants = constants + matrix[:, fixed_cols] @ fixed_vals
        free = np.array([2*i+c for i in range(len(self.points))
                         if i not in frozen and i not in fixed
                         for c in (0, 1)], dtype=int)
        delta = np.zeros(self.points.size)
        for i, (dx, dy) in fixed.items():
            delta[2*i], delta[2*i+1] = dx, dy
        if len(free):
            delta[free], _, rank, singular = np.linalg.lstsq(
                matrix[:, free], -constants, rcond=None)
            condition = (float(singular[0]/singular[-1])
                         if rank == len(free) else None)
        else:
            rank, condition = 0, None
        residuals = matrix @ delta + constants
        costs = {}
        for (group, _, _), value in zip(self.rows, residuals):
            costs[group] = costs.get(group, 0.0) + float(value*value)
        return {"points": self.points + delta.reshape(-1, 2),
                "delta": delta, "rank": int(rank), "free_variables": len(free),
                "condition": condition, "squared_residuals": costs,
                "max_movement": float(np.linalg.norm(delta.reshape(-1, 2), axis=1).max())}


def width_weight(w1, w2, tangent1, tangent2, height, width_scale=0.7):
    if min(w1, w2, height, width_scale) <= 0 or not all(
            math.isfinite(v) for v in (w1, w2, height, width_scale)):
        raise ValueError("positive finite widths, height and width scale required")
    vectors = [np.asarray(t, dtype=float) for t in (tangent1, tangent2)]
    if any(t.shape != (2,) or not np.isfinite(t).all()
           or np.linalg.norm(t) <= 0 for t in vectors):
        raise ValueError("finite nonzero directions required")
    cosine = np.dot(*vectors) / np.prod([np.linalg.norm(t) for t in vectors])
    angle = math.acos(float(np.clip(cosine, -1, 1)))
    return 500/height**2 * math.exp(-((w1-w2)/width_scale)**2 - (angle/9)**2)


def strip_area(normal, low, high, x, y, size=1.0):
    """Exact square/infinite-strip intersection by half-plane clipping.

    Sutherland-Hodgman clipping against two strip half-planes; see README.md.
    Analytic control, not Zeno coverage: no curves, winding overlaps or dropout.
    Coordinates are shifted into the cell to keep shoelace arithmetic stable.
    """
    normal = np.asarray(normal, dtype=float)
    if (normal.shape != (2,) or not np.isfinite(normal).all()
            or np.linalg.norm(normal) <= 0 or not all(
                math.isfinite(v) for v in (low, high, x, y, size))
            or high < low or size <= 0):
        raise ValueError("valid finite strip and cell required")
    origin = np.dot(normal, [x, y])
    polygon = [np.array(p, dtype=float) for p in ((0, 0), (size, 0),
                                                (size, size), (0, size))]
    for direction, bound in ((normal, high-origin), (-normal, origin-low)):
        clipped = []
        for a, b in zip(polygon, polygon[1:]+polygon[:1]):
            da, db = np.dot(direction, a)-bound, np.dot(direction, b)-bound
            if da <= 0:
                clipped.append(a)
            if (da <= 0) != (db <= 0):
                clipped.append(a + da/(da-db)*(b-a))
        polygon = clipped
    return abs(sum(a[0]*b[1]-a[1]*b[0]
                   for a, b in zip(polygon, polygon[1:]+polygon[:1]))) / 2


def strip_pixel(normal, low, high, x, y):
    center = low <= np.dot(normal, [x+0.5, y+0.5]) < high
    area = strip_area(normal, low, high, x, y)
    # Same reduction arithmetic as generator/overlap.rs, but exact clipped
    # subcell areas rounded to 8 bits replace the Zeno sample values.
    samples = [min(255, math.floor(255*16*strip_area(
        normal, low, high, x+dx/4, y+dy/4, 0.25)+0.5))
        for dy in range(4) for dx in range(4)]
    reduced = min(255, sum((sample+8)//16 for sample in samples))
    return {"center_fill": bool(center), "area": area,
            "exact_area_threshold": bool(255*area >= 128),
            "analytic_4x_coverage": reduced, "analytic_4x_ink": reduced >= 128}


def straight_demo(angle):
    # Same supplied geometry/offset transformed through arbitrary orientation.
    normal = np.array([math.cos(angle), math.sin(angle)])
    tangent = np.array([-normal[1], normal[0]])
    points = [normal*x+tangent*y for x in (0, 1.265625, 3, 4.265625)
              for y in (0, 8)]
    system = System(points, 14)
    for i in (0, 2, 4, 6):
        system.edge(i, i+1)
    a = system.pair(Sample.vertex(2), Sample.vertex(0), 8)
    b = system.pair(Sample.vertex(6), Sample.vertex(4), 8)
    for pair in (a, b):
        system.preserve_width(pair)
    system.match_width(a, b)
    # Integer components stay in the absolute grid, never rotate a supplied I.
    offset = (-1, 0) if angle == 0 else (-1, -1)
    system.offset(a, offset)
    result = system.solve()
    result.pop("points")
    delta = result.pop("delta")
    result["projected_widths"] = [p.width*(1+float(-p.error@delta)) for p in (a, b)]
    result["supplied_offset"] = offset
    return result


def curved_system(shape=True):
    # Two quarter-circle cubic approximations, concentric by construction.
    # Supplied radial correspondences approximate medial contacts; no claim
    # that equal-t contacts are exact nearest points on arbitrary font curves.
    kappa = 4*(math.sqrt(2)-1)/3
    arc = np.array([(1, 0), (1, kappa), (kappa, 1), (0, 1)])
    system = System(np.vstack((4*arc, 2.734375*arc)), 14)
    system.curve(range(4), shape=shape)
    system.curve(range(4, 8), shape=shape)
    pairs = [system.pair(Sample.cubic(range(4), t),
                         Sample.cubic(range(4, 8), t), math.pi/8)
             for t in (0.125, 0.375, 0.625, 0.875)]
    for pair in pairs:
        system.preserve_width(pair)
    for first, second in zip(pairs, pairs[1:]):
        system.match_width(first, second)
    # Local supplied axis-aligned integer offset near the bottom of the arc.
    # The finite (12) term penalizes changing the radial chord's direction.
    system.offset(pairs[0], (-1, 0))
    return system, pairs


def counter_system():
    # Two closed square contours; shared vertices are single variables.
    # White-space features are explicit, never automatically inferred ink.
    system = System([(-3, -3), (3, -3), (3, 3), (-3, 3),
                     (-1.8, -1.8), (1.8, -1.8), (1.8, 1.8), (-1.8, 1.8)], 14)
    for start in (0, 4):
        for i in range(4):
            system.edge(start+i, start+(i+1) % 4)
    mids = [Sample(((i, 0.5), (j, 0.5)))
            for i, j in ((0, 3), (1, 2), (4, 7), (5, 6))]
    left = system.pair(mids[2], mids[0], 3.6)
    right = system.pair(mids[1], mids[3], 3.6)
    white = system.pair(mids[3], mids[2], 3.6, "white")
    for pair in (left, right, white):
        system.preserve_width(pair)
    system.match_width(left, right)
    system.offset(left, (-1, 0))
    system.offset(right, (-1, 0))
    return system, [left, right, white]


def summarized(system, pairs, frozen=()):
    result = system.solve(frozen)
    result.pop("points")
    delta = result.pop("delta")
    result["features"] = [
        {"kind": p.kind, "source_width": p.width,
         "relative_error": float(p.error@delta),
         "projected_width": float(np.dot(p.normal, p.chord)-p.width*(p.error@delta))}
        for p in pairs]
    return result


def main():
    report = {"scope": "synthetic supplied correspondences; no production renderer change",
              "straight": {str(a): straight_demo(math.radians(a)) for a in (0, 30, 45)},
              "curved": summarized(*curved_system()),
              "curved_normal_only_negative_control": summarized(*curved_system(shape=False)),
              "counter": summarized(*counter_system()),
              "orthogonal_matching_weight_ratio": width_weight(
                  1, 1, (1, 0), (0, 1), 14) / width_weight(1, 1, (1, 0), (1, 0), 14),
              "integer_width_half_phase_control": [strip_pixel((1, 0), 0.5, 1.5, x, 0)
                                                   for x in range(2)]}
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
