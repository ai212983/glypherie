//! WASM seam: `YinYangEngine` over typed-array buffers.
//!
//! The page worker owns controls, canvas, generation and cancellation;
//! math lives here. No fetch: the worker instantiates from inlined bytes
//! (`initSync({ module: bytes })`). Errors surface as thrown strings.

use js_sys::{Float64Array, Int32Array};
use wasm_bindgen::prelude::*;

use crate::params::{
    EngineParams, ScoreParams, FROZEN_NORMALIZATION_RADIUS, LOCAL_ENERGY_MODEL_IDENTITY,
    MODEL_IDENTITY,
};
use crate::score::Strength;
use crate::SEARCH_POLICY;
use crate::{Engine, EngineError};

fn err(e: EngineError) -> JsValue {
    JsValue::from_str(&e.to_string())
}

fn params_from_json(json: Option<String>) -> Result<EngineParams, EngineError> {
    match json {
        None => Ok(EngineParams::frozen()),
        Some(text) => {
            let v: serde_json::Value = serde_json::from_str(&text)
                .map_err(|e| EngineError::Invalid(format!("params JSON: {e}")))?;
            if !v.is_object() {
                return Err(EngineError::Invalid(
                    "params JSON must be an object".to_string(),
                ));
            }
            let mut p = EngineParams::frozen();
            let get = |key: &str| -> Result<Option<f64>, EngineError> {
                v.get(key)
                    .map(|value| {
                        value
                            .as_f64()
                            .ok_or_else(|| EngineError::Invalid(format!("{key} must be a number")))
                    })
                    .transpose()
            };
            if let Some(q) = get("q")? {
                p.q = q;
            }
            if let Some(k) = get("kappa")? {
                p.kappa = k;
            }
            if let Some(r) = v.get("radius") {
                let r = r.as_u64().ok_or_else(|| {
                    EngineError::Invalid("radius must be an integer px".to_string())
                })?;
                p.radius = u32::try_from(r)
                    .map_err(|_| EngineError::Invalid(format!("radius out of range: {r}")))?;
            }
            if let Some(value) = v.get("sigmas") {
                let arr = value
                    .as_array()
                    .ok_or_else(|| EngineError::Invalid("sigmas must be an array".to_string()))?;
                p.sigmas = arr
                    .iter()
                    .map(|x| {
                        x.as_f64().ok_or_else(|| {
                            EngineError::Invalid("sigmas must be numbers".to_string())
                        })
                    })
                    .collect::<Result<Vec<_>, _>>()?;
            }
            if let Some(value) = v.get("weights") {
                let arr = value
                    .as_array()
                    .ok_or_else(|| EngineError::Invalid("weights must be an array".to_string()))?;
                p.weights = arr
                    .iter()
                    .map(|x| {
                        x.as_f64().ok_or_else(|| {
                            EngineError::Invalid("weights must be numbers".to_string())
                        })
                    })
                    .collect::<Result<Vec<_>, _>>()?;
            }
            if let Some(e) = get("eps")? {
                p.eps = e;
            }
            p.validate()?;
            Ok(p)
        }
    }
}

#[wasm_bindgen]
pub struct YinYangEngine {
    engine: Engine,
    last_origin: (i64, i64),
    last_wh: (usize, usize),
    last_comp_wh: (usize, usize),
}

#[wasm_bindgen]
impl YinYangEngine {
    #[wasm_bindgen(constructor)]
    pub fn new(params_json: Option<String>) -> Result<YinYangEngine, JsValue> {
        let params = params_from_json(params_json).map_err(err)?;
        let engine = Engine::new(params).map_err(err)?;
        Ok(YinYangEngine {
            engine,
            last_origin: (0, 0),
            last_wh: (0, 0),
            last_comp_wh: (0, 0),
        })
    }

    pub fn version(&self) -> String {
        let p = self.engine.params();
        serde_json::json!({
            "model": MODEL_IDENTITY,
            "score_model": LOCAL_ENERGY_MODEL_IDENTITY,
            "search": SEARCH_POLICY,
            "pkg": env!("CARGO_PKG_VERSION"),
            "params": {
                "q": p.q, "kappa": p.kappa, "sigmas": p.sigmas,
                "weights": p.weights, "radius": p.radius, "eps": p.eps,
                "n_v1": p.n_v1, "n_directed": p.n_directed,
            },
            "frozen_normalization_radius": FROZEN_NORMALIZATION_RADIUS,
            "params_hash": format!("{:016x}", self.engine.params_hash()),
        })
        .to_string()
    }

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
        cover: &Float64Array,
    ) -> Result<String, JsValue> {
        let mut buf = vec![0.0; cover.length() as usize];
        cover.copy_to(&mut buf);
        let recomputed = self
            .engine
            .load_glyph(dataset, capture_sha, codepoint, w, h, left, top, &buf)
            .map_err(err)?;
        Ok(serde_json::json!({ "recomputed": recomputed }).to_string())
    }

    fn score_params(tau: f64, norm_radius: Option<u32>) -> Result<ScoreParams, JsValue> {
        let score = ScoreParams {
            tau,
            normalization_radius: norm_radius.unwrap_or(FROZEN_NORMALIZATION_RADIUS),
        };
        score.validate().map_err(err)?;
        Ok(score)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn score_pair(
        &mut self,
        dataset: &str,
        left: u32,
        right: u32,
        metric: i32,
        deltas: &Int32Array,
        tau: f64,
        strength: &str,
        cstar: f64,
    ) -> Result<String, JsValue> {
        let mut d = vec![0i32; deltas.length() as usize];
        deltas.copy_to(&mut d);
        let deltas: Vec<i64> = d.iter().map(|v| *v as i64).collect();
        let score = Self::score_params(tau, None)?;
        let strength = Strength::parse(strength).map_err(err)?;
        let cstar = if cstar.is_nan() { None } else { Some(cstar) };
        let res = self
            .engine
            .score_pair(
                dataset,
                left,
                right,
                metric as i64,
                &deltas,
                &score,
                strength,
                cstar,
            )
            .map_err(err)?;
        Ok(serde_json::json!({
            "steps": res.steps.iter().map(|s| serde_json::json!({
                "step": s.step, "delta": s.delta, "valid": s.valid,
                "reason": s.reason, "g2": s.g2, "raw": s.raw,
                "floor_share": s.floor_share,
                "raw_floor_share": s.raw_floor_share,
                "both_supported_pairpx": s.both_supported_pairpx,
                "abstain": s.abstain, "faces": s.faces, "corners": s.corners,
            })).collect::<Vec<_>>(),
            "minimizing": res.minimizing,
            "chosen": res.chosen,
            "fallback": res.fallback,
            "fallback_reason": res.fallback_reason,
            "uncertainty": "uncertainty_not_certified",
        })
        .to_string())
    }

    pub fn search_domain(
        &mut self,
        dataset: &str,
        left: u32,
        right: u32,
    ) -> Result<String, JsValue> {
        let domain = self
            .engine
            .search_domain(dataset, left, right)
            .map_err(err)?;
        Ok(match domain {
            Ok(d) => serde_json::json!({ "lo": d.lo, "hi": d.hi }).to_string(),
            Err(crate::NoDomain::Blank) => serde_json::json!({ "blank": true }).to_string(),
            Err(crate::NoDomain::DisjointRows) => serde_json::json!({ "empty": true,
                    "reason": "row_bands_disjoint" })
            .to_string(),
            Err(crate::NoDomain::NoForwardStep) => serde_json::json!({ "empty": true,
                    "reason": "no_forward_step" })
            .to_string(),
        })
    }

    pub fn contribution_map(
        &mut self,
        dataset: &str,
        left: u32,
        right: u32,
        step: i32,
        tau: f64,
        strength: &str,
    ) -> Result<Float64Array, JsValue> {
        let score = Self::score_params(tau, None)?;
        let strength = Strength::parse(strength).map_err(err)?;
        let (map, origin, wh) = self
            .engine
            .contribution_map(dataset, left, right, step as i64, &score, strength)
            .map_err(err)?;
        self.last_origin = origin;
        self.last_wh = wh;
        Ok(Float64Array::from(map.as_slice()))
    }

    #[allow(clippy::too_many_arguments)]
    pub fn score_pair_local(
        &mut self,
        dataset: &str,
        left: u32,
        right: u32,
        metric: i32,
        deltas: &Int32Array,
        tau: f64,
        norm_radius: Option<u32>,
        strength: &str,
        cstar: f64,
    ) -> Result<String, JsValue> {
        let mut d = vec![0i32; deltas.length() as usize];
        deltas.copy_to(&mut d);
        let deltas: Vec<i64> = d.iter().map(|v| *v as i64).collect();
        let score = Self::score_params(tau, norm_radius)?;
        let strength = Strength::parse(strength).map_err(err)?;
        let cstar = if cstar.is_nan() { None } else { Some(cstar) };
        let res = self
            .engine
            .score_pair_local(
                dataset,
                left,
                right,
                metric as i64,
                &deltas,
                &score,
                strength,
                cstar,
            )
            .map_err(err)?;
        Ok(serde_json::json!({
            "steps": res.steps.iter().map(|s| serde_json::json!({
                "step": s.step, "delta": s.delta, "valid": s.valid,
                "reason": s.reason, "gl": s.gl,
                "both_supported_pairpx": s.both_supported_pairpx,
                "weak_normalized_share": s.weak_normalized_share,
                "max_term_cosine": s.max_term_cosine,
                "abstain": s.abstain, "abstain_reason": s.abstain_reason,
                "skipped_nonpositive": s.skipped_nonpositive,
                "conditioning_shortfall": s.conditioning_shortfall,
                "honest_bound": s.honest_bound,
                "faces": s.faces, "corners": s.corners,
            })).collect::<Vec<_>>(),
            "minimizing": res.minimizing,
            "chosen": res.chosen,
            "fallback": res.fallback,
            "fallback_reason": res.fallback_reason,
            "uncertainty": "uncertainty_not_certified",
        })
        .to_string())
    }

    #[allow(clippy::too_many_arguments)]
    pub fn contribution_map_local(
        &mut self,
        dataset: &str,
        left: u32,
        right: u32,
        step: i32,
        tau: f64,
        norm_radius: Option<u32>,
        strength: &str,
    ) -> Result<Float64Array, JsValue> {
        let score = Self::score_params(tau, norm_radius)?;
        let strength = Strength::parse(strength).map_err(err)?;
        let (map, origin, wh) = self
            .engine
            .contribution_map_local(
                dataset, left, right, step as i64, &score, strength,
            )
            .map_err(err)?;
        self.last_origin = origin;
        self.last_wh = wh;
        Ok(Float64Array::from(map.as_slice()))
    }

    pub fn confidence_pair(
        &mut self,
        dataset: &str,
        left: u32,
        right: u32,
        step: i32,
        strength: &str,
    ) -> Result<String, JsValue> {
        let strength = Strength::parse(strength).map_err(err)?;
        let c = self
            .engine
            .confidence_pair(dataset, left, right, step as i64, strength)
            .map_err(err)?;
        // Support-only readout: raw strength sums over the support union
        // (never gl-unit normalized mass, never energy-eligible counts).
        Ok(serde_json::json!({
            "support_mass_l": c.support_mass_l, "support_mass_r": c.support_mass_r,
            "support_weak_mass_l": c.support_weak_mass_l,
            "support_weak_mass_r": c.support_weak_mass_r,
            "support_share": c.support_share,
            "support_union_pairpx": c.support_union_pairpx,
        })
        .to_string())
    }

    pub fn last_map_geometry(&self) -> String {
        serde_json::json!({
            "origin": [self.last_origin.0, self.last_origin.1],
            "width": self.last_wh.0, "height": self.last_wh.1,
        })
        .to_string()
    }

    pub fn glyph_component(
        &mut self,
        dataset: &str,
        codepoint: u32,
        kind: &str,
        channel: usize,
        scale: usize,
    ) -> Result<Float64Array, JsValue> {
        let (arr, w, h) = self
            .engine
            .glyph_component(dataset, codepoint, kind, channel, scale)
            .map_err(err)?;
        self.last_comp_wh = (w, h);
        Ok(Float64Array::from(arr.as_slice()))
    }

    pub fn last_component_note(&self) -> String {
        serde_json::json!({
            "width": self.last_comp_wh.0, "height": self.last_comp_wh.1,
        })
        .to_string()
    }

    pub fn slate_max(&self, dataset: &str, codepoint: u32) -> Result<f64, JsValue> {
        self.engine.slate_max(dataset, codepoint).map_err(err)
    }

    pub fn clear_dataset(&mut self, dataset: &str) {
        self.engine.clear_dataset(dataset);
    }

    pub fn clear_all(&mut self) {
        self.engine.clear_all();
    }

    pub fn cache_sizes(&self) -> String {
        let s = self.engine.cache_stats();
        serde_json::json!({
            "glyphs": s.glyphs,
            "lru": s.lru,
            "payload_bytes": s.payload_bytes,
            "builds_fields": s.builds_fields,
            "builds_el": s.builds_el,
            "evictions": s.evictions,
        })
        .to_string()
    }

    pub fn cancel(&self) {
        self.engine.cancel();
    }

    pub fn clear_cancel(&self) {
        self.engine.clear_cancel();
    }
}
