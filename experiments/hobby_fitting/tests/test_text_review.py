"""Focused tests for the text-level width-only review plumbing.

Covers the compositor (shared union frames, overhang, spaces, explicit
line breaks, paragraph baselines), the native-layout contract (spacing
tables, no trailing break) and the frozen donor identities the run
asserts (full-key joins lookup, per-family axes, width-only arm shape).
Expected canvases are hand-computed for tiny fixtures. Corpus checks
skip cleanly when the ignored diagnostics are absent. These prove
plumbing integrity, not optical quality.
"""

import json
import os
import unittest

from experiments.hobby_fitting import text_review as review
from experiments.hobby_fitting import direct_diagonal_run as run

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DIAG = os.path.join(REPO, "out", "diagnostics", "direct-diagonal")
CAPTURES = os.path.join(DIAG, "captures.json")
JOINS_SUMMARY = os.path.join(DIAG, "joins-evaluation", "summary.json")
JOINS_DIR = os.path.join(DIAG, "joins-evaluation")


def tile(pixels, width, height, left=0, top=0):
    return {"pixels": list(pixels), "width": width, "height": height,
            "left": left, "top": top}


def line(text, placements, baseline=10):
    return {"text": text, "baseline": baseline, "placements": placements}


class SharedFrameTest(unittest.TestCase):
    def test_common_union_covers_changed_candidate_box(self):
        # The width-only arm may shrink a tile; the shared frame must
        # still cover the wider upstream box with one origin.
        placements = [{"codepoint": 65, "x": 4}]
        up = {65: tile([1, 1, 1, 1], 2, 2, left=-1, top=-2)}
        wo = {65: tile([1], 1, 1, left=0, top=-1)}
        composed = review.compose_line_common(line("A", placements), up, wo)
        for arm in ("upstream", "width_only"):
            for key in composed["frame"]:
                self.assertEqual(composed[arm][key], composed["frame"][key])
            self.assertEqual(composed[arm]["baseline_y"], 2)
        # Pen origin x=0 anchors the frame, so the negative overhang
        # survives inside a wider shared frame.
        self.assertEqual((composed["frame"]["width"],
                          composed["frame"]["height"]), (5, 2))
        self.assertEqual(composed["frame"]["origin_x"], 0)
        self.assertEqual(composed["upstream"]["pixels"],
                         [0, 0, 0, 1, 1, 0, 0, 0, 1, 1])
        self.assertEqual(composed["width_only"]["pixels"],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, 1])

    def test_overhang_and_trailing_space_share_origin(self):
        placements = [{"codepoint": 65, "x": 4},
                      {"codepoint": 32, "x": 6, "advance": 3}]
        tiles = {65: tile([1], 1, 1), 32: tile([], 0, 0)}
        composed = review.compose_line_common(line("A ", placements, 0),
                                              tiles, tiles)
        self.assertEqual(composed["frame"]["width"], 9)
        self.assertEqual(composed["upstream"]["pixels"],
                         [0, 0, 0, 0, 1, 0, 0, 0, 0])
        self.assertEqual(composed["upstream"]["pixels"],
                         composed["width_only"]["pixels"])

    def test_leading_whitespace_survives_pen_origin(self):
        # " A" puts ink at x=3; without the x=0 anchor the frame
        # would start at the ink and crop the leading space.
        placements = [{"codepoint": 32, "x": 0, "advance": 3},
                      {"codepoint": 65, "x": 3}]
        tiles = {32: tile([], 0, 0), 65: tile([1], 1, 1)}
        composed = review.compose_line_common(line(" A", placements, 0),
                                              tiles, tiles)
        self.assertEqual(composed["frame"]["origin_x"], 0)
        self.assertEqual(composed["frame"]["width"], 4)
        self.assertEqual(composed["upstream"]["pixels"], [0, 0, 0, 1])

    def test_space_only_line_keeps_origin_and_edge(self):
        placements = [{"codepoint": 32, "x": 0, "advance": 3}]
        tiles = {32: tile([], 0, 0)}
        composed = review.compose_line_common(line(" ", placements, 7),
                                              tiles, tiles)
        self.assertEqual((composed["frame"]["width"],
                          composed["frame"]["height"]), (3, 0))
        self.assertEqual(composed["upstream"]["pixels"], [])
        self.assertEqual(composed["frame"]["origin_y"], -7)

    def test_empty_line_holds_pitch_in_paragraph(self):
        tiles = {65: tile([1], 1, 1)}
        lines = [line("A", [{"codepoint": 65, "x": 0}], 12),
                 line("", [], 32),
                 line("A", [{"codepoint": 65, "x": 0}], 52)]
        paragraph = review.compose_paragraph(lines, tiles, tiles)
        self.assertEqual(paragraph["line_baselines"], [0, 20, 40])
        self.assertEqual(paragraph["frame"]["height"], 41)
        self.assertEqual(sum(paragraph["upstream"]["pixels"]), 2)

    def test_explicit_breaks_never_wrap(self):
        tiles = {65: tile([1], 1, 1)}
        placements = [{"codepoint": 65, "x": 3 * i} for i in range(200)]
        composed = review.compose_line_common(line("A" * 200, placements, 0),
                                              tiles, tiles)
        self.assertEqual(composed["frame"]["width"], 200 * 3 - 2)
        self.assertEqual(sum(composed["upstream"]["pixels"]), 200)

    def test_empty_line_is_degenerate(self):
        composed = review.compose_line_common(line("", [], 0), {}, {})
        self.assertEqual((composed["frame"]["width"],
                          composed["frame"]["height"]), (0, 0))
        self.assertEqual(composed["upstream"]["pixels"], [])

    def test_missing_tile_fails_closed(self):
        with self.assertRaises(SystemExit):
            review.compose_line_common(
                line("A", [{"codepoint": 65, "x": 0}], 0), {}, {})

    def test_paragraph_retains_native_baselines(self):
        tiles = {65: tile([1], 1, 1), 66: tile([1], 1, 1)}
        lines = [line("A", [{"codepoint": 65, "x": 0}], 12),
                 line("B", [{"codepoint": 66, "x": 0}], 32)]
        paragraph = review.compose_paragraph(lines, tiles, tiles)
        self.assertEqual(paragraph["line_baselines"], [0, 20])
        self.assertEqual(paragraph["line_baselines"][1]
                         - paragraph["line_baselines"][0], 20)
        self.assertEqual(sum(paragraph["upstream"]["pixels"]), 2)
        self.assertEqual(paragraph["upstream"]["pixels"],
                         paragraph["width_only"]["pixels"])


class NativeLayoutTest(unittest.TestCase):
    def test_layout_text_has_no_trailing_break(self):
        # A trailing newline would hand the worker an eighth empty line.
        payload = review.layout_text()
        self.assertEqual(payload, "\n".join(review.TEXT_LINES))
        self.assertFalse(payload.endswith("\n"))
        self.assertEqual(len(payload.split("\n")), len(review.TEXT_LINES))

    def test_ascii_repertoire_is_printable_95(self):
        self.assertEqual(len(review.ASCII_95), 95)
        self.assertEqual([ord(c) for c in review.ASCII_95],
                         list(range(0x20, 0x7F)))

    def test_rejects_pen_diverging_from_tables(self):
        mode = {"metrics": {"ascent_px": 10, "line_height_px": 12},
                "advances": [{"codepoint": 65, "advance": 5},
                             {"codepoint": 66, "advance": 6}],
                "pair_adjustments": [{"left": 65, "right": 66,
                                      "adjustment": -1}],
                "glyphs": [{"codepoint": 65, "glyph_id": 1, "advance": 5,
                            "left": 0, "top": 0, "width": 1, "height": 1},
                           {"codepoint": 66, "glyph_id": 2, "advance": 6,
                            "left": 0, "top": 0, "width": 1, "height": 1}],
                "lines": [{"text": "AB", "baseline": 10, "placements": [
                    {"codepoint": 65, "x": 0, "x_26_6": 0,
                     "advance": 5, "pair": 0},
                    {"codepoint": 66, "x": 99, "x_26_6": 99 * 64,
                     "advance": 6, "pair": -1}]}],
                "strategy": "s", "extensions": "e"}
        records = {65: {"glyph_id": 1, "left": 0, "top": 0,
                        "width": 1, "height": 1},
                   66: {"glyph_id": 2, "left": 0, "top": 0,
                        "width": 1, "height": 1}}
        with self.assertRaises(SystemExit):
            review.check_layout_mode(mode, "auto_default", records, "e")

    def test_rejects_layout_box_diverging_from_capture(self):
        mode = {"metrics": {"ascent_px": 10, "line_height_px": 12},
                "advances": [{"codepoint": 65, "advance": 5}],
                "pair_adjustments": [],
                "glyphs": [{"codepoint": 65, "glyph_id": 1, "advance": 5,
                            "left": 9, "top": 0, "width": 1, "height": 1}],
                "lines": [{"text": "A", "baseline": 10, "placements": [
                    {"codepoint": 65, "x": 0, "x_26_6": 0,
                     "advance": 5, "pair": 0}]}],
                "strategy": "s", "extensions": "e"}
        records = {65: {"glyph_id": 1, "left": 0, "top": 0,
                        "width": 1, "height": 1}}
        with self.assertRaises(SystemExit):
            review.check_layout_mode(mode, "auto_default", records, "e")

    def test_tiles_for_reads_nested_width_only_frame(self):
        # Upstream art carries its box flat; width-only nests it under
        # `frame`. Mixing them up drops every width-only tile.
        results = {65: {"upstream": dict(tile([1, 1], 2, 1),
                                          pixels=[1, 1]),
                        "width_only": {"pixels": [1, 0],
                                       "frame": {"left": 0, "top": 0,
                                                 "width": 2, "height": 1}}}}
        up = review.tiles_for(results, "upstream")
        wo = review.tiles_for(results, "width_only")
        self.assertEqual((up[65]["width"], up[65]["height"]), (2, 1))
        self.assertEqual((wo[65]["width"], wo[65]["height"]), (2, 1))
        self.assertEqual(wo[65]["pixels"], [1, 0])


class FrozenIdentityTest(unittest.TestCase):
    def test_donor_codes_match_donor_chars(self):
        self.assertEqual(sorted(review.DONOR_CODES),
                         sorted(ord(c) for c in "itflInhkyxzvAVW"))

    def test_ownership_axes_from_record(self):
        record = {"selected_engine": "auto",
                  "selective_fitting": {"native_axes": [True, False]}}
        axes, owner = run.ownership(record)
        self.assertEqual(list(axes), [True, False])
        record = {"selected_engine": "auto"}
        axes, _ = run.ownership(record)
        self.assertEqual(list(axes), [False, False])

    def test_joins_lookup_keys_full_identity(self):
        # Weight-specific files carry dedup suffixes; the summary keys
        # keep weights apart where basenames collide.
        summary = {"cases": [
            {"family": "Roboto", "size": 16.0,
             "axes": {"wdth": 100.0, "wght": 400.0},
             "hint_mode": "selective_default", "codepoint": 65,
             "file": "cases/Roboto_16.0_selective_default_U+0041.json"},
            {"family": "Roboto", "size": 16.0,
             "axes": {"wdth": 100.0, "wght": 700.0},
             "hint_mode": "selective_default", "codepoint": 65,
             "file": "cases/Roboto_16.0_selective_default_U+0041-3.json"},
        ]}
        table = review.joins_lookup(summary)
        self.assertEqual(len(table), 2)
        self.assertEqual(
            table[("Roboto", 16.0,
                   json.dumps({"wdth": 100.0, "wght": 700.0},
                              sort_keys=True),
                   "selective_default", 65)],
            "cases/Roboto_16.0_selective_default_U+0041-3.json")

    def test_frozen_axes_keep_family_shape(self):
        cases = [{"family": "Roboto", "size": 12.0,
                  "axes": {"wdth": 100.0, "wght": 300.0}},
                 {"family": "Roboto", "size": 24.0,
                  "axes": {"wdth": 100.0, "wght": 300.0}},
                 {"family": "SourceSans3", "size": 12.0,
                  "axes": {"wght": 300.0}}]
        self.assertEqual(review.frozen_axes_for(cases, "Roboto", 300),
                         {"wdth": 100.0, "wght": 300.0})
        self.assertEqual(review.frozen_axes_for(cases, "SourceSans3", 300),
                         {"wght": 300.0})

    @unittest.skipUnless(os.path.isfile(CAPTURES), "frozen captures absent")
    def test_captures_sha_matches_frozen_donor(self):
        with open(CAPTURES, "rb") as handle:
            import hashlib
            digest = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(digest, review.FROZEN_CAPTURE_SHA256)

    @unittest.skipUnless(os.path.isfile(CAPTURES), "frozen captures absent")
    def test_donor_group_matches_provenance(self):
        with open(CAPTURES) as handle:
            cases = json.load(handle)
        self.assertEqual(len(cases), 36)
        for case in cases:
            for mode in ("auto_default", "selective_default"):
                codes = sorted(r["codepoint"]
                               for r in case["modes"][mode]["records"])
                self.assertEqual(codes, sorted(review.DONOR_CODES))

    @unittest.skipUnless(os.path.isfile(JOINS_SUMMARY), "joins absent")
    def test_joins_evaluation_matches_frozen_inputs(self):
        with open(JOINS_SUMMARY) as handle:
            summary = json.load(handle)
        self.assertEqual(summary["capture_sha256"],
                         review.FROZEN_CAPTURE_SHA256)
        self.assertEqual(summary["topology_binary_sha256"],
                         review.FROZEN_TOPOLOGY_SHA256)
        self.assertEqual(summary["counts"]["width_only"]["applied"], 255)
        self.assertEqual(summary["counts"]["width_only"]["abstained"], 825)
        self.assertEqual(summary["topology_mode"], "exact_arrangement")

    @unittest.skipUnless(os.path.isfile(JOINS_SUMMARY), "joins absent")
    def test_donor_delivery_compares_width_only_arm(self):
        with open(JOINS_SUMMARY) as handle:
            summary = json.load(handle)
        lookup = review.joins_lookup(summary)
        key = ("Roboto", 16.0,
               json.dumps({"wdth": 100.0, "wght": 400.0}, sort_keys=True),
               "selective_default", 0x78)
        path = os.path.join(JOINS_DIR, lookup[key])
        with open(path) as handle:
            frozen = json.load(handle)["arms"]["width_only"]
        cell = {"family": "Roboto", "size": 16.0,
                "axes": {"wdth": 100.0, "wght": 400.0},
                "hint_mode": "selective_default"}
        review.check_donor_delivery(lookup, JOINS_DIR, cell,
                                    {0x78: dict(frozen)})
        with self.assertRaises(SystemExit):
            review.check_donor_delivery(
                lookup, JOINS_DIR, cell,
                {0x78: dict(frozen, applied=not frozen["applied"])})

    def test_saved_cell_problems_accepts_valid_rejects_stale(self):
        reference = {"anchors": [], "size_px": 16.0}
        cell = {"family": "Roboto", "size": 16.0, "weight": 400.0,
                "axes": {"wdth": 100.0, "wght": 400.0},
                "hint_mode": "selective_default",
                "glyphs": [{"codepoint": c} for c in range(0x20, 0x7F)],
                "layout": {"lines": [{"text": t} for t in review.TEXT_LINES]},
                "layout_status": {"status": "ready"},
                "reference": reference,
                "reference_sha256": review.reference_sha256(reference),
                "counts": {"applied": 1, "abstained": 2, "reasons": {}}}
        self.assertEqual(
            review.saved_cell_problems(
                cell, "Roboto", 16.0, 400.0,
                {"wdth": 100.0, "wght": 400.0}, "selective_default"), [])
        stale = dict(cell, axes={"wght": 400.0})
        self.assertIn(
            "axes", review.saved_cell_problems(
                stale, "Roboto", 16.0, 400.0,
                {"wdth": 100.0, "wght": 400.0}, "selective_default"))
        short = dict(cell, glyphs=cell["glyphs"][:90])
        self.assertIn(
            "repertoire", review.saved_cell_problems(
                short, "Roboto", 16.0, 400.0,
                {"wdth": 100.0, "wght": 400.0}, "selective_default"))
        wrong = dict(cell, reference_sha256="0" * 64)
        self.assertIn(
            "reference-hash", review.saved_cell_problems(
                wrong, "Roboto", 16.0, 400.0,
                {"wdth": 100.0, "wght": 400.0}, "selective_default"))
        pending = dict(cell, layout_status={"status": "pending"})
        self.assertIn(
            "layout-status", review.saved_cell_problems(
                pending, "Roboto", 16.0, 400.0,
                {"wdth": 100.0, "wght": 400.0}, "selective_default"))

    def test_recompose_reads_nested_width_only_frame(self):
        import tempfile
        reference = {"anchors": [], "size_px": 16.0}
        glyphs = []
        for code in range(0x20, 0x7F):
            glyphs.append({
                "char": chr(code), "codepoint": code, "applied": False,
                "reason": "all-abstained", "native_axes": [False, False],
                "ownership": "selected-engine",
                "upstream_commands": [],
                "upstream": {"pixels": [1], "coverage": [255],
                             "left": 0, "top": 0, "width": 1, "height": 1},
                "width_only": {"applied": False, "reason": "all-abstained",
                               "pixels": [1], "coverage": [255],
                               "frame": {"left": 0, "top": 0,
                                         "width": 1, "height": 1}},
                "widths": None})
        lines = [{"text": t, "baseline": 10 * (j + 1), "placements": [
            {"codepoint": ord(c), "x": i, "x_26_6": 64 * i,
             "advance": 1, "pair": 0}
            for i, c in enumerate(t)]} for j, t in enumerate(review.TEXT_LINES)]
        cell = {"family": "Roboto", "size": 16.0, "weight": 400.0,
                "axes": {"wdth": 100.0, "wght": 400.0},
                "hint_mode": "selective_default",
                "layout_status": {"status": "ready"},
                "layout": {"lines": lines},
                "reference": reference,
                "reference_sha256": review.reference_sha256(reference),
                "lines": [], "paragraph": {},
                "counts": {"applied": 0, "abstained": 95, "reasons": {}},
                "glyphs": glyphs, "donor_glyphs": [],
                "capture_policy": {}, "capture": "x"}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cell.json")
            with open(path, "w") as handle:
                json.dump(cell, handle)
            # Fake frozen joins for the donor codes: the delivery check
            # must pass on identical decisions while the nested frame
            # read is exercised for all 95 glyphs.
            lookup = {}
            axes_json = json.dumps({"wdth": 100.0, "wght": 400.0},
                                   sort_keys=True)
            for code in review.DONOR_CODES:
                name = "frozen_U+%04X.json" % code
                with open(os.path.join(tmp, name), "w") as handle:
                    json.dump({"arms": {"width_only": {
                        "applied": False, "reason": "all-abstained",
                        "candidate_commands": None, "pixels": [1]}}},
                        handle)
                lookup[("Roboto", 16.0, axes_json,
                        "selective_default", code)] = name
            entry = review.recompose_saved_cell(
                path, lookup, tmp, {"tool": review.TOOL_VERSION})
            with open(path) as handle:
                redone = json.load(handle)
        self.assertEqual(len(redone["lines"]), len(review.TEXT_LINES))
        self.assertEqual(redone["paragraph"]["texts"], review.TEXT_LINES)
        self.assertEqual(len(redone["donor_glyphs"]), 15)
        self.assertTrue(entry["file"].endswith("cell.json"))

    @unittest.skipUnless(os.path.isfile(JOINS_SUMMARY), "joins absent")
    def test_weight_700_resolves_through_full_key(self):
        # Basename-only matching confuses weight 400 and 700 donors;
        # the full key must select the suffixed weight-700 file.
        with open(JOINS_SUMMARY) as handle:
            summary = json.load(handle)
        lookup = review.joins_lookup(summary)
        key = ("Roboto", 16.0,
               json.dumps({"wdth": 100.0, "wght": 700.0}, sort_keys=True),
               "selective_default", 0x41)
        self.assertTrue(lookup[key].endswith("-3.json"))
        cell = {"family": "Roboto", "size": 16.0,
                "axes": {"wdth": 100.0, "wght": 700.0},
                "hint_mode": "selective_default"}
        path = os.path.join(JOINS_DIR, lookup[key])
        with open(path) as handle:
            frozen = json.load(handle)["arms"]["width_only"]
        review.check_donor_delivery(lookup, JOINS_DIR, cell,
                                    {0x41: dict(frozen)})


if __name__ == "__main__":
    unittest.main()
