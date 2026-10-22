//! Composition of the reviewed fitting models with original-input authority.
//!
//! Each feature solve owns its geometry; unsupported features retain the
//! preceding delivery. The terminal stage addresses source-cap violations,
//! rather than replacing an already constrained crossing or curve result.

use super::{geometry, FitResult, Reference};
use crate::{fitting_source::SourceOutline, probe::FittedCommand, Error};

fn cap_height_violation(
    raw: &SourceOutline,
    upstream: &[FittedCommand],
    previous: &[FittedCommand],
) -> bool {
    let (Ok(up), Ok(prior)) = (
        geometry::parse_commands(upstream),
        geometry::parse_commands(previous),
    ) else {
        return false;
    };
    if raw.contours != up.contours
        || up.contours != prior.contours
        || raw.oncurve.len() != up.oncurve.len()
    {
        return false;
    }
    if raw
        .oncurve
        .iter()
        .chain(&raw.offcurve)
        .any(|p| !p[0].is_finite() || !p[1].is_finite())
    {
        return false;
    }
    // The dispatcher and solve share reference-edge eligibility. A local
    // cap below an ascender must trigger the same hard rows as a global cap.
    super::terminal::detect_caps(raw, &up).0.iter().any(|cap| {
        [cap.vertices.0, cap.vertices.1]
            .iter()
            .any(|&v| prior.oncurve[v][1] != up.oncurve[v][1])
    })
}

pub fn fit(
    raw: Option<&SourceOutline>,
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    // The reviewed sequence replaces earlier deliveries, using original
    // inputs for attached/crossing solves. Evaluate that priority lazily:
    // work whose entire result would be overwritten has no authority.
    let source_analysis = super::SourceAnalysis::new(source);
    let crossing = raw
        .and_then(|raw| {
            super::crossing::fit_for_selection(
                raw,
                source,
                upstream,
                size_px,
                reference,
                native_axes,
            )
            .ok()
        })
        .filter(|fit| fit.applied);
    let attached = || {
        super::attached::fit_with_analysis(
            source,
            upstream,
            size_px,
            reference,
            native_axes,
            &source_analysis,
        )
        .ok()
        .filter(|fit| fit.applied)
    };
    let (mut selected, mut stage) = if let Some(fit) = crossing {
        (fit, "crossing")
    } else if let Some(fit) = attached() {
        (fit, "attached")
    } else {
        let width = super::fit_with_analysis(
            source,
            upstream,
            size_px,
            reference,
            native_axes,
            &source_analysis,
        )?;
        let curve = super::curve_model::fit_horizontal(
            source,
            &width.commands,
            size_px,
            reference,
            native_axes,
        )
        .ok()
        .filter(|fit| fit.applied);
        if let Some(fit) = curve {
            (fit, "curve")
        } else if let Some(fit) =
            super::joint::fit_for_selection(source, upstream, size_px, reference, native_axes)
                .ok()
                .filter(|fit| fit.applied)
        {
            (fit, "joint")
        } else {
            (width, "width")
        }
    };
    if let Some(raw) = raw {
        if cap_height_violation(raw, upstream, &selected.commands) {
            let terminal = super::terminal::fit_terminal(
                raw,
                source,
                upstream,
                size_px,
                reference,
                native_axes,
            );
            if terminal.applied {
                selected = terminal;
                stage = "terminal";
            }
        }
    }
    selected.diagnostics["stage"] = serde_json::json!(stage);
    selected.reason = format!("{stage}:{}", selected.reason);
    Ok(selected)
}

#[cfg(test)]
mod scheduling_tests {
    use super::*;
    use crate::diagonal_fitting::{crossing, joint, Anchor};

    fn reference() -> Reference {
        Reference {
            anchors: vec![Anchor {
                source_width: 2.0,
                fitted_width: 2.0,
                rel: 0.0,
                length: 8.0,
                tangent: [0.0, 1.0],
                source_ids: "analytic-upright".into(),
            }],
            size_px: 16.0,
            records: 1,
            n_anchors: 1,
            rel_min: Some(0.0),
            rel_max: Some(0.0),
            notes: vec![],
        }
    }

    fn polygon(points: &[[f32; 2]]) -> Vec<FittedCommand> {
        let mut commands = vec![FittedCommand::MoveTo(points[0][0], points[0][1])];
        commands.extend(
            points[1..]
                .iter()
                .map(|p| FittedCommand::LineTo(p[0], p[1])),
        );
        commands.push(FittedCommand::Close);
        commands
    }

    #[test]
    fn dispatcher_checks_local_reference_below_a_taller_feature() {
        // Hobby 3.3 horizontal regions: this branch ends below the
        // ascender, so a whole-glyph bounding box cannot own its height.
        let source = polygon(&[
            [0.0, 0.0],
            [2.0, 0.0],
            [2.0, 4.0],
            [6.0, 8.0],
            [4.0, 8.0],
            [2.0, 6.0],
            [2.0, 12.0],
            [0.0, 12.0],
        ]);
        let raw = geometry::parse_commands(&source).unwrap();
        assert!(!cap_height_violation(&raw, &source, &source));
        let mut raised = source.clone();
        raised[3] = FittedCommand::LineTo(6.0, 8.25);
        assert!(cap_height_violation(&raw, &source, &raised));
        // Source flatness alone cannot invent an upstream height when the
        // upstream fit deliberately gives the two endpoints different Y.
        let mut ambiguous = source.clone();
        ambiguous[3] = FittedCommand::LineTo(6.0, 8.125);
        assert!(!cap_height_violation(&raw, &ambiguous, &raised));
    }

    #[test]
    fn structural_crossing_rejection_is_affine_invariant() {
        // Dead-work elimination preserves the existing necessary attachment
        // condition, not a font/glyph rule: lines and multiple contours cannot
        // reach this stage's quadratic pair preparation under any such transform.
        // Foundation: https://llvm.org/docs/Passes.html#adce-aggressive-dead-code-elimination
        for (scale, dx, dy) in [(1.0, 0.0, 0.0), (2.0, 32.0, -64.0), (-1.0, 16.0, 8.0)] {
            let points = [[0.0, 0.0], [8.0, 0.0], [8.0, 8.0], [0.0, 8.0]]
                .map(|p| [scale * p[0] + dx, scale * p[1] + dy]);
            let square = polygon(&points);
            let mut two_contours = square.clone();
            two_contours.extend(square.clone());
            for source in [square, two_contours] {
                let raw = geometry::parse_commands(&source).unwrap();
                let detailed =
                    crossing::fit(&raw, &source, &source, 16.0, &reference(), [false; 2]).unwrap();
                let selected = crossing::fit_for_selection(
                    &raw,
                    &source,
                    &source,
                    16.0,
                    &reference(),
                    [false; 2],
                )
                .unwrap();
                assert!(!detailed.applied && !selected.applied);
                assert_eq!(detailed.commands, source);
                assert_eq!(selected.commands, source);
                assert_eq!(detailed.reason, "no-attached-diagonals");
                assert!(detailed.diagnostics.get("skipped").is_some());
            }
        }
    }

    #[test]
    fn early_joint_rejection_keeps_standalone_diagnostic_order() {
        // A rectangle has no internal crossing waist, although its symmetry
        // axis is well defined. The standalone stage must still report its
        // original earlier pair-preparation failure rather than the fast gate.
        for scale in [1.0, 2.0] {
            let source = polygon(&[
                [0.0, 0.0],
                [8.0 * scale, 0.0],
                [8.0 * scale, 8.0],
                [0.0, 8.0],
            ]);
            let detailed = joint::fit(&source, &source, 16.0, &reference(), [false; 2]).unwrap();
            let selected =
                joint::fit_for_selection(&source, &source, 16.0, &reference(), [false; 2]).unwrap();
            assert!(!detailed.applied && !selected.applied);
            assert_eq!(detailed.commands, source);
            assert_eq!(selected.commands, source);
            assert_eq!(detailed.reason, "all-abstained");
            assert_eq!(selected.reason, "no-waist");
            assert!(detailed.diagnostics.get("fixed").is_some());
        }
    }

    #[test]
    fn selection_still_validates_before_prerequisites() {
        let source = polygon(&[[0.0, 0.0], [8.0, 0.0], [8.0, 8.0]]);
        let raw = geometry::parse_commands(&source).unwrap();
        for size in [0.0, f64::NAN, f64::INFINITY] {
            let a =
                crossing::fit(&raw, &source, &source, size, &reference(), [false; 2]).unwrap_err();
            let b =
                crossing::fit_for_selection(&raw, &source, &source, size, &reference(), [false; 2])
                    .unwrap_err();
            assert_eq!(a.to_string(), b.to_string());
            let a = joint::fit(&source, &source, size, &reference(), [false; 2]).unwrap_err();
            let b = joint::fit_for_selection(&source, &source, size, &reference(), [false; 2])
                .unwrap_err();
            assert_eq!(a.to_string(), b.to_string());
        }
    }
}
