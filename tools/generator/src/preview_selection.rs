//! Explicit renderer roles compare candidate with legacy baseline, or baseline
//! with reference. Roleless historical manifests retain their original policy.
use crate::renderer::RendererRole;
use crate::{fail, Error};
use std::collections::BTreeSet;

/// Explicit roles compare a working candidate with the legacy baseline.
/// With no newer candidate, the legacy baseline is shown against reference.
/// Older manifests without roles retain their historical selection policy.
pub fn select_roles<'a>(
    variants: impl IntoIterator<Item = (&'a str, Option<&'a str>, Option<RendererRole>)>,
) -> Result<(&'a str, Option<&'a str>), Error> {
    let variants: Vec<_> = variants.into_iter().collect();
    let mut versions = BTreeSet::new();
    let mut reference = None;
    for &(id, label, _) in &variants {
        if let Some(label) = label {
            if !versions.insert(version(label)?) {
                return Err(fail("duplicate revision/iteration version"));
            }
        } else if reference.replace(id).is_some() {
            return Err(fail("preview requires a unique reference variant"));
        }
    }
    let mut baseline = None;
    for &(id, label, role) in &variants {
        if role == Some(RendererRole::Baseline) {
            let key = version(label.ok_or_else(|| fail("baseline requires a version"))?)?;
            if baseline.is_none_or(|(previous, _)| key > previous) {
                baseline = Some((key, id));
            }
        }
    }
    let Some((baseline_key, baseline_id)) = baseline else {
        if variants.iter().any(|(_, _, role)| role.is_some())
            && variants.iter().any(|(_, label, _)| label.is_some())
        {
            return Err(fail("explicit working preview requires a legacy baseline"));
        }
        return select(variants.iter().map(|(id, version, _)| (*id, *version)));
    };
    let mut candidate = None;
    for &(id, label, role) in &variants {
        if role == Some(RendererRole::Candidate) {
            let key = version(label.ok_or_else(|| fail("candidate requires a version"))?)?;
            if key > baseline_key && candidate.is_none_or(|(previous, _)| key > previous) {
                candidate = Some((key, id));
            }
        }
    }
    if let Some((_, candidate_id)) = candidate {
        return Ok((candidate_id, Some(baseline_id)));
    }
    let reference = variants
        .iter()
        .find(|(_, label, _)| label.is_none())
        .map(|(id, _, _)| *id)
        .ok_or_else(|| fail("baseline preview requires reference"))?;
    Ok((baseline_id, Some(reference)))
}

pub fn version(value: &str) -> Result<(u32, u32), Error> {
    let (revision, iteration) = value
        .split_once('.')
        .ok_or_else(|| fail("iteration version must be numeric revision.iteration"))?;
    let number = |part: &str| -> Result<u32, Error> {
        if part.is_empty() || !part.bytes().all(|b| b.is_ascii_digit()) {
            return Err(fail("iteration version must be numeric revision.iteration"));
        }
        part.parse::<u32>()
            .ok()
            .filter(|n| *n > 0)
            .ok_or_else(|| fail("revision and iteration must be positive 32-bit numbers"))
    };
    Ok((number(revision)?, number(iteration)?))
}

pub fn select<'a>(
    variants: impl IntoIterator<Item = (&'a str, Option<&'a str>)>,
) -> Result<(&'a str, Option<&'a str>), Error> {
    let mut reference = None;
    let mut iterations = Vec::new();
    let mut versions = BTreeSet::new();
    for (id, label) in variants {
        if let Some(label) = label {
            let key = version(label)?;
            if !versions.insert(key) {
                return Err(fail("duplicate revision/iteration version"));
            }
            iterations.push((key, id));
        } else if reference.replace(id).is_some() {
            return Err(fail("preview requires a unique reference variant"));
        }
    }
    iterations.sort_unstable();
    let Some(&(current, id)) = iterations.last() else {
        return Ok((reference.ok_or_else(|| fail("no preview variants"))?, None));
    };
    let previous = iterations
        .iter()
        .rev()
        .find(|(key, _)| key.0 < current.0)
        .map(|(_, id)| *id)
        .or(reference)
        .ok_or_else(|| fail("first revision requires reference for comparison"))?;
    Ok((id, Some(previous)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roles_keep_approved_baseline_across_candidate_versions() {
        let approved = [
            ("ref", None, Some(RendererRole::Reference)),
            ("approved", Some("001.01"), Some(RendererRole::Baseline)),
        ];
        assert_eq!(select_roles(approved).unwrap(), ("approved", Some("ref")));
        for candidate in ["001.02", "002.01", "100.500"] {
            assert_eq!(
                select_roles(approved.into_iter().chain([(
                    "working",
                    Some(candidate),
                    Some(RendererRole::Candidate)
                )]))
                .unwrap(),
                ("working", Some("approved"))
            );
        }
        assert_eq!(
            select_roles([
                ("approved", Some("001.01"), Some(RendererRole::Baseline)),
                ("working", Some("001.02"), Some(RendererRole::Candidate)),
            ])
            .unwrap(),
            ("working", Some("approved"))
        );
        assert!(select_roles([
            ("ref", None, Some(RendererRole::Reference)),
            ("working", Some("001.02"), Some(RendererRole::Candidate)),
        ])
        .is_err());
    }

    #[test]
    fn latest_iteration_in_first_revision_compares_to_reference() {
        assert_eq!(
            select([
                ("new", Some("001.02")),
                ("ref", None),
                ("old", Some("001.01"))
            ])
            .unwrap(),
            ("new", Some("ref"))
        );
    }

    #[test]
    fn revision_and_iteration_are_ordered_numerically() {
        assert_eq!(
            select([
                ("ref", None),
                ("a", Some("9.10")),
                ("b", Some("9.2")),
                ("c", Some("10.2")),
                ("d", Some("10.10"))
            ])
            .unwrap(),
            ("d", Some("a"))
        );
    }

    #[test]
    fn invalid_or_ambiguous_versions_are_rejected() {
        for bad in ["iteration-1", "1.2.3", "0.1", "1.0", "1.-1", "4294967296.1"] {
            assert!(version(bad).is_err());
        }
        assert!(select([("ref", None), ("a", Some("001.01")), ("b", Some("1.1"))]).is_err());
        assert!(select([("a", None), ("b", None)]).is_err());
    }
}
