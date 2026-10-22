"""Focused tests for the three-arm border-interval coverage review.

Covers the three-arm compositor (shared union frames), the
frozen-vs-candidate coverage delta (per-pair intervention and rejection
data, not whole-glyph means), saved-cell provenance and the frozen
baseline identities the run asserts. Expected canvases are hand-computed
for tiny fixtures. Corpus checks skip cleanly when the ignored
diagnostics are absent. These prove plumbing integrity, not optical
quality.
"""

import json
import os
import unittest

from experiments.hobby_fitting import coverage_review as coverage
from experiments.hobby_fitting import text_review as review

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DIAG = os.path.join(REPO, "out", "diagnostics", "direct-diagonal")
BASELINE = os.path.join(DIAG, "text-review")
BASELINE_SUMMARY = os.path.join(BASELINE, "summary.json")
CAPTURES = os.path.join(DIAG, "captures.json")
JOINS_SUMMARY = os.path.join(DIAG, "joins-evaluation", "summary.json")
JOINS_DIR = os.path.join(DIAG, "joins-evaluation")


def tile(pixels, width, height, left=0, top=0):
    return {"pixels": list(pixels), "width": width, "height": height,
            "left": left, "top": top}


def line(text, placements, baseline=10):
    return {"text": text, "baseline": baseline, "placements": placements}


def art(pixels, left=0, top=0, width=None, height=1):
    pixels = list(pixels)
    return {"pixels": pixels, "left": left, "top": top,
            "width": len(pixels) if width is None else width,
            "height": height}


def fit_result(applied, pairs=(), skipped=(), pixels=(1,), reason="applied",
               left=0, top=0, width=None):
    return {"applied": applied, "reason": reason,
            "pairs": [{"id": pid} for pid in pairs],
            "skipped": [{"reason": entry} for entry in skipped],
            "widths": None,
            **art(pixels, left, top, width)}


def nested(pixels, left=0, top=0):
    return {"pixels": list(pixels),
            "frame": {"left": left, "top": top, "width": len(pixels),
                      "height": 1}}


class ThreeArmFrameTest(unittest.TestCase):
    def test_union_covers_all_three_boxes(self):
        # Candidate shrinks one tile and widens another; the shared frame
        # must cover the widest arm of each with one origin.
        placements = [{"codepoint": 65, "x": 4}]
        up = {65: tile([1, 1, 1, 1], 2, 2, left=-1, top=-2)}
        frozen = {65: tile([1], 1, 1, left=0, top=-1)}
        cand = {65: tile([1, 1, 1], 3, 1, left=-2, top=-1)}
        composed = coverage.compose_line_three(
            line("A", placements), up, frozen, cand)
        for arm in ("upstream", "frozen", "candidate"):
            for key in composed["frame"]:
                self.assertEqual(composed[arm][key], composed["frame"][key])
        self.assertEqual((composed["frame"]["width"],
                          composed["frame"]["height"]), (5, 2))
        self.assertEqual(composed["frame"]["origin_x"], 0)
        self.assertEqual(composed["upstream"]["pixels"],
                         [0, 0, 0, 1, 1, 0, 0, 0, 1, 1])
        self.assertEqual(composed["candidate"]["pixels"],
                         [0, 0, 0, 0, 0, 0, 0, 1, 1, 1])

    def test_empty_line_is_degenerate(self):
        composed = coverage.compose_line_three(line("", [], 0), {}, {}, {})
        self.assertEqual((composed["frame"]["width"],
                          composed["frame"]["height"]), (0, 0))
        self.assertEqual(composed["candidate"]["pixels"], [])

    def test_missing_tile_fails_closed(self):
        with self.assertRaises(SystemExit):
            coverage.compose_line_three(
                line("A", [{"codepoint": 65, "x": 0}], 0), {}, {}, {})

    def test_paragraph_retains_native_baselines(self):
        tiles = {65: tile([1], 1, 1)}
        lines = [line("A", [{"codepoint": 65, "x": 0}], 12),
                 line("", [], 32)]
        paragraph = coverage.compose_paragraph_three(
            lines, tiles, tiles, tiles)
        self.assertEqual(paragraph["line_baselines"], [0, 20])
        self.assertEqual(sum(paragraph["candidate"]["pixels"]), 1)
        self.assertEqual(paragraph["upstream"]["pixels"],
                         paragraph["frozen"]["pixels"])
        self.assertEqual(paragraph["frozen"]["pixels"],
                         paragraph["candidate"]["pixels"])


class CoverageDeltaTest(unittest.TestCase):
    def test_newly_covered_names_added_pairs(self):
        frozen = fit_result(False, pairs=(), skipped=("no-dominance-ok",),
                            pixels=(0, 0), reason="all-abstained")
        cand = fit_result(True, pairs=("p1", "p2"), pixels=(0, 1))
        delta = coverage.coverage_delta(frozen, cand, art((0, 0)))
        self.assertEqual(delta["coverage_change"], "newly-covered")
        self.assertEqual(delta["pairs_added"], ["p1", "p2"])
        self.assertEqual(delta["pairs_removed"], [])
        self.assertEqual(delta["pixels_up_frozen"], 0)
        self.assertEqual(delta["pixels_frozen_candidate"], 1)
        self.assertEqual(delta["candidate_rejected"], {})

    def test_lost_names_removed_pairs(self):
        frozen = fit_result(True, pairs=("p1",), pixels=(1, 1))
        cand = fit_result(False, skipped=("movement-budget-empty",) * 2,
                          pixels=(0, 0), reason="all-abstained")
        delta = coverage.coverage_delta(frozen, cand, art((0, 0)))
        self.assertEqual(delta["coverage_change"], "lost")
        self.assertEqual(delta["pairs_removed"], ["p1"])
        self.assertEqual(delta["candidate_rejected"],
                         {"movement-budget-empty": 2})

    def test_same_decision_keeps_rejection_reasons(self):
        frozen = fit_result(False, skipped=("opposition-pruned",),
                            pixels=(0,), reason="all-abstained")
        cand = fit_result(False, skipped=("no-dominance-ok",),
                          pixels=(0,), reason="all-abstained")
        delta = coverage.coverage_delta(frozen, cand, art((0,)))
        self.assertEqual(delta["coverage_change"], "same-decision")
        self.assertEqual(delta["frozen_rejected"], {"opposition-pruned": 1})
        self.assertEqual(delta["candidate_rejected"],
                         {"no-dominance-ok": 1})
        self.assertEqual(delta["pixels_frozen_candidate"], 0)

    def test_candidate_difference_is_data_not_failure(self):
        # Baseline checks validate the frozen arm against joins; the
        # candidate may differ intentionally, recorded here not rejected.
        frozen = fit_result(True, pairs=("p1",), pixels=(1,))
        cand = fit_result(True, pairs=("p2",), pixels=(0,))
        delta = coverage.coverage_delta(frozen, cand, art((0,)))
        self.assertEqual(delta["pairs_added"], ["p2"])
        self.assertEqual(delta["pairs_removed"], ["p1"])
        self.assertEqual(delta["pixels_frozen_candidate"], 1)

    def test_pixel_length_mismatch_fails_closed(self):
        with self.assertRaises(SystemExit):
            coverage.pixel_diff((0, 1), (0,))

    def test_framed_diff_compares_shifted_boxes(self):
        # Tiles with different boxes compare over their union; off-tile
        # counts as empty rather than failing.
        frozen = nested((1,), left=0)
        cand = nested((1, 1), left=1)
        self.assertEqual(coverage.framed_diff(frozen, cand), 3)
        self.assertEqual(coverage.framed_diff(frozen, dict(frozen)), 0)
        with self.assertRaises(SystemExit):
            coverage.framed_diff({"pixels": [1]}, {"pixels": [1]})

    def test_pair_ids_skip_unidentified(self):
        result = {"pairs": [{"id": "p1"}, {}], "skipped": []}
        self.assertEqual(coverage.pair_ids(result), ["p1"])


class ModelProvenanceTest(unittest.TestCase):
    def test_provenance_covers_every_model_dependency(self):
        prov = coverage.model_provenance()
        self.assertEqual(sorted(prov), sorted(coverage.MODEL_DEPS))
        for rel, digest in prov.items():
            with open(os.path.join(REPO, rel), "rb") as handle:
                import hashlib
                self.assertEqual(digest,
                                 hashlib.sha256(handle.read()).hexdigest())

    def test_any_dependency_change_invalidates_saved_cell(self):
        cell = SavedCellTest.valid_cell(self)
        deps = dict(coverage.model_provenance())
        cell = dict(cell, model_dependencies=dict(deps))
        self.assertEqual(coverage.saved_coverage_problems(
            cell, "Roboto", 16.0, 400.0, {"wdth": 100.0, "wght": 400.0},
            "selective_default", "c" * 64, deps), [])
        stale = dict(deps, **{coverage.MODEL_DEPS[1]: "0" * 64})
        self.assertIn("model-dependencies",
                      coverage.saved_coverage_problems(
                          cell, "Roboto", 16.0, 400.0,
                          {"wdth": 100.0, "wght": 400.0},
                          "selective_default", "c" * 64, stale))
        missing = dict(cell)
        del missing["model_dependencies"]
        self.assertIn("model-dependencies",
                      coverage.saved_coverage_problems(
                          missing, "Roboto", 16.0, 400.0,
                          {"wdth": 100.0, "wght": 400.0},
                          "selective_default", "c" * 64, deps))


class DeliveredVersusRejectedTest(unittest.TestCase):
    def test_per_pair_detail_names_delivered_not_attempt(self):
        delivered = {"id": "p1", "interval": [0.1, 0.4],
                     "source_width": 1.2, "upstream_width": 1.3,
                     "candidate_width": 0.9, "bound": 0.5, "peak": 0.2,
                     "prefix": 1.0, "phase_applied": False}
        frozen = fit_result(True, pairs=("p1",), pixels=(1, 1))
        cand = dict(fit_result(True, pairs=("p1",), pixels=(0, 1)),
                    pairs=[delivered],
                    attempt={"pairs": [delivered]})
        delta = coverage.coverage_delta(frozen, cand, art((0, 0)))
        self.assertEqual(delta["pairs_candidate"][0]["interval"], [0.1, 0.4])
        self.assertEqual(delta["pairs_candidate"][0]["candidate_width"], 0.9)
        self.assertTrue(delta["candidate_rejected_attempt"])
        self.assertFalse(coverage.coverage_delta(
            frozen, fit_result(True, pairs=("p1",), pixels=(0, 1)),
            art((0, 0)))["candidate_rejected_attempt"])

    def test_pair_detail_tolerates_id_only_fixtures(self):
        self.assertEqual(coverage.pair_detail({"id": "p1"})["peak"], None)
        self.assertEqual(coverage.pair_detail("p1"), {"id": None})

    def test_delta_accepts_flat_upstream_and_nested_candidate(self):
        # Real call shape: flat upstream art against nested width-only
        # frames; the shared-frame diff must not fail on the list.
        upstream = art((0, 1), left=0, top=0)
        frozen = dict(nested((0, 1), left=0, top=0), applied=False,
                      reason="all-abstained", pairs=[], skipped=[],
                      widths=None)
        cand = dict(nested((1, 1), left=0, top=0), applied=True,
                    pairs=[{"id": "p1"}], skipped=[], widths=None)
        delta = coverage.coverage_delta(frozen, cand, upstream)
        self.assertEqual(delta["pixels_up_frozen"], 0)
        self.assertEqual(delta["pixels_frozen_candidate"], 1)
        self.assertEqual(delta["coverage_change"], "newly-covered")


class SavedCellTest(unittest.TestCase):
    def valid_cell(self):
        reference = {"anchors": [], "size_px": 16.0}
        glyphs = []
        for code in range(0x20, 0x7F):
            art = {"pixels": [1], "coverage": [255], "left": 0, "top": 0,
                   "width": 1, "height": 1}
            frame = {"frame": dict(art), "pixels": [1]}
            glyphs.append({
                "char": chr(code), "codepoint": code,
                "applied_frozen": False, "reason_frozen": "all-abstained",
                "applied": False, "reason": "all-abstained",
                "native_axes": [False, False], "ownership": "selected-engine",
                "upstream_commands": [], "upstream": dict(art),
                "frozen": dict(frame), "candidate": dict(frame),
                "delta": coverage.coverage_delta(
                    dict(frame), dict(frame), dict(art))})
        return {"family": "Roboto", "size": 16.0, "weight": 400.0,
                "axes": {"wdth": 100.0, "wght": 400.0},
                "hint_mode": "selective_default",
                "layout_status": {"status": "ready"},
                "layout": {"lines": [{"text": t}
                                     for t in review.TEXT_LINES]},
                "reference": reference,
                "reference_sha256": review.reference_sha256(reference),
                "baseline": {"model_source_sha256":
                             coverage.FROZEN_MODEL_SHA256},
                "candidate_core_sha256": "c" * 64,
                "counts": {"applied": 0, "abstained": 95, "reasons": {}},
                "glyphs": glyphs, "donor_glyphs": [],
                "capture_policy": {}, "capture": "x"}

    def test_accepts_valid_rejects_stale(self):
        cell = self.valid_cell()
        self.assertEqual(coverage.saved_coverage_problems(
            cell, "Roboto", 16.0, 400.0, {"wdth": 100.0, "wght": 400.0},
            "selective_default", "c" * 64), [])
        self.assertIn("candidate-core", coverage.saved_coverage_problems(
            cell, "Roboto", 16.0, 400.0, {"wdth": 100.0, "wght": 400.0},
            "selective_default", "d" * 64))
        stale = dict(cell, axes={"wght": 400.0})
        self.assertIn("axes", coverage.saved_coverage_problems(
            stale, "Roboto", 16.0, 400.0, {"wdth": 100.0, "wght": 400.0},
            "selective_default", "c" * 64))
        short = dict(cell, glyphs=cell["glyphs"][:90])
        self.assertIn("repertoire", coverage.saved_coverage_problems(
            short, "Roboto", 16.0, 400.0, {"wdth": 100.0, "wght": 400.0},
            "selective_default", "c" * 64))
        wrong = dict(cell, reference_sha256="0" * 64)
        self.assertIn("reference-hash", coverage.saved_coverage_problems(
            wrong, "Roboto", 16.0, 400.0, {"wdth": 100.0, "wght": 400.0},
            "selective_default", "c" * 64))
        old = dict(cell, baseline={"model_source_sha256": "0" * 64})
        self.assertIn("baseline-model", coverage.saved_coverage_problems(
            old, "Roboto", 16.0, 400.0, {"wdth": 100.0, "wght": 400.0},
            "selective_default", "c" * 64))

    def test_baseline_provenance_pins_frozen_packet(self):
        summary = {"tool": "text-review-v1",
                   "capture_sha256": coverage.FROZEN_CAPTURE_SHA256,
                   "topology_binary_sha256":
                       coverage.FROZEN_TOPOLOGY_SHA256,
                   "model_source_sha256": coverage.FROZEN_MODEL_SHA256}
        coverage.assert_baseline_provenance(summary)
        with self.assertRaises(SystemExit):
            coverage.assert_baseline_provenance(
                dict(summary, tool="other-tool"))
        with self.assertRaises(SystemExit):
            coverage.assert_baseline_provenance(
                dict(summary, capture_sha256="0" * 64))

    def test_donor_codes_match_donors(self):
        self.assertEqual(sorted(coverage.DONOR_CODES),
                         sorted(ord(c) for c in "itflInhkyxzvAVW"))

    def test_ascii_repertoire_is_printable_95(self):
        self.assertEqual(len(coverage.ASCII_95), 95)
        self.assertEqual([ord(c) for c in coverage.ASCII_95],
                         list(range(0x20, 0x7F)))

    @unittest.skipUnless(os.path.isfile(BASELINE_SUMMARY),
                         "baseline packet absent")
    def test_baseline_summary_matches_frozen_pins(self):
        with open(BASELINE_SUMMARY) as handle:
            summary = json.load(handle)
        coverage.assert_baseline_provenance(summary)
        self.assertEqual(len(summary["cells"]), 36)

    @unittest.skipUnless(os.path.isfile(CAPTURES), "frozen captures absent")
    def test_captures_sha_matches_frozen_donors(self):
        with open(CAPTURES, "rb") as handle:
            import hashlib
            digest = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(digest, coverage.FROZEN_CAPTURE_SHA256)

    @unittest.skipUnless(os.path.isfile(JOINS_SUMMARY), "joins absent")
    def test_frozen_donor_delivery_compares_width_only_arm(self):
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


if __name__ == "__main__":
    unittest.main()
