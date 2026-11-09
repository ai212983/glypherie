//! Session engine: cached banks/kernels, per-glyph field LRU, energies.
//!
//! Cache identity includes the FULL frame (dataset, codepoint, capture,
//! model params, geometry bytes) plus the field allocation identity —
//! never the codepoint alone. Same-input rerun is repeatable within the
//! stated field-path bounds; cross-padding agreement is a measured bound.

use std::collections::{HashMap, VecDeque};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use crate::fft::Conv;
use crate::fields::{
    build_oriented_kernels, build_v1_bank, glyph_fields, GlyphFields, OrientedKernels, V1Banks,
};
use crate::local_energy::{
    confidence_local, contribution_map_local as contribution_map_local_fn, local_energy_maps,
    score_step_local, LocalAbstain,
};
use crate::params::{
    EngineParams, ScoreParams, FROZEN_NORMALIZATION_RADIUS, LOCAL_ENERGY_MODEL_IDENTITY,
    MODEL_IDENTITY,
};
use crate::score::{
    contact_counts, contribution_map, facing_matrix, score_step, self_energy, tie_set,
    union_canvas, validate_score_request, Strength,
};
use crate::EngineError;

const GLYPH_LRU_CAP: usize = 32;
const RAW_DIM_CAP: usize = 1024;

/// Soft owned-payload target: 256 MiB of cache-owned glyph bytes (field
/// lattices, covers, self-energies, materialized local-energy maps).
/// Soft: the keep-floor below may hold more; this is NOT an RSS or
/// WASM-linear-memory cap, and no memory is returned to the OS on eviction.
const CACHE_PAYLOAD_TARGET: u64 = 256 * 1024 * 1024;
/// Keep-floor: eviction for payload never drops below the baseline LRU32
/// working set, so the resident set always includes it
/// (strictly-at-least-baseline inclusion).
const CACHE_KEEP_FLOOR: usize = GLYPH_LRU_CAP;
/// Count ceiling: non-binding DoS rail (the byte target always binds first
/// at every validated guard: the smallest entries are ~0.75 MB, so 512 of
/// them exceed any budget before this ceiling matters).
const CACHE_COUNT_CEILING: usize = 512;

fn fnv_bits(data: &[f64]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for v in data {
        h ^= v.to_bits();
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

fn params_hash(params: &EngineParams) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    let mut mix = |bits: u64| {
        h ^= bits;
        h = h.wrapping_mul(0x100000001b3);
    };
    mix(params.q.to_bits());
    mix(params.kappa.to_bits());
    for s in params.sigmas.iter() {
        mix(s.to_bits());
    }
    for w in params.weights.iter() {
        mix(w.to_bits());
    }
    mix(params.radius as u64);
    mix(params.eps.to_bits());
    mix(params.n_v1 as u64);
    mix(params.n_directed as u64);
    mix(MODEL_IDENTITY.len() as u64);
    for b in MODEL_IDENTITY.bytes() {
        mix(b as u64);
    }
    mix(LOCAL_ENERGY_MODEL_IDENTITY.len() as u64);
    for b in LOCAL_ENERGY_MODEL_IDENTITY.bytes() {
        mix(b as u64);
    }
    h
}

fn hash_str(s: &str) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in s.bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

struct GlyphEntry {
    capture_hash: u64,
    params_hash: u64,
    geom_hash: u64,
    w: usize,
    h: usize,
    left: f64,
    top: f64,
    cover: Vec<f64>,
    fields: Arc<GlyphFields>,
    energy_nb: Vec<f64>,
    energy_ms: Vec<f64>,
    /// Class-L local-energy maps keyed `(strength_code, normalization_radius)`.
    /// They live inside the entry and die with it, so a field rebuild
    /// structurally invalidates them (allocation identity); the key covers
    /// every effective normalizer param. Notebook = 0, manuscript = 1.
    local_energy: HashMap<(u8, u32), Arc<Vec<Vec<f64>>>>,
}

fn strength_code(s: Strength) -> u8 {
    match s {
        Strength::Notebook => 0,
        Strength::Manuscript => 1,
    }
}

/// Cache-owned live payload bytes of one glyph entry: cover, every field
/// lattice array (all nested channel/scale lengths), both self-energies,
/// and each materialized local-energy map. Measured in Vec lengths, not
/// capacity (overallocation excluded); HashMap/Vec structural overhead
/// excluded (KB-scale against MB entries). The single `Arc<GlyphFields>`
/// and each EL `Arc` are counted exactly once per entry; transient clones
/// held by in-flight calls are NOT cache-owned and never counted here.
fn entry_payload_bytes(e: &GlyphEntry) -> u64 {
    let mut b = (e.cover.len() + e.energy_nb.len() + e.energy_ms.len()) as u64 * 8;
    let f = &e.fields;
    for scale in f.c_per_scale.iter() {
        for ori in scale.iter() {
            b += ori.len() as u64 * 8;
        }
    }
    for arr in f.t_combined.iter() {
        b += arr.len() as u64 * 8;
    }
    for arr in f
        .u1
        .iter()
        .chain(f.u2.iter())
        .chain(f.distance.iter())
        .chain(f.conf_nb.iter())
        .chain(f.arc.iter())
    {
        b += arr.len() as u64 * 8;
    }
    // Vec<bool> is byte-per-element (not bitpacked).
    for m in f.supported.iter() {
        b += m.len() as u64;
    }
    for maps in e.local_energy.values() {
        for ch in maps.iter() {
            b += ch.len() as u64 * 8;
        }
    }
    b
}

/// Point-in-time cache resource readout (observational only; never enters
/// params_hash, model identity, tables, or score outputs).
#[derive(Debug, Clone, Copy)]
pub struct CacheStats {
    pub glyphs: usize,
    pub lru: usize,
    pub payload_bytes: u64,
    pub builds_fields: u64,
    pub builds_el: u64,
    pub evictions: u64,
}

/// One scored candidate step.
#[derive(Debug, Clone)]
pub struct StepRecord {
    pub step: i64,
    pub delta: i64,
    pub valid: bool,
    pub reason: Option<String>,
    pub g2: Option<f64>,
    pub raw: Option<f64>,
    pub floor_share: Option<f64>,
    pub raw_floor_share: Option<f64>,
    pub both_supported_pairpx: u64,
    pub abstain: bool,
    pub faces: usize,
    pub corners: usize,
}

/// Pair result with TIE-v2 selection.
#[derive(Debug, Clone)]
pub struct PairResult {
    pub steps: Vec<StepRecord>,
    /// Minimizing step values (TIE-v2 set over supported steps only),
    /// empty when no supported step or no C*.
    pub minimizing: Vec<i64>,
    /// Single pick: global-min then lowest step index; metric on fallback.
    pub chosen: i64,
    pub fallback: bool,
    /// Why the metric was retained (`occupied_cell_overlap`,
    /// `no_shared_support`, or `zero_local_evidence`); `None` when a
    /// supported step was chosen or no target was given.
    pub fallback_reason: Option<String>,
}

/// One Class-L scored candidate step.
#[derive(Debug, Clone)]
pub struct LocalStepRecord {
    pub step: i64,
    pub delta: i64,
    pub valid: bool,
    pub reason: Option<String>,
    pub gl: Option<f64>,
    pub both_supported_pairpx: u64,
    pub weak_normalized_share: Option<f64>,
    pub max_term_cosine: Option<f64>,
    pub abstain: bool,
    /// `no_shared_support` or `zero_local_evidence`; `None` when eligible.
    pub abstain_reason: Option<String>,
    pub skipped_nonpositive: u64,
    pub conditioning_shortfall: f64,
    pub honest_bound: Option<f64>,
    pub faces: usize,
    pub corners: usize,
}

/// Class-L pair result with TIE-v2 selection (same shape as `PairResult`).
#[derive(Debug, Clone)]
pub struct LocalPairResult {
    pub steps: Vec<LocalStepRecord>,
    pub minimizing: Vec<i64>,
    pub chosen: i64,
    pub fallback: bool,
    /// `occupied_cell_overlap`, `no_shared_support`, or the intentional
    /// new rule `zero_local_evidence`; `None` when chosen or no target.
    pub fallback_reason: Option<String>,
}

/// Geometry-derived search domain for one pair: every whole-pixel step in
/// `[lo, hi]` is evaluated in ascending order. `lo` keeps left-to-right
/// order from delivered ink extents; `hi` is the last step whose padded
/// field lattices can still share support.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SearchDomain {
    pub lo: i64,
    pub hi: i64,
}

/// Why a pair has no search domain: blank side, disjoint padded rows, or
/// no forward step (the padded lattices stop overlapping before the pen
/// can advance). All fall back to Source; none ever wins a placement.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NoDomain {
    Blank,
    DisjointRows,
    NoForwardStep,
}

/// Session engine owning banks, kernels, caches and the cancel flag.
pub struct Engine {
    params: EngineParams,
    params_hash: u64,
    banks: V1Banks,
    kernels: OrientedKernels,
    facing: Vec<Vec<f64>>,
    conv: Conv,
    glyphs: HashMap<(u64, u32), GlyphEntry>,
    lru: VecDeque<(u64, u32)>,
    cancel: Arc<AtomicBool>,
    /// Current cache-owned live payload bytes (sum of entry_payload_bytes).
    payload_bytes: u64,
    /// Cumulative field rebuilds (load_glyph returning true), per instance.
    builds_fields: u64,
    /// Cumulative local-energy materializations (cache misses only).
    builds_el: u64,
    /// Cumulative LRU evictions (each drops exactly one entry).
    evictions: u64,
    /// Active eviction policy; production values are the CACHE_* constants.
    /// Unit tests narrow these to avoid GB allocations; the shipped policy
    /// is fixed and never varies per caller.
    payload_target: u64,
    keep_floor: usize,
    count_ceiling: usize,
}

impl Engine {
    pub fn new(params: EngineParams) -> Result<Self, EngineError> {
        params.validate()?;
        let params_hash = params_hash(&params);
        let mut banks = Vec::with_capacity(params.sigmas.len());
        let mut halfwidths = Vec::with_capacity(params.sigmas.len());
        for s in params.sigmas.iter() {
            let (bank, hw) = build_v1_bank(*s, params.n_v1);
            banks.push(bank);
            halfwidths.push(hw);
        }
        let (h1, h2, mass1, mass2) =
            build_oriented_kernels(params.q, params.kappa, params.radius, params.n_directed);
        let taps = 2 * params.radius as usize + 1;
        let facing = facing_matrix(params.n_directed);
        Ok(Self {
            params,
            params_hash,
            banks: V1Banks { banks, halfwidths },
            kernels: OrientedKernels {
                h1,
                h2,
                mass1,
                mass2,
                taps,
            },
            facing,
            conv: Conv::new(),
            glyphs: HashMap::new(),
            lru: VecDeque::new(),
            cancel: Arc::new(AtomicBool::new(false)),
            payload_bytes: 0,
            builds_fields: 0,
            builds_el: 0,
            evictions: 0,
            payload_target: CACHE_PAYLOAD_TARGET,
            keep_floor: CACHE_KEEP_FLOOR,
            count_ceiling: CACHE_COUNT_CEILING,
        })
    }

    pub fn params(&self) -> &EngineParams {
        &self.params
    }

    pub fn params_hash(&self) -> u64 {
        self.params_hash
    }

    /// Signal cancellation for in-flight scoring loops. Buffers stay valid;
    /// in-flight calls return `Cancelled`. Use `clear_cancel` to resume.
    pub fn cancel(&self) {
        self.cancel.store(true, Ordering::Relaxed);
    }

    pub fn clear_cancel(&self) {
        self.cancel.store(false, Ordering::Relaxed);
    }

    fn touch(&mut self, key: (u64, u32)) {
        self.lru.retain(|k| *k != key);
        self.lru.push_back(key);
        self.enforce_budget();
    }

    /// Evict LRU-first while over the count ceiling, or over the soft
    /// payload target with more than the keep-floor resident. Recency
    /// semantics are unchanged (load-only touches, same insertion order),
    /// and eviction always removes the least-recently-loaded entry, so the
    /// resident set always includes the baseline's last-32 working set:
    /// with identical op history the policy can only retain MORE, never
    /// less, than LRU32 (inclusion proof: both keep the most recent loads;
    /// this policy additionally keeps up to the byte target / ceiling).
    /// A just-loaded pair is among the 2 most recent loads, hence always
    /// inside the keep-floor: score/map re-reads after EL growth cannot
    /// observe their own entries evicted. Oversized singles still build and
    /// evict everything else (the `len > 1` guard), never rejected.
    fn enforce_budget(&mut self) {
        while self.glyphs.len() > 1
            && (self.glyphs.len() > self.count_ceiling
                || (self.payload_bytes > self.payload_target
                    && self.glyphs.len() > self.keep_floor))
        {
            if let Some(old) = self.lru.pop_front() {
                if let Some(e) = self.glyphs.remove(&old) {
                    self.payload_bytes = self
                        .payload_bytes
                        .saturating_sub(entry_payload_bytes(&e));
                    self.evictions += 1;
                }
            } else {
                break;
            }
        }
    }

    /// Load (or reload on any identity/byte change) one glyph cover buffer.
    /// Returns true when fields were recomputed. Geometry beyond
    /// `RAW_DIM_CAP` or nonfinite cover errors; never silently clamps.
    #[allow(clippy::too_many_arguments)]
    pub fn load_glyph(
        &mut self,
        dataset: &str,
        capture_sha: &str,
        codepoint: u32,
        w: usize,
        h: usize,
        left: f64,
        top: f64,
        cover: &[f64],
    ) -> Result<bool, EngineError> {
        if w == 0 || h == 0 || w > RAW_DIM_CAP || h > RAW_DIM_CAP {
            return Err(EngineError::Invalid(format!(
                "glyph dims {w}x{h} exceed the {RAW_DIM_CAP} resource guard"
            )));
        }
        if cover.len() != w * h {
            return Err(EngineError::Invalid(format!(
                "cover length {} != {w}x{h}",
                cover.len()
            )));
        }
        if !left.is_finite() || !top.is_finite() {
            return Err(EngineError::Invalid(
                "glyph origin must be finite".to_string(),
            ));
        }
        let key = (hash_str(dataset), codepoint);
        let capture_hash = hash_str(capture_sha);
        let mut hasher_state = fnv_bits(cover);
        hasher_state ^= (w as u64).wrapping_mul(0x9e3779b97f4a7c15);
        hasher_state ^= (h as u64).wrapping_mul(0xbf58476d1ce4e5b9);
        hasher_state ^= left.to_bits();
        hasher_state ^= top.to_bits();
        let geom_hash = hasher_state;
        if let Some(entry) = self.glyphs.get(&key) {
            if entry.capture_hash == capture_hash
                && entry.params_hash == self.params_hash
                && entry.geom_hash == geom_hash
            {
                self.touch(key);
                return Ok(false);
            }
        }
        let fields = glyph_fields(
            cover,
            w,
            h,
            &self.params,
            &self.banks,
            &self.kernels,
            &mut self.conv,
            Some(&self.cancel),
        )?;
        let fields = Arc::new(fields);
        let energy_nb = self_energy(&fields, Strength::Notebook);
        let energy_ms = self_energy(&fields, Strength::Manuscript);
        // Replacement (identity/byte change) frees the old payload exactly
        // once; a fresh insert adds its full payload. No double count: the
        // single entry Arc is measured once via entry_payload_bytes.
        if let Some(old) = self.glyphs.remove(&key) {
            self.payload_bytes = self
                .payload_bytes
                .saturating_sub(entry_payload_bytes(&old));
            self.lru.retain(|k| *k != key);
        }
        let cover_bytes = cover.len() as u64 * 8;
        self.payload_bytes += cover_bytes;
        self.glyphs.insert(
            key,
            GlyphEntry {
                capture_hash,
                params_hash: self.params_hash,
                geom_hash,
                w,
                h,
                left,
                top,
                cover: cover.to_vec(),
                fields,
                energy_nb,
                energy_ms,
                local_energy: HashMap::new(),
            },
        );
        if let Some(e) = self.glyphs.get(&key) {
            self.payload_bytes += entry_payload_bytes(e) - cover_bytes;
        }
        self.builds_fields += 1;
        self.touch(key);
        Ok(true)
    }

    fn entry(&self, dataset: &str, codepoint: u32) -> Result<&GlyphEntry, EngineError> {
        self.glyphs
            .get(&(hash_str(dataset), codepoint))
            .ok_or_else(|| {
                EngineError::Invalid(format!(
                    "glyph U+{codepoint:04X} not loaded for dataset {dataset:?}"
                ))
            })
    }

    /// Score integer candidate steps for one pair. Overlap (occupied-cell)
    /// steps are invalid with `occupied_cell_overlap`; face/corner contact is
    /// allowed and counted. `cstar` applies the TIE-v2 selection; `None`
    /// leaves `minimizing` empty and `chosen` at the metric.
    #[allow(clippy::too_many_arguments)]
    pub fn score_pair(
        &mut self,
        dataset: &str,
        left_cp: u32,
        right_cp: u32,
        metric: i64,
        deltas: &[i64],
        score: &ScoreParams,
        strength: Strength,
        cstar: Option<f64>,
    ) -> Result<PairResult, EngineError> {
        validate_score_request(metric as f64, deltas, score)?;
        if let Some(c) = cstar {
            if !c.is_finite() || c < 0.0 {
                return Err(EngineError::Invalid(format!(
                    "C* must be a finite nonnegative target, got {c}"
                )));
            }
        }
        // Snapshot what scoring needs so the field cache is not borrowed
        // across the compute.
        let (lw, lh, lleft, ltop, lcover, lfields, len_nb, len_ms) = {
            let e = self.entry(dataset, left_cp)?;
            (
                e.w,
                e.h,
                e.left,
                e.top,
                e.cover.clone(),
                Arc::clone(&e.fields),
                e.energy_nb.clone(),
                e.energy_ms.clone(),
            )
        };
        let (rw, rh, rleft, rtop, rcover, rfields, ren_nb, ren_ms) = {
            let e = self.entry(dataset, right_cp)?;
            (
                e.w,
                e.h,
                e.left,
                e.top,
                e.cover.clone(),
                Arc::clone(&e.fields),
                e.energy_nb.clone(),
                e.energy_ms.clone(),
            )
        };
        let (el, er) = match strength {
            Strength::Notebook => (len_nb, ren_nb),
            Strength::Manuscript => (len_ms, ren_ms),
        };
        let pad = self.params.pad();
        let lo_f = (lleft - pad as f64, ltop - pad as f64);
        let ro_base_f = (rleft - pad as f64, rtop - pad as f64);
        let lo = (lo_f.0.trunc() as i64, lo_f.1.trunc() as i64);
        let ro_base = (ro_base_f.0.trunc() as i64, ro_base_f.1.trunc() as i64);
        let ros: Vec<(i64, i64)> = deltas
            .iter()
            .map(|d| (ro_base.0 + metric + d, ro_base.1))
            .collect();
        let (origin, (ch, cw)) = union_canvas(lfields.w, lfields.h, lo, rfields.w, rfields.h, &ros);
        let mut steps = Vec::with_capacity(deltas.len());
        for (d, ro) in deltas.iter().zip(ros.iter()) {
            let step = metric + d;
            let (overlaps, faces, corners) = contact_counts(
                &lcover,
                lw,
                lh,
                (lleft, ltop),
                &rcover,
                rw,
                rh,
                (rleft, rtop),
                step,
            );
            if overlaps > 0 {
                steps.push(StepRecord {
                    step,
                    delta: *d,
                    valid: false,
                    reason: Some("occupied_cell_overlap".to_string()),
                    g2: None,
                    raw: None,
                    floor_share: None,
                    raw_floor_share: None,
                    both_supported_pairpx: 0,
                    abstain: false,
                    faces,
                    corners,
                });
                continue;
            }
            let rec = score_step(
                &lfields,
                &rfields,
                lo,
                *ro,
                origin,
                cw,
                ch,
                &el,
                &er,
                score.tau,
                strength,
                &self.facing,
                Some(&self.cancel),
            )?;
            steps.push(StepRecord {
                step,
                delta: *d,
                valid: true,
                reason: None,
                g2: Some(rec.g2),
                raw: Some(rec.raw),
                floor_share: Some(rec.floor_share),
                raw_floor_share: Some(rec.raw_floor_share),
                both_supported_pairpx: rec.both_supported_pairpx,
                abstain: rec.abstain,
                faces,
                corners,
            });
        }
        let (minimizing, chosen, fallback, fallback_reason) = match cstar {
            Some(c) => {
                let supported: Vec<(usize, f64)> = steps
                    .iter()
                    .enumerate()
                    .filter(|(_, s)| s.valid && !s.abstain)
                    .map(|(i, s)| (i, (s.g2.unwrap_or(f64::NAN) - c).abs()))
                    .collect();
                if supported.is_empty() {
                    let reason = if steps.iter().any(|s| s.valid) {
                        "no_shared_support"
                    } else {
                        "occupied_cell_overlap"
                    };
                    (Vec::new(), metric, true, Some(reason.to_string()))
                } else {
                    let devs: Vec<f64> = supported.iter().map(|(_, d)| *d).collect();
                    let (tie, _) = tie_set(&devs);
                    let min_steps: Vec<i64> =
                        tie.iter().map(|t| steps[supported[*t].0].step).collect();
                    let chosen = *min_steps.iter().min().unwrap();
                    (min_steps, chosen, false, None)
                }
            }
            None => (Vec::new(), metric, false, None),
        };
        Ok(PairResult {
            steps,
            minimizing,
            chosen,
            fallback,
            fallback_reason,
        })
    }

    /// Per-glyph Class-L local-energy maps, cached inside the glyph entry
    /// under `(strength, normalization_radius)` and invalidated
    /// structurally with the entry's fields.
    pub fn local_energy_for(
        &mut self,
        dataset: &str,
        codepoint: u32,
        strength: Strength,
        radius: u32,
    ) -> Result<Arc<Vec<Vec<f64>>>, EngineError> {
        if radius < 1 || radius > 64 {
            return Err(EngineError::Invalid(format!(
                "normalization_radius must be an integer in [1, 64], got {radius}"
            )));
        }
        let key = (strength_code(strength), radius);
        let fields = {
            let e = self.entry(dataset, codepoint)?;
            if let Some(maps) = e.local_energy.get(&key) {
                return Ok(Arc::clone(maps));
            }
            Arc::clone(&e.fields)
        };
        let maps = local_energy_maps(&fields, radius, strength);
        let maps = Arc::new(maps);
        // Post-load growth: the new maps extend the live entry, so the
        // payload grows here too (same accounting as insert). Eviction
        // after growth keeps the just-used pair: it is among the most
        // recent loads, inside the keep-floor.
        let add: u64 = maps.iter().map(|ch| ch.len() as u64 * 8).sum();
        let e = self
            .glyphs
            .get_mut(&(hash_str(dataset), codepoint))
            .ok_or_else(|| {
                EngineError::Invalid(format!(
                    "glyph U+{codepoint:04X} not loaded for dataset {dataset:?}"
                ))
            })?;
        e.local_energy.insert(key, Arc::clone(&maps));
        self.payload_bytes += add;
        self.builds_el += 1;
        self.enforce_budget();
        Ok(maps)
    }

    /// Score integer candidate steps for one pair with Class L.
    /// Same domain/validity/TIE-v2 shape as `score_pair`; abstain carries
    /// the local reasons (`no_shared_support`, `zero_local_evidence`).
    #[allow(clippy::too_many_arguments)]
    pub fn score_pair_local(
        &mut self,
        dataset: &str,
        left_cp: u32,
        right_cp: u32,
        metric: i64,
        deltas: &[i64],
        score: &ScoreParams,
        strength: Strength,
        cstar: Option<f64>,
    ) -> Result<LocalPairResult, EngineError> {
        score.validate()?;
        if let Some(c) = cstar {
            if !c.is_finite() || c < 0.0 {
                return Err(EngineError::Invalid(format!(
                    "C* must be a finite nonnegative target, got {c}"
                )));
            }
        }
        let (lw, lh, lleft, ltop, lcover, lfields) = {
            let e = self.entry(dataset, left_cp)?;
            (
                e.w,
                e.h,
                e.left,
                e.top,
                e.cover.clone(),
                Arc::clone(&e.fields),
            )
        };
        let (rw, rh, rleft, rtop, rcover, rfields) = {
            let e = self.entry(dataset, right_cp)?;
            (
                e.w,
                e.h,
                e.left,
                e.top,
                e.cover.clone(),
                Arc::clone(&e.fields),
            )
        };
        let local_l = self.local_energy_for(dataset, left_cp, strength, score.normalization_radius)?;
        let local_r =
            self.local_energy_for(dataset, right_cp, strength, score.normalization_radius)?;
        let pad = self.params.pad();
        let lo_f = (lleft - pad as f64, ltop - pad as f64);
        let ro_base_f = (rleft - pad as f64, rtop - pad as f64);
        let lo = (lo_f.0.trunc() as i64, lo_f.1.trunc() as i64);
        let ro_base = (ro_base_f.0.trunc() as i64, ro_base_f.1.trunc() as i64);
        let ros: Vec<(i64, i64)> = deltas
            .iter()
            .map(|d| (ro_base.0 + metric + d, ro_base.1))
            .collect();
        let (origin, (ch, cw)) = union_canvas(
            lfields.w,
            lfields.h,
            lo,
            rfields.w,
            rfields.h,
            &ros,
        );
        let mut steps = Vec::with_capacity(deltas.len());
        for (d, ro) in deltas.iter().zip(ros.iter()) {
            let step = metric + d;
            let (overlaps, faces, corners) = contact_counts(
                &lcover,
                lw,
                lh,
                (lleft, ltop),
                &rcover,
                rw,
                rh,
                (rleft, rtop),
                step,
            );
            if overlaps > 0 {
                steps.push(LocalStepRecord {
                    step,
                    delta: *d,
                    valid: false,
                    reason: Some("occupied_cell_overlap".to_string()),
                    gl: None,
                    both_supported_pairpx: 0,
                    weak_normalized_share: None,
                    max_term_cosine: None,
                    abstain: false,
                    abstain_reason: None,
                    skipped_nonpositive: 0,
                    conditioning_shortfall: 0.0,
                    honest_bound: None,
                    faces,
                    corners,
                });
                continue;
            }
            let rec = score_step_local(
                &lfields,
                &rfields,
                lo,
                *ro,
                origin,
                cw,
                ch,
                &local_l,
                &local_r,
                &self.facing,
                score.tau,
                strength,
                Some(&self.cancel),
            )?;
            steps.push(LocalStepRecord {
                step,
                delta: *d,
                valid: true,
                reason: None,
                gl: Some(rec.gl),
                both_supported_pairpx: rec.both_supported_pairpx,
                weak_normalized_share: Some(rec.weak_normalized_share),
                max_term_cosine: Some(rec.max_term_cosine),
                abstain: rec.abstain,
                abstain_reason: rec.abstain_reason.map(|r| r.as_str().to_string()),
                skipped_nonpositive: rec.skipped_nonpositive,
                conditioning_shortfall: rec.conditioning_shortfall,
                honest_bound: Some(rec.honest_bound),
                faces,
                corners,
            });
        }
        let (minimizing, chosen, fallback, fallback_reason) = match cstar {
            Some(c) => {
                let supported: Vec<(usize, f64)> = steps
                    .iter()
                    .enumerate()
                    .filter(|(_, s)| s.valid && !s.abstain)
                    .map(|(i, s)| (i, (s.gl.unwrap_or(f64::NAN) - c).abs()))
                    .collect();
                if supported.is_empty() {
                    // Pair-level reason follows the per-step evidence reasons,
                    // not the gated count: support that is entirely guard-
                    // skipped is zero local evidence, not no shared support.
                    let zero_evidence = LocalAbstain::ZeroLocalEvidence.as_str();
                    let reason = if steps.iter().any(|s| {
                        s.valid && s.abstain_reason.as_deref() == Some(zero_evidence)
                    }) {
                        zero_evidence
                    } else if steps.iter().any(|s| s.valid) {
                        "no_shared_support"
                    } else {
                        "occupied_cell_overlap"
                    };
                    (Vec::new(), metric, true, Some(reason.to_string()))
                } else {
                    let devs: Vec<f64> = supported.iter().map(|(_, d)| *d).collect();
                    let (tie, _) = tie_set(&devs);
                    let min_steps: Vec<i64> =
                        tie.iter().map(|t| steps[supported[*t].0].step).collect();
                    let chosen = *min_steps.iter().min().unwrap();
                    (min_steps, chosen, false, None)
                }
            }
            None => (Vec::new(), metric, false, None),
        };
        Ok(LocalPairResult {
            steps,
            minimizing,
            chosen,
            fallback,
            fallback_reason,
        })
    }

    /// Exact locally-normalized contribution map for one step over an
    /// explicit canvas. Sums to the step `gl` (assertion-checked by tests).
    #[allow(clippy::too_many_arguments)]
    pub fn contribution_map_local(
        &mut self,
        dataset: &str,
        left_cp: u32,
        right_cp: u32,
        step: i64,
        score: &ScoreParams,
        strength: Strength,
    ) -> Result<(Vec<f64>, (i64, i64), (usize, usize)), EngineError> {
        score.validate()?;
        let (lo, ro, origin, cw, ch) = self.step_canvas(dataset, left_cp, right_cp, step)?;
        let local_l = self.local_energy_for(dataset, left_cp, strength, score.normalization_radius)?;
        let local_r =
            self.local_energy_for(dataset, right_cp, strength, score.normalization_radius)?;
        let le = self.entry(dataset, left_cp)?;
        let lfields = Arc::clone(&le.fields);
        let re = self.entry(dataset, right_cp)?;
        let rfields = Arc::clone(&re.fields);
        let map = contribution_map_local_fn(
            &lfields,
            &rfields,
            lo,
            ro,
            origin,
            cw,
            ch,
            &local_l,
            &local_r,
            &self.facing,
            score.tau,
            strength,
            Some(&self.cancel),
        )?;
        Ok((map, origin, (cw, ch)))
    }

    /// L/R-symmetric agreement readout for one step (informational only).
    pub fn confidence_pair(
        &self,
        dataset: &str,
        left_cp: u32,
        right_cp: u32,
        step: i64,
        strength: Strength,
    ) -> Result<crate::local_energy::LocalConfidence, EngineError> {
        let le = self.entry(dataset, left_cp)?;
        let re = self.entry(dataset, right_cp)?;
        let pad = self.params.pad();
        let lo = (
            (le.left - pad as f64).trunc() as i64,
            (le.top - pad as f64).trunc() as i64,
        );
        let ro = (
            (re.left - pad as f64).trunc() as i64 + step,
            (re.top - pad as f64).trunc() as i64,
        );
        let (origin, (ch, cw)) = union_canvas(
            le.fields.w,
            le.fields.h,
            lo,
            re.fields.w,
            re.fields.h,
            &[ro],
        );
        Ok(confidence_local(
            &le.fields,
            &re.fields,
            lo,
            ro,
            origin,
            cw,
            ch,
            strength,
        ))
    }

    fn step_canvas(
        &self,
        dataset: &str,
        left_cp: u32,
        right_cp: u32,
        step: i64,
    ) -> Result<((i64, i64), (i64, i64), (i64, i64), usize, usize), EngineError>
    {
        let le = self.entry(dataset, left_cp)?;
        let re = self.entry(dataset, right_cp)?;
        let pad = self.params.pad();
        let lo = (
            (le.left - pad as f64).trunc() as i64,
            (le.top - pad as f64).trunc() as i64,
        );
        let ro = (
            (re.left - pad as f64).trunc() as i64 + step,
            (re.top - pad as f64).trunc() as i64,
        );
        let (origin, (ch, cw)) = union_canvas(
            le.fields.w,
            le.fields.h,
            lo,
            re.fields.w,
            re.fields.h,
            &[ro],
        );
        Ok((lo, ro, origin, cw, ch))
    }

    /// Geometry-derived search domain for one pair: `None` when a side
    /// is blank or the padded row bands are disjoint (both fall back to
    /// Source). Lower bound `max(floor(L1 - R2), 1)` from delivered ink
    /// extents excludes the reversed-order component of the full padded
    /// interval, intersected with strictly forward pen order (LTR layout
    /// admissibility: every placed origin strictly advances); upper bound
    /// is the last step whose padded field lattices still overlap in x,
    /// beyond which both-supported pixels are impossible.
    pub fn search_domain(
        &self,
        dataset: &str,
        left_cp: u32,
        right_cp: u32,
    ) -> Result<Result<SearchDomain, NoDomain>, EngineError> {
        let le = self.entry(dataset, left_cp)?;
        let re = self.entry(dataset, right_cp)?;
        let ink_span = |e: &GlyphEntry| -> Option<(i64, i64)> {
            let ox = e.left.trunc() as i64;
            let mut lo: Option<i64> = None;
            let mut hi: Option<i64> = None;
            for y in 0..e.h {
                for x in 0..e.w {
                    if e.cover[y * e.w + x] > 0.0 {
                        let px = ox + x as i64;
                        lo = Some(lo.map_or(px, |v: i64| v.min(px)));
                        hi = Some(hi.map_or(px, |v: i64| v.max(px)));
                    }
                }
            }
            lo.zip(hi)
        };
        let (l1, r2) = match (ink_span(le), ink_span(re)) {
            (Some((a, _)), Some((_, b))) => (a, b),
            _ => return Ok(Err(NoDomain::Blank)),
        };
        let pad = self.params.pad();
        let loy = (le.top - pad as f64).trunc() as i64;
        let roy = (re.top - pad as f64).trunc() as i64;
        if loy + le.fields.h as i64 <= roy || roy + re.fields.h as i64 <= loy {
            return Ok(Err(NoDomain::DisjointRows));
        }
        let lo = ((l1 as f64 - r2 as f64).floor() as i64).max(1);
        let hi = ((le.left - pad as f64).trunc() as i64) + le.fields.w as i64
            - 1
            - ((re.left - pad as f64).trunc() as i64);
        if hi < 1 {
            return Ok(Err(NoDomain::NoForwardStep));
        }
        Ok(Ok(SearchDomain { lo, hi }))
    }

    /// Exact normalized contribution map for one step over an explicit
    /// canvas (e.g. the pair's scored union canvas from the adapter).
    /// Sums to the step G2 (assertion-checked by tests).
    #[allow(clippy::type_complexity)]
    pub fn contribution_map(
        &self,
        dataset: &str,
        left_cp: u32,
        right_cp: u32,
        step: i64,
        score: &ScoreParams,
        strength: Strength,
    ) -> Result<(Vec<f64>, (i64, i64), (usize, usize)), EngineError> {
        score.validate()?;
        let le = self.entry(dataset, left_cp)?;
        let re = self.entry(dataset, right_cp)?;
        let pad = self.params.pad();
        let lo = (
            (le.left - pad as f64).trunc() as i64,
            (le.top - pad as f64).trunc() as i64,
        );
        let ro = (
            (re.left - pad as f64).trunc() as i64 + step,
            (re.top - pad as f64).trunc() as i64,
        );
        let (origin, (ch, cw)) = union_canvas(
            le.fields.w,
            le.fields.h,
            lo,
            re.fields.w,
            re.fields.h,
            &[ro],
        );
        self.contribution_map_on_canvas(
            dataset, left_cp, right_cp, lo, ro, origin, cw, ch, score, strength,
        )
        .map(|map| (map, origin, (cw, ch)))
    }

    #[allow(clippy::too_many_arguments)]
    pub fn contribution_map_on_canvas(
        &self,
        dataset: &str,
        left_cp: u32,
        right_cp: u32,
        lo: (i64, i64),
        ro: (i64, i64),
        origin: (i64, i64),
        cw: usize,
        ch: usize,
        score: &ScoreParams,
        strength: Strength,
    ) -> Result<Vec<f64>, EngineError> {
        score.validate()?;
        let le = self.entry(dataset, left_cp)?;
        let re = self.entry(dataset, right_cp)?;
        let (el, er) = match strength {
            Strength::Notebook => (&le.energy_nb, &re.energy_nb),
            Strength::Manuscript => (&le.energy_ms, &re.energy_ms),
        };
        contribution_map(
            &le.fields,
            &re.fields,
            lo,
            ro,
            origin,
            cw,
            ch,
            el,
            er,
            score.tau,
            strength,
            &self.facing,
            Some(&self.cancel),
        )
    }

    /// One requested glyph component over the padded lattice (width,
    /// height returned alongside). Kinds: `confidence_notebook`,
    /// `arc_strength`, `distance`, `u1`, `u2`, `supported`, `t_combined`,
    /// `c_scale`, `cnorm` (per-channel `c/sqrt(E)`, zero-guarded), `slate`
    /// (per-pixel max over channels of `cnorm`, in `[0,1]`),
    /// `local_energy` (per-channel `EL` at the frozen radius, notebook),
    /// `lnorm` (per-channel `c/sqrt(EL)`, zero-guarded, notebook),
    /// `lslate` (per-pixel max over channels of `lnorm`, notebook).
    /// The `l*` kinds are explicitly local-normalized projections,
    /// distinct from the raw `cnorm`/`slate` ones.
    pub fn glyph_component(
        &mut self,
        dataset: &str,
        codepoint: u32,
        kind: &str,
        channel: usize,
        scale: usize,
    ) -> Result<(Vec<f64>, usize, usize), EngineError> {
        if matches!(kind, "local_energy" | "lnorm" | "lslate") {
            return self.local_component(dataset, codepoint, kind, channel);
        }
        let e = self.entry(dataset, codepoint)?;
        let f = &e.fields;
        let (w, h) = (f.w, f.h);
        let npx = w * h;
        let out = match kind {
            "confidence_notebook" | "arc_strength" | "distance" | "u1" | "u2" => {
                if channel >= f.supported.len() {
                    return Err(EngineError::Invalid(format!(
                        "channel {channel} out of range ({} directed)",
                        f.supported.len()
                    )));
                }
                let src = match kind {
                    "confidence_notebook" => &f.conf_nb[channel],
                    "arc_strength" => &f.arc[channel],
                    "distance" => &f.distance[channel],
                    "u1" => &f.u1[channel],
                    _ => &f.u2[channel],
                };
                src.clone()
            }
            "supported" => {
                if channel >= f.supported.len() {
                    return Err(EngineError::Invalid(format!(
                        "channel {channel} out of range ({} directed)",
                        f.supported.len()
                    )));
                }
                f.supported[channel]
                    .iter()
                    .map(|m| if *m { 1.0 } else { 0.0 })
                    .collect()
            }
            "t_combined" => {
                if channel >= f.t_combined.len() {
                    return Err(EngineError::Invalid(format!(
                        "channel {channel} out of range ({} V1)",
                        f.t_combined.len()
                    )));
                }
                f.t_combined[channel].clone()
            }
            "c_scale" => {
                if scale >= f.c_per_scale.len() {
                    return Err(EngineError::Invalid(format!(
                        "scale {scale} out of range ({})",
                        f.c_per_scale.len()
                    )));
                }
                if channel >= f.c_per_scale[scale].len() {
                    return Err(EngineError::Invalid(format!(
                        "channel {channel} out of range ({} V1)",
                        f.c_per_scale[scale].len()
                    )));
                }
                f.c_per_scale[scale][channel].clone()
            }
            "cnorm" => {
                if channel >= f.supported.len() {
                    return Err(EngineError::Invalid(format!(
                        "channel {channel} out of range ({} directed)",
                        f.supported.len()
                    )));
                }
                let energy = match e.energy_nb.get(channel) {
                    Some(v) => *v,
                    None => 0.0,
                };
                if !(energy.is_finite() && energy > 0.0) {
                    vec![0.0; npx]
                } else {
                    let inv = 1.0 / energy.sqrt();
                    f.conf_nb[channel]
                        .iter()
                        .zip(f.supported[channel].iter())
                        .map(|(v, m)| if *m { v * inv } else { 0.0 })
                        .collect()
                }
            }
            "slate" => {
                let mut out = vec![0.0; npx];
                for o in 0..f.supported.len() {
                    let energy = e.energy_nb[o];
                    if !(energy.is_finite() && energy > 0.0) {
                        continue;
                    }
                    let inv = 1.0 / energy.sqrt();
                    for (slot, (v, m)) in out
                        .iter_mut()
                        .zip(f.conf_nb[o].iter().zip(f.supported[o].iter()))
                    {
                        if *m {
                            let c = v * inv;
                            if c > *slot {
                                *slot = c;
                            }
                        }
                    }
                }
                out
            }
            _ => {
                return Err(EngineError::Invalid(format!(
                    "unknown component kind {kind:?}"
                )));
            }
        };
        Ok((out, w, h))
    }

    fn local_component(
        &mut self,
        dataset: &str,
        codepoint: u32,
        kind: &str,
        channel: usize,
    ) -> Result<(Vec<f64>, usize, usize), EngineError> {
        let maps = self.local_energy_for(
            dataset,
            codepoint,
            Strength::Notebook,
            FROZEN_NORMALIZATION_RADIUS,
        )?;
        let e = self.entry(dataset, codepoint)?;
        let (w, h) = (e.fields.w, e.fields.h);
        let n = e.fields.supported.len();
        let out = match kind {
            "local_energy" => {
                if channel >= n {
                    return Err(EngineError::Invalid(format!(
                        "channel {channel} out of range ({n} directed)"
                    )));
                }
                maps[channel].clone()
            }
            "lnorm" => {
                if channel >= n {
                    return Err(EngineError::Invalid(format!(
                        "channel {channel} out of range ({n} directed)"
                    )));
                }
                e.fields.conf_nb[channel]
                    .iter()
                    .zip(e.fields.supported[channel].iter())
                    .zip(maps[channel].iter())
                    .map(|((v, m), el)| {
                        if *m && *el > 0.0 && el.is_finite() {
                            v / el.sqrt()
                        } else {
                            0.0
                        }
                    })
                    .collect()
            }
            _ => {
                // lslate: per-pixel max over channels of lnorm.
                let mut out = vec![0.0; w * h];
                for o in 0..n {
                    for ((slot, (v, m)), el) in out
                        .iter_mut()
                        .zip(
                            e.fields.conf_nb[o]
                                .iter()
                                .zip(e.fields.supported[o].iter()),
                        )
                        .zip(maps[o].iter())
                    {
                        if *m && *el > 0.0 && el.is_finite() {
                            let c = v / el.sqrt();
                            if c > *slot {
                                *slot = c;
                            }
                        }
                    }
                }
                out
            }
        };
        Ok((out, w, h))
    }

    /// Per-glyph projection peak: max over channels and pixels of
    /// `c/sqrt(E)` (zero-guarded), the fixed-gain slate calibration basis.
    pub fn slate_max(&self, dataset: &str, codepoint: u32) -> Result<f64, EngineError> {
        let e = self.entry(dataset, codepoint)?;
        let f = &e.fields;
        let mut best = 0.0;
        for o in 0..f.supported.len() {
            let energy = e.energy_nb[o];
            if !(energy.is_finite() && energy > 0.0) {
                continue;
            }
            let inv = 1.0 / energy.sqrt();
            for i in 0..f.w * f.h {
                if f.supported[o][i] {
                    let v = f.conf_nb[o][i] * inv;
                    if v > best {
                        best = v;
                    }
                }
            }
        }
        Ok(best)
    }

    pub fn clear_dataset(&mut self, dataset: &str) {
        let dh = hash_str(dataset);
        let mut freed = 0u64;
        self.glyphs.retain(|k, e| {
            if k.0 == dh {
                freed += entry_payload_bytes(e);
                false
            } else {
                true
            }
        });
        self.payload_bytes = self.payload_bytes.saturating_sub(freed);
        self.lru.retain(|k| k.0 != dh);
    }

    pub fn clear_all(&mut self) {
        self.glyphs.clear();
        self.lru.clear();
        self.payload_bytes = 0;
    }

    pub fn cache_sizes(&self) -> (usize, usize) {
        (self.glyphs.len(), self.lru.len())
    }

    /// Point-in-time cache resource readout. Counters are cumulative per
    /// engine instance since construction (survive clears, which only drop
    /// the live payload); a fresh `Engine` restarts them at zero.
    pub fn cache_stats(&self) -> CacheStats {
        CacheStats {
            glyphs: self.glyphs.len(),
            lru: self.lru.len(),
            payload_bytes: self.payload_bytes,
            builds_fields: self.builds_fields,
            builds_el: self.builds_el,
            evictions: self.evictions,
        }
    }

    pub fn cancel_flag(&self) -> Arc<AtomicBool> {
        Arc::clone(&self.cancel)
    }
}

#[cfg(test)]
mod cache_policy_tests {
    use super::*;
    use crate::params::EngineParams;

    /// KB-scale params for policy tests (no GB allocations): pad 3 lattice.
    fn tiny_params() -> EngineParams {
        EngineParams {
            q: 2.0,
            kappa: 4.0,
            sigmas: vec![0.5],
            weights: vec![1.0],
            radius: 1,
            eps: 1e-12,
            n_v1: 1,
            n_directed: 1,
        }
    }

    fn cover(seed: u64, n: usize) -> Vec<f64> {
        // Deterministic nonzero pattern; exact values never asserted here.
        (0..n).map(|i| (((seed * 31 + i as u64) % 7) + 1) as f64 / 7.0).collect()
    }

    fn load(engine: &mut Engine, cp: u32, w: usize, h: usize) -> bool {
        let c = cover(cp as u64 + 1, w * h);
        engine
            .load_glyph("t", "s", cp, w, h, 0.0, 0.0, &c)
            .unwrap()
    }

    fn resident_sum(engine: &Engine) -> u64 {
        engine.glyphs.values().map(entry_payload_bytes).sum()
    }

    #[test]
    fn floor_holds_below_target_without_eviction() {
        let mut e = Engine::new(tiny_params()).unwrap();
        e.payload_target = 1 << 60; // effectively unbounded
        for cp in 0..5 {
            assert!(load(&mut e, cp, 4, 4));
        }
        let s = e.cache_stats();
        assert_eq!((s.glyphs, s.lru), (5, 5));
        assert_eq!(s.evictions, 0);
        assert_eq!(s.builds_fields, 5);
        assert_eq!(s.payload_bytes, resident_sum(&e));
    }

    #[test]
    fn ceiling_evicts_lru_front() {
        let mut e = Engine::new(tiny_params()).unwrap();
        e.payload_target = 1 << 60;
        e.count_ceiling = 2;
        for cp in 0..4 {
            load(&mut e, cp, 4, 4);
        }
        let s = e.cache_stats();
        assert_eq!((s.glyphs, s.lru), (2, 2));
        assert_eq!(s.evictions, 2);
        // Most recent two survive; oldest two are gone.
        assert!(e.glyphs.contains_key(&(hash_str("t"), 2)));
        assert!(e.glyphs.contains_key(&(hash_str("t"), 3)));
        assert_eq!(s.payload_bytes, resident_sum(&e));
    }

    #[test]
    fn over_target_evicts_beyond_floor_only() {
        let mut e = Engine::new(tiny_params()).unwrap();
        // One entry's bytes: load one, then set the target below a single.
        load(&mut e, 0, 4, 4);
        let one = e.cache_stats().payload_bytes;
        assert!(one > 0);
        e.keep_floor = 2;
        e.payload_target = one; // two entries exceed it
        load(&mut e, 1, 4, 4);
        load(&mut e, 2, 4, 4); // evicts cp 0, keeps newest two
        let s = e.cache_stats();
        assert_eq!(s.glyphs, 2);
        assert_eq!(s.evictions, 1);
        assert!(e.glyphs.contains_key(&(hash_str("t"), 1)));
        assert!(e.glyphs.contains_key(&(hash_str("t"), 2)));
        assert_eq!(s.payload_bytes, resident_sum(&e));
    }

    #[test]
    fn zero_target_still_keeps_floor() {
        let mut e = Engine::new(tiny_params()).unwrap();
        e.payload_target = 0; // degenerate target: floor still holds
        e.keep_floor = 3;
        for cp in 0..5 {
            load(&mut e, cp, 4, 4);
        }
        let s = e.cache_stats();
        assert_eq!(s.glyphs, 3); // never below the floor, never unbounded
        assert_eq!(s.evictions, 2);
        assert_eq!(s.payload_bytes, resident_sum(&e));
    }

    #[test]
    fn el_growth_is_accounted_and_can_evict() {
        let mut e = Engine::new(tiny_params()).unwrap();
        load(&mut e, 0, 4, 4);
        let before = e.cache_stats().payload_bytes;
        let maps = e
            .local_energy_for("t", 0, Strength::Notebook, 1)
            .unwrap();
        assert!(!maps.is_empty());
        let after = e.cache_stats().payload_bytes;
        assert!(after > before, "EL maps must grow the payload");
        assert_eq!(e.cache_stats().builds_el, 1);
        // Cache hit: same Arc content, no new build, no new bytes.
        let maps2 = e
            .local_energy_for("t", 0, Strength::Notebook, 1)
            .unwrap();
        assert!(Arc::ptr_eq(&maps, &maps2));
        assert_eq!(e.cache_stats().builds_el, 1);
        assert_eq!(e.cache_stats().payload_bytes, after);
        // EL growth under a tight target evicts LRU-front, not the entry.
        e.keep_floor = 1;
        e.payload_target = after; // exactly one full entry
        load(&mut e, 1, 4, 4);
        let s = e.cache_stats();
        assert_eq!(s.glyphs, 1);
        assert!(e.glyphs.contains_key(&(hash_str("t"), 1)));
        assert_eq!(s.payload_bytes, resident_sum(&e));
    }

    #[test]
    fn replacement_adjusts_payload_once() {
        let mut e = Engine::new(tiny_params()).unwrap();
        assert!(load(&mut e, 7, 4, 4));
        let one = e.cache_stats().payload_bytes;
        // Same key, different geometry bytes: rebuild, payload unchanged
        // in size class and counted exactly once.
        let c = cover(999, 4 * 4);
        assert!(e.load_glyph("t", "s", 7, 4, 4, 1.0, 0.0, &c).unwrap());
        let s = e.cache_stats();
        assert_eq!(s.glyphs, 1);
        assert_eq!(s.builds_fields, 2);
        assert_eq!(s.evictions, 0);
        assert_eq!(s.payload_bytes, resident_sum(&e));
        assert!(one > 0 && s.payload_bytes > 0);
    }

    #[test]
    fn clears_drop_payload_keep_counters() {
        let mut e = Engine::new(tiny_params()).unwrap();
        load(&mut e, 0, 4, 4);
        load(&mut e, 1, 4, 4);
        e.local_energy_for("t", 0, Strength::Notebook, 1).unwrap();
        assert!(e.cache_stats().payload_bytes > 0);
        e.clear_dataset("t");
        let s = e.cache_stats();
        assert_eq!((s.glyphs, s.lru, s.payload_bytes), (0, 0, 0));
        assert_eq!(s.builds_fields, 2); // cumulative: clears reset payload only
        e.clear_all();
        assert_eq!(e.cache_stats().payload_bytes, 0);
    }

    #[test]
    fn oversized_single_still_builds() {
        let mut e = Engine::new(tiny_params()).unwrap();
        e.payload_target = 1; // every entry is oversized
        e.keep_floor = 1;
        assert!(load(&mut e, 0, 4, 4)); // builds, len==1 guard holds it
        assert!(load(&mut e, 1, 4, 4)); // evicts cp 0, keeps cp 1
        let s = e.cache_stats();
        assert_eq!(s.glyphs, 1);
        assert!(e.glyphs.contains_key(&(hash_str("t"), 1)));
        // Re-accessing the evicted entry rebuilds (never skipped/rejected).
        assert!(load(&mut e, 0, 4, 4));
        assert_eq!(e.cache_stats().builds_fields, 3);
        // Overshoot is reported, not hidden: with the floor above the
        // target, all floor entries stay resident past the soft target.
        let mut e2 = Engine::new(tiny_params()).unwrap();
        e2.payload_target = 1;
        e2.keep_floor = 32;
        for cp in 0..33 {
            load(&mut e2, cp, 4, 4);
        }
        let s2 = e2.cache_stats();
        assert_eq!(s2.glyphs, 32); // floor holds: never below 32
        assert_eq!(s2.evictions, 1);
        assert!(s2.payload_bytes > e2.payload_target);
        assert_eq!(s2.payload_bytes, resident_sum(&e2));
    }

    #[test]
    fn live_arc_survives_entry_eviction() {
        let mut e = Engine::new(tiny_params()).unwrap();
        e.count_ceiling = 1; // every new load evicts the previous entry
        load(&mut e, 0, 4, 4);
        let maps = e
            .local_energy_for("t", 0, Strength::Notebook, 1)
            .unwrap();
        let nch = maps.len();
        load(&mut e, 1, 4, 4); // evicts cp 0 while `maps` is live
        assert_eq!(e.cache_stats().evictions, 1);
        // The retained Arc stays fully readable past eviction.
        assert_eq!(maps.len(), nch);
        assert!(maps.iter().any(|ch| ch.iter().any(|v| *v > 0.0)));
    }

    #[test]
    fn inclusion_and_miss_monotonicity_vs_baseline() {
        // Adversarial variable-size trace: C2 residency must always include
        // the baseline last-N set, and every baseline hit must be a C2 hit.
        let mut e = Engine::new(tiny_params()).unwrap();
        e.keep_floor = 3;
        e.count_ceiling = 512;
        e.payload_target = 30_000; // binds intermittently at these sizes
        let mut base: VecDeque<(u64, u32)> = VecDeque::new();
        // Variable sizes keyed by codepoint: same cp always loads the same
        // geometry (true hits), different cps have different payload bytes.
        let sizes = [(4, 4), (8, 5), (12, 6), (6, 9), (5, 7)];
        let mut seq = 0u32;
        for round in 0..4 {
            for i in 0..5 {
                // Skewed reuse: recent keys revisited, old keys return.
                let cp = ((i + round * 2 + (seq % 3) as usize) % 7) as u32;
                seq += 1;
                let (w, h) = sizes[(cp % 5) as usize];
                let rebuilt = load(&mut e, cp, w, h);
                if round > 0 || i > 0 {
                    e.local_energy_for("t", cp, Strength::Notebook, 1)
                        .unwrap();
                }
                let key = (hash_str("t"), cp);
                // Baseline hit = key already in the pre-load window.
                let base_hit = base.contains(&key);
                if base_hit {
                    assert!(!rebuilt, "baseline hit must be a C2 hit");
                }
                base.retain(|k| *k != key);
                base.push_back(key);
                while base.len() > 3 {
                    base.pop_front();
                }
                for k in base.iter() {
                    assert!(
                        e.glyphs.contains_key(k),
                        "C2 must include baseline last-3 set"
                    );
                }
                assert_eq!(e.cache_stats().payload_bytes, resident_sum(&e));
            }
        }
        // Direct hit-implies-hit check on a fixed window.
        let mut e2 = Engine::new(tiny_params()).unwrap();
        e2.keep_floor = 3;
        e2.payload_target = 1 << 60;
        let mut b2: VecDeque<(u64, u32)> = VecDeque::new();
        for cp in [0u32, 1, 2, 0, 3, 1, 0] {
            let key = (hash_str("t"), cp);
            let base_hit = b2.contains(&key);
            let rebuilt = load(&mut e2, cp, 4, 4);
            if base_hit {
                assert!(!rebuilt, "baseline hit must be a C2 hit");
            }
            b2.retain(|k| *k != key);
            b2.push_back(key);
            while b2.len() > 3 {
                b2.pop_front();
            }
        }
    }
}
