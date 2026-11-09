//! True full-preview workload for Class L: every text-adjacent pair of one
//! frozen site-reviewed case, full search-v2 domains, default R12.
//!
//! Usage: `bench_preview BOOT_JSON CASE_ID PROFILE REPO_ROOT` (release).
//! PROFILE is `mono` or `gray`. Pairs come from the case sample-text lines
//! (spaces excluded from scoring but counted); metrics come from the
//! frozen G2 preview gaps where present, else the domain floor. Phases:
//! cold load, cold full-window score (EL build + scoring), warm rescore
//! (cached fields and EL maps), contribution maps at the metric step,
//! and TIE-only selection cost (`tie_set` microbench — selection rides
//! inside score calls, so this is the target-only path). Prints JSON;
//! RSS is measured externally (`/usr/bin/time -l`).

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::time::Instant;

use yinyang_oriented_engine::Engine;
use yinyang_oriented_engine::params::{EngineParams, ScoreParams};
use yinyang_oriented_engine::score::{tie_set, Strength};

fn ensure_loaded(
    engine: &mut Engine,
    ds_name: &str,
    sha: &str,
    covers: &HashMap<u32, Cover>,
    cp: u32,
    n_reloads: &mut u64,
    reload_s: &mut f64,
) {
    let c = covers.get(&cp).unwrap();
    let t0 = Instant::now();
    let recomputed = engine
        .load_glyph(ds_name, sha, cp, c.w, c.h, c.left, c.top, &c.px)
        .unwrap();
    *reload_s += t0.elapsed().as_secs_f64();
    if recomputed {
        *n_reloads += 1;
    }
}

struct Cover {
    w: usize,
    h: usize,
    left: f64,
    top: f64,
    px: Vec<f64>,
}

fn parse_cover(s: &str, gray: bool) -> Vec<f64> {
    s.chars()
        .map(|c| {
            let d = c.to_digit(10).unwrap() as f64;
            if gray { d / 7.0 } else { d }
        })
        .collect()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 5 {
        eprintln!("usage: bench_preview BOOT_JSON CASE_ID PROFILE REPO_ROOT");
        std::process::exit(2);
    }
    let gray = match args[3].as_str() {
        "gray" => true,
        "mono" => false,
        _ => {
            eprintln!("PROFILE must be mono or gray");
            std::process::exit(2);
        }
    };
    let boot: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(PathBuf::from(&args[1])).unwrap(),
    )
    .unwrap();
    let case = boot["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|c| c["id"] == args[2])
        .unwrap_or_else(|| {
            eprintln!("case {} not found", args[2]);
            std::process::exit(2);
        });
    let prof = &case["profiles"][args[3].as_str()];
    let glyphs = prof["glyphs"].as_object().unwrap();
    let lines: Vec<String> = prof["lines"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap().to_string())
        .collect();
    // Frozen preview metrics per pair (first occurrence wins).
    let mut preview_metric: HashMap<(u32, u32), i64> = HashMap::new();
    if let Some(pv) = prof["preview"].as_array() {
        for line in pv {
            for g in line["gaps"].as_array().unwrap() {
                let pair = g["pair"].as_str().unwrap();
                let mut ch = pair.chars();
                if let (Some(a), Some(b)) = (ch.next(), ch.next()) {
                    if g.get("space").and_then(|v| v.as_bool()).unwrap_or(false) {
                        continue;
                    }
                    preview_metric
                        .entry((a as u32, b as u32))
                        .or_insert(g["metric"].as_i64().unwrap());
                }
            }
        }
    }
    // Unique text-adjacent non-space pairs present in the capture.
    let mut pairs: Vec<(u32, u32)> = Vec::new();
    let mut seen: HashSet<(u32, u32)> = HashSet::new();
    let mut n_text_pairs = 0usize;
    let mut n_space = 0usize;
    for line in &lines {
        let ch: Vec<char> = line.chars().collect();
        for w in ch.windows(2) {
            if w[0] == ' ' || w[1] == ' ' {
                n_space += 1;
                continue;
            }
            n_text_pairs += 1;
            let key = (w[0] as u32, w[1] as u32);
            if seen.insert(key)
                && glyphs.contains_key(&key.0.to_string())
                && glyphs.contains_key(&key.1.to_string())
            {
                pairs.push(key);
            }
        }
    }

    let ds_name = format!("{}-{}", args[2], args[3]);
    let sha = prof["capture_sha256"].as_str().unwrap();
    let frozen = ScoreParams::frozen();
    assert_eq!(frozen.normalization_radius, 12);
    let seed = 0.4697315871728616f64;
    let high = 8.0f64;

    // Full ASCII cases exceed the 32-entry glyph LRU, so the true
    // workload reloads evicted glyphs as it goes (reload fast-path:
    // identical bytes only re-touch, no field recompute). All covers
    // are parsed once; every phase ensure-loads per pair and accounts
    // reloads separately.
    let mut covers: HashMap<u32, Cover> = HashMap::new();
    for (l, r) in &pairs {
        for cp in [*l, *r] {
            covers.entry(cp).or_insert_with(|| {
                let g = &glyphs[&cp.to_string()];
                let px = parse_cover(g["cover"].as_str().unwrap(), gray);
                assert_eq!(
                    px.len(),
                    g["w"].as_u64().unwrap() as usize * g["h"].as_u64().unwrap() as usize
                );
                Cover {
                    w: g["w"].as_u64().unwrap() as usize,
                    h: g["h"].as_u64().unwrap() as usize,
                    left: g["left"].as_f64().unwrap(),
                    top: g["top"].as_f64().unwrap(),
                    px,
                }
            });
        }
    }
    let mut engine = Engine::new(EngineParams::frozen()).unwrap();
    let mut n_reloads = 0u64;
    let mut reload_s = 0.0f64;

    let t_load0 = Instant::now();
    let mut needed: Vec<u32> = covers.keys().copied().collect();
    needed.sort_unstable();
    for cp in needed {
        ensure_loaded(&mut engine, &ds_name, sha, &covers, cp, &mut n_reloads, &mut reload_s);
    }
    let load_s = t_load0.elapsed().as_secs_f64();
    let load_reloads = n_reloads;

    // Full domains (geometry only, timed separately as search cost).
    let t_dom0 = Instant::now();
    let mut work: Vec<(u32, u32, i64, Vec<i64>)> = Vec::new();
    let mut n_nodomain = 0usize;
    for (l, r) in &pairs {
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *l, &mut n_reloads, &mut reload_s);
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *r, &mut n_reloads, &mut reload_s);
        match engine.search_domain(&ds_name, *l, *r) {
            Ok(Ok(dom)) => {
                let deltas: Vec<i64> = (dom.lo..=dom.hi).collect();
                let metric = preview_metric
                    .get(&(*l, *r))
                    .copied()
                    .filter(|m| *m >= dom.lo && *m <= dom.hi)
                    .unwrap_or(dom.lo);
                work.push((*l, *r, metric, deltas));
            }
            other => {
                n_nodomain += 1;
                if std::env::var("BENCH_PREVIEW_DEBUG").is_ok() {
                    eprintln!("no-domain {} {}: {:?}", *l as u8 as char, *r as u8 as char, other);
                }
            }
        }
    }
    let domain_s = t_dom0.elapsed().as_secs_f64();

    let mut rows = Vec::new();
    // Cold: EL maps build on first use; time notebook then manuscript.
    // ensure() inside the loop accounts LRU-churn reloads honestly.
    let t_cold_nb = Instant::now();
    let mut gl_nb: HashMap<(u32, u32), f64> = HashMap::new();
    for (l, r, metric, deltas) in &work {
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *l, &mut n_reloads, &mut reload_s);
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *r, &mut n_reloads, &mut reload_s);
        let res = engine
            .score_pair_local(&ds_name, *l, *r, *metric, deltas, &frozen, Strength::Notebook, Some(seed))
            .unwrap();
        let at: HashMap<i64, f64> = res
            .steps
            .iter()
            .filter_map(|s| s.gl.map(|g| (s.delta, g)))
            .collect();
        gl_nb.insert((*l, *r), *at.get(metric).unwrap_or(&f64::NAN));
        rows.push((*l, *r, *metric, deltas.len(), res.chosen));
    }
    let cold_nb_s = t_cold_nb.elapsed().as_secs_f64();

    let t_cold_ms = Instant::now();
    for (l, r, metric, deltas) in &work {
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *l, &mut n_reloads, &mut reload_s);
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *r, &mut n_reloads, &mut reload_s);
        engine
            .score_pair_local(&ds_name, *l, *r, *metric, deltas, &frozen, Strength::Manuscript, Some(seed))
            .unwrap();
    }
    let cold_ms_s = t_cold_ms.elapsed().as_secs_f64();

    // Warm: identical rescore; cache benefit is whatever survives LRU
    // churn on this working set (evicted entries lose their EL maps).
    let t_warm_nb = Instant::now();
    for (l, r, metric, deltas) in &work {
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *l, &mut n_reloads, &mut reload_s);
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *r, &mut n_reloads, &mut reload_s);
        engine
            .score_pair_local(&ds_name, *l, *r, *metric, deltas, &frozen, Strength::Notebook, Some(seed))
            .unwrap();
    }
    let warm_nb_s = t_warm_nb.elapsed().as_secs_f64();
    let t_warm_ms = Instant::now();
    for (l, r, metric, deltas) in &work {
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *l, &mut n_reloads, &mut reload_s);
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *r, &mut n_reloads, &mut reload_s);
        engine
            .score_pair_local(&ds_name, *l, *r, *metric, deltas, &frozen, Strength::Manuscript, Some(high))
            .unwrap();
    }
    let warm_ms_s = t_warm_ms.elapsed().as_secs_f64();

    // Map costs at the metric step (notebook).
    let t_map0 = Instant::now();
    let mut map_px = 0usize;
    for (l, r, metric, _) in &work {
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *l, &mut n_reloads, &mut reload_s);
        ensure_loaded(&mut engine, &ds_name, sha, &covers, *r, &mut n_reloads, &mut reload_s);
        let (map, _, _) = engine
            .contribution_map_local(&ds_name, *l, *r, *metric, &frozen, Strength::Notebook)
            .unwrap();
        map_px += map.len();
    }
    let map_s = t_map0.elapsed().as_secs_f64();

    // Target-only selection cost: tie_set microbench over a 60-dev grid.
    let devs: Vec<f64> = (0..60).map(|i| (i as f64) * 0.37 + 0.11).collect();
    let t_tie0 = Instant::now();
    let mut tie_acc = 0usize;
    for _ in 0..20000 {
        tie_acc += tie_set(&devs).0.len();
    }
    let tie_s = t_tie0.elapsed().as_secs_f64() / 20000.0;
    let _ = tie_acc;

    let total_steps: usize = work.iter().map(|(_, _, _, d)| d.len()).sum();
    let out: Vec<serde_json::Value> = rows
        .iter()
        .map(|(l, r, metric, nsteps, chosen)| {
            let gl = gl_nb.get(&(*l, *r)).copied().unwrap_or(f64::NAN);
            serde_json::json!({
                "pair": format!("{}{}", char::from_u32(*l).unwrap_or('?'), char::from_u32(*r).unwrap_or('?')),
                "metric": metric, "domain_steps": nsteps,
                "gl_metric_notebook": gl, "chosen_seed": chosen,
            })
        })
        .collect();
    println!(
        "{}",
        serde_json::json!({
            "case": args[2], "profile": args[3],
            "normalization_radius": frozen.normalization_radius,
            "n_text_pairs": n_text_pairs, "n_space_adjacent": n_space,
            "n_unique_scored": work.len(), "n_no_domain": n_nodomain,
            "n_glyphs": covers.len(),
            "n_reload_recomputes": n_reloads,
            "reload_seconds": reload_s, "load_recomputes": load_reloads,
            "total_domain_steps": total_steps,
            "seconds": {"cold_load": load_s, "search_domain": domain_s,
                "cold_score_nb": cold_nb_s, "cold_score_ms": cold_ms_s,
                "warm_rescore_nb": warm_nb_s, "warm_rescore_ms": warm_ms_s,
                "maps_nb": map_s, "map_pixels": map_px,
                "tie_set_per_call_s": tie_s},
            "pairs": out,
        })
    );
}
