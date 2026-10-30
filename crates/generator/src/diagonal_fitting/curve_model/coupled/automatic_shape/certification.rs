//! Ordered certification of the quantized candidate against source and upstream authorities.

use super::*;

/// Quantized postconditions share one unrounded proposal and an ordered
/// diagnostic record; each phase may append evidence only after its predecessor.
pub(super) struct CandidateCertificate<'a, 'source> {
    shape: &'a PreparedShape<'source>,
    system: &'a AssembledShape,
    solution: &'a SolvedShape,
    cand: geometry::Parsed,
    raw_cont: Vec<[f64; 2]>,
    checks: serde_json::Value,
}

impl<'a, 'source> CandidateCertificate<'a, 'source> {
    pub(super) fn new(
        shape: &'a PreparedShape<'source>,
        system: &'a AssembledShape,
        solution: &'a SolvedShape,
    ) -> ShapeResult<Self> {
        let weld = &shape.weld;
        let ctx = &system.released.ctx;
        // Post-rounding shape verification against the original source.
        let Ok(cand) = geometry::parse_commands(&solution.commands) else {
            return no("shape-candidate-malformed", serde_json::json!({}));
        };
        // Unrounded proposal for all row representation allowances (never the
        // already-rounded candidate pretending to be raw).
        let raw_cont: Vec<[f64; 2]> = {
            let mut raw = shape.up_global.clone();
            for ((v, axis), d) in ctx.cols.iter().zip(solution.displacements.iter()) {
                raw[*v][*axis] += d;
            }
            for (dup, canon) in weld {
                raw[*dup] = raw[*canon];
            }
            raw
        };
        Ok(Self {
            shape,
            system,
            solution,
            cand,
            raw_cont,
            checks: serde_json::json!({}),
        })
    }

    pub(super) fn verify(mut self) -> ShapeResult<serde_json::Value> {
        self.body_profile()?;
        self.curves()?;
        self.head_tangent()?;
        self.ownership()?;
        self.named_rows()?;
        self.sharp_corners()?;
        Ok(self.checks)
    }

    fn body_profile(&mut self) -> ShapeResult<()> {
        let parsed = self.shape.parsed;
        let feature = &self.shape.feature;
        let standard = self.shape.standard;
        let bla = self.shape.bla;
        let up_global = &self.shape.up_global;
        let weld = &self.shape.weld;
        let ctx = &self.system.released.ctx;
        let raw_cont = &self.raw_cont;
        let n = ctx.base.len();
        let no_pts = parsed.oncurve.len();
        let global_index = |oncurve: bool, idx: usize| if oncurve { idx } else { no_pts + idx };
        let cand = &self.cand;
        let checks = &mut self.checks;
        let (cand_r_idx, _) = parsed.contours[0][feature.body_r_seg].endpoints();
        let cand_r = cand.oncurve[cand_r_idx][0];
        let body_w = cand_r - cand.oncurve[bla][0];
        checks["body_width"] = serde_json::json!(body_w);
        if body_w != standard {
            return no("shape-candidate-width", checks.clone());
        }
        let gl = (cand.oncurve[bla][0] * 64.0).round() as i64;
        let gr = (cand_r * 64.0).round() as i64;
        if gl.rem_euclid(64) == 32 || gr.rem_euclid(64) == 32 {
            return no("shape-candidate-phase", checks.clone());
        }
        // One head-mid width target only (S*src_mid/w_body). Quarter and
        // three-quarter stations are not independent hard rows; the
        // translated source profile plus the mid anchor determines them.
        // Verifying all three absolute widths would demand different moves
        // per station and contradict the single shared translation.
        {
            let (seg_idx, t, src_width) = &feature.stations[1];
            let geometry::Segment::Quad { c, a, b } = parsed.contours[0][*seg_idx] else {
                return no("shape-feature-unsupported", serde_json::json!({}));
            };
            let u = 1.0 - t;
            let cx = u * u * cand.oncurve[a][0]
                + 2.0 * u * t * cand.offcurve[c][0]
                + t * t * cand.oncurve[b][0];
            let target = standard * (src_width / feature.w_body);
            checks["station_target"] = serde_json::json!(target);
            let u2 = 1.0 - t;
            let mut srow = vec![0.0; 2 * n];
            srow[2 * global_index(true, cand_r_idx)] += 1.0;
            srow[2 * global_index(true, a)] += -u2 * u2;
            srow[2 * global_index(false, c)] += -2.0 * u2 * t;
            srow[2 * global_index(true, b)] += -t * t;
            let allowance = model::rounding_reserve(&srow, &ctx.cols, raw_cont, up_global, weld);
            checks["station_allowance"] = serde_json::json!(allowance);
            checks["station_width"] = serde_json::json!(cand_r - cx);
            if ((cand_r - cx) - target).abs() > allowance + 1e-9 {
                return no("shape-candidate-profile", checks.clone());
            }
        }
        Ok(())
    }

    fn curves(&mut self) -> ShapeResult<()> {
        let parsed = self.shape.parsed;
        let fitted = &self.shape.fitted;
        let cand = &self.cand;
        let checks = &mut self.checks;
        // Foot/lower curve curvature signs against source for every quad
        // whose control or endpoints moved.
        for seg in &parsed.contours[0] {
            let geometry::Segment::Quad { c, a, b } = *seg else {
                continue;
            };
            let moved = cand.oncurve[a] != fitted.oncurve[a]
                || cand.oncurve[b] != fitted.oncurve[b]
                || cand.offcurve[c] != fitted.offcurve[c];
            if !moved {
                continue;
            }
            let cross = |p: &geometry::Parsed| {
                (p.offcurve[c][0] - p.oncurve[a][0]) * (p.oncurve[b][1] - p.oncurve[a][1])
                    - (p.offcurve[c][1] - p.oncurve[a][1]) * (p.oncurve[b][0] - p.oncurve[a][0])
            };
            let (cs, cc) = (cross(parsed), cross(cand));
            if cs != 0.0 && (cc == 0.0 || cs.signum() != cc.signum()) {
                return no("shape-candidate-curvature", checks.clone());
            }
        }
        // Whole-outline topology under the existing substituted-curve
        // certificate (depth-0 substitution, the raw-certified depth).
        if !curves::compare_substituted(parsed, fitted, cand) {
            return no("shape-candidate-topology", checks.clone());
        }
        Ok(())
    }

    fn head_tangent(&mut self) -> ShapeResult<()> {
        let parsed = self.shape.parsed;
        let feature = &self.shape.feature;
        let up_global = &self.shape.up_global;
        let weld = &self.shape.weld;
        let ctx = &self.system.released.ctx;
        let raw_cont = &self.raw_cont;
        let n = ctx.base.len();
        let no_pts = parsed.oncurve.len();
        let global_index = |oncurve: bool, idx: usize| if oncurve { idx } else { no_pts + idx };
        let cand = &self.cand;
        let checks = &mut self.checks;
        // Source component survival: the top head quad's endpoint tangent
        // keeps a nonzero horizontal component with the source sign. The top
        // endpoint is the chain boundary vertex adjacent to the cap (highest
        // Y among chain endpoints touching cap ownership), independent of
        // chain traversal direction; the incident quad control gives dx.
        {
            let cap_set: HashSet<usize> = feature
                .cap
                .iter()
                .flat_map(|(cv, lv, rv, _)| [*cv, *lv, *rv])
                .collect();
            let mut top_v: Option<usize> = None;
            let mut top_y = f64::NEG_INFINITY;
            for &v in &feature.chain_verts {
                let y = parsed.oncurve[v][1];
                let adjacent = cap_set.contains(&v) || {
                    // Contour-adjacent to a cap vertex counts as boundary.
                    let mut adj = false;
                    for seg in &parsed.contours[0] {
                        let (a, b) = seg.endpoints();
                        if (a == v && cap_set.contains(&b)) || (b == v && cap_set.contains(&a)) {
                            adj = true;
                            break;
                        }
                    }
                    adj
                };
                if (adjacent || top_v.is_none()) && y > top_y {
                    top_y = y;
                    top_v = Some(v);
                }
            }
            let Some(tv) = top_v else {
                return no("shape-candidate-tangent", checks.clone());
            };
            let mut top_quad: Option<(usize, usize, usize)> = None;
            for &sg in &feature.chain_segs {
                if let geometry::Segment::Quad { c, a, b } = parsed.contours[0][sg] {
                    if a == tv || b == tv {
                        // Prefer the quad where tv is the higher endpoint.
                        let other = if a == tv { b } else { a };
                        if parsed.oncurve[tv][1] >= parsed.oncurve[other][1] {
                            top_quad = Some((c, a, b));
                            break;
                        }
                        if top_quad.is_none() {
                            top_quad = Some((c, a, b));
                        }
                    }
                }
            }
            let Some((c, a, b)) = top_quad else {
                return no("shape-candidate-tangent", checks.clone());
            };
            let end = if parsed.oncurve[a][1] >= parsed.oncurve[b][1] {
                a
            } else {
                b
            };
            let src_dx = parsed.offcurve[c][0] - parsed.oncurve[end][0];
            let cand_dx = cand.offcurve[c][0] - cand.oncurve[end][0];
            checks["tangent_dx"] = serde_json::json!({
                "source": src_dx, "candidate": cand_dx, "joint": tv, "control": c, "end": end,
            });
            if src_dx != 0.0 && (cand_dx == 0.0 || cand_dx.signum() != src_dx.signum()) {
                return no("shape-candidate-tangent", checks.clone());
            }
            // Resolvable-component error against the actual row allowance.
            {
                let mut trow = vec![0.0; 2 * n];
                trow[2 * global_index(false, c)] += 1.0;
                trow[2 * global_index(true, end)] += -1.0;
                let allow = rounding_reserve(&trow, &ctx.cols, raw_cont, up_global, weld);
                checks["tangent_allowance"] = serde_json::json!(allow);
                if (cand_dx - src_dx).abs() > allow + 1e-9 {
                    return no("shape-candidate-tangent", checks.clone());
                }
            }
        }
        Ok(())
    }

    fn ownership(&mut self) -> ShapeResult<()> {
        let parsed = self.shape.parsed;
        let fitted = &self.shape.fitted;
        let feature = &self.shape.feature;
        let bla = self.shape.bla;
        let up_global = &self.shape.up_global;
        let ctx = &self.system.released.ctx;
        let public_caps = &self.solution.public_caps;
        let (cand_r_idx, _) = parsed.contours[0][feature.body_r_seg].endpoints();
        let cand_r = self.cand.oncurve[cand_r_idx][0];
        let cand = &self.cand;
        let checks = &mut self.checks;
        // Y authority: retained upstream Y bit-identical everywhere.
        for (i, (c, u)) in cand.oncurve.iter().zip(fitted.oncurve.iter()).enumerate() {
            if c[1] != u[1] {
                checks["y_changed"] = serde_json::json!({ "point": i });
                return no("shape-candidate-y", checks.clone());
            }
        }
        for (i, (c, u)) in cand.offcurve.iter().zip(fitted.offcurve.iter()).enumerate() {
            if c[1] != u[1] {
                checks["y_changed"] = serde_json::json!({ "offcurve": i });
                return no("shape-candidate-y", checks.clone());
            }
        }
        // Per-feature movement caps after quantization: the delivered
        // quantized displacement must not exceed the public cap (exact).
        // The solver already reserved one half-quantum inside each cap.
        for (ci, (v, axis)) in ctx.cols.iter().enumerate() {
            if *axis != 0 {
                continue;
            }
            let dq = cand
                .oncurve
                .iter()
                .chain(cand.offcurve.iter())
                .nth(*v)
                .map(|pt| pt[*axis])
                .unwrap_or(f64::NAN)
                - up_global[*v][*axis];
            let cap = public_caps[ci];
            if !(dq.abs() <= cap + 1e-12) {
                checks["bound_exceeded"] =
                    serde_json::json!({ "point": v, "disp": dq, "cap": cap });
                return no("shape-candidate-bound", checks.clone());
            }
        }
        // Body width exact plus both borders straight (constant X).
        for &v in &feature.r_verts[1..] {
            if cand.oncurve[v][0] != cand_r {
                return no("shape-candidate-straightness", checks.clone());
            }
        }
        let cand_l = cand.oncurve[bla][0];
        for &v in &feature.l_verts {
            if cand.oncurve[v][0] != cand_l {
                return no("shape-candidate-straightness", checks.clone());
            }
        }
        Ok(())
    }

    fn named_rows(&mut self) -> ShapeResult<()> {
        let up_global = &self.shape.up_global;
        let weld = &self.shape.weld;
        let ctx = &self.system.released.ctx;
        let raw_cont = &self.raw_cont;
        let hard = &self.system.hard;
        let cand = &self.cand;
        let checks = &mut self.checks;
        // Intended feature rows after rounding against their actual row
        // rounding_reserve (never a global tolerance). Uses the unrounded
        // proposal defined above.
        {
            let check_row = |rvec: &[f64], rhs_v: f64, label: &str| -> Option<serde_json::Value> {
                // Quantized displacement dot row minus rhs.
                let mut qd = 0.0;
                for (v, axis) in &ctx.cols {
                    let all: Vec<[f64; 2]> = cand
                        .oncurve
                        .iter()
                        .chain(cand.offcurve.iter())
                        .copied()
                        .collect();
                    qd += rvec[2 * v + axis] * (all[*v][*axis] - up_global[*v][*axis]);
                }
                let allowance = rounding_reserve(rvec, &ctx.cols, raw_cont, up_global, weld);
                if (qd - rhs_v).abs() > allowance + 1e-9 {
                    return Some(serde_json::json!({
                        "row": label, "error": qd - rhs_v, "allowance": allowance,
                    }));
                }
                None
            };
            for hr in &hard.rows {
                // rhs = target - up_dot, stored constant is up_dot - target.
                let rhs_v = -hr.constant;
                if let Some(diag) = check_row(&hr.coefficients, rhs_v, hr.name) {
                    checks["row_error"] = diag;
                    return no("shape-candidate-row", checks.clone());
                }
            }
        }
        Ok(())
    }

    fn sharp_corners(&mut self) -> ShapeResult<()> {
        let parsed = self.shape.parsed;
        let captured = &self.shape.captured;
        let fitted = &self.shape.fitted;
        let feature = &self.shape.feature;
        let cand = &self.cand;
        let checks = &mut self.checks;
        // Source-sharp transformed corners: retain turn orientation and
        // nondegeneracy against source (no exact-angle claim). Uses exact
        // rational leg geometry via joints plus coordinate orientation
        // postcheck on the quantized candidate.
        {
            let src_map = joints(parsed);
            let cap_map_post = joints(captured);
            let up_map_post = joints(fitted);
            let smooth_post = |j: &usize| -> bool {
                src_map.get(j).is_some_and(|v| v.iter().any(|o| o.smooth))
                    || cap_map_post
                        .get(j)
                        .is_some_and(|v| v.iter().any(|o| o.smooth))
                    || up_map_post
                        .get(j)
                        .is_some_and(|v| v.iter().any(|o| o.smooth))
            };
            for (j, occs) in &src_map {
                for occ in occs {
                    if occ.smooth || occ.degenerate {
                        continue;
                    }
                    // Conservative continuity: raw/captured/upstream-smooth
                    // joins stay hard G1 (captured source is the producer
                    // proof; raw 1ULP noise never reclassifies them).
                    if smooth_post(j) {
                        continue;
                    }
                    let owned_here = feature.r_verts.contains(j)
                        || feature.l_verts.contains(j)
                        || feature.chain_verts.contains(j)
                        || feature.cap.is_some_and(|(cv, _, _, _)| cv == *j);
                    if !owned_here {
                        continue;
                    }
                    let leg =
                        |p: &geometry::Parsed, s: model::SegRef, at_joint_out: bool| -> [f64; 2] {
                            match (s, at_joint_out) {
                                (model::SegRef::Line { b, .. }, true) => p.oncurve[b],
                                (model::SegRef::Line { a, .. }, false) => p.oncurve[a],
                                (model::SegRef::Quad { off, .. }, _) => {
                                    let no = p.oncurve.len();
                                    if off >= no {
                                        p.offcurve[off - no]
                                    } else {
                                        p.oncurve[off]
                                    }
                                }
                            }
                        };
                    let fin_s = leg(parsed, occ.prev, false);
                    let fout_s = leg(parsed, occ.seg, true);
                    let lin_s = [
                        parsed.oncurve[*j][0] - fin_s[0],
                        parsed.oncurve[*j][1] - fin_s[1],
                    ];
                    let lout_s = [
                        fout_s[0] - parsed.oncurve[*j][0],
                        fout_s[1] - parsed.oncurve[*j][1],
                    ];
                    let cs = lin_s[0] * lout_s[1] - lin_s[1] * lout_s[0];
                    if cs == 0.0 {
                        continue;
                    }
                    let fin_c = leg(&cand, occ.prev, false);
                    let fout_c = leg(&cand, occ.seg, true);
                    let lin_c = [
                        cand.oncurve[*j][0] - fin_c[0],
                        cand.oncurve[*j][1] - fin_c[1],
                    ];
                    let lout_c = [
                        fout_c[0] - cand.oncurve[*j][0],
                        fout_c[1] - cand.oncurve[*j][1],
                    ];
                    if !(lin_c[0].hypot(lin_c[1]) > 0.0 && lout_c[0].hypot(lout_c[1]) > 0.0) {
                        checks["degenerate"] = serde_json::json!({ "joint": j });
                        return no("shape-candidate-degenerate", checks.clone());
                    }
                    let cc = lin_c[0] * lout_c[1] - lin_c[1] * lout_c[0];
                    if cc == 0.0 || cc.signum() != cs.signum() {
                        let up_smooth = up_map_post
                            .get(j)
                            .is_some_and(|v| v.iter().any(|o| o.smooth));
                        let src_smooth = src_map.get(j).is_some_and(|v| v.iter().any(|o| o.smooth));
                        let cap_smooth = cap_map_post
                            .get(j)
                            .is_some_and(|v| v.iter().any(|o| o.smooth));
                        checks["orientation"] = serde_json::json!({
                            "joint": j, "source": cs, "candidate": cc,
                            "src_smooth": src_smooth, "cap_smooth": cap_smooth,
                            "up_smooth": up_smooth,
                            "in_r": feature.r_verts.contains(j),
                            "in_l": feature.l_verts.contains(j),
                            "in_chain": feature.chain_verts.contains(j),
                            "in_cap": feature.cap.is_some_and(|(cv, _, _, _)| cv == *j),
                            "chain_segs": feature.chain_segs,
                            "cap": feature.cap,
                        });
                        return no("shape-candidate-orientation", checks.clone());
                    }
                }
            }
        }
        Ok(())
    }
}
