"""Export an isolated, offline comparison of retained Mono captures.

Every automatic adjustment comes from the existing Python Solver. The browser
places the retained metrics and marks cell contacts for inspection; it neither
estimates optical separation nor changes delivered glyph images.
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

from estimator import UnsupportedGeometry, WorkLimitExceeded
from solver import Controls, IMPLEMENTATION_IDENTITY, Solver, bitmap_commands, canonical, finite
from browser_reference import attach_browser_reference

STRENGTHS = [0, 0.25, 0.5, 0.75, 1]
COUNTERSPACE_MODELS = ("counterspace", "counterspace_delivered_first", "counterspace_source_first")
DENSITY_MODELS = ("hu_alphabet_source_target", "hu_density_conserved", "hu_density_conserved_touch", "hu_fitted_density_conserved_touch",
                  "hu_fitted_full_density_conserved_touch")
HU_MODELS = ("hu_hersch", "hu_source_relative", "hu_source_calibrated", *DENSITY_MODELS)
BASE_MODELS = (*HU_MODELS, "filtered_walls", "font_calibrated", "source_relative", "balanced")
DEFAULT_MODELS = tuple(model for model in BASE_MODELS if model not in DENSITY_MODELS)
DIAGNOSTIC_LABELS = ["corrected", "rounded_unchanged", "unchanged", "optical_disabled",
                     "fixed_pitch", "source_tabular_digits", "empty_geometry", "no_shared_bands",
                     "unsupported_calibration_class", "calibration_unavailable",
                     "clearance_limited", "unsupported_geometry_policy", "no_shared_ink_rows",
                     "counterspace_unsupported_scalar", "captured_bitmap_outside_reference_canvas", "counterspace_no_feasible_candidate"]
DEFAULT_TEXT = "ty type type type\nyp pe\nff cc zz nn oo no on\nbd ct ab du\njo yd le pi ip te tp OE OR\noe kh rn xn co\n01 12 23 0123456789\nlynx tuft frogs minimum awkward rhythm\nAV To Wa fi ffi lmi é, À."
ASSET_DIRECTORY = Path(__file__).resolve().parent


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def embedded_json(value):
    """A JSON script element must not be terminated by captured metadata."""
    return canonical(value).translate(str.maketrans({
        "<": "\\u003c", ">": "\\u003e", "&": "\\u0026",
        "\u2028": "\\u2028", "\u2029": "\\u2029",
    }))


def default_text(codepoints):
    supported = set(codepoints)
    text = "".join(c for c in DEFAULT_TEXT if c == "\n" or ord(c) in supported)
    if not text.strip():
        text = "".join(chr(cp) for cp in codepoints if cp != 32)
    return text


HU_SOURCE_TARGET_FIELDS = ("source_step_px", "source_target_px", "target_area_px2", "unconstrained_step_px")
HU_SOURCE_DIAGNOSTIC_FIELDS = ("source_kerning", "source_step_px", "source_target_px")


def source_metadata_overlay(record):
    """Store the declared kerning-dependent values without repeating geometry."""
    result = {key: record[key] for key in HU_SOURCE_TARGET_FIELDS}
    diagnostic = record["hu_hersch"]
    result["hu_hersch"] = ({key: diagnostic[key] for key in HU_SOURCE_DIAGNOSTIC_FIELDS}
                           if diagnostic is not None else None)
    return result


def merge_source_metadata(base, overlay):
    """Select stored source-target metadata; never recompute optical geometry."""
    result = dict(base)
    result.update({key: overlay[key] for key in HU_SOURCE_TARGET_FIELDS})
    result["hu_hersch"] = (dict(base.get("hu_hersch") or {}, **overlay["hu_hersch"])
                           if overlay["hu_hersch"] is not None else None)
    return result


def selected_models(include_counterspace=False, spacing_models=None):
    available = BASE_MODELS + (COUNTERSPACE_MODELS if include_counterspace else ())
    models = list(DEFAULT_MODELS + (COUNTERSPACE_MODELS if include_counterspace else ())
                  if spacing_models is None else spacing_models)
    if not models or len(set(models)) != len(models) or any(model not in available for model in models):
        raise ValueError("export models must be nonempty, unique and available")
    return models


def build_case(capture, capture_path, capture_sha256, work_limit=10000, target_separation_em=0.15, include_counterspace=False,
               spacing_models=None):
    """Build every ordered pair at all finite controls, or raise without a page."""
    solver = Solver(capture)
    settings = capture.get("produced_settings", {})
    raw_capture = capture.get("capture", {})
    if settings.get("output_bits", 1) != 1 or raw_capture.get("profile", "mono_1bit") != "mono_1bit":
        raise ValueError("optical tables require retained Mono captures; add a default Gray reference with --grayscale-captures")
    codepoints = sorted(solver.glyphs)
    glyphs = []
    for cp in codepoints:
        original = solver.glyphs[cp]
        bitmap = original["bitmap"]
        bitmap_commands(bitmap, 1)  # Validate all bitmaps, including abstaining pairs.
        if any(type(bitmap[key]) is not int for key in ("left", "top")):
            raise ValueError("retained bitmap offsets must be whole pixels")
        glyphs.append(dict(codepoint=cp, glyphId=original["glyph_id"],
                           advancePx=original["finalized_advance_px"], bitmap=bitmap))
    Controls(target_separation_em=target_separation_em)  # Validate exporter configuration.
    models, model_results = {}, {}

    def retain(result, bundle, prefix=""):
        table = [record["automatic_adjustment_px"] for record in result["pairs"]]
        if any(finite(value) != int(value) for value in table):
            raise ValueError("automatic pair adjustments must be integer pixels")
        key = lambda suffix: prefix + suffix if prefix else suffix[0].lower() + suffix[1:]
        bundle[key("PairTables")].append([int(value) for value in table])
        bundle[key("PairDiagnostics")].append([DIAGNOSTIC_LABELS.index(record["diagnostic"]) for record in result["pairs"]])
        bundle[key("PairReasonCounts")].append(dict(Counter(record["reason"] or "optical_solved" for record in result["pairs"])))

    model_names = selected_models(include_counterspace, spacing_models)
    for model in model_names:
        bundle = {key: [] for key in ("pairTables", "pairDiagnostics", "pairReasonCounts",
                                      "preservedPairTables", "preservedPairDiagnostics", "preservedPairReasonCounts")}
        if model in HU_MODELS + ("filtered_walls",) + COUNTERSPACE_MODELS:
            bundle.update(pairRoundedUnconstrainedStepsPx=[], pairClearanceAdjustmentsPx=[])
        if model in HU_MODELS:
            bundle.update(preservedPairRoundedUnconstrainedStepsPx=[], preservedPairClearanceAdjustmentsPx=[])
        if model in COUNTERSPACE_MODELS:
            bundle.update(pairTargetScores=[], pairRealizedScores=[], pairScoreErrors=[],
                          preservedPairTargetScores=[], preservedPairRealizedScores=[], preservedPairScoreErrors=[],
                          preservedPairRoundedUnconstrainedStepsPx=[], preservedPairClearanceAdjustmentsPx=[])
        bundle.update(calibration=solver.calibration_metadata(spacing_model=model)
                      if model in HU_MODELS + ("filtered_walls", "font_calibrated") + COUNTERSPACE_MODELS else None,
                      targetSeparationEm=target_separation_em if model == "balanced" else None, pairTargetsPx=[])
        if model == "hu_source_relative":
            bundle.update(pairTargetMetadataByKerning=[], preservedPairTargetMetadataByKerning=[])
        results, preserved_results = [], []
        for k in STRENGTHS:
            for o in STRENGTHS:
                options = dict(source_kerning=k, optical=o, spacing_model=model,
                               target_separation_em=target_separation_em)
                preserved = solver.generate(Controls(**options, preserve_tabular_spacing=True), work_limit=work_limit)
                if preserved["status"] != "complete" or preserved["completed_pairs"] != len(codepoints) ** 2:
                    raise ValueError(f"incomplete pair table for {capture_path}: model={model}, k={k}, o={o}; "
                                     f"{preserved['status']}: {preserved['reason']}")
                controls = Controls(**options, preserve_tabular_spacing=False)
                pairs = preserved["pairs"]
                if capture["tabular_digits"] and not capture["monospace"]:
                    # Only source-tabular digit pairs differ between policies.
                    pairs = list(pairs)
                    for index, record in enumerate(pairs):
                        if all(48 <= cp <= 57 for cp in (record["left"], record["right"])):
                            try:
                                pairs[index] = solver.pair(record["left"], record["right"], controls)
                            except (UnsupportedGeometry, WorkLimitExceeded) as error:
                                raise ValueError(f"incomplete pair table for {capture_path}: model={model}, "
                                                 f"k={k}, o={o}, preserve_tabular_spacing=false: {error}") from error
                result = dict(preserved, pairs=pairs,
                              controls=dict(preserved["controls"], preserve_tabular_spacing=False))
                retain(result, bundle)
                retain(preserved, bundle, "preserved")
                results.append(result)
                preserved_results.append(preserved)
                if model in HU_MODELS + ("filtered_walls",) + COUNTERSPACE_MODELS:
                    bundle["pairRoundedUnconstrainedStepsPx"].append(
                        [record["rounded_unconstrained_step_px"] for record in pairs])
                    bundle["pairClearanceAdjustmentsPx"].append(
                        [record["clearance_adjustment_px"] for record in pairs])
                if model in HU_MODELS + COUNTERSPACE_MODELS:
                    bundle["preservedPairRoundedUnconstrainedStepsPx"].append(
                        [record["rounded_unconstrained_step_px"] for record in preserved["pairs"]])
                    bundle["preservedPairClearanceAdjustmentsPx"].append(
                        [record["clearance_adjustment_px"] for record in preserved["pairs"]])
                if model in COUNTERSPACE_MODELS:
                    for prefix, records in (("", pairs), ("preserved", preserved["pairs"])):
                        for suffix, field in (("TargetScores", "target_score"), ("RealizedScores", "realized_score"), ("ScoreErrors", "score_error")):
                            key = prefix + "Pair" + suffix if prefix else "pair" + suffix
                            bundle[key].append([record[field] for record in records])
                if o == 1:
                    bundle["pairTargetsPx"].append([record["target_separation_px"] for record in pairs])
                    if k == 0:
                        fields = ("target_provenance", "calibration_basis", "calibration_reason", "calibration_detail")
                        if model in COUNTERSPACE_MODELS:
                            fields += ("reference_pair", "unconstrained_step_px", "clearance_min_step_px",
                                       "calibration_geometry", "search_policy", "search_outcome", "target_crossed",
                                       "candidate_count", "feasible_candidate_count", "candidate_domain_min_step_px",
                                       "candidate_domain_stop_step_px", "first_crossing_step_px", "first_crossing_score",
                                       "closest_feasible_step_px", "closest_feasible_score")
                        if model in HU_MODELS + ("filtered_walls",):
                            fields += ("target_area_px2", "window_height_px", "measurement_window_px",
                                       "unconstrained_step_px", "clearance_min_step_px")
                        if model in HU_MODELS:
                            fields += ("reference_pair", "hu_hersch")
                        if model in DENSITY_MODELS:
                            fields += ("clearance_policy", "candidate_geometry", "measurement_method")
                        if model == "hu_source_relative":
                            fields += ("source_step_px", "source_advance_px", "source_pair_adjustment_px",
                                       "source_hu_offset_px", "delivered_hu_offset_px", "source_target_px")
                        bundle["pairTargetMetadata"] = [{key: record[key] for key in fields} for record in pairs]
                        bundle["preservedPairTargetMetadata"] = [{key: record[key] for key in fields}
                                                                  for record in preserved["pairs"]]
                        # A linear measurement offset, retained from Python geometry.
                        # The viewer can measure placement without solving it again.
                        bundle["pairGeometryOffsetsPx"] = [] if model in COUNTERSPACE_MODELS else [
                            None if record["realized_separation_px"] is None else
                            record["realized_separation_px"] - record["resolved_step_px"] for record in pairs]
                    if model == "hu_source_relative":
                        for prefix, records in (("pair", pairs), ("preservedPair", preserved["pairs"])):
                            bundle[prefix + "TargetMetadataByKerning"].append([
                                source_metadata_overlay(record) for record in records])
        bundle["estimator"] = results[-1]["estimator"]
        if model in COUNTERSPACE_MODELS:
            bundle["counterspace"] = results[-1].get("counterspace", bundle["calibration"])
            bundle["analysisIdentity"] = results[-1].get("counterspace_analysis_identity")
        models[model] = bundle
        model_results[model] = (results, preserved_results)
    metrics = capture.get("metrics", {})
    ascent = finite(metrics.get("ascent_26_6", max(-g["bitmap"]["top"] for g in glyphs) * 64)) / 64
    descent = finite(metrics.get("descent_26_6", -max(g["bitmap"]["top"] + g["bitmap"]["height"] for g in glyphs) * 64)) / 64
    line_gap = finite(metrics.get("line_gap_26_6", 0)) / 64
    label = Path(capture.get("font_path", capture_path)).stem
    case = dict(id=solver.identity, label=label, sizePx=solver.size, axes=capture.get("axes", {}),
                pipeline=capture.get("pipeline", {}), sourceSha256=capture["source_sha256"],
                analysisIdentity=solver.identity, capturePath=str(capture_path), captureSha256=capture_sha256,
                codepoints=codepoints, glyphs=glyphs, models=models,
                calibration=models.get("filtered_walls", models[model_names[0]])["calibration"],
                monospace=capture["monospace"], tabularDigits=capture["tabular_digits"],
                metricsAscent=ascent, metricsDescent=descent, metricsLineGap=line_gap,
                defaultText=default_text(codepoints), estimator=models.get("filtered_walls", models[model_names[0]])["estimator"],
                sourceMetricQuantization=capture.get("source_metric_quantization"),
                adapterIdentity=capture.get("adapter_identity"),
                rendererImplementation=capture.get("capture", {}).get("implementation"))
    attach_source_layout(case, capture)
    if "font_path" in capture:
        attach_browser_reference(case, capture)
    # Executable cross-language expectations exercise all strengths, repeated
    # spaces, explicit breaks, fractional signed offsets, and greedy wrapping.
    sample = case["defaultText"]
    if 32 in codepoints:
        first = next((chr(cp) for cp in codepoints if cp != 32), " ")
        sample += f"\n{first}{first}  {first}\n"
    if all(cp in codepoints for cp in (49, 50)):
        sample += "\n12"
    verification = []
    for model, (results, preserved_results) in model_results.items():
        for preserve, policy_results in ((False, results), (True, preserved_results)):
            for index, result in enumerate(policy_results):
                for width in (None, max(1, math.ceil(solver.size * 2.5))):
                    letter, word = (0, 0) if capture["monospace"] else (-0.5, 1.5)
                    controls = dict(result["controls"], letter_spacing=letter, word_spacing=word)
                    controlled = dict(result, controls=controls)
                    verification.append(dict(text=sample, kIndex=index // len(STRENGTHS),
                                             oIndex=index % len(STRENGTHS), letterSpacing=letter,
                                             wordSpacing=word, width=width, preserveTabularSpacing=preserve,
                                             spacingModel=model,
                                             expected=solver.layout(sample, controlled, width=width)))
    case["verification"] = verification
    return case


def load_presets(path):
    presets = json.loads(Path(path).read_text())
    if not isinstance(presets, list):
        raise ValueError("presets must be a list")
    identities = set()
    for preset in presets:
        if (not isinstance(preset, dict) or set(preset) != {"id", "label", "text"}
                or any(not isinstance(preset[key], str) or not preset[key] for key in preset)
                or preset["id"] in identities):
            raise ValueError("presets require unique IDs and nonempty labels and text")
        identities.add(preset["id"])
    return presets


def _build_capture_case(request):
    """Picklable case boundary: each process owns one optional numerical fit."""
    path, work_limit, target_separation_em, include_counterspace, presets, spacing_models = request
    raw = path.read_bytes()
    capture = json.loads(raw)
    supported = {glyph["codepoint"] for glyph in capture["glyphs"]} | {10}
    for preset in presets:
        missing = sorted({ord(c) for c in preset["text"]} - supported)
        if missing:
            scalars = ", ".join(f"U+{cp:04X}" for cp in missing)
            raise ValueError(f"preset {preset['label']!r} unsupported by {path}: {scalars}")
    return build_case(capture, str(path), sha256(raw), work_limit=work_limit,
                      target_separation_em=target_separation_em, include_counterspace=include_counterspace,
                      spacing_models=spacing_models)


def attach_source_layout(case, capture):
    """Expose original 26.6 metrics beside unchanged delivered Mono cells.

    The generator's native source-layout surface accumulates fractional source
    advances and pair kerning, rounding only draw origins (API.md#live-spacing-api).
    This diagnostic does not use finalized bitmap advances or bearing deltas.
    """
    glyphs = {glyph["codepoint"]: glyph for glyph in capture["glyphs"]}
    if (sorted(glyphs) != case["codepoints"] or capture["source_sha256"] != case["sourceSha256"]
            or capture["size_px"] != case["sizePx"] or capture.get("axes", {}) != case["axes"]):
        raise ValueError("source-layout capture must match the Mono case")
    advances = {str(cp): finite(glyphs[cp]["source_advance_px"]) for cp in case["codepoints"]}
    pairs = {}
    for pair in capture["source_pairs"]:
        key = f"{pair['left']},{pair['right']}"
        if pair["left"] not in glyphs or pair["right"] not in glyphs or key in pairs:
            raise ValueError("invalid source-layout pair")
        pairs[key] = finite(pair["adjustment_px"])
    case["sourceLayout"] = dict(advancesPx=advances, pairAdjustmentsPx=pairs,
                                spacingPolicy="source_linear_26_6",
                                metricQuantization=capture.get("source_metric_quantization"))


def attach_grayscale(case, path):
    """Retain vanilla source-linear Gray metrics without bitmap finalization."""
    raw = Path(path).read_bytes()
    capture = json.loads(raw)
    if (capture.get("schema_version") != "contextual-spacing-grayscale-v2"
            or capture.get("spacing_policy") != "source_linear_26_6"):
        raise ValueError("unsupported grayscale capture")
    font = capture["font"]
    config = font["config"]
    if (font["source_sha256"] != case["sourceSha256"] or config["size_px"] != case["sizePx"]
            or config["axes"] != case["axes"]):
        raise ValueError("grayscale source, size and axes must match the Mono case")
    if (config["output_bits"] != 3 or config["hinting"] != "auto" or config["gray_gamma"] != 1
            or config["kerning"] is not True or config["metric_rounding"] != "subpixel"
            or config["mono_raster"] != dict(dropout="smart", include_stubs=False, font_instructions=False)):
        raise ValueError("grayscale capture must use the renderer defaults with 3-bit output")
    glyphs = font["glyphs"]
    if font["missing_codepoints"] or sorted(g["codepoint"] for g in glyphs) != case["codepoints"]:
        raise ValueError("grayscale repertoire must match the Mono case exactly")
    retained = []
    for glyph in glyphs:
        bitmap = {key: glyph[key] for key in ("left", "top", "width", "height", "pixels")}
        if (any(type(bitmap[key]) is not int for key in ("left", "top", "width", "height"))
                or bitmap["width"] < 0 or bitmap["height"] < 0
                or len(bitmap["pixels"]) != bitmap["width"] * bitmap["height"]
                or any(type(p) is not int or not 0 <= p <= 7 for p in bitmap["pixels"])
                or type(glyph["advance_26_6"]) is not int):
            raise ValueError("invalid vanilla grayscale bitmap or source advance")
        retained.append(dict(codepoint=glyph["codepoint"], glyphId=glyph["glyph_id"],
                             advancePx=glyph["advance_26_6"] / 64, bitmap=bitmap))
    pairs = {}
    for pair in font["kerning"]:
        key = f"{pair['left']},{pair['right']}"
        if (pair["left"] not in case["codepoints"] or pair["right"] not in case["codepoints"]
                or key in pairs or type(pair["adjustment_26_6"]) is not int):
            raise ValueError("invalid default grayscale pair adjustment")
        pairs[key] = pair["adjustment_26_6"] / 64
    metrics = font["metrics"]
    case["grayscale"] = dict(glyphs=retained, pairAdjustmentsPx=pairs, inkLevels=7,
                              metricsAscent=metrics["ascent_26_6"] / 64,
                              metricsDescent=metrics["descent_26_6"] / 64,
                              metricsLineGap=metrics["line_gap_26_6"] / 64,
                              sizePx=case["sizePx"], settings=config, policy=capture["policy"],
                              spacingPolicy=capture["spacing_policy"],
                              capturePath=str(path), captureSha256=sha256(raw))
    source = case.get("sourceLayout")
    if source and (source["advancesPx"] != {str(g["codepoint"]): g["advancePx"] for g in retained}
                   or {k: v for k, v in source["pairAdjustmentsPx"].items() if v}
                   != {k: v for k, v in pairs.items() if v}):
        raise ValueError("grayscale source metrics disagree with the Mono source-layout reference")


def build_data(capture_paths, work_limit=10000, target_separation_em=0.15, presets=(), include_counterspace=False,
               default_spacing_model="hu_hersch", grayscale_paths=(), spacing_models=None):
    models = selected_models(include_counterspace, spacing_models)
    if default_spacing_model not in models:
        raise ValueError("default spacing model must be included in the export")
    if not capture_paths:
        raise ValueError("at least one capture is required")
    paths = list(map(Path, capture_paths))
    if grayscale_paths and len(grayscale_paths) != len(paths):
        raise ValueError("provide one grayscale capture for each Mono capture, in the same order")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"capture file not found: {path}")
    requests = [(path, work_limit, target_separation_em, include_counterspace, presets, models) for path in paths]
    if include_counterspace and len(paths) > 1:
        # Numerical fitting is isolated per font. map retains input ordering;
        # any worker error aborts before the atomic exporter publishes a page.
        with ProcessPoolExecutor(max_workers=min(4, len(paths))) as executor:
            cases = list(executor.map(_build_capture_case, requests))
    else:
        cases = [_build_capture_case(request) for request in requests]
    for case, path in zip(cases, grayscale_paths):
        attach_grayscale(case, path)
    identities = set()
    for path, case in zip(paths, cases):
        if case["id"] in identities:
            raise ValueError(f"duplicate captured case: {path}")
        identities.add(case["id"])
    data = dict(schema_version="contextual-spacing-page-v9", strengths=STRENGTHS,
                diagnosticLabels=DIAGNOSTIC_LABELS, defaultPreserveTabularSpacing=False, defaultSpacingModel=default_spacing_model,
                targetSeparationEm=target_separation_em,
                defaultText=cases[0]["defaultText"], presets=list(presets), cases=cases, status="complete",
                solverImplementationSha256=IMPLEMENTATION_IDENTITY,
                exporterSha256=sha256(Path(__file__).read_bytes()))
    construction_models = ("hu_fitted_density_conserved_touch", "hu_fitted_full_density_conserved_touch")
    if set(models) == set(construction_models):
        data["comparisonModels"] = list(construction_models)
    return data


def neighbor_layout(positions, pairs, delta_px=-1):
    """Diagnostic neighboring placement; never an optical solver policy.

    Shift the suffix after each selected adjacent pair and preserve every
    other pair step, glyph and terminal advance. Explicit lines reset shifts.
    """
    chosen = {tuple(map(ord, pair)) for pair in pairs}
    result = copy.deepcopy(positions)
    for line in result["lines"]:
        shift, previous = 0, None
        for placement in line["placements"]:
            if (previous, placement["codepoint"]) in chosen:
                shift += delta_px
            placement["x_px"] += shift
            previous = placement["codepoint"]
        line["width_px"] += shift
    return result


def neighbor_text_layout(solver, text, result, pairs, delta_px=-1, width=None):
    """Apply a diagnostic pair delta before independent wrapping.

    The solved result stays unchanged. This shadow placement is not exported
    as a solved model and intentionally does not reapply optical clearance.
    """
    chosen = {tuple(map(ord, pair)) for pair in pairs}
    shadow = dict(result, pairs=[dict(record, automatic_adjustment_px=record["automatic_adjustment_px"] +
                                    (delta_px if (record["left"], record["right"]) in chosen else 0))
                               for record in result["pairs"]])
    return solver.layout(text, shadow, width=width)


def attach_neighbor_review(data, config):
    """Attach optional pair/word diagnostics to completed, unchanged tables."""
    if not isinstance(config, dict) or set(config) - {"pairs", "words", "spacingModel", "deltaPx", "mode"}:
        raise ValueError("neighbor review requires pairs, words, spacingModel and optional deltaPx")
    pairs, words, model = config.get("pairs"), config.get("words"), config.get("spacingModel")
    delta = config.get("deltaPx", -1)
    mode = config.get("mode", "pairs")
    if mode not in ("pairs", "text"):
        raise ValueError("neighbor review mode must be pairs or text")
    if type(delta) is not int or delta != -1:
        raise ValueError("neighbor review shows exactly one pixel tighter")
    if (not isinstance(pairs, list) or not 1 <= len(pairs) <= 32 or
            any(not isinstance(pair, str) or len(pair) != 2 or any(c.isspace() for c in pair) for pair in pairs)
            or len(set(pairs)) != len(pairs)):
        raise ValueError("neighbor pairs must be distinct two-character strings")
    if (not isinstance(words, list) or len(words) > 32 or
            any(not isinstance(word, str) or not word or len(word) > 128 or "\n" in word for word in words)):
        raise ValueError("neighbor words must be bounded single-line strings")
    records = []
    texts = [*pairs, *words, pairs[0] + " " + pairs[0], pairs[0] + "\n" + pairs[-1]]
    for case in data["cases"]:
        if model not in case["models"]:
            raise ValueError("neighbor review model must be included in every case")
        if any(ord(c) not in case["codepoints"] for text in texts for c in text if c != "\n"):
            raise ValueError("neighbor review contains uncaptured characters")
        path = Path(case["capturePath"])
        raw = path.read_bytes()
        if sha256(raw) != case["captureSha256"]:
            raise ValueError("neighbor review capture identity mismatch")
        solver = Solver(json.loads(raw))
        for k, o in ((4, 4), (0, 4), (2, 2), (4, 0)):
            for preserve in (False, True):
                controls = Controls(source_kerning=STRENGTHS[k], optical=STRENGTHS[o],
                                    preserve_tabular_spacing=preserve, spacing_model=model)
                for text in texts:
                    current = solver.layout(text, solver.generate(controls, text=text), width=None)
                    records.append(dict(caseId=case["id"], text=text, kIndex=k, oIndex=o,
                                        preserveTabularSpacing=preserve, expectedCurrent=current,
                                        expectedNeighbor=neighbor_layout(current, pairs, delta)))
        if mode == "text":
            for preset in data.get("presets", []):
                text = preset["text"]
                controls = Controls(spacing_model=model, preserve_tabular_spacing=False)
                solved = solver.generate(controls, text=text)
                for width in (160, 280):
                    records.append(dict(caseId=case["id"], text=text, kIndex=4, oIndex=4,
                        preserveTabularSpacing=False, width=width, presetId=preset["id"],
                        expectedCurrent=solver.layout(text, solved, width=width),
                        expectedNeighbor=neighbor_text_layout(solver, text, solved, pairs, delta, width)))
            text = pairs[0] + " " + pairs[0] + "\n" + pairs[-1]
            controls = Controls(spacing_model=model, letter_spacing=1, word_spacing=2,
                                preserve_tabular_spacing=False)
            solved = solver.generate(controls, text=text)
            records.append(dict(caseId=case["id"], text=text, kIndex=4, oIndex=4,
                preserveTabularSpacing=False, width=160, letterSpacing=1, wordSpacing=2,
                expectedCurrent=solver.layout(text, solved, width=160),
                expectedNeighbor=neighbor_text_layout(solver, text, solved, pairs, delta, 160)))
    data["neighborReview"] = dict(pairs=pairs, words=words, deltaPx=delta, spacingModel=model, mode=mode)
    data["neighborReviewVerification"] = records
    return data


def render_html(data, asset_directory=ASSET_DIRECTORY):
    directory = Path(asset_directory)
    template = (directory / "page.html").read_text()
    # Detailed parity fixtures belong to the diagnostic JSON, not the viewer.
    runtime_data = dict(data, cases=[{key: value for key, value in case.items()
                                    if key != "verification"} for case in data.get("cases", [])])
    runtime_data.pop("neighborReviewVerification", None)
    runtime_data.pop("wholeTextVerification", None)
    replacements = {"__STYLE__": (directory / "page.css").read_text(),
                    "__SCRIPT__": (directory / "page.js").read_text(),
                    "__DATA__": embedded_json(runtime_data)}
    for token in replacements:
        if template.count(token) != 1:
            raise ValueError(f"page template requires exactly one {token} placeholder")
    # Replace in one pass so captured metadata cannot become a later token.
    import re
    return re.sub("|".join(re.escape(token) for token in replacements),
                  lambda match: replacements[match.group()], template)


def export_page(output_directory, capture_paths, work_limit=10000, asset_directory=ASSET_DIRECTORY,
                target_separation_em=0.15, presets=(), include_counterspace=False,
                default_spacing_model="hu_hersch", grayscale_paths=(), spacing_models=None, neighbor_review=None):
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output directory already exists: {output}")
    data = build_data(capture_paths, work_limit=work_limit, target_separation_em=target_separation_em,
                      presets=presets, include_counterspace=include_counterspace,
                      default_spacing_model=default_spacing_model, grayscale_paths=grayscale_paths, spacing_models=spacing_models)
    if neighbor_review is not None:
        attach_neighbor_review(data, neighbor_review)
    return write_page(output_directory, data, asset_directory)


def write_page(output_directory, data, asset_directory=ASSET_DIRECTORY):
    """Atomically package completed tables and references without solving again."""
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output directory already exists: {output}")
    if data["solverImplementationSha256"] != IMPLEMENTATION_IDENTITY:
        raise ValueError("completed spacing data belongs to a different solver implementation")
    data = dict(data, exporterSha256=sha256(Path(__file__).read_bytes()))
    document = render_html(data, asset_directory)
    data_bytes = (canonical(data) + "\n").encode()
    html_bytes = document.encode()
    assets = {name: sha256((Path(asset_directory) / name).read_bytes())
              for name in ("page.html", "page.js", "page.css")}
    manifest = dict(schema_version="contextual-spacing-page-manifest-v1", status="complete",
                    pageSchemaVersion=data["schema_version"],
                    pageSha256=sha256(html_bytes), dataSha256=sha256(data_bytes), assets=assets,
                    exporterSha256=data["exporterSha256"],
                    solverImplementationSha256=IMPLEMENTATION_IDENTITY,
                    cases=[{key: case[key] for key in ("id", "capturePath", "captureSha256", "sourceSha256")}
                           for case in data["cases"]])
    manifest["grayscaleCaptures"] = [dict(caseId=case["id"], **{key: case["grayscale"][key]
                                        for key in ("capturePath", "captureSha256")})
                                     for case in data["cases"] if "grayscale" in case]
    if "retainedSpacingData" in data:
        manifest["retainedSpacingData"] = data["retainedSpacingData"]
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    reserved = False
    try:
        (stage / "page-data.json").write_bytes(data_bytes)
        (stage / "index.html").write_bytes(html_bytes)
        (stage / "page-manifest.json").write_text(canonical(manifest) + "\n")
        # Exclusive reservation prevents replacing even an existing empty folder.
        # Replacing our own empty reservation publishes all complete files at once.
        output.mkdir()
        reserved = True
        os.replace(stage, output)
        reserved = False
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if reserved:
            output.rmdir()
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("captures", type=Path, nargs="+")
    parser.add_argument("--grayscale-captures", type=Path, nargs="+", default=[],
                        help="Default 3-bit strikes, one per Mono capture in matching order")
    parser.add_argument("--target-separation-em", type=float, default=0.15,
                        help="Fixed-target diagnostic model only; font calibration derives its own targets")
    parser.add_argument("--work-limit", type=int, default=10000, help="Maximum ordered pairs per solver table")
    parser.add_argument("--presets", type=Path, default=ASSET_DIRECTORY / "presets.json",
                        help="Text catalogue; every preset must be supported by every capture")
    parser.add_argument("--default-spacing-model", choices=BASE_MODELS + COUNTERSPACE_MODELS,
                        default="hu_hersch", help="Initial comparison selection; must be included in the export")
    parser.add_argument("--include-counterspace", action="store_true",
                        help="Fit the pinned optional CounterSpace adapter and add its completed comparison tables")
    parser.add_argument("--models", nargs="+", choices=BASE_MODELS + COUNTERSPACE_MODELS,
                        help="Only generate the selected models; CounterSpace models also require --include-counterspace")
    parser.add_argument("--neighbor-review", type=Path,
                        help="Optional JSON pairs/words/spacingModel configuration for diagnostic neighboring placements")
    args = parser.parse_args()
    try:
        data = export_page(args.output_directory, args.captures, work_limit=args.work_limit,
                           target_separation_em=args.target_separation_em, presets=load_presets(args.presets),
                           include_counterspace=args.include_counterspace, default_spacing_model=args.default_spacing_model,
                           grayscale_paths=args.grayscale_captures, spacing_models=args.models,
                           neighbor_review=json.loads(args.neighbor_review.read_text()) if args.neighbor_review else None)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        parser.exit(1, f"comparison export failed: {error}\n")
    print(f"Exported {len(data['cases'])} complete cases: {args.output_directory / 'index.html'}")


if __name__ == "__main__":
    main()
