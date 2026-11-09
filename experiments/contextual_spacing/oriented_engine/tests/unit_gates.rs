//! Self-contained model gates (no corpus files needed).
//!
//! Expected values below come from the frozen Python modules (see the
//! command in each test's provenance comment); tolerances are asserted,
//! never relaxed.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use yinyang_oriented_engine::fields::GlyphFields;
use yinyang_oriented_engine::local_energy::{
    check_local_bound, confidence_local, contribution_map_local, disc_kernel, local_energy_direct,
    local_energy_maps, score_step_local, LocalAbstain,
};
use yinyang_oriented_engine::params::{EngineParams, ScoreParams, FROZEN_NORMALIZATION_RADIUS};
use yinyang_oriented_engine::score::{
    check_g2_bound, contact_counts, facing_matrix, pixel_round, score_step, self_energy, tie_set,
    union_canvas, Strength,
};
use yinyang_oriented_engine::{Engine, EngineError};

fn tiny_fields() -> GlyphFields {
    // Fixture from yinyang_oriented_score_evidence validation (2 channels,
    // 2x3): supported all but [0,1,2]; U2 = 2.0; notebook strengths as
    // listed; expected EL = [6, 8], g2 = 0.11720379331126889,
    // raw = 0.8120116994196762, both = 10 (frozen run, 2026-11-04).
    let supported = vec![
        vec![true, true, true, true, true, false],
        vec![true, true, true, true, true, true],
    ];
    let conf = vec![
        vec![1.0, 2.0, 0.0, 0.0, 1.0, 0.0],
        vec![1.0, 1.0, 1.0, 2.0, 0.0, 1.0],
    ];
    let dist = vec![
        vec![1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        vec![2.0, 2.0, 2.0, 2.0, 2.0, 2.0],
    ];
    GlyphFields {
        w: 3,
        h: 2,
        pad: 0,
        c_per_scale: Vec::new(),
        t_combined: Vec::new(),
        u1: vec![vec![0.0; 6], vec![0.0; 6]],
        u2: vec![vec![2.0; 6], vec![2.0; 6]],
        distance: dist,
        conf_nb: conf,
        arc: vec![vec![0.0; 6], vec![0.0; 6]],
        supported,
    }
}

#[test]
fn facing_sums_to_128() {
    // Frozen gate: sum(F) == 128 within 1e-9 (probe_new_engine.py).
    let f = facing_matrix(16);
    let sum: f64 = f.iter().flat_map(|r| r.iter()).sum();
    assert!((sum - 128.0).abs() < 1e-9, "facing sum = {sum}");
}

#[test]
fn tiny_manual_g2_matches_frozen() {
    let f = tiny_fields();
    let el = self_energy(&f, Strength::Notebook);
    assert_eq!(el, vec![6.0, 8.0]);
    let facing = facing_matrix(2);
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    let rec = score_step(
        &f,
        &f,
        (0, 0),
        (0, 0),
        origin,
        cw,
        ch,
        &el,
        &el,
        0.5,
        Strength::Notebook,
        &facing,
        None,
    )
    .unwrap();
    assert!(
        (rec.g2 - 0.11720379331126889).abs() < 1e-12,
        "g2 = {}",
        rec.g2
    );
    assert!(
        (rec.raw - 0.8120116994196762).abs() < 1e-9,
        "raw = {}",
        rec.raw
    );
    assert_eq!(rec.both_supported_pairpx, 10);
    assert!(!rec.abstain);
    check_g2_bound(rec.g2).unwrap();
}

#[test]
fn contribution_map_reduces_to_g2() {
    let f = tiny_fields();
    let el = self_energy(&f, Strength::Notebook);
    let facing = facing_matrix(2);
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    let map = yinyang_oriented_engine::score::contribution_map(
        &f,
        &f,
        (0, 0),
        (0, 0),
        origin,
        cw,
        ch,
        &el,
        &el,
        0.5,
        Strength::Notebook,
        &facing,
        None,
    )
    .unwrap();
    let rec = score_step(
        &f,
        &f,
        (0, 0),
        (0, 0),
        origin,
        cw,
        ch,
        &el,
        &el,
        0.5,
        Strength::Notebook,
        &facing,
        None,
    )
    .unwrap();
    let sum: f64 = map.iter().sum();
    assert!(
        (sum - rec.g2).abs() < 1e-12,
        "map sum {sum} vs g2 {}",
        rec.g2
    );
}

#[test]
fn tie_set_lowest_index_wins() {
    // TIE-v2: tol = 1e-9 * max(1, m*); single pick is the lowest index.
    let (idx, mstar) = tie_set(&[3.0, 1.0, 1.0 + 5e-10, 2.0]);
    assert_eq!(mstar, 1.0);
    assert_eq!(idx, vec![1, 2]);
    let (idx, _) = tie_set(&[0.5, 0.5, 0.5]);
    assert_eq!(idx, vec![0, 1, 2]);
}

#[test]
fn pixel_round_halves_away_from_zero() {
    // Frozen v1.pixel_round: 2.5 -> 3, -2.5 -> -3, 8.0 -> 8.
    assert_eq!(pixel_round(2.5), 3);
    assert_eq!(pixel_round(-2.5), -3);
    assert_eq!(pixel_round(8.0), 8);
}

#[test]
fn contact_counts_match_frozen() {
    // Frozen v1.contact_counts on 3x3 full cells at left 0 / right 5:
    // -4 -> 6 overlaps; -3 -> 3 overlaps; -2 -> faces 3 corners 4.
    let cover = vec![1.0; 9];
    let (ov, fa, co) = contact_counts(&cover, 3, 3, (0.0, 0.0), &cover, 3, 3, (5.0, 0.0), -4);
    assert_eq!((ov, fa, co), (6, 0, 0));
    let (ov, fa, co) = contact_counts(&cover, 3, 3, (0.0, 0.0), &cover, 3, 3, (5.0, 0.0), -3);
    assert_eq!((ov, fa, co), (3, 0, 0));
    let (ov, fa, co) = contact_counts(&cover, 3, 3, (0.0, 0.0), &cover, 3, 3, (5.0, 0.0), -2);
    assert_eq!((ov, fa, co), (0, 3, 4));
    let (ov, fa, co) = contact_counts(&cover, 3, 3, (0.0, 0.0), &cover, 3, 3, (5.0, 0.0), -1);
    assert_eq!((ov, fa, co), (0, 0, 0));
}

#[test]
fn params_reject_invalid_configs() {
    let p = EngineParams::frozen();
    p.validate().unwrap();
    Engine::new(EngineParams::frozen()).unwrap();
    for bad in [
        EngineParams {
            q: 0.1,
            ..EngineParams::frozen()
        },
        EngineParams {
            q: f64::NAN,
            ..EngineParams::frozen()
        },
        EngineParams {
            radius: 0,
            ..EngineParams::frozen()
        },
        EngineParams {
            radius: 65,
            ..EngineParams::frozen()
        },
        EngineParams {
            kappa: -1.0,
            ..EngineParams::frozen()
        },
        EngineParams {
            weights: vec![1.0, 1.0],
            ..EngineParams::frozen()
        },
        EngineParams {
            weights: vec![1.0, -1.0, 1.0, 1.0, 1.0],
            ..EngineParams::frozen()
        },
    ] {
        assert!(bad.validate().is_err(), "accepted {bad:?}");
    }
    assert!(ScoreParams { tau: 0.0, ..ScoreParams::frozen() }
        .validate()
        .is_err());
    assert!(ScoreParams {
        tau: f64::INFINITY,
        ..ScoreParams::frozen()
    }
    .validate()
    .is_err());
    assert!(ScoreParams {
        tau: 0.5,
        normalization_radius: 0
    }
    .validate()
    .is_err());
    assert!(ScoreParams {
        tau: 0.5,
        normalization_radius: 65
    }
    .validate()
    .is_err());
}

#[test]
fn strength_names_are_explicit() {
    assert!(Strength::parse("notebook").is_ok());
    assert!(Strength::parse("manuscript").is_ok());
    assert!(Strength::parse("b2").is_err());
}

#[test]
fn blank_glyph_abstains_with_zero_energy() {
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let cover = vec![0.0; 12 * 12];
    eng.load_glyph("d", "sha", 0x41, 12, 12, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 12, 12, 20.0, 0.0, &cover)
        .unwrap();
    let res = eng
        .score_pair(
            "d",
            0x41,
            0x42,
            12,
            &[-2, -1, 0, 1, 2],
            &ScoreParams::frozen(),
            Strength::Notebook,
            Some(4.0),
        )
        .unwrap();
    // Blank steps stay valid (only overlap invalidates) and abstain; the
    // search excludes abstained steps from TIE-v2, so an all-abstain curve
    // retains Source with a reason instead of letting G2 = 0 win.
    assert!(res.fallback);
    assert_eq!(res.chosen, 12);
    assert!(res.minimizing.is_empty());
    assert_eq!(res.fallback_reason.as_deref(), Some("no_shared_support"));
    for s in res.steps {
        assert!(s.valid);
        assert!(s.abstain);
        assert_eq!(s.g2, Some(0.0));
    }
}

#[test]
fn cache_identity_keys_full_frame() {
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 8 * 8];
    cover[3 * 8 + 3] = 1.0;
    assert!(eng
        .load_glyph("d", "sha1", 0x41, 8, 8, 0.0, 0.0, &cover)
        .unwrap());
    // Same bytes: no recompute.
    assert!(!eng
        .load_glyph("d", "sha1", 0x41, 8, 8, 0.0, 0.0, &cover)
        .unwrap());
    // Same codepoint, different capture: recompute.
    assert!(eng
        .load_glyph("d", "sha2", 0x41, 8, 8, 0.0, 0.0, &cover)
        .unwrap());
    // Same codepoint+capture, different ink: recompute.
    cover[4 * 8 + 4] = 1.0;
    assert!(eng
        .load_glyph("d", "sha2", 0x41, 8, 8, 0.0, 0.0, &cover)
        .unwrap());
    // Nonfinite cover errors.
    cover[0] = f64::NAN;
    assert!(matches!(
        eng.load_glyph("d", "sha2", 0x41, 8, 8, 0.0, 0.0, &cover),
        Err(EngineError::Invalid(_))
    ));
    eng.clear_dataset("d");
    assert_eq!(eng.cache_sizes(), (0, 0));
}

#[test]
fn shared_step_g2_is_canvas_invariant() {
    // Widening the sweep never changes shared-step G2 (union canvas is
    // embedding only). Bitwise: accumulation order is identical.
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 16, 16, 20.0, 0.0, &cover)
        .unwrap();
    let narrow = eng
        .score_pair(
            "d",
            0x41,
            0x42,
            10,
            &[-2, -1, 0, 1, 2],
            &ScoreParams::frozen(),
            Strength::Notebook,
            None,
        )
        .unwrap();
    let broad = eng
        .score_pair(
            "d",
            0x41,
            0x42,
            10,
            &[-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6],
            &ScoreParams::frozen(),
            Strength::Notebook,
            None,
        )
        .unwrap();
    for n in narrow.steps {
        let b = broad.steps.iter().find(|s| s.step == n.step).unwrap();
        assert_eq!(n.g2, b.g2, "step {}", n.step);
    }
}

#[test]
fn single_active_weight_matches_own_scale() {
    // Limiting-case gate: single-active weight reproduces that scale's C.
    let mut p = EngineParams::frozen();
    p.weights = vec![0.0, 0.0, 1.0, 0.0, 0.0];
    let mut eng = Engine::new(p).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    let (t, _, _) = eng.glyph_component("d", 0x41, "t_combined", 3, 0).unwrap();
    let (c, _, _) = eng.glyph_component("d", 0x41, "c_scale", 3, 2).unwrap();
    assert_eq!(t, c);
}

#[test]
fn slate_projection_is_bounded() {
    // Parent-preferred view max_o(c/sqrt(E)) sits in [0,1] wherever defined.
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    let (slate, _, _) = eng.glyph_component("d", 0x41, "slate", 0, 0).unwrap();
    assert!(slate
        .iter()
        .all(|v| v.is_finite() && *v >= 0.0 && *v <= 1.0));
    assert!(slate.iter().any(|v| *v > 0.0));
    let peak = eng.slate_max("d", 0x41).unwrap();
    let max: f64 = slate.iter().cloned().fold(0.0, f64::max);
    assert_eq!(peak, max);
}

#[test]
fn cancel_is_buffer_safe() {
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 16, 16, 20.0, 0.0, &cover)
        .unwrap();
    eng.cancel();
    let out = eng.score_pair(
        "d",
        0x41,
        0x42,
        10,
        &[-2, -1, 0, 1, 2],
        &ScoreParams::frozen(),
        Strength::Notebook,
        Some(4.0),
    );
    assert!(matches!(out, Err(EngineError::Cancelled)));
    // Buffers survive: resume and score normally.
    eng.clear_cancel();
    let flag: Arc<AtomicBool> = eng.cancel_flag();
    assert!(!flag.load(Ordering::Relaxed));
    let res = eng
        .score_pair(
            "d",
            0x41,
            0x42,
            10,
            &[-2, -1, 0, 1, 2],
            &ScoreParams::frozen(),
            Strength::Notebook,
            Some(4.0),
        )
        .unwrap();
    assert!(!res.fallback);
}

#[test]
fn abstained_steps_cannot_win_small_targets() {
    // Search-v1 selection: an abstained tail (G2 = 0) loses to a supported
    // step even when the target is 0. Two single-ink glyphs far apart:
    // wide steps abstain, tight steps carry signal.
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 8 * 8];
    cover[3 * 8 + 3] = 1.0;
    eng.load_glyph("d", "sha", 0x41, 8, 8, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 8, 8, 0.0, 0.0, &cover)
        .unwrap();
    let domain = eng.search_domain("d", 0x41, 0x42).unwrap().unwrap();
    assert!(domain.lo <= domain.hi);
    let deltas: Vec<i64> = (domain.lo..=domain.hi).map(|s| s - 4).collect();
    assert!(deltas.len() <= 512, "frozen domain fits the sweep guard");
    let res = eng
        .score_pair(
            "d",
            0x41,
            0x42,
            4,
            &deltas,
            &ScoreParams::frozen(),
            Strength::Notebook,
            Some(0.0),
        )
        .unwrap();
    assert!(!res.fallback, "supported steps exist");
    let ci = res.steps.iter().position(|s| s.step == res.chosen).unwrap();
    assert!(
        !res.steps[ci].abstain,
        "target 0 must not pick an abstain step"
    );
}

#[test]
fn search_domain_bounds_come_from_ink_and_pad() {
    // Hand-computed: left ink x in {3,4}, right ink x in {10,11} at step
    // 0, so ink-order lo = 3 - 11 = -8, clamped to the forward-order
    // floor 1; pad = 12 + 12 = 24 under frozen params.
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut left = vec![0.0; 8 * 8];
    left[3 * 8 + 2] = 1.0;
    left[3 * 8 + 3] = 1.0;
    let mut right = vec![0.0; 8 * 8];
    right[3 * 8 + 1] = 1.0;
    right[3 * 8 + 2] = 1.0;
    eng.load_glyph("d", "sha", 0x41, 8, 8, 1.0, 0.0, &left)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 8, 8, 9.0, 0.0, &right)
        .unwrap();
    let domain = eng.search_domain("d", 0x41, 0x42).unwrap().unwrap();
    assert_eq!(domain.lo, 1);
    let pad = 24i64;
    assert_eq!(domain.hi, (1 - pad) + (8 + 2 * 24) - 1 - (9 - pad));
}

#[test]
fn search_domain_never_moves_pen_backward() {
    // LTR layout admissibility: the ordered domain holds only strictly
    // positive advances, even when the ink-order term goes negative.
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 8 * 8];
    cover[3 * 8 + 3] = 1.0;
    eng.load_glyph("d", "sha", 0x41, 8, 8, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 8, 8, 0.0, 0.0, &cover)
        .unwrap();
    let domain = eng.search_domain("d", 0x41, 0x42).unwrap().unwrap();
    assert!(domain.lo >= 1, "forward pen order, got {:?}", domain);
    assert!(domain.lo <= domain.hi);
}

#[test]
fn search_domain_reports_blank_and_disjoint_rows() {
    use yinyang_oriented_engine::NoDomain;
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let blank = vec![0.0; 8 * 8];
    let mut ink = vec![0.0; 8 * 8];
    ink[3 * 8 + 3] = 1.0;
    eng.load_glyph("d", "sha", 0x41, 8, 8, 0.0, 0.0, &blank)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 8, 8, 0.0, 0.0, &ink)
        .unwrap();
    assert_eq!(
        eng.search_domain("d", 0x41, 0x42).unwrap(),
        Err(NoDomain::Blank)
    );
    // Same ink, rows separated beyond twice the pad: disjoint, not blank.
    eng.load_glyph("d", "sha2", 0x41, 8, 8, 0.0, 0.0, &ink)
        .unwrap();
    eng.load_glyph("d", "sha2", 0x42, 8, 8, 0.0, 200.0, &ink)
        .unwrap();
    assert_eq!(
        eng.search_domain("d", 0x42, 0x41).unwrap(),
        Err(NoDomain::DisjointRows)
    );
}

fn tiny_local_pair() -> (GlyphFields, GlyphFields) {
    // Mirrors the exporter's tiny_pair (all-supported 2x3, notebook):
    // expected gl = 0.9504872700785215, both = 12, weak = 0,
    // maxterm = 0.5172510845694978, bound = 12 (local_adapter.json tiny,
    // via the frozen pilot module, 2026-11-05).
    let mk = |conf: Vec<Vec<f64>>, dist: f64, u2: f64| GlyphFields {
        w: 3,
        h: 2,
        pad: 0,
        c_per_scale: Vec::new(),
        t_combined: Vec::new(),
        u1: vec![vec![0.0; 6], vec![0.0; 6]],
        u2: vec![vec![u2; 6], vec![u2; 6]],
        distance: vec![vec![dist; 6], vec![dist; 6]],
        conf_nb: conf,
        arc: vec![vec![0.0; 6], vec![0.0; 6]],
        supported: vec![vec![true; 6], vec![true; 6]],
    };
    let lf = mk(
        vec![
            vec![1.0, 2.0, 0.0, 0.0, 1.0, 1.0],
            vec![1.0, 1.0, 1.0, 2.0, 0.0, 1.0],
        ],
        1.0,
        2.0,
    );
    let mut rf = mk(
        vec![
            vec![2.0, 1.0, 1.0, 1.0, 0.0, 2.0],
            vec![0.0, 2.0, 1.0, 1.0, 1.0, 0.0],
        ],
        1.5,
        3.0,
    );
    rf.distance[1] = vec![0.5; 6];
    (lf, rf)
}

#[test]
fn local_tiny_matches_pilot_reference() {
    let (lf, rf) = tiny_local_pair();
    let el = local_energy_maps(&lf, 12, Strength::Notebook);
    let er = local_energy_maps(&rf, 12, Strength::Notebook);
    // Whole-lattice pool at R=12: uniform maps equal to channel energies.
    for (map, total) in [(0, 7.0), (1, 8.0)] {
        for v in el[map].iter() {
            assert!((v - total).abs() < 1e-9, "EL[{map}] = {v}, want {total}");
        }
    }
    for (map, total) in [(0, 11.0), (1, 7.0)] {
        for v in er[map].iter() {
            assert!((v - total).abs() < 1e-9, "ER[{map}] = {v}, want {total}");
        }
    }
    let facing = facing_matrix(2);
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    let rec = score_step_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert!(
        (rec.gl - 0.9504872700785215).abs() < 1e-9,
        "gl = {}",
        rec.gl
    );
    assert_eq!(rec.both_supported_pairpx, 12);
    assert!(rec.weak_normalized_share.abs() < 1e-12);
    assert!((rec.max_term_cosine - 0.5172510845694978).abs() < 1e-9);
    assert!(!rec.abstain);
    assert!(rec.abstain_reason.is_none());
    assert_eq!(rec.skipped_nonpositive, 0);
    assert!(rec.conditioning_shortfall.abs() < 1e-12);
    assert!((rec.honest_bound - 12.0).abs() < 1e-9);
    check_local_bound(rec.gl, rec.honest_bound, 1e-9).unwrap();
}

#[test]
fn local_energy_matches_independent_direct_within_arithmetic_bound() {
    // Production (f64 tap-inner order) vs independent Complex reference
    // (tap-outer order): agreement bound derived from the operator/data
    // arithmetic, never tuned — each sum of ntaps nonnegatives errs by at
    // most ntaps*eps*S, so two orders agree within 2*ntaps*eps*max.
    let radius = 12u32;
    let (kernel, _) = disc_kernel(radius);
    let ntaps = kernel.iter().filter(|&&v| v != 0.0).count() as f64;
    // Deterministic pseudo-random strengths (LCG, fixed seed).
    let (w, h) = (25usize, 19usize);
    let mut state = 0x12345678u64;
    let mut unit = Vec::with_capacity(2 * w * h);
    for _ in 0..2 * w * h {
        state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        unit.push(((state >> 33) as f64) / (u32::MAX as f64));
    }
    for scale in [0.0, 1.0, 2.5] {
        let mut lf = tiny_local_pair().0;
        lf.w = w;
        lf.h = h;
        for o in 0..2 {
            lf.conf_nb[o] = unit[o * w * h..(o + 1) * w * h]
                .iter()
                .map(|v| v * scale)
                .collect();
            lf.supported[o] = vec![true; w * h];
        }
        let prod = local_energy_maps(&lf, radius, Strength::Notebook);
        for o in 0..2 {
            let c2: Vec<f64> = lf.conf_nb[o].iter().map(|v| v * v).collect();
            let direct = local_energy_direct(&c2, w, h, radius);
            let maxv = prod[o]
                .iter()
                .chain(direct.iter())
                .cloned()
                .fold(0.0f64, f64::max);
            let bound = 2.0 * ntaps * f64::EPSILON * maxv;
            let mut worst = 0.0f64;
            for (a, b) in prod[o].iter().zip(direct.iter()) {
                worst = worst.max((*a - *b).abs());
            }
            assert!(
                worst <= bound,
                "order-dependence {worst} exceeds arithmetic bound {bound}"
            );
            // Nonnegative by construction, on every cell.
            assert!(prod[o].iter().all(|&v| v >= 0.0));
            // Center inclusion up to the one-sided summation bound.
            for (i, m) in lf.supported[o].iter().enumerate() {
                if *m {
                    let c2v = lf.conf_nb[o][i] * lf.conf_nb[o][i];
                    assert!(
                        prod[o][i] + ntaps * f64::EPSILON * maxv >= c2v,
                        "center undercut: EL={} c2={c2v}",
                        prod[o][i]
                    );
                }
            }
        }
    }
}

#[test]
fn local_energy_is_nonnegative_on_adversarial_ink() {
    // Single-strong-pixel plus weak tail: the FFT path produced negative
    // energies here (review oracle: -1.79e-15). Direct positive summation
    // stays nonnegative by construction and honors center inclusion.
    let mut lf = tiny_local_pair().0;
    for o in 0..2 {
        lf.conf_nb[o] = vec![1e-150; 6];
    }
    lf.conf_nb[0][0] = 3.0;
    lf.conf_nb[1][5] = 2.0;
    let maps = local_energy_maps(&lf, 12, Strength::Notebook);
    for o in 0..2 {
        assert!(maps[o].iter().all(|&v| v >= 0.0));
    }
    // R=12 disc covers the whole 2x3 lattice: every cell pools everything.
    let total0: f64 = lf.conf_nb[0].iter().map(|v| v * v).sum();
    let total1: f64 = lf.conf_nb[1].iter().map(|v| v * v).sum();
    for v in maps[0].iter() {
        assert!((v - total0).abs() <= 1e-12 * total0.max(1.0));
    }
    for v in maps[1].iter() {
        assert!((v - total1).abs() <= 1e-12 * total1.max(1.0));
    }
}

#[test]
fn local_map_reduces_to_gl() {
    let (lf, rf) = tiny_local_pair();
    let el = local_energy_maps(&lf, 12, Strength::Notebook);
    let er = local_energy_maps(&rf, 12, Strength::Notebook);
    let facing = facing_matrix(2);
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    let rec = score_step_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    let map = contribution_map_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    let sum: f64 = map.iter().sum();
    assert!(
        (sum - rec.gl).abs() < 1e-12,
        "map sum {sum} vs gl {}",
        rec.gl
    );
}

#[test]
fn local_abstain_reconciles_evidence_agreement_underflow() {
    let facing = facing_matrix(2);
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    // (a) Zero evidence: disjoint supported pixels.
    let mut lf = tiny_local_pair().0;
    let mut rf = tiny_local_pair().1;
    for o in 0..2 {
        for i in 0..6 {
            lf.supported[o][i] = i < 3;
            rf.supported[o][i] = i >= 3;
        }
    }
    let el = local_energy_maps(&lf, 12, Strength::Notebook);
    let er = local_energy_maps(&rf, 12, Strength::Notebook);
    let rec = score_step_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert!(rec.abstain);
    assert_eq!(rec.abstain_reason, Some(LocalAbstain::NoSharedSupport));
    // (b) Valid zero agreement: healthy energies, all c products zero.
    let mk_zero = |l0: Vec<f64>, r1: Vec<f64>| {
        let mut l = tiny_local_pair().0;
        let mut r = tiny_local_pair().1;
        l.conf_nb = vec![l0, vec![0.0; 6]];
        r.conf_nb = vec![vec![0.0; 6], r1];
        (l, r)
    };
    let (lz, rz) = mk_zero(vec![1.0, 0.0, 0.0, 0.0, 0.0, 0.0], vec![0.0, 0.0, 0.0, 0.0, 0.0, 1.0]);
    let el = local_energy_maps(&lz, 12, Strength::Notebook);
    let er = local_energy_maps(&rz, 12, Strength::Notebook);
    let rec = score_step_local(
        &lz, &rz, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert!(!rec.abstain, "valid zero agreement must stay eligible");
    assert_eq!(rec.gl, 0.0);
    // (c) Underflow: c^2 vanishes in f64, energies hit zero -> guarded.
    let tiny = 1e-200f64;
    let (mut lu, mut ru) = (tiny_local_pair().0, tiny_local_pair().1);
    for o in 0..2 {
        for v in lu.conf_nb[o].iter_mut() {
            *v = tiny;
        }
        for v in ru.conf_nb[o].iter_mut() {
            *v = tiny;
        }
    }
    let el = local_energy_maps(&lu, 12, Strength::Notebook);
    let er = local_energy_maps(&ru, 12, Strength::Notebook);
    let rec = score_step_local(
        &lu, &ru, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert!(rec.abstain);
    assert_eq!(rec.abstain_reason, Some(LocalAbstain::ZeroLocalEvidence));
    assert!(rec.skipped_nonpositive > 0);
    // G2 contrast on the same underflow fields: zero whole-glyph energies
    // trip its per-pair energy gate (pairs skipped, both count stays 0),
    // so the frozen oracle also abstains here — through an anonymous
    // gate, while L reports the explicit ZeroLocalEvidence reason.
    let eln = self_energy(&lu, Strength::Notebook);
    let ern = self_energy(&ru, Strength::Notebook);
    let g = score_step(
        &lu, &ru, (0, 0), (0, 0), origin, cw, ch, &eln, &ern, 0.5,
        Strength::Notebook, &facing, None,
    )
    .unwrap();
    assert!(g.abstain);
    assert_eq!(g.g2, 0.0);
}

#[test]
fn local_bound_is_geometric_not_128() {
    let (lf, rf) = tiny_local_pair();
    let el = local_energy_maps(&lf, 12, Strength::Notebook);
    let er = local_energy_maps(&rf, 12, Strength::Notebook);
    let facing = facing_matrix(2);
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    let rec = score_step_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    // Honest bound is sum w*|both| = 12 here, not the G2 128 clamp.
    assert!((rec.honest_bound - 12.0).abs() < 1e-9);
    check_local_bound(rec.gl, rec.honest_bound, 1e-9).unwrap();
    assert!(check_local_bound(rec.honest_bound + 1.0, rec.honest_bound, 1e-9).is_err());
}

#[test]
fn local_confidence_is_symmetric_and_common_support() {
    let (lf, _) = tiny_local_pair();
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    let c = confidence_local(&lf, &lf, (0, 0), (0, 0), origin, cw, ch, Strength::Notebook);
    // Support-unit names: raw strength sums and union canvas pixels only,
    // never gl-unit normalized mass or energy-eligible scored counts.
    assert!((c.support_mass_l - c.support_mass_r).abs() / c.support_mass_l.max(1.0) < 1e-12);
    assert!((c.support_weak_mass_l - c.support_weak_mass_r).abs() < 1e-9);
    // Union is the full 2x3 canvas here: share == 1.
    assert_eq!(c.support_union_pairpx, 6);
    assert!((c.support_share - 1.0).abs() < 1e-12);
    // Widened canvas: masses identical, share drops honestly.
    let (origin2, (ch2, cw2)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0), (6, 0)]);
    let c2 = confidence_local(&lf, &lf, (0, 0), (0, 0), origin2, cw2, ch2, Strength::Notebook);
    assert!((c2.support_mass_l - c.support_mass_l).abs() < 1e-12);
    assert_eq!(c2.support_union_pairpx, 6);
    assert!(c2.support_share < c.support_share);
}

#[test]
fn local_cache_keys_radius_and_strength() {
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    let m12 = eng
        .local_energy_for("d", 0x41, Strength::Notebook, 12)
        .unwrap();
    let m24 = eng
        .local_energy_for("d", 0x41, Strength::Notebook, 24)
        .unwrap();
    assert!(!Arc::ptr_eq(&m12, &m24));
    let m12b = eng
        .local_energy_for("d", 0x41, Strength::Notebook, 12)
        .unwrap();
    assert!(Arc::ptr_eq(&m12, &m12b));
    let mms = eng
        .local_energy_for("d", 0x41, Strength::Manuscript, 12)
        .unwrap();
    assert!(!Arc::ptr_eq(&m12, &mms));
    // Radius guardrails: 1 and 64 work, 0 and 65 reject.
    eng.local_energy_for("d", 0x41, Strength::Notebook, 1)
        .unwrap();
    eng.local_energy_for("d", 0x41, Strength::Notebook, 64)
        .unwrap();
    assert!(eng
        .local_energy_for("d", 0x41, Strength::Notebook, 0)
        .is_err());
    assert!(eng
        .local_energy_for("d", 0x41, Strength::Notebook, 65)
        .is_err());
    // Reload with different bytes invalidates structurally.
    let mut cover2 = cover.clone();
    cover2[5 * 16 + 5] = 0.0;
    eng.load_glyph("d", "sha2", 0x41, 16, 16, 0.0, 0.0, &cover2)
        .unwrap();
    let m12c = eng
        .local_energy_for("d", 0x41, Strength::Notebook, 12)
        .unwrap();
    assert!(!Arc::ptr_eq(&m12, &m12c));
}

#[test]
fn local_cancel_is_buffer_safe() {
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    eng.cancel();
    let res = eng.score_pair_local(
        "d",
        0x41,
        0x42,
        0,
        &[-2, -1, 0, 1, 2],
        &ScoreParams::frozen(),
        Strength::Notebook,
        None,
    );
    assert!(matches!(res, Err(EngineError::Cancelled)));
    eng.clear_cancel();
    let res = eng
        .score_pair_local(
            "d",
            0x41,
            0x42,
            0,
            &[-2, -1, 0, 1, 2],
            &ScoreParams::frozen(),
            Strength::Notebook,
            None,
        )
        .unwrap();
    assert_eq!(res.steps.len(), 5);
}

#[test]
fn local_tie_targets_behave() {
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    // C* = 0 picks the minimum-gl valid step.
    let res = eng
        .score_pair_local(
            "d",
            0x41,
            0x42,
            0,
            &[-2, -1, 0, 1, 2],
            &ScoreParams::frozen(),
            Strength::Notebook,
            Some(0.0),
        )
        .unwrap();
    let mut best = (i64::MAX, f64::INFINITY);
    for s in res.steps.iter().filter(|s| s.valid && !s.abstain) {
        let g = s.gl.unwrap();
        if g < best.1 {
            best = (s.step, g);
        }
    }
    assert_eq!(res.chosen, best.0);
    // Unreachable target picks the closest step.
    let res = eng
        .score_pair_local(
            "d",
            0x41,
            0x42,
            0,
            &[-2, -1, 0, 1, 2],
            &ScoreParams::frozen(),
            Strength::Notebook,
            Some(1e6),
        )
        .unwrap();
    assert!(!res.fallback);
    // Negative target rejects.
    assert!(eng
        .score_pair_local(
            "d",
            0x41,
            0x42,
            0,
            &[-2, -1, 0, 1, 2],
            &ScoreParams::frozen(),
            Strength::Notebook,
            Some(-1.0),
        )
        .is_err());
}

#[test]
fn local_shared_steps_are_canvas_invariant() {
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    let narrow: Vec<i64> = (-2..=2).collect();
    let wide: Vec<i64> = (-6..=6).collect();
    let rn = eng
        .score_pair_local(
            "d",
            0x41,
            0x42,
            0,
            &narrow,
            &ScoreParams::frozen(),
            Strength::Notebook,
            None,
        )
        .unwrap();
    let rw = eng
        .score_pair_local(
            "d",
            0x41,
            0x42,
            0,
            &wide,
            &ScoreParams::frozen(),
            Strength::Notebook,
            None,
        )
        .unwrap();
    for sn in rn.steps.iter() {
        let sw = rw.steps.iter().find(|s| s.step == sn.step).unwrap();
        match (sn.gl, sw.gl) {
            (Some(a), Some(b)) => assert!((a - b).abs() < 1e-12, "step {}", sn.step),
            (None, None) => {}
            _ => panic!("eligibility differs at step {}", sn.step),
        }
    }
}

#[test]
fn local_wide_r_q_guardrails_work() {
    // Extended field params plus wide/narrow normalizer radii verify
    // without silent control changes.
    let mut p = EngineParams::frozen();
    p.q = 16.0;
    p.radius = 32;
    let mut eng = Engine::new(p).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    for radius in [1u32, 12] {
        let score = ScoreParams {
            tau: 0.5,
            normalization_radius: radius,
        };
        let res = eng
            .score_pair_local(
                "d",
                0x41,
                0x42,
                0,
                &[-2, -1, 0, 1, 2],
                &score,
                Strength::Notebook,
                None,
            )
            .unwrap();
        assert_eq!(res.steps.len(), 5);
    }
    // Radius 64 exercises the same code path with a ~12.9k-tap disc.
    // Direct summation cost scales with taps, so this leg uses a minimal
    // cover (it asserts shapes/counts only; timing is bench-measured).
    let mut eng64 = Engine::new(EngineParams::frozen()).unwrap();
    let cover64 = vec![1.0; 4 * 4];
    eng64
        .load_glyph("d64", "sha", 0x41, 4, 4, 0.0, 0.0, &cover64)
        .unwrap();
    eng64
        .load_glyph("d64", "sha", 0x42, 4, 4, 0.0, 0.0, &cover64)
        .unwrap();
    let res64 = eng64
        .score_pair_local(
            "d64",
            0x41,
            0x42,
            0,
            &[-2, -1, 0, 1, 2],
            &ScoreParams {
                tau: 0.5,
                normalization_radius: 64,
            },
            Strength::Notebook,
            None,
        )
        .unwrap();
    assert_eq!(res64.steps.len(), 5);
    // Manuscript strength path works too.
    let res = eng
        .score_pair_local(
            "d",
            0x41,
            0x42,
            0,
            &[-2, -1, 0, 1, 2],
            &ScoreParams::frozen(),
            Strength::Manuscript,
            None,
        )
        .unwrap();
    assert_eq!(res.steps.len(), 5);
}

#[test]
fn local_components_are_explicitly_normalized() {
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 16 * 16];
    for y in 4..12 {
        for x in 4..6 {
            cover[y * 16 + x] = 1.0;
        }
    }
    eng.load_glyph("d", "sha", 0x41, 16, 16, 0.0, 0.0, &cover)
        .unwrap();
    // lnorm equals c/sqrt(EL) on supported pixels, zero elsewhere.
    let (lnorm, w, h) = eng.glyph_component("d", 0x41, "lnorm", 0, 0).unwrap();
    let (el, _, _) = eng
        .glyph_component("d", 0x41, "local_energy", 0, 0)
        .unwrap();
    let (c, _, _) = eng
        .glyph_component("d", 0x41, "confidence_notebook", 0, 0)
        .unwrap();
    let (sup, sw, sh) = eng.glyph_component("d", 0x41, "supported", 0, 0).unwrap();
    assert_eq!((sw, sh), (w, h));
    assert_eq!(w, h);
    assert!(w > 16);
    for i in 0..w * h {
        let expect = if sup[i] > 0.5 && el[i] > 0.0 && el[i].is_finite() {
            c[i] / el[i].sqrt()
        } else {
            0.0
        };
        assert!((lnorm[i] - expect).abs() < 1e-12, "pixel {i}");
    }
    // lslate is the per-pixel max over channels of lnorm.
    let (lslate, _, _) = eng.glyph_component("d", 0x41, "lslate", 0, 0).unwrap();
    for i in 0..w * h {
        let mut best = 0.0;
        for o in 0..16 {
            let (chn, _, _) = eng.glyph_component("d", 0x41, "lnorm", o, 0).unwrap();
            if chn[i] > best {
                best = chn[i];
            }
        }
        assert!((lslate[i] - best).abs() < 1e-12, "pixel {i}");
    }
    assert!(eng.glyph_component("d", 0x41, "nope", 0, 0).is_err());
}

#[test]
fn local_kernel_intersection_matches_shifted_and_padded_canvas() {
    // Fused single-pass + clipped intersection traversal: the same
    // relative placement scores bit-identical results under a shifted
    // canvas origin (negative origins included) and under extra dead
    // canvas border; the dead border only appends zeros to the map.
    let (lf, rf) = tiny_local_pair();
    let el = local_energy_maps(&lf, 12, Strength::Notebook);
    let er = local_energy_maps(&rf, 12, Strength::Notebook);
    let facing = facing_matrix(2);
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    let base = score_step_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    let base_map = contribution_map_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    // Shifted origin, including negative coordinates.
    let (origin2, (ch2, cw2)) = union_canvas(3, 2, (-9, -4), 3, 2, &[(-9, -4)]);
    let shifted = score_step_local(
        &lf, &rf, (-9, -4), (-9, -4), origin2, cw2, ch2, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert_eq!(base.gl.to_bits(), shifted.gl.to_bits());
    assert_eq!(
        base.both_supported_pairpx,
        shifted.both_supported_pairpx
    );
    assert_eq!(
        base.weak_normalized_share.to_bits(),
        shifted.weak_normalized_share.to_bits()
    );
    assert_eq!(
        base.max_term_cosine.to_bits(),
        shifted.max_term_cosine.to_bits()
    );
    assert_eq!(
        base.conditioning_shortfall.to_bits(),
        shifted.conditioning_shortfall.to_bits()
    );
    assert_eq!(
        base.honest_bound.to_bits(),
        shifted.honest_bound.to_bits()
    );
    assert_eq!(base.skipped_nonpositive, shifted.skipped_nonpositive);
    assert_eq!((base.abstain, base.abstain_reason), (shifted.abstain, shifted.abstain_reason));
    // Dead border: same placement on a larger canvas, glyph tucked in a
    // corner so right/bottom rows are provably outside both lattices.
    let wide = contribution_map_local(
        &lf, &rf, (0, 0), (0, 0), (0, 0), 9, 7, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    let wide_rec = score_step_local(
        &lf, &rf, (0, 0), (0, 0), (0, 0), 9, 7, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert_eq!(base.gl.to_bits(), wide_rec.gl.to_bits());
    assert_eq!(base.both_supported_pairpx, wide_rec.both_supported_pairpx);
    assert_eq!(base.skipped_nonpositive, wide_rec.skipped_nonpositive);
    assert_eq!(wide.len(), 9 * 7);
    for y in 0..ch {
        for x in 0..cw {
            assert_eq!(
                wide[y * 9 + x].to_bits(),
                base_map[y * cw + x].to_bits(),
                "map cell ({x},{y}) moved under dead border"
            );
        }
    }
    for y in 0..7 {
        for x in 0..9 {
            if x >= cw || y >= ch {
                assert_eq!(wide[y * 9 + x].to_bits(), 0.0f64.to_bits());
            }
        }
    }
}

#[test]
fn local_kernel_disjoint_empty_and_clipped_canvases() {
    // Disjoint lattice rectangles, empty canvases, and canvases clipped
    // below the placement all keep the old abstain semantics: valid
    // zero stays +0, reasons stay evidence-driven, maps stay dense with
    // the caller geometry, and nothing panics on i64 bound arithmetic.
    let (lf, rf) = tiny_local_pair();
    let el = local_energy_maps(&lf, 12, Strength::Notebook);
    let er = local_energy_maps(&rf, 12, Strength::Notebook);
    let facing = facing_matrix(2);
    // Disjoint rectangles: no shared support.
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(40, 30)]);
    let rec = score_step_local(
        &lf, &rf, (0, 0), (40, 30), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert!(rec.abstain);
    assert_eq!(rec.abstain_reason, Some(LocalAbstain::NoSharedSupport));
    assert_eq!(rec.gl.to_bits(), 0.0f64.to_bits());
    assert_eq!(rec.both_supported_pairpx, 0);
    assert_eq!(rec.skipped_nonpositive, 0);
    assert_eq!(rec.honest_bound.to_bits(), 0.0f64.to_bits());
    let map = contribution_map_local(
        &lf, &rf, (0, 0), (40, 30), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert_eq!(map.len(), cw * ch);
    assert!(map.iter().all(|&v| v.to_bits() == 0.0f64.to_bits()));
    // Empty canvases (either axis zero): same abstain, no panic.
    for (ew, eh) in [(0usize, 0usize), (0, 5), (7, 0)] {
        let rec = score_step_local(
            &lf, &rf, (0, 0), (0, 0), (0, 0), ew, eh, &el, &er, &facing, 0.5,
            Strength::Notebook, None,
        )
        .unwrap();
        assert!(rec.abstain, "empty canvas {ew}x{eh} must abstain");
        assert_eq!(rec.abstain_reason, Some(LocalAbstain::NoSharedSupport));
        assert_eq!(rec.gl.to_bits(), 0.0f64.to_bits());
        let map = contribution_map_local(
            &lf, &rf, (0, 0), (0, 0), (0, 0), ew, eh, &el, &er, &facing, 0.5,
            Strength::Notebook, None,
        )
        .unwrap();
        assert_eq!(map.len(), ew * eh);
    }
    // Fully clipped canvas: placement entirely right/below of it.
    let rec = score_step_local(
        &lf, &rf, (50, 50), (50, 50), (0, 0), 4, 4, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert!(rec.abstain);
    assert_eq!(rec.abstain_reason, Some(LocalAbstain::NoSharedSupport));
    // Partially clipped canvas: only in-canvas pixels score, and the map
    // still reduces to gl on that canvas with the caller origin.
    let rec = score_step_local(
        &lf, &rf, (0, 0), (0, 0), (0, 0), 2, 1, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    let map = contribution_map_local(
        &lf, &rf, (0, 0), (0, 0), (0, 0), 2, 1, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert_eq!(map.len(), 2);
    let sum: f64 = map.iter().sum();
    // Map reduction uses the established 1e-12 gate (summing per-pixel
    // pair-sums reorders the single-scalar gl accumulation by
    // construction, in old and new code alike).
    assert!(
        (sum - rec.gl).abs() < 1e-12,
        "map sum {sum} vs gl {}",
        rec.gl
    );
}

#[test]
fn local_kernel_forced_guard_failure_skips_everything() {
    // Zeroed local energies force the EL/ER guard on every overlap
    // pixel: support exists (any_both) but nothing is eligible, so the
    // step abstains with zero local evidence, skipped == overlap count,
    // and gl is +0 rather than a signed or nonzero residue.
    let (lf, rf) = tiny_local_pair();
    let el = vec![vec![0.0; 6]; 2];
    let er = vec![vec![0.0; 6]; 2];
    let facing = facing_matrix(2);
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 3, 2, &[(0, 0)]);
    let rec = score_step_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert!(rec.abstain);
    assert_eq!(rec.abstain_reason, Some(LocalAbstain::ZeroLocalEvidence));
    assert_eq!(rec.gl.to_bits(), 0.0f64.to_bits());
    assert_eq!(rec.both_supported_pairpx, 0);
    // All-supported 2x3 over the two evaluated off-diagonal facing pairs.
    assert_eq!(rec.skipped_nonpositive, 12);
    let map = contribution_map_local(
        &lf, &rf, (0, 0), (0, 0), origin, cw, ch, &el, &er, &facing, 0.5,
        Strength::Notebook, None,
    )
    .unwrap();
    assert!(map.iter().all(|&v| v.to_bits() == 0.0f64.to_bits()));
}

#[test]
fn local_kernel_unequal_lattices_and_hole_masks() {
    // Unequal lattice sizes, negative origins, and support holes:
    // traversal stays in-bounds on both lattices, map reduces to gl,
    // and a rigid origin shift is bit-identical.
    let mk = |w: usize, h: usize, holes: &[usize]| {
        let n = w * h;
        let mut supported = vec![vec![true; n], vec![true; n]];
        for &i in holes {
            supported[0][i] = false;
            supported[1][n - 1 - i] = false;
        }
        GlyphFields {
            w,
            h,
            pad: 0,
            c_per_scale: Vec::new(),
            t_combined: Vec::new(),
            u1: vec![vec![0.0; n], vec![0.0; n]],
            u2: vec![vec![2.0; n], vec![2.0; n]],
            distance: vec![vec![1.0; n], vec![2.0; n]],
            conf_nb: vec![vec![1.5; n], vec![0.5; n]],
            arc: vec![vec![0.7; n], vec![1.3; n]],
            supported,
        }
    };
    let lf = mk(3, 2, &[1, 4]);
    let rf = mk(4, 3, &[0, 11]);
    let el = local_energy_maps(&lf, 12, Strength::Notebook);
    let er = local_energy_maps(&rf, 12, Strength::Notebook);
    let el_ms = local_energy_maps(&lf, 12, Strength::Manuscript);
    let er_ms = local_energy_maps(&rf, 12, Strength::Manuscript);
    let facing = facing_matrix(2);
    // Overlapping placement: left 3x2 at (0,0), right 4x3 at (1,1).
    let (origin, (ch, cw)) = union_canvas(3, 2, (0, 0), 4, 3, &[(1, 1)]);
    let run = |dx: i64, dy: i64| {
        let lo = (dx, dy);
        let ro = (1 + dx, 1 + dy);
        let og = (origin.0 + dx, origin.1 + dy);
        let rec = score_step_local(
            &lf, &rf, lo, ro, og, cw, ch, &el, &er, &facing, 0.5,
            Strength::Notebook, None,
        )
        .unwrap();
        let map = contribution_map_local(
            &lf, &rf, lo, ro, og, cw, ch, &el, &er, &facing, 0.5,
            Strength::Notebook, None,
        )
        .unwrap();
        (rec, map)
    };
    let (rec, map) = run(0, 0);
    let sum: f64 = map.iter().sum();
    assert!(
        (sum - rec.gl).abs() < 1e-12,
        "map sum {sum} vs gl {}",
        rec.gl
    );
    assert!(!rec.abstain);
    assert!(rec.both_supported_pairpx > 0);
    // Rigid shift into negative origins: bit-identical scores and maps.
    let (rec2, map2) = run(-11, -9);
    assert_eq!(rec.gl.to_bits(), rec2.gl.to_bits());
    assert_eq!(rec.both_supported_pairpx, rec2.both_supported_pairpx);
    assert_eq!(map, map2);
    // Manuscript strength path exercises the other strength lattice
    // with its own matching energy maps.
    let rec_ms = score_step_local(
        &lf, &rf, (0, 0), (1, 1), origin, cw, ch, &el_ms, &er_ms, &facing, 0.5,
        Strength::Manuscript, None,
    )
    .unwrap();
    assert!(!rec_ms.abstain);
    assert!(rec_ms.both_supported_pairpx > 0);
}

#[test]
fn search_domain_uses_the_scorers_fractional_field_origins() {
    // Field origins follow score_pair: truncate after subtracting the pad.
    let mut eng = Engine::new(EngineParams::frozen()).unwrap();
    let mut cover = vec![0.0; 8 * 8];
    cover[3 * 8 + 3] = 1.0;
    eng.load_glyph("d", "sha", 0x41, 8, 8, 0.5, 0.5, &cover)
        .unwrap();
    eng.load_glyph("d", "sha", 0x42, 8, 8, -1.5, -1.5, &cover)
        .unwrap();
    let domain = eng.search_domain("d", 0x41, 0x42).unwrap().unwrap();
    let left_origin = (0.5_f64 - 24.0).trunc() as i64;
    let right_origin = (-1.5_f64 - 24.0).trunc() as i64;
    assert_eq!(domain.hi, left_origin + 56 - 1 - right_origin);
}
