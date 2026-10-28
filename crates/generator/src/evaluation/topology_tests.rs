use super::*;

fn fixture_rows() -> Vec<(usize, u16, usize, usize)> {
    let raw = include_str!("../../tests/fixtures/topology-small-patterns.json");
    let parsed: serde_json::Value = serde_json::from_str(raw).unwrap();
    assert_eq!(parsed["count"].as_u64().unwrap() as usize, 530);
    parsed["rows"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            let cells: Vec<usize> = row
                .as_array()
                .unwrap()
                .iter()
                .map(|cell| cell.as_u64().unwrap() as usize)
                .collect();
            assert_eq!(cells.len(), 4);
            (cells[0], cells[1] as u16, cells[2], cells[3])
        })
        .collect()
}

#[test]
fn all_small_patterns_match_cli_baseline() {
    let rows = fixture_rows();
    assert_eq!(rows.len(), 530);
    for (side, mask, ink8, holes4) in rows {
        let area = side * side;
        assert!(area <= 9);
        let bitmap: Vec<bool> = (0..area).map(|i| mask >> i & 1 == 1).collect();
        let got = topology(&bitmap, side, side);
        assert_eq!(
            (got.ink_components_8, got.enclosed_background_components_4),
            (ink8, holes4),
            "side {side} mask {mask:#b}"
        );
    }
}

#[test]
fn empty_dimensions_yield_no_components() {
    let empty: Vec<bool> = Vec::new();
    assert_eq!(
        topology(&empty, 0, 0),
        Topology {
            ink_components_8: 0,
            enclosed_background_components_4: 0,
        }
    );
}

#[test]
fn sole_edge_opening_excluded() {
    let left_open: Vec<bool> = vec![
        true, true, true, true, true, false, false, true, true, true, true, true, true, true, true,
        true, true, true, true, true, true, true, true, true, true,
    ];
    assert_eq!(
        topology(&left_open, 5, 5),
        Topology {
            ink_components_8: 1,
            enclosed_background_components_4: 0,
        }
    );
}

#[test]
fn diagonal_ink_bridges_diagonal_white_splits() {
    let diagonal: Vec<bool> = vec![true, false, false, false, true, false, false, false, true];
    assert_eq!(
        topology(&diagonal, 3, 3),
        Topology {
            ink_components_8: 1,
            enclosed_background_components_4: 0,
        }
    );
    let corners: Vec<bool> = vec![
        true, true, true, true, true, false, true, true, true, true, false, true, true, true, true,
        true,
    ];
    assert_eq!(
        topology(&corners, 4, 4),
        Topology {
            ink_components_8: 1,
            enclosed_background_components_4: 2,
        }
    );
}
