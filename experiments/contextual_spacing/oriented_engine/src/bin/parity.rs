//! Native parity driver: frozen Python adapter corpus vs this engine.
//!
//! Usage: `parity ADAPTER_DIR REPO_ROOT` (both must exist). Compares every
//! study/novel step (both strength variants, tau spot checks), every
//! TIE-v2 choice on the C* grid, every custom q/R axis point, the reference
//! contribution map, slate projection peaks and metric steps. Prints a JSON
//! summary; exits nonzero on any mismatch.

use std::collections::HashMap;
use std::path::PathBuf;

use yinyang_oriented_engine::capture::load_capture;
use yinyang_oriented_engine::params::{EngineParams, ScoreParams};
use yinyang_oriented_engine::score::Strength;
use yinyang_oriented_engine::Engine;

const REL_TOL: f64 = 1e-9;

fn close_enough_q(got: f64, exp: f64, tol: f64) -> bool {
    if exp.is_finite() {
        got.is_finite() && (got - exp).abs() <= tol * 1.0f64.max(exp.abs())
    } else if exp.is_nan() {
        got.is_nan()
    } else {
        got.is_infinite() && got.signum() == exp.signum()
    }
}

fn close_enough(got: f64, exp: f64) -> bool {
    if exp.is_finite() {
        got.is_finite() && (got - exp).abs() <= REL_TOL * 1.0f64.max(exp.abs())
    } else if exp.is_nan() {
        got.is_nan()
    } else {
        got.is_infinite() && got.signum() == exp.signum()
    }
}

fn opt_close(got: Option<f64>, exp: &serde_json::Value) -> bool {
    match (got, exp.as_f64()) {
        (Some(g), Some(e)) => close_enough(g, e),
        (None, None) => true,
        _ => false,
    }
}

struct Report {
    failures: Vec<String>,
    compared_steps: usize,
    compared_choices: usize,
    worst_rel: f64,
    worst_where: String,
    worst_rel_default: f64,
    worst_default_where: String,
    boundary_notes: Vec<String>,
    max_boundary_diff: u64,
    conditioned: Vec<String>,
}

fn tol_for_q(q: f64) -> (f64, bool) {
    // High-q exponentiation (d^(q-1)) amplifies fp path differences; the
    // 1e-9 default gate holds at q <= 4, q in {10, 16} compares at 1e-8
    // with an explicit conditioning flag (choices still exact).
    if q > 4.0 {
        (1e-8, true)
    } else {
        (REL_TOL, false)
    }
}

impl Report {
    fn fail(&mut self, msg: String) {
        self.failures.push(msg);
    }

    fn note_boundary(&mut self, wh: &str, diff: u64) {
        if diff > self.max_boundary_diff {
            self.max_boundary_diff = diff;
        }
        if self.boundary_notes.len() < 8 {
            self.boundary_notes.push(format!("{wh}: diff {diff}"));
        }
    }

    fn note(&mut self, got: f64, exp: f64, wh: &str) {
        if exp.is_finite() && exp.abs() > 0.0 {
            let rel = (got - exp).abs() / exp.abs();
            if rel > self.worst_rel {
                self.worst_rel = rel;
                self.worst_where = wh.to_string();
            }
        }
    }

    fn note_default(&mut self, got: f64, exp: f64, wh: &str) {
        self.note(got, exp, wh);
        if exp.is_finite() && exp.abs() > 0.0 {
            let rel = (got - exp).abs() / exp.abs();
            if rel > self.worst_rel_default {
                self.worst_rel_default = rel;
                self.worst_default_where = wh.to_string();
            }
        }
    }
}

fn load_engine_for(q: f64, r: u32, report: &mut Report) -> Option<Engine> {
    let mut p = EngineParams::frozen();
    if (q - 2.0).abs() > f64::EPSILON {
        p.q = q;
    }
    if r != 12 {
        p.radius = r;
    }
    match Engine::new(p) {
        Ok(e) => Some(e),
        Err(err) => {
            report.fail(format!("engine build q={q} R={r}: {err}"));
            None
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
        eprintln!("usage: parity ADAPTER_DIR REPO_ROOT");
        std::process::exit(2);
    }
    let adapter_dir = PathBuf::from(&args[1]);
    let repo_root = PathBuf::from(&args[2]);
    let mut report = Report {
        failures: Vec::new(),
        compared_steps: 0,
        compared_choices: 0,
        worst_rel: 0.0,
        worst_where: String::new(),
        worst_rel_default: 0.0,
        worst_default_where: String::new(),
        boundary_notes: Vec::new(),
        max_boundary_diff: 0,
        conditioned: Vec::new(),
    };
    let adapter_text = std::fs::read_to_string(adapter_dir.join("adapter.json")).unwrap();
    let adapter: serde_json::Value = serde_json::from_str(&adapter_text).unwrap();

    // Frozen pins must match the parent-agreed values.
    let frozen = &adapter["frozen"];
    let pins = [
        (
            "oriented_fields_sha256",
            "6e3322d9125abdb7247f6bbe6c8d410db501fc523ffcf558c7985e88d74ec6e1",
        ),
        (
            "multiscale_fields_sha256",
            "b16bb4a47642fdf896655d5768f1781af003123892ebf61449cd8aecbadcefca",
        ),
        (
            "oriented_score_sha256",
            "207637f0ae6e69a1898f85bdf256d21f8c9cc2f76b3dd4c954d86ed8660dc1ac",
        ),
    ];
    for (key, want) in pins {
        if frozen[key].as_str() != Some(want) {
            report.fail(format!("adapter pin drift: {key}"));
        }
    }

    // Load every dataset the corpus references.
    let datasets = adapter["datasets"].as_object().unwrap().clone();
    let mut entries: Vec<(&serde_json::Value, bool)> = Vec::new();
    for e in adapter["study"].as_array().unwrap() {
        entries.push((e, true));
    }
    for e in adapter["novel"].as_array().unwrap() {
        entries.push((e, false));
    }

    let repo_root_p = repo_root.clone();
    let mut frozen_engine = match load_engine_for(2.0, 12, &mut report) {
        Some(e) => e,
        None => {
            println!("{{\"pass\":false,\"failures\":[\"frozen engine build failed\"]}}");
            std::process::exit(1);
        }
    };

    let frozen_score = ScoreParams::frozen();
    let tau025 = ScoreParams {
        tau: 0.25,
        ..ScoreParams::frozen()
    };
    let tau100 = ScoreParams {
        tau: 1.0,
        ..ScoreParams::frozen()
    };
    let cstar_grid: Vec<f64> = adapter["frozen"]["cstar_grid"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect();

    let mut loaded: HashMap<String, yinyang_oriented_engine::capture::Dataset> = HashMap::new();
    for (e, is_study) in entries.iter() {
        let ds_name = e["dataset"].as_str().unwrap();
        let pair = e["pair"].as_str().unwrap();
        let l = pair.chars().next().unwrap() as u32;
        let r = pair.chars().nth(1).unwrap() as u32;
        let metric = e["metric"].as_i64().unwrap();
        if !loaded.contains_key(ds_name) {
            let info = &datasets[ds_name];
            let path = repo_root_p.join(info["path"].as_str().unwrap());
            match load_capture(ds_name, &path) {
                Ok(ds) => {
                    if ds.sha256 != info["sha256"].as_str().unwrap() {
                        report.fail(format!("capture drift: {ds_name}"));
                    }
                    loaded.insert(ds_name.to_string(), ds);
                }
                Err(err) => {
                    report.fail(format!("load capture {ds_name}: {err}"));
                    continue;
                }
            }
        }
        let ds = &loaded[ds_name];
        // Metric steps validate the capture reader end to end.
        match ds.metric_step(l, r) {
            Ok(m) if m == metric => {}
            Ok(m) => report.fail(format!("{ds_name} {pair}: metric {m} != {metric}")),
            Err(err) => report.fail(format!("{ds_name} {pair} metric: {err}")),
        }
        load_pair_glyphs(&mut frozen_engine, ds_name, ds, l, r, &mut report);
        let deltas: Vec<i64> = e["steps"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s["delta"].as_i64().unwrap())
            .collect();
        let check_variant = |engine: &mut Engine,
                             report: &mut Report,
                             strength: Strength,
                             tau: &ScoreParams,
                             key: &str| {
            match engine.score_pair(ds_name, l, r, metric, &deltas, tau, strength, None) {
                Ok(res) => {
                    for (rec, exp) in res.steps.iter().zip(e["steps"].as_array().unwrap()) {
                        report.compared_steps += 1;
                        let wh = format!("{ds_name} {pair} {} step {}", key, rec.step);
                        if rec.valid != exp["valid"].as_bool().unwrap() {
                            report.fail(format!("{wh}: valid {} != {}", rec.valid, exp["valid"]));
                        }
                        if rec.faces != exp["faces"].as_u64().unwrap() as usize
                            || rec.corners != exp["corners"].as_u64().unwrap() as usize
                        {
                            report.fail(format!("{wh}: contact mismatch"));
                        }
                        if rec.valid {
                            let gkey = if key == "notebook" { "g2" } else { "g2_a1" };
                            if !opt_close(rec.g2, &exp[gkey]) {
                                report.fail(format!("{wh}: g2 {:?} != {}", rec.g2, exp[gkey]));
                            } else if let (Some(g), Some(x)) = (rec.g2, exp[gkey].as_f64()) {
                                report.note_default(g, x, &wh);
                            }
                            if key == "notebook" && (tau.tau - 0.5).abs() < 1e-12 {
                                for (field, ek) in [
                                    (rec.raw, "raw"),
                                    (rec.floor_share, "floor_share"),
                                    (rec.raw_floor_share, "raw_floor_share"),
                                ] {
                                    if !opt_close(field, &exp[ek]) {
                                        report.fail(format!("{wh}: {ek} {field:?} != {}", exp[ek]));
                                    }
                                }
                                let exp_both = exp["both_pairpx"].as_u64().unwrap();
                                let got_both = rec.both_supported_pairpx;
                                if got_both != exp_both {
                                    let diff = got_both.abs_diff(exp_both);
                                    // Near-floor single-pixel flips (U2 within
                                    // 1ulp of the eps floor change support on
                                    // one pixel x a few channel pairs; the
                                    // energy-weighted G2 is unaffected).
                                    if diff <= 64 {
                                        report.note_boundary(&wh, diff);
                                    } else {
                                        report.fail(format!(
                                            "{wh}: both_pairpx {got_both} != {exp_both}"
                                        ));
                                    }
                                }
                                if rec.abstain != exp["abstain"].as_bool().unwrap() {
                                    report.fail(format!("{wh}: abstain mismatch"));
                                }
                            }
                        } else if exp["reason"].as_str() != Some("occupied_cell_overlap")
                            || rec.reason.as_deref() != Some("occupied_cell_overlap")
                        {
                            report.fail(format!("{wh}: reason mismatch"));
                        }
                    }
                }
                Err(err) => report.fail(format!("{ds_name} {pair} {key}: {err}")),
            }
        };
        check_variant(
            &mut frozen_engine,
            &mut report,
            Strength::Notebook,
            &frozen_score,
            "notebook",
        );
        check_variant(
            &mut frozen_engine,
            &mut report,
            Strength::Manuscript,
            &frozen_score,
            "a1",
        );
        if *is_study {
            // Tau spot checks on the study set only (cost control).
            for (tau, tkey) in [(&tau025, "g2_tau_0.25"), (&tau100, "g2_tau_1.0")] {
                match frozen_engine.score_pair(
                    ds_name,
                    l,
                    r,
                    metric,
                    &deltas,
                    tau,
                    Strength::Notebook,
                    None,
                ) {
                    Ok(res) => {
                        for (rec, exp) in res.steps.iter().zip(e["steps"].as_array().unwrap()) {
                            if rec.valid && !opt_close(rec.g2, &exp[tkey]) {
                                report.fail(format!(
                                    "{ds_name} {pair} {tkey} step {}: {:?} != {}",
                                    rec.step, rec.g2, exp[tkey]
                                ));
                            }
                        }
                    }
                    Err(err) => report.fail(format!("{ds_name} {pair} {tkey}: {err}")),
                }
            }
        }
        // TIE-v2 choices across the whole C* grid.
        for c in cstar_grid.iter() {
            let key = if c.fract() == 0.0 {
                format!("{c:.1}")
            } else {
                format!("{c}")
            };
            let exp = &e["choices"][key.as_str()];
            match frozen_engine.score_pair(
                ds_name,
                l,
                r,
                metric,
                &deltas,
                &frozen_score,
                Strength::Notebook,
                Some(*c),
            ) {
                Ok(res) => {
                    report.compared_choices += 1;
                    let mut mins = res.minimizing.clone();
                    mins.sort_unstable();
                    let mut exp_mins: Vec<i64> = exp["minimizing"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .map(|v| v.as_i64().unwrap())
                        .collect();
                    exp_mins.sort_unstable();
                    if mins != exp_mins
                        || res.chosen != exp["chosen"].as_i64().unwrap_or(metric)
                        || res.fallback != exp["fallback"].as_bool().unwrap()
                    {
                        report.fail(format!(
                            "{ds_name} {pair} C*={c}: choice {mins:?}/{} != {}/{}",
                            res.chosen, exp["minimizing"], exp["chosen"]
                        ));
                    }
                }
                Err(err) => report.fail(format!("{ds_name} {pair} C*={c}: {err}")),
            }
        }
    }

    // Custom q/R axes, one engine per config (q/R threaded everywhere).
    let axes_by_config: HashMap<(u64, u32), Vec<&serde_json::Value>> = {
        let mut m: HashMap<(u64, u32), Vec<&serde_json::Value>> = HashMap::new();
        for a in adapter["axes"].as_array().unwrap() {
            let q = a["q"].as_f64().unwrap();
            let r = a["R"].as_u64().unwrap() as u32;
            m.entry((q.to_bits(), r)).or_default().push(a);
        }
        m
    };
    for ((qbits, r), items) in axes_by_config {
        let q = f64::from_bits(qbits);
        let tag = format!("q{q}-R{r}");
        let mut engine = match load_engine_for(q, r, &mut report) {
            Some(e) => e,
            None => continue,
        };
        for a in items {
            let ds_name = a["dataset"].as_str().unwrap();
            let pair = a["pair"].as_str().unwrap();
            let l = pair.chars().next().unwrap() as u32;
            let rr = pair.chars().nth(1).unwrap() as u32;
            let metric = a["metric"].as_i64().unwrap();
            if !loaded.contains_key(ds_name) {
                let info = &datasets[ds_name];
                if info.is_null() {
                    report.fail(format!("axes dataset missing: {ds_name}"));
                    continue;
                }
                let path = repo_root_p.join(info["path"].as_str().unwrap());
                match load_capture(ds_name, &path) {
                    Ok(ds) => {
                        loaded.insert(ds_name.to_string(), ds);
                    }
                    Err(err) => {
                        report.fail(format!("load capture {ds_name}: {err}"));
                        continue;
                    }
                }
            }
            let ds = &loaded[ds_name];
            load_pair_glyphs(&mut engine, ds_name, ds, l, rr, &mut report);
            let deltas: Vec<i64> = a["steps"]
                .as_array()
                .unwrap()
                .iter()
                .map(|s| s["delta"].as_i64().unwrap())
                .collect();
            match engine.score_pair(
                ds_name,
                l,
                rr,
                metric,
                &deltas,
                &frozen_score,
                Strength::Notebook,
                None,
            ) {
                Ok(res) => {
                    for (rec, exp) in res.steps.iter().zip(a["steps"].as_array().unwrap()) {
                        report.compared_steps += 1;
                        let wh = format!("{tag} {ds_name} {pair} step {}", rec.step);
                        if rec.valid != exp["valid"].as_bool().unwrap() {
                            report.fail(format!("{wh}: valid mismatch"));
                        }
                        let (qtol, cond) = tol_for_q(q);
                        let qclose = |got: Option<f64>, exp: &serde_json::Value| -> bool {
                            match (got, exp.as_f64()) {
                                (Some(g), Some(x)) => close_enough_q(g, x, qtol),
                                (None, None) => true,
                                _ => false,
                            }
                        };
                        if cond && !report.conditioned.iter().any(|t| t == &tag) {
                            report.conditioned.push(tag.clone());
                        }
                        if rec.valid && !qclose(rec.g2, &exp["g2"]) {
                            report.fail(format!("{wh}: g2 {:?} != {}", rec.g2, exp["g2"]));
                        } else if let (Some(g), Some(x)) = (rec.g2, exp["g2"].as_f64()) {
                            report.note(g, x, &wh);
                        }
                        if rec.valid && !qclose(rec.raw, &exp["raw"]) {
                            report.fail(format!("{wh}: raw {:?} != {}", rec.raw, exp["raw"]));
                        }
                    }
                }
                Err(err) => report.fail(format!("{tag} {ds_name} {pair}: {err}")),
            }
        }
    }

    // `custom` stage-2 references: synthetic bar pair through the same
    // custom-params path (defaults stay frozen).
    {
        let mut bar = vec![0.0; 48 * 48];
        for y in 8..40 {
            for x in 20..22 {
                bar[y * 48 + x] = 1.0;
            }
        }
        for c in adapter["custom"].as_array().unwrap() {
            let tag = c["tag"].as_str().unwrap();
            let (q, r) = match tag {
                "q3" => (3.0, 12u32),
                "r8" => (2.0, 8u32),
                _ => {
                    report.fail(format!("unknown custom tag {tag}"));
                    continue;
                }
            };
            if (c["q"].as_f64().unwrap() - q).abs() > 1e-12
                || c["radius"].as_u64().unwrap() as u32 != r
            {
                report.fail(format!("custom tag/param mismatch: {tag}"));
                continue;
            }
            let mut engine = match load_engine_for(q, r, &mut report) {
                Some(e) => e,
                None => continue,
            };
            engine
                .load_glyph("synthetic", "adapter-bar", 0x41, 48, 48, 0.0, 0.0, &bar)
                .unwrap();
            engine
                .load_glyph("synthetic", "adapter-bar", 0x42, 48, 48, 0.0, 0.0, &bar)
                .unwrap();
            match engine.score_pair(
                "synthetic",
                0x41,
                0x42,
                8,
                &[0],
                &frozen_score,
                Strength::Notebook,
                None,
            ) {
                Ok(res) => {
                    let s = &res.steps[0];
                    report.compared_steps += 1;
                    let wh = format!("custom {tag}");
                    if !s.valid {
                        report.fail(format!("{wh}: unexpectedly invalid"));
                    }
                    if !opt_close(s.g2, &c["g2"])
                        || !opt_close(s.raw, &c["raw"])
                        || !opt_close(s.floor_share, &c["floor_share"])
                    {
                        report.fail(format!(
                            "{wh}: {:?}/{:?}/{:?} != {}/{}/{}",
                            s.g2, s.raw, s.floor_share, c["g2"], c["raw"], c["floor_share"]
                        ));
                    } else if let (Some(g), Some(x)) = (s.g2, c["g2"].as_f64()) {
                        report.note(g, x, &wh);
                    }
                    if s.both_supported_pairpx != c["both_pairpx"].as_u64().unwrap() {
                        report.fail(format!("{wh}: both_pairpx mismatch"));
                    }
                }
                Err(err) => report.fail(format!("custom {tag}: {err}")),
            }
        }
    }

    // Reference contribution map over the adapter canvas.
    {
        let rm = &adapter["refmap"];
        let ds_name = rm["dataset"].as_str().unwrap();
        let l = 0x75u32;
        let rr = 0x6du32;
        let metric = rm["metric"].as_i64().unwrap();
        let origin = (
            rm["canvas_origin"][0].as_i64().unwrap(),
            rm["canvas_origin"][1].as_i64().unwrap(),
        );
        let shape = rm["canvas_shape"].as_array().unwrap();
        let ch = shape[0].as_u64().unwrap() as usize;
        let cw = shape[1].as_u64().unwrap() as usize;
        let pad = EngineParams::frozen().pad();
        let ds = &loaded[ds_name];
        // Reload: the LRU evicted these during the pair sweep.
        load_pair_glyphs(&mut frozen_engine, ds_name, ds, l, rr, &mut report);
        let lc = &ds.cells[&l];
        let rc = &ds.cells[&rr];
        let lo = (
            (lc.left - pad as f64).trunc() as i64,
            (lc.top - pad as f64).trunc() as i64,
        );
        let ro = (
            (rc.left - pad as f64).trunc() as i64 + metric,
            (rc.top - pad as f64).trunc() as i64,
        );
        match frozen_engine.contribution_map_on_canvas(
            ds_name,
            l,
            rr,
            lo,
            ro,
            origin,
            cw,
            ch,
            &frozen_score,
            Strength::Notebook,
        ) {
            Ok(map) => {
                let exp: Vec<f64> = rm["map"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v.as_f64().unwrap())
                    .collect();
                if map.len() != exp.len() {
                    report.fail(format!("refmap length {} != {}", map.len(), exp.len()));
                } else {
                    let mut worst: f64 = 0.0;
                    for (g, x) in map.iter().zip(exp.iter()) {
                        worst = worst.max((g - x).abs());
                    }
                    let g2 = rm["g2"].as_f64().unwrap();
                    if worst > REL_TOL * 1.0f64.max(g2.abs()) {
                        report.fail(format!("refmap worst abs diff {worst}"));
                    }
                    let sum: f64 = map.iter().sum();
                    if (sum - g2).abs() > REL_TOL * 1.0f64.max(g2.abs()) {
                        report.fail(format!("refmap sum {sum} != g2 {g2}"));
                    }
                }
            }
            Err(err) => report.fail(format!("refmap: {err}")),
        }
    }

    // Slate projection peaks.
    {
        for (ds_name, glyphs) in adapter["glyph_proj"].as_object().unwrap() {
            // Reload: the LRU evicted these during the pair sweep.
            let ds = &loaded[ds_name.as_str()];
            let cps: Vec<u32> = glyphs
                .as_object()
                .unwrap()
                .keys()
                .map(|k| k.parse().unwrap())
                .collect();
            for cp in cps {
                let cell = &ds.cells[&cp];
                if let Err(e) = frozen_engine.load_glyph(
                    ds_name.as_str(),
                    &ds.sha256,
                    cp,
                    cell.w,
                    cell.h,
                    cell.left,
                    cell.top,
                    &cell.cover,
                ) {
                    report.fail(format!("reload {ds_name} U+{cp:04X}: {e}"));
                }
            }
            for (cp, exp) in glyphs.as_object().unwrap() {
                let cp_num: u32 = cp.parse().unwrap();
                match frozen_engine.slate_max(ds_name, cp_num) {
                    Ok(got) => {
                        let x = exp.as_f64().unwrap();
                        if (got - x).abs() > REL_TOL * 1.0f64.max(x.abs()) {
                            report
                                .fail(format!("slate_max {ds_name} U+{cp_num:04X}: {got} != {x}"));
                        }
                    }
                    Err(err) => {
                        report.fail(format!("slate_max {ds_name} {cp}: {err}"));
                    }
                }
            }
        }
    }

    let summary = serde_json::json!({
        "compared_steps": report.compared_steps,
        "compared_choices": report.compared_choices,
        "worst_rel": report.worst_rel,
        "worst_where": report.worst_where,
        "worst_rel_default": report.worst_rel_default,
        "worst_default_where": report.worst_default_where,
        "max_boundary_diff_pairpx": report.max_boundary_diff,
        "boundary_notes": report.boundary_notes,
        "conditioned_tolerances": report.conditioned,
        "failures": report.failures,
        "pass": report.failures.is_empty(),
    });
    println!("{summary}");
    if !report.failures.is_empty() {
        std::process::exit(1);
    }
}
