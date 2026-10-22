//! Completed pure-fit reuse across requests of one immutable loaded font.
//!
//! FreeType's cache model bounds retained glyph data and evicts least-recently
//! used entries: https://freetype.org/freetype2/docs/reference/ft2-cache_subsystem.html
//! This adaptation keys every argument of approved::fit by exact floating bits.
//! It never reuses validation, source capture, rasterization or layout.

use super::{approved, Reference};
use crate::{fitting_source::SourceOutline, probe::FittedCommand, Error};
use sha2::{Digest, Sha256};
use std::collections::VecDeque;

const PAYLOAD_LIMIT: usize = 2 * 1024 * 1024;
const ENTRY_LIMIT: usize = 256;

#[derive(Clone)]
pub(crate) struct Outcome {
    pub commands: Vec<FittedCommand>,
    pub applied: bool,
    pub reason: String,
}

struct Entry {
    hash: [u8; 32],
    key: Box<[u8]>,
    commands: Box<[FittedCommand]>,
    reason: Box<str>,
    applied: bool,
}

impl Entry {
    fn payload(&self) -> usize {
        self.key.len() + std::mem::size_of_val(&*self.commands) + self.reason.len()
    }

    fn outcome(&self) -> Outcome {
        Outcome {
            commands: self.commands.to_vec(),
            applied: self.applied,
            reason: self.reason.to_string(),
        }
    }
}

pub(crate) struct FitCache {
    entries: VecDeque<Entry>,
    bytes: usize,
    limit: usize,
    #[cfg(test)]
    pub hits: usize,
    #[cfg(test)]
    pub misses: usize,
    #[cfg(test)]
    pub evictions: usize,
}

impl Default for FitCache {
    fn default() -> Self {
        Self {
            entries: VecDeque::new(),
            bytes: 0,
            limit: PAYLOAD_LIMIT,
            #[cfg(test)]
            hits: 0,
            #[cfg(test)]
            misses: 0,
            #[cfg(test)]
            evictions: 0,
        }
    }
}

impl FitCache {
    fn get_or_compute(
        &mut self,
        key: Vec<u8>,
        compute: impl FnOnce() -> Result<Outcome, Error>,
    ) -> Result<Outcome, Error> {
        if key.len() > self.limit {
            return compute();
        }
        let hash: [u8; 32] = Sha256::digest(&key).into();
        // Hashing accelerates lookup; full equality, not the digest, authorizes reuse.
        if let Some(i) = self
            .entries
            .iter()
            .position(|entry| entry.hash == hash && *entry.key == key)
        {
            let entry = self.entries.remove(i).unwrap();
            let outcome = entry.outcome();
            self.entries.push_back(entry);
            #[cfg(test)]
            {
                self.hits += 1;
            }
            return Ok(outcome);
        }
        #[cfg(test)]
        {
            self.misses += 1;
        }
        // Errors are never retained; successful abstentions are pure outcomes too.
        let value = compute()?;
        let Some(payload) = value
            .commands
            .len()
            .checked_mul(std::mem::size_of::<FittedCommand>())
            .and_then(|n| n.checked_add(key.len()))
            .and_then(|n| n.checked_add(value.reason.len()))
        else {
            return Ok(value);
        };
        if payload > self.limit {
            return Ok(value);
        }
        while self.bytes + payload > self.limit || self.entries.len() >= ENTRY_LIMIT {
            let Some(old) = self.entries.pop_front() else {
                break;
            };
            self.bytes -= old.payload();
            #[cfg(test)]
            {
                self.evictions += 1;
            }
        }
        self.entries.push_back(Entry {
            hash,
            key: key.into_boxed_slice(),
            commands: value.commands.clone().into_boxed_slice(),
            reason: value.reason.clone().into_boxed_str(),
            applied: value.applied,
        });
        self.bytes += payload;
        Ok(value)
    }

    pub(crate) fn fit(
        &mut self,
        raw: Option<&SourceOutline>,
        source: &[FittedCommand],
        upstream: &[FittedCommand],
        size_px: f64,
        reference: &Reference,
        native_axes: [bool; 2],
    ) -> Result<Outcome, Error> {
        let compute = || fit(raw, source, upstream, size_px, reference, native_axes);
        let Some(key) = key(raw, source, upstream, size_px, reference, native_axes) else {
            return compute();
        };
        self.get_or_compute(key, compute)
    }
}

pub(crate) fn fit(
    raw: Option<&SourceOutline>,
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<Outcome, Error> {
    let value = approved::fit(raw, source, upstream, size_px, reference, native_axes)?;
    // Detailed fit diagnostics were already discarded by the delivery caller.
    Ok(Outcome {
        commands: value.commands,
        applied: value.applied,
        reason: value.reason,
    })
}

fn key(
    raw: Option<&SourceOutline>,
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Option<Vec<u8>> {
    // FittedCommand's serializer includes every f32 bit pattern. Convert all
    // other floats explicitly: JSON numeric formatting alone is not an exact
    // identity for exceptional values or signed zero. Keep ordering and None.
    let bits = |points: &[[f64; 2]]| {
        points
            .iter()
            .map(|p| [p[0].to_bits(), p[1].to_bits()])
            .collect::<Vec<_>>()
    };
    let raw = raw.map(|r| (bits(&r.oncurve), bits(&r.offcurve), &r.contours));
    let anchors = reference
        .anchors
        .iter()
        .map(|a| {
            (
                a.source_width.to_bits(),
                a.fitted_width.to_bits(),
                a.rel.to_bits(),
                a.length.to_bits(),
                a.tangent.map(f64::to_bits),
                &a.source_ids,
            )
        })
        .collect::<Vec<_>>();
    serde_json::to_vec(&(
        raw,
        source,
        upstream,
        size_px.to_bits(),
        native_axes,
        anchors,
        reference.size_px.to_bits(),
        reference.records,
        reference.n_anchors,
        reference.rel_min.map(f64::to_bits),
        reference.rel_max.map(f64::to_bits),
        &reference.notes,
    ))
    .ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn outcome() -> Outcome {
        Outcome {
            commands: vec![FittedCommand::Close],
            applied: false,
            reason: "unsupported".into(),
        }
    }

    #[test]
    fn repeated_abstentions_hit_but_errors_retry() {
        let mut cache = FitCache::default();
        cache.get_or_compute(vec![1], || Ok(outcome())).unwrap();
        assert!(
            !cache
                .get_or_compute(vec![1], || panic!("cache miss"))
                .unwrap()
                .applied
        );
        for _ in 0..2 {
            assert!(cache
                .get_or_compute(vec![2], || Err(Error("test".into())))
                .is_err());
        }
        assert_eq!((cache.hits, cache.misses), (1, 3));
    }

    #[test]
    fn byte_limit_evicts_least_recent_and_oversize_bypasses() {
        let mut cache = FitCache::default();
        let size = 1 + std::mem::size_of::<FittedCommand>() + outcome().reason.len();
        cache.limit = 2 * size;
        for k in [1, 2, 1, 3] {
            cache.get_or_compute(vec![k], || Ok(outcome())).unwrap();
        }
        assert_eq!((cache.hits, cache.evictions, cache.bytes), (1, 1, 2 * size));
        assert_eq!(cache.entries[0].key.as_ref(), &[1]);
        assert_eq!(cache.entries[1].key.as_ref(), &[3]);
        cache
            .get_or_compute(vec![0; cache.limit + 1], || Ok(outcome()))
            .unwrap();
        assert_eq!((cache.entries.len(), cache.bytes), (2, 2 * size));
    }

    #[test]
    fn entry_count_is_bounded_with_tiny_outcomes() {
        let mut cache = FitCache::default();
        for i in 0..ENTRY_LIMIT + 10 {
            cache
                .get_or_compute(i.to_le_bytes().to_vec(), || Ok(outcome()))
                .unwrap();
        }
        assert_eq!((cache.entries.len(), cache.evictions), (ENTRY_LIMIT, 10));
    }

    #[test]
    fn key_preserves_float_bits_and_every_geometric_input() {
        let empty = SourceOutline {
            oncurve: vec![[0., 0.]],
            offcurve: vec![],
            contours: vec![],
        };
        let reference = Reference {
            anchors: vec![],
            size_px: 16.,
            records: 0,
            n_anchors: 0,
            rel_min: None,
            rel_max: None,
            notes: vec![],
        };
        let make =
            |raw: Option<&SourceOutline>, commands: &[FittedCommand], size, r: &Reference, axes| {
                key(raw, commands, &[], size, r, axes).unwrap()
            };
        let base = make(Some(&empty), &[], 16., &reference, [false; 2]);
        let mut changed = empty.clone();
        changed.oncurve[0][0] = -0.;
        assert_ne!(base, make(Some(&changed), &[], 16., &reference, [false; 2]));
        assert_ne!(base, make(None, &[], 16., &reference, [false; 2]));
        assert_ne!(
            base,
            make(
                Some(&empty),
                &[],
                f64::from_bits(16_f64.to_bits() + 1),
                &reference,
                [false; 2]
            )
        );
        assert_ne!(
            base,
            make(Some(&empty), &[], 16., &reference, [true, false])
        );
        let mut r = reference.clone();
        r.rel_min = Some(0.);
        assert_ne!(base, make(Some(&empty), &[], 16., &r, [false; 2]));
        let a = make(
            None,
            &[FittedCommand::MoveTo(0., 0.)],
            16.,
            &reference,
            [false; 2],
        );
        let b = make(
            None,
            &[FittedCommand::MoveTo(-0., 0.)],
            16.,
            &reference,
            [false; 2],
        );
        assert_ne!(a, b);
    }
}
