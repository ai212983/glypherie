//! Automatic fitting fills axes not read or constrained by native hints.
//!
//! Turner/Lemberg §2 separates X/Y fitting. TrueType projection/freedom
//! semantics supply conservative native ownership, including reads and zero
//! moves: https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions
//! Combining those independently fitted coordinates is a project adaptation.
//! Unknown execution, implicit native changes or incompatible command streams
//! retain the complete native fit rather than guessing which points may move.
use crate::{
    candidate, fail,
    font_scan::FontScanFitter,
    probe::FittedCommand,
    reference::{CaptureSession, ReferenceReport, ReferenceRequest, PROFILE_MONO_1BIT},
    renderer::Rasterization,
    stem_fitting::{
        EXTENSIONS_FONT_HINTS_AUTO, EXTENSIONS_MONO_WIDTH_01, EXTENSIONS_SOURCE_WIDTH_01,
    },
    Error, Hinting,
};
use skrifa_scan::{FontRef, MetadataProvider};

pub(crate) fn render(
    session: &CaptureSession<'_>,
    request: &ReferenceRequest,
    raster: Rasterization,
) -> Result<ReferenceReport, Error> {
    let data = session.data;
    if request.profile != PROFILE_MONO_1BIT
        || request.settings.output_bits != 1
        || raster == Rasterization::Coverage
    {
        return Err(fail(
            "selective font hints require monochrome scan conversion",
        ));
    }
    let mut native_request = request.clone();
    // Retain the existing source-relative correction on wholly automatic
    // glyphs. Native-controlled axes are never passed through that solver.
    native_request.extensions = EXTENSIONS_SOURCE_WIDTH_01.into();
    let mut report =
        candidate::render_with_rasterization_in_session(session, &native_request, raster)?;
    report.extensions = EXTENSIONS_FONT_HINTS_AUTO.into();
    report.implementation.push_str(":selective-axes-01");
    if report.records.iter().all(|r| r.selected_engine == "auto") {
        return Ok(report);
    }
    let mut auto_request = request.clone();
    auto_request.extensions = EXTENSIONS_MONO_WIDTH_01.into();
    let automatic =
        candidate::render_with_rasterization_in_session(session, &auto_request, raster)?;
    let mut source_request = request.clone();
    source_request.extensions = "none".into();
    source_request.settings.hinting = Hinting::None;
    source_request.settings.mono_raster = Default::default();
    let source = session.source(&source_request)?;
    let fitter = FontScanFitter::new(data, &request.settings)?;
    let font = FontRef::new(data).map_err(|e| fail(e.to_string()))?;
    let outlines = font.outline_glyphs();
    let location = font
        .axes()
        .location(request.settings.axes.iter().map(|(t, v)| (t.as_str(), *v)));
    if report.records.len() != automatic.records.len()
        || report.records.len() != source.records.len()
    {
        return Err(fail("selective fitting repertoire changed"));
    }
    for ((native, auto), raw) in report
        .records
        .iter_mut()
        .zip(automatic.records)
        .zip(&source.records)
    {
        if native.glyph_id != auto.glyph_id
            || native.glyph_id != raw.glyph_id
            || native.codepoint != auto.codepoint
            || native.codepoint != raw.codepoint
        {
            return Err(fail("selective fitting glyph identity changed"));
        }
        if native.selected_engine == "auto" {
            continue;
        }
        let axes = if let Some(scan) = &native.font_scan {
            Some(scan.hinting_axes)
        } else if let Some(fitter) = &fitter {
            // Explicitly disabled native hinting is an instruction decision,
            // not evidence of a missing axis.
            if !fitter.is_enabled() {
                None
            } else {
                let mut pen = crate::probe::FittedPen::default();
                let (_, scan) = fitter.draw(native.glyph_id, &mut pen)?;
                if pen.into_commands() != native.fitted_commands {
                    None
                } else {
                    scan.map(|s| s.hinting_axes)
                }
            }
        } else {
            outlines
                .get(skrifa_scan::GlyphId::new(native.glyph_id))
                .and_then(|g| g.postscript_hinting_axes(location.coords()))
        };
        let Some(axes) = axes else { continue };
        if axes == [true; 2] {
            continue;
        }
        // Do not replace an axis changed implicitly by native scaling,
        // component attachment or another unrecorded operation.
        if axes != [false; 2]
            && !unowned_unchanged(&raw.fitted_commands, &native.fitted_commands, axes)
        {
            continue;
        }
        let commands = if axes == [false; 2] {
            auto.fitted_commands.clone()
        } else {
            let Some(commands) = combine(&native.fitted_commands, &auto.fitted_commands, axes)
            else {
                continue;
            };
            commands
        };
        if !axes[0] {
            native.advance_26_6 = auto.advance_26_6;
            native.hinted_advance_width = auto.hinted_advance_width;
            native.hinted_lsb = auto.hinted_lsb;
            native.side_bearing_deltas_26_6 = auto.side_bearing_deltas_26_6;
        }
        let output = crate::mono::rasterize_with_scan_state(
            &commands,
            &request.settings,
            native.font_scan.as_ref(),
        )?;
        native.selected_engine = match axes {
            [false, true] => "auto_x_native_y",
            [true, false] => "native_x_auto_y",
            _ => "auto_with_native_scan",
        }
        .into();
        native.source_commands = Some(raw.fitted_commands.clone());
        native.selective_fitting = Some(crate::reference::SelectiveFittingCapture {
            native_axes: axes,
            native_commands: native.fitted_commands.clone(),
            automatic_commands: auto.fitted_commands,
        });
        native.fitted_commands = commands;
        native.coverage_sha256 = format!("{:x}", sha2::Sha256::digest(&output.coverage));
        native.coverage = output.coverage;
        native.pixels = output.pixels;
        native.left = output.left;
        native.top = output.top;
        native.width = output.width;
        native.height = output.height;
    }
    Ok(report)
}

use sha2::Digest;

pub(crate) fn unowned_unchanged(
    source: &[FittedCommand],
    native: &[FittedCommand],
    axes: [bool; 2],
) -> bool {
    combine(native, source, axes).is_some_and(|c| c == native)
}

pub(crate) fn combine(
    native: &[FittedCommand],
    auto: &[FittedCommand],
    axes: [bool; 2],
) -> Option<Vec<FittedCommand>> {
    use FittedCommand::*;
    if native.len() != auto.len() {
        return None;
    }
    let x = |n, a| if axes[0] { n } else { a };
    let y = |n, a| if axes[1] { n } else { a };
    native
        .iter()
        .zip(auto)
        .map(|(n, a)| {
            Some(match (n, a) {
                (MoveTo(nx, ny), MoveTo(ax, ay)) => MoveTo(x(*nx, *ax), y(*ny, *ay)),
                (LineTo(nx, ny), LineTo(ax, ay)) => LineTo(x(*nx, *ax), y(*ny, *ay)),
                (QuadTo(nx1, ny1, nx, ny), QuadTo(ax1, ay1, ax, ay)) => {
                    QuadTo(x(*nx1, *ax1), y(*ny1, *ay1), x(*nx, *ax), y(*ny, *ay))
                }
                (CurveTo(nx1, ny1, nx2, ny2, nx, ny), CurveTo(ax1, ay1, ax2, ay2, ax, ay)) => {
                    CurveTo(
                        x(*nx1, *ax1),
                        y(*ny1, *ay1),
                        x(*nx2, *ax2),
                        y(*ny2, *ay2),
                        x(*nx, *ax),
                        y(*ny, *ay),
                    )
                }
                (Close, Close) => Close,
                _ => return None,
            })
        })
        .collect()
}
