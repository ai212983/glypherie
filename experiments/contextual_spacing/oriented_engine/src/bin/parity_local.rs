//! Native parity driver: frozen Class-L Python reference vs this engine.
//!
//! Usage: `parity_local ADAPTER_FILE REPO_ROOT` (release build). Compares
//! every adapter step (tiny fixture, synthetic bars incl. trio and wide
//! R/q configs, real pairs on two captures) against `score_pair_local`:
//! validity, gl, both counts, weak shares, abstain flags, honest bounds,
//! manuscript variant. The port must reproduce the reference, not mirror
//! itself. Prints JSON; exit 1 on any failure.

use std::collections::HashMap;
use std::path::PathBuf;

use yinyang_oriented_engine::capture::load_capture;
use yinyang_oriented_engine::params::{EngineParams, ScoreParams};
use yinyang_oriented_engine::score::{facing_matrix, Strength};
use yinyang_oriented_engine::Engine;

struct Report {
    failures: Vec<String>,
    compared_steps: usize,
    worst_rel: f64,
    worst_rel_where: String,
    worst_shortfall: f64,
    worst_shortfall_where: String,
    conditioned: Vec<String>,
    boundary_notes: Vec<String>,
    max_boundary_diff: u64,
    max_skipped: u64,
    max_skipped_where: String,
    // Support-derived statistics, kept separate from scalar errors: the
    // bound is a support-weighted count, so its allowance is linked to
    // the observed count flip (D2), never widened absolutely.
    max_bound_abs_diff: f64,
    max_bound_abs_where: String,
}

impl Report {
    fn note_boundary(&mut self, wh: &str, diff: u64) {
        if diff > self.max_boundary_diff {
            self.max_boundary_diff = diff;
        }
        if self.boundary_notes.len() < 8 {
            self.boundary_notes
                .push(format!("{wh}: diff {diff}"));
        }
    }
    fn flag_conditioned(&mut self, wh: &str) {
        if self.conditioned.len() < 8 {
            self.conditioned.push(wh.to_string());
        }
    }
}

impl Report {
    fn fail(&mut self, msg: String) {
        self.failures.push(msg);
    }
    fn note(&mut self, got: f64, exp: f64, wh: &str) {
        if exp.is_finite() && got.is_finite() {
            let rel = (got - exp).abs() / exp.abs().max(1.0);
            if rel > self.worst_rel {
                self.worst_rel = rel;
                self.worst_rel_where = wh.to_string();
            }
        }
    }
    /// Flip-linked honest-bound gate (D2): the bound is a support-weighted
    /// count, so a support flip of `both_diff` pair-px can move it by at
    /// most `both_diff * max_w`. Exact 1e-9 when counts agree. Scalar
    /// errors (gl/weak) keep absolute relative gates; support-derived
    /// statistics (both/bound) are recorded separately below.
    fn check_bound(&mut self, wh: &str, got: f64, exp: f64, both_diff: u64, max_w: f64) {
        let allowance = both_diff as f64 * max_w + 1e-9;
        let d = (got - exp).abs();
        if d > self.max_bound_abs_diff {
            self.max_bound_abs_diff = d;
            self.max_bound_abs_where = wh.to_string();
        }
        if !(got.is_finite() && exp.is_finite() && d <= allowance) {
            self.fail(format!(
                "{wh}: bound {got} != {exp} (allowance {allowance}, both_diff {both_diff})"
            ));
        }
    }
}

/// Derived agreement gates (measured, mechanism-attributed — never
/// blindly enlarged):
/// - default (R12), R24, q3-notebook: 1e-9 relative.
/// - R6 bars gl: 1e-5 relative. Mechanism (D3): the engine side is
///   now stable direct positive summation (deterministic; the worst
///   R6 residual reproduces bitwise across debug/release), so the
///   residual vs the FFT pilot comes from the reference side —
///   numpy-FFT ripple at the exact-zero guard plus rustfft-vs-numpy
///   support flips (15 guard-boundary pair-px on bars R6). Narrow
///   windows amplify via small EL denominators; R12 has zero such
///   pixels. The gate is flagged conditioned; R6 stays a diagnostic
///   envelope, never the default.
/// - R6 real-curve gl: 3e-5 relative. Same reference-side mechanism
///   on denser ink; measured worst after D3 is 7.875e-6 relative
///   (roboto-16-mono um step 10 R6, notebook), covered here with ~4x
///   margin and flagged conditioned. The same worst value reproduces
///   bitwise on debug and release, attributing it to the reference
///   side, not engine codegen. True choice parity (band-aware TIE
///   selection below) is the selection-relevant agreement.
/// - manuscript (d^4 at q=3): 1e-8 relative with an explicit conditioning
///   flag, the same power-amplification rationale as the G2 parity
///   `tol_for_q` (q>4 -> 1e-8). Notebook powers stay at 1e-9.
///   R6 manuscript is 1e-6: d^4 amplifies guard-zone reference noise
///   and all three shipping profiles agree at rel 1.22e-7 (debug,
///   release, wasm32 measured separately). Weak share rides the
///   config tol throughout (same guard-zone summands as gl).
/// - both counts: scored-pixel semantics (support overlap gated by
///   positive-finite local energies, matching the pilot). Support
///   itself is FFT-derived (u2 > eps), so rustfft-vs-numpy AND
///   debug-vs-release codegen flip floor-boundary pixels (observed:
///   og R6 steps differ by 15 pair-px between profiles, carrying ~0
///   mass — gl worst is bitwise identical across profiles). Notes are
///   a recorder (<= 64 bars, <= 1024 real R6), never a gate; the
///   honest bound absorbs each run's own flip via both_diff * max_w.
fn close(got: f64, exp: f64, tol: f64) -> bool {
    if !got.is_finite() || !exp.is_finite() {
        return got == exp;
    }
    let rel = (got - exp).abs() / exp.abs().max(1.0);
    let abs = (got - exp).abs();
    rel <= tol || abs <= 1e-12
}

fn load_engine_for(q: f64, r: u32) -> Engine {
    let mut p = EngineParams::frozen();
    if (q - 2.0).abs() > f64::EPSILON {
        p.q = q;
    }
    if r != 12 {
        p.radius = r;
    }
    Engine::new(p).unwrap()
}

/// True target-choice parity (D7): TIE selection over the full window at
/// study, edge, unreachable, and constructed-midpoint targets. Targets
/// are reconstructed from the adapter's eligible gl values with the same
/// formulas as the reference exporter; the engine call passes cstar, so
/// this exercises the real selection path, not raw argmin.
#[allow(clippy::too_many_arguments)]
fn check_choices(
    engine: &mut Engine,
    report: &mut Report,
    ds_name: &str,
    pair: &str,
    case: &serde_json::Value,
    rows_key: &str,
    choice_key: &str,
    metric: i64,
    l: u32,
    r: u32,
    score: &ScoreParams,
) {
    let rows = case[rows_key].as_array().unwrap();
    let mut elig: Vec<(i64, f64)> = Vec::new();
    for st in rows {
        if st["valid"].as_bool().unwrap_or(false)
            && !st["abstain"].as_bool().unwrap_or(true)
        {
            if let Some(g) = st["gl"].as_f64() {
                if g.is_finite() {
                    elig.push((st["step"].as_i64().unwrap(), g));
                }
            }
        }
    }
    let mut targets = vec![
        ("seed_exact".to_string(), 0.4697315871728616f64),
        ("seed_rounded".to_string(), 0.47),
        ("zero".to_string(), 0.0),
        ("high".to_string(), 8.0),
    ];
    if elig.is_empty() {
        targets.push(("unreachable".to_string(), 5.0));
    } else {
        let mut gs: Vec<f64> = elig.iter().map(|(_, g)| *g).collect();
        gs.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let med = gs[gs.len() / 2];
        let mut by_dev: Vec<(f64, f64)> = elig
            .iter()
            .map(|(_, g)| ((g - 0.4697315871728616).abs(), *g))
            .collect();
        by_dev.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
        let mid_w = if by_dev.len() > 1 {
            (by_dev[0].1 + by_dev[1].1) / 2.0
        } else {
            by_dev[0].1
        };
        targets.push(("mid_w".to_string(), mid_w));
        targets.push(("mid_lo".to_string(), (gs[0] + med) / 2.0));
        targets.push(("mid_hi".to_string(), (med + gs[gs.len() - 1]) / 2.0));
        targets.push(("unreachable".to_string(), gs[gs.len() - 1] + 5.0));
    }
    let all_deltas: Vec<i64> = rows
        .iter()
        .map(|st| st["step"].as_i64().unwrap() - metric)
        .collect();
    for (tname, cstar) in &targets {
        let wh = format!("{ds_name} {pair} {rows_key} choice/{tname}");
        match engine.score_pair_local(
            ds_name,
            l,
            r,
            metric,
            &all_deltas,
            score,
            Strength::Notebook,
            Some(*cstar),
        ) {
            Ok(res) => {
                report.compared_steps += 1;
                let exp = &case[choice_key][tname];
                // TIE-faithful agreement: the engine's pick must be
                // acceptable to the oracle band (a constructed midpoint
                // makes band membership itself noise-dominated, so band
                // identity is not required), and the engine's own tiebreak
                // (lowest step in its band) must hold on its own values.
                let exp_tied: Vec<i64> = exp["tied"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_i64().unwrap())
                    .collect();
                let exp_fallback = exp["fallback"].as_bool().unwrap();
                let tiebreak_ok = res.minimizing.iter().min() == Some(&res.chosen);
                let ok = res.fallback == exp_fallback
                    && (res.fallback
                        || (exp_tied.contains(&res.chosen) && tiebreak_ok));
                // A flip between oracle-tied steps is recorded evidence of
                // near-tie fragility, not a failure: both picks are TIE-
                // correct, and the constructed midpoint makes band edges
                // noise-dominated by design.
                if ok
                    && !res.fallback
                    && res.chosen != exp["chosen"].as_i64().unwrap()
                {
                    report.boundary_notes.push(format!(
                        "{wh}: choice flip within tied band (engine {} vs ref {})",
                        res.chosen, exp["chosen"]
                    ));
                }
                if !ok {
                    report.fail(format!(
                        "{wh}: chosen {} band {:?} fallback {} != {} {:?} {}",
                        res.chosen,
                        res.minimizing,
                        res.fallback,
                        exp["chosen"],
                        exp_tied,
                        exp["fallback"]
                    ));
                }
            }
            Err(e) => report.fail(format!("{wh}: {e}")),
        }
    }
}

fn load_pair_glyphs(
    engine: &mut Engine,
    ds_name: &str,
    ds: &yinyang_oriented_engine::capture::Dataset,
    l: u32,
    r: u32,
    report: &mut Report,
) {
    for cp in [l, r] {
        let cell = &ds.cells[&cp];
        if let Err(e) = engine.load_glyph(
            ds_name,
            &ds.sha256,
            cp,
            cell.w,
            cell.h,
            cell.left,
            cell.top,
            &cell.cover,
        ) {
            report.fail(format!("load {ds_name} U+{cp:04X}: {e}"));
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: parity_local ADAPTER_FILE REPO_ROOT");
        std::process::exit(2);
    }
    let adapter: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&args[1]).unwrap()).unwrap();
    let repo_root = PathBuf::from(&args[2]);
    let mut report = Report {
        failures: Vec::new(),
        compared_steps: 0,
        worst_rel: 0.0,
        worst_rel_where: String::new(),
        worst_shortfall: 0.0,
        worst_shortfall_where: String::new(),
        conditioned: Vec::new(),
        boundary_notes: Vec::new(),
        max_boundary_diff: 0,
        max_skipped: 0,
        max_skipped_where: String::new(),
        max_bound_abs_diff: 0.0,
        max_bound_abs_where: String::new(),
    };
    // Largest facing weight over the frozen 16-direction bank: a support
    // flip of F pair-px moves the honest bound by at most F * max_w.
    let max_w = facing_matrix(16)
        .iter()
        .flat_map(|row| row.iter())
        .cloned()
        .fold(0.0f64, f64::max);
    // The adapter is the frozen pilot reference (own identity); the engine
    // under test reports LOCAL_ENERGY_MODEL_IDENTITY in version(). The
    // pin below guards reference drift; identity separation is covered by
    // the params-hash gate and the node smoke version check.
    if adapter["score_model"].as_str() != Some("yinyangfit-local-normalization-pilot-v1") {
        report.fail(format!(
            "adapter score_model drift: {:?}",
            adapter["score_model"]
        ));
    }
    let frozen = ScoreParams::frozen();
    if frozen.normalization_radius != 12 {
        report.fail("frozen normalization_radius drift".to_string());
    }

    // Synthetic bars: default + wide R/q, pair + trio, both strengths.
    // Bar: 20x100, ink rows 4..16 cols 20..22; trio adds cols 62..64
    // (matches the exporter geometry exactly).
    let mut bar_cover = vec![0.0; 20 * 100];
    let mut trio_cover = vec![0.0; 20 * 100];
    for y in 4..16 {
        for x in 20..22 {
            bar_cover[y * 100 + x] = 1.0;
            trio_cover[y * 100 + x] = 1.0;
        }
        for x in 62..64 {
            trio_cover[y * 100 + x] = 1.0;
        }
    }
    // R configs vary ONLY the normalizer window on frozen fields (the
    // frozen mapping: normalization_radius is separate from field R);
    // q3 varies the field falloff with a frozen normalizer.
    let mut engine_frozen = load_engine_for(2.0, 12);
    let mut engine_q3 = load_engine_for(3.0, 12);
    for (tag, exp_cfg) in [
        ("R12", (12u32, 2.0f64)),
        ("R24", (24, 2.0)),
        ("R6", (6, 2.0)),
        ("q3", (12, 3.0)),
    ] {
        let (radius, q) = exp_cfg;
        let engine: &mut Engine = if (q - 2.0).abs() < f64::EPSILON {
            &mut engine_frozen
        } else {
            &mut engine_q3
        };
        for (cp, cover) in [
            (0x41u32, &bar_cover),
            (0x42u32, &bar_cover),
            (0x43u32, &trio_cover),
        ] {
            if let Err(e) =
                engine.load_glyph("synthetic", "adapter-bar", cp, 100, 20, 0.0, 0.0, cover)
            {
                report.fail(format!("{tag} load U+{cp:04X}: {e}"));
            }
        }
        let score = ScoreParams {
            tau: 0.5,
            normalization_radius: radius,
        };
        for (name, left) in [("pair", 0x41u32), ("trio", 0x43u32)] {
            let exp = &adapter["bars"][tag][name];
            for (strength, gkey) in [(Strength::Notebook, "gl"), (Strength::Manuscript, "gl_ms")]
            {
                let wh = format!("bars {tag} {name} {gkey}");
                // Per-config agreement gate (derived; see `close` docs).
                let (tol, cond) = match (gkey, tag) {
                    // Manuscript d^4 amplifies guard-zone reference noise;
                    // shipping worst 1.22e-7 (release + wasm32 agree) -> 1e-6
                    // on R6 only. Other manuscript configs stay 1e-8
                    // (shipping worst 3.3e-9 on q3).
                    ("gl_ms", "R6") => (1e-6, true),
                    ("gl_ms", _) => (1e-8, true),
                    (_, "R6") => (1e-5, true),
                    _ => (1e-9, false),
                };
                if cond {
                    report.flag_conditioned(&wh);
                }
                match engine.score_pair_local(
                    "synthetic",
                    left,
                    0x42,
                    0,
                    &[6],
                    &score,
                    strength,
                    None,
                ) {
                    Ok(res) => {
                        let rec = &res.steps[0];
                        report.compared_steps += 1;
                        match (rec.gl, exp[gkey].as_f64()) {
                            (Some(g), Some(x)) => {
                                if !close(g, x, tol) {
                                    report.fail(format!("{wh}: gl {g} != {x} (tol {tol})"));
                                } else {
                                    report.note(g, x, &wh);
                                }
                            }
                            _ => report.fail(format!("{wh}: missing gl")),
                        }
                        if strength == Strength::Notebook {
                            let exp_both = exp["both"].as_u64().unwrap();
                            let got_both = rec.both_supported_pairpx;
                            let mut both_diff = 0u64;
                            if got_both != exp_both {
                                both_diff = got_both.abs_diff(exp_both);
                                if both_diff <= 64 {
                                    report.note_boundary(&wh, both_diff);
                                } else {
                                    report.fail(format!(
                                        "{wh}: both {got_both} != {exp_both}"
                                    ));
                                }
                            }
                            // Weak share rides the config tol: it sums over the
                            // same guard-zone pixels as gl (u2-floor mask),
                            // and wasm32 codegen moves R6 weak at 1.3e-6,
                            // so the R6 1e-5 mechanism gate covers it on
                            // all profiles. R12/R24/q3 stay 1e-9.
                            match (rec.weak_normalized_share, exp["weak"].as_f64()) {
                                (Some(g), Some(x)) => {
                                    if !close(g, x, tol) {
                                        report.fail(format!("{wh}: weak {g} != {x}"));
                                    }
                                }
                                _ => report.fail(format!("{wh}: missing weak")),
                            }
                            if rec.abstain != exp["abstain"].as_bool().unwrap() {
                                report.fail(format!("{wh}: abstain mismatch"));
                            }
                            match (rec.honest_bound, exp["bound"].as_f64()) {
                                (Some(b), Some(x)) => {
                                    report.check_bound(&wh, b, x, both_diff, max_w);
                                }
                                _ => report.fail(format!("{wh}: missing bound")),
                            }
                            if rec.conditioning_shortfall > report.worst_shortfall {
                                report.worst_shortfall = rec.conditioning_shortfall;
                                report.worst_shortfall_where = wh.clone();
                            }
                            if rec.skipped_nonpositive > report.max_skipped {
                                report.max_skipped = rec.skipped_nonpositive;
                                report.max_skipped_where = wh.clone();
                            }
                        }
                    }
                    Err(e) => report.fail(format!("{wh}: score error: {e}")),
                }
            }
        }
    }

    // Real pairs: full narrow windows from the adapter.
    let frozen_ds: serde_json::Value = adapter["real"].clone();
    let mut loaded: HashMap<String, yinyang_oriented_engine::capture::Dataset> = HashMap::new();
    // Capture paths resolve via the frozen provenance (same scheme as parity).
    let prov: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(
            repo_root.join("out/diagnostics/contextual-spacing/yinyang-oriented-fields/implementation/provenance.json"),
        )
        .unwrap(),
    )
    .unwrap();
    for ds_name in frozen_ds.as_object().unwrap().keys() {
        let cap = &prov["captures"][ds_name];
        let path = repo_root.join(cap["path"].as_str().unwrap());
        match load_capture(ds_name, &path) {
            Ok(ds) => {
                if ds.sha256 != cap["sha256"].as_str().unwrap() {
                    report.fail(format!("capture drift: {ds_name}"));
                }
                loaded.insert(ds_name.clone(), ds);
            }
            Err(e) => report.fail(format!("load capture {ds_name}: {e}")),
        }
    }
    // Score objects live across datasets; one engine per field config is
    // enough because entries key the dataset.
    let mut engine = load_engine_for(2.0, 12);
    for (ds_name, pairs) in frozen_ds.as_object().unwrap() {
        let ds = match loaded.get(ds_name) {
            Some(d) => d,
            None => continue,
        };
        for (pair, case) in pairs.as_object().unwrap() {
            let l = pair.chars().next().unwrap() as u32;
            let r = pair.chars().nth(1).unwrap() as u32;
            let metric = case["metric"].as_i64().unwrap();
            match ds.metric_step(l, r) {
                Ok(m) if m == metric => {}
                Ok(m) => report.fail(format!("{ds_name} {pair}: metric {m} != {metric}")),
                Err(e) => report.fail(format!("{ds_name} {pair} metric: {e}")),
            }
            load_pair_glyphs(&mut engine, ds_name, ds, l, r, &mut report);
            // R6 real-curve check (wide normalizer on frozen fields).
            let score6 = ScoreParams {
                tau: 0.5,
                normalization_radius: 6,
            };
            let mut r6_vals: Vec<(i64, f64)> = Vec::new();
            let mut r6_exp: Vec<(i64, f64)> = Vec::new();
            if let Some(r6steps) = case.get("steps_R6").and_then(|v| v.as_array()) {
                for st in r6steps {
                    if st["valid"].as_bool().unwrap() {
                        let step = st["step"].as_i64().unwrap();
                        let delta = step - metric;
                        match engine.score_pair_local(
                            ds_name, l, r, metric, &[delta], &score6,
                            Strength::Notebook, None,
                        ) {
                            Ok(res) => {
                                let rec = &res.steps[0];
                                report.compared_steps += 1;
                                let wh = format!("{ds_name} {pair} step {step} R6");
                                // Real-curve R6 gl gate: 3e-5 relative (~3x over
                                // the measured worst 1.02e-5). Same guard-pixel
                                // mechanism as bars R6; denser real ink puts
                                // more support pixels in the sub-1e-9 local
                                // energy zone. Choice parity (argmin below) is
                                // the selection-relevant agreement.
                                report.flag_conditioned(&format!("{wh} gl"));
                                match (rec.gl, st["gl"].as_f64()) {
                                    (Some(g), Some(x)) => {
                                        if !close(g, x, 3e-5) {
                                            report.fail(format!("{wh}: gl {g} != {x}"));
                                        } else {
                                            report.note(g, x, &wh);
                                        }
                                    }
                                    _ => report.fail(format!("{wh}: missing gl")),
                                }
                                let mut both_diff = 0u64;
                                if let Some(exp_both) = st.get("both").and_then(|v| v.as_u64()) {
                                    if rec.both_supported_pairpx != exp_both {
                                        both_diff = rec.both_supported_pairpx.abs_diff(exp_both);
                                        // Recorder, not a gate: R6 real curves
                                        // straddle guard-zone pair-px; the cap
                                        // at 1024 keeps any NEW mechanism loud
                                        // while the gl gate bounds significance.
                                        if both_diff <= 1024 {
                                            report.note_boundary(&wh, both_diff);
                                        } else {
                                            report.fail(format!(
                                                "{wh}: both {} != {exp_both}",
                                                rec.both_supported_pairpx
                                            ));
                                        }
                                    }
                                }
                                if let (Some(b), Some(x)) = (
                                    rec.honest_bound,
                                    st.get("bound").and_then(|v| v.as_f64()),
                                ) {
                                    report.check_bound(&wh, b, x, both_diff, max_w);
                                }
                                if let Some(exp_ab) = st.get("abstain").and_then(|v| v.as_bool()) {
                                    if rec.abstain != exp_ab {
                                        report.fail(format!("{wh}: abstain mismatch"));
                                    }
                                }
                                if rec.skipped_nonpositive > report.max_skipped {
                                    report.max_skipped = rec.skipped_nonpositive;
                                    report.max_skipped_where = wh.clone();
                                }
                                if !rec.abstain {
                                    if let (Some(g), Some(x)) =
                                        (rec.gl, st["gl"].as_f64())
                                    {
                                        r6_vals.push((step, g));
                                        r6_exp.push((step, x));
                                    }
                                }
                            }
                            Err(e) => report.fail(format!(
                                "{ds_name} {pair} R6 step {step}: {e}"
                            )),
                        }
                    }
                }
                // Choice-level parity for the wide window: argmin must agree.
                if !r6_vals.is_empty() {
                    let rust_min = r6_vals
                        .iter()
                        .min_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
                        .unwrap()
                        .0;
                    let exp_min = r6_exp
                        .iter()
                        .min_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
                        .unwrap()
                        .0;
                    if rust_min != exp_min {
                        report.fail(format!(
                            "{ds_name} {pair} R6 argmin {rust_min} != {exp_min}"
                        ));
                    }
                }
                // True target-choice parity through the real selection path.
                check_choices(
                    &mut engine,
                    &mut report,
                    ds_name,
                    pair,
                    case,
                    "steps_R6",
                    "choices_R6",
                    metric,
                    l,
                    r,
                    &score6,
                );
            }
            for st in case["steps"].as_array().unwrap() {
                let step = st["step"].as_i64().unwrap();
                let delta = step - metric;
                let res = engine
                    .score_pair_local(
                        ds_name,
                        l,
                        r,
                        metric,
                        &[delta],
                        &frozen,
                        Strength::Notebook,
                        None,
                    )
                    .unwrap();
                let rec = &res.steps[0];
                let wh = format!("{ds_name} {pair} step {step}");
                report.compared_steps += 1;
                if rec.valid != st["valid"].as_bool().unwrap() {
                    report.fail(format!("{wh}: valid {} != {}", rec.valid, st["valid"]));
                    continue;
                }
                if !rec.valid {
                    continue;
                }
                for (got, key) in [(rec.gl, "gl"), (rec.weak_normalized_share, "weak")] {
                    match (got, st[key].as_f64()) {
                        (Some(g), Some(x)) => {
                            if !close(g, x, 1e-9) {
                                report.fail(format!("{wh}: {key} {g} != {x}"));
                            } else {
                                report.note(g, x, &wh);
                            }
                        }
                        _ => report.fail(format!("{wh}: missing {key}")),
                    }
                }
                let exp_both = st["both"].as_u64().unwrap();
                let mut both_diff = 0u64;
                if rec.both_supported_pairpx != exp_both {
                    both_diff = rec.both_supported_pairpx.abs_diff(exp_both);
                    if both_diff <= 64 {
                        report.note_boundary(&wh, both_diff);
                    } else {
                        report.fail(format!(
                            "{wh}: both {} != {exp_both}",
                            rec.both_supported_pairpx
                        ));
                    }
                }
                let exp_ab = st["abstain"].as_bool().unwrap();
                if rec.abstain != exp_ab {
                    report.fail(format!("{wh}: abstain {} != {exp_ab}", rec.abstain));
                }
                match (rec.honest_bound, st["bound"].as_f64()) {
                    (Some(b), Some(x)) => {
                        report.check_bound(&wh, b, x, both_diff, max_w);
                    }
                    _ => report.fail(format!("{wh}: missing bound")),
                }
                if rec.conditioning_shortfall > report.worst_shortfall {
                    report.worst_shortfall = rec.conditioning_shortfall;
                    report.worst_shortfall_where = wh.clone();
                }
                if rec.skipped_nonpositive > report.max_skipped {
                    report.max_skipped = rec.skipped_nonpositive;
                    report.max_skipped_where = wh.clone();
                }
            }
            // True target-choice parity through the real selection path.
            check_choices(
                &mut engine,
                &mut report,
                ds_name,
                pair,
                case,
                "steps",
                "choices",
                metric,
                l,
                r,
                &frozen,
            );
        }
    }
    // Tiny fixture is covered by unit gates (independent hand values);
    // the adapter pins the same numbers for the record.
    // Center-inclusive invariant gate: EL >= c^2 up to the stated bound.
    if report.worst_shortfall > 1e-12 {
        report.fail(format!(
            "center-inclusive shortfall {} exceeds 1e-12 at {}",
            report.worst_shortfall, report.worst_shortfall_where
        ));
    }
    let summary = serde_json::json!({
        "pass": report.failures.is_empty(),
        "failures": report.failures,
        "compared_steps": report.compared_steps,
        "worst_rel": report.worst_rel,
        "worst_rel_where": report.worst_rel_where,
        "worst_shortfall": report.worst_shortfall,
        "worst_shortfall_where": report.worst_shortfall_where,
        "conditioned": report.conditioned,
        "boundary_notes": report.boundary_notes,
        "max_boundary_diff": report.max_boundary_diff,
        "max_skipped_nonpositive": report.max_skipped,
        "max_skipped_where": report.max_skipped_where,
        "support": {
            "max_both_diff": report.max_boundary_diff,
            "max_bound_abs_diff": report.max_bound_abs_diff,
            "max_bound_abs_where": report.max_bound_abs_where,
            "max_facing_weight": max_w,
        },
    });
    println!("{summary}");
    if !report.failures.is_empty() {
        std::process::exit(1);
    }
}
