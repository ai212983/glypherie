//! Local-energy bench: modest full-workload timing on real captures.
//!
//! Usage: `bench_local G2_ADAPTER_DIR REPO_ROOT` (release build).
//! 13 size-points (v3mono roboto/literata/italic 8/12/16/20 plus
//! rouge-script-20) x pair `ef` x notebook/manuscript strengths = 26 runs,
//! each a full metric+-6 window (13 steps) at the frozen default (R12).
//! Reports cold load+score, warm rescore (cached fields and EL maps),
//! cancel plumbing, and per-sample profile/score bands. Prints JSON; RSS
//! is measured externally (`/usr/bin/time -l`) since this leaf takes no
//! allocator dependency.

use std::collections::HashMap;
use std::path::PathBuf;
use std::time::Instant;

use yinyang_oriented_engine::capture::load_capture;
use yinyang_oriented_engine::params::{EngineParams, ScoreParams};
use yinyang_oriented_engine::score::Strength;
use yinyang_oriented_engine::Engine;

const SIZES: [(&str, u32); 13] = [
    ("v3mono:roboto-8", 8),
    ("v3mono:roboto-12", 12),
    ("v3mono:roboto-16", 16),
    ("v3mono:roboto-20", 20),
    ("v3mono:literata-8", 8),
    ("v3mono:literata-12", 12),
    ("v3mono:literata-16", 16),
    ("v3mono:literata-20", 20),
    ("v3mono:roboto-italic-8", 8),
    ("v3mono:roboto-italic-12", 12),
    ("v3mono:roboto-italic-16", 16),
    ("v3mono:roboto-italic-20", 20),
    ("v3mono:rouge-script-20", 20),
];

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: bench_local G2_ADAPTER_DIR REPO_ROOT");
        std::process::exit(2);
    }
    let adapter: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(PathBuf::from(&args[1]).join("adapter.json")).unwrap(),
    )
    .unwrap();
    let repo_root = PathBuf::from(&args[2]);
    let datasets = adapter["datasets"].as_object().unwrap().clone();
    // metric per (dataset, pair) from the novel list.
    let mut metrics: HashMap<(String, String), i64> = HashMap::new();
    for e in adapter["novel"].as_array().unwrap() {
        metrics.insert(
            (
                e["dataset"].as_str().unwrap().to_string(),
                e["pair"].as_str().unwrap().to_string(),
            ),
            e["metric"].as_i64().unwrap(),
        );
    }
    let frozen = ScoreParams::frozen();
    assert_eq!(frozen.normalization_radius, 12);
    let deltas: Vec<i64> = (-6..=6).collect();

    let mut samples = Vec::new();
    let mut cancel_ok = false;
    for (ds_name, size) in SIZES {
        let info = &datasets[ds_name];
        let path = repo_root.join(info["path"].as_str().unwrap());
        let t_load0 = Instant::now();
        let ds = load_capture(ds_name, &path).unwrap();
        if ds.sha256 != info["sha256"].as_str().unwrap() {
            eprintln!("capture drift: {ds_name}");
            std::process::exit(1);
        }
        let mut engine = Engine::new(EngineParams::frozen()).unwrap();
        let (l, r) = ('e' as u32, 'f' as u32);
        for cp in [l, r] {
            let cell = &ds.cells[&cp];
            engine
                .load_glyph(ds_name, &ds.sha256, cp, cell.w, cell.h, cell.left, cell.top, &cell.cover)
                .unwrap();
        }
        let load_s = t_load0.elapsed().as_secs_f64();
        let metric = *metrics.get(&(ds_name.to_string(), "ef".to_string())).unwrap();

        // Cold: full window both strengths (EL maps compute on first use).
        let t_cold0 = Instant::now();
        let mut gl_nb = 0.0;
        let mut gl_ms = 0.0;
        for (strength, slot) in [(Strength::Notebook, &mut gl_nb), (Strength::Manuscript, &mut gl_ms)] {
            let res = engine
                .score_pair_local(ds_name, l, r, metric, &deltas, &frozen, strength, None)
                .unwrap();
            assert_eq!(res.steps.len(), 13);
            *slot = res.steps[6].gl.unwrap();
        }
        let cold_s = t_cold0.elapsed().as_secs_f64();

        // Warm: identical rescore served from cached fields and EL maps.
        let t_warm0 = Instant::now();
        for strength in [Strength::Notebook, Strength::Manuscript] {
            let res = engine
                .score_pair_local(ds_name, l, r, metric, &deltas, &frozen, strength, None)
                .unwrap();
            assert_eq!(res.steps.len(), 13);
        }
        let warm_s = t_warm0.elapsed().as_secs_f64();

        // Cancel plumbing: flag trips in-flight scoring, buffers stay valid.
        engine.cancel();
        let cancelled = engine
            .score_pair_local(ds_name, l, r, metric, &deltas, &frozen, Strength::Notebook, None)
            .is_err();
        engine.clear_cancel();
        let resumed = engine
            .score_pair_local(ds_name, l, r, metric, &[0], &frozen, Strength::Notebook, None)
            .is_ok();
        cancel_ok = cancel_ok || (cancelled && resumed);

        let (lw, lh) = (ds.cells[&l].w, ds.cells[&l].h);
        let (rw, rh) = (ds.cells[&r].w, ds.cells[&r].h);
        samples.push(serde_json::json!({
            "dataset": ds_name, "size_px": size, "pair": "ef", "metric": metric,
            "canvas_l_wh": [lw, lh], "canvas_r_wh": [rw, rh],
            "cold_load_s": load_s, "cold_score_s": cold_s, "warm_score_s": warm_s,
            "gl_metric_notebook": gl_nb, "gl_metric_manuscript": gl_ms,
        }));
    }
    // Per-size bands (timing profile + score bands over the 13x2 runs).
    let mut bands = serde_json::Map::new();
    for size in [8u32, 12, 16, 20] {
        let sel: Vec<&serde_json::Value> =
            samples.iter().filter(|s| s["size_px"] == size).collect();
        if sel.is_empty() {
            continue;
        }
        let mean = |f: fn(&serde_json::Value) -> f64| {
            sel.iter().map(|s| f(s)).sum::<f64>() / sel.len() as f64
        };
        bands.insert(
            size.to_string(),
            serde_json::json!({
                "n": sel.len(),
                "mean_cold_load_s": mean(|s| s["cold_load_s"].as_f64().unwrap()),
                "mean_cold_score_s": mean(|s| s["cold_score_s"].as_f64().unwrap()),
                "mean_warm_score_s": mean(|s| s["warm_score_s"].as_f64().unwrap()),
                "min_gl_nb": sel.iter().map(|s| s["gl_metric_notebook"].as_f64().unwrap())
                    .fold(f64::INFINITY, f64::min),
                "max_gl_nb": sel.iter().map(|s| s["gl_metric_notebook"].as_f64().unwrap())
                    .fold(f64::NEG_INFINITY, f64::max),
                "min_gl_ms": sel.iter().map(|s| s["gl_metric_manuscript"].as_f64().unwrap())
                    .fold(f64::INFINITY, f64::min),
                "max_gl_ms": sel.iter().map(|s| s["gl_metric_manuscript"].as_f64().unwrap())
                    .fold(f64::NEG_INFINITY, f64::max),
            }),
        );
    }
    println!(
        "{}",
        serde_json::json!({
            "pass": cancel_ok,
            "cancel_plumbing_ok": cancel_ok,
            "normalization_radius": frozen.normalization_radius,
            "n_runs": samples.len(),
            "samples": samples,
            "bands": bands,
        })
    );
    if !cancel_ok {
        std::process::exit(1);
    }
}
