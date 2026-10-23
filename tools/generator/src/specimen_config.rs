pub use crate::renderer::RendererRole;
use crate::{fail, Error, Hinting};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SpecimenConfig {
    pub schema_version: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preview_policy: Option<PathBuf>,
    pub characters: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub samples: Vec<Sample>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cards: Option<Vec<Card>>,
    pub variants: Vec<Variant>,
    pub profiles: Vec<Profile>,
    pub defaults: Selection,
    pub families: Vec<Family>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Variant {
    pub id: String,
    pub kind: VariantKind,
    pub version: Option<String>,
    pub hinting: Hinting,
    pub extensions: String,
    /// Stable renderer role; versions identify states, never Cargo features.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub renderer: Option<RendererRole>,
}

impl Variant {
    pub fn renderer(&self) -> RendererRole {
        self.renderer
            .unwrap_or(if self.kind == VariantKind::Reference {
                RendererRole::Reference
            } else {
                RendererRole::Candidate
            })
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Sample {
    pub id: String,
    pub label: String,
    pub text: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Card {
    pub id: String,
    pub title: String,
    pub content: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum VariantKind {
    Reference,
    Iteration,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    pub id: String,
    pub output_bits: u8,
    pub mono_threshold: u8,
    pub gray_gamma: f32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub sizes: Vec<SizeSelection>,
    pub variants: Vec<String>,
    pub profiles: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Family {
    pub id: String,
    pub name: String,
    pub font: PathBuf,
    pub provenance: Provenance,
    pub axes: BTreeMap<String, AxisValue>,
    pub sizes: Option<Vec<SizeSelection>>,
    pub variants: Option<Vec<String>>,
    pub profiles: Option<Vec<String>>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    pub source: String,
    pub license: String,
    pub expected_sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(untagged)]
pub enum AxisValue {
    Fixed(f32),
    Binding(AxisBinding),
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AxisBinding {
    SizePx,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(untagged)]
pub enum SizeSelection {
    Size(f32),
    Overrides(SizeOverrides),
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SizeOverrides {
    pub size_px: f32,
    pub variants: Option<Vec<String>>,
    pub profiles: Option<Vec<String>>,
}

#[derive(Clone, Debug)]
pub struct RenderCase {
    pub family_id: String,
    pub font: PathBuf,
    pub size_px: f32,
    pub axes: BTreeMap<String, f32>,
    pub variant: String,
    pub profile: String,
}

#[derive(Clone, Debug)]
pub struct LoadedSpecimens {
    pub config: SpecimenConfig,
    pub cases: Vec<RenderCase>,
}

pub fn load(path: &Path) -> Result<LoadedSpecimens, Error> {
    let bytes = fs::read(path).map_err(|e| fail(format!("cannot read specimen config: {e}")))?;
    let mut config: SpecimenConfig = serde_json::from_slice(&bytes)
        .map_err(|e| fail(format!("invalid specimen config: {e}")))?;
    let cases = config.resolve(path.parent().unwrap_or(Path::new(".")))?;
    config.samples = config.resolved_samples()?;
    config.cards = None;
    Ok(LoadedSpecimens { config, cases })
}

fn identities<'a>(
    ids: impl Iterator<Item = &'a str>,
    what: &str,
) -> Result<BTreeSet<&'a str>, Error> {
    let mut found = BTreeSet::new();
    for id in ids {
        if id.is_empty()
            || id.len() > 128
            || !id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
            || !found.insert(id)
        {
            return Err(fail(format!("invalid or duplicate {what} ID {id:?}")));
        }
    }
    if found.is_empty() {
        return Err(fail(format!("{what} definitions must be nonempty")));
    }
    Ok(found)
}

fn selected(ids: &[String], known: &BTreeSet<&str>, what: &str) -> Result<(), Error> {
    let unique = identities(ids.iter().map(String::as_str), what)?;
    if let Some(id) = unique.iter().find(|id| !known.contains(**id)) {
        return Err(fail(format!("unknown {what} ID {id:?}")));
    }
    Ok(())
}

fn sizes_valid(
    sizes: &[SizeSelection],
    variants: &BTreeSet<&str>,
    profiles: &BTreeSet<&str>,
) -> Result<(), Error> {
    if sizes.is_empty() {
        return Err(fail("size selections must be nonempty"));
    }
    let mut seen = BTreeSet::new();
    for size in sizes {
        let px = match size {
            SizeSelection::Size(px) => *px,
            SizeSelection::Overrides(overrides) => {
                if let Some(ids) = &overrides.variants {
                    selected(ids, variants, "variant")?;
                }
                if let Some(ids) = &overrides.profiles {
                    selected(ids, profiles, "profile")?;
                }
                overrides.size_px
            }
        };
        if !px.is_finite() || !(1.0..=512.0).contains(&px) || !seen.insert(px.to_bits()) {
            return Err(fail(format!("invalid or duplicate size {px}")));
        }
    }
    Ok(())
}

fn validate_variants(variants: &[Variant]) -> Result<(), Error> {
    for variant in variants {
        if (variant.kind == VariantKind::Reference)
            != (variant.renderer() == RendererRole::Reference)
        {
            return Err(fail("reference package kind and renderer role must agree"));
        }
        if variant.renderer() == RendererRole::Baseline
            && (variant.version.as_deref() != Some(crate::baseline::VERSION)
                || variant.extensions != crate::baseline::EXTENSIONS_DIAGONAL_01)
        {
            return Err(fail(
                "baseline must identify the legacy version and fitting policy",
            ));
        }
        // Validate the effective route, including roleless iterations.
        // `none` remains the explicit upstream-reference bypass.
        if variant.renderer() == RendererRole::Candidate
            && ![
                crate::reference::EXTENSIONS_NONE,
                crate::stem_fitting::EXTENSIONS_FONT_HINTS_FIRST,
                crate::stem_fitting::EXTENSIONS_MONO_WIDTH_01,
            ]
            .contains(&variant.extensions.as_str())
        {
            return Err(fail(
                "candidate requires extensions none, font-hints-01 or mono-width-01",
            ));
        }
        if ![
            "none",
            "diagonal-01",
            crate::stem_fitting::EXTENSIONS_FONT_HINTS_FIRST,
            crate::stem_fitting::EXTENSIONS_MONO_WIDTH_01,
        ]
        .contains(&variant.extensions.as_str())
            || !(variant.hinting == Hinting::Auto
                || (variant.renderer() == RendererRole::Candidate
                    && variant.extensions == crate::stem_fitting::EXTENSIONS_FONT_HINTS_FIRST
                    && variant.hinting == Hinting::AutoFallback))
        {
            return Err(fail("specimen variants support automatic fitting with extensions none, diagonal-01, font-hints-01 or mono-width-01"));
        }
        if variant.kind == VariantKind::Reference && variant.extensions != "none" {
            return Err(fail("reference variants require extensions none"));
        }
        match variant.kind {
            VariantKind::Reference if variant.version.is_some() => {
                return Err(fail("reference version must be null"))
            }
            VariantKind::Iteration
                if variant.version.as_ref().is_none_or(|v| v.trim().is_empty()) =>
            {
                return Err(fail("iteration requires a nonempty version"))
            }
            _ => {}
        }
    }
    Ok(())
}

fn expand_family_cases(
    family: &Family,
    defaults: &Selection,
    variants: &BTreeSet<&str>,
    profiles: &BTreeSet<&str>,
    config_dir: &Path,
) -> Result<Vec<RenderCase>, Error> {
    let sizes = family.sizes.as_ref().unwrap_or(&defaults.sizes);
    let family_variants = family.variants.as_ref().unwrap_or(&defaults.variants);
    let family_profiles = family.profiles.as_ref().unwrap_or(&defaults.profiles);
    sizes_valid(sizes, variants, profiles)?;
    selected(family_variants, variants, "variant")?;
    selected(family_profiles, profiles, "profile")?;
    let mut cases = Vec::new();
    for size in sizes {
        let (px, chosen_variants, chosen_profiles) = match size {
            SizeSelection::Size(px) => (*px, family_variants, family_profiles),
            SizeSelection::Overrides(overrides) => (
                overrides.size_px,
                overrides.variants.as_ref().unwrap_or(family_variants),
                overrides.profiles.as_ref().unwrap_or(family_profiles),
            ),
        };
        let axes = family
            .axes
            .iter()
            .map(|(tag, value)| {
                (
                    tag.clone(),
                    match value {
                        AxisValue::Fixed(value) => *value,
                        AxisValue::Binding(AxisBinding::SizePx) => px,
                    },
                )
            })
            .collect::<BTreeMap<_, _>>();
        for variant in chosen_variants {
            for profile in chosen_profiles {
                cases.push(RenderCase {
                    family_id: family.id.clone(),
                    font: config_dir.join(&family.font),
                    size_px: px,
                    axes: axes.clone(),
                    variant: variant.clone(),
                    profile: profile.clone(),
                });
            }
        }
    }
    Ok(cases)
}

impl SpecimenConfig {
    pub fn latest_variant(&self) -> Result<&str, Error> {
        crate::preview_selection::select_roles(self.variants.iter().map(|variant| {
            (
                variant.id.as_str(),
                variant.version.as_deref(),
                variant.renderer,
            )
        }))
        .map(|(latest, _)| latest)
    }

    fn resolved_samples(&self) -> Result<Vec<Sample>, Error> {
        let Some(cards) = &self.cards else {
            return Ok(self.samples.clone());
        };
        if !self.samples.is_empty() {
            return Err(fail("configure either cards or legacy samples, not both"));
        }
        for card in cards {
            if ["coverage", "changed-symbols"].contains(&card.id.as_str())
                || ["Character coverage", "Changed symbols"].contains(&card.title.trim())
            {
                return Err(fail(
                    "Character coverage and Changed symbols are built-in cards",
                ));
            }
        }
        let mut samples: Vec<_> = cards
            .iter()
            .map(|card| Sample {
                id: card.id.clone(),
                label: card.title.clone(),
                text: card.content.clone(),
            })
            .collect();
        let mut rows = [String::new(), String::new(), String::new(), String::new()];
        let mut seen = BTreeSet::new();
        for ch in self.characters.chars().filter(|ch| seen.insert(*ch)) {
            let row = if ch.is_ascii_uppercase() {
                0
            } else if ch.is_ascii_lowercase() {
                1
            } else if ch.is_ascii_digit() {
                2
            } else {
                3
            };
            rows[row].push(ch);
        }
        let symbols = rows[3].clone();
        if !rows[2].is_empty() && !symbols.is_empty() {
            rows[2].push(' ');
        }
        rows[2].push_str(&symbols);
        samples.push(Sample {
            id: "coverage".into(),
            label: "Character coverage".into(),
            text: rows[..3]
                .iter()
                .filter(|row| !row.is_empty())
                .cloned()
                .collect::<Vec<_>>()
                .join("\n"),
        });
        Ok(samples)
    }

    pub fn resolve(&self, config_dir: &Path) -> Result<Vec<RenderCase>, Error> {
        if self.schema_version != "specimen-config-v1" {
            return Err(fail("unsupported specimen config schema"));
        }
        let characters: BTreeSet<_> = self.characters.chars().collect();
        if characters.is_empty()
            || characters.len() > 1024
            || characters.contains(&' ')
            || characters.iter().any(|ch| ch.is_control())
        {
            return Err(fail("characters must contain 1–1024 drawable scalars; space is a separate layout metric"));
        }
        let samples = self.resolved_samples()?;
        identities(samples.iter().map(|sample| sample.id.as_str()), "sample")?;
        for sample in &samples {
            if sample.label.trim().is_empty()
                || sample.text.trim().is_empty()
                || sample.text.chars().count() > 4096
                || sample.text.lines().count() > 128
                || sample
                    .text
                    .chars()
                    .any(|ch| ch != ' ' && ch != '\n' && !characters.contains(&ch))
            {
                return Err(fail(format!(
                    "invalid text or repertoire for sample {:?}",
                    sample.id
                )));
            }
        }
        let variants = identities(self.variants.iter().map(|v| v.id.as_str()), "variant")?;
        let profiles = identities(self.profiles.iter().map(|p| p.id.as_str()), "profile")?;
        identities(self.families.iter().map(|f| f.id.as_str()), "family")?;
        let latest = self.latest_variant()?;
        validate_variants(&self.variants)?;
        for profile in &self.profiles {
            let expected = match profile.id.as_str() {
                "mono_1bit" => 1,
                "gray_3bit" => 3,
                _ => return Err(fail(format!("unsupported profile {:?}", profile.id))),
            };
            if profile.output_bits != expected
                || profile.mono_threshold == 0
                || !profile.gray_gamma.is_finite()
                || profile.gray_gamma <= 0.0
            {
                return Err(fail(format!(
                    "invalid settings for profile {:?}",
                    profile.id
                )));
            }
        }
        selected(&self.defaults.variants, &variants, "variant")?;
        selected(&self.defaults.profiles, &profiles, "profile")?;
        sizes_valid(&self.defaults.sizes, &variants, &profiles)?;
        let mut cases = Vec::new();
        for family in &self.families {
            if family.name.trim().is_empty()
                || family.font.as_os_str().is_empty()
                || family.provenance.source.trim().is_empty()
                || family.provenance.license.trim().is_empty()
                || family.provenance.expected_sha256.len() != 64
                || !family
                    .provenance
                    .expected_sha256
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                return Err(fail(format!(
                    "invalid source metadata for family {:?}",
                    family.id
                )));
            }
            for (tag, value) in &family.axes {
                if tag.len() != 4
                    || !tag.is_ascii()
                    || matches!(value, AxisValue::Fixed(v) if !v.is_finite())
                {
                    return Err(fail(format!(
                        "invalid axis {tag:?} for family {:?}",
                        family.id
                    )));
                }
            }
            cases.extend(expand_family_cases(
                family,
                &self.defaults,
                &variants,
                &profiles,
                config_dir,
            )?);
        }
        if !cases.iter().any(|case| case.variant == latest) {
            return Err(fail("latest variant must select at least one render case"));
        }
        let (_, previous) =
            crate::preview_selection::select_roles(self.variants.iter().map(|variant| {
                (
                    variant.id.as_str(),
                    variant.version.as_deref(),
                    variant.renderer,
                )
            }))?;
        if previous.is_some_and(|previous| !cases.iter().any(|case| case.variant == previous)) {
            return Err(fail(
                "comparison baseline must select at least one render case",
            ));
        }
        if let Some(policy_path) = &self.preview_policy {
            validate_preview_policy(&config_dir.join(policy_path), &cases)?;
        }
        Ok(cases)
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PreviewPolicy {
    schema_version: String,
    families: BTreeMap<String, Vec<f32>>,
}

// Project scope constraint, established by the user: diagnostic sweeps must not
// expand or shrink the ordinary web preview. Keep its agreed sizes independent
// of renderer configuration and check effective cases, including overrides.
fn validate_preview_policy(path: &Path, cases: &[RenderCase]) -> Result<(), Error> {
    let bytes = fs::read(path).map_err(|e| {
        fail(format!(
            "cannot read preview policy {}: {e}",
            path.display()
        ))
    })?;
    let policy: PreviewPolicy =
        serde_json::from_slice(&bytes).map_err(|e| fail(format!("invalid preview policy: {e}")))?;
    if policy.schema_version != "preview-policy-v1" {
        return Err(fail("unsupported preview policy schema"));
    }
    let families = identities(policy.families.keys().map(String::as_str), "preview family")?;
    let actual_families: BTreeSet<_> = cases.iter().map(|case| case.family_id.as_str()).collect();
    if families != actual_families {
        return Err(fail(
            "preview policy mismatch: configured families differ from the agreed preview",
        ));
    }
    let mut expected = BTreeMap::new();
    for (family, sizes) in &policy.families {
        let set: BTreeSet<_> = sizes.iter().map(|size| size.to_bits()).collect();
        if sizes.is_empty()
            || set.len() != sizes.len()
            || sizes
                .iter()
                .any(|size| !size.is_finite() || !(1.0..=512.0).contains(size))
        {
            return Err(fail(format!("invalid preview policy sizes for {family}")));
        }
        expected.insert(family.as_str(), set);
    }
    let mut effective: BTreeMap<_, BTreeSet<_>> = BTreeMap::new();
    for case in cases {
        effective
            .entry((
                case.family_id.as_str(),
                case.variant.as_str(),
                case.profile.as_str(),
            ))
            .or_default()
            .insert(case.size_px.to_bits());
    }
    for ((family, variant, profile), sizes) in effective {
        if sizes != expected[family] {
            let actual: Vec<_> = sizes.into_iter().map(f32::from_bits).collect();
            return Err(fail(format!(
                "preview policy mismatch for {family}, {variant}, {profile}: expected {:?} px, got {actual:?} px; keep diagnostic sizes in an isolated sweep",
                policy.families[family]
            )));
        }
    }
    Ok(())
}
