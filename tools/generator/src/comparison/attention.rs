//! Explicit review annotations, separate from fitting decisions and normal preview coverage.
use super::*;
use crate::specimen_config;
use std::path::PathBuf;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AttentionConfig {
    schema_version: String,
    version: String,
    specimens: PathBuf,
    symbols: Vec<Mark>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Mark {
    id: String,
    family_id: String,
    character: String,
    size_px: f32,
    axes: BTreeMap<String, f32>,
    profile: String,
    status: String,
    inspection: String,
    #[serde(default)]
    description: String,
    #[serde(default)]
    disposition: Option<String>,
}

#[derive(Serialize)]
pub(super) struct AttentionCase {
    id: String,
    family_id: String,
    family_name: String,
    codepoint: u32,
    character: String,
    size_px: f32,
    axes: BTreeMap<String, f32>,
    status: String,
    inspection: String,
    description: String,
    canvas: Canvas,
    profiles: Vec<GlyphProfile>,
}

fn validate(mark: &Mark) -> Result<u32, Error> {
    let mut chars = mark.character.chars();
    let ch = chars
        .next()
        .ok_or_else(|| fail("attention symbol is empty"))?;
    if chars.next().is_some()
        || !safe_id(&mark.id)
        || !safe_id(&mark.family_id)
        || !mark.size_px.is_finite()
        || !(1.0..=512.0).contains(&mark.size_px)
        || mark.axes.iter().any(|(tag, value)| {
            tag.len() != 4 || !tag.bytes().all(|b| (32..=126).contains(&b)) || !value.is_finite()
        })
        || !matches!(mark.profile.as_str(), "mono_1bit" | "gray_3bit")
        || !matches!(mark.status.as_str(), "pending" | "confirmed" | "accepted")
        || mark.inspection.trim().is_empty()
        || mark.inspection.len() > 160
        || mark.description.len() > 240
        || (mark.status == "accepted"
            && mark
                .disposition
                .as_deref()
                .is_none_or(|s| s.trim().is_empty()))
    {
        return Err(fail(
            "invalid attention symbol, scope, status or description",
        ));
    }
    Ok(ch as u32)
}

pub(super) fn build(
    path: &Path,
    selection: &Selection,
    previous: &Package,
    current: &Package,
    assets: &mut BTreeMap<String, Vec<u8>>,
) -> Result<Vec<AttentionCase>, Error> {
    let config: AttentionConfig = read(path)?;
    if config.schema_version != "symbol-attention-v1" || config.version != selection.current.label {
        return Err(fail(
            "attention annotations must match the current iteration",
        ));
    }
    let loaded = specimen_config::load(
        &path
            .parent()
            .unwrap_or(Path::new("."))
            .join(&config.specimens),
    )?;
    let latest = loaded.config.latest_variant()?;
    let variant = loaded
        .config
        .variants
        .iter()
        .find(|v| v.id == latest)
        .unwrap();
    if variant.version.as_deref().unwrap_or("Reference") != selection.current.label
        || serde_json::to_value(current.canonical.variant.as_ref()).unwrap()
            != serde_json::to_value(Some(variant)).unwrap()
    {
        return Err(fail(
            "attention specimen selection differs from publication",
        ));
    }
    let mut results = Vec::new();
    let mut ids = BTreeSet::new();
    let mut cases = BTreeSet::new();
    for mark in config.symbols {
        let codepoint = validate(&mark)?;
        if !ids.insert(mark.id.clone())
            || !cases.insert((
                mark.family_id.clone(),
                mark.size_px.to_bits(),
                serde_json::to_string(&mark.axes).unwrap(),
                codepoint,
                mark.profile.clone(),
            ))
        {
            return Err(fail("duplicate attention ID or symbol case"));
        }
        let family = current
            .manifest
            .families
            .iter()
            .find(|f| f.id == mark.family_id)
            .ok_or_else(|| fail("attention family missing from current publication"))?;
        let profile = loaded
            .config
            .profiles
            .iter()
            .find(|p| p.id == mark.profile)
            .ok_or_else(|| fail("attention profile missing from configuration"))?;
        if !current
            .manifest
            .profiles
            .iter()
            .any(|p| p.id == mark.profile && p.output_bits == profile.output_bits)
        {
            return Err(fail("attention profile differs from publication"));
        }
        let published_profile = current
            .canonical
            .profiles
            .iter()
            .find(|p| p.id == mark.profile);
        if serde_json::to_value(published_profile).unwrap()
            != serde_json::to_value(Some(profile)).unwrap()
        {
            return Err(fail(
                "attention render settings differ from publication; regenerate specimens",
            ));
        }
        if mark.status == "accepted" {
            continue;
        }
        let published_pair = [&previous, &current].map(|package| {
            let c = case(package, &mark.family_id, mark.size_px, &mark.profile)?;
            (c.axes == mark.axes)
                .then(|| bitmap(Some(c), codepoint))
                .flatten()
        });
        let [Some(before_record), Some(after_record)] = published_pair else {
            return Err(fail("attention case is outside the published preview scope; keep diagnostic sizes/axes/profiles isolated"));
        };
        if !loaded.cases.iter().any(|c| {
            c.family_id == mark.family_id
                && c.variant == latest
                && c.size_px == mark.size_px
                && c.axes == mark.axes
                && c.profile == mark.profile
        }) {
            return Err(fail(
                "attention case is outside the configured preview scope",
            ));
        }
        let pair = [before_record, after_record];
        let area = canvas(pair.into_iter())?;
        let before = aligned(pair[0], area);
        let after = aligned(pair[1], area);
        let encode_ink = |levels: &[u8]| {
            levels
                .iter()
                .flat_map(|q| rgb(*q, profile.output_bits))
                .collect::<Vec<_>>()
        };
        results.push(AttentionCase {
            id: mark.id,
            family_id: mark.family_id,
            family_name: family.name.clone(),
            codepoint,
            character: mark.character,
            size_px: mark.size_px,
            axes: mark.axes,
            status: mark.status,
            inspection: mark.inspection,
            description: mark.description,
            canvas: area,
            profiles: vec![GlyphProfile {
                id: mark.profile,
                advance_px: ((i64::from(pair[1].advance_26_6) + 32).div_euclid(64)).max(1) as u32,
                previous: Some(image(&encode_ink(&before), area, assets)?),
                current: Some(image(&encode_ink(&after), area, assets)?),
                difference: Some(image(
                    &difference(&before, &after, profile.output_bits),
                    area,
                    assets,
                )?),
                reason: None,
            }],
        });
    }
    Ok(results)
}
