use super::*;

#[test]
fn missing_bitmap_fields() {
    assert_eq!(topology(&json!({})).unwrap_err(), "missing width");
    assert_eq!(
        topology(&json!({"width": 1})).unwrap_err(),
        "missing height"
    );
    assert_eq!(
        topology(&json!({"width": 1, "height": 1})).unwrap_err(),
        "missing pixels"
    );
}

#[test]
fn allocation_error_precedes_pixel_error() {
    assert_eq!(
        topology(&json!({"width": 2, "height": 2, "pixels": [0]})).unwrap_err(),
        "invalid bitmap allocation"
    );
    assert_eq!(
        topology(&json!({"width": 2, "height": 2, "pixels": ["x"]})).unwrap_err(),
        "invalid bitmap allocation"
    );
}

#[test]
fn overflow_and_cap_reject() {
    assert_eq!(
        topology(&json!({"width": 18446744073709551615u64, "height": 2, "pixels": []}))
            .unwrap_err(),
        "invalid bitmap allocation"
    );
    let pixels = vec![json!(0); 4194305];
    assert_eq!(
        topology(&json!({"width": 5, "height": 838861, "pixels": pixels})).unwrap_err(),
        "invalid bitmap allocation"
    );
}

#[test]
fn zero_dimensions_accepted() {
    assert_eq!(
        topology(&json!({"width": 0, "height": 0, "pixels": []})).unwrap(),
        [0, 0]
    );
    assert_eq!(
        topology(&json!({"width": 0, "height": 5, "pixels": []})).unwrap(),
        [0, 0]
    );
}

#[test]
fn nonzero_u64_is_ink() {
    assert_eq!(
        topology(&json!({"width": 1, "height": 1, "pixels": [7]})).unwrap(),
        [1, 0]
    );
    assert_eq!(
        topology(&json!({"width": 1, "height": 1, "pixels": [0]})).unwrap(),
        [0, 0]
    );
    assert_eq!(
        topology(&json!({"width": 1, "height": 1, "pixels": [1.5]})).unwrap_err(),
        "invalid pixel"
    );
}

#[test]
fn diagonal_ink_joins_eight_connected() {
    assert_eq!(
        topology(&json!({"width": 3, "height": 3, "pixels": [1, 0, 0, 0, 1, 0, 0, 0, 1]})).unwrap(),
        [1, 0]
    );
}

#[test]
fn diagonal_white_splits_four_connected() {
    assert_eq!(
        topology(&json!({"width": 4, "height": 4, "pixels": [
            1, 1, 1, 1,
            1, 0, 1, 1,
            1, 1, 0, 1,
            1, 1, 1, 1,
        ]}))
        .unwrap(),
        [1, 2]
    );
}

#[test]
fn enclosed_white_counts_border_white_excluded() {
    assert_eq!(
        topology(&json!({"width": 3, "height": 1, "pixels": [0, 1, 0]})).unwrap(),
        [1, 0]
    );
    assert_eq!(
        topology(&json!({"width": 1, "height": 3, "pixels": [0, 1, 0]})).unwrap(),
        [1, 0]
    );
    assert_eq!(
        topology(&json!({"width": 1, "height": 3, "pixels": [1, 0, 1]})).unwrap(),
        [2, 0]
    );
}

#[test]
fn reflection_preserves_counts() {
    let plain = json!({"width": 4, "height": 4, "pixels": [
        1, 1, 1, 1,
        1, 0, 1, 1,
        1, 1, 0, 1,
        1, 1, 1, 1,
    ]});
    let mirrored = json!({"width": 4, "height": 4, "pixels": [
        1, 1, 1, 1,
        1, 1, 0, 1,
        1, 0, 1, 1,
        1, 1, 1, 1,
    ]});
    assert_eq!(topology(&plain).unwrap(), [1, 2]);
    assert_eq!(topology(&mirrored).unwrap(), topology(&plain).unwrap());
}

#[test]
fn validate_bitmap_fields_and_cap_direct() {
    let bitmap = validate_bitmap(&json!({"width": 2, "height": 1, "pixels": [0, 9]})).unwrap();
    assert_eq!((bitmap.width, bitmap.height), (2, 1));
    assert_eq!(bitmap.ink, vec![false, true]);
    let pixels = vec![json!(0); 4194304];
    let bitmap =
        validate_bitmap(&json!({"width": 2048, "height": 2048, "pixels": pixels})).unwrap();
    assert_eq!((bitmap.width, bitmap.height), (2048, 2048));
    assert_eq!(bitmap.ink.len(), 4194304);
}

fn corridor_opening(whites: &[usize]) -> Value {
    let mut pixels = vec![json!(1); 25];
    for w in whites {
        pixels[*w] = json!(0);
    }
    json!({"width": 5, "height": 5, "pixels": pixels})
}

#[test]
fn sole_left_opening_excluded() {
    assert_eq!(topology(&corridor_opening(&[12, 11, 10])).unwrap(), [1, 0]);
}

#[test]
fn sole_right_opening_excluded() {
    assert_eq!(topology(&corridor_opening(&[12, 13, 14])).unwrap(), [1, 0]);
}

#[test]
fn sole_top_opening_excluded() {
    assert_eq!(topology(&corridor_opening(&[12, 7, 2])).unwrap(), [1, 0]);
}

#[test]
fn sole_bottom_opening_excluded() {
    assert_eq!(topology(&corridor_opening(&[12, 17, 22])).unwrap(), [1, 0]);
}

#[test]
fn flood_fill_connected_unique_reusable_queue() {
    let bitmap =
        validate_bitmap(&json!({"width": 3, "height": 3, "pixels": [1, 1, 1, 1, 1, 1, 1, 1, 1]}))
            .unwrap();
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
    let bitmap = validate_bitmap(&json!({"width": 3, "height": 1, "pixels": [1, 0, 1]})).unwrap();
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
    let ring =
        validate_bitmap(&json!({"width": 3, "height": 3, "pixels": [1, 1, 1, 1, 0, 1, 1, 1, 1]}))
            .unwrap();
    let mut visited = vec![false; 9];
    assert_eq!(
        flood_fill(&ring, 4, &mut visited, &mut queue),
        (false, false)
    );
    assert_eq!(
        visited,
        vec![false, false, false, false, true, false, false, false, false]
    );
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
fn transpose_preserves_counts() {
    let wide = json!({"width": 3, "height": 2, "pixels": [1, 0, 0, 0, 0, 1]});
    let tall = json!({"width": 2, "height": 3, "pixels": [1, 0, 0, 0, 0, 1]});
    assert_eq!(topology(&wide).unwrap(), [2, 0]);
    assert_eq!(topology(&tall).unwrap(), topology(&wide).unwrap());
}
