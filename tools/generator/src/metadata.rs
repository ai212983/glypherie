//! Descriptive source-font metadata; never used to select fitting behavior.
//! Sources: OpenType name, fvar, OS/2, post, cmap, GPOS and kern tables,
//! plus Apple's kerx table. Style describes the default instance.
use crate::{fail, Error};
use serde::{Deserialize, Serialize};
use skrifa::{
    attribute::Style,
    raw::{
        tables::{gpos::PositionLookup, kern, kerx},
        ReadError, TableProvider,
    },
    string::StringId,
    FontRef, MetadataProvider,
};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FontMetadata {
    /// English when available, otherwise the first localized value. Missing strings are null.
    pub names: BTreeMap<String, Option<String>>,
    pub axes: Vec<AxisMetadata>,
    /// Total glyphs from OpenType maxp.numGlyphs, including unencoded glyphs.
    #[serde(default)]
    pub glyph_count: Option<u32>,
    /// Source hint presence, not a claim about quality or axis coverage.
    #[serde(default)]
    pub font_hints: Option<bool>,
    pub kerning: KerningMetadata,
    pub style: StyleMetadata,
    pub classification: ClassificationMetadata,
    /// Nominal Unicode coverage, not a claim about language shaping support.
    pub coverage: Option<UnicodeCoverage>,
    /// Raw OS/2 range flags, separate from actual cmap coverage.
    pub declared_unicode_ranges: Option<[u32; 4]>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AxisMetadata {
    pub tag: String,
    pub name: Option<String>,
    pub min: f32,
    pub default: f32,
    pub max: f32,
    pub hidden: bool,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KerningMetadata {
    pub horizontal: bool,
    pub vertical: bool,
    pub sources: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StyleMetadata {
    pub slope: Option<String>,
    pub weight_class: Option<u16>,
    pub width_class: Option<u16>,
    pub italic_angle: Option<f32>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClassificationMetadata {
    /// High byte is IBM family class; low byte is its subclass.
    pub family_class: Option<u16>,
    pub panose: Option<[u8; 10]>,
    /// The post table's declaration, not an analysis of glyph widths.
    pub monospaced: Option<bool>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct UnicodeCoverage {
    pub character_count: u32,
    /// Sorted, disjoint inclusive ranges of Unicode scalar values.
    pub ranges: Vec<[u32; 2]>,
}

fn optional<T>(result: Result<T, ReadError>) -> Result<Option<T>, Error> {
    match result {
        Ok(value) => Ok(Some(value)),
        Err(ReadError::TableIsMissing(_)) => Ok(None),
        Err(error) => Err(fail(format!("font metadata: {error}"))),
    }
}

fn string(font: &FontRef<'_>, id: u16) -> Option<String> {
    font.localized_strings(StringId::new(id))
        .filter(|value| !value.to_string().trim().is_empty())
        .min_by_key(|value| match value.language() {
            Some("en-US") => 0,
            Some("en") => 1,
            None => 2,
            _ => 3,
        })
        .map(|value| value.to_string())
}

/// Extract metadata from the same single font face accepted by the renderer.
/// Missing optional tables remain unknown; malformed tables return an error.
pub fn extract(data: &[u8]) -> Result<FontMetadata, Error> {
    let font = FontRef::new(data).map_err(|error| fail(error.to_string()))?;
    optional(font.name())?;
    if let Some(fvar) = optional(font.fvar())? {
        fvar.axes().map_err(|error| fail(error.to_string()))?;
    }
    let os2 = optional(font.os2())?;
    let post = optional(font.post())?;
    let head = optional(font.head())?;
    let names = [
        ("family", 16, Some(1)),
        ("style", 17, Some(2)),
        ("full", 4, None),
        ("postscript", 6, None),
        ("version", 5, None),
        ("copyright", 0, None),
        ("manufacturer", 8, None),
        ("designer", 9, None),
        ("description", 10, None),
        ("vendor_url", 11, None),
        ("designer_url", 12, None),
        ("license", 13, None),
        ("license_url", 14, None),
    ]
    .into_iter()
    .map(|(key, id, fallback)| {
        (
            key.into(),
            string(&font, id).or_else(|| fallback.and_then(|id| string(&font, id))),
        )
    })
    .collect();
    let axes = font
        .axes()
        .iter()
        .map(|axis| AxisMetadata {
            tag: axis.tag().to_string(),
            name: string(&font, axis.name_id().to_u16()),
            min: axis.min_value(),
            default: axis.default_value(),
            max: axis.max_value(),
            hidden: axis.is_hidden(),
        })
        .collect();
    let attrs = font.attributes();
    let slope = if os2.is_some() || head.is_some() {
        Some(
            match attrs.style {
                Style::Normal => "upright",
                Style::Italic => "italic",
                Style::Oblique(_) => "oblique",
            }
            .into(),
        )
    } else {
        None
    };
    let style = StyleMetadata {
        slope,
        weight_class: os2.as_ref().map(|table| table.us_weight_class()),
        width_class: os2.as_ref().map(|table| table.us_width_class()),
        italic_angle: post
            .as_ref()
            .map(|table| table.italic_angle().to_f64() as f32),
    };
    let classification = ClassificationMetadata {
        family_class: os2.as_ref().map(|table| table.s_family_class() as u16),
        panose: os2
            .as_ref()
            .map(|table| table.panose_10().try_into().unwrap()),
        monospaced: post.as_ref().map(|table| table.is_fixed_pitch() != 0),
    };
    let declared_unicode_ranges = os2.as_ref().map(|table| {
        [
            table.ul_unicode_range_1(),
            table.ul_unicode_range_2(),
            table.ul_unicode_range_3(),
            table.ul_unicode_range_4(),
        ]
    });
    let glyph_count = optional(font.maxp())?.map(|table| u32::from(table.num_glyphs()));
    let cmap = optional(font.cmap())?;
    let charmap = font.charmap();
    let coverage = if cmap.is_some() && charmap.has_map() && !charmap.is_symbol() {
        let mut ranges: Vec<[u32; 2]> = Vec::new();
        let mut character_count = 0;
        for (cp, gid) in charmap.mappings() {
            if char::from_u32(cp).is_none()
                || gid.to_u32() == 0
                || glyph_count.is_some_and(|count| gid.to_u32() >= count)
            {
                continue;
            }
            character_count += 1;
            match ranges.last_mut() {
                Some(range) if range[1] + 1 == cp => range[1] = cp,
                _ => ranges.push([cp, cp]),
            }
        }
        Some(UnicodeCoverage {
            character_count,
            ranges,
        })
    } else {
        None
    };
    Ok(FontMetadata {
        names,
        axes,
        glyph_count,
        font_hints: font_hint_presence(data)?,
        kerning: kerning(&font)?,
        style,
        classification,
        coverage,
        declared_unicode_ranges,
    })
}

fn font_hint_presence(data: &[u8]) -> Result<Option<bool>, Error> {
    let font = FontRef::new(data).map_err(|e| fail(e.to_string()))?;
    #[cfg(feature = "candidate")]
    let outlines = skrifa_scan::MetadataProvider::outline_glyphs(&font);
    #[cfg(not(feature = "candidate"))]
    let outlines = font.outline_glyphs();
    let mut unknown = false;
    for (_, glyph) in outlines.iter() {
        match glyph.has_hinting() {
            Some(true) => return Ok(Some(true)),
            None => unknown = true,
            _ => {}
        }
    }
    Ok(if unknown { None } else { Some(false) })
}

fn kerning(font: &FontRef<'_>) -> Result<KerningMetadata, Error> {
    let mut result = KerningMetadata::default();
    if let Some(gpos) = optional(font.gpos())? {
        let features = gpos
            .feature_list()
            .map_err(|error| fail(error.to_string()))?;
        let lookups = gpos
            .lookup_list()
            .map_err(|error| fail(error.to_string()))?;
        for record in features.feature_records() {
            let tag = record.feature_tag().to_string();
            if tag != "kern" && tag != "vkrn" {
                continue;
            }
            let feature = record
                .feature(features.offset_data())
                .map_err(|error| fail(error.to_string()))?;
            let mut present = false;
            for index in feature.lookup_list_indices() {
                let lookup = lookups
                    .lookups()
                    .get(index.get() as usize)
                    .map_err(|error| fail(error.to_string()))?;
                macro_rules! check_subtables {
                    ($lookup:expr) => {{
                        for subtable in $lookup.subtables().iter() {
                            subtable.map_err(|error| fail(error.to_string()))?;
                            present = true;
                        }
                    }};
                }
                match lookup {
                    PositionLookup::Single(table) => check_subtables!(table),
                    PositionLookup::Pair(table) => check_subtables!(table),
                    PositionLookup::Cursive(table) => check_subtables!(table),
                    PositionLookup::MarkToBase(table) => check_subtables!(table),
                    PositionLookup::MarkToLig(table) => check_subtables!(table),
                    PositionLookup::MarkToMark(table) => check_subtables!(table),
                    PositionLookup::Contextual(table) => check_subtables!(table),
                    PositionLookup::ChainContextual(table) => check_subtables!(table),
                    PositionLookup::Extension(table) => check_subtables!(table),
                }
            }
            if present {
                result.horizontal |= tag == "kern";
                result.vertical |= tag == "vkrn";
                let source = format!("GPOS {tag}");
                if !result.sources.contains(&source) {
                    result.sources.push(source);
                }
            }
        }
    }
    if let Some(kern) = optional(font.kern())? {
        let count = match &kern {
            kern::Kern::Ot(table) => u32::from(table.n_tables()),
            kern::Kern::Aat(table) => table.n_tables(),
        };
        let mut seen = 0;
        for subtable in kern.subtables() {
            let subtable = subtable.map_err(|error| fail(error.to_string()))?;
            seen += 1;
            let kind = subtable.kind().map_err(|error| fail(error.to_string()))?;
            let present = match kind {
                kern::SubtableKind::Format0(table) => !table.pairs().is_empty(),
                _ => true,
            };
            if present {
                result.horizontal |= subtable.is_horizontal();
                result.vertical |= subtable.is_vertical();
                if !result.sources.iter().any(|source| source == "kern") {
                    result.sources.push("kern".into());
                }
            }
        }
        if seen != count {
            return Err(fail("font metadata: truncated kern subtables"));
        }
    }
    if let Some(kerx) = optional(font.kerx())? {
        let mut seen = 0;
        for subtable in kerx.subtables().iter().take(kerx.n_tables() as usize) {
            let subtable = subtable.map_err(|error| fail(error.to_string()))?;
            seen += 1;
            let kind = subtable.kind().map_err(|error| fail(error.to_string()))?;
            let present = match kind {
                kerx::SubtableKind::Format0(table) => !table.pairs().is_empty(),
                _ => true,
            };
            if present {
                result.horizontal |= subtable.is_horizontal();
                result.vertical |= subtable.is_vertical();
                if !result.sources.iter().any(|source| source == "kerx") {
                    result.sources.push("kerx".into());
                }
            }
        }
        if seen != kerx.n_tables() {
            return Err(fail("font metadata: truncated kerx subtables"));
        }
    }
    Ok(result)
}
