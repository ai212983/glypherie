"""Cache identity tests: build_identity, keys, validation; no upstream needed."""

import importlib.util
import json
import os
import tempfile
import unittest

RUNNER = os.path.join(os.path.dirname(__file__), "..", "runner", "run_extract.py")


def load_runner():
    spec = importlib.util.spec_from_file_location("run_extract_cache", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rx = load_runner()

BASE_KWARGS = {
    "font_sha256_original": "b" * 64,
    "font_sha256_instantiated": "a" * 64,
    "axes_resolved": {},
    "outline_flavor": "quad",
    "shape_size": 150,
    "curve_steps": 12,
    "seed": 0,
    "char": "k",
    "packages": {
        "numpy": "1.26.4",
        "scipy": "1.11.4",
        "matplotlib": "3.8.4",
        "networkx": "3.1",
        "pillow": "10.4.0",
        "fonttools": "4.53.1",
        "pyclipper": "1.3.0.post5",
        "opencv": "4.8.1.78",
        "skgeom": "unversioned",
        "svgpathtools": "1.6.1",
        "svgwrite": "1.4.3",
    },
    "binding": {"sha256": "c" * 64, "objects": {"cautograff": [], "skgeom": []}},
    "image_id": "sha256:test",
}


def identity(**overrides):
    kwargs = dict(BASE_KWARGS)
    kwargs.update(overrides)
    return rx.build_identity(**kwargs)


def valid_record(ident):
    return {
        "schema_version": rx.SCHEMA_VERSION,
        "strokes": [{"P": [[0, 0]]}],
        "provenance": {"char": ident["char"]},
        "identity": ident,
    }


class CacheIdentityTests(unittest.TestCase):
    def test_key_stable(self):
        self.assertEqual(rx.cache_key(identity()), rx.cache_key(identity()))

    def test_each_field_changes_key(self):
        base = rx.cache_key(identity())
        mutations = {
            "font_sha256_original": "0" * 64,
            "font_sha256_instantiated": "0" * 64,
            "axes_resolved": {"wght": 700.0},
            "char": "y",
            "outline_flavor": "cubic",
            "shape_size": 100,
            "curve_steps": 6,
            "seed": 1,
            "image_id": "sha256:other",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                self.assertNotEqual(base, rx.cache_key(identity(**{field: value})))

    def test_each_version_changes_key(self):
        base = rx.cache_key(identity())
        for pkg in BASE_KWARGS["packages"]:
            with self.subTest(pkg=pkg):
                packages = dict(BASE_KWARGS["packages"], **{pkg: "0.0.0"})
                self.assertNotEqual(base, rx.cache_key(identity(packages=packages)))

    def test_binding_change_rejected(self):
        ident = identity()
        record = valid_record(ident)
        other = identity(binding={"sha256": "0" * 64, "objects": {}})
        ok, reason = rx.cache_valid(record, other)
        self.assertFalse(ok)
        self.assertIn("native_binding", reason)

    def test_repo_commit_change_rejected(self):
        ident = identity()
        record = valid_record(ident)
        tampered = dict(ident, repo_commits=dict(ident["repo_commits"]))
        tampered["repo_commits"] = dict(tampered["repo_commits"], skgeom="0" * 40)
        ok, reason = rx.cache_valid(record, tampered)
        self.assertFalse(ok)
        self.assertIn("repo_commits", reason)

    def test_runner_change_rejected(self):
        ident = identity()
        record = valid_record(ident)
        tampered = dict(ident, runner_sha256="0" * 64)
        ok, reason = rx.cache_valid(record, tampered)
        self.assertFalse(ok)
        self.assertIn("runner_sha256", reason)

    def test_seed_change_rejected(self):
        ok, _ = rx.cache_valid(valid_record(identity()), identity(seed=7))
        self.assertFalse(ok)

    def test_extra_identity_field_rejected(self):
        ident = identity()
        record = valid_record(ident)
        record["identity"] = dict(ident, surprise="x")
        ok, reason = rx.cache_valid(record, ident)
        self.assertFalse(ok)
        self.assertIn("surprise", reason)


class CacheValidationTests(unittest.TestCase):
    def test_round_trip_through_disk(self):
        ident = identity()
        record = valid_record(ident)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, rx.cache_key(ident) + ".json")
            with open(path, "w") as handle:
                json.dump(record, handle)
            with open(path) as handle:
                loaded = json.load(handle)
            ok, reason = rx.cache_valid(loaded, ident)
            self.assertTrue(ok, reason)

    def test_corrupt_file_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w") as handle:
                handle.write("{not json")
            with self.assertRaises(Exception):
                with open(path) as handle:
                    json.load(handle)

    def test_stale_schema_rejected(self):
        record = valid_record(identity())
        record["schema_version"] = "extract-record-v1"
        ok, reason = rx.cache_valid(record, identity())
        self.assertFalse(ok)
        self.assertIn("schema", reason)

    def test_missing_identity_rejected(self):
        record = {"schema_version": rx.SCHEMA_VERSION, "strokes": [{}]}
        ok, reason = rx.cache_valid(record, identity())
        self.assertFalse(ok)
        self.assertIn("identity", reason)

    def test_empty_strokes_rejected(self):
        record = valid_record(identity())
        record["strokes"] = []
        ok, reason = rx.cache_valid(record, identity())
        self.assertFalse(ok)
        self.assertIn("strokes", reason)


class UnionReportTests(unittest.TestCase):
    def test_overlap_fraction(self):
        # Two unit squares overlapping on half their area.
        s1 = [(0, 0), (1, 0), (1, 1), (0, 1)]
        s2 = [(0.5, 0), (1.5, 0), (1.5, 1), (0.5, 1)]
        info = rx.union_report([s1, s2], [[(0, 0), (1.5, 0), (1.5, 1), (0, 1)]])
        self.assertEqual(info["n_contours_original"], 2)
        self.assertEqual(info["n_contours_unioned"], 1)
        self.assertAlmostEqual(info["overlap_fraction"], 0.25)
        self.assertEqual(info["fill_rule"], "nonzero")

    def test_disjoint_union(self):
        s1 = [(0, 0), (1, 0), (1, 1), (0, 1)]
        s2 = [(2, 0), (3, 0), (3, 1), (2, 1)]
        info = rx.union_report([s1, s2], [s1, s2])
        self.assertAlmostEqual(info["overlap_fraction"], 0.0)

    def test_union_shape_real_clip(self):
        try:
            import autograff.geom.clipper_wrap  # noqa: F401
        except ImportError:
            self.skipTest("autograff/clipper unavailable outside container")
        # Overlapping bars merge; disjoint unit squares do not.
        bar1 = [(0, 0), (2, 0), (2, 5), (0, 5)]
        bar2 = [(1, 3), (3, 3), (3, 8), (1, 8)]
        united = rx.union_shape([bar1, bar2])
        self.assertEqual(len(united), 1)
        info = rx.union_report([bar1, bar2], united)
        self.assertGreater(info["overlap_fraction"], 0.0)
        self.assertLess(info["overlap_fraction"], 1.0)


if __name__ == "__main__":
    unittest.main()
