//! Released controls, intended feature relationships and original movement budgets.

use super::*;

/// A feature relationship and its diagnostic name cannot be updated separately.
impl NamedConstraints {
    fn new(points: usize) -> Self {
        Self {
            points,
            rows: Vec::new(),
        }
    }

    fn push(
        &mut self,
        upstream: &[[f64; 2]],
        name: &'static str,
        coeffs: &[(usize, f64)],
        target: f64,
    ) {
        let mut rvec = vec![0.0; 2 * self.points];
        let mut up_dot = 0.0;
        for &(g, a) in coeffs {
            rvec[2 * g] += a;
            up_dot += a * upstream[g][0];
        }
        self.rows.push(NamedConstraint {
            name,
            coefficients: rvec,
            constant: up_dot - target,
        });
    }

    fn solver_rows(&self) -> Vec<(RowKind, Vec<f64>, f64)> {
        self.rows
            .iter()
            .map(|r| (RowKind::Joint, r.coefficients.clone(), r.constant))
            .collect()
    }

    pub(super) fn names(&self) -> Vec<&'static str> {
        self.rows.iter().map(|r| r.name).collect()
    }
}

impl MovementBudget {
    fn new(feature: &ShapeFeature) -> ShapeResult<Self> {
        // Incident-feature movement caps from one original-upstream budget
        // (Hobby 3.1/6 single displacement measure; Shamir shared-feature
        // solve; existing per-pair cap rule: narrowest certified sample of
        // the owning feature over two minus HEADROOM). Body cap from the
        // body width, head cap from the minimum certified head sample.
        // Shared-border R and the cap vertex obey the intersection (minimum);
        // head-chain controls, extreme endpoints and vertical-connector
        // endpoints obey the head cap; body-L and offcurve controls on their
        // source vertical support obey the body cap; all other body/foot
        // controls obey the body cap unless jointly head-owned. The 26.6
        // rounding reserve (half quantum per moved X) sits inside each cap,
        // so the delivered quantized movement never exceeds the cap.
        let body_cap = feature.w_body / 2.0 - fitting::HEADROOM;
        let head_cap = feature.w_head_min / 2.0 - fitting::HEADROOM;
        if body_cap < fitting::HEADROOM || head_cap < fitting::HEADROOM {
            return no("shape-budget-empty", serde_json::json!({}));
        }
        let shared_cap = body_cap.min(head_cap);
        // Solver bounds reserve one half-quantum per moved X inside the cap.
        let solver_body = body_cap - model::ROUND_HALF;
        let solver_head = head_cap - model::ROUND_HALF;
        let solver_shared = shared_cap - model::ROUND_HALF;
        if solver_body < 0.0 || solver_head < 0.0 || solver_shared < 0.0 {
            return no("shape-budget-empty", serde_json::json!({}));
        }
        // Per-control caps metadata (explicit; solver bounds reserve rounding).
        let caps_meta = serde_json::json!({
            "body_cap": body_cap, "head_cap": head_cap, "shared_cap": shared_cap,
            "solver_reserve": model::ROUND_HALF,
            "solver_body": solver_body, "solver_head": solver_head,
            "solver_shared": solver_shared,
        });
        Ok(Self {
            body: body_cap,
            head: head_cap,
            shared: shared_cap,
            metadata: caps_meta,
        })
    }

    pub(super) fn column_limits(
        &self,
        shape: &PreparedShape<'_>,
        ctx: &model::SolveCtx,
        connector_verts: &[usize],
    ) -> ColumnLimits {
        let parsed = shape.parsed;
        let feature = &shape.feature;
        let no_pts = parsed.oncurve.len();
        let (body_cap, head_cap, shared_cap) = (self.body, self.head, self.shared);
        // Per-column incident-feature caps (solver bounds reserve rounding;
        // public caps gate the delivered quantized movement).
        let r_set: HashSet<usize> = feature.r_verts.iter().copied().collect();
        let l_set: HashSet<usize> = feature.l_verts.iter().copied().collect();
        let chain_vset: HashSet<usize> = feature.chain_verts.iter().copied().collect();
        let conn_set: HashSet<usize> = connector_verts.iter().copied().collect();
        let chain_cset: HashSet<usize> = feature.chain_ctrls.iter().copied().collect();
        let (cap_v, cap_l, cap_r, _) =
            feature
                .cap
                .unwrap_or((usize::MAX, usize::MAX, usize::MAX, 0.0));
        let mut off_seg: HashMap<usize, (usize, usize)> = HashMap::new();
        for seg in &parsed.contours[0] {
            if let geometry::Segment::Quad { c, a, b } = *seg {
                off_seg.insert(c, (a, b));
            }
        }
        let public_cap_of = |g: usize| -> f64 {
            if g < no_pts {
                let v = g;
                if r_set.contains(&v) || v == cap_v || v == cap_l || v == cap_r {
                    shared_cap
                } else if chain_vset.contains(&v) || conn_set.contains(&v) {
                    head_cap
                } else if l_set.contains(&v) {
                    body_cap
                } else {
                    body_cap
                }
            } else {
                let c = g - no_pts;
                if chain_cset.contains(&c) {
                    head_cap
                } else if parsed.offcurve.get(c).is_some_and(|p| p[0] == feature.x_r) {
                    shared_cap
                } else if parsed.offcurve.get(c).is_some_and(|p| p[0] == feature.x_l) {
                    body_cap
                } else if let Some((a, b)) = off_seg.get(&c) {
                    if chain_vset.contains(a)
                        || chain_vset.contains(b)
                        || conn_set.contains(a)
                        || conn_set.contains(b)
                        || r_set.contains(a)
                        || r_set.contains(b)
                        || *a == cap_v
                        || *b == cap_v
                        || *a == cap_l
                        || *b == cap_l
                        || *a == cap_r
                        || *b == cap_r
                    {
                        head_cap
                    } else {
                        body_cap
                    }
                } else {
                    body_cap
                }
            }
        };
        let bounds: Vec<f64> = ctx
            .cols
            .iter()
            .map(|(v, _)| public_cap_of(*v) - model::ROUND_HALF)
            .collect();
        let public_caps: Vec<f64> = ctx.cols.iter().map(|(v, _)| public_cap_of(*v)).collect();
        ColumnLimits {
            bounds,
            public_caps,
        }
    }
}

impl AssembledShape {
    pub(super) fn new(shape: &PreparedShape<'_>) -> ShapeResult<Self> {
        let mut released = release_controls(shape)?;
        // Assembly must retain precedence over movement-budget rejection.
        let budget = MovementBudget::new(&shape.feature)?;
        let constraints =
            feature_constraints(shape, released.ctx.base.len(), &released.connector_verts)?;
        reconcile_owned_joints(shape, &mut released.ctx, &constraints.intrinsic);
        released.ctx.rows.extend(constraints.named.solver_rows());
        Ok(Self {
            released,
            budget,
            hard: constraints.named,
        })
    }
}

fn release_controls(shape: &PreparedShape<'_>) -> ShapeResult<ReleasedControls> {
    let parsed = shape.parsed;
    let fitted = &shape.fitted;
    let weld = &shape.weld;
    let feature = &shape.feature;
    let up_global = &shape.up_global;
    let size_px = shape.size_px;
    let specs = &shape.specs;
    // Whole-outline free-X coupled assembly (Hobby 3.1/3.6/6: every X
    // control is a coupled variable). Only closure aliases stay frozen;
    // upright pins below hold every non-owned vertical. No ad hoc
    // free_set freeze: the coupled objective already owns all controls,
    // and freezing the complement reintroduces hidden stationary foot
    // attachments and frozen connector points.
    // Weld-canonical release for both body borders, head-owned vertices,
    // and both endpoints of every source vertical connector incident to
    // the head chain. Built completely before assemble.
    let canon = |v: usize| weld.get(&v).copied().unwrap_or(v);
    let chain_set: HashSet<usize> = feature.chain_verts.iter().copied().collect();
    let mut connector_verts: Vec<usize> = Vec::new();
    for seg in &parsed.contours[0] {
        if let geometry::Segment::Line { a, b } = *seg {
            let (pa, pb) = (parsed.oncurve[a], parsed.oncurve[b]);
            if pa[0] == pb[0] && (chain_set.contains(&a) || chain_set.contains(&b)) {
                for v in [a, b] {
                    if !connector_verts.contains(&v) {
                        connector_verts.push(v);
                    }
                }
            }
        }
    }
    // Fitted group coherence plus full-span width verification (not a
    // single point): both body borders must be constant-X in the
    // original upstream, otherwise the straight-border ownership is
    // ineligible and the candidate abstains.
    {
        let mut r_fit: Option<f64> = None;
        for &v in &feature.r_verts {
            let x = fitted.oncurve[v][0];
            match r_fit {
                None => r_fit = Some(x),
                Some(y) if y == x => {}
                _ => {
                    return no(
                        "shape-border-incoherent",
                        serde_json::json!({ "border": "right" }),
                    );
                }
            }
        }
        let mut l_fit: Option<f64> = None;
        for &v in &feature.l_verts {
            let x = fitted.oncurve[v][0];
            match l_fit {
                None => l_fit = Some(x),
                Some(y) if y == x => {}
                _ => {
                    return no(
                        "shape-border-incoherent",
                        serde_json::json!({ "border": "left" }),
                    );
                }
            }
        }
        // Full-span check: every fitted border vertex participates above,
        // so a split border anywhere in the span abstains.
    }
    let mut fixed_x = HashSet::new();
    for edge in straight_edges(parsed) {
        if edge.p0[0] == edge.p1[0] {
            for v in [edge.i0, edge.i1] {
                fixed_x.insert(canon(v));
            }
        }
    }
    // Release weld-canonical vertices for both body borders, the head
    // chain, its controls' endpoints, connector endpoints, and cap.
    for &v in feature
        .r_verts
        .iter()
        .chain(&feature.l_verts)
        .chain(&feature.chain_verts)
        .chain(&connector_verts)
    {
        fixed_x.remove(&canon(v));
    }
    if let Some((cv, lv, rv, _)) = feature.cap {
        for v in [cv, lv, rv] {
            fixed_x.remove(&canon(v));
        }
    }
    let owned = vec![1usize];
    let frozen: HashSet<usize> = weld.keys().copied().collect();
    let empty_reference = Reference {
        anchors: Vec::new(),
        size_px,
        records: 0,
        n_anchors: 0,
        rel_min: None,
        rel_max: None,
        notes: Vec::new(),
    };
    let ctx = match assemble(
        parsed,
        up_global,
        &[],
        &empty_reference,
        size_px,
        &owned,
        &frozen,
        true,
        &fixed_x,
        true,
        specs,
        true,
    ) {
        Ok(ctx) => ctx,
        Err(reason) => return no(&reason, serde_json::json!({})),
    };
    Ok(ReleasedControls {
        ctx,
        connector_verts,
        owned,
    })
}

fn feature_constraints(
    shape: &PreparedShape<'_>,
    points: usize,
    connector_verts: &[usize],
) -> ShapeResult<FeatureConstraints> {
    let parsed = shape.parsed;
    let fitted = &shape.fitted;
    let captured = &shape.captured;
    let up_global = &shape.up_global;
    let feature = &shape.feature;
    let standard = shape.standard;
    let bla = shape.bla;
    let no_pts = parsed.oncurve.len();
    let global_index = |oncurve: bool, idx: usize| if oncurve { idx } else { no_pts + idx };
    // Hard rows over candidate absolute X (constant folds upstream X).
    // Every row below is an intended source relationship by name:
    // body-width, border-straightness (R/L), head-translation
    // (intrinsic), head-mid, cap-ratio.
    let n = points;
    let mut hard = NamedConstraints::new(n);
    // Both body borders stay straight constant-X: hard equal-displacement
    // rows for ALL R-group and ALL L-group verts (Shamir shared point).
    // Canonical order for determinism.
    {
        let mut r_sorted = feature.r_verts.clone();
        r_sorted.sort_unstable();
        r_sorted.dedup();
        for w in r_sorted.windows(2) {
            hard.push(
                up_global,
                "border-straightness-R",
                &[
                    (global_index(true, w[0]), 1.0),
                    (global_index(true, w[1]), -1.0),
                ],
                up_global[global_index(true, w[0])][0] - up_global[global_index(true, w[1])][0],
            );
        }
        let mut l_sorted = feature.l_verts.clone();
        l_sorted.sort_unstable();
        l_sorted.dedup();
        for w in l_sorted.windows(2) {
            hard.push(
                up_global,
                "border-straightness-L",
                &[
                    (global_index(true, w[0]), 1.0),
                    (global_index(true, w[1]), -1.0),
                ],
                up_global[global_index(true, w[0])][0] - up_global[global_index(true, w[1])][0],
            );
        }
    }
    // Body-width row: shared-border X minus body-left X equals S.
    let (r_rep, _) = parsed.contours[0][feature.body_r_seg].endpoints();
    hard.push(
        up_global,
        "body-width",
        &[
            (global_index(true, r_rep), 1.0),
            (global_index(true, bla), -1.0),
        ],
        standard,
    );
    // Translated original source head X profile with one shared
    // translation (Hobby control variables; Shamir shared feature
    // displacement). Source OFFCURVE X plus chain EXTREME endpoints are
    // copied; interior smooth oncurve knots stay free so existing G1
    // equations determine X under retained Y (Hersch 2 / TrueType
    // midpoint mechanism: oncurve X is weighted by adjacent retained-Y
    // legs between offcurve controls). Connector endpoints share the
    // same translation; the complete set is built BEFORE rows.
    let mut knot_degree: HashMap<usize, usize> = HashMap::new();
    for &sg in &feature.chain_segs {
        let (a, b) = parsed.contours[0][sg].endpoints();
        *knot_degree.entry(a).or_insert(0) += 1;
        *knot_degree.entry(b).or_insert(0) += 1;
    }
    // Conservative smoothness for intrinsic membership (exact; no
    // epsilon). Interior smooth knots stay free for G1; interior
    // sharp knots share the head translation to avoid kinks. Smooth if
    // raw source OR genuine captured source OR upstream is exactly
    // smooth: raw f64 scaling can move an original implicit TrueType
    // midpoint off exact collinearity by 1ULP, while the captured source
    // (producer-proof discrete outline) retains the exact G1. This is a
    // project adaptation (Hersch endpoint identities applied to the
    // producer's discrete proof), not a near-zero threshold.
    let src_map_pre = joints(parsed);
    let cap_map_pre = joints(captured);
    let up_map_pre = joints(fitted);
    let smooth_pre = |j: &usize| -> bool {
        src_map_pre
            .get(j)
            .is_some_and(|v| v.iter().any(|o| o.smooth))
            || cap_map_pre
                .get(j)
                .is_some_and(|v| v.iter().any(|o| o.smooth))
            || up_map_pre
                .get(j)
                .is_some_and(|v| v.iter().any(|o| o.smooth))
    };
    let mut intrinsic: Vec<(usize, f64)> = Vec::new();
    let mut seen_intrinsic: HashSet<usize> = HashSet::new();
    let push_intrinsic =
        |g: usize, x: f64, intrinsic: &mut Vec<(usize, f64)>, seen: &mut HashSet<usize>| {
            if seen.insert(g) {
                intrinsic.push((g, x));
            }
        };
    for &v in &feature.chain_verts {
        let deg = knot_degree.get(&v).copied().unwrap_or(0);
        if deg <= 1 || !smooth_pre(&v) {
            push_intrinsic(
                global_index(true, v),
                parsed.oncurve[v][0],
                &mut intrinsic,
                &mut seen_intrinsic,
            );
        }
    }
    for &c in &feature.chain_ctrls {
        push_intrinsic(
            global_index(false, c),
            parsed.offcurve[c][0],
            &mut intrinsic,
            &mut seen_intrinsic,
        );
    }
    for &v in connector_verts {
        push_intrinsic(
            global_index(true, v),
            parsed.oncurve[v][0],
            &mut intrinsic,
            &mut seen_intrinsic,
        );
    }
    if let Some(&(ref_g, _)) = intrinsic.first() {
        let ref_src = intrinsic[0].1;
        for &(g, src_x) in &intrinsic[1..] {
            hard.push(
                up_global,
                "head-translation",
                &[(g, 1.0), (ref_g, -1.0)],
                src_x - ref_src,
            );
        }
    }
    // Head-mid coupling: candidate width at the mid station equals the
    // decided standard times the source head/body ratio (Shamir cap
    // ratio anchored to neighbors; Hersch grid phase elsewhere).
    {
        let (seg_idx, t, src_width) = &feature.stations[1];
        let geometry::Segment::Quad { c, a, b } = parsed.contours[0][*seg_idx] else {
            return no("shape-feature-unsupported", serde_json::json!({}));
        };
        let u = 1.0 - t;
        let target = standard * (src_width / feature.w_body);
        hard.push(
            up_global,
            "head-mid",
            &[
                (global_index(true, r_rep), 1.0),
                (global_index(true, a), -u * u),
                (global_index(false, c), -2.0 * u * t),
                (global_index(true, b), -t * t),
            ],
            target,
        );
    }
    // Cap ratio anchored to its neighbors (Shamir ratio relation).
    if let Some((cap_v, left_v, right_v, f)) = feature.cap {
        hard.push(
            up_global,
            "cap-ratio",
            &[
                (global_index(true, cap_v), 1.0),
                (global_index(true, left_v), -(1.0 - f)),
                (global_index(true, right_v), -f),
            ],
            0.0,
        );
    } else {
        let (ta, tb) = parsed.contours[0][feature.head_r_seg].endpoints();
        let top = if parsed.oncurve[ta][1] >= parsed.oncurve[tb][1] {
            ta
        } else {
            tb
        };
        let direct = parsed.contours[0].iter().any(|sg| {
            let (a, b) = sg.endpoints();
            (a == top || b == top) && matches!(sg, geometry::Segment::Quad { .. })
        });
        if !direct {
            return no("shape-cap-unsupported", serde_json::json!({}));
        }
    }
    Ok(FeatureConstraints {
        named: hard,
        intrinsic,
    })
}

fn reconcile_owned_joints(
    shape: &PreparedShape<'_>,
    ctx: &mut model::SolveCtx,
    intrinsic: &[(usize, f64)],
) {
    let parsed = shape.parsed;
    let fitted = &shape.fitted;
    let captured = &shape.captured;
    let up_global = &shape.up_global;
    let feature = &shape.feature;
    let size_px = shape.size_px;
    let no_pts = parsed.oncurve.len();
    let global_index = |oncurve: bool, idx: usize| if oncurve { idx } else { no_pts + idx };
    // Smooth joints stay hard (G1). Conservative continuity: a join is
    // smooth if source OR original upstream is smooth (exact rational
    // classification; raw f64 1ULP off-collinearity never reclassifies
    // an upstream-smooth join as a kink). Sharp source corners owned by
    // the feature transform with source orientation plus feature rows;
    // their obsolete preserved-cross/tangent equalities are removed
    // where owned controls move (row identity and joint metadata stay
    // consistent). Native-Y mode untouched.
    {
        let src_map = joints(parsed);
        let cap_map = joints(captured);
        let up_map = joints(fitted);
        let smooth_of = |map: &HashMap<usize, Vec<model::JointOcc>>, j: usize| -> bool {
            map.get(&j).is_some_and(|v| v.iter().any(|o| o.smooth))
        };
        let complex: HashSet<usize> = feature
            .r_verts
            .iter()
            .map(|&v| global_index(true, v))
            .chain(feature.l_verts.iter().map(|&v| global_index(true, v)))
            .chain(intrinsic.iter().map(|&(g, _)| g))
            .chain(
                feature
                    .cap
                    .iter()
                    .map(|&(cv, _, _, _)| global_index(true, cv)),
            )
            .chain(feature.chain_verts.iter().map(|&v| global_index(true, v)))
            .chain(feature.chain_ctrls.iter().map(|&c| global_index(false, c)))
            .collect();
        // Map joint_rows index to ctx.rows index for Joint/White rows.
        let mut joint_row_pos: Vec<usize> = Vec::new();
        {
            let mut ji = 0usize;
            for (ri, (k, _, _)) in ctx.rows.iter().enumerate() {
                if matches!(k, RowKind::Joint | RowKind::White) {
                    // White rows have no joint metadata; only Joint rows
                    // advance the joint index in assemble order.
                    if matches!(k, RowKind::Joint) {
                        joint_row_pos.push(ri);
                        ji += 1;
                    }
                }
            }
            let _ = ji;
        }
        // Collect replacements/removals by joint_rows index.
        let mut replace_smooth: Vec<(usize, Vec<f64>, f64)> = Vec::new();
        let mut drop_joints: HashSet<usize> = HashSet::new();
        for (ji, jr) in ctx.joint_rows.iter().enumerate() {
            let cons_smooth = smooth_of(&src_map, jr.joint)
                || smooth_of(&cap_map, jr.joint)
                || smooth_of(&up_map, jr.joint);
            let iv = leg_vertex(jr.occ_prev, false);
            let ov = leg_vertex(jr.occ_seg, true);
            let touches_owned =
                complex.contains(&jr.joint) || complex.contains(&iv) || complex.contains(&ov);
            if cons_smooth {
                if !jr.smooth {
                    // Upgrade sharp defect row to hard G1 zero row with
                    // upstream-frozen coefficients (Hobby linearity).
                    if let Some((new_row, constant)) =
                        g1_row(up_global, jr.joint, jr.occ_prev, jr.occ_seg, size_px, true)
                    {
                        replace_smooth.push((ji, new_row, constant));
                    }
                }
            } else if touches_owned {
                // Sharp owned corner: obsolete preserved-cross/tangent
                // locks horizontal span under retained Y. Remove it;
                // orientation/nondegeneracy are post-checked.
                drop_joints.insert(ji);
            }
        }
        for (ji, new_row, constant) in replace_smooth {
            let ri = joint_row_pos[ji];
            ctx.rows[ri].1 = new_row;
            ctx.rows[ri].2 = constant;
            ctx.joint_rows[ji].smooth = true;
            ctx.joint_rows[ji].tangent = None;
        }
        if !drop_joints.is_empty() {
            // Consistent rebuild: drop the Joint rows and their joint
            // metadata together, preserving order for the rest.
            let mut new_rows = Vec::with_capacity(ctx.rows.len());
            let mut ji = 0usize;
            for (k, r, c) in ctx.rows.drain(..) {
                if matches!(k, RowKind::Joint) {
                    if drop_joints.contains(&ji) {
                        ji += 1;
                        continue;
                    }
                    ji += 1;
                }
                new_rows.push((k, r, c));
            }
            ctx.rows = new_rows;
            let mut filtered = Vec::with_capacity(ctx.joint_rows.len());
            for (idx, jr) in ctx.joint_rows.drain(..).enumerate() {
                if !drop_joints.contains(&idx) {
                    filtered.push(jr);
                }
            }
            ctx.joint_rows = filtered;
        }
    }
}
