//! Cache-budget integration gates on the public API at production values.
//!
//! No corpus files needed; tiny synthetic covers exercise the real
//! `load_glyph` / `local_energy_for` / clear paths. Policy internals
//! (narrowed budgets) are covered by the inline unit tests in `engine.rs`;
//! this file pins the shipped 256 MiB + floor-32 + ceiling-512 behavior and
//! the observational counter surface.

use yinyang_oriented_engine::params::EngineParams;
use yinyang_oriented_engine::score::Strength;
use yinyang_oriented_engine::Engine;

fn tiny_params() -> EngineParams {
    EngineParams {
        q: 2.0,
        kappa: 4.0,
        sigmas: vec![0.5],
        weights: vec![1.0],
        radius: 1,
        eps: 1e-12,
        n_v1: 1,
        n_directed: 1,
    }
}

fn cover(seed: u64, n: usize) -> Vec<f64> {
    (0..n).map(|i| (((seed * 31 + i as u64) % 7) + 1) as f64 / 7.0).collect()
}

#[test]
fn production_policy_holds_small_working_set() {
    // Shipped 256 MiB target with KB-scale entries: no eviction, exact
    // accounting, cumulative counters.
    let mut e = Engine::new(tiny_params()).unwrap();
    for cp in 0..6u32 {
        let c = cover(cp as u64 + 1, 16);
        assert!(e.load_glyph("t", "s", cp, 4, 4, 0.0, 0.0, &c).unwrap());
    }
    let s = e.cache_stats();
    assert_eq!((s.glyphs, s.lru), (6, 6));
    assert_eq!((s.evictions, s.builds_el), (0, 0));
    assert_eq!(s.builds_fields, 6);
    assert!(s.payload_bytes > 0);
    // Repeat loads are hits: no new builds.
    for cp in 0..6u32 {
        let c = cover(cp as u64 + 1, 16);
        assert!(!e.load_glyph("t", "s", cp, 4, 4, 0.0, 0.0, &c).unwrap());
    }
    assert_eq!(e.cache_stats().builds_fields, 6);
    // EL materializes once per entry and the counter tracks misses only.
    for cp in 0..6u32 {
        e.local_energy_for("t", cp, Strength::Notebook, 1).unwrap();
    }
    assert_eq!(e.cache_stats().builds_el, 6);
    for cp in 0..6u32 {
        e.local_energy_for("t", cp, Strength::Notebook, 1).unwrap();
    }
    assert_eq!(e.cache_stats().builds_el, 6);
}

#[test]
fn production_policy_holds_33_small_entries() {
    // 33 KB-scale entries fit the 256 MiB target and the 512 ceiling, so
    // the keep-floor never engages: everything stays resident. (Floor and
    // ceiling transitions at binding limits are covered by the inline unit
    // tests with narrowed budgets.)
    let mut e = Engine::new(tiny_params()).unwrap();
    for cp in 0..33u32 {
        let c = cover(cp as u64 + 1, 16);
        e.load_glyph("t", "s", cp, 4, 4, 0.0, 0.0, &c).unwrap();
    }
    let s = e.cache_stats();
    assert_eq!((s.glyphs, s.lru), (33, 33));
    assert_eq!(s.evictions, 0);
    assert_eq!(s.builds_fields, 33);
    assert!(s.payload_bytes > 0);
}

#[test]
fn capture_or_geometry_change_rebuilds() {
    // Same key with different capture or geometry bytes rebuilds exactly
    // once; identical reloads stay hits.
    let mut e = Engine::new(tiny_params()).unwrap();
    let c = cover(1, 16);
    assert!(e.load_glyph("t", "s", 9, 4, 4, 0.0, 0.0, &c).unwrap());
    assert!(!e.load_glyph("t", "s", 9, 4, 4, 0.0, 0.0, &c).unwrap());
    assert!(e.load_glyph("t2", "s", 9, 4, 4, 0.0, 0.0, &c).unwrap());
    let c2 = cover(2, 16);
    assert!(e.load_glyph("t2", "s", 9, 4, 4, 0.0, 0.0, &c2).unwrap());
    assert_eq!(e.cache_stats().builds_fields, 3);
    assert_eq!(e.cache_stats().glyphs, 2);
}
