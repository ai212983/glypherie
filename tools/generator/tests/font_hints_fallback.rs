#![cfg(feature = "candidate")]

//! Conservative `FontHintsFirst` engine-selection fallback: candidate
//! monochrome `FontHintsFirst` uses upstream automatic Mono fitting only for
//! TrueType fonts verified to carry no glyph instructions, no `fpgm`, and an
//! absent or scan-control-only `prep`. Every other font keeps upstream engine
//! selection. Mechanical checks only; no optical acceptance.
//!
//! Synthetic fonts are rebuilt from `fonts/SourceSans3.ttf` (no glyph
//! instructions, scan-only `prep`) with the existing `write-fonts` builder
//! pattern: programs are added, glyph instruction streams are spliced into
//! `glyf`/`loca`, and `maxp` is left at `maxSizeOfInstructions == 0` as the
//! misleading-maximum witness.

use font_generator::{
    candidate,
    reference::{reference, ReferenceReport, ReferenceRequest, EXTENSIONS_NONE, PROFILE_MONO_1BIT},
    stem_fitting::EXTENSIONS_FONT_HINTS_FIRST,
    Config, Hinting,
};
use skrifa::{FontRef, MetadataProvider};
use std::{fs, path::Path};

const SCAN_ONLY_PREP: &[u8] = &[0xb8, 0x01, 0xff, 0x85, 0xb0, 0x04, 0x8d];
const PUSH_INSTR: &[u8] = &[0xb0, 0x01];

fn font(name: &str) -> Vec<u8> {
    fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap()
}

fn table(data: &[u8], tag: &[u8; 4]) -> Vec<u8> {
    let font = FontRef::new(data).unwrap();
    font.table_data(skrifa::Tag::new(tag))
        .unwrap()
        .as_bytes()
        .to_vec()
}

fn max_size_of_instructions(data: &[u8]) -> u16 {
    let maxp = table(data, b"maxp");
    u16::from_be_bytes([maxp[26], maxp[27]])
}

fn max_stack_elements(data: &[u8]) -> u16 {
    let maxp = table(data, b"maxp");
    u16::from_be_bytes(maxp[24..26].try_into().unwrap())
}

/// Copy one directory record over another, producing duplicate tags without
/// moving table data. `read-fonts` resolves duplicates by sorted binary
/// search or first match, so this stays a loadable font with ambiguous
/// table selection.
fn with_duplicate_record(data: &[u8], tag: &[u8; 4], victim: &[u8; 4]) -> Vec<u8> {
    let count = u16::from_be_bytes([data[4], data[5]]) as usize;
    let mut tag_rec = None;
    let mut victim_at = None;
    for i in 0..count {
        let base = 12 + 16 * i;
        if &data[base..base + 4] == tag {
            tag_rec = Some(data[base..base + 16].to_vec());
        }
        if &data[base..base + 4] == victim {
            victim_at = Some(base);
        }
    }
    let (tag_rec, victim_at) = (
        tag_rec.expect("tagged record"),
        victim_at.expect("victim record"),
    );
    let mut out = data.to_vec();
    out[victim_at..victim_at + 16].copy_from_slice(&tag_rec);
    out
}

fn prefer_interpreter(data: &[u8]) -> bool {
    FontRef::new(data)
        .unwrap()
        .outline_glyphs()
        .prefer_interpreter()
}

/// Rebuild a font from all of its tables, replacing `overrides`, dropping
/// `remove`, and adding override tags absent from the source directory.
fn rebuild(data: &[u8], overrides: &[(&[u8; 4], Vec<u8>)], remove: &[&[u8; 4]]) -> Vec<u8> {
    let source = FontRef::new(data).unwrap();
    let mut builder = write_fonts::FontBuilder::new();
    for record in source.table_directory().table_records() {
        let tag = record.tag();
        if remove.iter().any(|raw| tag == skrifa::Tag::new(raw)) {
            continue;
        }
        match overrides
            .iter()
            .find(|(raw, _)| tag == skrifa::Tag::new(raw))
        {
            Some((_, bytes)) => {
                builder.add_raw(tag, bytes.clone());
            }
            None => {
                builder.add_raw(tag, source.table_data(tag).unwrap().as_bytes());
            }
        }
    }
    for (raw, bytes) in overrides {
        let tag = skrifa::Tag::new(raw);
        if source.table_data(tag).is_none() {
            builder.add_raw(tag, bytes.clone());
        }
    }
    builder.build()
}

fn stripped(data: &[u8]) -> Vec<u8> {
    rebuild(data, &[], &[b"fpgm", b"prep"])
}

fn request(characters: &str) -> ReferenceRequest {
    let mut config = Config {
        size_px: 14.0,
        characters: characters.into(),
        hinting: Hinting::AutoFallback,
        output_bits: 1,
        ..Config::default()
    };
    config.axes.insert("wght".into(), 400.0);
    ReferenceRequest {
        profile: PROFILE_MONO_1BIT.into(),
        extensions: EXTENSIONS_FONT_HINTS_FIRST.into(),
        settings: config,
    }
}

fn render(data: &[u8], characters: &str) -> ReferenceReport {
    candidate::render(data, &request(characters)).unwrap()
}

fn assert_selected_engine(report: &ReferenceReport, engine: &str) {
    assert_eq!(report.hinting_requested, "auto_fallback");
    assert!(!report.records.is_empty());
    for record in &report.records {
        assert_eq!(record.selected_engine, engine, "U+{:04X}", record.codepoint);
    }
}

/// The candidate geometry must equal an explicit independent reference draw
/// with the expected engine: the fallback changes engine selection, never
/// the fitting itself.
fn assert_matches_explicit_engine(
    data: &[u8],
    characters: &str,
    actual: &ReferenceReport,
    engine: Hinting,
) {
    let mut explicit = request(characters);
    explicit.extensions = EXTENSIONS_NONE.into();
    explicit.settings.hinting = engine;
    let expected = reference(data, &explicit).unwrap();
    assert_eq!(actual.records.len(), expected.records.len());
    for (a, b) in actual.records.iter().zip(&expected.records) {
        assert_eq!(
            a.fitted_commands, b.fitted_commands,
            "U+{:04X}",
            a.codepoint
        );
    }
}

fn glyph_parts(data: &[u8]) -> (Vec<usize>, Vec<u8>, bool) {
    let head = table(data, b"head");
    let long = u16::from_be_bytes([head[50], head[51]]) == 1;
    let maxp = table(data, b"maxp");
    let num = u16::from_be_bytes([maxp[4], maxp[5]]) as usize;
    let loca = table(data, b"loca");
    let offsets = (0..=num)
        .map(|i| {
            if long {
                u32::from_be_bytes(loca[4 * i..4 * i + 4].try_into().unwrap()) as usize
            } else {
                u16::from_be_bytes(loca[2 * i..2 * i + 2].try_into().unwrap()) as usize * 2
            }
        })
        .collect();
    (offsets, table(data, b"glyf"), long)
}

fn encode_loca(offsets: &[usize], long: bool) -> Vec<u8> {
    let mut out = Vec::new();
    for offset in offsets {
        if long {
            out.extend_from_slice(&(*offset as u32).to_be_bytes());
        } else {
            assert_eq!(offset % 2, 0, "short loca requires even offsets");
            out.extend_from_slice(&(*offset as u16 / 2).to_be_bytes());
        }
    }
    out
}

fn contours(glyph: &[u8]) -> i16 {
    i16::from_be_bytes([glyph[0], glyph[1]])
}

/// Splice a real instruction stream into the first clean simple glyph
/// (index >= 1, keeping `.notdef` pristine), leaving `maxp` untouched.
fn with_simple_instructions(data: &[u8], instructions: &[u8]) -> Vec<u8> {
    assert_eq!(instructions.len() % 2, 0);
    let (offsets, glyf, long) = glyph_parts(data);
    let mut target = None;
    for (i, pair) in offsets.windows(2).enumerate().skip(1) {
        let glyph = &glyf[pair[0]..pair[1]];
        if glyph.len() < 12 || contours(glyph) <= 0 {
            continue;
        }
        let ends = 10 + 2 * contours(glyph) as usize + 2;
        if glyph.len() >= ends && u16::from_be_bytes([glyph[ends - 2], glyph[ends - 1]]) == 0 {
            target = Some((i, ends));
            break;
        }
    }
    let (index, ends) = target.expect("clean simple glyph");
    let (start, end) = (offsets[index], offsets[index + 1]);
    let mut patched = Vec::new();
    patched.extend_from_slice(&glyf[start..start + ends - 2]);
    patched.extend_from_slice(&(instructions.len() as u16).to_be_bytes());
    patched.extend_from_slice(instructions);
    patched.extend_from_slice(&glyf[start + ends..end]);
    let mut new_glyf = Vec::new();
    new_glyf.extend_from_slice(&glyf[..start]);
    new_glyf.extend_from_slice(&patched);
    new_glyf.extend_from_slice(&glyf[end..]);
    let mut new_offsets = offsets.clone();
    for offset in new_offsets.iter_mut().skip(index + 1) {
        *offset += instructions.len();
    }
    rebuild(
        data,
        &[
            (b"glyf", new_glyf),
            (b"loca", encode_loca(&new_offsets, long)),
        ],
        &[],
    )
}

/// Set `WE_HAVE_INSTRUCTIONS` on the final component of the first clean
/// composite glyph and append a real instruction stream.
fn with_composite_instructions(data: &[u8], instructions: &[u8]) -> Vec<u8> {
    assert_eq!(instructions.len() % 2, 0);
    let (offsets, glyf, long) = glyph_parts(data);
    let mut target = None;
    for (i, pair) in offsets.windows(2).enumerate().skip(1) {
        let glyph = &glyf[pair[0]..pair[1]];
        if glyph.len() < 14 || contours(glyph) != -1 {
            continue;
        }
        // Walk component records to the final flags field; component layout
        // follows the `glyf` specification (flags, glyph id, arguments, then
        // an optional transform sized by its scale bits).
        let mut cursor = 10usize;
        let mut last_flags = None;
        let mut clean = true;
        loop {
            if cursor + 4 > glyph.len() {
                clean = false;
                break;
            }
            let flags = u16::from_be_bytes([glyph[cursor], glyph[cursor + 1]]);
            cursor += 4;
            cursor += if flags & 0x0001 != 0 { 4 } else { 2 };
            cursor += if flags & 0x0008 != 0 {
                2
            } else if flags & 0x0040 != 0 {
                4
            } else if flags & 0x0080 != 0 {
                8
            } else {
                0
            };
            if cursor > glyph.len() {
                clean = false;
                break;
            }
            if flags & 0x0020 == 0 {
                if flags & 0x0100 == 0 && cursor == glyph.len() {
                    last_flags = Some((cursor, flags));
                } else {
                    clean = false;
                }
                break;
            }
        }
        if clean {
            if let Some((end, flags)) = last_flags {
                target = Some((i, end, flags));
                break;
            }
        }
    }
    let (index, _, flags) = target.expect("clean composite glyph");
    assert_eq!(flags & 0x0100, 0);
    let (start, end) = (offsets[index], offsets[index + 1]);
    let mut patched = glyf[start..end].to_vec();
    // Re-walk the copy to locate the final flags field, then set
    // `WE_HAVE_INSTRUCTIONS` (0x0100) and append the stream.
    let mut cursor = 10usize;
    let mut last_at = 0usize;
    loop {
        last_at = cursor;
        let flags = u16::from_be_bytes([patched[cursor], patched[cursor + 1]]);
        cursor += 4;
        cursor += if flags & 0x0001 != 0 { 4 } else { 2 };
        cursor += if flags & 0x0008 != 0 {
            2
        } else if flags & 0x0040 != 0 {
            4
        } else if flags & 0x0080 != 0 {
            8
        } else {
            0
        };
        if flags & 0x0020 == 0 {
            break;
        }
    }
    patched[last_at] |= 0x01;
    patched.extend_from_slice(&(instructions.len() as u16).to_be_bytes());
    patched.extend_from_slice(instructions);
    let mut new_glyf = Vec::new();
    new_glyf.extend_from_slice(&glyf[..start]);
    new_glyf.extend_from_slice(&patched);
    new_glyf.extend_from_slice(&glyf[end..]);
    let mut new_offsets = offsets.clone();
    for offset in new_offsets.iter_mut().skip(index + 1) {
        *offset += 2 + instructions.len();
    }
    rebuild(
        data,
        &[
            (b"glyf", new_glyf),
            (b"loca", encode_loca(&new_offsets, long)),
        ],
        &[],
    )
}

#[test]
fn scan_only_prep_falls_back_to_automatic() {
    let base = stripped(&font("SourceSans3.ttf"));
    assert!(!prefer_interpreter(&base));
    let data = rebuild(&base, &[(b"prep", SCAN_ONLY_PREP.to_vec())], &[]);
    // Upstream still prefers the interpreter for any nonempty `prep`, so this
    // premise distinguishes the fallback from upstream selection.
    assert!(prefer_interpreter(&data));
    let actual = render(&data, "aHm");
    assert_selected_engine(&actual, "auto");
    assert_matches_explicit_engine(&data, "aHm", &actual, Hinting::Auto);
}

#[test]
fn program_free_font_uses_automatic() {
    let data = stripped(&font("SourceSans3.ttf"));
    assert!(!prefer_interpreter(&data));
    let actual = render(&data, "aHm");
    assert_selected_engine(&actual, "auto");
    assert_matches_explicit_engine(&data, "aHm", &actual, Hinting::Auto);
}

#[test]
fn hinted_font_keeps_interpreter() {
    let data = font("Roboto.ttf");
    assert!(prefer_interpreter(&data));
    let actual = render(&data, "aHm");
    assert_selected_engine(&actual, "interpreter");
    assert_matches_explicit_engine(&data, "aHm", &actual, Hinting::Interpreter);
}

#[test]
fn real_simple_instructions_keep_interpreter_despite_zero_maxp() {
    let base = stripped(&font("SourceSans3.ttf"));
    assert_eq!(max_size_of_instructions(&base), 0);
    // Real glyph instructions with a misleading zero maximum, plus the
    // scan-only `prep` that makes upstream prefer the interpreter: only
    // actual glyph-data verification retains the interpreter here.
    let data = with_simple_instructions(&base, PUSH_INSTR);
    let data = rebuild(&data, &[(b"prep", SCAN_ONLY_PREP.to_vec())], &[]);
    assert_eq!(max_size_of_instructions(&data), 0);
    assert!(prefer_interpreter(&data));
    let actual = render(&data, "aHm");
    assert_selected_engine(&actual, "interpreter");
    assert_matches_explicit_engine(&data, "aHm", &actual, Hinting::Interpreter);
}

#[test]
fn real_composite_instructions_keep_interpreter() {
    let base = stripped(&font("SourceSans3.ttf"));
    let data = with_composite_instructions(&base, PUSH_INSTR);
    let data = rebuild(&data, &[(b"prep", SCAN_ONLY_PREP.to_vec())], &[]);
    assert_eq!(max_size_of_instructions(&data), 0);
    let actual = render(&data, "aHm");
    assert_selected_engine(&actual, "interpreter");
    assert_matches_explicit_engine(&data, "aHm", &actual, Hinting::Interpreter);
}

#[test]
fn unexpected_and_truncated_prep_keep_interpreter() {
    let base = stripped(&font("SourceSans3.ttf"));
    // Valid but unrecognized programs keep upstream interpreter selection.
    for prep in [&[0x00][..], &[0xb0, 0x01, 0x85, 0x00][..]] {
        let data = rebuild(&base, &[(b"prep", prep.to_vec())], &[]);
        assert!(prefer_interpreter(&data));
        let actual = render(&data, "aHm");
        assert_selected_engine(&actual, "interpreter");
    }
    // Truncated bytecode keeps the upstream setup failure: the fallback must
    // not mask it by silently fitting automatically.
    let data = rebuild(&base, &[(b"prep", vec![0xb0])], &[]);
    assert!(candidate::render(&data, &request("aHm")).is_err());
}

#[test]
fn duplicate_directory_tags_keep_upstream_selection() {
    let base = stripped(&font("SourceSans3.ttf"));
    let data = rebuild(&base, &[(b"prep", SCAN_ONLY_PREP.to_vec())], &[]);
    assert!(prefer_interpreter(&data));
    // Duplicating the `prep` record over the unused signature record keeps
    // a loadable font whose `prep` selection is ambiguous: the fallback
    // rejects the directory and upstream selection (interpreter) applies.
    let data = with_duplicate_record(&data, b"prep", b"DSIG");
    let actual = render(&data, "aHm");
    assert_selected_engine(&actual, "interpreter");
    assert_matches_explicit_engine(&data, "aHm", &actual, Hinting::Interpreter);
}

#[test]
fn overflowing_prep_keeps_upstream_setup_error() {
    let base = stripped(&font("SourceSans3.ttf"));
    // The fixture declares zero stack elements, so the interpreter stack
    // holds 32 values: forty pushes overflow it upstream.
    assert_eq!(max_stack_elements(&base), 0);
    let mut prep = Vec::new();
    for _ in 0..5 {
        prep.push(0xb7);
        prep.extend([0u8; 8]);
    }
    prep.push(0x85);
    let data = rebuild(&base, &[(b"prep", prep)], &[]);
    assert!(prefer_interpreter(&data));
    // The fallback must not mask the upstream stack-overflow setup error by
    // silently fitting automatically.
    assert!(candidate::render(&data, &request("aHm")).is_err());
}

#[test]
fn nonempty_fpgm_keeps_interpreter() {
    let base = stripped(&font("SourceSans3.ttf"));
    let data = rebuild(&base, &[(b"fpgm", PUSH_INSTR.to_vec())], &[]);
    assert!(prefer_interpreter(&data));
    let actual = render(&data, "aHm");
    assert_selected_engine(&actual, "interpreter");
}

#[test]
fn explicit_policies_are_isolated_from_the_fallback() {
    let data = rebuild(
        &stripped(&font("SourceSans3.ttf")),
        &[(b"prep", SCAN_ONLY_PREP.to_vec())],
        &[],
    );
    // Forced automatic Mono is unchanged: it already selects `auto`.
    let mut forced = request("aHm");
    forced.extensions = font_generator::stem_fitting::EXTENSIONS_MONO_WIDTH_01.into();
    let forced = candidate::render(&data, &forced).unwrap();
    assert_eq!(forced.hinting_requested, "auto");
    for record in &forced.records {
        assert_eq!(record.selected_engine, "auto");
    }
    // Explicit reference engines are unchanged by the candidate fallback.
    for (hinting, engine) in [
        (Hinting::Auto, "auto"),
        (Hinting::Interpreter, "interpreter"),
    ] {
        let mut explicit = request("aHm");
        explicit.extensions = EXTENSIONS_NONE.into();
        explicit.settings.hinting = hinting;
        let report = reference(&data, &explicit).unwrap();
        assert_eq!(report.hinting_requested, engine);
        for record in &report.records {
            assert_eq!(record.selected_engine, engine);
        }
    }
    // CFF outlines keep upstream interpreter selection (the static fixture
    // carries no variation axes, so it uses a default configuration).
    let cff = include_bytes!("fixtures/static-cff.otf").as_slice();
    let cff_report = candidate::render(
        cff,
        &ReferenceRequest {
            profile: PROFILE_MONO_1BIT.into(),
            extensions: EXTENSIONS_FONT_HINTS_FIRST.into(),
            settings: Config {
                characters: "A".into(),
                hinting: Hinting::AutoFallback,
                ..Config::default()
            },
        },
    )
    .unwrap();
    assert_selected_engine(&cff_report, "interpreter");
}
