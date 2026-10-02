//! Rebuild the original rectangle fonts used by the CFF/CFF2 format tests.
//! Run with `cargo run --locked --example build_fixtures` from tools/generator.
//! No third-party outlines are used, and timestamps are fixed.

use std::{error::Error, fs, path::Path};
use write_fonts::{
    dump_table,
    ps::cff::v2::{Cff2Header, Index},
    tables::{
        cmap::Cmap,
        fvar::{Fvar, VariationAxisRecord},
        head::Head,
        hhea::Hhea,
        hmtx::{Hmtx, LongMetric},
        maxp::Maxp,
        name::{Name, NameRecord},
        os2::Os2,
        post::Post,
        variations::{
            ItemVariationData, ItemVariationStore, RegionAxisCoordinates, VariationRegion,
            VariationRegionList,
        },
    },
    types::{F2Dot14, FWord, Fixed, GlyphId, LongDateTime, NameId, Tag, UfWord, Version16Dot16},
    FontBuilder,
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn main() -> Result<()> {
    let directory = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures");
    for (filename, variable) in [("static-cff.otf", false), ("variable-cff2.otf", true)] {
        let path = directory.join(filename);
        fs::write(&path, build_font(variable)?)?;
        println!("Wrote {}", path.display());
    }
    Ok(())
}

fn build_font(variable: bool) -> Result<Vec<u8>> {
    let mut font = FontBuilder::new();
    font.add_table(&Head {
        font_revision: Fixed::from_i32(1),
        units_per_em: 1000,
        created: LongDateTime::new(2_082_844_800),
        modified: LongDateTime::new(2_082_844_800),
        x_min: 50,
        x_max: 350,
        y_max: 700,
        lowest_rec_ppem: 3,
        ..Default::default()
    })?;
    font.add_table(&Hhea {
        ascender: FWord::new(800),
        descender: FWord::new(-200),
        advance_width_max: UfWord::new(600),
        min_left_side_bearing: FWord::new(50),
        min_right_side_bearing: FWord::new(250),
        x_max_extent: FWord::new(350),
        caret_slope_rise: 1,
        number_of_h_metrics: 3,
        ..Default::default()
    })?;
    font.add_table(&Hmtx {
        h_metrics: [(600, 0), (300, 0), (600, 50)]
            .into_iter()
            .map(|(advance, side_bearing)| LongMetric {
                advance,
                side_bearing,
            })
            .collect(),
        left_side_bearings: vec![],
    })?;
    font.add_table(&Maxp {
        num_glyphs: 3,
        ..Default::default()
    })?;
    font.add_table(&Cmap::from_mappings([
        (' ', GlyphId::new(1)),
        ('A', GlyphId::new(2)),
    ])?)?;
    font.add_table(&Os2 {
        x_avg_char_width: 500,
        us_first_char_index: 32,
        us_last_char_index: 65,
        ul_unicode_range_1: 1,
        ach_vend_id: Tag::new(b"????"),
        s_typo_ascender: 800,
        s_typo_descender: -200,
        us_win_ascent: 800,
        us_win_descent: 200,
        ..Default::default()
    })?;
    let mut name = Name::default();
    for (id, text) in [
        (1, "Generator Format Fixture"),
        (2, "Regular"),
        (4, "Generator Format Fixture Regular"),
        (6, "GeneratorFormatFixture-Regular"),
        (256, "Weight"),
    ] {
        if id != 256 || variable {
            name.name_record.push(NameRecord::new(
                3,
                1,
                0x409,
                NameId::new(id),
                text.to_string().into(),
            ));
        }
    }
    font.add_table(&name)?;
    font.add_table(&Post {
        version: Version16Dot16::VERSION_3_0,
        ..Default::default()
    })?;
    if variable {
        let mut fvar = Fvar::default();
        fvar.axis_instance_arrays.axes.push(VariationAxisRecord {
            axis_tag: Tag::new(b"wght"),
            min_value: Fixed::from_i32(100),
            default_value: Fixed::from_i32(100),
            max_value: Fixed::from_i32(900),
            axis_name_id: NameId::new(256),
            ..Default::default()
        });
        font.add_table(&fvar)?;
        font.add_raw(Tag::new(b"CFF2"), cff2()?);
    } else {
        font.add_raw(Tag::new(b"CFF "), cff());
    }
    Ok(font.build())
}

// Only the handful of Type 2/DICT operators needed by these fixtures are
// encoded here. write-fonts supplies sfnt tables, checksums and variation data.
fn number(bytes: &mut Vec<u8>, value: i16) {
    // The shortint encoding is valid in both DICTs and CharStrings.
    bytes.push(28);
    bytes.extend(value.to_be_bytes());
}

fn command(bytes: &mut Vec<u8>, operands: &[i16], operator: u8) {
    for &value in operands {
        number(bytes, value);
    }
    bytes.push(operator);
}

fn dict_offset(bytes: &mut Vec<u8>, offset: usize, operator: &[u8]) {
    // Fixed-width int32 offsets keep DICT sizes independent of their values.
    bytes.push(29);
    bytes.extend(i32::try_from(offset).unwrap().to_be_bytes());
    bytes.extend(operator);
}

fn rectangle(variable: bool) -> Vec<u8> {
    let mut bytes = vec![];
    if !variable {
        number(&mut bytes, 600); // CFF1 stores the advance in the CharString.
    }
    command(&mut bytes, &[50, 0], 21); // rmoveto
    if variable {
        command(&mut bytes, &[300, 100, 1], 16); // blend: 300..400 over normalized wght 0..1
        command(&mut bytes, &[0], 5); // rlineto using the blended x delta
    } else {
        command(&mut bytes, &[300, 0], 5); // rlineto
    }
    command(&mut bytes, &[0, 700], 5);
    if variable {
        command(&mut bytes, &[-300, -100, 1], 16);
        command(&mut bytes, &[0], 5);
    } else {
        command(&mut bytes, &[-300, 0], 5);
        bytes.push(14); // endchar, omitted in CFF2; both implicitly close paths.
    }
    bytes
}

fn empty_glyph(advance: i16) -> Vec<u8> {
    let mut bytes = vec![];
    command(&mut bytes, &[advance], 14); // width, endchar
    bytes
}

// CFF1 INDEX uses a uint16 count (CFF2 uses uint32). These tiny indexes
// need only one byte per offset, including the final one-based end offset.
fn index1(items: &[&[u8]]) -> Vec<u8> {
    let mut bytes = u16::try_from(items.len()).unwrap().to_be_bytes().to_vec();
    if !items.is_empty() {
        bytes.push(1); // offSize
        let mut offset = 1;
        bytes.push(offset);
        for item in items {
            offset = offset
                .checked_add(u8::try_from(item.len()).unwrap())
                .unwrap();
            bytes.push(offset);
        }
        for item in items {
            bytes.extend(*item);
        }
    }
    bytes
}

fn cff() -> Vec<u8> {
    let name = index1(&[b"GeneratorFormatFixture"]);
    let empty_index = index1(&[]);
    let charset = [0, 0, 1, 0, 34]; // format 0: standard SIDs for space and A
    let charstrings = index1(&[&empty_glyph(600), &empty_glyph(300), &rectangle(false)]);
    let top_dict = |charset_offset, charstrings_offset, private_offset| {
        let mut dict = vec![];
        command(&mut dict, &[50, 0, 350, 700], 5); // FontBBox
        dict_offset(&mut dict, charset_offset, &[15]);
        dict_offset(&mut dict, charstrings_offset, &[17]);
        number(&mut dict, 0); // empty Private DICT size
        dict_offset(&mut dict, private_offset, &[18]);
        index1(&[&dict])
    };
    let charset_offset = 4 + name.len() + top_dict(0, 0, 0).len() + 2 * empty_index.len();
    let charstrings_offset = charset_offset + charset.len();
    let private_offset = charstrings_offset + charstrings.len();
    let mut bytes = vec![1, 0, 4, 1]; // major, minor, hdrSize, offSize
    bytes.extend(name);
    bytes.extend(top_dict(charset_offset, charstrings_offset, private_offset));
    bytes.extend(&empty_index); // String INDEX: all names use standard SIDs
    bytes.extend(&empty_index); // Global Subr INDEX
    bytes.extend(charset);
    bytes.extend(charstrings);
    bytes
}

fn cff2() -> Result<Vec<u8>> {
    let charstrings = dump_table(&Index::from_items(vec![vec![], vec![], rectangle(true)]))?;
    let store = dump_table(&ItemVariationStore::new(
        VariationRegionList::new(
            1,
            vec![VariationRegion::new(vec![RegionAxisCoordinates::new(
                F2Dot14::from_f32(0.0),
                F2Dot14::from_f32(1.0),
                F2Dot14::from_f32(1.0),
            )])],
        ),
        // CFF2 deltas live in blend operands, so there are no delta-set rows.
        vec![Some(ItemVariationData::new(0, 0, vec![0], vec![]))],
    ))?;
    let font_dict = |private_offset| {
        let mut dict = vec![];
        number(&mut dict, 0); // empty Private DICT size
        dict_offset(&mut dict, private_offset, &[18]);
        dump_table(&Index::from_items(vec![dict]))
    };
    let mut top_dict = vec![];
    // Each offset takes five bytes plus its operator (FDArray is escaped).
    let charstrings_offset = 5 + (6 + 7 + 6) + 4;
    let fdarray_offset = charstrings_offset + charstrings.len();
    let vstore_offset = fdarray_offset + font_dict(0)?.len();
    dict_offset(&mut top_dict, charstrings_offset, &[17]);
    dict_offset(&mut top_dict, fdarray_offset, &[12, 36]);
    dict_offset(&mut top_dict, vstore_offset, &[24]);
    let mut trailing = 0u32.to_be_bytes().to_vec(); // empty Global Subr INDEX
    trailing.extend(charstrings);
    trailing.extend(font_dict(vstore_offset)?);
    trailing.extend(u16::try_from(store.len())?.to_be_bytes()); // VariationStore length
    trailing.extend(store);
    Ok(dump_table(&Cff2Header::new(
        5,
        u16::try_from(top_dict.len())?,
        vec![],
        top_dict,
        trailing,
    ))?)
}
