#![cfg(feature = "candidate")]
use font_generator::diagonal_fitting::topology::signature;

#[test]
fn input_edge_budget_boundary() {
    let zigzag =
        |n: usize| -> Vec<[f64; 2]> { (0..n).map(|i| [i as f64, (i % 2) as f64 * 10.0]).collect() };
    assert!(signature(&[zigzag(512)]).is_some());
    assert!(signature(&[zigzag(513)]).is_none());
}
