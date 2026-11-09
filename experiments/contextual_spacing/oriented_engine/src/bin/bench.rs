//! Native benchmark: TRUE workload timing, not one-pair timing.
//!
//! Usage: `bench ADAPTER_DIR REPO_ROOT` (release build). Measures, on the
//! real 13+2 corpus: per-dataset cold open (fresh engine, glyph loads,
//! all pairs x 5 narrow steps), warm re-derive (cached fields, rescore) and
//! C*-choice derivation across the 17-grid, plus the q/R config sweep that
//! informs UI band freezing. Prints JSON; RSS is measured externally
//! (`/usr/bin/time -l`) since this leaf takes no allocator dependency.

use std::collections::HashMap;
use std::path::PathBuf;
use std::time::Instant;

use yinyang_oriented_engine::capture::load_capture;
use yinyang_oriented_engine::params::{EngineParams, ScoreParams};
use yinyang_oriented_engine::score::Strength;
use yinyang_oriented_engine::Engine;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 || args.len() > 4 {
        eprintln!("usage: bench ADAPTER_DIR REPO_ROOT [DATASET]");
        std::process::exit(2);
    }
    let only: Option<String> = args.get(3).cloned();
    let adapter: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(PathBuf::from(&args[1]).join("adapter.json")).unwrap(),
    )
    .unwrap();
    let repo_root = PathBuf::from(&args[2]);
    let frozen_score = ScoreParams::frozen();
    let cstar_grid: Vec<f64> = adapter["frozen"]["cstar_grid"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect();

    let datasets = adapter["datasets"].as_object().unwrap().clone();
    let mut pairs_by_ds: HashMap<String, Vec<(u32, u32, i64)>> = HashMap::new();
    let mut take = |key: &str| {
        for e in adapter[key].as_array().unwrap() {
            let ds = e["dataset"].as_str().unwrap().to_string();
            let pair = e["pair"].as_str().unwrap();
            pairs_by_ds.entry(ds).or_default().push((
                pair.chars().next().unwrap() as u32,
                pair.chars().nth(1).unwrap() as u32,
                e["metric"].as_i64().unwrap(),
            ));
        }
    };
    take("study");
    take("novel");
    let total_pairs: usize = pairs_by_ds.values().map(|v| v.len()).sum();

    // Cold: per-dataset fresh engine (mirrors opening each case in the UI).
    let mut engines: HashMap<String, Engine> = HashMap::new();
    let mut loaded: HashMap<String, yinyang_oriented_engine::capture::Dataset> = HashMap::new();
    let mut cold_load = 0.0;
    let mut cold_score = 0.0;
    let mut cold_steps = 0usize;
    let mut per_ds_cold: HashMap<String, f64> = HashMap::new();
    let mut g2_store: HashMap<(String, u32, u32), Vec<f64>> = HashMap::new();
    for (ds_name, pairs) in pairs_by_ds.iter() {
        if let Some(prefix) = only.as_ref() {
            if ds_name != prefix {
                continue;
            }
        }
        let t0 = Instant::now();
        let info = &datasets[ds_name];
        let ds = load_capture(ds_name, &repo_root.join(info["path"].as_str().unwrap())).unwrap();
        let mut engine = Engine::new(EngineParams::frozen()).unwrap();
        let mut glyphs: Vec<u32> = pairs.iter().flat_map(|(l, r, _)| [*l, *r]).collect();
        glyphs.sort_unstable();
        glyphs.dedup();
        for cp in glyphs {
            let cell = &ds.cells[&cp];
            engine
                .load_glyph(
                    ds_name,
                    &ds.sha256,
                    cp,
                    cell.w,
                    cell.h,
                    cell.left,
                    cell.top,
                    &cell.cover,
                )
                .unwrap();
        }
        let t1 = Instant::now();
        for (l, r, metric) in pairs {
            let res = engine
                .score_pair(
                    ds_name,
                    *l,
                    *r,
                    *metric,
                    &[-2, -1, 0, 1, 2],
                    &frozen_score,
                    Strength::Notebook,
                    None,
                )
                .unwrap();
            g2_store.insert(
                (ds_name.clone(), *l, *r),
                res.steps.iter().map(|s| s.g2.unwrap_or(f64::NAN)).collect(),
            );
            cold_steps += res.steps.len();
        }
        let t2 = Instant::now();
        cold_load += (t1 - t0).as_secs_f64();
        cold_score += (t2 - t1).as_secs_f64();
        per_ds_cold.insert(ds_name.clone(), (t2 - t0).as_secs_f64());
        engines.insert(ds_name.clone(), engine);
        loaded.insert(ds_name.clone(), ds);
    }

    // Warm: rescore everything on cached fields (the cohesion-only analog:
    // choice derivation needs no rescoring at all).
    let t0 = Instant::now();
    for (ds_name, pairs) in pairs_by_ds.iter() {
        if let Some(prefix) = only.as_ref() {
            if ds_name != prefix {
                continue;
            }
        }
        let engine = engines.get_mut(ds_name).unwrap();
        for (l, r, metric) in pairs {
            engine
                .score_pair(
                    ds_name,
                    *l,
                    *r,
                    *metric,
                    &[-2, -1, 0, 1, 2],
                    &frozen_score,
                    Strength::Notebook,
                    None,
                )
                .unwrap();
        }
    }
    let warm_rescore = t0.elapsed().as_secs_f64();

    // Wide: the shipped search-v2 workload — full geometry-bounded domain
    // per pair on cached fields (what the tables actually score).
    let t0 = Instant::now();
    let mut wide_steps = 0usize;
    let mut wide_pairs = 0usize;
    let mut per_ds_wide: HashMap<String, f64> = HashMap::new();
    for (ds_name, pairs) in pairs_by_ds.iter() {
        if let Some(prefix) = only.as_ref() {
            if ds_name != prefix {
                continue;
            }
        }
        let tds = Instant::now();
        let engine = engines.get_mut(ds_name).unwrap();
        for (l, r, metric) in pairs {
            let domain = match engine.search_domain(ds_name, *l, *r).unwrap() {
                Ok(d) => d,
                Err(_) => continue,
            };
            let deltas: Vec<i64> = (domain.lo..=domain.hi).collect();
            let res = engine
                .score_pair(
                    ds_name,
                    *l,
                    *r,
                    *metric,
                    &deltas,
                    &frozen_score,
                    Strength::Notebook,
                    None,
                )
                .unwrap();
            wide_steps += res.steps.len();
            wide_pairs += 1;
        }
        per_ds_wide.insert(ds_name.clone(), tds.elapsed().as_secs_f64());
    }
    let wide_rescore = t0.elapsed().as_secs_f64();

    // C* derivation across the grid from cached G2 (pure arithmetic, no
    // rescoring: the cohesion-only analog reuses stored step values).
    let t0 = Instant::now();
    let mut choices_derived = 0usize;
    for g2s in g2_store.values() {
        for c in cstar_grid.iter() {
            let mut mstar = f64::INFINITY;
            for g in g2s.iter() {
                let d = (g - c).abs();
                if d < mstar {
                    mstar = d;
                }
            }
            let tol = 1e-9 * 1.0f64.max(mstar);
            let mut best = 0usize;
            let mut nmin = 0usize;
            for (i, g) in g2s.iter().enumerate() {
                if (g - c).abs() <= mstar + tol {
                    if nmin == 0 {
                        best = i;
                    }
                    nmin += 1;
                }
            }
            let _ = (best, nmin);
            choices_derived += 1;
        }
    }
    let choice_derive = t0.elapsed().as_secs_f64();

    // Config sweep: stratified set (axes pairs), fresh engine per config.
    let mut sweep: HashMap<String, f64> = HashMap::new();
    let mut sweep_steps = 0usize;
    let do_sweep = only.is_none();
    let axes_cfg: Vec<(f64, u32)> = {
        let mut v: Vec<(u64, u32)> = adapter["axes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|a| {
                (
                    a["q"].as_f64().unwrap().to_bits(),
                    a["R"].as_u64().unwrap() as u32,
                )
            })
            .collect();
        v.sort_unstable();
        v.dedup();
        v.into_iter().map(|(b, r)| (f64::from_bits(b), r)).collect()
    };
    for (q, r) in axes_cfg {
        if !do_sweep {
            break;
        }
        let t0 = Instant::now();
        let mut p = EngineParams::frozen();
        p.q = q;
        p.radius = r;
        let mut engine = Engine::new(p).unwrap();
        for a in adapter["axes"].as_array().unwrap() {
            if (a["q"].as_f64().unwrap() - q).abs() > 1e-12 || a["R"].as_u64().unwrap() as u32 != r
            {
                continue;
            }
            let ds_name = a["dataset"].as_str().unwrap();
            let pair = a["pair"].as_str().unwrap();
            let l = pair.chars().next().unwrap() as u32;
            let rr = pair.chars().nth(1).unwrap() as u32;
            let metric = a["metric"].as_i64().unwrap();
            let ds = &loaded[ds_name];
            for cp in [l, rr] {
                let cell = &ds.cells[&cp];
                engine
                    .load_glyph(
                        ds_name,
                        &ds.sha256,
                        cp,
                        cell.w,
                        cell.h,
                        cell.left,
                        cell.top,
                        &cell.cover,
                    )
                    .unwrap();
            }
            let res = engine
                .score_pair(
                    ds_name,
                    l,
                    rr,
                    metric,
                    &[-2, -1, 0, 1, 2],
                    &frozen_score,
                    Strength::Notebook,
                    None,
                )
                .unwrap();
            sweep_steps += res.steps.len();
        }
        sweep.insert(format!("q{q}-R{r}"), t0.elapsed().as_secs_f64());
    }

    let slowest = per_ds_cold
        .iter()
        .max_by(|a, b| a.1.partial_cmp(b.1).unwrap());
    let out = serde_json::json!({
        "pairs": total_pairs,
        "cold_steps": cold_steps,
        "cold_load_seconds": cold_load,
        "cold_score_seconds": cold_score,
        "cold_total_seconds": cold_load + cold_score,
        "slowest_dataset": [slowest.map(|(k, _)| k), slowest.map(|(_, v)| v)],
        "warm_rescore_seconds": warm_rescore,
        "wide_pairs": wide_pairs,
        "wide_steps": wide_steps,
        "wide_rescore_seconds": wide_rescore,
        "wide_slowest_dataset": per_ds_wide
            .iter()
            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
            .map(|(k, v)| (k, v)),
        "choices_derived": choices_derived,
        "choice_derive_seconds": choice_derive,
        "sweep_seconds": sweep,
        "sweep_steps": sweep_steps,
        "cache_sizes": engines.iter().map(|(k, e)| (k, e.cache_sizes())).collect::<HashMap<_, _>>(),
    });
    println!("{out}");
}
