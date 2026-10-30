//! Automatic source-shape preparation, assembly, solve and certification.

use super::*;

mod assembly;
mod certification;
use crate::diagonal_fitting as fitting;
use crate::diagonal_fitting::curve_model as model;
use certification::CandidateCertificate;

struct Abstention {
    reason: String,
    diagnostics: serde_json::Value,
}

type ShapeResult<T> = Result<T, Abstention>;

fn no<T>(reason: &str, diagnostics: serde_json::Value) -> ShapeResult<T> {
    Err(Abstention {
        reason: reason.to_string(),
        diagnostics,
    })
}

impl Abstention {
    fn into_fit(mut self, upstream: &[FittedCommand]) -> FitResult {
        self.diagnostics["model"] = serde_json::json!("coupled-shape-auto-01");
        FitResult {
            commands: upstream.to_vec(),
            applied: false,
            reason: format!("shape:{}", self.reason),
            diagnostics: self.diagnostics,
        }
    }
}

/// A recognized feature keeps raw shape authority separate from captured
/// standard certificates and the original upstream grid.
struct PreparedShape<'a> {
    parsed: &'a geometry::Parsed,
    fitted: geometry::Parsed,
    captured: geometry::Parsed,
    up_global: Vec<[f64; 2]>,
    weld: HashMap<usize, usize>,
    feature: ShapeFeature,
    standard: f64,
    bla: usize,
    size_px: f64,
    upstream_cmds: &'a [FittedCommand],
    specs: Vec<WhiteSpec>,
}

impl<'a> PreparedShape<'a> {
    fn new(
        parsed: &'a geometry::Parsed,
        source_captured: &[FittedCommand],
        upstream_cmds: &'a [FittedCommand],
        size_px: f64,
        reference: &Reference,
        native_axes: [bool; 2],
    ) -> ShapeResult<Self> {
        if native_axes != [false, false] {
            return no("automatic-axes-required", serde_json::json!({}));
        }
        let Ok(fitted) = geometry::parse_commands(upstream_cmds) else {
            return no("malformed-commands", serde_json::json!({}));
        };
        // Raw index graph correspondence plus finite/MAX guards before any
        // raw index dereference (Hobby 6: control variables are named by the
        // source outline graph). Exact contour data equality covers segment
        // variants and endpoint indices, not just counts.
        if !parsed
            .oncurve
            .iter()
            .chain(parsed.offcurve.iter())
            .flat_map(|p| [p[0], p[1]])
            .all(|v| v.is_finite())
        {
            return no("malformed-commands", serde_json::json!({}));
        }
        let source_units = parsed.oncurve.len()
            + parsed.offcurve.len()
            + parsed.contours.iter().map(|c| c.len()).sum::<usize>();
        if source_units > MAX_COMMANDS || upstream_cmds.len() > MAX_COMMANDS {
            return no("oversize-outline", serde_json::json!({}));
        }
        let topology_match = parsed.contours.len() == fitted.contours.len()
            && parsed.oncurve.len() == fitted.oncurve.len()
            && parsed.offcurve.len() == fitted.offcurve.len()
            && parsed.contours == fitted.contours;
        if !topology_match
            || parsed.contours.len() != 1
            || parsed
                .contours
                .iter()
                .flatten()
                .any(|s| matches!(s, geometry::Segment::Cubic { .. }))
            || !contour_closed(parsed)
        {
            return no("unsupported-correspondence", serde_json::json!({}));
        }
        let up_global: Vec<[f64; 2]> = fitted
            .oncurve
            .iter()
            .chain(fitted.offcurve.iter())
            .copied()
            .collect();
        if up_global
            .iter()
            .flat_map(|p| [p[0], p[1]])
            .any(|v| v * 64.0 != (v * 64.0).round())
        {
            return no("upstream-not-26.6", serde_json::json!({}));
        }
        let weld = weld_map(parsed);
        if weld != weld_map(&fitted) {
            return no("weld-mismatch", serde_json::json!({}));
        }
        let Some(feature) = extract_shape_feature(parsed, &fitted) else {
            return no("shape-feature-unsupported", serde_json::json!({}));
        };
        // Narrower-head eligibility from the old source class (fail closed):
        // the head is a genuinely narrower feature than the body.
        if !(0.0 < feature.w_head_mid
            && feature.w_head_mid < feature.w_body
            && 0.0 < feature.w_head_min
            && feature.w_head_min < feature.w_body)
        {
            return no("shape-feature-unsupported", serde_json::json!({}));
        }
        // Standard and class stay on the existing certified certificates
        // (captured-source DonorCert); shape authority below is raw.
        let Ok(captured) = geometry::parse_commands(source_captured) else {
            return no("shape-standard-unavailable", serde_json::json!({}));
        };
        let Some(captured_feature) = extract_shape_feature(&captured, &fitted) else {
            return no("shape-standard-unavailable", serde_json::json!({}));
        };
        let Some(standard) =
            fitting::upright::certified_standard(reference, captured_feature.w_body)
        else {
            return no("shape-standard-unavailable", serde_json::json!({}));
        };
        // Fitted body width from the body borders.
        let geometry::Segment::Line { a: bla, .. } = parsed.contours[0][feature.body_l_seg] else {
            return no("shape-feature-unsupported", serde_json::json!({}));
        };
        let fx_l = fitted.oncurve[bla][0];
        let fx_r = {
            let (a, _) = parsed.contours[0][feature.body_r_seg].endpoints();
            fitted.oncurve[a][0]
        };
        let w_up = fx_r - fx_l;
        if w_up == standard {
            return no(
                "shape-already-standard",
                serde_json::json!({ "standard": standard }),
            );
        }
        let (features, white_reason) = white_contacts_parsed_depths(parsed, &[0, 2, 3, 4]);
        if let Some(reason) = white_reason {
            return no(&reason, serde_json::json!({}));
        }
        let specs: Vec<WhiteSpec> = features.iter().map(|f| f.spec.clone()).collect();

        Ok(Self {
            parsed,
            fitted,
            captured,
            up_global,
            weld,
            feature,
            standard,
            bla,
            size_px,
            upstream_cmds,
            specs,
        })
    }
}

pub(super) fn fit(
    parsed: &geometry::Parsed,
    source_captured: &[FittedCommand],
    upstream_cmds: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
    collect_witness: bool,
) -> Result<FitResult, Error> {
    require_finite_positive_size(size_px)?;
    let result = PreparedShape::new(
        parsed,
        source_captured,
        upstream_cmds,
        size_px,
        reference,
        native_axes,
    )
    .and_then(|shape| run(shape, collect_witness));
    Ok(result.unwrap_or_else(|reason| reason.into_fit(upstream_cmds)))
}

struct NamedConstraint {
    name: &'static str,
    coefficients: Vec<f64>,
    constant: f64,
}

struct NamedConstraints {
    points: usize,
    rows: Vec<NamedConstraint>,
}

struct ReleasedControls {
    ctx: model::SolveCtx,
    connector_verts: Vec<usize>,
    owned: Vec<usize>,
}

struct MovementBudget {
    body: f64,
    head: f64,
    shared: f64,
    metadata: serde_json::Value,
}

struct ColumnLimits {
    bounds: Vec<f64>,
    public_caps: Vec<f64>,
}

struct FeatureConstraints {
    named: NamedConstraints,
    intrinsic: Vec<(usize, f64)>,
}

struct AssembledShape {
    released: ReleasedControls,
    budget: MovementBudget,
    hard: NamedConstraints,
}

struct SolvedShape {
    commands: Vec<FittedCommand>,
    displacements: Vec<f64>,
    peak: f64,
    qp: Option<model::QpInfo>,
    public_caps: Vec<f64>,
}

fn solve_shape(
    shape: &PreparedShape<'_>,
    system: &AssembledShape,
    collect_witness: bool,
) -> ShapeResult<SolvedShape> {
    let parsed = shape.parsed;
    let fitted = &shape.fitted;
    let up_global = &shape.up_global;
    let weld = &shape.weld;
    let feature = &shape.feature;
    let standard = shape.standard;
    let upstream_cmds = shape.upstream_cmds;
    let ctx = &system.released.ctx;
    let owned = &system.released.owned;
    let hard = &system.hard;
    let caps_meta = &system.budget.metadata;
    let n_hard = hard.rows.len();
    let (mat, rhs, kinds) = restricted_matrix(ctx, weld);
    if mat.is_empty() || rhs.is_empty() || ctx.cols.is_empty() {
        return no("shape-solve-incompatible", serde_json::json!({}));
    }
    let ColumnLimits {
        bounds,
        public_caps,
    } = system
        .budget
        .column_limits(shape, ctx, &system.released.connector_verts);
    // Automatic source-shape mode only: elastic Phase-I start repairs an
    // equality minimum-norm start outside the per-column boxes when a
    // feasible point exists (same BOUNDED_TOL, same bounds). Native-Y keeps
    // the legacy strict entry untouched.
    let (sol, peak, qp) = match hard_solve_bounded_phase1(&mat, &rhs, &kinds, &bounds) {
        Ok(v) => v,
        Err(reason) => {
            // The production dispatcher discards failed-stage diagnostics.
            // Only explicit diagnostic calls need a second solve and the full
            // binding witness; neither affects selection or fallback geometry.
            if !collect_witness {
                return no(
                    &format!("shape-solve-{reason}"),
                    serde_json::json!({ "n_hard_rows": n_hard, "caps": caps_meta }),
                );
            }
            // Smallest exact binding witness (not a representation limit):
            // retry once with a finite large bound. If that succeeds, the
            // binding constraint is the single movement budget; name the
            // exceeded columns. If it still fails, the binding constraint
            // is among the named intended relationships themselves.
            let big = vec![1e6; bounds.len()];
            // No speculative constraint drops: the witness below names the
            // binding intended relationship instead of hunting pixels.
            // Same Phase-I entry with large bounds distinguishes bound
            // from equality infeasibility under identical start repair.
            let retry = hard_solve_bounded_phase1(&mat, &rhs, &kinds, &big);
            let (finite_retry_ok, exceeded) = match &retry {
                Ok((s2, _, _)) => {
                    let exc: Vec<serde_json::Value> = s2
                        .iter()
                        .zip(&bounds)
                        .enumerate()
                        .filter(|(_, (x, b))| x.abs() > **b)
                        .map(|(ci, (x, b))| {
                            serde_json::json!({
                                "point": ctx.cols[ci].0, "axis": ctx.cols[ci].1,
                                "disp": x, "bound": b,
                            })
                        })
                        .collect();
                    (true, exc)
                }
                Err(_) => (false, Vec::new()),
            };
            // Smallest exact binding witness with its intended relationship
            // (body-width, border-straightness, head translation, head-mid,
            // cap-ratio, or retained smooth G1). Returned in diagnostics for
            // the experiment adapter to save; the kernel writes no files.
            let intended = hard.names();
            let witness = serde_json::json!({
                "reason": reason,
                "n_hard_rows": n_hard,
                "hard_names": intended,
                "finite_retry_ok": finite_retry_ok,
                "bound_exceeded_points": exceeded,
                "caps": caps_meta,
                "public_caps": public_caps,
                "solver_bounds": bounds,
                "cols": ctx.cols,
                "n_cols": ctx.cols.len(),
                "mat": mat,
                "rhs": rhs,
                "kinds": kinds.iter().map(|k| match k {
                    RowKind::Joint => "Joint",
                    RowKind::White => "White",
                    RowKind::Shape => "Shape",
                    RowKind::Ink => "Ink",
                }).collect::<Vec<_>>(),
                "up_global": up_global,
                "source_oncurve": parsed.oncurve,
                "source_offcurve": parsed.offcurve,
                "upstream_oncurve": fitted.oncurve,
                "upstream_offcurve": fitted.offcurve,
                "r_verts": feature.r_verts,
                "l_verts": feature.l_verts,
                "chain_segs": feature.chain_segs,
                "chain_verts": feature.chain_verts,
                "chain_ctrls": feature.chain_ctrls,
                "cap": feature.cap,
                "stations": feature.stations,
                "w_body": feature.w_body,
                "w_head_mid": feature.w_head_mid,
                "standard": standard,
            });
            return no(
                &format!("shape-solve-{reason}"),
                serde_json::json!({
                    "n_hard_rows": n_hard,
                    "hard_names": intended,
                    "finite_retry_ok": finite_retry_ok,
                    "bound_exceeded_points": exceeded,
                    "caps": caps_meta,
                    "witness": witness,
                }),
            );
        }
    };
    // Joint rows were already filtered consistently before the solve;
    // sharp owned corners rely on orientation/nondegeneracy postchecks.
    let map = joints(parsed);
    let degenerate: Vec<[usize; 3]> = degenerate_triples(&map);
    let ok = match run_prefixes(
        ctx,
        &sol,
        weld,
        owned,
        &degenerate,
        parsed,
        upstream_cmds,
        fitted,
    ) {
        Ok(v) => v,
        Err(fail) => {
            return no(
                &fail.reason,
                serde_json::json!({ "n_hard_rows": n_hard, "attempts": fail.tried, "extra": fail.extra }),
            );
        }
    };
    Ok(SolvedShape {
        commands: ok.out.clone(),
        displacements: sol,
        peak,
        qp,
        public_caps,
    })
}

fn run(shape: PreparedShape<'_>, collect_witness: bool) -> ShapeResult<FitResult> {
    let system = AssembledShape::new(&shape)?;
    let solved = solve_shape(&shape, &system, collect_witness)?;
    let checks = CandidateCertificate::new(&shape, &system, &solved)?.verify()?;
    let mut selected = FitResult {
        commands: solved.commands,
        applied: true,
        reason: "shape-candidate".to_string(),
        diagnostics: serde_json::json!({}),
    };
    selected.diagnostics["model"] = serde_json::json!("coupled-shape-auto-01");
    selected.diagnostics["shape_prototype"] = serde_json::json!({
        "standard": shape.standard, "peak": solved.peak, "qp": solved.qp.as_ref().map(qp_json),
        "n_hard_rows": system.hard.rows.len(), "hard_names": system.hard.names(), "checks": checks,
        "caps": system.budget.metadata,
    });
    Ok(selected)
}
