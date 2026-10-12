//! Independent dimensions for compact filled curved contours.
//!
//! Feature: detached filled round marks (lowercase `i`/`j` dots, standalone
//! punctuation such as periods) carry their own curved extremities and
//! diameter. A diameter is not automatically a stem thickness.
//!
//! Source foundation:
//! - Microsoft, _From typeface to font file_, "Measuring Stems and Strokes":
//!   <https://learn.microsoft.com/en-us/typography/truetype/from-typeface-to-font-file>
//!   documents separate lowercase `i`/`j` dot control values for the
//!   horizontal dimension, the vertical dimension and the whitespace above the
//!   stem. Independent dot dimensions are documented practice.
//! - Adobe, _Type 1 Font Format_, sections 8.1-8.2, printed pp. 69-72:
//!   <https://www.adobe.com/content/dam/acom/en/devnet/font/pdfs/T1_SPEC.pdf>
//!   identifies poor interactions between stem/alignment hints and dots in
//!   `i`, `j` and `!`, and recommends replacing the active hints for the
//!   relevant outline portion (scoped hint ownership).
//! - Adobe, _Type 2 Charstring Format_, section 4.3, printed p. 24:
//!   <https://partners.adobe.com/public/developer/en/font/5177.Type2.pdf>
//!   specifies `hintmask` to select active hints for subsequent path
//!   operations (the old `dotsection` operator itself is obsolete).
//! - Hersch 1993, section 5, printed pp. 90-96:
//!   <https://lspwww.epfl.ch/publications/typography/frsa.pdf> separates hint
//!   specification from its application to selected outline parts, permits
//!   proportional curved deformation, and controls curvilinear centering.
//! - Zongker, Wade and Salesin 2000, section 2:
//!   <https://grail.cs.washington.edu/wp-content/uploads/2015/08/Zongker2000.pdf>
//!   distinguishes CVT-controlled links, natural-distance constraints,
//!   proportional interpolation and anchors.
//! - ttfautohint documentation, "Smooth hinting":
//!   <https://freetype.org/ttfautohint/doc/ttfautohint.html> explains why
//!   fractional grayscale widths need a separate Mono quantization policy.
//! - FreeType, width management in the auto-hinter:
//!   <https://freetype.org/autohinting/widths.html> warns that independent
//!   rounding can exaggerate the widths of nearby features relative to each
//!   other. This experiment therefore keeps the horizontal mark diameter at
//!   its natural fractional source span instead of rounding it to whole
//!   pixels; the vertical diameter keeps the existing whole-pixel policy.
//!
//! PROJECT HYPOTHESIS: the automatic separator below (smooth convex filled
//! quadratic contours with convex cages, rejecting holes, overlap, tails,
//! straight stem features and conflicting ownership), the per-axis
//! source-derived Mono diameters (fractional horizontal span, whole-pixel
//! vertical span), the inherited-center placement, and the contour-space
//! affine transfer are project model work. None of the sources above
//! supplies a geometric classifier, a universal diameter, or a guaranteed
//! column result. Source-derived Mono dimensions are this sourced
//! experiment; they are not a mandatory whole-pixel rule and they do not
//! change the accepted gradual stem-width policy.
//!
//! Geometric invariant: every point of an accepted contour keeps its source
//! proportional position inside its own fitted diameters, so the affine map
//! preserves normalized curve proportions and joint tangency around the
//! inherited fitted center. Independent axis quantization can change aspect
//! ratio. Ordinary fitting supplies placement only; the final affine transfer
//! owns accepted coordinates after strong/weak interpolation. Contours whose
//! shape or ownership is not provable keep the usual path (safe general
//! fallback, never glyph exceptions).

use super::super::{outline::Outline, topo::Dimension};
use alloc::vec::Vec;
#[cfg(feature = "libm")]
#[allow(unused_imports)]
use core_maths::*;
use raw::tables::glyf::PointMarker;

/// Source-space control point used by the classifier.
///
/// Coordinates are font units, so classification is independent of size,
/// scale and grid placement. Translation and uniform-scale invariance are
/// covered by unit tests.
#[derive(Clone, Copy)]
struct SrcPt {
    x: i64,
    y: i64,
    on_curve: bool,
    /// Meaningful only when `on_curve` is false: quadratic off-curve.
    /// Cubic contours are outside this model and take the usual path.
    quad: bool,
}

/// Bounding box of the other contours in the glyph, in font units.
type BBox = (i64, i64, i64, i64);

/// Accepted contour ownership and independently fitted natural diameters.
struct Accepted {
    points: Vec<usize>,
    diameters: [f64; 2],
}

pub(super) struct Plan {
    accepted: Vec<Accepted>,
}

fn bbox_of(pts: &[SrcPt]) -> BBox {
    let mut bbox = (i64::MAX, i64::MIN, i64::MAX, i64::MIN);
    for pt in pts {
        bbox.0 = bbox.0.min(pt.x);
        bbox.1 = bbox.1.max(pt.x);
        bbox.2 = bbox.2.min(pt.y);
        bbox.3 = bbox.3.max(pt.y);
    }
    bbox
}

fn intersects(a: BBox, b: BBox) -> bool {
    // Inclusive contact counts as shared ownership: a mark resting exactly on
    // another contour's bound keeps the usual path.
    a.0 <= b.1 && b.0 <= a.1 && a.2 <= b.3 && b.2 <= a.3
}

/// Classify one contour's control cage in source space.
///
/// `others` holds the font-unit bounding boxes of every other contour in the
/// glyph. `conflicted` reports pre-existing ownership (for example diagonal
/// reservation) of any contour point. Returns `None` for every unprovable
/// shape, which selects the usual fitting path.
fn classify(pts: &[SrcPt], conflicted: bool, others: &[BBox]) -> Option<Accepted> {
    if conflicted || pts.len() < 4 {
        return None;
    }
    // Every interval between consecutive on-curve points must be curved:
    // quadratic off-curve controls only, at least one per interval. A
    // straight on-curve chord is a tail, serif or stem feature, and cubic
    // controls are outside this model.
    let mut on_curve = 0usize;
    for pt in pts {
        if pt.on_curve {
            on_curve += 1;
        } else if !pt.quad {
            return None;
        }
    }
    if on_curve < 2 {
        return None;
    }
    let n = pts.len();
    let at = |i: usize| pts[i % n];
    // Locate on-curve joints in cyclic order.
    let mut joints = Vec::new();
    for (i, pt) in pts.iter().enumerate() {
        if pt.on_curve {
            joints.push(i);
        }
    }
    for (k, joint) in joints.iter().enumerate() {
        let next_joint = joints[(k + 1) % joints.len()];
        // Count off-curve controls strictly between the joints.
        let mut span = 0usize;
        let mut i = (joint + 1) % n;
        while i != next_joint {
            if pts[i].on_curve {
                // Unreachable: joints enumerate every on-curve point.
                return None;
            }
            if !pts[i].quad {
                return None;
            }
            span += 1;
            i = (i + 1) % n;
            if span > n {
                return None;
            }
        }
        let start = at(*joint);
        let end = at(next_joint);
        let mut curved = false;
        let mut control = (joint + 1) % n;
        while control != next_joint {
            let p = at(control);
            curved |= (end.x - start.x) * (p.y - start.y) != (end.y - start.y) * (p.x - start.x);
            control = (control + 1) % n;
        }
        if span == 0 || !curved {
            // Straight chord between on-curve points.
            return None;
        }
        // Smooth joint: incoming and outgoing tangents must not fold back.
        // With cyclic indexing the tangent vectors use immediate neighbors,
        // which are the adjacent controls for curved intervals.
        let prev = at(joint + n - 1);
        let here = at(*joint);
        let next = at(joint + 1);
        let incoming = (here.x - prev.x, here.y - prev.y);
        let outgoing = (next.x - here.x, next.y - here.y);
        if incoming.0 * outgoing.0 + incoming.1 * outgoing.1 <= 0 {
            return None;
        }
    }
    // Convex control cage: nonzero turns have one sense. Collinear forward
    // tangents are smooth joints, not a rejection. Require the whole cage
    // to lie in each directed edge half-plane (also rejects star traversals).
    let mut sense = 0i64;
    for i in 0..n {
        let a = at(i);
        let b = at(i + 1);
        let c = at(i + 2);
        let cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
        let s = cross.signum();
        if s == 0 {
            continue;
        }
        if sense == 0 {
            sense = s;
        } else if s != sense {
            return None;
        }
    }
    if sense == 0 {
        return None;
    }
    for i in 0..n {
        let a = at(i);
        let b = at(i + 1);
        if a.x == b.x && a.y == b.y {
            return None;
        }
        for p in pts {
            let cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
            if cross.signum() != 0 && cross.signum() != sense {
                return None;
            }
        }
    }
    // Filled and detached: no shared bounds with any other contour. Nested
    // boxes (counters, bowls) and touching contours keep the usual path.
    let own = bbox_of(pts);
    if others.iter().any(|other| intersects(own, *other)) {
        return None;
    }
    Some(Accepted {
        points: Vec::new(),
        diameters: [0.0; 2],
    })
}

impl Plan {
    pub(super) fn new(
        outline: &Outline,
        diagonal: Option<&super::diagonal::Plan>,
        natural_scale: Option<&super::super::metrics::Scale>,
    ) -> Self {
        // Per-contour source cages plus font-unit bounding boxes.
        let mut cages: Vec<(Vec<usize>, Vec<SrcPt>, BBox)> = Vec::new();
        for contour in outline.contours.iter() {
            let mut ix = Vec::new();
            let mut cage = Vec::new();
            for p in contour.range() {
                let point = &outline.points[p];
                ix.push(p);
                cage.push(SrcPt {
                    x: point.fx as i64,
                    y: point.fy as i64,
                    on_curve: point.is_on_curve(),
                    quad: point.flags.is_off_curve_quad(),
                });
            }
            if cage.is_empty() {
                continue;
            }
            let bbox = bbox_of(&cage);
            cages.push((ix, cage, bbox));
        }
        let boxes: Vec<BBox> = cages.iter().map(|(_, _, bbox)| *bbox).collect();
        let mut accepted = Vec::new();
        for (i, (ix, cage, _)) in cages.iter().enumerate() {
            let others: Vec<BBox> = boxes
                .iter()
                .enumerate()
                .filter(|(j, _)| *j != i)
                .map(|(_, bbox)| *bbox)
                .collect();
            let conflicted = diagonal.is_some_and(|plan| ix.iter().any(|p| plan.owns(*p)));
            if let Some(mut slot) = classify(cage, conflicted, &others) {
                slot.points = ix.clone();
                for dim in [Dimension::Horizontal, Dimension::Vertical] {
                    let bounds = if let Some(scale) = natural_scale {
                        let values = slot
                            .points
                            .iter()
                            .map(|ix| {
                                let p = &outline.points[*ix];
                                let (value, factor, delta) = if dim == Dimension::Horizontal {
                                    (p.fx, scale.x_scale, scale.x_delta)
                                } else {
                                    (p.fy, scale.y_scale, scale.y_delta)
                                };
                                (
                                    (super::super::metrics::fixed_mul(value, factor) + delta)
                                        as f64,
                                    p.is_on_curve(),
                                )
                            })
                            .collect::<Vec<_>>();
                        curve_extent(&values)
                    } else {
                        extent(outline, &slot, dim, true)
                    };
                    // Horizontal marks keep the natural fractional source span
                    // (one-pixel floor only), removing the whole-pixel rounding
                    // that can exaggerate it against a gradually fitted stem.
                    // Vertical marks keep the existing whole-pixel policy.
                    // Both axes share the source scale and the same minimum.
                    slot.diameters[dim as usize] = if dim == Dimension::Horizontal {
                        (bounds.1 - bounds.0).max(64.0)
                    } else {
                        (((bounds.1 - bounds.0) / 64.0 + 0.5).floor() * 64.0).max(64.0)
                    };
                }
                accepted.push(slot);
            }
        }
        Self { accepted }
    }

    pub(super) fn len(&self) -> usize {
        self.accepted.len()
    }

    /// Fit one axis of every accepted contour through its own diameters.
    ///
    /// The contour-space affine map keeps each point's proportional position
    /// inside the fitted diameters, so source shape, joint tangents and
    /// inherited center transfer through the original curved contour (affine
    /// maps send Bezier controls to the controls of the mapped curve).
    /// Fitted points are marked touched, which withholds them from later
    /// strong/weak interpolation: this plan owns these coordinates.
    pub(super) fn apply_dim(&self, outline: &mut Outline, dim: Dimension) {
        for slot in &self.accepted {
            let (src_min, src_max, fit_center, fit_width) = fit_params(outline, slot, dim);
            let src_span = src_max - src_min;
            if src_span <= 0.0 {
                continue;
            }
            let src_center = (src_min + src_max) / 2.0;
            let ratio = fit_width / src_span;
            for p in &slot.points {
                let point = &mut outline.points[*p];
                let src = if dim == Dimension::Horizontal {
                    point.ox
                } else {
                    point.oy
                };
                // Nearest-integer placement of the mapped cage point; the vertical
                // diameter carries whole-pixel quantization while the
                // horizontal diameter keeps its fractional span; the inherited
                // center remains fractional. Only 26.6 arithmetic remainder
                // rounds.
                let fitted = (fit_center + (src as f64 - src_center) * ratio).round() as i32;
                if dim == Dimension::Horizontal {
                    point.x = fitted;
                    point.flags.set_marker(PointMarker::TOUCHED_X);
                } else {
                    point.y = fitted;
                    point.flags.set_marker(PointMarker::TOUCHED_Y);
                }
            }
        }
    }
}

/// Tight quadratic extent, including implied on-curve joints and interior
/// derivative roots. Control-cage bounds are not curve diameters.
fn extent(outline: &Outline, slot: &Accepted, dim: Dimension, source: bool) -> (f64, f64) {
    let values: Vec<_> = slot
        .points
        .iter()
        .map(|p| {
            let p = &outline.points[*p];
            (
                match (dim, source) {
                    (Dimension::Horizontal, true) => p.ox,
                    (Dimension::Vertical, true) => p.oy,
                    (Dimension::Horizontal, false) => p.x,
                    (Dimension::Vertical, false) => p.y,
                } as f64,
                p.is_on_curve(),
            )
        })
        .collect();
    curve_extent(&values)
}

fn curve_extent(values: &[(f64, bool)]) -> (f64, f64) {
    let mut bounds = (f64::INFINITY, f64::NEG_INFINITY);
    let mut observe = |v: f64| {
        bounds.0 = bounds.0.min(v);
        bounds.1 = bounds.1.max(v);
    };
    let n = values.len();
    for i in 0..n {
        let (c, on) = values[i];
        if on {
            observe(c);
            continue;
        }
        let prev = values[(i + n - 1) % n];
        let next = values[(i + 1) % n];
        let a = if prev.1 { prev.0 } else { (prev.0 + c) / 2.0 };
        let b = if next.1 { next.0 } else { (next.0 + c) / 2.0 };
        observe(a);
        observe(b);
        let denominator = a - 2.0 * c + b;
        if denominator != 0.0 {
            let t = (a - c) / denominator;
            if t > 0.0 && t < 1.0 {
                observe((1.0 - t) * (1.0 - t) * a + 2.0 * (1.0 - t) * t * c + t * t * b);
            }
        }
    }
    bounds
}

/// Own source diameter, ordinary fitting's center. The standard stem width
/// influences placement, not diameter. No absolute center phase is chosen.
fn fit_params(outline: &Outline, slot: &Accepted, dim: Dimension) -> (f64, f64, f64, f64) {
    let source = extent(outline, slot, dim, true);
    let fitted = extent(outline, slot, dim, false);
    let width = slot.diameters[dim as usize];
    (source.0, source.1, (fitted.0 + fitted.1) / 2.0, width)
}

impl Plan {
    pub(super) fn apply(&self, outline: &mut Outline, metrics: &mut Option<super::EdgeMetrics>) {
        let original = outline.points.to_vec();
        for dim in [Dimension::Horizontal, Dimension::Vertical] {
            self.apply_dim(outline, dim);
        }
        // Google Fonts' VTT guide constrains a separated dot to at least a
        // pixel above its parent. Project adaptation: retain the inherited
        // center only when one-pixel vertical clearance is feasible against
        // source-separated contours with overlapping horizontal projections.
        // Otherwise yield this contour to ordinary fitting, in both axes.
        // Recheck after fallback because another accepted mark can be a parent.
        let mut active = alloc::vec![true; self.accepted.len()];
        loop {
            let mut rejected = Vec::new();
            for (i, slot) in self.accepted.iter().enumerate() {
                if !active[i] {
                    continue;
                }
                let sx = extent(outline, slot, Dimension::Horizontal, true);
                let sy = extent(outline, slot, Dimension::Vertical, true);
                let fy = extent(outline, slot, Dimension::Vertical, false);
                for contour in &outline.contours {
                    let other = Accepted {
                        points: contour.range().collect(),
                        diameters: [0.0; 2],
                    };
                    if other.points == slot.points {
                        continue;
                    }
                    let ox = extent(outline, &other, Dimension::Horizontal, true);
                    if sx.1 < ox.0 || ox.1 < sx.0 {
                        continue;
                    }
                    let oy = extent(outline, &other, Dimension::Vertical, true);
                    let fitted = extent(outline, &other, Dimension::Vertical, false);
                    if (sy.0 > oy.1 && fy.0 - fitted.1 < 64.0)
                        || (sy.1 < oy.0 && fitted.0 - fy.1 < 64.0)
                    {
                        rejected.push(i);
                        break;
                    }
                }
            }
            if rejected.is_empty() {
                break;
            }
            for i in rejected {
                active[i] = false;
                for p in &self.accepted[i].points {
                    outline.points[*p] = original[*p];
                }
            }
        }
        // Keep bearing/advance deltas consistent when an owned mark becomes
        // an exterior edge. Interior dots leave the ordinary outer metrics.
        if let Some(metrics) = metrics {
            for (i, slot) in self.accepted.iter().enumerate() {
                if !active[i] {
                    continue;
                }
                let original = extent(outline, slot, Dimension::Horizontal, true);
                let fitted = extent(outline, slot, Dimension::Horizontal, false);
                if fitted.0 < metrics.left_pos as f64 {
                    metrics.left_pos = fitted.0.round() as i32;
                    metrics.left_opos = metrics.left_opos.min(original.0.round() as i32);
                }
                if fitted.1 > metrics.right_pos as f64 {
                    metrics.right_pos = fitted.1.round() as i32;
                    metrics.right_opos = metrics.right_opos.max(original.1.round() as i32);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::outline::unscaled::{UnscaledOutlineSink, UnscaledPoint};
    use raw::tables::glyf::PointFlags;

    // Four quadratic arcs with exactly collinear incoming/outgoing tangents.
    fn circle(scale: i64, dx: i64, dy: i64) -> Vec<SrcPt> {
        [
            (100, 0, true),
            (100, 100, false),
            (0, 100, true),
            (-100, 100, false),
            (-100, 0, true),
            (-100, -100, false),
            (0, -100, true),
            (100, -100, false),
        ]
        .map(|(x, y, on)| SrcPt {
            x: x * scale + dx,
            y: y * scale + dy,
            on_curve: on,
            quad: !on,
        })
        .to_vec()
    }
    fn outline(pts: &[SrcPt]) -> Outline {
        let mut out = Outline::default();
        for (i, p) in pts.iter().enumerate() {
            out.push(UnscaledPoint {
                x: p.x as i16,
                y: p.y as i16,
                flags: if p.on_curve {
                    PointFlags::on_curve()
                } else {
                    PointFlags::off_curve_quad()
                },
                is_contour_start: i == 0,
            })
            .unwrap();
            let point = out.points.last_mut().unwrap();
            point.ox = p.x as i32;
            point.oy = p.y as i32;
            // Simulate ordinary hinted placement with a compressed width.
            point.x = (p.x / 2 + 37) as i32;
            point.y = (p.y + 91) as i32;
        }
        out
    }
    #[test]
    fn smooth_joints_and_transformed_geometry() {
        for (scale, dx, dy) in [(1, 0, 0), (2, 400, -300), (7, -500, 50)] {
            let pts = circle(scale, dx, dy);
            assert!(classify(&pts, false, &[]).is_some());
            let mut reverse = pts.clone();
            reverse.reverse();
            assert!(classify(&reverse, false, &[]).is_some());
            let mut rotated = pts.clone();
            for p in &mut rotated {
                let (x, y) = (p.x - dx, p.y - dy);
                p.x = x + y + dx;
                p.y = y - x + dy;
            }
            assert!(classify(&rotated, false, &[]).is_some());
            let mut out = outline(&rotated);
            let plan = Plan::new(&out, None, None);
            assert_eq!(plan.len(), 1);
            let slot = &plan.accepted[0];
            let original = extent(&out, slot, Dimension::Horizontal, true);
            // Rotation puts controls at +/-200, but the actual curve at +/-150.
            assert_eq!(original.1 - original.0, 300.0 * scale as f64);
            let inherited = extent(&out, slot, Dimension::Horizontal, false);
            plan.apply(&mut out, &mut None);
            let fitted = extent(&out, slot, Dimension::Horizontal, false);
            assert!(((fitted.0 + fitted.1) - (inherited.0 + inherited.1)).abs() <= 1.0);
            // Horizontal diameters keep the natural fractional span.
            let intended = (original.1 - original.0).max(64.0);
            assert!((fitted.1 - fitted.0 - intended).abs() <= 1.0);
        }
    }
    #[test]
    fn diameters_use_requested_scale_and_one_pixel_floor_independently_of_style_scale() {
        use crate::outline::autohint::{metrics::Scale, style::ScriptGroup};
        use crate::{attribute::Style, outline::Target};
        let natural = Scale::new(
            10.0,
            1000,
            Style::Normal,
            Target::Mono,
            ScriptGroup::Default,
        );
        let mut out = outline(&circle(1, 300, 700));
        // Simulate substantial style-scale expansion without changing source
        // font geometry or requested size. Diameter must use the latter.
        for p in &mut out.points {
            p.ox *= 4;
            p.oy *= 4;
        }
        let plan = Plan::new(&out, None, Some(&natural));
        assert_eq!(plan.len(), 1);
        assert_eq!(plan.accepted[0].diameters, [128.0, 128.0]);
        let tiny = Scale::new(1.0, 1000, Style::Normal, Target::Mono, ScriptGroup::Default);
        let plan = Plan::new(&out, None, Some(&tiny));
        assert_eq!(plan.accepted[0].diameters, [64.0, 64.0]);
    }
    #[test]
    fn horizontal_diameter_keeps_fractional_span_while_vertical_rounds() {
        // A 200-unit source span is 3.125 px: not a whole number of pixels.
        // The horizontal diameter must keep that fraction instead of
        // snapping to 192 or 256; the vertical diameter keeps the existing
        // nearest-whole-pixel policy. Both keep the one-pixel floor, and the
        // fractional policy never selects a glyph, family, size or axis.
        let mut out = outline(&circle(1, 300, 700));
        let plan = Plan::new(&out, None, None);
        assert_eq!(plan.len(), 1);
        assert_eq!(plan.accepted[0].diameters[0], 200.0);
        assert_eq!(plan.accepted[0].diameters[1], 192.0);
        // The fitted transfer still owns the contour around its inherited
        // center: horizontal extent matches the fractional diameter within
        // point-rounding remainder, and every point stays touched.
        plan.apply(&mut out, &mut None);
        let fitted = extent(&out, &plan.accepted[0], Dimension::Horizontal, false);
        assert!((fitted.1 - fitted.0 - 200.0).abs() <= 1.0);
        for p in &out.points[..8] {
            assert!(p
                .flags
                .has_marker(PointMarker::TOUCHED_X | PointMarker::TOUCHED_Y));
        }
    }

    #[test]
    fn rejects_holes_overlap_straight_features_and_ownership_conflict() {
        let dot = circle(1, 0, 0);
        assert!(classify(&dot, true, &[]).is_none());
        assert!(classify(&dot, false, &[bbox_of(&circle(4, 0, 0))]).is_none());
        assert!(classify(&dot, false, &[bbox_of(&circle(1, 150, 0))]).is_none());
        let mut flat = dot.clone();
        flat.remove(1);
        assert!(classify(&flat, false, &[]).is_none());
        let mut cubic = dot.clone();
        cubic[1].quad = false;
        assert!(classify(&cubic, false, &[]).is_none());
        let mut cusp = dot.clone();
        cusp[0].x = 0;
        assert!(classify(&cusp, false, &[]).is_none());
    }
    #[test]
    fn rejects_straight_quadratic_intervals_and_yields_when_clearance_is_infeasible() {
        let mut flat = circle(1, 0, 0);
        flat[1].x = 50;
        flat[1].y = 50;
        assert!(classify(&flat, false, &[]).is_none());
        let mut out = outline(&circle(1, 300, 700));
        for (i, (x, y)) in [(200, 0), (400, 0), (400, 500), (200, 500)]
            .into_iter()
            .enumerate()
        {
            out.push(UnscaledPoint {
                x,
                y,
                flags: PointFlags::on_curve(),
                is_contour_start: i == 0,
            })
            .unwrap();
            let p = out.points.last_mut().unwrap();
            p.ox = x as i32;
            p.x = x as i32;
            p.oy = y as i32;
            p.y = y as i32 + 160;
        }
        let before = out.points.to_vec();
        let plan = Plan::new(&out, None, None);
        assert_eq!(plan.len(), 1);
        plan.apply(&mut out, &mut None);
        // Explicit fallback contract: no partial axis or metric update.
        assert_eq!(out.points.as_slice(), before.as_slice());
    }

    #[test]
    fn affine_transfer_preserves_anchor_tangents_and_exclusive_point_ownership() {
        let mut out = outline(&circle(1, 300, 700));
        // A separate straight body below the mark must not be claimed or moved.
        for (i, (x, y)) in [(200, 0), (400, 0), (400, 300), (200, 300)]
            .into_iter()
            .enumerate()
        {
            out.push(UnscaledPoint {
                x,
                y,
                flags: PointFlags::on_curve(),
                is_contour_start: i == 0,
            })
            .unwrap();
            let p = out.points.last_mut().unwrap();
            p.ox = x as i32;
            p.x = x as i32 + 17;
            p.oy = y as i32;
            p.y = y as i32 + 32;
        }
        let body = out.points[8..].to_vec();
        let plan = Plan::new(&out, None, None);
        assert_eq!(plan.len(), 1);
        let original = out.points[..8].to_vec();
        let params = fit_params(&out, &plan.accepted[0], Dimension::Horizontal);
        plan.apply(&mut out, &mut None);
        assert_eq!(&out.points[8..], &body);
        for (before, after) in original.iter().zip(&out.points[..8]) {
            let expected = params.2
                + (before.ox as f64 - (params.0 + params.1) / 2.0) * params.3
                    / (params.1 - params.0);
            assert!((after.x as f64 - expected).abs() <= 0.5);
            assert!(after
                .flags
                .has_marker(PointMarker::TOUCHED_X | PointMarker::TOUCHED_Y));
        }
        // Source's horizontal tangent at the top remains horizontal after fitting.
        assert_eq!(out.points[1].y, out.points[2].y);
        assert_eq!(out.points[2].y, out.points[3].y);
    }
}
