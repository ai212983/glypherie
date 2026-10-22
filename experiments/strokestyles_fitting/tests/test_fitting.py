"""StrokeStyles consumer invariants; algebra controls, not optical proof.

Synthetic fixtures carry extractor tags starting with "synthetic-" and
are never presented as upstream output. Coupling, contrast, frozen
axes/anchors, unchanged commands/advances, transforms and safe fallback
are geometric checks only.
"""

import json
import math
import os
import sys
import tempfile
import unittest

import numpy as np

import experiments.strokestyles_fitting.fitting as fitting
import experiments.strokestyles_fitting.fit as fit_cli

UPEM = 2048.0
SIZE = 16.0
SCALE = SIZE / UPEM
SYNTHETIC = "synthetic-algebra-control-v1"


def _load_real_fixture():
    """Tracked deterministic regression fixture (sibling directory).

    Minimized real subset: analysis glyphs lIkA (strokes, connectivity,
    junctions, conventions) plus the Roboto400 capture blocks the cold
    tests read (16px selective_default, 12px auto_default) with records
    pruned to codepoint and source/fitted commands. Provenance and
    rebuild notes live in fixtures/README.md.
    """
    from pathlib import Path as _Path
    path = (_Path(__file__).resolve().parent / "fixtures"
            / "roboto400-regression.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def px(units):
    return units * SCALE


def cmds(contours):
    out = []
    for contour in contours:
        out.append({"op": "move_to", "x": contour[0][0], "y": contour[0][1]})
        for pt in contour[1:]:
            out.append({"op": "line_to", "x": pt[0], "y": pt[1]})
        out.append({"op": "close"})
    return out


def quad_stroke(p0, p1, radius, samples=65):
    """Single straight constant-width stroke contour in pixels.

    Dense sampling mirrors upstream reskeleton density; the consumer's
    per-run tolerance derives from recorded sample gaps.
    """
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    delta = p1 - p0
    length = float(np.linalg.norm(delta))
    tangent = delta / length
    normal = np.array([-tangent[1], tangent[0]])
    spine = [p0 + (p1 - p0) * t for t in np.linspace(0, 1, samples)]
    contour = [tuple(p0 + normal * radius), tuple(p1 + normal * radius),
               tuple(p1 - normal * radius), tuple(p0 - normal * radius)]
    return contour, spine, [radius] * samples


def anchor_stem():
    """Upright rect source/fitted pair with integral fitted bounds."""
    source = [(px(1024), px(0)), (px(1024), px(1536)),
              (px(1216), px(1536)), (px(1216), px(0))]
    fitted = [(8.0, 0.0), (8.0, 12.0), (9.0, 12.0), (9.0, 0.0)]
    spine = [(1120, y) for y in np.linspace(100, 1400, 65)]
    return source, fitted, spine, [96.0] * 65


def analysis_record(entries):
    glyphs = {}
    for char, strokes in entries.items():
        glyphs[char] = {
            "strokes": [{"P": p, "Wv": r, "W": r[:-1]} for p, r, _ in strokes],
            "connectivity": {"links": [], "joins": [],
                             "terminals": [{"stroke": i, "terminal": t}
                                           for i in range(len(strokes))
                                           for t in (0, 1)]},
            "junctions": []}
    return {"schema_version": "extract-record-v2",
            "provenance": {"source_font_sha256": "test-fixture",
                           "axes_resolved": {},
                           "units_per_em": UPEM,
                           "extractor": SYNTHETIC},
            "glyphs": glyphs}


def source_units(contour_px):
    return [[c / SCALE for c in pt] for pt in contour_px]


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        contour, spine, radii = quad_stroke((2.0, 0.0), (5.0, 8.0), 0.66)
        self.diag = (contour, spine, radii)
        src, fit, spine_a, radii_a = anchor_stem()
        self.anchor = (src, fit, spine_a, radii_a)

    def _glyphs(self):
        contour, spine, radii = self.diag
        src, fit, spine_a, radii_a = self.anchor
        strokes_d = [(source_units(spine), [r / SCALE for r in radii], None),
                     ([list(p) for p in spine_a], radii_a, None)]
        strokes_a = [([list(p) for p in spine_a], radii_a, None)]
        record = analysis_record({"D": strokes_d, "I": strokes_a})
        validated = fitting.validate_analysis(record)
        self.assertTrue(validated["supported"])
        glyph_d = validated["glyphs"]["D"]
        glyph_a = validated["glyphs"]["I"]
        source_cmds = cmds([contour, src])
        fitted_cmds = cmds([contour, fit])
        return glyph_d, glyph_a, source_cmds, fitted_cmds, validated["upem"]

    def test_synthetic_mark(self):
        self.assertTrue(SYNTHETIC.startswith("synthetic-"))

    def test_width_coupling(self):
        glyph_d, glyph_a, source_cmds, fitted_cmds, upem = self._glyphs()
        reference = fitting.build_reference(
            [{"char": "I", "source_cmds": cmds([self.anchor[0]]),
              "fitted_cmds": cmds([self.anchor[1]]), "size_px": SIZE,
              "analysis": glyph_a, "upem": upem}])
        self.assertTrue(reference["supported"])
        self.assertAlmostEqual(reference["rel"], -1 / 3, places=9)
        result = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                   glyph_d, upem, reference, (False, False))
        self.assertTrue(result["applied"], result.get("reason"))
        width = result["widths"][0]
        self.assertLess(width["candidate_rel"], width["upstream_rel"])
        self.assertAlmostEqual(width["candidate_rel"], -1 / 3, delta=0.08)
        self.assertLessEqual(result["movement"], result["bound"])
        self.assertTrue(all(result["validity"].values()))
        self.assertLess(result["cost_candidate"], result["cost_upstream"])

    def test_source_contrast(self):
        thin, spine_thin, radii_thin = quad_stroke((12.0, 0.0), (15.0, 8.0),
                                                  0.47)
        contour, spine, radii = self.diag
        src, fit, spine_a, radii_a = self.anchor
        record = analysis_record({
            "D": [(source_units(spine), [r / SCALE for r in radii], None),
                  (source_units(spine_thin),
                   [r / SCALE for r in radii_thin], None)],
            "I": [([list(p) for p in spine_a], radii_a, None)]})
        validated = fitting.validate_analysis(record)
        glyph_d = validated["glyphs"]["D"]
        upem = validated["upem"]
        source_cmds = cmds([contour, thin, src])
        fitted_cmds = cmds([contour, thin, fit])
        reference = fitting.build_reference(
            [{"char": "I", "source_cmds": cmds([src]),
              "fitted_cmds": cmds([fit]), "size_px": SIZE,
              "analysis": validated["glyphs"]["I"], "upem": upem}])
        result = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                   glyph_d, upem, reference, (False, False))
        self.assertTrue(result["applied"], result.get("reason"))
        self.assertEqual(len(result["widths"]), 2)
        before = [w["ws"] for w in result["widths"]]
        after = [w["candidate"] for w in result["widths"]]
        self.assertAlmostEqual(after[0] / after[1], before[0] / before[1],
                               delta=0.05 * before[0] / before[1])

    def test_native_axis_frozen(self):
        glyph_d, glyph_a, source_cmds, fitted_cmds, upem = self._glyphs()
        reference = fitting.build_reference(
            [{"char": "I", "source_cmds": cmds([self.anchor[0]]),
              "fitted_cmds": cmds([self.anchor[1]]), "size_px": SIZE,
              "analysis": glyph_a, "upem": upem}])
        result = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                   glyph_d, upem, reference, (False, True))
        self.assertTrue(result["applied"], result.get("reason"))
        fitted_xy = [(c.get("x"), c.get("y")) for c in fitted_cmds]
        cand_xy = [(c.get("x"), c.get("y"))
                   for c in result["candidate_commands"]]
        for (fx, fy), (cx, cy) in zip(fitted_xy, cand_xy):
            if fy is not None:
                self.assertEqual(cy, fy)

    def test_anchor_fixed_and_commands_unchanged(self):
        glyph_d, glyph_a, source_cmds, fitted_cmds, upem = self._glyphs()
        reference = fitting.build_reference(
            [{"char": "I", "source_cmds": cmds([self.anchor[0]]),
              "fitted_cmds": cmds([self.anchor[1]]), "size_px": SIZE,
              "analysis": glyph_a, "upem": upem}])
        result = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                   glyph_d, upem, reference, (False, False))
        self.assertTrue(result["applied"], result.get("reason"))
        src_ops = [c["op"] for c in source_cmds]
        cand_ops = [c["op"] for c in result["candidate_commands"]]
        self.assertEqual(src_ops, cand_ops)
        fitted_xy = {i: (c.get("x"), c.get("y"))
                     for i, c in enumerate(fitted_cmds)}
        cand_xy = {i: (c.get("x"), c.get("y"))
                   for i, c in enumerate(result["candidate_commands"])}
        n_diag = len(cmds([self.diag[0]]))
        for i in range(n_diag, len(fitted_cmds)):
            self.assertEqual(cand_xy[i], fitted_xy[i])
        for cmd in result["candidate_commands"]:
            for key in ("x", "y"):
                if key in cmd:
                    import struct as _struct
                    self.assertEqual(
                        cmd[key + "_bits"],
                        _struct.unpack(">I", _struct.pack(">f", cmd[key]))[0])

    def test_translation_invariant(self):
        glyph_d, glyph_a, source_cmds, fitted_cmds, upem = self._glyphs()
        cases = [{"char": "I", "source_cmds": cmds([self.anchor[0]]),
                  "fitted_cmds": cmds([self.anchor[1]]), "size_px": SIZE,
                  "analysis": glyph_a, "upem": upem}]
        reference = fitting.build_reference(cases)

        def shift(commands, dx, dy):
            moved = []
            for cmd in commands:
                cmd = dict(cmd)
                if "x" in cmd:
                    cmd["x"] += dx
                    cmd["y"] += dy
                moved.append(cmd)
            return moved

        first = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                  glyph_d, upem, reference, (False, False))
        moved_src = shift(source_cmds, 3.0, -2.0)
        moved_fit = shift(fitted_cmds, 3.0, -2.0)
        moved_glyph = {
            "strokes": [{"spine": (s["spine"] + np.array(
                [3.0 / SCALE, -2.0 / SCALE])), "radii": s["radii"]}
                        for s in glyph_d["strokes"]],
            "connectivity": glyph_d["connectivity"]}
        second = fitting.run_glyph("D", moved_src, moved_fit, SIZE,
                                   moved_glyph, upem, reference,
                                   (False, False))
        self.assertTrue(first["applied"] and second["applied"])
        for a, b in zip(first["widths"], second["widths"]):
            self.assertAlmostEqual(a["candidate"], b["candidate"], places=6)

    def test_malformed_abstains(self):
        glyph_d, glyph_a, source_cmds, fitted_cmds, upem = self._glyphs()
        reference = fitting.build_reference(
            [{"char": "I", "source_cmds": cmds([self.anchor[0]]),
              "fitted_cmds": cmds([self.anchor[1]]), "size_px": SIZE,
              "analysis": glyph_a, "upem": upem}])
        bad_glyphs = [{}, {"strokes": []},
                      {"strokes": [{"spine": [[0, 0]], "radii": [1]}],
                       "connectivity": {}},
                      {"strokes": [{"spine": [[0, 0], [1, 1]],
                                    "radii": [1, -2]}],
                       "connectivity": {"links": [], "joins": [],
                                        "terminals": []}},
                      {"strokes": [{"spine": [[0, 0], [1, float("nan")]],
                                    "radii": [1, 1]}],
                       "connectivity": {"links": [], "joins": [],
                                        "terminals": []}},
                      None, []]
        for bad in bad_glyphs:
            result = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                       bad, upem, reference, (False, False))
            self.assertFalse(result["applied"])
            self.assertIn(result["reason"],
                          ("unsupported-analysis", "unsupported-connectivity",
                           "no-upright-reference"))
        bad_records = [{}, {"schema_version": "nope"},
                       {"schema_version": "extract-record-v2"}]
        for bad in bad_records:
            validated = fitting.validate_analysis(bad)
            self.assertFalse(validated["supported"])

    def test_radii_shapes_rejected(self):
        base = {"schema_version": "extract-record-v2",
                "provenance": {"source_font_sha256": "test-fixture",
                               "axes_resolved": {},
                               "units_per_em": UPEM,
                               "extractor": SYNTHETIC},
                "glyphs": {}}

        def check(strokes):
            record = dict(base)
            record["glyphs"] = {
                "D": {"strokes": strokes,
                      "connectivity": {"links": [], "joins": [],
                                       "terminals": []},
                      "junctions": []}}
            return fitting.validate_analysis(record)["supported"]

        self.assertFalse(check([{"P": [[0, 0], [1, 1], [2, 2]],
                                 "Wv": [1, 1], "W": [1, 1]}]))
        self.assertFalse(check([{"P": [[0, 0], [1, 1]], "Wv": [1, 1],
                                 "W": [1], "W_full": [3.0]}]))
        self.assertFalse(check([{"P": [[0, 0], [1, 1]], "Wv": [1, -1],
                                 "W": [1]}]))

    def test_provenance_match(self):
        provenance = {"source_font_sha256": "abc", "axes_resolved": {},
                      "units_per_em": UPEM}
        ok, _ = fitting.match_provenance(provenance, "abc", {})
        self.assertTrue(ok)
        ok, reason = fitting.match_provenance(provenance, "other", {})
        self.assertFalse(ok)
        self.assertEqual(reason, "provenance-mismatch-font")
        ok, reason = fitting.match_provenance(provenance, "abc",
                                              {"wght": 400})
        self.assertFalse(ok)
        self.assertEqual(reason, "provenance-mismatch-axes")

    def test_disabled_byte_identical(self):
        record = {"codepoint": 68, "fitted_commands": [
            {"op": "move_to", "x": 1.0, "y": 2.0},
            {"op": "line_to", "x": 3.0, "y": 4.0},
            {"op": "close"}],
            "advance_26_6": 512, "hinted_advance_width": 8.0,
            "hinted_lsb": 1.0, "hinted_has_overlaps": False,
            "left": 1, "top": 2, "width": 3, "height": 4}
        captures = [{"size": 16.0, "modes": {"selective_default": {
            "source_sha256": "s", "axes": {},
            "records": [record]}}}]
        with tempfile.TemporaryDirectory() as tmp:
            caps = os.path.join(tmp, "captures.json")
            with open(caps, "w") as handle:
                json.dump(captures, handle)
            out = os.path.join(tmp, "out")
            self.assertNotIn("run_extract", sys.modules)
            code = fit_cli.main(["--captures", caps, "--mode",
                                 "selective_default", "--out", out])
            self.assertEqual(code, 0)
            self.assertNotIn("run_extract", sys.modules)
            with open(os.path.join(out, "selective_default",
                                   "summary.json")) as handle:
                summary = json.load(handle)
            self.assertFalse(summary["enabled"])
            self.assertEqual(summary["applied"], 0)
            import glob as _glob
            files = _glob.glob(os.path.join(out, "selective_default",
                                            "U+0044_*.json"))
            self.assertEqual(len(files), 1)
            with open(files[0]) as handle:
                case = json.load(handle)
            self.assertEqual(case["candidate_commands"],
                             record["fitted_commands"])
            self.assertEqual(case["metrics"]["advance_26_6"], 512)
            self.assertEqual(case["metrics"]["hinted_advance_width"], 8.0)
            self.assertEqual(case["reason"], "strokestyles-disabled")

    def test_native_axes_conservative(self):
        explicit = {"selective_fitting": {"native_axes": [False, True]},
                    "selected_engine": "auto_x_native_y"}
        self.assertEqual(fit_cli._native_axes(explicit, "selective_default"),
                         [False, True])
        fallback = {"selected_engine": "interpreter",
                    "font_scan": {"enabled": True}}
        self.assertEqual(fit_cli._native_axes(fallback, "selective_default"),
                         [True, True])
        unknown = {"selected_engine": "mystery"}
        self.assertEqual(fit_cli._native_axes(unknown, "auto_default"),
                         [True, True])
        auto = {"selected_engine": "auto"}
        self.assertEqual(fit_cli._native_axes(auto, "auto_default"),
                         [False, False])
        native = {"selected_engine": "interpreter"}
        self.assertEqual(fit_cli._native_axes(native, "native_default"),
                         [True, True])

    def test_frozen_conflict_abstains_with_upstream(self):
        glyph_d, glyph_a, source_cmds, fitted_cmds, upem = self._glyphs()
        reference = fitting.build_reference(
            [{"char": "I", "source_cmds": cmds([self.anchor[0]]),
              "fitted_cmds": cmds([self.anchor[1]]), "size_px": SIZE,
              "analysis": glyph_a, "upem": upem}])
        result = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                   glyph_d, upem, reference, (True, True))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "junction-locked")

    def test_tapered_straight_applies(self):
        p0 = np.array((2.0, 0.0))
        p1 = np.array((5.0, 8.0))
        delta = p1 - p0
        tangent = delta / np.linalg.norm(delta)
        normal = np.array([-tangent[1], tangent[0]])
        spine = [p0 + (p1 - p0) * t for t in np.linspace(0, 1, 65)]
        contour = [tuple(p0 + normal * 0.60), tuple(p1 + normal * 0.72),
                   tuple(p1 - normal * 0.72), tuple(p0 - normal * 0.60)]
        src, fit, spine_a, radii_a = self.anchor
        record = analysis_record({
            "D": [(source_units(spine),
                   [r / SCALE for r in np.linspace(0.60, 0.72, 65)], None),
                  ([list(p) for p in spine_a], radii_a, None)],
            "I": [([list(p) for p in spine_a], radii_a, None)]})
        validated = fitting.validate_analysis(record)
        glyph_d = validated["glyphs"]["D"]
        upem = validated["upem"]
        source_cmds = cmds([contour, src])
        fitted_cmds = cmds([contour, fit])
        reference = fitting.build_reference(
            [{"char": "I", "source_cmds": cmds([src]),
              "fitted_cmds": cmds([fit]), "size_px": SIZE,
              "analysis": validated["glyphs"]["I"], "upem": upem}])
        result = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                   glyph_d, upem, reference, (False, False))
        self.assertTrue(result["applied"], result.get("reason"))
        for width in result["widths"]:
            self.assertLess(width["candidate"], width["ws"])

    def test_corner_flags_split_runs(self):
        spine = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [2.0, 1.0],
                          [2.0, 2.0]])
        radii = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        runs = fitting._split_runs(spine, radii, [0, 0, 1, 0, 0])
        self.assertEqual(len(runs), 2)
        self.assertFalse(any(r["curved"] for r in runs))
        bent = fitting._split_runs(spine, radii, None)
        self.assertEqual(len(bent), 1)
        self.assertTrue(bent[0]["curved"])

    def test_crossings_per_contour(self):
        bowtie = cmds([[(0.0, 0.0), (2.0, 2.0), (2.0, 0.0), (0.0, 2.0)]])
        glyph_d, _, _, _, upem = self._glyphs()
        prep = fitting._prepare(bowtie, bowtie, SIZE, glyph_d, upem)
        self.assertFalse(prep["supported"])
        self.assertEqual(prep["reason"], "crossing")
        inner = cmds([[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
                      [(1.0, 1.0), (1.0, 3.0), (3.0, 3.0), (3.0, 1.0)]])
        prep = fitting._prepare(inner, inner, SIZE, glyph_d, upem)
        self.assertTrue(prep["supported"], prep.get("reason"))

    def test_no_reference_fallback_identity(self):
        glyph_d, _, source_cmds, fitted_cmds, upem = self._glyphs()
        result = fitting.run_glyph("D", source_cmds, fitted_cmds, SIZE,
                                   glyph_d, upem,
                                   {"supported": False,
                                    "reason": "no-upright-reference"},
                                   (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "no-upright-reference")

    def test_cold_reference_builds(self):
        fixture = _load_real_fixture()
        validated = fitting.validate_analysis(fixture["analysis"])
        self.assertTrue(validated["supported"])
        entry = [e for e in fixture["captures"]["entries"]
                 if e.get("family") == "Roboto"
                 and float(e["size"]) == 16.0
                 and e["modes"]["selective_default"]["axes"].get("wght")
                 == 400][0]
        block = entry["modes"]["selective_default"]
        self.assertEqual(block["source_sha256"],
                         "d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134")
        cases = []
        for char in ("l", "I", "k"):
            record = [r for r in block["records"]
                      if chr(r["codepoint"]) == char][0]
            cases.append({"char": char,
                          "source_cmds": record["source_commands"],
                          "fitted_cmds": record["fitted_commands"],
                          "size_px": 16.0,
                          "analysis": validated["glyphs"][char],
                          "upem": validated["upem"]})
        reference = fitting.build_reference(cases)
        self.assertTrue(reference["supported"])
        self.assertEqual(set(reference["contributors"]), {"l", "I", "k"})
        self.assertAlmostEqual(reference["rel"], -0.31, places=2)

    def test_cold_stem_anchor_and_abstains(self):
        fixture = _load_real_fixture()
        validated = fitting.validate_analysis(fixture["analysis"])
        entry = [e for e in fixture["captures"]["entries"]
                 if e.get("family") == "Roboto"
                 and float(e["size"]) == 16.0
                 and e["modes"]["selective_default"]["axes"].get("wght")
                 == 400][0]
        block = entry["modes"]["selective_default"]

        def record_for(char):
            return [r for r in block["records"]
                    if chr(r["codepoint"]) == char][0]

        record = record_for("k")
        prep = fitting._prepare(record["source_commands"],
                               record["fitted_commands"], 16.0,
                               validated["glyphs"]["k"],
                               validated["upem"])
        self.assertTrue(prep["supported"])
        stem = [a for a in prep["anchors"] if a["axis"] == "x"]
        self.assertTrue(stem)
        self.assertAlmostEqual(stem[0]["ws"], 1.45, places=2)
        self.assertAlmostEqual(stem[0]["rel"], -0.31, places=2)
        reasons = [p.get("skipped") for p in prep["pairs"]
                   if "edges" not in p]
        self.assertIn("curved-spine", reasons)
        rec = record_for("A")
        prep = fitting._prepare(rec["source_commands"],
                                rec["fitted_commands"], 16.0,
                                validated["glyphs"]["A"],
                                validated["upem"])
        self.assertTrue(prep["supported"])
        reasons = [p.get("skipped") for p in prep["pairs"]
                   if "edges" not in p]
        self.assertTrue(reasons)
        self.assertTrue(all(r == "unassigned-run" for r in reasons))

    def test_cold_incoherent_stations_fail_closed(self):
        """A12 auto: contradictory station errors fail closed upstream.

        Exercises the conservative project hypothesis over Hobby (5)/(17):
        reject station disagreement larger than the existing motion budget
        normalized by source width. This is an experimental abstention bar,
        not a bound proved by Hobby or an optical acceptance rule.
        """
        fixture = _load_real_fixture()
        validated = fitting.validate_analysis(fixture["analysis"])
        entry = [e for e in fixture["captures"]["entries"]
                 if e.get("family") == "Roboto"
                 and float(e["size"]) == 12.0
                 and e["modes"]["auto_default"]["axes"].get("wght")
                 == 400][0]
        block = entry["modes"]["auto_default"]
        cases = []
        for char in ("l", "I", "k"):
            record = [r for r in block["records"]
                      if chr(r["codepoint"]) == char][0]
            cases.append({"char": char,
                          "source_cmds": record["source_commands"],
                          "fitted_cmds": record["fitted_commands"],
                          "size_px": 12.0,
                          "analysis": validated["glyphs"][char],
                          "upem": validated["upem"]})
        reference = fitting.build_reference(cases)
        self.assertTrue(reference["supported"])
        record = [r for r in block["records"]
                  if chr(r["codepoint"]) == "A"][0]
        result = fitting.run_glyph(
            "A", record["source_commands"], record["fitted_commands"],
            12.0, validated["glyphs"]["A"], validated["upem"],
            reference, (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "incoherent-stations")
        self.assertEqual(result["candidate_commands"],
                         record["fitted_commands"])
        entry = result["coherence"][0]
        self.assertGreater(entry["spread"], entry["limit"])

    def test_enabled_no_analysis_abstains(self):
        record = {"codepoint": 68, "fitted_commands": [
            {"op": "move_to", "x": 1.0, "y": 2.0},
            {"op": "line_to", "x": 3.0, "y": 4.0},
            {"op": "close"}],
            "source_commands": [
                {"op": "move_to", "x": 1.0, "y": 2.0},
                {"op": "line_to", "x": 3.0, "y": 4.0},
                {"op": "close"}],
            "advance_26_6": 512}
        captures = [{"size": 16.0, "modes": {"selective_default": {
            "source_sha256": "s", "axes": {},
            "records": [record]}}}]
        with tempfile.TemporaryDirectory() as tmp:
            caps = os.path.join(tmp, "captures.json")
            with open(caps, "w") as handle:
                json.dump(captures, handle)
            out = os.path.join(tmp, "out")
            code = fit_cli.main(["--captures", caps, "--mode",
                                 "selective_default", "--out", out,
                                 "--enable-strokestyles"])
            self.assertEqual(code, 0)
            import glob as _glob
            files = _glob.glob(os.path.join(out, "selective_default",
                                            "U+0044_*.json"))
            self.assertEqual(len(files), 1)
            with open(files[0]) as handle:
                case = json.load(handle)
            self.assertFalse(case["applied"])
            self.assertEqual(case["candidate_commands"],
                             record["fitted_commands"])


if __name__ == "__main__":
    unittest.main()
