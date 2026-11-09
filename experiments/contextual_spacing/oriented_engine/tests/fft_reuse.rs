//! F1 FFT-reuse gate: original per-kernel FFT loop vs the shared-spectrum
//! candidate (`glyph_fields`), compared at field-bit level first.
//!
//! The original algorithm (one `conv_same` per kernel, i.e. one input
//! forward FFT per kernel) is replicated here as `original_glyph_fields`
//! from public APIs only. The candidate shares one input spectrum per
//! padded shape. Every `f64` array (`u1`/`u2`/`distance`/`conf_nb`/`arc`/
//! `c_per_scale`/`t_combined`) is compared bitwise (`to_bits`); `supported`
//! is compared exactly. Score/map/TIE checks ride on top and cannot hide
//! a boundary flip: any differing field bit fails before scores run.
//!
//! Fixtures: synthetic point/bar/blank/disjoint plus real mono/gray/
//! italic/small/large captures; configs frozen, R1/q0.25, R13/q4, R32/q16
//! and offgrid q4.2; both strengths in scores and maps. Domain scoring
//! covers whole forward domains for a bounded 6-pair selection (not the
//! full 26 build), with TIE midpoint/exact checks.

use std::collections::HashMap;
use std::path::PathBuf;
use std::time::Instant;

use yinyang_oriented_engine::capture::load_capture;
use yinyang_oriented_engine::engine::Engine;
use yinyang_oriented_engine::fft::Conv;
use yinyang_oriented_engine::fields::{
    build_oriented_kernels, build_v1_bank, glyph_fields, GlyphFields, OrientedKernels, V1Banks,
};
use yinyang_oriented_engine::local_energy::{
    contribution_map_local, local_energy_maps, score_step_local,
};
use yinyang_oriented_engine::params::{EngineParams, ScoreParams};
use yinyang_oriented_engine::score::{
    contact_counts, facing_matrix, score_step, self_energy, tie_set, union_canvas, Strength,
};
use yinyang_oriented_engine::EngineError;

use rustfft::num_complex::Complex;

fn repo_root() -> PathBuf {
    let mut dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    loop {
        if dir.join("out/diagnostics/contextual-spacing/yinyang-browser-integration/runtime/adapter/adapter.json").exists() {
            return dir;
        }
        if !dir.pop() {
            panic!("repo root with adapter.json not found above CARGO_MANIFEST_DIR");
        }
    }
}

fn adapter() -> serde_json::Value {
    let path = repo_root().join(
        "out/diagnostics/contextual-spacing/yinyang-browser-integration/runtime/adapter/adapter.json",
    );
    serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap()
}

/// Original pre-F1 field loop: one `conv_same` (own input forward FFT)
/// per kernel. Replicates the retired `glyph_fields` body exactly; the
/// candidate must match it bitwise.
fn original_glyph_fields(
    cover: &[f64],
    w: usize,
    h: usize,
    params: &EngineParams,
    banks: &V1Banks,
    kernels: &OrientedKernels,
    conv: &mut Conv,
) -> Result<GlyphFields, EngineError> {
    if cover.len() != w * h {
        return Err(EngineError::Invalid("cover length mismatch".to_string()));
    }
    if cover.iter().any(|v| !v.is_finite()) {
        return Err(EngineError::Invalid(
            "glyph cover must be finite (no NaN/Inf)".to_string(),
        ));
    }
    let pad = params.pad();
    let pw = w + 2 * pad as usize;
    let ph = h + 2 * pad as usize;
    if pw > 2048 || ph > 2048 {
        return Err(EngineError::Invalid(
            "padded lattice exceeds guard".to_string(),
        ));
    }
    let mut padded = vec![Complex::new(0.0, 0.0); pw * ph];
    for y in 0..h {
        for x in 0..w {
            padded[(y + pad as usize) * pw + x + pad as usize] =
                Complex::new(cover[y * w + x], 0.0);
        }
    }
    let kside = 2 * params.radius as usize + 1;
    let n_v1 = params.n_v1;
    let n_dir = params.n_directed;

    let mut c_per_scale: Vec<Vec<Vec<f64>>> = Vec::with_capacity(banks.banks.len());
    for (s, bank) in banks.banks.iter().enumerate() {
        let hw = banks.halfwidths[s] as usize;
        let side = 2 * hw + 1;
        let mut per_ori = Vec::with_capacity(n_v1);
        for g in bank.iter() {
            let out = conv.conv_same(&padded, pw, ph, g, side, side);
            per_ori.push(out.iter().map(|c| c.norm()).collect::<Vec<f64>>());
        }
        c_per_scale.push(per_ori);
    }
    let mut t_combined = vec![vec![0.0f64; pw * ph]; n_v1];
    for (s, per_ori) in c_per_scale.iter().enumerate() {
        let wt = params.weights[s];
        for o in 0..n_v1 {
            let dst = &mut t_combined[o];
            for (d, c) in dst.iter_mut().zip(per_ori[o].iter()) {
                *d += wt * c;
            }
        }
    }
    let directed_t: Vec<Vec<f64>> = (0..n_dir).map(|o| t_combined[o % n_v1].clone()).collect();
    let mut u1: Vec<Vec<f64>> = Vec::with_capacity(n_dir);
    let mut u2: Vec<Vec<f64>> = Vec::with_capacity(n_dir);
    for ((t_row, k1_row), k2_row) in directed_t
        .iter()
        .zip(kernels.h1.iter())
        .zip(kernels.h2.iter())
    {
        let tre: Vec<Complex<f64>> = t_row
            .iter()
            .map(|v| Complex::new(v.max(0.0), 0.0))
            .collect();
        let hk1: Vec<Complex<f64>> = k1_row.iter().map(|v| Complex::new(*v, 0.0)).collect();
        let hk2: Vec<Complex<f64>> = k2_row.iter().map(|v| Complex::new(*v, 0.0)).collect();
        let o1 = conv.conv_same(&tre, pw, ph, &hk1, kside, kside);
        let o2 = conv.conv_same(&tre, pw, ph, &hk2, kside, kside);
        u1.push(o1.iter().map(|c| c.re.max(0.0)).collect());
        u2.push(o2.iter().map(|c| c.re.max(0.0)).collect());
    }
    let npx = pw * ph;
    let mut distance = vec![vec![f64::NAN; npx]; n_dir];
    let mut conf_nb = vec![vec![0.0; npx]; n_dir];
    let mut arc = vec![vec![0.0; npx]; n_dir];
    let mut supported = vec![vec![false; npx]; n_dir];
    let exp_nb = params.notebook_exponent();
    let exp_ms = params.manuscript_exponent();
    for o in 0..n_dir {
        for i in 0..npx {
            let a = u1[o][i];
            let b = u2[o][i];
            if a.is_finite() && b.is_finite() && b > params.eps {
                let d = a / b;
                supported[o][i] = true;
                distance[o][i] = d;
                conf_nb[o][i] = a * d.powf(exp_nb);
                arc[o][i] = a * d.powf(exp_ms);
            }
        }
    }
    Ok(GlyphFields {
        w: pw,
        h: ph,
        pad,
        c_per_scale,
        t_combined,
        u1,
        u2,
        distance,
        conf_nb,
        arc,
        supported,
    })
}

fn bits(v: f64) -> u64 {
    v.to_bits()
}

/// Bitwise field comparison. Returns (compared_values, differing_values,
/// nan_pixels_checked) and panics on the first mismatch with location.
fn assert_fields_bitwise(orig: &GlyphFields, cand: &GlyphFields, label: &str) -> (u64, u64) {
    assert_eq!(orig.w, cand.w, "{label}: w");
    assert_eq!(orig.h, cand.h, "{label}: h");
    assert_eq!(orig.pad, cand.pad, "{label}: pad");
    let mut compared: u64 = 0;
    let mut nan_px: u64 = 0;
    let mut check = |name: &str, o: &[f64], c: &[f64]| {
        assert_eq!(o.len(), c.len(), "{label}:{name} len");
        for (i, (x, y)) in o.iter().zip(c.iter()).enumerate() {
            compared += 1;
            if x.is_nan() || y.is_nan() {
                nan_px += 1;
            }
            assert_eq!(
                bits(*x),
                bits(*y),
                "{label}:{name}[{i}] bit flip {:e} vs {:e}",
                x,
                y
            );
        }
    };
    for (s, (o, c)) in orig
        .c_per_scale
        .iter()
        .zip(cand.c_per_scale.iter())
        .enumerate()
    {
        for (ori, (x, y)) in o.iter().zip(c.iter()).enumerate() {
            check(&format!("c_per_scale[{s}][{ori}]"), x, y);
        }
    }
    for (o, (x, y)) in orig
        .t_combined
        .iter()
        .zip(cand.t_combined.iter())
        .enumerate()
    {
        check(&format!("t_combined[{o}]"), x, y);
    }
    for (o, (x, y)) in orig.u1.iter().zip(cand.u1.iter()).enumerate() {
        check(&format!("u1[{o}]"), x, y);
    }
    for (o, (x, y)) in orig.u2.iter().zip(cand.u2.iter()).enumerate() {
        check(&format!("u2[{o}]"), x, y);
    }
    for (o, (x, y)) in orig.distance.iter().zip(cand.distance.iter()).enumerate() {
        check(&format!("distance[{o}]"), x, y);
    }
    for (o, (x, y)) in orig.conf_nb.iter().zip(cand.conf_nb.iter()).enumerate() {
        check(&format!("conf_nb[{o}]"), x, y);
    }
    for (o, (x, y)) in orig.arc.iter().zip(cand.arc.iter()).enumerate() {
        check(&format!("arc[{o}]"), x, y);
    }
    assert_eq!(orig.supported, cand.supported, "{label}: supported flips");
    (compared, nan_px)
}

fn build_pw(params: &EngineParams) -> (V1Banks, OrientedKernels) {
    let mut banks = Vec::with_capacity(params.sigmas.len());
    let mut halfwidths = Vec::with_capacity(params.sigmas.len());
    for s in params.sigmas.iter() {
        let (bank, hw) = build_v1_bank(*s, params.n_v1);
        banks.push(bank);
        halfwidths.push(hw);
    }
    let (h1, h2, mass1, mass2) =
        build_oriented_kernels(params.q, params.kappa, params.radius, params.n_directed);
    let taps = 2 * params.radius as usize + 1;
    (
        V1Banks { banks, halfwidths },
        OrientedKernels {
            h1,
            h2,
            mass1,
            mass2,
            taps,
        },
    )
}

fn configs() -> Vec<(&'static str, EngineParams)> {
    let mut out = Vec::new();
    out.push(("frozen", EngineParams::frozen()));
    let mut r1 = EngineParams::frozen();
    r1.radius = 1;
    r1.q = 0.25;
    out.push(("R1-q0.25", r1));
    let mut r13 = EngineParams::frozen();
    r13.radius = 13;
    r13.q = 4.0;
    out.push(("R13-q4", r13));
    let mut r32 = EngineParams::frozen();
    r32.radius = 32;
    r32.q = 16.0;
    out.push(("R32-q16", r32));
    let mut off = EngineParams::frozen();
    off.q = 4.2;
    out.push(("R12-q4.2-offgrid", off));
    for (_, p) in out.iter() {
        p.validate().unwrap();
    }
    out
}

struct Fixture {
    label: &'static str,
    cover: Vec<f64>,
    w: usize,
    h: usize,
}

fn synthetic_fixtures() -> Vec<Fixture> {
    // Single point.
    let mut point = vec![0.0; 81];
    point[4 * 9 + 4] = 1.0;
    // Horizontal bar.
    let mut bar = vec![0.0; 20 * 12];
    for x in 2..18 {
        for y in 5..7 {
            bar[y * 20 + x] = 1.0;
        }
    }
    // Blank.
    let blank = vec![0.0; 64];
    // Two disjoint blocks (far apart in one canvas).
    let mut disj = vec![0.0; 48 * 12];
    for y in 1..4 {
        for x in 1..4 {
            disj[y * 48 + x] = 1.0;
        }
    }
    for y in 8..11 {
        for x in 44..47 {
            disj[y * 48 + x] = 0.5;
        }
    }
    vec![
        Fixture {
            label: "point",
            cover: point,
            w: 9,
            h: 9,
        },
        Fixture {
            label: "bar",
            cover: bar,
            w: 20,
            h: 12,
        },
        Fixture {
            label: "blank",
            cover: blank,
            w: 8,
            h: 8,
        },
        Fixture {
            label: "disjoint",
            cover: disj,
            w: 48,
            h: 12,
        },
    ]
}

fn real_cell(dataset: &str, codepoint: u32) -> (Vec<f64>, usize, usize, f64, f64, String) {
    let root = repo_root();
    let ad = adapter();
    let info = &ad["datasets"][dataset];
    let path = root.join(info["path"].as_str().unwrap());
    let ds = load_capture(dataset, &path).unwrap();
    assert_eq!(
        ds.sha256,
        info["sha256"].as_str().unwrap(),
        "capture drift: {dataset}"
    );
    let cell = ds.cells.get(&codepoint).unwrap_or_else(|| {
        let (&cp, _) = ds.cells.iter().next().unwrap();
        &ds.cells[&cp]
    });
    (
        cell.cover.clone(),
        cell.w,
        cell.h,
        cell.left,
        cell.top,
        ds.sha256.clone(),
    )
}

fn real_fixtures() -> Vec<(Fixture, f64, f64)> {
    // (dataset, codepoint): mono, gray, italic, small, large.
    let picks = [
        ("roboto-16-mono", 0x6Eu32, "mono"),
        ("roboto-16-gray", 0x6E, "gray"),
        ("v3mono:roboto-italic-16", 0x6E, "italic"),
        ("v3mono:roboto-8", 0x65, "small"),
        ("roboto-24-mono", 0x6D, "large"),
    ];
    picks
        .iter()
        .map(|(ds, cp, kind)| {
            let (cover, w, h, left, top, _) = real_cell(ds, *cp);
            let label: &'static str = Box::leak(format!("real-{kind}").into_boxed_str());
            (Fixture { label, cover, w, h }, left, top)
        })
        .collect()
}

fn evidence_dir() -> Option<PathBuf> {
    std::env::var("YINYANG_F1_EVIDENCE_DIR")
        .ok()
        .map(PathBuf::from)
}

#[test]
fn f1_field_bits_parity() {
    let t0 = Instant::now();
    let mut total_compared: u64 = 0;
    let mut total_nan: u64 = 0;
    let mut cases: Vec<serde_json::Value> = Vec::new();
    let mut fixtures = synthetic_fixtures();
    for (f, _, _) in real_fixtures() {
        fixtures.push(f);
    }
    for (cfg_label, params) in configs() {
        let (banks, kernels) = build_pw(&params);
        for fx in fixtures.iter() {
            let mut conv_o = Conv::new();
            let mut conv_c = Conv::new();
            let orig = original_glyph_fields(
                &fx.cover,
                fx.w,
                fx.h,
                &params,
                &banks,
                &kernels,
                &mut conv_o,
            )
            .unwrap();
            let cand = glyph_fields(
                &fx.cover,
                fx.w,
                fx.h,
                &params,
                &banks,
                &kernels,
                &mut conv_c,
                None,
            )
            .unwrap();
            let (compared, nan_px) =
                assert_fields_bitwise(&orig, &cand, &format!("{cfg_label}/{}", fx.label));
            total_compared += compared;
            total_nan += nan_px;
            let (fo, io) = conv_o.fft_counts();
            let (fc, ic) = conv_c.fft_counts();
            cases.push(serde_json::json!({
                "config": cfg_label, "fixture": fx.label,
                "compared_values": compared, "nan_pixels": nan_px, "mismatches": 0,
                "orig_fwd": fo, "orig_inv": io, "cand_fwd": fc, "cand_inv": ic,
            }));
            // Candidate must do strictly fewer forward FFTs on multiscale
            // input (frozen: 144 -> 85); inverses are unchanged by design.
            assert!(fc < fo, "{cfg_label}/{}: no forward FFT saving", fx.label);
            assert_eq!(ic, io, "{cfg_label}/{}: inverse count moved", fx.label);
        }
    }
    let summary = serde_json::json!({
        "test": "f1_field_bits_parity",
        "cases": cases.len(),
        "compared_values": total_compared,
        "nan_pixels_checked": total_nan,
        "mismatches": 0,
        "seconds": t0.elapsed().as_secs_f64(),
        "detail": cases,
    });
    println!("{summary}");
    if let Some(dir) = evidence_dir() {
        std::fs::write(
            dir.join("fft_reuse_field_parity.json"),
            format!("{summary}"),
        )
        .unwrap();
    }
}

#[test]
fn f1_fft_call_counts() {
    // Frozen analytic expectation per glyph load: V1 5 scales x 8 ori and
    // directed 16 ch x 2 kernels. Original forwards every input per
    // kernel (2 x 72 = 144); the candidate forwards 5 V1 inputs + 8
    // directed inputs once (5 + 40 + 8 + 32 = 85). Inverses stay 72.
    let params = EngineParams::frozen();
    let (banks, kernels) = build_pw(&params);
    let (cover, w, h, _, _, _) = real_cell("roboto-16-mono", 0x6E);
    let mut conv = Conv::new();
    let _ = glyph_fields(&cover, w, h, &params, &banks, &kernels, &mut conv, None).unwrap();
    let (fwd, inv) = conv.fft_counts();
    assert_eq!((fwd, inv), (85, 72), "candidate FFT counts moved");
    let (scratch, col_tmp) = conv.scratch_extent();
    assert!(scratch > 0 && col_tmp > 0, "workspace not reused");
    let summary = serde_json::json!({
        "test": "f1_fft_call_counts",
        "candidate_fwd": fwd, "candidate_inv": inv,
        "original_fwd": 144, "original_inv": 72,
        "scratch_len": scratch, "col_tmp_len": col_tmp,
        "scratch_bytes": scratch * 16, "col_tmp_bytes": col_tmp * 16,
    });
    println!("{summary}");
    if let Some(dir) = evidence_dir() {
        std::fs::write(dir.join("fft_reuse_counts.json"), format!("{summary}")).unwrap();
    }
}

use yinyang_oriented_engine::score::contribution_map;

struct Side {
    cover: Vec<f64>,
    w: usize,
    h: usize,
    left: f64,
    top: f64,
    orig: GlyphFields,
    cand: GlyphFields,
}

#[allow(clippy::too_many_arguments)]
fn build_side(
    cover: Vec<f64>,
    w: usize,
    h: usize,
    left: f64,
    top: f64,
    params: &EngineParams,
    banks: &V1Banks,
    kernels: &OrientedKernels,
    label: &str,
) -> Side {
    let mut conv_o = Conv::new();
    let mut conv_c = Conv::new();
    let orig = original_glyph_fields(&cover, w, h, params, banks, kernels, &mut conv_o).unwrap();
    let cand = glyph_fields(&cover, w, h, params, banks, kernels, &mut conv_c, None).unwrap();
    assert_fields_bitwise(&orig, &cand, label);
    Side {
        cover,
        w,
        h,
        left,
        top,
        orig,
        cand,
    }
}

fn load_side(
    dataset: &str,
    cp: u32,
    params: &EngineParams,
    banks: &V1Banks,
    kernels: &OrientedKernels,
) -> (Side, String) {
    let (cover, w, h, left, top, sha) = real_cell(dataset, cp);
    let side = build_side(
        cover,
        w,
        h,
        left,
        top,
        params,
        banks,
        kernels,
        &format!("domain/{dataset}/U+{cp:04X}"),
    );
    (side, sha)
}

/// Per-step bit summaries: G2 (valid, faces, corners, g2/raw/floor/
/// rawfloor bits, both, abstain) and local (gl/max/weak/bound/shortfall
/// bits, both, skipped, abstain, reason).
struct StepBits {
    valid: bool,
    faces: usize,
    corners: usize,
    g2: [u64; 4],
    both: u64,
    abstain: bool,
    local: [u64; 4],
    lboth: u64,
    skipped: u64,
    labstain: u8,
    lreason: u8,
    lcond: [u64; 2],
}

#[allow(clippy::too_many_arguments)]
fn manual_domain(
    l: &Side,
    r: &Side,
    orig: bool,
    metric: i64,
    deltas: &[i64],
    params: &EngineParams,
    score: &ScoreParams,
    strength: Strength,
    facing: &[Vec<f64>],
) -> Vec<StepBits> {
    let (lf, rf) = if orig {
        (&l.orig, &r.orig)
    } else {
        (&l.cand, &r.cand)
    };
    let pad = params.pad() as f64;
    let lo = ((l.left - pad).trunc() as i64, (l.top - pad).trunc() as i64);
    let ro_base = ((r.left - pad).trunc() as i64, (r.top - pad).trunc() as i64);
    let ros: Vec<(i64, i64)> = deltas
        .iter()
        .map(|d| (ro_base.0 + metric + d, ro_base.1))
        .collect();
    let (origin, (ch, cw)) = union_canvas(lf.w, lf.h, lo, rf.w, rf.h, &ros);
    let el = self_energy(lf, strength);
    let er = self_energy(rf, strength);
    let local_l = local_energy_maps(lf, score.normalization_radius, strength);
    let local_r = local_energy_maps(rf, score.normalization_radius, strength);
    let mut out = Vec::with_capacity(deltas.len());
    for (d, ro) in deltas.iter().zip(ros.iter()) {
        let step = metric + d;
        let (overlaps, faces, corners) = contact_counts(
            &l.cover,
            l.w,
            l.h,
            (l.left, l.top),
            &r.cover,
            r.w,
            r.h,
            (r.left, r.top),
            step,
        );
        if overlaps > 0 {
            out.push(StepBits {
                valid: false,
                faces,
                corners,
                g2: [0; 4],
                both: 0,
                abstain: false,
                local: [0; 4],
                lboth: 0,
                skipped: 0,
                labstain: 0,
                lreason: 0,
                lcond: [0; 2],
            });
            continue;
        }
        let rec = score_step(
            lf, rf, lo, *ro, origin, cw, ch, &el, &er, score.tau, strength, facing, None,
        )
        .unwrap();
        let lrec = score_step_local(
            lf, rf, lo, *ro, origin, cw, ch, &local_l, &local_r, facing, score.tau, strength, None,
        )
        .unwrap();
        out.push(StepBits {
            valid: true,
            faces,
            corners,
            g2: [
                rec.g2.to_bits(),
                rec.raw.to_bits(),
                rec.floor_share.to_bits(),
                rec.raw_floor_share.to_bits(),
            ],
            both: rec.both_supported_pairpx,
            abstain: rec.abstain,
            local: [
                lrec.gl.to_bits(),
                lrec.max_term_cosine.to_bits(),
                lrec.weak_normalized_share.to_bits(),
                lrec.honest_bound.to_bits(),
            ],
            lboth: lrec.both_supported_pairpx,
            skipped: lrec.skipped_nonpositive,
            labstain: lrec.abstain as u8,
            lreason: match lrec.abstain_reason {
                None => 0,
                Some(yinyang_oriented_engine::LocalAbstain::NoSharedSupport) => 1,
                Some(yinyang_oriented_engine::LocalAbstain::ZeroLocalEvidence) => 2,
            },
            lcond: [lrec.conditioning_shortfall.to_bits(), 0],
        });
    }
    out
}

fn tie_choice(steps: &[StepBits], cstar: f64) -> (Vec<i64>, i64) {
    // Replicates the engine TIE-v2 selection over valid non-abstained
    // steps; step index order matches manual_domain order.
    let mut devs: Vec<f64> = Vec::new();
    let mut idx: Vec<usize> = Vec::new();
    for (i, s) in steps.iter().enumerate() {
        if s.valid && !s.abstain {
            let g = f64::from_bits(s.g2[0]);
            devs.push((g - cstar).abs());
            idx.push(i);
        }
    }
    if devs.is_empty() {
        return (Vec::new(), 0);
    }
    let (tie, _) = tie_set(&devs);
    let mut min_steps: Vec<i64> = tie.iter().map(|t| idx[*t] as i64).collect();
    min_steps.sort_unstable();
    let chosen = *min_steps.iter().min().unwrap();
    (min_steps, chosen)
}

fn select_pairs() -> Vec<(String, u32, u32, i64)> {
    // Bounded 6-pair selection across mono/gray/italic/small/large plus a
    // second family; first adapter entry per dataset whose glyphs load.
    let ad = adapter();
    let want = [
        "roboto-16-mono",
        "roboto-16-gray",
        "v3mono:roboto-italic-16",
        "v3mono:roboto-8",
        "roboto-24-mono",
        "literata-16-gray",
    ];
    let root = repo_root();
    let mut out = Vec::new();
    for ds in want {
        let info = &ad["datasets"][ds];
        let path = root.join(info["path"].as_str().unwrap());
        let data = load_capture(ds, &path).unwrap();
        let mut pick: Option<(u32, u32, i64)> = None;
        for key in ["study", "novel"] {
            for e in ad[key].as_array().unwrap() {
                if e["dataset"].as_str().unwrap() != ds {
                    continue;
                }
                let pair = e["pair"].as_str().unwrap();
                let mut ch = pair.chars();
                let (l, r) = (ch.next().unwrap() as u32, ch.next().unwrap() as u32);
                if data.cells.contains_key(&l) && data.cells.contains_key(&r) {
                    pick = Some((l, r, e["metric"].as_i64().unwrap()));
                    break;
                }
            }
            if pick.is_some() {
                break;
            }
        }
        let (l, r, metric) = pick.unwrap_or_else(|| panic!("no loadable pair for {ds}"));
        out.push((ds.to_string(), l, r, metric));
    }
    out
}

fn assert_steps_equal(a: &[StepBits], b: &[StepBits], label: &str) {
    assert_eq!(a.len(), b.len(), "{label}: step count");
    for (i, (x, y)) in a.iter().zip(b.iter()).enumerate() {
        assert_eq!(x.valid, y.valid, "{label}[{i}]: valid");
        assert_eq!(
            (x.faces, x.corners),
            (y.faces, y.corners),
            "{label}[{i}]: contact"
        );
        assert_eq!(x.g2, y.g2, "{label}[{i}]: G2 bits");
        assert_eq!(x.both, y.both, "{label}[{i}]: both_supported_pairpx");
        assert_eq!(x.abstain, y.abstain, "{label}[{i}]: abstain");
        assert_eq!(x.local, y.local, "{label}[{i}]: local bits");
        assert_eq!(x.lboth, y.lboth, "{label}[{i}]: local both");
        assert_eq!(x.skipped, y.skipped, "{label}[{i}]: skipped");
        assert_eq!(x.labstain, y.labstain, "{label}[{i}]: local abstain");
        assert_eq!(x.lreason, y.lreason, "{label}[{i}]: abstain reason");
        assert_eq!(x.lcond, y.lcond, "{label}[{i}]: conditioning");
    }
}

#[test]
fn f1_domain_score_parity() {
    let t0 = Instant::now();
    let score = ScoreParams::frozen();
    let facing = facing_matrix(16);
    let pairs = select_pairs();
    assert_eq!(pairs.len(), 6, "bounded selection must hold 6 pairs");
    let mut total_steps: u64 = 0;
    let mut pair_notes: Vec<serde_json::Value> = Vec::new();

    for params in [EngineParams::frozen(), r13q4_params()] {
        let cfg = if params.radius == 12 && params.q == 2.0 {
            "frozen"
        } else {
            "R13-q4"
        };
        let (banks, kernels) = build_pw(&params);
        // Candidate engine doubles as the harness check on frozen params.
        let mut engine = Engine::new(params.clone()).unwrap();
        for (ds, lcp, rcp, metric) in pairs.iter() {
            let (l, lsha) = load_side(ds, *lcp, &params, &banks, &kernels);
            let (r, _) = load_side(ds, *rcp, &params, &banks, &kernels);
            // Whole forward domain from the engine geometry.
            engine
                .load_glyph(ds, &lsha, *lcp, l.w, l.h, l.left, l.top, &l.cover)
                .unwrap();
            engine
                .load_glyph(ds, &lsha, *rcp, r.w, r.h, r.left, r.top, &r.cover)
                .unwrap();
            let domain = match engine.search_domain(ds, *lcp, *rcp).unwrap() {
                Ok(d) => d,
                Err(e) => panic!("{cfg}/{ds}: unexpected no-domain {e:?}"),
            };
            let deltas: Vec<i64> = (domain.lo..=domain.hi).collect();
            assert!(!deltas.is_empty(), "{cfg}/{ds}: empty domain");
            for strength in [Strength::Notebook, Strength::Manuscript] {
                let sname = match strength {
                    Strength::Notebook => "notebook",
                    Strength::Manuscript => "manuscript",
                };
                let mo = manual_domain(
                    &l, &r, true, *metric, &deltas, &params, &score, strength, &facing,
                );
                let mc = manual_domain(
                    &l, &r, false, *metric, &deltas, &params, &score, strength, &facing,
                );
                assert_steps_equal(&mo, &mc, &format!("{cfg}/{ds}/{sname}: orig-vs-cand"));
                total_steps += mo.len() as u64;
                // TIE exact (a scored step value) and midpoint between two
                // adjacent valid steps; lowest-index choice must agree.
                let valid_g2: Vec<f64> = mc
                    .iter()
                    .filter(|s| s.valid && !s.abstain)
                    .map(|s| f64::from_bits(s.g2[0]))
                    .collect();
                if valid_g2.len() >= 2 {
                    let exact = valid_g2[valid_g2.len() / 2];
                    let mid = 0.5 * (valid_g2[0] + valid_g2[1]);
                    for cstar in [exact, mid] {
                        let (omin, oc) = tie_choice(&mo, cstar);
                        let (cmin, cc) = tie_choice(&mc, cstar);
                        assert_eq!(
                            (omin, oc),
                            (cmin, cc),
                            "{cfg}/{ds}/{sname}: TIE choice at {cstar}"
                        );
                    }
                }
                // Harness self-check: manual candidate vs the engine on the
                // frozen config (both G2 and local paths).
                if cfg == "frozen" {
                    let er = engine
                        .score_pair(ds, *lcp, *rcp, *metric, &deltas, &score, strength, None)
                        .unwrap();
                    assert_eq!(er.steps.len(), mc.len());
                    for (i, (es, ms)) in er.steps.iter().zip(mc.iter()).enumerate() {
                        assert_eq!(es.valid, ms.valid, "engine valid {i}");
                        assert_eq!((es.faces, es.corners), (ms.faces, ms.corners));
                        if es.valid {
                            for (got, exp) in [
                                (es.g2.unwrap().to_bits(), ms.g2[0]),
                                (es.raw.unwrap().to_bits(), ms.g2[1]),
                                (es.floor_share.unwrap().to_bits(), ms.g2[2]),
                                (es.raw_floor_share.unwrap().to_bits(), ms.g2[3]),
                            ] {
                                assert_eq!(got, exp, "engine G2 bits {i}");
                            }
                            assert_eq!(es.both_supported_pairpx, ms.both);
                            assert_eq!(es.abstain, ms.abstain);
                        }
                    }
                    let lr = engine
                        .score_pair_local(ds, *lcp, *rcp, *metric, &deltas, &score, strength, None)
                        .unwrap();
                    for (i, (es, ms)) in lr.steps.iter().zip(mc.iter()).enumerate() {
                        if es.valid {
                            for (got, exp) in [
                                (es.gl.unwrap().to_bits(), ms.local[0]),
                                (es.max_term_cosine.unwrap().to_bits(), ms.local[1]),
                                (es.weak_normalized_share.unwrap().to_bits(), ms.local[2]),
                                (es.honest_bound.unwrap().to_bits(), ms.local[3]),
                            ] {
                                assert_eq!(got, exp, "engine local bits {i}");
                            }
                            assert_eq!(es.both_supported_pairpx, ms.lboth);
                            assert_eq!(es.abstain, ms.labstain == 1);
                            let exp_reason = match ms.lreason {
                                0 => None,
                                1 => Some("no_shared_support"),
                                _ => Some("zero_local_evidence"),
                            };
                            assert_eq!(es.abstain_reason.as_deref(), exp_reason);
                        }
                    }
                }
            }
            // Maps at the metric step: bitwise orig-vs-cand, both strengths.
            let d0: Vec<i64> = vec![0];
            let mo_nb = manual_domain(
                &l,
                &r,
                true,
                *metric,
                &d0,
                &params,
                &score,
                Strength::Notebook,
                &facing,
            );
            if mo_nb[0].valid {
                let mut maps: Vec<(bool, Strength, Vec<u64>, Vec<u64>)> = Vec::new();
                for strength in [Strength::Notebook, Strength::Manuscript] {
                    for orig in [true, false] {
                        let (lf, rf) = if orig {
                            (&l.orig, &r.orig)
                        } else {
                            (&l.cand, &r.cand)
                        };
                        let pad = params.pad() as f64;
                        let lo = ((l.left - pad).trunc() as i64, (l.top - pad).trunc() as i64);
                        let ro = (
                            ((r.left - pad).trunc() as i64) + *metric,
                            (r.top - pad).trunc() as i64,
                        );
                        let (origin, (ch, cw)) = union_canvas(lf.w, lf.h, lo, rf.w, rf.h, &[ro]);
                        let el = self_energy(lf, strength);
                        let er = self_energy(rf, strength);
                        let m = contribution_map(
                            lf, rf, lo, ro, origin, cw, ch, &el, &er, score.tau, strength, &facing,
                            None,
                        )
                        .unwrap();
                        let ll = local_energy_maps(lf, score.normalization_radius, strength);
                        let lr_ = local_energy_maps(rf, score.normalization_radius, strength);
                        let lm = contribution_map_local(
                            lf, rf, lo, ro, origin, cw, ch, &ll, &lr_, &facing, score.tau,
                            strength, None,
                        )
                        .unwrap();
                        maps.push((
                            orig,
                            strength,
                            m.iter().map(|v| v.to_bits()).collect(),
                            lm.iter().map(|v| v.to_bits()).collect(),
                        ));
                    }
                }
                assert_eq!(maps.len(), 4);
                assert_eq!(maps[0].2, maps[1].2, "{cfg}/{ds}: G2 notebook map bits");
                assert_eq!(maps[0].3, maps[1].3, "{cfg}/{ds}: local notebook map bits");
                assert_eq!(maps[2].2, maps[3].2, "{cfg}/{ds}: G2 manuscript map bits");
                assert_eq!(
                    maps[2].3, maps[3].3,
                    "{cfg}/{ds}: local manuscript map bits"
                );
            }
            pair_notes.push(serde_json::json!({
                "config": cfg, "dataset": ds,
                "pair": format!("{}{}", *lcp as u8 as char, *rcp as u8 as char),
                "metric": metric, "domain": [domain.lo, domain.hi],
                "steps": deltas.len(),
            }));
        }
        // Blank pair (abstain path) and disjoint-rows geometry guard.
        let (bn, _) = load_side("roboto-16-mono", 0x6E, &params, &banks, &kernels);
        let blank_cover = vec![0.0; bn.w * bn.h];
        let blank = build_side(
            blank_cover,
            bn.w,
            bn.h,
            bn.left,
            bn.top,
            &params,
            &banks,
            &kernels,
            &format!("{cfg}/blank"),
        );
        let deltas = [-2, -1, 0, 1, 2];
        for strength in [Strength::Notebook, Strength::Manuscript] {
            let mo = manual_domain(
                &blank, &bn, true, 8, &deltas, &params, &score, strength, &facing,
            );
            let mc = manual_domain(
                &blank, &bn, false, 8, &deltas, &params, &score, strength, &facing,
            );
            assert_steps_equal(&mo, &mc, &format!("{cfg}/blank"));
            assert!(
                mo.iter().all(|s| !s.valid || s.abstain),
                "{cfg}/blank: expected abstain-only steps"
            );
        }
        let _shifted = build_side(
            bn.cover.clone(),
            bn.w,
            bn.h,
            bn.left,
            bn.top + 1000.0,
            &params,
            &banks,
            &kernels,
            &format!("{cfg}/shifted"),
        );
        engine
            .load_glyph(
                "f1blank",
                "f1-blank-fixture",
                0xE000,
                bn.w,
                bn.h,
                bn.left,
                bn.top,
                &bn.cover,
            )
            .unwrap();
        engine
            .load_glyph(
                "f1blank",
                "f1-blank-fixture",
                0xE001,
                bn.w,
                bn.h,
                bn.left,
                bn.top + 1000.0,
                &bn.cover,
            )
            .unwrap();
        let dom = engine.search_domain("f1blank", 0xE000, 0xE001).unwrap();
        assert!(
            matches!(dom, Err(yinyang_oriented_engine::NoDomain::DisjointRows)),
            "{cfg}: disjoint-rows guard, got {dom:?}"
        );
        engine
            .load_glyph(
                "f1blank",
                "f1-blank-fixture",
                0xE002,
                blank.w,
                blank.h,
                blank.left,
                blank.top,
                &blank.cover,
            )
            .unwrap();
        let blank_dom = engine.search_domain("f1blank", 0xE002, 0xE000).unwrap();
        assert!(
            matches!(blank_dom, Err(yinyang_oriented_engine::NoDomain::Blank)),
            "{cfg}: blank guard, got {blank_dom:?}"
        );
        engine.clear_dataset("f1blank");
    }
    let summary = serde_json::json!({
        "test": "f1_domain_score_parity",
        "pairs": pair_notes,
        "compared_steps": total_steps,
        "seconds": t0.elapsed().as_secs_f64(),
    });
    println!("{summary}");
    if let Some(dir) = evidence_dir() {
        std::fs::write(
            dir.join("fft_reuse_domain_parity.json"),
            format!("{summary}"),
        )
        .unwrap();
    }
}

fn r13q4_params() -> EngineParams {
    let mut p = EngineParams::frozen();
    p.radius = 13;
    p.q = 4.0;
    p.validate().unwrap();
    p
}

#[test]
fn f1_field_timing() {
    // Alternating original-vs-candidate field builds after one warmup:
    // 3 reps x 2 glyphs on frozen params. Times only; parity is gated
    // above, so no time assertion here.
    let params = EngineParams::frozen();
    let (banks, kernels) = build_pw(&params);
    let (cover_n, wn, hn, _, _, _) = real_cell("roboto-16-mono", 0x6E);
    let (cover_g, wg, hg, _, _, _) = real_cell("roboto-16-gray", 0x6E);
    let glyphs = [("mono-n", cover_n, wn, hn), ("gray-n", cover_g, wg, hg)];
    let mut conv = Conv::new();
    for (label, cover, w, h) in glyphs.iter() {
        let _ = original_glyph_fields(cover, *w, *h, &params, &banks, &kernels, &mut conv);
        let _ = glyph_fields(cover, *w, *h, &params, &banks, &kernels, &mut conv, None);
        let _ = label;
    }
    let mut reps: Vec<serde_json::Value> = Vec::new();
    for rep in 0..3 {
        for (label, cover, w, h) in glyphs.iter() {
            let order: [bool; 2] = if rep % 2 == 0 {
                [true, false]
            } else {
                [false, true]
            };
            let mut times = HashMap::new();
            for is_orig in order {
                let t = Instant::now();
                if is_orig {
                    let _ = original_glyph_fields(
                        cover,
                        *w,
                        *h,
                        &params,
                        &banks,
                        &kernels,
                        &mut Conv::new(),
                    );
                } else {
                    let _ = glyph_fields(
                        cover,
                        *w,
                        *h,
                        &params,
                        &banks,
                        &kernels,
                        &mut Conv::new(),
                        None,
                    );
                }
                times.insert(
                    if is_orig { "orig_s" } else { "cand_s" },
                    t.elapsed().as_secs_f64(),
                );
            }
            reps.push(serde_json::json!({
                "rep": rep, "glyph": label,
                "orig_s": times["orig_s"], "cand_s": times["cand_s"],
            }));
        }
    }
    let summary = serde_json::json!({"test": "f1_field_timing", "reps": reps});
    println!("{summary}");
    if let Some(dir) = evidence_dir() {
        std::fs::write(dir.join("fft_reuse_timing.json"), format!("{summary}")).unwrap();
    }
}
