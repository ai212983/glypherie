//! Class-L numerical envelope: field reach R x falloff q on frozen normalizer.
//!
//! Usage: `envelope_local G2_ADAPTER_DIR REPO_ROOT OUT_JSON [phase]`.
//! `phase` is `a` (risk-first extremes, default) or `b` (full grid).
//!
//! Every record names all three variables explicitly: `field_radius` R
//! (square kernel half-width), `normalization_radius` (frozen 12, asserted),
//! `falloff` q. Notebook-primary, `tau = 0.5`, full forward domains
//! (`search_domain`, every integer delta, `cstar` None). No residual gates
//! against any reference here — only mathematical invariants (shortfall 0,
//! bound holds, map reduction, finite gl) plus recorded empirical
//! observations (support flips vs baseline with scalar impact, timing).
//! Any invariant failure is a bug report, never a gate to widen.

use std::collections::HashMap;
use std::path::PathBuf;
use std::time::Instant;

use yinyang_oriented_engine::capture::load_capture;
use yinyang_oriented_engine::local_energy::check_local_bound;
use yinyang_oriented_engine::params::{EngineParams, ScoreParams};
use yinyang_oriented_engine::score::Strength;
use yinyang_oriented_engine::Engine;

const PHASE_A_R: [u32; 2] = [1, 32];
const PHASE_A_Q: [f64; 2] = [0.25, 16.0];
const GRID_R: [u32; 7] = [1, 4, 8, 12, 16, 24, 32];
const GRID_Q: [f64; 7] = [0.25, 0.5, 2.0, 4.2, 8.0, 10.0, 16.0];

/// (dataset, left, right): stratified mono/gray/italic/script/small/large
/// plus parity-continuity pairs.
const PAIRS: [(&str, u32, u32); 8] = [
    ("v3mono:roboto-16", 'e' as u32, 'f' as u32),
    ("roboto-16-gray", 'e' as u32, 'f' as u32),
    ("v3mono:roboto-italic-16", 'e' as u32, 'f' as u32),
    ("v3mono:rouge-script-20", 'e' as u32, 'f' as u32),
    ("v3mono:roboto-8", 'e' as u32, 'f' as u32),
    ("v3mono:literata-20", 'e' as u32, 'f' as u32),
    ("roboto-16-mono", 'u' as u32, 'm' as u32),
    ("literata-24-gray", 'o' as u32, 'g' as u32),
];

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 4 {
        eprintln!("usage: envelope_local G2_ADAPTER_DIR REPO_ROOT OUT_JSON [phase]");
        std::process::exit(2);
    }
    let phase_b = args.get(4).map(|s| s == "b").unwrap_or(false);
    let adapter: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(PathBuf::from(&args[1]).join("adapter.json")).unwrap(),
    )
    .unwrap();
    let repo_root = PathBuf::from(&args[2]);
    let datasets = adapter["datasets"].as_object().unwrap().clone();

    let score = ScoreParams::frozen();
    assert_eq!(score.normalization_radius, 12, "normalizer must stay frozen at 12");

    let mut failures: Vec<String> = Vec::new();
    let mut configs: Vec<serde_json::Value> = Vec::new();

    // Baseline maps for support-flip accounting: (R12, q2) both per step.
    let mut baseline: HashMap<(String, u32, u32), Vec<(i64, u64)>> = HashMap::new();

    let radii: Vec<u32> = if phase_b { GRID_R.to_vec() } else { PHASE_A_R.to_vec() };
    let qs: Vec<f64> = if phase_b { GRID_Q.to_vec() } else { PHASE_A_Q.to_vec() };

    // Load every dataset once (fields rebuild per engine config below).
    let mut loaded: HashMap<String, yinyang_oriented_engine::capture::Dataset> = HashMap::new();
    for (ds_name, _, _) in PAIRS {
        if loaded.contains_key(ds_name) {
            continue;
        }
        let info = match datasets.get(ds_name) {
            Some(i) => i,
            None => {
                failures.push(format!("{ds_name}: not in adapter"));
                continue;
            }
        };
        let path = repo_root.join(info["path"].as_str().unwrap());
        match load_capture(ds_name, &path) {
            Ok(ds) => {
                if ds.sha256 != info["sha256"].as_str().unwrap() {
                    failures.push(format!("{ds_name}: capture drift"));
                    continue;
                }
                loaded.insert(ds_name.to_string(), ds);
            }
            Err(e) => failures.push(format!("{ds_name}: load {e}")),
        }
    }

    for (ds_name, l, r) in PAIRS {
        let ds = match loaded.get(ds_name) {
            Some(d) => d,
            None => continue,
        };
        if ds.cells.get(&l).is_none() || ds.cells.get(&r).is_none() {
            configs.push(serde_json::json!({"pair": [ds_name, l, r], "skipped": "cells missing"}));
            continue;
        }
        // Baseline first so every grid config gets flip accounting.
        run_config(
            ds_name, ds, l, r, 12, 2.0, &score,
            &mut baseline, &mut configs, &mut failures,
        );
        for &fr in &radii {
            for &q in &qs {
                if fr == 12 && q == 2.0 {
                    continue;
                }
                run_config(
                    ds_name, ds, l, r, fr, q, &score,
                    &mut baseline, &mut configs, &mut failures,
                );
                if !failures.is_empty() && failures.len() > 20 {
                    // Stop a doomed branch early; the ledger keeps everything.
                    break;
                }
            }
        }
    }

    if !phase_b {
        run_synthetics(&score, &mut configs, &mut failures);
    }

    let out = serde_json::json!({
        "phase": if phase_b { "b" } else { "a" },
        "normalization_radius": 12,
        "failures": failures,
        "configs": configs,
    });
    std::fs::write(&args[3], serde_json::to_string_pretty(&out).unwrap()).unwrap();
    println!(
        "envelope phase={} configs={} failures={}",
        out["phase"].as_str().unwrap(),
        configs.len(),
        failures.len()
    );
    if !failures.is_empty() {
        for f in failures.iter().take(10) {
            println!("FAIL {f}");
        }
        std::process::exit(1);
    }
}

#[allow(clippy::too_many_arguments)]
fn run_config(
    ds_name: &str,
    ds: &yinyang_oriented_engine::capture::Dataset,
    l: u32,
    r: u32,
    field_radius: u32,
    q: f64,
    score: &ScoreParams,
    baseline: &mut HashMap<(String, u32, u32), Vec<(i64, u64)>>,
    configs: &mut Vec<serde_json::Value>,
    failures: &mut Vec<String>,
) {
    let wh = format!("{ds_name} U+{l:04X}/U+{r:04X} field_R{field_radius} q{q}");
    let mut params = EngineParams::frozen();
    params.radius = field_radius;
    params.q = q;
    let mut engine = match Engine::new(params) {
        Ok(e) => e,
        Err(e) => {
            failures.push(format!("{wh}: engine build: {e}"));
            return;
        }
    };
    for cp in [l, r] {
        let cell = &ds.cells[&cp];
        if let Err(e) = engine.load_glyph(
            ds_name, &ds.sha256, cp, cell.w, cell.h, cell.left, cell.top, &cell.cover,
        ) {
            failures.push(format!("{wh}: load U+{cp:04X}: {e}"));
            return;
        }
    }
    let domain = match engine.search_domain(ds_name, l, r) {
        Ok(Ok(d)) => d,
        Ok(Err(nodomain)) => {
            configs.push(serde_json::json!({"config": wh, "no_domain": format!("{nodomain:?}")}));
            return;
        }
        Err(e) => {
            failures.push(format!("{wh}: search_domain: {e}"));
            return;
        }
    };
    // metric 0 with absolute-step deltas: record.step == record.delta,
    // so the map check below addresses the same step it compares.
    let deltas: Vec<i64> = (domain.lo..=domain.hi).collect();
    let t0 = Instant::now();
    let res = match engine.score_pair_local(
        ds_name, l, r, 0, &deltas, score, Strength::Notebook, None,
    ) {
        Ok(v) => v,
        Err(e) => {
            failures.push(format!("{wh}: score: {e}"));
            return;
        }
    };
    let score_s = t0.elapsed().as_secs_f64();

    let mut n_valid = 0u32;
    let mut max_shortfall = 0.0f64;
    let mut total_skipped = 0u64;
    let mut min_adjacent_dgl = f64::INFINITY;
    let mut prev_gl: Option<f64> = None;
    let mut max_gl = 0.0f64;
    let mut both_now: Vec<(i64, u64)> = Vec::new();
    for st in &res.steps {
        if !(st.valid && !st.abstain) {
            continue;
        }
        n_valid += 1;
        let g = match st.gl {
            Some(v) if v.is_finite() => v,
            _ => {
                failures.push(format!("{wh} step {}: nonfinite gl", st.step));
                continue;
            }
        };
        max_gl = max_gl.max(g);
        if st.conditioning_shortfall > max_shortfall {
            max_shortfall = st.conditioning_shortfall;
        }
        if st.conditioning_shortfall > 0.0 {
            failures.push(format!(
                "{wh} step {}: shortfall {} > 0", st.step, st.conditioning_shortfall
            ));
        }
        total_skipped += st.skipped_nonpositive;
        if let Some(b) = st.honest_bound {
            // Same-side mathematical invariant: gl and bound come from
            // the same scored terms, so only fp noise separates them.
            if let Err(e) = check_local_bound(g, b, 1e-12) {
                failures.push(format!("{wh} step {}: bound: {e}", st.step));
            }
        } else {
            failures.push(format!("{wh} step {}: missing bound", st.step));
        }
        both_now.push((st.step, st.both_supported_pairpx));
        if let Some(p) = prev_gl {
            min_adjacent_dgl = min_adjacent_dgl.min((g - p).abs());
        }
        prev_gl = Some(g);
    }

    // Support flips vs (field_R12, q2) baseline with scalar impact.
    let key = (ds_name.to_string(), l, r);
    let max_flip = match baseline.get(&key) {
        None => {
            if field_radius == 12 && q == 2.0 {
                baseline.insert(key, both_now.clone());
            }
            0u64
        }
        Some(base) => {
            let m: HashMap<i64, u64> = base.iter().cloned().collect();
            let mut mf = 0u64;
            for (step, b) in &both_now {
                if let Some(bb) = m.get(step) {
                    mf = mf.max(b.abs_diff(*bb));
                }
            }
            // Scalar impact rides alongside as max_gl in the record;
            // per-step gl-vs-baseline re-derivation is out of scope.
            mf
        }
    };
    // Map reduction at the middle valid step.
    let mut map_note = serde_json::json!(null);
    if let Some(mid) = res.steps.iter().find(|s| s.valid && !s.abstain && s.gl.is_some()) {
        let t1 = Instant::now();
        match engine.contribution_map_local(ds_name, l, r, mid.delta, score, Strength::Notebook) {
            Ok((map, _, _)) => {
                let sum: f64 = map.iter().sum();
                let g = mid.gl.unwrap();
                let diff = (sum - g).abs();
                let tol = 1e-9 * g.abs().max(1.0);
                if diff > tol {
                    failures.push(format!(
                        "{wh} step {}: map sum {sum} != gl {g}", mid.step
                    ));
                }
                map_note = serde_json::json!({
                    "step": mid.step, "map_sum": sum, "gl": g,
                    "abs_diff": diff, "seconds": t1.elapsed().as_secs_f64(),
                });
            }
            Err(e) => failures.push(format!("{wh}: map: {e}")),
        }
    }

    configs.push(serde_json::json!({
        "config": wh,
        "domain": [domain.lo, domain.hi],
        "n_valid": n_valid,
        "max_shortfall": max_shortfall,
        "total_skipped": total_skipped,
        "max_both_flip_vs_baseline": max_flip,
        "max_gl": max_gl,
        "min_adjacent_dgl": if min_adjacent_dgl.is_finite() { Some(min_adjacent_dgl) } else { None },
        "tie_tol_at_median_gl": 1e-9 * max_gl.max(1.0),
        "score_seconds": score_s,
        "map_check": map_note,
    }));
}

fn run_synthetics(
    score: &ScoreParams,
    configs: &mut Vec<serde_json::Value>,
    failures: &mut Vec<String>,
) {
    // Blank 10x10 vs single pixel; single vs single; touching bars sweep.
    let blank = vec![0.0f64; 100];
    let mut px = vec![0.0f64; 400];
    px[10 * 20 + 10] = 1.0;
    let mut engine = Engine::new(EngineParams::frozen()).unwrap();
    engine.load_glyph("synthetic", "env", 0x60, 10, 10, 0.0, 0.0, &blank).unwrap();
    engine.load_glyph("synthetic", "env", 0x61, 20, 20, 0.0, 0.0, &px).unwrap();
    let res = engine
        .score_pair_local("synthetic", 0x60, 0x61, 0, &[0], score, Strength::Notebook, None)
        .unwrap();
    let st = &res.steps[0];
    if !(st.abstain && st.abstain_reason.as_deref() == Some("no_shared_support")) {
        failures.push(format!("synthetic blank-vs-px: {st:?}"));
    }
    configs.push(serde_json::json!({"config": "synthetic blank-vs-px",
        "abstain": st.abstain, "reason": st.abstain_reason}));

    // Bars contact scan: 20x100, ink rows 4..16 cols 20..22 both sides.
    let mut bars = vec![0.0f64; 20 * 100];
    for y in 4..16 {
        for x in 20..22 {
            bars[y * 20 + x] = 1.0;
        }
    }
    let mut engine = Engine::new(EngineParams::frozen()).unwrap();
    engine.load_glyph("synthetic", "env", 0x41, 20, 100, 0.0, 0.0, &bars).unwrap();
    engine.load_glyph("synthetic", "env", 0x42, 20, 100, 0.0, 0.0, &bars).unwrap();
    let domain = match engine.search_domain("synthetic", 0x41, 0x42) {
        Ok(Ok(d)) => d,
        other => {
            failures.push(format!("bars contact: no domain: {other:?}"));
            return;
        }
    };
    let deltas: Vec<i64> = (domain.lo..=domain.hi).collect();
    let res = engine
        .score_pair_local("synthetic", 0x41, 0x42, 0, &deltas, score, Strength::Notebook, None)
        .unwrap();
    let contact: Vec<i64> = res.steps.iter().filter(|s| s.faces > 0).map(|s| s.step).collect();
    let invalid: Vec<i64> =
        res.steps.iter().filter(|s| !s.valid).map(|s| s.step).collect();
    configs.push(serde_json::json!({"config": "synthetic bars contact scan",
        "domain": [domain.lo, domain.hi], "contact_steps": contact,
        "invalid_steps": invalid}));
}
