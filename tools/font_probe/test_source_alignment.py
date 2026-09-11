"""Focused tests for the source-alignment working path."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audit_source_alignment as asa


def _record():
    return {
        "reduced_graph": {"constraints": [], "order": [], "scalar_order": [], "rejected": []},
        "graph": {"constraints": [], "order": [], "scalar_order": [], "rejected": []},
        "representative_points": [],
        "reduced_selected_relation_count": 0,
        "segment_dominance": {"rejected": []},
    }


def _fake_pipeline_cls(tmp):
    tmp = Path(tmp)

    class FakePipeline:
        def __init__(self, output):
            self.output = Path(output)
            self.inputs = {"tools/font_probe/x.py": "abc"}
            self.provenance = {"instantiation": {}}
            self.work = tmp / "work"

        def note_sources(self):
            pass

        def instantiate(self, key, name, size):
            return tmp / "static.ttf"

        def verify_inputs_unchanged(self):
            pass

        def verify_sources(self):
            pass

        def close(self):
            pass

        def use_input(self, path):
            return path

    return FakePipeline


class SourceAlignmentTest(unittest.TestCase):
    def test_direct_build_font_kwargs_no_override(self):
        from compare_shamir_pipeline import CHARS
        build = {"records": {c: _record() for c in CHARS},
                 "baseline_decisions": {"policy": "x"}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fresh"
            out.mkdir()
            with mock.patch.object(asa, "Pipeline", _fake_pipeline_cls(tmp)), \
                mock.patch.object(asa, "build_font", return_value=build) as bf, \
                mock.patch.object(asa, "digest", return_value="deadbeef"), \
                mock.patch.object(asa.ft, "Face", return_value=mock.Mock()), \
                mock.patch.object(asa, "graph_issues", return_value=[]), \
                mock.patch.object(asa, "construction_issues", return_value=[]), \
                mock.patch.object(
                    asa, "coordinate_check",
                    return_value={"passed": True, "max_coordinate_error_px": 0.0,
                                  "tolerance_px": 0.01}):
                report = asa.run(out, families=["roboto"], sizes=[14])
            self.assertEqual(bf.call_count, 1)
            self.assertEqual(bf.call_args[1], {"profile": "baseline", "ppem": 14})
            self.assertTrue(report["passed"])
        # FakePipeline has no baseline or post-stage API.

    def test_case_failure_records_and_continues(self):
        from compare_shamir_pipeline import CHARS
        chars = list(CHARS)
        build = {"records": {c: _record() for c in CHARS},
                 "baseline_decisions": {"policy": "x"}}

        def coord(face, char, size, graph):
            return {"passed": char != chars[0], "max_coordinate_error_px": 0.0,
                    "tolerance_px": 0.01}

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fresh"
            out.mkdir()
            with mock.patch.object(asa, "Pipeline", _fake_pipeline_cls(tmp)), \
                mock.patch.object(asa, "build_font", return_value=build), \
                mock.patch.object(asa, "digest", return_value="deadbeef"), \
                mock.patch.object(asa.ft, "Face", return_value=mock.Mock()), \
                mock.patch.object(asa, "graph_issues", return_value=[]), \
                mock.patch.object(asa, "construction_issues", return_value=[]), \
                mock.patch.object(asa, "coordinate_check", side_effect=coord):
                report = asa.run(out, families=["roboto"], sizes=[14])
        self.assertFalse(report["passed"])
        self.assertEqual(report["counts"]["cases"], len(chars))
        self.assertTrue(any(f.get("char") == chars[0] for f in report["failures"]))

    def test_build_failure_is_failure_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fresh"
            out.mkdir()
            with mock.patch.object(asa, "Pipeline", _fake_pipeline_cls(tmp)), \
                mock.patch.object(asa, "build_font", side_effect=RuntimeError("boom")):
                report = asa.run(out, families=["roboto"], sizes=[14])
            self.assertFalse(report["passed"])
            self.assertEqual(report["builds"], [])
            self.assertTrue(any("boom" in f["error"] for f in report["failures"]))
            self.assertTrue((out / "source-alignment-report.json").exists())

    def test_provenance_is_enabled_stages_only(self):
        from compare_shamir_pipeline import CHARS
        build = {"records": {c: _record() for c in CHARS},
                 "baseline_decisions": {"policy": "x"}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fresh"
            out.mkdir()
            with mock.patch.object(asa, "Pipeline", _fake_pipeline_cls(tmp)), \
                mock.patch.object(asa, "build_font", return_value=build), \
                mock.patch.object(asa, "digest", return_value="deadbeef"), \
                mock.patch.object(asa.ft, "Face", return_value=mock.Mock()), \
                mock.patch.object(asa, "graph_issues", return_value=[]), \
                mock.patch.object(asa, "construction_issues", return_value=[]), \
                mock.patch.object(
                    asa, "coordinate_check",
                    return_value={"passed": True, "max_coordinate_error_px": 0.0,
                                  "tolerance_px": 0.01}):
                report = asa.run(out, families=["roboto"], sizes=[14])
            self.assertEqual(report["provenance"]["stages"], list(asa.ENABLED_STAGES))
            self.assertEqual(report["config"]["enabled_stages"], list(asa.ENABLED_STAGES))
            self.assertEqual(report["counts"]["expected_builds"], 1)
            self.assertEqual(report["counts"]["builds"], 1)

    def test_case_error_continues_to_next_char(self):
        from compare_shamir_pipeline import CHARS
        chars = list(CHARS)
        build = {"records": {c: _record() for c in CHARS},
                 "baseline_decisions": {"policy": "x"}}

        def coord(face, char, size, graph):
            if char == chars[0]:
                raise RuntimeError("oracle boom")
            return {"passed": True, "max_coordinate_error_px": 0.0,
                    "tolerance_px": 0.01}

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fresh"
            out.mkdir()
            with mock.patch.object(asa, "Pipeline", _fake_pipeline_cls(tmp)), \
                mock.patch.object(asa, "build_font", return_value=build), \
                mock.patch.object(asa, "digest", return_value="deadbeef"), \
                mock.patch.object(asa.ft, "Face", return_value=mock.Mock()), \
                mock.patch.object(asa, "graph_issues", return_value=[]), \
                mock.patch.object(asa, "construction_issues", return_value=[]), \
                mock.patch.object(asa, "coordinate_check", side_effect=coord):
                report = asa.run(out, families=["roboto"], sizes=[14])
        self.assertFalse(report["passed"])
        self.assertEqual(report["counts"]["cases"], len(chars))
        self.assertEqual(len(report["builds"]), 1)
        self.assertTrue(any(f.get("char") == chars[0] and "boom" in f["error"]
                            for f in report["failures"]))
        second = [c for c in report["builds"][0]["cases"] if c["char"] == chars[1]]
        self.assertTrue(second and second[0]["passed"])

    def test_invalid_inputs_rejected_before_mkdir(self):
        import build_source_bitmap as bsb
        real_pipeline = bsb.Pipeline
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                asa.run(Path(tmp) / "nope", families=[], sizes=[14])
            self.assertFalse((Path(tmp) / "nope").exists())
            with self.assertRaises(ValueError):
                asa.run(Path(tmp) / "nope", families=["roboto", "roboto"], sizes=[14])
            with self.assertRaises(ValueError):
                asa.run(Path(tmp) / "nope", families=["nope"], sizes=[14])
            with self.assertRaises(ValueError):
                asa.run(Path(tmp) / "nope", families=["roboto"], sizes=[0])
            with self.assertRaises(ValueError):
                asa.run(Path(tmp) / "nope2", families=["roboto"], sizes=[14])
            self.assertFalse((Path(tmp) / "nope2").exists())

    def test_fresh_output_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fresh"
            out.mkdir()
            (out / "old.txt").write_text("x")
            with mock.patch.object(asa, "Pipeline", _fake_pipeline_cls(tmp)):
                with self.assertRaises(ValueError):
                    asa.run(out, families=["roboto"], sizes=[14])
            self.assertFalse((out / "source-alignment-report.json").exists())

    def test_missing_decision_metadata_is_failure(self):
        from compare_shamir_pipeline import CHARS
        build = {"records": {c: _record() for c in CHARS}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fresh"
            out.mkdir()
            with mock.patch.object(asa, "Pipeline", _fake_pipeline_cls(tmp)), \
                mock.patch.object(asa, "build_font", return_value=build), \
                mock.patch.object(asa, "digest", return_value="deadbeef"), \
                mock.patch.object(asa.ft, "Face", return_value=mock.Mock()):
                report = asa.run(out, families=["roboto"], sizes=[14])
        self.assertFalse(report["passed"])
        self.assertIn("baseline_decisions", report["failures"][0]["error"])


if __name__ == "__main__":
    unittest.main()
