#![cfg(feature = "candidate")]
//! Source-shape preservation regressions for the Literata `t` head, cap and
//! foot at the real pipeline seam.
//!
//! Shape authority is the raw f64 SourceOutline for the existence, sign,
//! and direction of source detail; restoration is measured against the
//! 26.6-rounded source capture, the pipeline's own input representation
//! (f32 points on the observed 1/64 grid). Comparisons state their
//! quantization: exact where values are grid-representable on both sides,
//! bounded by the rounding the representation can introduce, never tuned.
//! Upstream Y stays hinter-owned and is checked for exact retention. Features are
//! located structurally from the outlines (single closed contour,
//! verified op correspondence raw and rounded); no pixel rows, preferred
//! bitmaps or tuned thresholds appear. Paper grounding: Hobby section 6
//! keeps Bezier control points as adjusted variables; Shamir section 3.2
//! requires ownership of adjoining attachments; Hersch section 2 supplies
//! the endpoint-derivative identities used for the tangent measures below.
use font_generator::{
    candidate,
    diagonal_fitting::{self, Reference},
    fitting_source::{self, SourceOutline, SourceSegment},
    probe::FittedCommand,
    reference::{reference, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting,
};
use std::collections::BTreeMap;

fn font() -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../fonts/Literata.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap()
}

fn request(characters: &str, size_px: f32) -> ReferenceRequest {
    let mut axes = BTreeMap::new();
    axes.insert("wght".to_string(), 400.0);
    axes.insert("opsz".to_string(), size_px);
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::FontHintsAuto)).into(),
        settings: Config {
            characters: characters.into(),
            size_px,
            output_bits: 1,
            hinting: StemFittingStrategy::FontHintsAuto.hinting(),
            axes,
            mono_raster: font_generator::MonoRasterSettings {
                font_instructions: true,
                include_stubs: true,
                ..Default::default()
            },
            ..Default::default()
        },
    }
}

#[derive(Clone, Copy, PartialEq, Debug)]
enum Op {
    Line,
    Quad,
    Curve,
}

#[derive(Clone, Copy, Debug)]
struct Seg {
    op: Op,
    /// Source command index, so failures cite outline positions.
    cmd: usize,
    /// On-curve endpoints in pen order; `c1`, `c2` hold off-curve controls.
    a: [f64; 2],
    b: [f64; 2],
    c1: Option<[f64; 2]>,
    c2: Option<[f64; 2]>,
}

fn pt(x: f32, y: f32) -> [f64; 2] {
    [f64::from(x), f64::from(y)]
}

/// Pen walk over one contour; fails closed on anything but a single
/// open-then-closed contour so structural drift cannot pass silently.
fn segments(cmds: &[FittedCommand]) -> Vec<Seg> {
    let mut segs = Vec::new();
    let mut pen: Option<[f64; 2]> = None;
    let mut moves = 0;
    let mut closed = false;
    for (ci, cmd) in cmds.iter().enumerate() {
        match *cmd {
            FittedCommand::MoveTo(x, y) => {
                pen = Some(pt(x, y));
                moves += 1;
            }
            FittedCommand::LineTo(x, y) => {
                let a = pen.expect("line without pen");
                segs.push(Seg {
                    op: Op::Line,
                    cmd: ci,
                    a,
                    b: pt(x, y),
                    c1: None,
                    c2: None,
                });
                pen = Some(pt(x, y));
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let a = pen.expect("quad without pen");
                segs.push(Seg {
                    op: Op::Quad,
                    cmd: ci,
                    a,
                    b: pt(x, y),
                    c1: Some(pt(x1, y1)),
                    c2: None,
                });
                pen = Some(pt(x, y));
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let a = pen.expect("curve without pen");
                segs.push(Seg {
                    op: Op::Curve,
                    cmd: ci,
                    a,
                    b: pt(x, y),
                    c1: Some(pt(x1, y1)),
                    c2: Some(pt(x2, y2)),
                });
                pen = Some(pt(x, y));
            }
            FittedCommand::Close => {
                closed = true;
            }
        }
    }
    assert_eq!(moves, 1, "expected a single contour");
    // Explicit closure only: the pen need not return to the move origin,
    // since implicit closure (Close joining the last point back to the
    // origin, as in any triangle) is valid and the neighbor walk below
    // wraps explicitly. An unterminated loop with no Close marker would
    // pass the structural gates while breaking those relations.
    assert!(closed, "contour never closes");
    segs
}

fn opcodes(cmds: &[FittedCommand]) -> Vec<u8> {
    cmds.iter()
        .map(|c| match c {
            FittedCommand::MoveTo(..) => 0,
            FittedCommand::LineTo(..) => 1,
            FittedCommand::QuadTo(..) => 2,
            FittedCommand::CurveTo(..) => 3,
            FittedCommand::Close => 4,
        })
        .collect()
}

/// Raw contour geometry alongside the op walk the rounded side is checked
/// against. The op walk carries the segment opcodes in order with a single
/// trailing Close (opcode 4): a final segment returning to the contour's
/// start index is the explicit closure edge, so it maps to Close rather
/// than entering the walk. `Parsed` contours are implicitly closed (the
/// same walk the pipeline's `loops_points` flattens), whether or not that
/// edge is listed.
struct RawWalk {
    segs: Vec<Seg>,
    ops: Vec<u8>,
    /// Whether the contour listed an explicit closing edge (degenerate
    /// or real), mapped to the trailing Close above. Needed to reverse
    /// the walk back to the original segment list.
    explicit_close: bool,
}

/// Convert one raw f64 contour to test segments. A degenerate closing
/// segment (same point) is the Close marker, not geometry; a real closing
/// edge is kept as geometry since the rounded side's Close implies it.
/// Any other zero-length segment is pathological input the locators below
/// cannot read, so it fails closed rather than being silently dropped.
fn raw_walk(raw: &SourceOutline) -> RawWalk {
    assert_eq!(
        raw.contours.len(),
        1,
        "expected a single raw contour, found {}",
        raw.contours.len()
    );
    let contour = &raw.contours[0];
    let first_a: usize = match contour.first() {
        Some(SourceSegment::Line { a, .. })
        | Some(SourceSegment::Quad { a, .. })
        | Some(SourceSegment::Cubic { a, .. }) => *a,
        None => panic!("empty raw contour"),
    };
    let mut segs = Vec::new();
    let mut ops = Vec::new();
    let mut explicit = false;
    for (i, s) in contour.iter().enumerate() {
        let is_last = i + 1 == contour.len();
        let (op, a, b, c1, c2) = match *s {
            SourceSegment::Line { a, b } => (1u8, raw.oncurve[a], raw.oncurve[b], None, None),
            SourceSegment::Quad { c, a, b } => (
                2u8,
                raw.oncurve[a],
                raw.oncurve[b],
                Some(raw.offcurve[c]),
                None,
            ),
            SourceSegment::Cubic { c1, c2, a, b } => (
                3u8,
                raw.oncurve[a],
                raw.oncurve[b],
                Some(raw.offcurve[c1]),
                Some(raw.offcurve[c2]),
            ),
        };
        if is_last && end_of(s) == first_a {
            // Explicit closure edge: maps to Close on the op walk. A
            // degenerate return carries no geometry; a real one stays in
            // the segment list where wraparound walking reaches it.
            if a != b {
                segs.push(Seg {
                    op: opcode(op),
                    cmd: i,
                    a,
                    b,
                    c1,
                    c2,
                });
            }
            ops.push(4);
            explicit = true;
        } else {
            assert!(
                a != b,
                "degenerate non-closing raw segment {i}: not the Close marker, cannot locate features on it"
            );
            segs.push(Seg {
                op: opcode(op),
                cmd: i,
                a,
                b,
                c1,
                c2,
            });
            ops.push(op);
        }
    }
    if !explicit {
        // No listed return edge: the contour is still a closed loop, so
        // the walk ends with the implicit Close the rounded side lists.
        ops.push(4);
    }
    RawWalk {
        segs,
        ops,
        explicit_close: explicit,
    }
}

/// End index of a raw segment: the closure edge is the final segment
/// returning here to the contour's start index.
fn end_of(s: &SourceSegment) -> usize {
    match *s {
        SourceSegment::Line { b, .. } => b,
        SourceSegment::Quad { b, .. } => b,
        SourceSegment::Cubic { b, .. } => b,
    }
}

/// Opcode number to segment op, mirroring `opcodes` above.
fn opcode(code: u8) -> Op {
    match code {
        1 => Op::Line,
        2 => Op::Quad,
        _ => Op::Curve,
    }
}

/// Bounding box over every outline point, controls included.
fn bbox(segs: &[Seg]) -> ([f64; 2], [f64; 2]) {
    let mut lo = [f64::INFINITY, f64::INFINITY];
    let mut hi = [f64::NEG_INFINITY, f64::NEG_INFINITY];
    let mut eat = |p: [f64; 2]| {
        for k in 0..2 {
            lo[k] = lo[k].min(p[k]);
            hi[k] = hi[k].max(p[k]);
        }
    };
    for s in segs {
        eat(s.a);
        eat(s.b);
        if let Some(c) = s.c1 {
            eat(c);
        }
        if let Some(c) = s.c2 {
            eat(c);
        }
    }
    (lo, hi)
}

/// Maximal contiguous quad-command ranges, by segment index.
fn quad_runs(segs: &[Seg]) -> Vec<std::ops::Range<usize>> {
    let mut runs = Vec::new();
    let mut start: Option<usize> = None;
    for (i, s) in segs.iter().enumerate() {
        if s.op == Op::Quad {
            if start.is_none() {
                start = Some(i);
            }
        } else if let Some(st) = start.take() {
            runs.push(st..i);
        }
    }
    if let Some(st) = start {
        runs.push(st..segs.len());
    }
    runs
}

/// The upper head chain: the single contiguous quad run lying wholly above
/// the outline's vertical center, extended over immediately adjacent
/// vertical connector lines. Returns the chain segment range, the X extent
/// over every chain point, the top quad's endpoint-tangent dx (Hersch
/// section 2: endpoint derivative from control to endpoint), and the top
/// quad's curvature sign.
fn head_chain(segs: &[Seg]) -> (std::ops::Range<usize>, f64, f64, f64) {
    let (lo, hi) = bbox(segs);
    let center = (lo[1] + hi[1]) / 2.0;
    let mut found = None;
    for run in quad_runs(segs) {
        let ymin = run
            .clone()
            .fold(f64::INFINITY, |m, i| m.min(segs[i].a[1]).min(segs[i].b[1]));
        if ymin > center {
            assert!(found.is_none(), "expected one upper quad run");
            found = Some(run);
        }
    }
    let run = found.expect("no upper quad run above outline center");
    let mut lo_i = run.start;
    while lo_i > 0 {
        match segs[lo_i - 1] {
            Seg {
                op: Op::Line, a, b, ..
            } if a[0] == b[0] => lo_i -= 1,
            _ => break,
        }
    }
    let mut hi_i = run.end;
    while hi_i < segs.len() {
        match segs[hi_i] {
            Seg {
                op: Op::Line, a, b, ..
            } if a[0] == b[0] => hi_i += 1,
            _ => break,
        }
    }
    let range = lo_i..hi_i;
    let mut xlo = f64::INFINITY;
    let mut xhi = f64::NEG_INFINITY;
    let mut eat = |p: [f64; 2]| {
        xlo = xlo.min(p[0]);
        xhi = xhi.max(p[0]);
    };
    for s in &segs[range.clone()] {
        eat(s.a);
        eat(s.b);
        if let Some(c) = s.c1 {
            eat(c);
        }
        if let Some(c) = s.c2 {
            eat(c);
        }
    }
    let top = segs[run.end - 1];
    assert_eq!(top.op, Op::Quad, "run must end in a quad");
    let c = top.c1.unwrap();
    let dx = top.b[0] - c[0];
    let cross =
        (c[0] - top.a[0]) * (top.b[1] - top.a[1]) - (c[1] - top.a[1]) * (top.b[0] - top.a[0]);
    (range, xhi - xlo, dx, cross)
}

/// The cap vertex: the unique highest vertex with two incident straight
/// segments. Reports its horizontal-run fraction left/(left+right).
fn cap_vertex(segs: &[Seg]) -> ([f64; 2], [f64; 2], [f64; 2], f64) {
    let ymax = segs
        .iter()
        .fold(f64::NEG_INFINITY, |m, s| m.max(s.a[1]).max(s.b[1]));
    let n = segs.len();
    let at = |i: usize| &segs[i % n];
    let mut found = None;
    for (i, s) in segs.iter().enumerate() {
        if s.b[1] != ymax {
            continue;
        }
        // The vertex is `s.b`; its incoming edge is `s` itself.
        let next = at((i + 1) % n);
        if !matches!(s.op, Op::Line) || !matches!(next.op, Op::Line) {
            continue;
        }
        assert!(found.is_none(), "expected one straight-sided top vertex");
        found = Some((s.a, s.b, next.b));
    }
    let (p, v, q) = found.expect("no straight-sided top vertex");
    assert!(
        p[0] < v[0] && v[0] < q[0],
        "cap vertex must sit between its borders"
    );
    let (left, right) = (v[0] - p[0], q[0] - v[0]);
    (p, v, q, left / (left + right))
}

fn cross(a: [f64; 2], c: [f64; 2], b: [f64; 2]) -> f64 {
    (c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])
}

struct Stage {
    source: Vec<FittedCommand>,
    upstream: Vec<FittedCommand>,
    candidate: Vec<FittedCommand>,
    raw: RawWalk,
    /// Genuine f64 outline the walk above was converted from; kept so
    /// kernel inputs and walk round-trips share one drawing.
    raw_source: SourceOutline,
}

fn outlines(size_px: f32) -> Stage {
    let data = font();
    let settings = request("t", size_px).settings;
    let report = candidate::render_with_pipeline(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::FontHintsAuto))
                .into(),
            settings: settings.clone(),
        },
        RenderPipeline {
            fitting: StemFittingStrategy::FontHintsAuto,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: true,
        },
    )
    .unwrap();
    let record = report
        .records
        .iter()
        .find(|r| r.codepoint == 116)
        .expect("t record");
    let diagonal = record
        .diagonal_fitting
        .as_ref()
        .expect("t must carry the diagonal capture");
    let mut source_settings = settings;
    source_settings.hinting = Hinting::None;
    source_settings.mono_raster = Default::default();
    let source = reference(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "none".into(),
            settings: source_settings.clone(),
        },
    )
    .unwrap();
    let srec = source
        .records
        .iter()
        .find(|r| r.codepoint == 116)
        .expect("t source");
    // Raw f64 outline: the same glyph at the same size/axes, unrounded.
    // `draw` reads size and axes only; hinting flags do not enter.
    let raw_source = fitting_source::draw(&data, &source_settings, record.glyph_id)
        .expect("raw source draw for t");
    let raw = raw_walk(&raw_source);
    let stage = Stage {
        source: srec.fitted_commands.clone(),
        upstream: diagonal.upstream_commands.clone(),
        candidate: record.fitted_commands.clone(),
        raw,
        raw_source,
    };
    // Raw/rounded op correspondence: same operations in order, the same
    // single contour (one leading MoveTo), the same single Close.
    assert_eq!(
        opcodes(&stage.source)[1..],
        stage.raw.ops[..],
        "raw/rounded command correspondence changed"
    );
    assert_eq!(
        opcodes(&stage.source),
        opcodes(&stage.upstream),
        "source/upstream command correspondence changed"
    );
    assert_eq!(
        opcodes(&stage.source),
        opcodes(&stage.candidate),
        "source/candidate command correspondence changed"
    );
    stage
}

/// Quad indices whose control or endpoints the stage moved
/// (candidate versus upstream, exact coordinate comparison).
fn moved_quads(stage: &Stage) -> Vec<usize> {
    let (su, sc) = (segments(&stage.upstream), segments(&stage.candidate));
    assert_eq!(su.len(), sc.len(), "segment count changed");
    su.iter()
        .zip(sc.iter())
        .enumerate()
        .filter(|(_, (u, c))| {
            matches!(u.op, Op::Quad) && (u.a != c.a || u.b != c.b || u.c1 != c.c1 || u.c2 != c.c2)
        })
        .map(|(i, _)| i)
        .collect()
}

fn quad_cross(segs: &[Seg], i: usize) -> f64 {
    let s = segs[i];
    assert_eq!(s.op, Op::Quad, "expected quad at {i}");
    cross(s.a, s.c1.unwrap(), s.b)
}

#[test]
fn head_chain_restores_source_profile() {
    // The auto-hinter flattens the upper-left profile and the current
    // stage preserves that flattening rigidly; restoration must bring
    // back the source X extent and the endpoint tangent's horizontal
    // component. Both values are read off the source outline itself.
    for size in [15.0f32, 16.0] {
        let stage = outlines(size);
        let (src, up, cand) = (
            segments(&stage.source),
            segments(&stage.upstream),
            segments(&stage.candidate),
        );
        let (_, src_extent, src_dx, src_cross) = head_chain(&src);
        let (_, up_extent, up_dx, _) = head_chain(&up);
        let (_, cand_extent, cand_dx, cand_cross) = head_chain(&cand);
        assert_ne!(src_cross, 0.0, "source comparison quad degenerate");
        assert_ne!(cand_cross, 0.0, "candidate comparison quad degenerate");
        // Raw authority for the detail under test: the same chain located
        // on the raw f64 outline is a non-degenerate curve, and its
        // endpoint tangent (Hersch section 2) is nonzero with the same
        // sign the rounded capture shows. Restoration can only be demanded
        // of detail that exists and survives quantization.
        let (_, raw_extent, raw_dx, raw_cross) = head_chain(&stage.raw.segs);
        assert_ne!(raw_cross, 0.0, "raw head quad degenerate");
        // The rounded capture sits on the 1/64 grid (the pipeline's 26.6
        // representation); under the nearest mapping the captures show,
        // each chain endpoint contributes at most half a quantum, so the
        // extent tracks raw within one quantum. A larger gap would mean
        // the capture no longer describes the source outline.
        assert!(
            (src_extent - raw_extent).abs() <= 1.0 / 64.0,
            "rounded/raw head extent split at {size}px: raw {raw_extent}, rounded {src_extent}"
        );
        assert!(
            raw_dx != 0.0 && src_dx != 0.0 && (raw_dx > 0.0) == (src_dx > 0.0),
            "head tangent detail lost to quantization at {size}px: raw {raw_dx}, rounded {src_dx}"
        );
        // Necessary under any restoration contract, in the rounded domain:
        // where the source capture differs from upstream, the candidate
        // must move off the flattened upstream values toward source on
        // both components. A restoration that changes nothing, or moves
        // away, restores nothing.
        for (name, s, u, c) in [
            ("extent", src_extent, up_extent, cand_extent),
            ("tangent dx", src_dx, up_dx, cand_dx),
        ] {
            if s != u {
                let towards = (c - u) != 0.0 && (c - u).signum() == (s - u).signum();
                assert!(
                    towards,
                    "head chain {name} not moved toward source at {size}px: source {s}, upstream {u}, candidate {c}"
                );
            }
        }
    }
}

#[test]
fn cap_anchor_keeps_source_relative_position() {
    // A vertex stationary between differentially moved neighbors warps
    // its relative anchor (source share 81% to candidate 54%). The stage
    // must move it under ownership or justify the fixed point, never
    // leave an incidental zero displacement (Shamir section 3.2).
    for size in [15.0f32, 16.0] {
        let stage = outlines(size);
        let (src, up, cand) = (
            segments(&stage.source),
            segments(&stage.upstream),
            segments(&stage.candidate),
        );
        let src_cap = cap_vertex(&src);
        let up_cap = cap_vertex(&up);
        let cand_cap = cap_vertex(&cand);
        // The same straight-sided peak must exist on the raw outline;
        // its share is the asserted ratio below, the rounded shares are
        // provenance for the warp.
        let raw_cap = cap_vertex(&stage.raw.segs);
        let frac = |cap: ([f64; 2], [f64; 2], [f64; 2], f64)| cap.3;
        let stationary = cand_cap.1 == up_cap.1;
        let dl = cand_cap.0[0] - up_cap.0[0];
        let dr = cand_cap.2[0] - up_cap.2[0];
        assert!(
            !(stationary && dl != dr),
            "cap anchor warped at {size}px: vertex stationary while neighbors moved {dl} and {dr}; share raw {}, source {}, upstream {}, candidate {}",
            frac(raw_cap),
            frac(src_cap),
            frac(up_cap),
            frac(cand_cap)
        );
        // Shamir 3.2 hard relative position from the raw source triple:
        // the cap vertex must divide its owned interval in the raw ratio
        // f, wherever the stage moved its owners. Hersch endpoint
        // coordinates reach the 26.6 grid by quantization (half a quantum
        // each); the Bernstein interpolation weights the two neighbor
        // errors by |1-f| and |f|, and placing the vertex itself costs
        // half a quantum more — half-quantum*(1+|1-f|+|f|), one quantum
        // for a strictly interior peak. Compared against the raw ratio,
        // never the rounded capture.
        let f = frac(raw_cap);
        let expected = (1.0 - f) * cand_cap.0[0] + f * cand_cap.2[0];
        let residual = (cand_cap.1[0] - expected).abs();
        let allowance = 0.5 / 64.0 * (1.0 + (1.0 - f).abs() + f.abs());
        assert!(
            residual <= allowance,
            "cap ratio broken at {size}px: raw f {f}, vertex {} against owned [{}, {}], residual {residual} over {allowance}",
            cand_cap.1[0],
            cand_cap.0[0],
            cand_cap.2[0]
        );
    }
}

#[test]
fn moved_quads_keep_source_curvature_sign() {
    // Whole-interval tangent and curvature certification for every quad
    // with a moved control or an endpoint adjacent to differential
    // motion; sign is binary, so no threshold is involved. Upstream
    // preserved the source sign here, so a flip is new damage, not an
    // inherited simplification.
    for size in [15.0f32, 16.0] {
        let stage = outlines(size);
        let (src, up, cand) = (
            segments(&stage.source),
            segments(&stage.upstream),
            segments(&stage.candidate),
        );
        for i in moved_quads(&stage) {
            let (s, u, c) = (
                quad_cross(&src, i),
                quad_cross(&up, i),
                quad_cross(&cand, i),
            );
            if s == 0.0 {
                continue;
            }
            // The rounded capture must keep the raw sign where both
            // resolve the curve; a rounding flip would make the sign
            // below assert a quantization artifact, not stage damage.
            let r = quad_cross(&stage.raw.segs, i);
            if r != 0.0 {
                assert!(
                    (s > 0.0) == (r > 0.0),
                    "rounding flipped source curvature sign at command {} ({size}px): raw {r}, rounded {s}",
                    cand[i].cmd
                );
            }
            assert!(
                (c > 0.0) == (s > 0.0),
                "curvature sign flip at command {} ({size}px): source {s}, upstream {u}, candidate {c}",
                cand[i].cmd
            );
        }
    }
}

#[test]
fn chain_measures_detect_translation_and_flattening() {
    // Control for the structural measures above: translation invariance
    // proves they read shape, flattening sensitivity proves a lost
    // horizontal component cannot pass unnoticed.
    let chain = vec![
        FittedCommand::MoveTo(1.0, 0.0),
        FittedCommand::LineTo(1.0, 6.0),
        FittedCommand::QuadTo(1.5, 6.5, 2.0, 7.0),
        FittedCommand::QuadTo(2.5, 7.5, 3.0, 8.0),
        FittedCommand::QuadTo(3.5, 8.5, 4.0, 9.0),
        FittedCommand::LineTo(6.0, 0.0),
        FittedCommand::Close,
    ];
    let measure = |cmds: &[FittedCommand]| head_chain(&segments(cmds));
    let (_, base_extent, base_dx, _) = measure(&chain);
    let shifted: Vec<FittedCommand> = chain
        .iter()
        .map(|c| match *c {
            FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x + 5.25, y - 3.125),
            FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x + 5.25, y - 3.125),
            FittedCommand::QuadTo(x1, y1, x, y) => {
                FittedCommand::QuadTo(x1 + 5.25, y1 - 3.125, x + 5.25, y - 3.125)
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => FittedCommand::CurveTo(
                x1 + 5.25,
                y1 - 3.125,
                x2 + 5.25,
                y2 - 3.125,
                x + 5.25,
                y - 3.125,
            ),
            FittedCommand::Close => FittedCommand::Close,
        })
        .collect();
    let (_, moved_extent, moved_dx, _) = measure(&shifted);
    assert_eq!(
        moved_extent, base_extent,
        "extent must be translation invariant"
    );
    assert_eq!(moved_dx, base_dx, "tangent must be translation invariant");
    // Same closed loop entered at a different vertex must read
    // identically: the chain locators walk the loop, not a command list.
    let rotated = vec![
        FittedCommand::MoveTo(6.0, 0.0),
        FittedCommand::LineTo(1.0, 0.0),
        FittedCommand::LineTo(1.0, 6.0),
        FittedCommand::QuadTo(1.5, 6.5, 2.0, 7.0),
        FittedCommand::QuadTo(2.5, 7.5, 3.0, 8.0),
        FittedCommand::QuadTo(3.5, 8.5, 4.0, 9.0),
        FittedCommand::Close,
    ];
    let (_, rot_extent, rot_dx, _) = measure(&rotated);
    assert_eq!(
        base_extent, rot_extent,
        "extent must not depend on loop entry"
    );
    assert_eq!(base_dx, rot_dx, "tangent must not depend on loop entry");
    let mut flat = chain.clone();
    for c in &mut flat {
        match c {
            FittedCommand::QuadTo(x1, _, x, _) => {
                *x1 = 1.0 + (*x1 - 1.0) * 0.7;
                *x = 1.0 + (*x - 1.0) * 0.7;
            }
            FittedCommand::MoveTo(x, _) | FittedCommand::LineTo(x, _) => {
                *x = 1.0 + (*x - 1.0) * 0.7;
            }
            _ => {}
        }
    }
    let (_, flat_extent, flat_dx, _) = measure(&flat);
    assert!(flat_extent < base_extent, "extent must detect flattening");
    assert_ne!(flat_dx, base_dx, "tangent must detect flattening");
}

/// f32 round-trip of an f64 pipeline value: the rounded side is
/// f32-native, so any value that is not exactly representable would
/// expose a lossy cast here rather than in the kernel below.
fn f32_exact(v: f64) -> f32 {
    assert!(
        (v as f32) as f64 == v,
        "non-f32 pipeline value {v}: casts would round the kernel input"
    );
    v as f32
}

/// Reverse `segments` for one closed contour: re-seal with Close, which
/// `parse_commands` expands back to the same segment list.
fn emit_commands(segs: &[Seg]) -> Vec<FittedCommand> {
    assert!(!segs.is_empty(), "nothing to emit");
    let mut cmds = vec![FittedCommand::MoveTo(
        f32_exact(segs[0].a[0]),
        f32_exact(segs[0].a[1]),
    )];
    for s in segs {
        match s.op {
            Op::Line => cmds.push(FittedCommand::LineTo(f32_exact(s.b[0]), f32_exact(s.b[1]))),
            Op::Quad => {
                let c = s.c1.expect("quad without control");
                cmds.push(FittedCommand::QuadTo(
                    f32_exact(c[0]),
                    f32_exact(c[1]),
                    f32_exact(s.b[0]),
                    f32_exact(s.b[1]),
                ));
            }
            Op::Curve => {
                let (c1, c2) = (s.c1.expect("curve c1"), s.c2.expect("curve c2"));
                cmds.push(FittedCommand::CurveTo(
                    f32_exact(c1[0]),
                    f32_exact(c1[1]),
                    f32_exact(c2[0]),
                    f32_exact(c2[1]),
                    f32_exact(s.b[0]),
                    f32_exact(s.b[1]),
                ));
            }
        }
    }
    cmds.push(FittedCommand::Close);
    cmds
}

/// Reverse `raw_walk`: vertices and controls in walk order (the source
/// emits controls in walk order, so numbering is preserved), with the
/// explicit closing alias restored when the walk mapped one to Close.
fn emit_raw(walk: &RawWalk) -> SourceOutline {
    assert!(!walk.segs.is_empty(), "nothing to emit");
    let mut oncurve = vec![walk.segs[0].a];
    for s in &walk.segs {
        oncurve.push(s.b);
    }
    let mut offcurve = Vec::new();
    let mut contour = Vec::new();
    for (j, s) in walk.segs.iter().enumerate() {
        match s.op {
            Op::Line => contour.push(SourceSegment::Line { a: j, b: j + 1 }),
            Op::Quad => {
                offcurve.push(s.c1.expect("quad without control"));
                contour.push(SourceSegment::Quad {
                    c: offcurve.len() - 1,
                    a: j,
                    b: j + 1,
                });
            }
            Op::Curve => {
                let (c1, c2) = (s.c1.expect("curve c1"), s.c2.expect("curve c2"));
                offcurve.push(c1);
                offcurve.push(c2);
                contour.push(SourceSegment::Cubic {
                    c1: offcurve.len() - 2,
                    c2: offcurve.len() - 1,
                    a: j,
                    b: j + 1,
                });
            }
        }
    }
    if walk.explicit_close {
        // The listed return edge: same point alias the forward walk
        // dropped, restored with the original index shape.
        contour.push(SourceSegment::Line {
            a: oncurve.len() - 1,
            b: 0,
        });
    }
    SourceOutline {
        oncurve,
        offcurve,
        contours: vec![contour],
    }
}

/// Quad indices moved between two command lists with the same op walk
/// (candidate versus upstream, exact coordinate comparison).
fn moved_between(old: &[FittedCommand], new: &[FittedCommand]) -> Vec<usize> {
    let (a, b) = (segments(old), segments(new));
    assert_eq!(a.len(), b.len(), "segment count changed");
    a.iter()
        .zip(b.iter())
        .enumerate()
        .filter(|(_, (u, c))| {
            matches!(u.op, Op::Quad) && (u.a != c.a || u.b != c.b || u.c1 != c.c1 || u.c2 != c.c2)
        })
        .map(|(i, _)| i)
        .collect()
}

/// Genuine kernel inputs from one pipeline render: raw f64, rounded
/// captured source, and upstream share the glyph, size, axes, and
/// pipeline; the reference is built from genuine donor captures with
/// the pipeline's own builder.
struct KernelCase {
    raw: SourceOutline,
    captured: Vec<FittedCommand>,
    upstream: Vec<FittedCommand>,
    reference: Reference,
}

/// The pipeline's frozen donor set (candidate::DIAGONAL_DONORS, private
/// there; repeated here so the test renders the same glyphs).
const DONORS: &str = "itflInhkyxzvAVW";

fn donor_reference(size_px: f32) -> Reference {
    let data = font();
    let settings = request(DONORS, size_px).settings;
    // Unhinted source leg, mirroring the pipeline's donor source leg.
    let mut src_settings = settings.clone();
    src_settings.hinting = Hinting::None;
    src_settings.mono_raster = Default::default();
    let source = reference(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "none".into(),
            settings: src_settings,
        },
    )
    .expect("donor source render");
    // Fitted upstream leg: the pipeline without the diagonal stage.
    let fitted = candidate::render_with_pipeline(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::FontHintsAuto))
                .into(),
            settings,
        },
        RenderPipeline {
            fitting: StemFittingStrategy::FontHintsAuto,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: false,
        },
    )
    .expect("donor upstream render");
    let mut pairs = Vec::new();
    for ch in DONORS.chars() {
        let cp = ch as u32;
        let raw = source
            .records
            .iter()
            .find(|r| r.codepoint == cp)
            .expect("donor source record");
        let fit = fitted
            .records
            .iter()
            .find(|r| r.codepoint == cp)
            .expect("donor upstream record");
        // Same glyph-identity discipline as the pipeline's donor pairing:
        // a missing or substituted donor must fail loudly, never pair.
        assert!(
            raw.glyph_id != 0 && raw.glyph_id == fit.glyph_id,
            "donor glyph identity changed for U+{cp:04X}"
        );
        pairs.push((
            raw.fitted_commands.as_slice(),
            fit.fitted_commands.as_slice(),
        ));
    }
    diagonal_fitting::build_reference(&pairs, f64::from(size_px))
}

fn kernel_case(size_px: f32) -> KernelCase {
    let stage = outlines(size_px);
    KernelCase {
        raw: stage.raw_source,
        captured: stage.source,
        upstream: stage.upstream,
        reference: donor_reference(size_px),
    }
}

fn call_kernel(
    raw: &SourceOutline,
    captured: &[FittedCommand],
    upstream: &[FittedCommand],
    reference: &Reference,
    native_axes: [bool; 2],
    size_px: f64,
) -> font_generator::diagonal_fitting::FitResult {
    diagonal_fitting::coupled::automatic_shape(
        raw,
        captured,
        upstream,
        size_px,
        reference,
        native_axes,
    )
    .expect("kernel error")
}

#[test]
fn explicit_shape_diagnostics_preserve_selection_and_fallback() {
    let case = kernel_case(16.0);
    // A positive X dilation retains topology and the 26.6 grid but puts the
    // source-relative target beyond the original movement budget. This is a
    // geometric failure control, not a different production fitting rule.
    let dilated: Vec<_> = case
        .upstream
        .iter()
        .map(|command| match *command {
            FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(4.0 * x, y),
            FittedCommand::LineTo(x, y) => FittedCommand::LineTo(4.0 * x, y),
            FittedCommand::QuadTo(cx, cy, x, y) => FittedCommand::QuadTo(4.0 * cx, cy, 4.0 * x, y),
            FittedCommand::CurveTo(cx, cy, dx, dy, x, y) => {
                FittedCommand::CurveTo(4.0 * cx, cy, 4.0 * dx, dy, 4.0 * x, y)
            }
            FittedCommand::Close => FittedCommand::Close,
        })
        .collect();
    for upstream in [&case.upstream, &dilated] {
        let production = call_kernel(
            &case.raw,
            &case.captured,
            upstream,
            &case.reference,
            [false, false],
            16.0,
        );
        let diagnostic = diagonal_fitting::curve_model::diagnose_automatic_shape(
            &case.raw,
            &case.captured,
            upstream,
            16.0,
            &case.reference,
            [false, false],
        )
        .unwrap();
        assert_eq!(production.applied, diagnostic.applied);
        assert_eq!(production.reason, diagnostic.reason);
        assert_eq!(production.commands, diagnostic.commands);
        if upstream == &case.upstream {
            assert!(production.applied);
            assert_eq!(production.diagnostics, diagnostic.diagnostics);
        } else {
            assert!(!production.applied);
            assert!(
                production.reason.starts_with("shape:shape-solve-"),
                "{}",
                production.reason
            );
            assert_eq!(production.commands, *upstream);
            assert!(production.diagnostics.get("witness").is_none());
            assert!(production.diagnostics.get("finite_retry_ok").is_none());
            assert!(production.diagnostics.get("caps").is_some());
            assert!(diagnostic.diagnostics["witness"]["mat"].is_array());
            assert!(diagnostic.diagnostics["finite_retry_ok"].is_boolean());
        }
    }
}

#[test]
fn walks_reverse_to_bit_identical_outlines() {
    // Control for the test machinery itself: the forward walks lose
    // nothing, so every raw assert above reads the genuine outline.
    let stage = outlines(16.0);
    for cmds in [&stage.source, &stage.upstream, &stage.candidate]
        .iter()
        .copied()
    {
        assert_eq!(emit_commands(&segments(cmds)), *cmds);
    }
    let back = emit_raw(&stage.raw);
    assert_eq!(back.oncurve, stage.raw_source.oncurve);
    assert_eq!(back.offcurve, stage.raw_source.offcurve);
    assert_eq!(back.contours, stage.raw_source.contours);
}

#[test]
fn kernel_native_axes_fall_back_exact() {
    // Any native axis conflicts with the automatic route: exact
    // upstream fallback, no partial application.
    let case = kernel_case(16.0);
    for axes in [[true, false], [false, true], [true, true]] {
        let out = call_kernel(
            &case.raw,
            &case.captured,
            &case.upstream,
            &case.reference,
            axes,
            16.0,
        );
        assert!(!out.applied, "kernel applied under native axes {axes:?}");
        assert_eq!(out.commands, case.upstream);
    }
}

#[test]
fn kernel_missing_standard_falls_back_exact() {
    // No certified standard (empty anchor list, exactly what the
    // reference builder yields when no donor certifies): exact upstream
    // fallback. A conflicting certificate set funnels to the same
    // `None` standard and the same fallback.
    let case = kernel_case(16.0);
    let empty = Reference {
        anchors: Vec::new(),
        size_px: 16.0,
        records: 0,
        n_anchors: 0,
        rel_min: None,
        rel_max: None,
        notes: Vec::new(),
    };
    let out = call_kernel(
        &case.raw,
        &case.captured,
        &case.upstream,
        &empty,
        [false, false],
        16.0,
    );
    assert!(!out.applied, "kernel applied without a standard");
    assert_eq!(out.commands, case.upstream);
}

/// Shift every X of a command list by an integer grid step (exact on
/// the f32 grid values the pipeline emits).
fn shift_commands(cmds: &[FittedCommand], dx: f32) -> Vec<FittedCommand> {
    cmds.iter()
        .map(|c| match *c {
            FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x + dx, y),
            FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x + dx, y),
            FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(x1 + dx, y1, x + dx, y),
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                FittedCommand::CurveTo(x1 + dx, y1, x2 + dx, y2, x + dx, y)
            }
            FittedCommand::Close => FittedCommand::Close,
        })
        .collect()
}

/// Shift a raw outline in X. The f32 grid sides translate bitwise
/// (asserted by the caller); the f64 side carries up to one ulp of
/// translation noise on full-precision variation tails, which the
/// covariance property absorbs — a kernel that amplifies it into a
/// different grid output is genuinely non-robust.
fn shift_case(case: &KernelCase, dx: f64, dx32: f32) -> KernelCase {
    let raw = SourceOutline {
        oncurve: case
            .raw
            .oncurve
            .iter()
            .map(|&p| [p[0] + dx, p[1]])
            .collect(),
        offcurve: case
            .raw
            .offcurve
            .iter()
            .map(|&p| [p[0] + dx, p[1]])
            .collect(),
        contours: case.raw.contours.clone(),
    };
    KernelCase {
        raw,
        captured: shift_commands(&case.captured, dx32),
        upstream: shift_commands(&case.upstream, dx32),
        reference: Reference {
            anchors: case.reference.anchors.clone(),
            size_px: case.reference.size_px,
            records: case.reference.records,
            n_anchors: case.reference.n_anchors,
            rel_min: case.reference.rel_min,
            rel_max: case.reference.rel_max,
            notes: case.reference.notes.clone(),
        },
    }
}

#[test]
fn kernel_output_covaries_with_integer_x_translation() {
    // The kernel is posed in relations, not places (Hobby 3.1: the
    // coupled assembly solves displacements; every gate compares
    // widths, counts, or index graphs). Shifting every input outline by
    // one integer X step must shift the output by the same step,
    // whether the kernel applies or abstains. Integer steps preserve
    // fractional phases exactly on the grid sides; the raw side carries
    // at most one ulp of translation noise, which the property absorbs.
    let case = kernel_case(16.0);
    let (dx, dx32) = (8.0f64, 8.0f32);
    for cmds in [&case.captured, &case.upstream] {
        for c in cmds.iter() {
            let mut xs = Vec::new();
            match *c {
                FittedCommand::MoveTo(x, _) | FittedCommand::LineTo(x, _) => xs.push(x),
                FittedCommand::QuadTo(x1, _, x, _) => xs.extend([x1, x]),
                FittedCommand::CurveTo(x1, _, x2, _, x, _) => xs.extend([x1, x2, x]),
                FittedCommand::Close => {}
            }
            for x in xs {
                assert!((x + dx32) - dx32 == x, "command translation inexact at {x}");
            }
        }
    }
    let moved = shift_case(&case, dx, dx32);
    let a = call_kernel(
        &case.raw,
        &case.captured,
        &case.upstream,
        &case.reference,
        [false, false],
        16.0,
    );
    let b = call_kernel(
        &moved.raw,
        &moved.captured,
        &moved.upstream,
        &moved.reference,
        [false, false],
        16.0,
    );
    assert_eq!(
        a.applied, b.applied,
        "translation changed the kernel branch"
    );
    assert_eq!(shift_commands(&b.commands, -dx32), a.commands);
}

#[test]
fn kernel_applies_source_shape_correction() {
    // Kernel consumers receive the same source relationships and retained
    // upstream Y as the integrated renderer route.
    let case = kernel_case(16.0);
    let out = call_kernel(
        &case.raw,
        &case.captured,
        &case.upstream,
        &case.reference,
        [false, false],
        16.0,
    );
    assert!(out.applied, "kernel abstained");
    assert_ne!(out.commands, case.upstream, "kernel applied without change");
    let (src, up, res) = (
        segments(&case.captured),
        segments(&case.upstream),
        segments(&out.commands),
    );
    for (upstream, candidate) in up.iter().zip(&res) {
        for (u, c) in [
            (Some(upstream.a), Some(candidate.a)),
            (Some(upstream.b), Some(candidate.b)),
            (upstream.c1, candidate.c1),
            (upstream.c2, candidate.c2),
        ] {
            assert_eq!(u.is_some(), c.is_some(), "control correspondence changed");
            if let (Some(u), Some(c)) = (u, c) {
                assert_eq!(c[1].to_bits(), u[1].to_bits(), "upstream Y changed");
                for coordinate in c {
                    assert_eq!(
                        coordinate * 64.0,
                        (coordinate * 64.0).round(),
                        "candidate left the 26.6 grid"
                    );
                }
            }
        }
    }
    let (_, src_extent, src_dx, _) = head_chain(&src);
    let (_, up_extent, up_dx, _) = head_chain(&up);
    let (_, res_extent, res_dx, res_cross) = head_chain(&res);
    assert_ne!(res_cross, 0.0, "kernel head quad degenerate");
    for (name, s, u, c) in [
        ("extent", src_extent, up_extent, res_extent),
        ("tangent dx", src_dx, up_dx, res_dx),
    ] {
        if s != u {
            let towards = (c - u) != 0.0 && (c - u).signum() == (s - u).signum();
            assert!(
                towards,
                "kernel head chain {name} not moved toward source: source {s}, upstream {u}, kernel {c}"
            );
        }
    }
    let (src_cap, up_cap, res_cap) = (cap_vertex(&src), cap_vertex(&up), cap_vertex(&res));
    // The same peak located on the raw kernel input, by the same
    // structural rule: the asserted ratio below is raw-source.
    let raw_cap = cap_vertex(&raw_walk(&case.raw).segs);
    let frac = |cap: ([f64; 2], [f64; 2], [f64; 2], f64)| cap.3;
    let stationary = res_cap.1 == up_cap.1;
    let dl = res_cap.0[0] - up_cap.0[0];
    let dr = res_cap.2[0] - up_cap.2[0];
    assert!(
        !(stationary && dl != dr),
        "kernel cap anchor warped: vertex stationary while neighbors moved {dl} and {dr}; share raw {}, source {}, upstream {}, kernel {}",
        frac(raw_cap),
        frac(src_cap),
        frac(up_cap),
        frac(res_cap)
    );
    // Shamir 3.2 hard relative position, as in the pipeline cap test: a
    // nonzero move to the wrong place must fail as clearly as no move.
    let f = frac(raw_cap);
    let expected = (1.0 - f) * res_cap.0[0] + f * res_cap.2[0];
    let residual = (res_cap.1[0] - expected).abs();
    let allowance = 0.5 / 64.0 * (1.0 + (1.0 - f).abs() + f.abs());
    assert!(
        residual <= allowance,
        "kernel cap ratio broken: raw f {f}, vertex {} against owned [{}, {}], residual {residual} over {allowance}",
        res_cap.1[0],
        res_cap.0[0],
        res_cap.2[0]
    );
    for i in moved_between(&case.upstream, &out.commands) {
        let (s, u, c) = (quad_cross(&src, i), quad_cross(&up, i), quad_cross(&res, i));
        if s == 0.0 {
            continue;
        }
        assert!(
            (c > 0.0) == (s > 0.0),
            "kernel curvature sign flip at command {}: source {s}, upstream {u}, kernel {c}",
            res[i].cmd
        );
    }
}

#[test]
fn kernel_competing_faults_keep_boundary_precedence() {
    let case = kernel_case(16.0);
    let mut empty = case.reference.clone();
    empty.anchors.clear();
    for size in [0.0, -1.0, f64::NAN, f64::INFINITY] {
        let result = diagonal_fitting::coupled::automatic_shape(
            &case.raw,
            &case.captured,
            &case.upstream,
            size,
            &empty,
            [true, true],
        );
        match result {
            Err(error) => assert_eq!(error.0, "curve model requires finite positive size"),
            Ok(_) => panic!("invalid size bypassed the hard boundary under native ownership"),
        }
    }
    let malformed = vec![FittedCommand::LineTo(0.0, 0.0)];
    let mut off_grid = case.upstream.clone();
    match &mut off_grid[0] {
        FittedCommand::MoveTo(x, _) => *x += 1.0 / 128.0,
        _ => panic!("fixture must start with a move"),
    }
    let mut mismatch = case.raw.clone();
    mismatch.contours.push(case.raw.contours[0].clone());
    for (raw, captured, upstream, axes, reason) in [
        (
            &case.raw,
            case.captured.as_slice(),
            malformed.as_slice(),
            [true, false],
            "automatic-axes-required",
        ),
        (
            &case.raw,
            case.captured.as_slice(),
            malformed.as_slice(),
            [false, false],
            "malformed-commands",
        ),
        (
            &mismatch,
            case.captured.as_slice(),
            case.upstream.as_slice(),
            [false, false],
            "unsupported-correspondence",
        ),
        (
            &case.raw,
            malformed.as_slice(),
            off_grid.as_slice(),
            [false, false],
            "upstream-not-26.6",
        ),
        (
            &case.raw,
            malformed.as_slice(),
            case.upstream.as_slice(),
            [false, false],
            "shape-standard-unavailable",
        ),
    ] {
        let out = call_kernel(raw, captured, upstream, &empty, axes, 16.0);
        assert!(!out.applied);
        assert_eq!(out.commands, upstream, "{reason} changed fallback commands");
        assert_eq!(out.reason, format!("shape:{reason}"));
        assert_eq!(
            out.diagnostics,
            serde_json::json!({"model": "coupled-shape-auto-01"})
        );
    }
}

#[test]
fn kernel_captured_class_does_not_replace_raw_shape_authority() {
    let case = kernel_case(16.0);
    // Exact positive X scaling preserves captured continuity; its width
    // certificate follows the same scaling, while raw shape authority and
    // the certified fitted standard remain unchanged.
    let captured: Vec<FittedCommand> = case
        .captured
        .iter()
        .map(|command| match *command {
            FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(2.0 * x, y),
            FittedCommand::LineTo(x, y) => FittedCommand::LineTo(2.0 * x, y),
            FittedCommand::QuadTo(cx, cy, x, y) => FittedCommand::QuadTo(2.0 * cx, cy, 2.0 * x, y),
            FittedCommand::CurveTo(c1x, c1y, c2x, c2y, x, y) => {
                FittedCommand::CurveTo(2.0 * c1x, c1y, 2.0 * c2x, c2y, 2.0 * x, y)
            }
            FittedCommand::Close => FittedCommand::Close,
        })
        .collect();
    let mut reference = case.reference.clone();
    for anchor in &mut reference.anchors {
        if let Some(cert) = &mut anchor.cert {
            cert.border_width *= 2.0;
        }
    }
    let original = call_kernel(
        &case.raw,
        &case.captured,
        &case.upstream,
        &case.reference,
        [false, false],
        16.0,
    );
    let scaled = call_kernel(
        &case.raw,
        &captured,
        &case.upstream,
        &reference,
        [false, false],
        16.0,
    );
    assert!(original.applied && scaled.applied);
    assert_eq!(scaled.commands, original.commands);
    assert_eq!(scaled.reason, original.reason);
    assert_eq!(scaled.diagnostics, original.diagnostics);
}

#[test]
fn kernel_empty_captured_source_falls_back_exact() {
    let case = kernel_case(16.0);
    let out = call_kernel(
        &case.raw,
        &[],
        &case.upstream,
        &case.reference,
        [false, false],
        16.0,
    );
    assert!(!out.applied);
    assert_eq!(out.commands, case.upstream);
    assert_eq!(out.reason, "shape:shape-standard-unavailable");
    assert_eq!(
        out.diagnostics,
        serde_json::json!({"model": "coupled-shape-auto-01"})
    );
}

#[test]
fn kernel_delivered_movement_stays_inside_original_feature_caps() {
    let case = kernel_case(16.0);
    let out = call_kernel(
        &case.raw,
        &case.captured,
        &case.upstream,
        &case.reference,
        [false, false],
        16.0,
    );
    assert!(out.applied);
    let raw = raw_walk(&case.raw).segs;
    let upstream = segments(&case.upstream);
    let candidate = segments(&out.commands);
    assert_eq!(raw.len(), upstream.len());
    assert_eq!(raw.len(), candidate.len());
    let cap = cap_vertex(&raw);
    let x_right = cap.2[0];
    let shared: Vec<&Seg> = raw
        .iter()
        .filter(|s| s.op == Op::Line && s.a[0] == x_right && s.b[0] == x_right && s.a[1] != s.b[1])
        .collect();
    assert_eq!(
        shared.len(),
        2,
        "fixture must have separate body and head borders"
    );
    let body = shared
        .iter()
        .min_by(|a, b| a.a[1].min(a.b[1]).total_cmp(&b.a[1].min(b.b[1])))
        .unwrap();
    let head = shared
        .iter()
        .find(|s| s.a == cap.2 || s.b == cap.2)
        .unwrap();
    let body_mid = (body.a[1] + body.b[1]) / 2.0;
    let mut left_supports: Vec<f64> = raw
        .iter()
        .filter(|s| {
            s.op == Op::Line
                && s.a[0] == s.b[0]
                && s.a[0] < x_right
                && s.a[1].min(s.b[1]) <= body_mid
                && body_mid <= s.a[1].max(s.b[1])
        })
        .map(|s| s.a[0])
        .collect();
    left_supports.sort_by(f64::total_cmp);
    left_supports.dedup();
    assert_eq!(
        left_supports.len(),
        1,
        "fixture must have one opposite body support"
    );
    let body_cap = (x_right - left_supports[0]) / 2.0 - diagonal_fitting::HEADROOM;
    let (head_range, _, _, _) = head_chain(&raw);
    // Invert monotone source Bernstein Y independently of the kernel's
    // analytic root solver. This measures the original three source-width
    // samples; no candidate coordinate participates in its own budget.
    let mut widths = Vec::new();
    for fraction in [0.25, 0.5, 0.75] {
        let y_low = head.a[1].min(head.b[1]);
        let y_high = head.a[1].max(head.b[1]);
        let y = y_low + (y_high - y_low) * fraction;
        let hits: Vec<&Seg> = raw[head_range.clone()]
            .iter()
            .filter(|s| s.op == Op::Quad && s.a[1].min(s.b[1]) <= y && y <= s.a[1].max(s.b[1]))
            .collect();
        assert_eq!(hits.len(), 1, "source head sample must meet one quad");
        let segment = hits[0];
        let control = segment.c1.unwrap();
        assert!(
            segment.a[1].min(segment.b[1]) <= control[1]
                && control[1] <= segment.a[1].max(segment.b[1]),
            "source head must be monotone"
        );
        let bernstein = |t: f64, axis: usize| {
            let u = 1.0 - t;
            u * u * segment.a[axis] + 2.0 * u * t * control[axis] + t * t * segment.b[axis]
        };
        let (mut low, mut high) = (0.0, 1.0);
        for _ in 0..64 {
            let middle = (low + high) / 2.0;
            if (bernstein(middle, 1) < y) == (segment.a[1] < segment.b[1]) {
                low = middle;
            } else {
                high = middle;
            }
        }
        widths.push(x_right - bernstein((low + high) / 2.0, 0));
    }
    let head_cap =
        widths.into_iter().fold(f64::INFINITY, f64::min) / 2.0 - diagonal_fitting::HEADROOM;
    let shared_cap = body_cap.min(head_cap);
    assert!(
        0.0 < head_cap && head_cap < body_cap,
        "fixture must distinguish head and body budgets"
    );
    for (index, ((source, upstream), candidate)) in
        raw.iter().zip(&upstream).zip(&candidate).enumerate()
    {
        for (source_point, upstream_point, candidate_point) in [
            (Some(source.a), Some(upstream.a), Some(candidate.a)),
            (Some(source.b), Some(upstream.b), Some(candidate.b)),
            (source.c1, upstream.c1, candidate.c1),
        ] {
            if let (Some(s), Some(u), Some(c)) = (source_point, upstream_point, candidate_point) {
                let movement = (c[0] - u[0]).abs();
                assert!(
                    movement <= body_cap,
                    "point on segment {index} exceeded original body cap"
                );
                if s[0] == x_right || [cap.0, cap.1, cap.2].contains(&s) {
                    assert!(
                        movement <= shared_cap,
                        "shared/cap point on segment {index} exceeded its original cap"
                    );
                } else if head_range.contains(&index) {
                    assert!(
                        movement <= head_cap,
                        "head/connector point on segment {index} exceeded original head cap"
                    );
                }
            }
        }
    }
}
