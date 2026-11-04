//! Integer-origin selection for the existing bitmap layout contract.
//! TypeFacet only supplies constraints; this module owns the origin grid,
//! delivered-cell feasibility and repertoire policies. Tracking is applied later.
use super::typefacet::{Prepared, WorkBudget};
use crate::{fail, Error, Glyph};
use std::collections::{BTreeMap, HashMap, HashSet};

#[derive(Clone, Copy)]
pub(super) enum Feasibility {
    BinaryCells,
    ProfileBounds,
}

pub(super) struct Policy {
    pub feasibility: Feasibility,
    pub preserve_tabular_digits: bool,
}

pub(super) type Rows = BTreeMap<i32, (i32, i32)>;

fn eligible(codepoint: u32) -> bool {
    char::from_u32(codepoint).is_some_and(|ch| !ch.is_whitespace())
}

pub(super) fn participating_codepoints(
    ids: impl IntoIterator<Item = u32>,
    preserve_tabular: bool,
) -> HashSet<u32> {
    let ids: HashSet<_> = ids.into_iter().filter(|cp| eligible(*cp)).collect();
    if preserve_tabular && ids.iter().all(|cp| source_tabular_digit(*cp)) {
        HashSet::new()
    } else {
        ids
    }
}

pub(super) fn cell_rows(glyph: &Glyph) -> Result<Rows, Error> {
    let length = (glyph.width as usize)
        .checked_mul(glyph.height as usize)
        .ok_or_else(|| fail("kerning cell dimensions overflow"))?;
    if length > 1_048_576
        || glyph.width > 4096
        || glyph.height > 4096
        || glyph.pixels.len() != length
        || glyph.pixels.iter().any(|v| *v > 1)
        || glyph.left.unsigned_abs() > 32768
        || glyph.top.unsigned_abs() > 32768
    {
        return Err(fail(
            "binary-cell feasibility requires bounded unpacked binary pixels",
        ));
    }
    let mut rows = Rows::new();
    for row in 0..glyph.height as usize {
        let values = &glyph.pixels[row * glyph.width as usize..(row + 1) * glyph.width as usize];
        if let (Some(left), Some(right)) = (
            values.iter().position(|v| *v != 0),
            values.iter().rposition(|v| *v != 0),
        ) {
            rows.insert(
                glyph.top + row as i32,
                (glyph.left + left as i32, glyph.left + right as i32 + 1),
            );
        }
    }
    Ok(rows)
}

pub(super) fn minimum(a: &Rows, b: &Rows) -> Option<i32> {
    a.iter()
        .filter_map(|(row, (_, right))| b.get(row).map(|(left, _)| right - left))
        .max()
}

fn source_tabular_digit(codepoint: u32) -> bool {
    // FontSpacingProperties.tabular_digits is measured on U+0030..U+0039.
    // Do not infer equal advances for unrelated Unicode numeral sets.
    (0x30..=0x39).contains(&codepoint)
}

pub(super) fn resolve(
    prepared: &Prepared,
    glyphs: &[Glyph],
    advances: &HashMap<u32, i32>,
    units_per_pixel: f64,
    policy: Policy,
) -> Result<HashMap<(u32, u32), i32>, Error> {
    if !units_per_pixel.is_finite() || units_per_pixel <= 0.0 {
        return Err(fail(
            "kerning placement requires a positive finite coordinate scale",
        ));
    }
    let ids: Vec<_> = prepared.codepoints().collect();
    let cells =
        if matches!(policy.feasibility, Feasibility::BinaryCells) {
            let glyphs: HashMap<_, _> = glyphs.iter().map(|g| (g.codepoint, g)).collect();
            ids.iter()
                .map(|cp| {
                    Ok((
                        *cp,
                        cell_rows(glyphs.get(cp).ok_or_else(|| {
                            fail("missing delivered-cell geometry for placement")
                        })?)?,
                    ))
                })
                .collect::<Result<HashMap<_, _>, Error>>()?
        } else {
            HashMap::new()
        };
    let integer = |value: f64| -> Result<i32, Error> {
        if !value.is_finite()
            || value < f64::from(i32::MIN / 64)
            || value > f64::from(i32::MAX / 64)
        {
            return Err(fail("kerning origin exceeds integer layout range"));
        }
        Ok(value as i32)
    };
    let mut result = HashMap::new();
    let mut budget = WorkBudget::default();
    for &left in &ids {
        for &right in &ids {
            if !eligible(left)
                || !eligible(right)
                || (policy.preserve_tabular_digits
                    && source_tabular_digit(left)
                    && source_tabular_digit(right))
            {
                continue;
            }
            let constraint = prepared
                .pair(left, right)
                .ok_or_else(|| fail("missing kerning pair constraints"))?;
            let first = if cells.is_empty() {
                integer((constraint.minimum_units / units_per_pixel).floor())?
            } else {
                minimum(&cells[&left], &cells[&right]).unwrap_or(integer(
                    (constraint.minimum_units / units_per_pixel).floor(),
                )?)
            };
            let last = integer(
                (constraint
                    .minimum_units
                    .max(constraint.maximum_units)
                    .max(constraint.extrema_bound_units)
                    .max(f64::from(first) * units_per_pixel)
                    / units_per_pixel)
                    .ceil(),
            )?;
            if i64::from(last) - i64::from(first) > 128 {
                return Err(fail("kerning integer search work limit exceeded"));
            }
            let mut chosen = None;
            for step in first..=last {
                if constraint.admissible(f64::from(step) * units_per_pixel, &mut budget)? {
                    chosen = Some(step);
                    break;
                }
            }
            let step = chosen.ok_or_else(|| fail("kerning has no admissible integer placement"))?;
            let advance = *advances
                .get(&left)
                .ok_or_else(|| fail("missing finalized kerning advance"))?;
            if advance % 64 != 0 {
                return Err(fail(
                    "integer placement requires whole-pixel finalized advances",
                ));
            }
            let adjustment = step
                .checked_mul(64)
                .and_then(|s| s.checked_sub(advance))
                .ok_or_else(|| fail("kerning adjustment overflow"))?;
            result.insert((left, right), adjustment);
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::kerning::{
        geometry,
        typefacet::{self, TypefacetSettings},
    };

    #[test]
    fn composed_binary_adapter_retains_every_original_integer_setting() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/typefacet/literata.json")).unwrap();
        let glyphs: Vec<Glyph> = serde_json::from_value(fixture["glyphs"].clone()).unwrap();
        let advances = glyphs
            .iter()
            .map(|g| (g.codepoint, g.advance_26_6))
            .collect();
        let unit = fixture["units_per_em"].as_f64().unwrap() / fixture["size_px"].as_f64().unwrap();
        let geometry = geometry::delivered_cells(&glyphs, unit).unwrap();
        let ascender = fixture["ascender_26_6"].as_f64().unwrap() / 64.0 * unit;
        for setting in fixture["settings"].as_array().unwrap() {
            let settings = TypefacetSettings {
                normal_distance_em: setting["normal_distance_em"].as_f64().unwrap(),
                intrusion_tolerance_em: setting["intrusion_tolerance_em"].as_f64().unwrap(),
                ..TypefacetSettings::default()
            };
            let prepared = typefacet::prepare(
                &geometry,
                fixture["units_per_em"].as_u64().unwrap() as u16,
                ascender,
                &settings,
            )
            .unwrap();
            let pairs = resolve(
                &prepared,
                &glyphs,
                &advances,
                unit,
                Policy {
                    feasibility: Feasibility::BinaryCells,
                    preserve_tabular_digits: false,
                },
            )
            .unwrap();
            for a in b'a'..=b'z' {
                for b in b'a'..=b'z' {
                    let index = usize::from(a - b'a') * 26 + usize::from(b - b'a');
                    let expected = setting["steps"][index].as_i64().unwrap() as i32;
                    let actual =
                        (pairs[&(u32::from(a), u32::from(b))] + advances[&u32::from(a)]) / 64;
                    assert_eq!(
                        actual,
                        expected,
                        "{}{} {settings:?}",
                        char::from(a),
                        char::from(b)
                    );
                }
            }
        }
    }

    #[test]
    fn geometry_and_cell_feasibility_are_independent() {
        let glyph = |cp| Glyph {
            codepoint: cp,
            glyph_id: cp,
            advance_26_6: 128,
            left: 0,
            top: -2,
            width: 1,
            height: 2,
            pixels: vec![1; 2],
        };
        let glyphs = vec![
            glyph(97),
            glyph(0x03a9),
            glyph(49),
            glyph(50),
            glyph(0x1d7ce),
        ];
        let geometry = geometry::delivered_cells(&glyphs, 62.5).unwrap();
        let prepared =
            typefacet::prepare(&geometry, 1000, 750., &TypefacetSettings::default()).unwrap();
        let advances = glyphs
            .iter()
            .map(|g| (g.codepoint, g.advance_26_6))
            .collect();
        let mut coverage = glyphs.clone();
        for g in &mut coverage {
            g.pixels = vec![7; 2];
        }
        let policy = Policy {
            feasibility: Feasibility::ProfileBounds,
            preserve_tabular_digits: true,
        };
        let pairs = resolve(&prepared, &coverage, &advances, 62.5, policy).unwrap();
        assert!(pairs.contains_key(&(97, 0x03a9)));
        assert!(!pairs.contains_key(&(49, 50)));
        assert!(
            pairs.contains_key(&(0x1d7ce, 0x1d7ce)),
            "ASCII tabular metrics do not classify other numeral sets"
        );
        assert!(resolve(
            &prepared,
            &coverage,
            &advances,
            62.5,
            Policy {
                feasibility: Feasibility::BinaryCells,
                preserve_tabular_digits: false
            }
        )
        .is_err());
    }

    #[test]
    fn fallback_only_repertoires_do_not_require_analysis_geometry() {
        assert!(participating_codepoints([32, 0x00a0, 49, 50], true).is_empty());
        assert_eq!(
            participating_codepoints([32, 49, 50], false),
            HashSet::from([49, 50])
        );
        assert_eq!(
            participating_codepoints([32, 49, 0x03a9], true),
            HashSet::from([49, 0x03a9])
        );
    }
}
