//! Project preview policy: newest revision/iteration versus the preceding
//! revision's newest iteration, falling back to reference for the first revision.
use crate::{fail, Error};
use std::collections::BTreeSet;

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
