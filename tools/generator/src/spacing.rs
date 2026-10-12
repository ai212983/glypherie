use crate::{fail, fixed, Config, Error, Glyph, KerningPair, MetricRounding};
use harfrust::{Feature, FontRef, ShapeOptions, ShaperData, ShaperInstance, Tag, UnicodeBuffer};
use skrifa_baseline::MetadataProvider;
use std::collections::BTreeMap;
use unicode_general_category::{get_general_category, GeneralCategory};
use unicode_script::{Script, UnicodeScript};

pub(crate) fn validate_request(ch: char) -> Result<(), Error> {
    if get_general_category(ch) == GeneralCategory::Unassigned {
        Ok(())
    } else {
        validate_character(ch)
    }
}

pub(crate) fn validate_character(ch: char) -> Result<(), Error> {
    let mark = matches!(
        get_general_category(ch),
        GeneralCategory::NonspacingMark
            | GeneralCategory::SpacingMark
            | GeneralCategory::EnclosingMark
            | GeneralCategory::Format
            | GeneralCategory::Control
    );
    if mark
        || !matches!(
            ch.script(),
            Script::Latin | Script::Greek | Script::Cyrillic | Script::Common
        )
    {
        return Err(fail(format!("U+{:04X} requires unsupported text-run shaping; repertoire supports Latin, Greek, Cyrillic and common symbols",ch as u32)));
    }
    Ok(())
}

/// Bounded source-font kerning display: horizontal pair adjustments for the
/// printable ASCII subset (U+0020..=U+007E) at one size/axes coordinate.
///
/// Source foundation: the same scalar harfrust shaping path as fitted
/// generation (pair kerning only, ligatures off), evaluated with
/// `kerning = true` and `MetricRounding::Subpixel`. No outlines are drawn and
/// no bitmaps are rasterized: shaping only reads each placeholder's
/// codepoint and cmap glyph id. Numeric settings reuse
/// `validate_settings` and variation coordinates reuse the shared axis
/// validation; those failures and single-glyph shaping errors stay explicit
/// errors. Codepoints absent from cmap are skipped. Pairs that need more
/// than a scalar left-advance change (substitutions or text-run positioning)
/// are omitted and reported in `skipped_pairs`, so one contextual pair
/// cannot hide the subset; this display omission changes no layout path.
/// The ASCII scope is explicit: this is not a complete font-table
/// enumeration.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
pub struct AsciiKerning {
    pub pairs: Vec<KerningPair>,
    pub skipped_pairs: u32,
}

pub fn ascii_kerning_pairs(
    data: &[u8],
    size_px: f32,
    axes: &BTreeMap<String, f32>,
) -> Result<AsciiKerning, Error> {
    let config = Config {
        size_px,
        axes: axes.clone(),
        kerning: true,
        metric_rounding: MetricRounding::Subpixel,
        ..Config::default()
    };
    crate::validate_settings(&config)?;
    let font = crate::open_font(data)?;
    crate::validate_axes(&font, &config.axes)?;
    let cmap = font.charmap();
    let mut glyphs = Vec::new();
    for codepoint in 0x20u32..=0x7E {
        let ch = char::from_u32(codepoint).unwrap();
        validate_character(ch)?;
        if let Some(gid) = cmap.map(ch).filter(|g| g.to_u32() != 0) {
            glyphs.push(Glyph {
                codepoint,
                glyph_id: gid.to_u32(),
                advance_26_6: 0,
                left: 0,
                top: 0,
                width: 0,
                height: 0,
                pixels: Vec::new(),
            });
        }
    }
    let (pairs, skipped_pairs) = extract_impl(data, &config, &glyphs, false)?;
    Ok(AsciiKerning {
        pairs,
        skipped_pairs,
    })
}

pub(crate) fn extract(
    data: &[u8],
    config: &Config,
    glyphs: &[Glyph],
) -> Result<Vec<KerningPair>, Error> {
    let (pairs, _) = extract_impl(data, config, glyphs, true)?;
    Ok(pairs)
}

/// Shared scalar-only shaping body: pair kerning on, ligatures off. Fitted
/// generation (`strict`) keeps the exact previous contract: any pair beyond
/// scalar advances is an error. The ASCII display table (`!strict`) omits
/// such unrepresentable pairs and reports how many, so one contextual pair
/// cannot hide the whole subset; single-glyph failures stay errors in both
/// modes. Returns the pairs plus the omitted-pair count (zero when strict).
fn extract_impl(
    data: &[u8],
    config: &Config,
    glyphs: &[Glyph],
    strict: bool,
) -> Result<(Vec<KerningPair>, u32), Error> {
    let font = FontRef::from_index(data, 0).map_err(|e| fail(format!("shaper font: {e}")))?;
    let instance =
        ShaperInstance::from_variations(&font, config.axes.iter().map(|(t, v)| (t.as_str(), *v)));
    let shaping = ShaperData::new(&font);
    let shaper = shaping.shaper(&font).instance(Some(&instance)).build();
    let scale = config.size_px / shaper.units_per_em() as f32;
    let features = [
        Feature::new(Tag::new(b"liga"), 0, ..),
        Feature::new(Tag::new(b"clig"), 0, ..),
        Feature::new(Tag::new(b"calt"), 0, ..),
        Feature::new(Tag::new(b"kern"), u32::from(config.kerning), ..),
    ];
    let shape = |text: &str, expected: &[u32]| -> Result<Vec<i32>, Error> {
        let mut buffer = UnicodeBuffer::new();
        buffer.push_str(text);
        buffer.guess_segment_properties();
        let out = shaper.shape(buffer, ShapeOptions::new().features(&features));
        if out
            .glyph_infos()
            .iter()
            .map(|g| g.glyph_id)
            .ne(expected.iter().copied())
            || out
                .glyph_positions()
                .iter()
                .any(|p| p.x_offset != 0 || p.y_offset != 0 || p.y_advance != 0)
        {
            return Err(fail(format!("text {text:?} requires substitutions or positioning beyond scalar glyphs and pair kerning")));
        }
        Ok(out.glyph_positions().iter().map(|p| p.x_advance).collect())
    };
    let mut singles = Vec::with_capacity(glyphs.len());
    for glyph in glyphs {
        let ch = char::from_u32(glyph.codepoint).unwrap();
        singles.push(shape(&ch.to_string(), &[glyph.glyph_id])?[0]);
    }
    let mut pairs = Vec::new();
    let mut skipped: u32 = 0;
    for (i, left) in glyphs.iter().enumerate() {
        for (j, right) in glyphs.iter().enumerate() {
            let text: String = [
                char::from_u32(left.codepoint).unwrap(),
                char::from_u32(right.codepoint).unwrap(),
            ]
            .into_iter()
            .collect();
            let advances = match shape(&text, &[left.glyph_id, right.glyph_id]) {
                Ok(advances) => advances,
                Err(_) if !strict => {
                    skipped += 1;
                    continue;
                }
                Err(error) => return Err(error),
            };
            if advances[1] != singles[j] {
                if !strict {
                    skipped += 1;
                    continue;
                }
                return Err(fail(format!(
                    "pair {text:?} changes the right advance; requires text-run positioning"
                )));
            }
            let adjustment = fixed(
                (advances[0] - singles[i]) as f32 * scale,
                config.metric_rounding,
            );
            if adjustment != 0 {
                pairs.push(KerningPair {
                    left: left.codepoint,
                    right: right.codepoint,
                    adjustment_26_6: adjustment,
                });
            }
        }
    }
    Ok((pairs, skipped))
}
