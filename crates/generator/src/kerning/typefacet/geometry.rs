//! TypeFacet TFSSegment/TFSPath/TFSPoint/TFSIntersection calculation, ported
//! from revision 8c6db26d0c599ece16f3704696811275120a4044 (Apache-2.0).
use super::python_round_tenth;

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct Point {
    pub x: f64,
    pub y: f64,
}
impl Point {
    pub(super) fn add(self, b: Self) -> Self {
        Self {
            x: self.x + b.x,
            y: self.y + b.y,
        }
    }
    pub(super) fn sub(self, b: Self) -> Self {
        Self {
            x: self.x - b.x,
            y: self.y - b.y,
        }
    }
    pub(super) fn scale(self, s: f64) -> Self {
        Self {
            x: self.x * s,
            y: self.y * s,
        }
    }
    pub(super) fn length(self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }
    fn normalized(self) -> Self {
        let length = self.length();
        Self {
            x: self.x / length,
            y: self.y / length,
        }
    }
    fn dot(self, b: Self) -> f64 {
        self.x * b.x + self.y * b.y
    }
    fn rounded(self) -> Self {
        Self {
            x: python_round_tenth(self.x),
            y: python_round_tenth(self.y),
        }
    }
    fn angle(self) -> f64 {
        self.y.atan2(self.x)
    }
    fn lerp(self, b: Self, t: f64) -> Self {
        Self {
            x: self.x * (1.0 - t) + b.x * t,
            y: self.y * (1.0 - t) + b.y * t,
        }
    }
    fn offset(self, radius: f64) -> Self {
        let angle = std::f64::consts::FRAC_PI_2;
        let rotated = Self {
            x: self.x * angle.cos() + (-self.y) * angle.sin(),
            y: self.y * angle.cos() + self.x * angle.sin(),
        };
        let factor = rotated.y.abs().clamp(0.0, 1.0);
        rotated.scale(radius * factor + radius * (1.0 - factor))
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum Segment {
    Line([Point; 2]),
    Quad([Point; 3]),
    Cubic([Point; 4]),
}
impl Segment {
    pub(super) fn points(&self) -> &[Point] {
        match self {
            Self::Line(p) => p,
            Self::Quad(p) => p,
            Self::Cubic(p) => p,
        }
    }
    pub(super) fn start(self) -> Point {
        self.points()[0]
    }
    pub(super) fn end(self) -> Point {
        *self.points().last().unwrap()
    }
    fn vector(self, start: bool) -> Point {
        let p = self.points();
        if start {
            for q in &p[1..] {
                let v = q.sub(p[0]);
                if v.x != 0.0 || v.y != 0.0 {
                    return v;
                }
            }
        } else {
            for q in p[..p.len() - 1].iter().rev() {
                let v = p[p.len() - 1].sub(*q);
                if v.x != 0.0 || v.y != 0.0 {
                    return v;
                }
            }
        }
        Point { x: 0.0, y: 0.0 }
    }
    fn mapped(self, f: impl Fn(Point) -> Point) -> Self {
        match self {
            Self::Line(p) => Self::Line(p.map(f)),
            Self::Quad(p) => Self::Quad(p.map(f)),
            Self::Cubic(p) => Self::Cubic(p.map(f)),
        }
    }
    pub(super) fn reverse(self) -> Self {
        match self {
            Self::Line([a, b]) => Self::Line([b, a]),
            Self::Quad([a, b, c]) => Self::Quad([c, b, a]),
            Self::Cubic([a, b, c, d]) => Self::Cubic([d, c, b, a]),
        }
    }
    pub(super) fn evaluate(self, t: f64) -> Point {
        match self {
            Self::Line([a, b]) => a.lerp(b, t),
            Self::Quad([a, b, c]) => a.lerp(b, t).lerp(b.lerp(c, t), t),
            Self::Cubic([a, b, c, d]) => a
                .lerp(b, t)
                .lerp(b.lerp(c, t), t)
                .lerp(b.lerp(c, t).lerp(c.lerp(d, t), t), t),
        }
    }
    pub(super) fn valid(self) -> bool {
        if self
            .points()
            .iter()
            .any(|p| !p.x.is_finite() || !p.y.is_finite())
            || self.start() == self.end()
        {
            return false;
        }
        if let Self::Cubic([a, b, c, d]) = self {
            if let Some(intersection) = segment_intersection(a, b, c, d) {
                if !intersection.x.is_finite() || !intersection.y.is_finite() {
                    return false;
                }
                if intersection.sub(a).length() <= self.vector(true).length() * 0.5
                    && intersection.sub(d).length() <= self.vector(false).length() * 0.5
                {
                    return false;
                }
            }
        }
        true
    }
    pub(super) fn inflated(self, radius: f64) -> Result<Option<Self>, crate::Error> {
        if self.vector(true).length() == 0.0 || self.vector(false).length() == 0.0 {
            return Err(crate::fail(
                "TypeFacet endpoint tangent cannot be normalized",
            ));
        }
        let start_tangent = self.vector(true).normalized();
        let end_tangent = self.vector(false).normalized();
        let start = self.start().add(start_tangent.offset(radius));
        let end = self.end().add(end_tangent.offset(radius));
        let result = match self {
            Self::Line(_) => Self::Line([start, end]),
            Self::Quad(_) => {
                let control =
                    line_intersection(start, start.add(start_tangent), end, end.sub(end_tangent))
                        .ok_or_else(|| {
                        crate::fail("TypeFacet quadratic offset has parallel endpoint tangents")
                    })?;
                if !control.x.is_finite() || !control.y.is_finite() {
                    return Err(crate::fail(
                        "TypeFacet quadratic tangent intersection is nonfinite",
                    ));
                }
                Self::Quad([start, control, end])
            }
            Self::Cubic([a, b, c, d]) => {
                let scale = end.sub(start).length() / d.sub(a).length();
                Self::Cubic([
                    start,
                    start.add(b.sub(a).scale(scale)),
                    end.sub(d.sub(c).scale(scale)),
                    end,
                ])
            }
        };
        // Upstream validates both the constructed and rounded segments.
        if !result.valid() {
            return Ok(None);
        }
        let result = result.mapped(Point::rounded);
        if !result.valid() {
            return Ok(None);
        }
        if result
            .end()
            .sub(result.start())
            .normalized()
            .dot(self.end().sub(self.start()).normalized())
            < 0.0
        {
            return Ok(None);
        }
        Ok(Some(result))
    }
}

fn line_intersection(a: Point, b: Point, c: Point, d: Point) -> Option<Point> {
    let denominator = (a.x - b.x) * (c.y - d.y) - (a.y - b.y) * (c.x - d.x);
    if denominator == 0.0 {
        return None;
    }
    let x = ((a.x * b.y - a.y * b.x) * (c.x - d.x) - (a.x - b.x) * (c.x * d.y - c.y * d.x))
        / denominator;
    let y = ((a.x * b.y - a.y * b.x) * (c.y - d.y) - (a.y - b.y) * (c.x * d.y - c.y * d.x))
        / denominator;
    Some(Point { x, y }.rounded())
}

fn segment_intersection(a: Point, b: Point, c: Point, d: Point) -> Option<Point> {
    let mut p = line_intersection(a, b, c, d)?;
    if !p.x.is_finite() || !p.y.is_finite() {
        return Some(p);
    }
    let [aa, bb, cc, dd] = [a, b, c, d].map(Point::rounded);
    if p.x < aa.x.min(bb.x)
        || p.x < cc.x.min(dd.x)
        || p.x > aa.x.max(bb.x)
        || p.x > cc.x.max(dd.x)
        || p.y < aa.y.min(bb.y)
        || p.y < cc.y.min(dd.y)
        || p.y > aa.y.max(bb.y)
        || p.y > cc.y.max(dd.y)
    {
        return None;
    }
    p.x =
        p.x.max(a.x.min(b.x).min(c.x).min(d.x))
            .min(a.x.max(b.x).max(c.x).max(d.x));
    p.y =
        p.y.max(a.y.min(b.y).min(c.y).min(d.y))
            .min(a.y.max(b.y).max(c.y).max(d.y));
    Some(p)
}

pub(super) fn clockwise(contour: &[Segment]) -> bool {
    let mut sum = 0.0;
    let mut last = contour.last().unwrap().start();
    for segment in contour {
        let a = segment.start();
        let b = segment.end();
        let mut difference = b.sub(a).angle() - a.sub(last).angle();
        while difference < -std::f64::consts::PI {
            difference += std::f64::consts::TAU;
        }
        while difference > std::f64::consts::PI {
            difference -= std::f64::consts::TAU;
        }
        sum += difference;
        last = a;
    }
    sum < 0.0
}

pub(super) fn circle(center: Point, radius: f64) -> [Segment; 4] {
    let tl = Point {
        x: center.x - radius,
        y: center.y + radius,
    };
    let tr = Point {
        x: center.x + radius,
        y: center.y + radius,
    };
    let br = Point {
        x: center.x + radius,
        y: center.y - radius,
    };
    let bl = Point {
        x: center.x - radius,
        y: center.y - radius,
    };
    let top = tl.lerp(tr, 0.5);
    let right = tr.lerp(br, 0.5);
    let bottom = bl.lerp(br, 0.5);
    let left = tl.lerp(bl, 0.5);
    [
        (left, tl, top),
        (top, tr, right),
        (right, br, bottom),
        (bottom, bl, left),
    ]
    .map(|(a, c, b)| {
        let first = c.sub(a);
        let last = b.sub(c);
        Segment::Cubic([
            a,
            a.add(first.normalized().scale(first.length() * 0.55228475)),
            b.sub(last.normalized().scale(last.length() * 0.55228475)),
            b,
        ])
    })
}
