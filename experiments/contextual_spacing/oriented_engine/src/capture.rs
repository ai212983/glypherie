//! Capture-JSON reader for the native parity/bench drivers (not the engine).
//!
//! Supports the maintained capture schemas the frozen corpus reads: mono
//! (`contextual-spacing-capture-v1`: bitmap cells plus `finalized_advance_px`
//! and `metric_pairs_on` adjustments) and gray
//! (`contextual-spacing-grayscale-v2`: `p/7` pixels, `advance_26_6`, kerning
//! `adjustment_26_6`). Cover mapping matches the frozen loaders exactly:
//! mono `1.0/0.0`, gray `p/7` linear.

use std::collections::HashMap;
use std::path::Path;

use serde::Deserialize;

use crate::score::pixel_round;
use crate::EngineError;

#[derive(Debug, Clone)]
pub struct Cell {
    pub w: usize,
    pub h: usize,
    pub left: f64,
    pub top: f64,
    pub cover: Vec<f64>,
    pub advance_px: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct Dataset {
    pub name: String,
    pub profile: String,
    pub path: String,
    pub sha256: String,
    pub cells: HashMap<u32, Cell>,
    pub adjustments: HashMap<(u32, u32), f64>,
    pub advances: HashMap<u32, f64>,
}

impl Dataset {
    /// Current-source placement step for an isolated pair (named control):
    /// mono finalized advances, gray fractional advances, plus the pair
    /// adjustment, rounded once at draw.
    pub fn metric_step(&self, left: u32, right: u32) -> Result<i64, EngineError> {
        let advance = if self.profile == "mono" {
            self.cells
                .get(&left)
                .and_then(|c| c.advance_px)
                .ok_or_else(|| {
                    EngineError::Invalid(format!("missing mono advance for U+{left:04X}"))
                })?
        } else {
            *self.advances.get(&left).ok_or_else(|| {
                EngineError::Invalid(format!("missing gray advance for U+{left:04X}"))
            })?
        };
        let adjustment = self.adjustments.get(&(left, right)).copied().unwrap_or(0.0);
        Ok(pixel_round(advance + adjustment))
    }
}

#[derive(Deserialize)]
struct MonoBitmap {
    width: usize,
    height: usize,
    left: f64,
    top: f64,
    pixels: Vec<u8>,
}

#[derive(Deserialize)]
struct MonoGlyph {
    codepoint: u32,
    bitmap: MonoBitmap,
    finalized_advance_px: f64,
}

#[derive(Deserialize)]
struct MonoPair {
    left: u32,
    right: u32,
    adjustment_px: f64,
}

#[derive(Deserialize)]
struct MonoCapture {
    schema_version: String,
    #[allow(dead_code)]
    profile: Option<String>,
    #[allow(dead_code)]
    size_px: Option<f64>,
    glyphs: Vec<MonoGlyph>,
    #[serde(default)]
    metric_pairs_on: Vec<MonoPair>,
}

#[derive(Deserialize)]
struct GrayGlyph {
    codepoint: u32,
    width: usize,
    height: usize,
    left: f64,
    top: f64,
    pixels: Vec<u8>,
    advance_26_6: i64,
}

#[derive(Deserialize)]
struct GrayKerning {
    left: u32,
    right: u32,
    adjustment_26_6: i64,
}

#[derive(Deserialize)]
struct GrayFont {
    glyphs: Vec<GrayGlyph>,
    #[serde(default)]
    kerning: Vec<GrayKerning>,
}

#[derive(Deserialize)]
struct GrayCapture {
    schema_version: String,
    font: GrayFont,
}

fn sha256_file(path: &Path) -> Result<String, EngineError> {
    let bytes =
        std::fs::read(path).map_err(|e| EngineError::Invalid(format!("read {path:?}: {e}")))?;
    // Minimal SHA-256 (FIPS 180-4) to avoid a hash dependency in this leaf.
    Ok(sha256_hex(&bytes))
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut msg = bytes.to_vec();
    let bit_len = (bytes.len() as u64).wrapping_mul(8);
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());
    for chunk in msg.chunks(64) {
        let mut w = [0u32; 64];
        for t in 0..16 {
            w[t] = u32::from_be_bytes([
                chunk[4 * t],
                chunk[4 * t + 1],
                chunk[4 * t + 2],
                chunk[4 * t + 3],
            ]);
        }
        for t in 16..64 {
            let s0 = w[t - 15].rotate_right(7) ^ w[t - 15].rotate_right(18) ^ (w[t - 15] >> 3);
            let s1 = w[t - 2].rotate_right(17) ^ w[t - 2].rotate_right(19) ^ (w[t - 2] >> 10);
            w[t] = w[t - 16]
                .wrapping_add(s0)
                .wrapping_add(w[t - 7])
                .wrapping_add(s1);
        }
        let (mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh) =
            (h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]);
        for t in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[t])
                .wrapping_add(w[t]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let mj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(mj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }
    h.iter().map(|x| format!("{x:08x}")).collect()
}

/// Load a mono or gray capture by schema version.
pub fn load_capture(name: &str, path: &Path) -> Result<Dataset, EngineError> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| EngineError::Invalid(format!("read {path:?}: {e}")))?;
    let sha256 = sha256_file(path)?;
    if text.contains("\"contextual-spacing-capture-v1\"") {
        let cap: MonoCapture = serde_json::from_str(&text)
            .map_err(|e| EngineError::Invalid(format!("mono parse {path:?}: {e}")))?;
        if cap.schema_version != "contextual-spacing-capture-v1" {
            return Err(EngineError::Invalid(format!(
                "unsupported mono schema {:?}",
                cap.schema_version
            )));
        }
        let mut cells = HashMap::new();
        for g in cap.glyphs {
            let b = g.bitmap;
            if b.pixels.len() != b.width * b.height {
                return Err(EngineError::Invalid(format!(
                    "mono bitmap length mismatch for U+{:04X}",
                    g.codepoint
                )));
            }
            cells.insert(
                g.codepoint,
                Cell {
                    w: b.width,
                    h: b.height,
                    left: b.left,
                    top: b.top,
                    cover: b
                        .pixels
                        .iter()
                        .map(|p| if *p > 0 { 1.0 } else { 0.0 })
                        .collect(),
                    advance_px: Some(g.finalized_advance_px),
                },
            );
        }
        let mut adjustments = HashMap::new();
        for p in cap.metric_pairs_on {
            adjustments.insert((p.left, p.right), p.adjustment_px);
        }
        Ok(Dataset {
            name: name.to_string(),
            profile: "mono".to_string(),
            path: path.to_string_lossy().into_owned(),
            sha256,
            cells,
            adjustments,
            advances: HashMap::new(),
        })
    } else {
        let cap: GrayCapture = serde_json::from_str(&text)
            .map_err(|e| EngineError::Invalid(format!("gray parse {path:?}: {e}")))?;
        if cap.schema_version != "contextual-spacing-grayscale-v1"
            && cap.schema_version != "contextual-spacing-grayscale-v2"
        {
            return Err(EngineError::Invalid(format!(
                "unsupported grayscale schema {:?}",
                cap.schema_version
            )));
        }
        let mut cells = HashMap::new();
        let mut advances = HashMap::new();
        for g in cap.font.glyphs {
            if g.pixels.len() != g.width * g.height {
                return Err(EngineError::Invalid(format!(
                    "gray bitmap length mismatch for U+{:04X}",
                    g.codepoint
                )));
            }
            // Delivered 3-bit Gray coverage, linear 0..1 (documented
            // assumption shared with the frozen loader).
            cells.insert(
                g.codepoint,
                Cell {
                    w: g.width,
                    h: g.height,
                    left: g.left,
                    top: g.top,
                    cover: g.pixels.iter().map(|p| f64::from(*p) / 7.0).collect(),
                    advance_px: None,
                },
            );
            advances.insert(g.codepoint, g.advance_26_6 as f64 / 64.0);
        }
        let mut adjustments = HashMap::new();
        for k in cap.font.kerning {
            adjustments.insert((k.left, k.right), k.adjustment_26_6 as f64 / 64.0);
        }
        Ok(Dataset {
            name: name.to_string(),
            profile: "gray".to_string(),
            path: path.to_string_lossy().into_owned(),
            sha256,
            cells,
            adjustments,
            advances,
        })
    }
}
