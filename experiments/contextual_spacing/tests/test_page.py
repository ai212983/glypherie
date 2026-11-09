import copy
import hashlib
import json
import re
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from page import BASE_MODELS, DEFAULT_MODELS, DENSITY_MODELS, HU_MODELS, merge_source_metadata, COUNTERSPACE_MODELS, DIAGNOSTIC_LABELS, STRENGTHS, attach_grayscale, attach_source_layout, build_case, build_data, embedded_json, export_page, load_presets, render_html, neighbor_layout, neighbor_text_layout, attach_neighbor_review
from solver import Controls, Solver
from browser_reference import attach_browser_reference
from test_solver import HuHerschStub, capture as base_capture


def capture():
    value = base_capture()
    exemplar = value["glyphs"][1]
    value["source_calibration"] = dict(
        schema_version="contextual-spacing-source-calibration-v1",
        references=[dict(codepoint=cp, glyph_id=cp, status="available",
                         source_commands=copy.deepcopy(exemplar["source_commands"]),
                         source_advance_px=advance, source_pair_adjustment_px=0)
                    for cp, advance in ((110, 4), (72, 5), (48, 4.5))])
    return value


class PageTests(unittest.TestCase):
    def test_whole_text_neighbor_reflows_before_wrapping_and_preserves_original(self):
        solver = Solver(capture())
        text = "AVAV\nAV"
        solved = solver.generate(Controls(spacing_model="balanced", optical=0), text=text)
        before = copy.deepcopy(solved)
        current = solver.layout(text, solved, width=12)
        neighbor = neighbor_text_layout(solver, text, solved, ["AV"], width=12)
        self.assertEqual(solved, before)
        self.assertEqual([len(line["placements"]) for line in current["lines"]], [3, 1, 2])
        self.assertEqual([len(line["placements"]) for line in neighbor["lines"]], [4, 2])
        self.assertEqual(neighbor["lines"][0]["width_px"], 12)
        self.assertEqual(neighbor["lines"][1]["placements"][0]["x_px"], 0)
        self.assertEqual(neighbor_text_layout(solver, text, solved, ["AV"]),
                         neighbor_layout(solver.layout(text, solved), ["AV"]))

    def test_neighbor_layout_shifts_only_selected_gaps_and_resets_at_line_breaks(self):
        value = capture()
        solver = Solver(value)
        text = "AV AV\nVA"
        current = solver.layout(text, solver.generate(Controls(spacing_model="balanced"), text=text))
        before = copy.deepcopy(current)
        neighbor = neighbor_layout(current, ["AV"])
        self.assertEqual(current, before)
        self.assertEqual([b["x_px"] - a["x_px"] for a, b in
                          zip(current["lines"][0]["placements"], neighbor["lines"][0]["placements"])],
                         [0, -1, -1, -1, -2])
        self.assertEqual(neighbor["lines"][0]["width_px"], current["lines"][0]["width_px"] - 2)
        self.assertEqual(neighbor["lines"][1], current["lines"][1])
        for a, b in zip(current["lines"][0]["placements"], neighbor["lines"][0]["placements"]):
            self.assertEqual({k: v for k, v in a.items() if k != "x_px"},
                             {k: v for k, v in b.items() if k != "x_px"})

    def test_optional_neighbor_review_has_python_fixtures_without_changing_tables(self):
        retained = capture()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            raw = json.dumps(retained).encode(); path.write_bytes(raw)
            case = dict(id="synthetic", capturePath=str(path), captureSha256=hashlib.sha256(raw).hexdigest(),
                        codepoints=[g["codepoint"] for g in retained["glyphs"]], models={"balanced": {"unchanged": True}})
            data = dict(cases=[case]); before = copy.deepcopy(case)
            attach_neighbor_review(data, dict(pairs=["AV"], words=["AV AV"], spacingModel="balanced"))
            self.assertEqual(case, before)
            self.assertEqual(data["neighborReview"]["deltaPx"], -1)
            fixtures = data["neighborReviewVerification"]
            self.assertEqual(len(fixtures), 32)
            self.assertEqual({f["oIndex"] for f in fixtures}, {0, 2, 4})
            html = render_html(data)
            self.assertNotIn('"neighborReviewVerification"', html)
            self.assertIn('"neighborReview"', html)
            data["presets"] = [dict(id="full", text="AV AV\nVA")]
            attach_neighbor_review(data, dict(pairs=["AV"], words=["AV AV"], spacingModel="balanced", mode="text"))
            wrapped = [f for f in data["neighborReviewVerification"] if f.get("presetId") == "full"]
            self.assertEqual({f["width"] for f in wrapped}, {160, 280})
            self.assertEqual(data["neighborReview"]["mode"], "text")
            for config in (dict(pairs=["A"], words=[], spacingModel="balanced"),
                           dict(pairs=["AV"], words=[], spacingModel="balanced", deltaPx=-2),
                           dict(pairs=["AV"], words=["A\nV"], spacingModel="balanced")):
                with self.assertRaises(ValueError):
                    attach_neighbor_review(data, config)

    def test_browser_reference_embeds_original_bytes_and_rejects_wrong_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Example.ttf"
            raw = b"original source font bytes"
            path.write_bytes(raw)
            identity = hashlib.sha256(raw).hexdigest()
            case = dict(sourceSha256=identity, sizePx=16, axes={"wght": 400})
            capture = dict(font_path=str(path), source_sha256=identity, size_px=16, axes={"wght": 400})
            attach_browser_reference(case, capture)
            self.assertEqual(case["browserReference"]["fontSha256"], identity)
            self.assertEqual(case["browserReference"]["geometry"], "original_font_bytes")
            path.write_bytes(b"other font")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                attach_browser_reference(case, capture)

    def test_source_layout_keeps_source_metrics_and_retained_binary_glyphs(self):
        captured = capture()
        case = build_case(captured, "capture.json", "capture-sha")
        source = case["sourceLayout"]
        for glyph in captured["glyphs"]:
            self.assertEqual(source["advancesPx"][str(glyph["codepoint"])], glyph["source_advance_px"])
            retained = next(g for g in case["glyphs"] if g["codepoint"] == glyph["codepoint"])
            self.assertEqual(retained["bitmap"], glyph["bitmap"])
        self.assertEqual(source["pairAdjustmentsPx"],
                         {f"{p['left']},{p['right']}": p["adjustment_px"] for p in captured["source_pairs"]})
        wrong = copy.deepcopy(captured)
        wrong["size_px"] += 1
        with self.assertRaisesRegex(ValueError, "must match"):
            attach_source_layout(case, wrong)

    def test_grayscale_capture_retains_levels_and_fractional_source_spacing(self):
        case = dict(sourceSha256="source", sizePx=16, axes={}, codepoints=[65, 86])
        gray = dict(schema_version="contextual-spacing-grayscale-v2", policy="vanilla source layout",
                    spacing_policy="source_linear_26_6",
                    font=dict(source_sha256="source", config=dict(size_px=16, axes={}, output_bits=3,
                              hinting="auto", gray_gamma=1, kerning=True, metric_rounding="subpixel",
                              mono_raster=dict(dropout="smart", include_stubs=False, font_instructions=False)),
                              glyphs=[dict(codepoint=cp, glyph_id=cp, advance_26_6=650, left=0, top=-1,
                                           width=3, height=1, pixels=[1, 4, 7]) for cp in (65, 86)],
                              metrics=dict(ascent_26_6=768, descent_26_6=-256, line_gap_26_6=0),
                              missing_codepoints=[], kerning=[dict(left=65, right=86, adjustment_26_6=-35)]))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gray.json"
            path.write_text(json.dumps(gray))
            attach_grayscale(case, path)
            self.assertEqual(case["grayscale"]["glyphs"][0]["bitmap"]["pixels"], [1, 4, 7])
            self.assertEqual(case["grayscale"]["pairAdjustmentsPx"], {"65,86": -35 / 64})
            self.assertEqual(case["grayscale"]["glyphs"][0]["advancePx"], 650 / 64)
            self.assertEqual(case["grayscale"]["spacingPolicy"], "source_linear_26_6")
            self.assertEqual(case["grayscale"]["metricsDescent"], -4)
            self.assertNotIn("models", case["grayscale"])
            old = copy.deepcopy(gray)
            old["schema_version"] = "contextual-spacing-grayscale-v1"
            path.write_text(json.dumps(old))
            with self.assertRaisesRegex(ValueError, "unsupported grayscale capture"):
                attach_grayscale(case, path)
            for field, value in (("output_bits", 1), ("gray_gamma", 1.5), ("kerning", False), ("axes", {"wght": 700})):
                invalid = copy.deepcopy(gray)
                invalid["font"]["config"][field] = value
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    attach_grayscale(case, path)
            invalid = copy.deepcopy(gray)
            invalid["font"]["glyphs"][0]["pixels"][0] = 8
            path.write_text(json.dumps(invalid))
            with self.assertRaises(ValueError):
                attach_grayscale(case, path)

    def test_presets_retain_exact_text_and_require_complete_repertoire(self):
        presets = [dict(id="digits", label="Numbers", text="01\n10")]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "capture.json"
            source.write_text(json.dumps(capture()))
            catalogue = root / "presets.json"
            catalogue.write_text(json.dumps(presets))
            self.assertEqual(load_presets(catalogue), presets)
            data = build_data([source], presets=presets)
            self.assertEqual(data["presets"], presets)
            self.assertIn('"text":"01\\n10"', render_html(data))
            presets[0]["text"] += "\u2030"
            with self.assertRaisesRegex(ValueError, "Numbers.*U\\+2030"):
                build_data([source], presets=presets)
            for invalid in ({}, [dict(id="x", label="X", text="")], presets * 2):
                catalogue.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    load_presets(catalogue)

    def test_supplied_catalogue_keeps_long_unicode_and_multiline_presets(self):
        presets = load_presets(Path(__file__).resolve().parents[1] / "presets.json")
        self.assertEqual(len(presets), 7)
        self.assertEqual(presets[1]["text"], presets[0]["text"].upper())
        self.assertGreater(len(presets[2]["text"]), 2000)
        self.assertIn("Uzßai", presets[2]["text"])
        self.assertIn("Don’t I’ll I’m I’se", presets[2]["text"])
        self.assertEqual(len(presets[3]["text"].splitlines()), 10)
        self.assertEqual(len(presets[6]["text"].splitlines()), 10)
        self.assertIn("£00", presets[5]["text"])
        self.assertIn("9‰ 9-9.9,9…9°", presets[6]["text"])

    def test_every_model_strength_and_ordered_pair_uses_existing_solver(self):
        value = capture()
        value["tabular_digits"] = True
        two = copy.deepcopy(value["glyphs"][3])
        two.update(codepoint=50, glyph_id=50)
        value["glyphs"].append(two)
        value["capture"] = dict(implementation="current-renderer-test")
        original = copy.deepcopy(value)
        case = build_case(value, "capture.json", "hash", target_separation_em=0.2)
        self.assertEqual(value, original)
        self.assertEqual(case["rendererImplementation"], "current-renderer-test")
        solver = Solver(value)
        self.assertNotIn("pairTables", case)
        self.assertEqual(set(case["models"]), set(DEFAULT_MODELS))
        for model, bundle in case["models"].items():
            self.assertEqual(bundle["targetSeparationEm"], 0.2 if model == "balanced" else None)
            self.assertEqual(bundle["calibration"], solver.calibration_metadata(spacing_model=model)
                             if model in (*HU_MODELS, "filtered_walls", "font_calibrated") else None)
            for preserve, table_key, diagnostic_key in (
                    (False, "pairTables", "pairDiagnostics"),
                    (True, "preservedPairTables", "preservedPairDiagnostics")):
                self.assertEqual(len(bundle[table_key]), 25)
                for ki, k in enumerate(STRENGTHS):
                    for oi, o in enumerate(STRENGTHS):
                        for li, left in enumerate(case["codepoints"]):
                            for ri, right in enumerate(case["codepoints"]):
                                index = li * len(case["glyphs"]) + ri
                                pair = solver.pair(left, right, Controls(k, o, preserve_tabular_spacing=preserve,
                                                  spacing_model=model, target_separation_em=0.2))
                                adjustment = bundle[table_key][ki * 5 + oi][index]
                                self.assertEqual(adjustment, pair["automatic_adjustment_px"])
                                self.assertIs(type(adjustment), int)
                                if model in (*HU_MODELS, "filtered_walls") and (not preserve or model in HU_MODELS):
                                    self.assertEqual(bundle[("preservedPair" if preserve else "pair") + "RoundedUnconstrainedStepsPx"][ki * 5 + oi][index],
                                                     pair["rounded_unconstrained_step_px"])
                                    self.assertEqual(bundle[("preservedPair" if preserve else "pair") + "ClearanceAdjustmentsPx"][ki * 5 + oi][index],
                                                     pair["clearance_adjustment_px"])
                                self.assertEqual(DIAGNOSTIC_LABELS[bundle[diagnostic_key][ki * 5 + oi][index]], pair["diagnostic"])
                                if o == 1:
                                    metadata_key = "preservedPairTargetMetadata" if preserve else "pairTargetMetadata"
                                    metadata = bundle[metadata_key][index]
                                    if model == "hu_source_relative":
                                        metadata = merge_source_metadata(metadata, bundle[metadata_key + "ByKerning"][ki][index])
                                    for key, actual in metadata.items():
                                        self.assertEqual(actual, pair[key])
                                    if not preserve:
                                        self.assertEqual(bundle["pairTargetsPx"][ki][index], pair["target_separation_px"])
                                        offset = bundle["pairGeometryOffsetsPx"][index]
                                        if offset is not None:
                                            self.assertAlmostEqual(offset + pair["resolved_step_px"], pair["realized_separation_px"])
                for ki in range(5):
                    self.assertEqual(bundle["pairTables"][ki * 5], bundle["preservedPairTables"][ki * 5])
        self.assertEqual(case["glyphs"][case["codepoints"].index(65)]["bitmap"], value["glyphs"][1]["bitmap"])
        self.assertEqual(len(case["verification"]), len(case["models"]) * 100)
        self.assertTrue(all("12" in fixture["text"] for fixture in case["verification"]))
        for fixture in case["verification"]:
            controls = Controls(STRENGTHS[fixture["kIndex"]], STRENGTHS[fixture["oIndex"]],
                                fixture["letterSpacing"], fixture["wordSpacing"],
                                preserve_tabular_spacing=fixture["preserveTabularSpacing"],
                                spacing_model=fixture["spacingModel"], target_separation_em=0.2)
            self.assertEqual(fixture["expected"], solver.layout(fixture["text"], solver.generate(controls), fixture["width"]))

    def test_hu_bundle_retains_python_area_policies_and_both_clearance_policies(self):
        value = capture()
        module = types.SimpleNamespace(HuHerschModel=HuHerschStub)
        with patch.dict(sys.modules, hu_calibration=module):
            case = build_case(value, "capture.json", "hash")
            solver = Solver(value)
            bundle = case["models"]["hu_hersch"]
            self.assertEqual(bundle["calibration"]["calibration_geometry"], "delivered")
            for preserve in (False, True):
                prefix = "preservedPair" if preserve else "pair"
                for strength_index, strength in enumerate(STRENGTHS):
                    for index, (left, right) in enumerate((a, b) for a in case["codepoints"] for b in case["codepoints"]):
                        record = solver.pair(left, right, Controls(optical=strength,
                            spacing_model="hu_hersch", preserve_tabular_spacing=preserve))
                        self.assertEqual(bundle[prefix + "ClearanceAdjustmentsPx"][20 + strength_index][index],
                                         record["clearance_adjustment_px"])
                        if strength == 1:
                            metadata = bundle[prefix + "TargetMetadata"][index]
                            for field in ("target_area_px2", "measurement_window_px", "window_height_px",
                                          "reference_pair", "hu_hersch", "clearance_min_step_px"):
                                self.assertEqual(metadata[field], record[field])
            left, right = 65, 86
            index = case["codepoints"].index(left) * len(case["codepoints"]) + case["codepoints"].index(right)
            self.assertIsNotNone(bundle["pairTargetMetadata"][index]["hu_hersch"])
            self.assertEqual(bundle["pairTargetMetadata"][index]["reference_pair"], "HH")

    def test_optional_counterspace_retains_nonlinear_scores_for_both_policies(self):
        class CounterSpaceFixture:
            def __init__(self, retained, calibration_geometry):
                self.retained = retained
                self.geometry = calibration_geometry

            def metadata(self):
                return dict(fit_status="converged", upstream=dict(revision="test", license="Apache-2.0"))

            def pair(self, left, right, search_policy, clearance_min_step):
                step = 7 if self.geometry == "source" else 6
                return dict(optical_step_px=step, unconstrained_step_px=step, target_score=step ** 2,
                            reference_pair="nn", target_crossed=False, candidate_count=5,
                            feasible_candidate_count=3, candidate_domain_min_step_px=4,
                            candidate_domain_stop_step_px=9,
                            search_outcome="target_above_feasible_scores" if search_policy == "closest_feasible" else "peak_without_crossing",
                            first_crossing_step_px=None, first_crossing_score=None,
                            closest_feasible_step_px=step if search_policy == "closest_feasible" else None,
                            closest_feasible_score=step ** 2 if search_policy == "closest_feasible" else None)

            def measure_pair(self, left, right, step):
                return step ** 2  # Nonlinear score must never become a pixel offset.

        value = capture()
        value["tabular_digits"] = True
        module = types.SimpleNamespace(CounterSpaceModel=CounterSpaceFixture)
        with patch.dict(sys.modules, counterspace=module):
            case = build_case(value, "capture.json", "hash", include_counterspace=True)
            solver = Solver(value)
            self.assertEqual(len(case["models"]), len(DEFAULT_MODELS) + len(COUNTERSPACE_MODELS))
            self.assertEqual(len(case["verification"]), len(case["models"]) * 100)
            for model_name in COUNTERSPACE_MODELS:
                bundle = case["models"][model_name]
                self.assertEqual(bundle["pairGeometryOffsetsPx"], [])
                self.assertEqual(bundle["calibration"]["fit_status"], "converged")
                for preserve, prefix in ((False, "pair"), (True, "preservedPair")):
                    for ki, k in enumerate(STRENGTHS):
                        for oi, o in enumerate(STRENGTHS):
                            for li, left in enumerate(case["codepoints"]):
                                for ri, right in enumerate(case["codepoints"]):
                                    index = li * len(case["codepoints"]) + ri
                                    record = solver.pair(left, right, Controls(k, o, preserve_tabular_spacing=preserve,
                                                                             spacing_model=model_name))
                                    for suffix, field in (("TargetScores", "target_score"),
                                                          ("RealizedScores", "realized_score"),
                                                          ("ScoreErrors", "score_error"),
                                                          ("RoundedUnconstrainedStepsPx", "rounded_unconstrained_step_px"),
                                                          ("ClearanceAdjustmentsPx", "clearance_adjustment_px")):
                                        self.assertEqual(bundle[prefix + suffix][ki * 5 + oi][index], record[field])
                                    if oi == 4 and ki == 0:
                                        metadata_key = "preservedPairTargetMetadata" if preserve else "pairTargetMetadata"
                                        for field in ("calibration_geometry", "search_policy", "search_outcome", "candidate_count",
                                                      "target_crossed", "closest_feasible_step_px", "first_crossing_step_px"):
                                            self.assertEqual(bundle[metadata_key][index][field], record[field])
            with tempfile.TemporaryDirectory() as temporary:
                source = Path(temporary) / "capture.json"
                source.write_text(json.dumps(value))
                data = build_data([source], include_counterspace=True)
                self.assertEqual(data["schema_version"], "contextual-spacing-page-v9")
                self.assertEqual(data["defaultSpacingModel"], "hu_hersch")
            class SerialExecutor:
                def __init__(self, max_workers):
                    self.max_workers = max_workers

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    pass

                def map(self, operation, requests):
                    return map(operation, requests)

            with tempfile.TemporaryDirectory() as temporary:
                paths = []
                for index in range(2):
                    retained = copy.deepcopy(value)
                    retained["source_sha256"] = str(index) * 64
                    source = Path(temporary) / f"capture-{index}.json"
                    source.write_text(json.dumps(retained))
                    paths.append(source)
                with patch("page.ProcessPoolExecutor", side_effect=SerialExecutor) as executor:
                    parallel = build_data(paths, include_counterspace=True)
                executor.assert_called_once_with(max_workers=2)
                self.assertEqual([case["capturePath"] for case in parallel["cases"]], list(map(str, paths)))
            # The legacy comparison export does not import the optional adapter.
            with patch.object(module, "CounterSpaceModel", side_effect=AssertionError("optional dependency loaded")):
                self.assertEqual(len(build_case(value, "capture.json", "hash")["models"]), len(DEFAULT_MODELS))

    def test_calibration_metadata_reference_scope_and_missing_reference_fallback(self):
        value = capture()
        case = build_case(value, "capture.json", "hash")
        self.assertEqual(case["calibration"], Solver(value).calibration_metadata())
        self.assertEqual(case["calibration"], case["models"]["filtered_walls"]["calibration"])
        self.assertNotEqual(case["calibration"], case["models"]["font_calibrated"]["calibration"])
        self.assertNotIn(110, case["codepoints"])
        self.assertNotIn(72, case["codepoints"])
        self.assertEqual(len(case["models"]["font_calibrated"]["pairTables"][24]), len(value["glyphs"]) ** 2)
        value["source_calibration"]["references"] = []
        missing = build_case(value, "capture.json", "hash")
        self.assertEqual(missing["calibration"]["classes"]["uppercase"]["status"], "unavailable")
        index = missing["codepoints"].index(65) * len(missing["codepoints"]) + missing["codepoints"].index(86)
        bundle = missing["models"]["font_calibrated"]
        self.assertEqual(DIAGNOSTIC_LABELS[bundle["pairDiagnostics"][24][index]], "calibration_unavailable")
        self.assertEqual(bundle["pairTables"][24][index], bundle["pairTables"][20][index])
        self.assertNotEqual(case["analysisIdentity"], missing["analysisIdentity"])
        invalid = capture()
        invalid["source_calibration"]["references"][0]["source_advance_px"] = float("nan")
        with self.assertRaises(ValueError):
            build_case(invalid, "capture.json", "hash")

    def test_configured_target_is_validated_and_changes_balanced_tables(self):
        small = build_case(capture(), "capture.json", "hash", target_separation_em=0.1)
        large = build_case(capture(), "capture.json", "hash", target_separation_em=0.3)
        self.assertNotEqual(small["models"]["balanced"]["pairTables"][24], large["models"]["balanced"]["pairTables"][24])
        for model in (*(model for model in HU_MODELS if model not in DENSITY_MODELS), "filtered_walls", "source_relative", "font_calibrated"):
            self.assertEqual(small["models"][model]["pairTables"], large["models"][model]["pairTables"])
        for target in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(target=target), self.assertRaises(ValueError):
                build_case(capture(), "capture.json", "hash", target_separation_em=target)

    def test_unpreserved_digit_geometry_failure_cannot_become_complete_page(self):
        value = capture()
        value["tabular_digits"] = True
        value["glyphs"] = [glyph for glyph in value["glyphs"] if glyph["codepoint"] in (48, 49)]
        value["source_pairs"] = value["metric_pairs_on"] = []
        value["glyphs"][1]["source_commands"][1]["x"] = 100000
        with self.assertRaisesRegex(ValueError, "incomplete pair table.*preserve_tabular_spacing=false"):
            build_case(value, "capture.json", "hash")

    def test_incomplete_unsupported_nonfinite_and_gray_cannot_export(self):
        value = capture()
        with self.assertRaisesRegex(ValueError, "incomplete pair table"):
            build_case(value, "capture.json", "hash", work_limit=2)
        value["glyphs"][1]["source_commands"][1]["x"] = 100000
        with self.assertRaisesRegex(ValueError, "incomplete pair table"):
            build_case(value, "capture.json", "hash")
        value = capture()
        value["glyphs"][1]["source_advance_px"] = float("nan")
        with self.assertRaises(ValueError):
            build_case(value, "capture.json", "hash")
        value = capture()
        value["produced_settings"] = dict(output_bits=3)
        with self.assertRaisesRegex(ValueError, "optical tables require retained Mono"):
            build_case(value, "capture.json", "hash")
        value = capture()
        value["monospace"] = True
        value["glyphs"][1]["bitmap"]["pixels"][0] = 7
        with self.assertRaisesRegex(ValueError, "1-bit bitmap"):
            build_case(value, "capture.json", "hash")

    def test_metadata_cannot_escape_script_or_be_replaced_as_a_template_token(self):
        attack = '</script><script>alert("x")</script>&\u2028\u2029__SCRIPT__'
        encoded = embedded_json({"label": attack})
        self.assertNotIn("<", encoded)
        self.assertNotIn(">", encoded)
        self.assertNotIn("&", encoded)
        self.assertNotIn("\u2028", encoded)
        self.assertEqual(json.loads(encoded)["label"], attack)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            self.assets(directory)
            html = render_html({"label": attack}, directory)
            self.assertEqual(html.count("</script>"), 2)
            self.assertIn("__SCRIPT__", html)
            self.assertEqual(html.count("window.ready = true;"), 1)

    def test_embedded_page_omits_diagnostic_fixtures_but_retains_runtime_data(self):
        case = build_case(capture(), "capture.json", "hash")
        data = dict(cases=[case], defaultText=case["defaultText"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assets(directory)
            html = render_html(data, directory)
        embedded = json.loads(re.search(r'<script type="application/json">(.*?)</script>', html).group(1))
        self.assertNotIn("verification", embedded["cases"][0])
        self.assertEqual(embedded["cases"][0]["models"], case["models"])
        self.assertEqual(embedded["cases"][0]["glyphs"], case["glyphs"])
        self.assertEqual(len(data["cases"][0]["verification"]), len(case["models"]) * 100)

    @staticmethod
    def assets(directory):
        (directory / "page.html").write_text('<style>__STYLE__</style><script type="application/json">__DATA__</script><script>__SCRIPT__</script>')
        (directory / "page.js").write_text("window.ready = true;")
        (directory / "page.css").write_text("body { color: black; }")

    def test_source_hu_metadata_selects_authoritative_target_at_each_kerning_strength(self):
        value = capture()
        reference = copy.deepcopy(value["glyphs"][1])
        reference.update(codepoint=72, glyph_id=72)
        value["glyphs"].append(reference)
        case = build_case(value, "capture.json", "hash")
        solver, bundle = Solver(value), case["models"]["hu_source_relative"]
        index = case["codepoints"].index(65) * len(case["codepoints"]) + case["codepoints"].index(86)
        for preserve in (False, True):
            prefix = "preservedPair" if preserve else "pair"
            for k_index, strength in enumerate(STRENGTHS):
                record = solver.pair(65, 86, Controls(source_kerning=strength,
                    spacing_model="hu_source_relative", preserve_tabular_spacing=preserve))
                metadata = merge_source_metadata(bundle[prefix + "TargetMetadata"][index],
                    bundle[prefix + "TargetMetadataByKerning"][k_index][index])
                for field, actual in metadata.items():
                    self.assertEqual(actual, record[field])
                self.assertAlmostEqual(metadata["source_step_px"], 4 - 0.75 * strength)
                self.assertEqual(metadata["hu_hersch"]["source_kerning"], strength)
                self.assertEqual(bundle["pairTargetsPx"][k_index][index], record["source_target_px"])
        self.assertNotEqual(bundle["pairTargetsPx"][0][index], bundle["pairTargetsPx"][4][index])

    def test_initial_model_is_export_configuration_and_requires_an_included_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            path.write_text(json.dumps(capture()))
            shared = build_data([path])
            relative = build_data([path], default_spacing_model="hu_source_relative")
            self.assertEqual(shared["defaultSpacingModel"], "hu_hersch")
            self.assertEqual(relative["defaultSpacingModel"], "hu_source_relative")
            self.assertEqual(shared["cases"], relative["cases"])
            for unavailable in ("counterspace", "unknown", None):
                with self.assertRaisesRegex(ValueError, "default spacing model must be included"):
                    build_data([path], default_spacing_model=unavailable)
            published = export_page(Path(temporary) / "site", [path], default_spacing_model="hu_source_relative")
            self.assertEqual(published["defaultSpacingModel"], "hu_source_relative")

    def test_fixed_alphabet_models_are_opt_in_and_selected_tables_match_solver(self):
        from test_hu_density import complete_capture, rectangle
        self.assertTrue(set(DENSITY_MODELS).issubset(BASE_MODELS))
        self.assertTrue(set(DENSITY_MODELS).isdisjoint(DEFAULT_MODELS))
        retained = complete_capture()
        # A positive quarter-pixel target makes touching optimal on these
        # rectangles; strict clearance must add a pixel while no-overlap does not.
        for glyph in retained["glyphs"]:
            glyph["source_advance_px"] = 2.25
            glyph["finalized_advance_px"] = 2
            if glyph["bitmap"]["pixels"]:
                glyph["produced_commands"] = rectangle(width=3 if glyph["codepoint"] == 110 else 2,
                                                       height=glyph["bitmap"]["height"], scale=1)

        class BoundedSolver(Solver):
            def __init__(self, value):
                super().__init__(value)
                # Calibration still receives the complete immutable capture.
                # Bound the exporter table domain to exercise actual math cheaply.
                self.glyphs = {cp: self.glyphs[cp] for cp in (32, 49, 50, 110, 111, 114)}

        def attach_bounded_source(case, value):
            subset = set(case["codepoints"])
            view = dict(value, glyphs=[glyph for glyph in value["glyphs"] if glyph["codepoint"] in subset],
                        source_pairs=[pair for pair in value["source_pairs"]
                                      if pair["left"] in subset and pair["right"] in subset])
            attach_source_layout(case, view)

        selected = ["hu_source_calibrated", *DENSITY_MODELS]
        with patch("page.Solver", BoundedSolver), patch("page.attach_source_layout", attach_bounded_source):
            case = build_case(retained, "fixed-alphabet.json", "hash", spacing_models=selected)
        self.assertEqual(list(case["models"]), selected)
        self.assertEqual(len(case["verification"]), len(selected) * 100)
        solver = BoundedSolver(retained)
        for model in DENSITY_MODELS:
            bundle = case["models"][model]
            self.assertEqual(bundle["calibration"], solver.calibration_metadata(spacing_model=model))
            lower = bundle["calibration"]["classes"]["lowercase"]
            self.assertEqual(lower["status"], "available")
            self.assertEqual(lower["pair_count"], 26 ** 2)
            if model != "hu_alphabet_source_target":
                self.assertAlmostEqual(lower["continuous_mean_origin_residual_px"], 0)
            for preserve, prefix in ((False, "pair"), (True, "preservedPair")):
                for ki, k in enumerate(STRENGTHS):
                    for oi, o in enumerate(STRENGTHS):
                        result = solver.generate(Controls(k, o, preserve_tabular_spacing=preserve, spacing_model=model))
                        records = result["pairs"]
                        self.assertEqual(bundle[prefix + "Tables"][ki * 5 + oi],
                                         [record["automatic_adjustment_px"] for record in records])
                        self.assertEqual(bundle[prefix + "Diagnostics"][ki * 5 + oi],
                                         [DIAGNOSTIC_LABELS.index(record["diagnostic"]) for record in records])
                        if o == 1:
                            for index, record in enumerate(records):
                                metadata = bundle[prefix + "TargetMetadata"][index]
                                for field, actual in metadata.items():
                                    self.assertEqual(actual, record[field])
            # The table subset cannot silently choose a smaller calibration alphabet.
            self.assertEqual(lower["pair_domain"]["ordered_pairs"], 26 ** 2)
        strict = case["models"]["hu_density_conserved"]
        touching = case["models"]["hu_density_conserved_touch"]
        self.assertEqual(strict["pairTargetsPx"], touching["pairTargetsPx"])
        self.assertEqual(strict["pairGeometryOffsetsPx"], touching["pairGeometryOffsetsPx"])
        index = case["codepoints"].index(110) * len(case["codepoints"]) + case["codepoints"].index(111)
        self.assertEqual(strict["pairTargetMetadata"][index]["clearance_policy"], "strict")
        self.assertEqual(touching["pairTargetMetadata"][index]["clearance_policy"], "no_overlap")
        self.assertEqual(touching["calibration"]["clearance_policy"], "no_overlap")
        self.assertEqual(strict["pairTables"][24][index], 1)
        self.assertEqual(touching["pairTables"][24][index], 0)
        self.assertEqual(strict["pairRoundedUnconstrainedStepsPx"], touching["pairRoundedUnconstrainedStepsPx"])
        fitted = case["models"]["hu_fitted_density_conserved_touch"]
        self.assertEqual(touching["calibration"]["candidate_geometry"], "bitmap")
        self.assertEqual(fitted["calibration"]["candidate_geometry"], "fitted_outline")
        self.assertEqual(fitted["calibration"]["clearance_policy"], "no_overlap")
        self.assertEqual(fitted["pairTargetMetadata"][index]["candidate_geometry"], "fitted_outline")
        self.assertNotEqual(fitted["pairTargetMetadata"][index]["measurement_method"],
                            touching["pairTargetMetadata"][index]["measurement_method"])
        self.assertNotEqual(fitted["pairGeometryOffsetsPx"][index], touching["pairGeometryOffsetsPx"][index])
        self.assertNotEqual(fitted["pairTargetsPx"], touching["pairTargetsPx"])
        self.assertNotEqual(fitted["pairTables"][24][index], touching["pairTables"][24][index])
        self.assertEqual(fitted["pairTargetMetadata"][index]["clearance_min_step_px"],
                         touching["pairTargetMetadata"][index]["clearance_min_step_px"])
        complete = case["models"]["hu_fitted_full_density_conserved_touch"]
        self.assertEqual(complete["calibration"]["candidate_geometry"], "fitted_outline")
        self.assertEqual(complete["calibration"]["construction_policy"], "full_outline")
        self.assertEqual(complete["calibration"]["clearance_policy"], "no_overlap")
        self.assertNotEqual(complete["pairTargetMetadata"][index]["measurement_method"],
                            fitted["pairTargetMetadata"][index]["measurement_method"])
        self.assertEqual(complete["pairTargetMetadata"][index]["clearance_min_step_px"],
                         fitted["pairTargetMetadata"][index]["clearance_min_step_px"])
        for k_index in range(len(STRENGTHS)):
            # The optical-zero endpoint is metric placement for both models,
            # independent of the construction/calibration policy.
            row = k_index * len(STRENGTHS)
            self.assertEqual(complete["pairTables"][row], fitted["pairTables"][row])
        retained_by_cp = {g["codepoint"]: g for g in retained["glyphs"]}
        self.assertTrue(all(glyph["bitmap"] == retained_by_cp[glyph["codepoint"]]["bitmap"] for glyph in case["glyphs"]))
        for fixture in case["verification"]:
            controls = Controls(STRENGTHS[fixture["kIndex"]], STRENGTHS[fixture["oIndex"]],
                                fixture["letterSpacing"], fixture["wordSpacing"],
                                preserve_tabular_spacing=fixture["preserveTabularSpacing"],
                                spacing_model=fixture["spacingModel"])
            self.assertEqual(fixture["expected"], solver.layout(fixture["text"], solver.generate(controls), fixture["width"]))

        comparison_models = ["hu_fitted_density_conserved_touch", "hu_fitted_full_density_conserved_touch"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            path.write_text(json.dumps(retained))
            with patch("page.Solver", BoundedSolver), patch("page.attach_source_layout", attach_bounded_source):
                for requested in (comparison_models, list(reversed(comparison_models))):
                    compared = build_data([path], spacing_models=requested, default_spacing_model=comparison_models[1])
                    self.assertEqual(compared["comparisonModels"], comparison_models)
                    self.assertEqual(list(compared["cases"][0]["models"]), requested)
                standalone = build_data([path], spacing_models=comparison_models[1:],
                                        default_spacing_model=comparison_models[1])
                self.assertNotIn("comparisonModels", standalone)

    def test_selected_models_export_only_completed_requested_tables(self):
        models = ["hu_hersch", "hu_source_calibrated"]
        value = capture()
        case = build_case(value, "capture.json", "capture-sha", spacing_models=models)
        self.assertEqual(list(case["models"]), models)
        self.assertEqual(case["glyphs"], build_case(value, "capture.json", "capture-sha", spacing_models=["hu_hersch"])["glyphs"])
        bundle = case["models"]["hu_source_calibrated"]
        solver = Solver(value)
        for k_index, k in enumerate(STRENGTHS):
            for o_index, o in enumerate(STRENGTHS):
                records = solver.generate(Controls(source_kerning=k, optical=o, spacing_model="hu_source_calibrated",
                                                  preserve_tabular_spacing=False))["pairs"]
                self.assertEqual(bundle["pairTables"][k_index * 5 + o_index],
                                 [r["automatic_adjustment_px"] for r in records])
        for invalid in ([], ["unknown"], ["hu_hersch", "hu_hersch"]):
            with self.assertRaisesRegex(ValueError, "nonempty, unique and available"):
                build_case(value, "capture.json", "capture-sha", spacing_models=invalid)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            path.write_text(json.dumps(value))
            data = build_data([path], spacing_models=models, default_spacing_model="hu_source_calibrated")
            self.assertEqual(data["defaultSpacingModel"], "hu_source_calibrated")
            self.assertEqual(list(data["cases"][0]["models"]), models)
            self.assertNotIn("comparisonModels", data)
            with self.assertRaisesRegex(ValueError, "default spacing model must be included"):
                build_data([path], spacing_models=["hu_source_calibrated"])

    def test_complete_offline_bundle_has_hashes_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "capture.json"
            source.write_text(json.dumps(capture()))
            assets = root / "assets"
            assets.mkdir()
            self.assets(assets)
            output = root / "output"
            exported = export_page(output, [source], asset_directory=assets)
            self.assertEqual(exported["status"], "complete")
            data = json.loads((output / "page-data.json").read_text())
            self.assertEqual(data, exported)
            self.assertEqual(data["defaultText"], data["cases"][0]["defaultText"])
            self.assertEqual(data["schema_version"], "contextual-spacing-page-v9")
            self.assertEqual(data["diagnosticLabels"], DIAGNOSTIC_LABELS)
            self.assertIs(data["defaultPreserveTabularSpacing"], False)
            self.assertEqual(data["defaultSpacingModel"], "hu_hersch")
            self.assertEqual(data["targetSeparationEm"], 0.15)
            manifest = json.loads((output / "page-manifest.json").read_text())
            self.assertEqual(manifest["pageSha256"], hashlib.sha256((output / "index.html").read_bytes()).hexdigest())
            self.assertEqual(manifest["dataSha256"], hashlib.sha256((output / "page-data.json").read_bytes()).hexdigest())
            self.assertEqual(data["cases"][0]["captureSha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaises(FileExistsError):
                export_page(output, [source], asset_directory=assets)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
            empty = root / "existing-empty"
            empty.mkdir()
            with self.assertRaises(FileExistsError):
                export_page(empty, [source], asset_directory=assets)
            self.assertEqual(list(empty.iterdir()), [])
            with self.assertRaisesRegex(ValueError, "duplicate captured case"):
                build_data([source, source])

    def test_failure_leaves_no_output_or_partial_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "capture.json"
            source.write_text(json.dumps(capture()))
            assets = root / "assets"
            assets.mkdir()
            self.assets(assets)
            output = root / "output"
            with self.assertRaisesRegex(ValueError, "incomplete pair table"):
                export_page(output, [source], work_limit=2, asset_directory=assets)
            self.assertFalse(output.exists())
            with patch("page.os.replace", side_effect=OSError("simulated publish failure")):
                with self.assertRaisesRegex(OSError, "simulated publish failure"):
                    export_page(output, [source], asset_directory=assets)
            self.assertFalse(output.exists())
            self.assertFalse(list(root.glob(".output-*")))


if __name__ == "__main__":
    unittest.main()
