use super::*;
use std::collections::BTreeSet;

#[derive(serde::Deserialize)]
struct Golden {
    count: usize,
    rows: Vec<[usize; 4]>,
}

#[test]
fn constructor_rejects_mismatch_and_overflow() {
    let ink = vec![true; 6];
    assert!(Bitmap::new(2, 2, &ink).is_none());
    assert!(Bitmap::new(usize::MAX, 2, &[]).is_none());
    assert!(Bitmap::new(2, usize::MAX, &[]).is_none());
}

#[test]
fn constructor_accepts_empty_including_zero_by_max() {
    let empty: Vec<bool> = Vec::new();
    let zero = Bitmap::new(0, 0, &empty).expect("empty dims with empty slice");
    assert_eq!(zero.counts(), [0, 0]);
    let tall = Bitmap::new(0, usize::MAX, &empty).expect("zero width with empty slice");
    assert_eq!(tall.counts(), [0, 0]);
    let wide = Bitmap::new(usize::MAX, 0, &empty).expect("max width with empty slice");
    assert_eq!(wide.counts(), [0, 0]);
    assert!(Bitmap::new(0, 0, &[true]).is_none());
}

#[test]
fn neighbor_center_order_and_corner_bounds() {
    let ink: Vec<usize> = neighbors(4, 3, 3, true).collect();
    assert_eq!(ink, vec![0, 1, 2, 3, 5, 6, 7, 8]);
    let white: Vec<usize> = neighbors(4, 3, 3, false).collect();
    assert_eq!(white, vec![1, 3, 5, 7]);
    let ink_corner: Vec<usize> = neighbors(0, 3, 3, true).collect();
    assert_eq!(ink_corner, vec![1, 3, 4]);
    let white_corner: Vec<usize> = neighbors(0, 3, 3, false).collect();
    assert_eq!(white_corner, vec![1, 3]);
}

#[test]
fn flood_fill_connected_unique_reusable_queue() {
    let ink = vec![true; 9];
    let bitmap = Bitmap::new(3, 3, &ink).expect("valid dims");
    let mut visited = vec![false; 9];
    let mut queue = vec![77, 88];
    assert_eq!(
        flood_fill(&bitmap, 4, &mut visited, &mut queue),
        (true, true)
    );
    assert_eq!(visited, vec![true; 9]);
    let mut ordered = queue.clone();
    ordered.sort();
    assert_eq!(ordered, vec![0, 1, 2, 3, 4, 5, 6, 7, 8]);
}

#[test]
fn flood_fill_disconnected_and_enclosed_white() {
    let ink = vec![true, false, true];
    let bitmap = Bitmap::new(3, 1, &ink).expect("valid dims");
    let mut visited = vec![false; 3];
    let mut queue = Vec::new();
    assert_eq!(
        flood_fill(&bitmap, 0, &mut visited, &mut queue),
        (true, true)
    );
    assert_eq!(visited, vec![true, false, false]);
    assert_eq!(queue, vec![0]);
    assert_eq!(
        flood_fill(&bitmap, 2, &mut visited, &mut queue),
        (true, true)
    );
    assert_eq!(visited, vec![true, false, true]);
    assert_eq!(queue, vec![2]);
    let ring = vec![true, true, true, true, false, true, true, true, true];
    let bitmap = Bitmap::new(3, 3, &ring).expect("valid dims");
    let mut visited = vec![false; 9];
    assert_eq!(
        flood_fill(&bitmap, 4, &mut visited, &mut queue),
        (false, false)
    );
    assert_eq!(
        visited,
        vec![false, false, false, false, true, false, false, false, false]
    );
}

#[test]
fn golden_small_patterns_match_cli_baseline() {
    let raw = include_str!("../../tests/fixtures/topology-small-patterns.json");
    let golden: Golden = serde_json::from_str(raw).unwrap();
    assert_eq!(golden.count, 530);
    assert_eq!(golden.rows.len(), 530);
    for side in 1..=3usize {
        let masks: BTreeSet<usize> = golden
            .rows
            .iter()
            .filter(|row| row[0] == side)
            .map(|row| row[1])
            .collect();
        let full: BTreeSet<usize> = (0..(1 << (side * side))).collect();
        assert_eq!(masks, full, "side {side}");
    }
    for [side, mask, ink8, holes4] in golden.rows {
        assert!(side * side <= 9);
        let ink: Vec<bool> = (0..side * side).map(|i| mask >> i & 1 == 1).collect();
        let bitmap = Bitmap::new(side, side, &ink).expect("valid fixture dims");
        assert_eq!(
            bitmap.counts(),
            [ink8, holes4],
            "side {side} mask {mask:#b}"
        );
    }
}
