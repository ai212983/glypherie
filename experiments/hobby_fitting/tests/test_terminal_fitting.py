# cspell:words oncurve offcurve fontTools instancer wght lstsq emit subpixel

"""Terminal reference-height constraints: geometry checks, no optical claims.

Every assertion follows the owning model: Hersch sections 5-6 supply
reference-line phase and diagonal-width control; Hobby 3.3 supplies common
displacement of horizontal regions; Shene convex-hull support bounds curves
by their controls. Real A/y cases load the canonical font through fontTools
and the capture glyph id, never an ad hoc raw cache. Width assertions
compare source-relative contrast direction and the (17) cost improvement,
never exact preferred pixels. Passing tests do not establish optical
acceptance.
"""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

from experiments.hobby_fitting import curved_crossing_review as review
from experiments.hobby_fitting import smooth_curve_fit as scf
from experiments.hobby_fitting import terminal_fitting as tf
from experiments.hobby_fitting.real_outline import parse_commands
from experiments.hobby_fitting.tests.test_curved_crossing import (
    assert_same_geometry,
    primitives,
    rotate_commands,
)
from experiments.hobby_fitting.tests.test_smooth_curve_geometry import (
    TOPOLOGY_BINARY_REASON,
    topology_binary_present,
)


DATA = ROOT / "out/diagnostics/curved-crossing/review-final" / \
    "SourceSans3-400-16-selective_default" / "data.json"
CELL = ROOT / "out/diagnostics/direct-diagonal/coverage-review/cells" / \
    "SourceSans3_16.0_400_selective_default.json"
CAPTURE = ROOT / "out/diagnostics/direct-diagonal/text-review" / \
    "ascii-captures" / "SourceSans3-400-16.json"
FONT = ROOT / "fonts" / "SourceSans3.ttf"

REAL = {}
REFERENCE = {}
HAS_REAL = False
REAL_REASON = "real-glyph prerequisites not checked yet"


def _require_real():
    if not HAS_REAL:
        raise unittest.SkipTest(REAL_REASON)


def setUpModule():
    global HAS_REAL, REAL_REASON
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
    except ImportError:
        REAL_REASON = (
            "missing optional fontTools dependency (run with "
            "uv run --with fonttools==4.53.1 -- python -m unittest ...)")
        return
    # Optional git-ignored corpora: DATA from
    # experiments/hobby_fitting/curved_crossing_review.py (review-final),
    # CAPTURE from experiments/hobby_fitting/text_review.py (text-review),
    # CELL from experiments/hobby_fitting/coverage_review.py
    # (coverage-review). Synthetic CapDetection/UprightControl/
    # WeldConstraints tests still run without them.
    missing = [str(p) for p in (DATA, CAPTURE, CELL) if not p.exists()]
    if missing:
        REAL_REASON = (
            "missing optional captures %s (git-ignored corpora; see "
            "comment above setUpModule for generators)"
            % ", ".join(missing))
        return
    glyphs = {g["char"]: g for g in json.loads(DATA.read_text())["glyphs"]}
    capture = json.loads(CAPTURE.read_text())[0]
    records = {r["codepoint"]: r
               for r in capture["modes"]["selective_default"]["records"]}
    font = instantiateVariableFont(TTFont(FONT), capture["axes"],
                                   inplace=False)
    REFERENCE.update(json.loads(CELL.read_text())["reference"])
    for char in ("A", "y"):
        fix = glyphs[char]
        record = records[fix["codepoint"]]
        raw = review.raw_commands(font, record["glyph_id"], 16.0)
        assert raw == fix["raw_source"]
        REAL[char] = {"raw": raw, "source": fix["source"],
                      "upstream": fix["original_upstream_commands"],
                      "native": tuple(fix["native_axes"])}
    HAS_REAL = True


def shift(commands, dx=0.0, dy=0.0):
    out = []
    for cmd in commands:
        cmd = dict(cmd)
        for key in ("x", "x1", "x2"):
            if key in cmd:
                cmd[key] = cmd[key] + dx
        for key in ("y", "y1", "y2"):
            if key in cmd:
                cmd[key] = cmd[key] + dy
        out.append(cmd)
    return out


def fit_real(char, native=(False, False), topology_checker=None):
    fix = REAL[char]
    return tf.fit(fix["raw"], fix["source"], fix["upstream"], 16.0,
                  REFERENCE, native, topology_checker)


class RealTerminalFitting(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _require_real()
        if not topology_binary_present():
            raise unittest.SkipTest(TOPOLOGY_BINARY_REASON)
        cls.a = fit_real("A")
        cls.y = fit_real("y")

    def test_a_applies_with_exact_cap_heights(self):
        self.assertTrue(self.a["applied"])
        self.assertEqual(self.a["reason"], "fitted")
        planes = {(tuple(c["vertices"]), c["plane"]) for c in self.a["caps"]}
        self.assertIn(((1, 2), "max"), planes)
        self.assertIn(((3, 4), "min"), planes)
        # The implicit closing line is a welded cap edge, not a duplicate.
        self.assertIn(((11, 0), "min"), planes)
        self.assertEqual(self.a["cap_vertices"], [0, 1, 2, 3, 4, 11])
        up = parse_commands(REAL["A"]["upstream"])["oncurve"]
        cand = parse_commands(self.a["candidate_commands"])["oncurve"]
        for v in self.a["cap_vertices"]:
            self.assertEqual(cand[v][1], up[v][1])
        self.assertEqual([up[v][1] for v in (3, 4, 11, 0)],
                         [0.0, 0.0, 0.0, 0.0])
        self.assertEqual([up[v][1] for v in (1, 2)], [11.0, 11.0])

    def test_y_applies_with_upper_terminal_only(self):
        self.assertTrue(self.y["applied"])
        planes = {(tuple(c["vertices"]), c["plane"]) for c in self.y["caps"]}
        self.assertEqual(planes, {((9, 10), "max"), ((17, 18), "max"), ((13, 14), "interior")})
        # The descender minimum is a curve extremum, never a straight cap.
        self.assertNotIn("min", {c["plane"] for c in self.y["caps"]})
        up = parse_commands(REAL["y"]["upstream"])["oncurve"]
        cand = parse_commands(self.y["candidate_commands"])["oncurve"]
        for v in self.y["cap_vertices"]:
            self.assertEqual(cand[v][1], 8.0)
            self.assertEqual(cand[v][1], up[v][1])

    def test_real_validity_covers_cost_topology_and_sweep(self):
        for result in (self.a, self.y):
            validity = result["validity"]
            self.assertTrue(validity["ok"])
            self.assertTrue(validity["cost_ok"])
            self.assertLess(validity["cost_candidate"],
                            validity["cost_upstream"])
            self.assertTrue(validity["topology"])
            self.assertTrue(validity["cap_exact"])
            self.assertEqual(validity["curve_sweep"], "clear")
            self.assertLessEqual(result["movement"], result["bound"])

    def test_a_uprights_keep_reference_x(self):
        self.assertEqual(self.a["upright_vertices"], [12, 13, 14, 15])
        up = parse_commands(REAL["A"]["upstream"])["oncurve"]
        cand = parse_commands(self.a["candidate_commands"])["oncurve"]
        for v in self.a["upright_vertices"]:
            self.assertEqual(cand[v][0], up[v][0])
        self.assertTrue(self.a["validity"]["upright_exact"])

    def test_y_has_no_uprights(self):
        self.assertEqual(self.y["uprights"], [])
        self.assertEqual(self.y["upright_vertices"], [])
        self.assertTrue(self.y["validity"]["upright_exact"])

    def test_width_contrast_follows_anchor_coupling(self):
        rels = [a["rel"] for a in REFERENCE["anchors"]]
        mean_rel = sum(rels) / len(rels)
        self.assertLess(mean_rel, 0.0)
        for result in (self.a, self.y):
            widths = result["widths"]
            # Coupled narrowing toward the anchor change, not pixel identity.
            self.assertLess(widths["candidate"], widths["upstream"])
            self.assertGreater(len(result["pairs"]), 0)

    def test_only_unpinned_vertices_move(self):
        for char, result in (("A", self.a), ("y", self.y)):
            upstream = REAL[char]["upstream"]
            cand = result["candidate_commands"]
            table = _positions(upstream)
            owned = {pos: idx for idx, pos in table.items()}
            pinned = set(result["fixed"]["anchors"])
            for pos, (c, u) in enumerate(zip(cand, upstream)):
                if c != u:
                    self.assertNotIn(owned[pos], pinned)


def _positions(commands):
    table, n = {}, 0
    for pos, cmd in enumerate(commands):
        if cmd["op"] in ("move_to", "line_to", "quad_to", "curve_to"):
            table[n] = pos
            n += 1
    return table


class CapDetection(unittest.TestCase):

    def test_interior_flat_reference_included_below_taller_strokes(self):
        raw = [{"op": "move_to", "x": 0.0, "y": 0.0},
               {"op": "line_to", "x": 10.0, "y": 0.0},
               {"op": "line_to", "x": 10.0, "y": 100.0},
               {"op": "line_to", "x": 0.0, "y": 100.0},
               {"op": "close"},
               {"op": "move_to", "x": 2.0, "y": 50.0},
               {"op": "line_to", "x": 8.0, "y": 50.0},
               {"op": "line_to", "x": 8.0, "y": 52.0},
               {"op": "line_to", "x": 2.0, "y": 52.0},
               {"op": "close"}]
        caps, lo, hi = tf.detect_caps(raw, shift(raw, dx=1.0))
        self.assertEqual((lo, hi), (0.0, 100.0))
        self.assertIn(50.0, [c["source_y"] for c in caps])
        self.assertEqual(len(caps), 4)
        self.assertEqual([c['plane'] for c in caps], ['min', 'max', 'interior', 'interior'])

    def test_nonflat_foot_excluded(self):
        raw = [{"op": "move_to", "x": 0.0, "y": 1.0},
               {"op": "line_to", "x": 10.0, "y": 10.0},
               {"op": "line_to", "x": 20.0, "y": 0.0},
               {"op": "close"}]
        caps, lo, hi = tf.detect_caps(raw, shift(raw, dx=1.0))
        self.assertEqual(lo, 0.0)
        self.assertEqual(caps, [])

    def test_curve_extremum_excluded(self):
        raw = [{"op": "move_to", "x": 0.0, "y": 0.0},
               {"op": "quad_to", "x1": 10.0, "y1": -10.0,
                "x": 20.0, "y": 0.0},
               {"op": "quad_to", "x1": 10.0, "y1": 10.0,
                "x": 0.0, "y": 0.0},
               {"op": "close"}]
        caps, lo, hi = tf.detect_caps(raw, shift(raw, dy=2.0))
        # Off-curve controls set the supporting planes beyond every endpoint.
        self.assertEqual((lo, hi), (-10.0, 10.0))
        self.assertEqual(caps, [])

    def test_detection_stable_under_translation(self):
        raw = [{"op": "move_to", "x": 0.0, "y": 0.0},
               {"op": "line_to", "x": 10.0, "y": 10.0},
               {"op": "line_to", "x": 20.0, "y": 0.0},
               {"op": "close"}]
        up = shift(raw, dx=1.0, dy=0.5)
        caps, _, _ = tf.detect_caps(raw, up)
        self.assertEqual(len(caps), 1)
        moved, _, _ = tf.detect_caps(shift(raw, dx=3.5, dy=-2.0),
                                     shift(up, dx=3.5, dy=-2.0))
        self.assertEqual([c["vertices"] for c in moved],
                         [c["vertices"] for c in caps])
        self.assertEqual([c["plane"] for c in moved],
                         [c["plane"] for c in caps])
        self.assertAlmostEqual(moved[0]["source_y"],
                               caps[0]["source_y"] - 2.0)

    def test_closing_edge_cap_recorded_without_pairs(self):
        raw = [{"op": "move_to", "x": 0.0, "y": 0.0},
               {"op": "line_to", "x": 10.0, "y": 10.0},
               {"op": "line_to", "x": 20.0, "y": 0.0},
               {"op": "close"}]
        up = shift(raw, dx=1.0)
        caps, _, _ = tf.detect_caps(raw, up)
        self.assertEqual([(c["vertices"], c["plane"]) for c in caps],
                         [((2, 0), "min")])
        result = tf.fit(raw, raw, up, 16.0, REFERENCE, (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["caps"], caps)
        self.assertIs(result["candidate_commands"], up)


class Abstention(unittest.TestCase):

    def test_native_y_owned_preserves_packet(self):
        _require_real()
        fix = REAL["A"]
        result = tf.fit(fix["raw"], fix["source"], fix["upstream"], 16.0,
                        REFERENCE, (False, True))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "native-y-owned")
        self.assertIs(result["candidate_commands"], fix["upstream"])

    def test_native_x_leaves_no_useful_delta(self):
        _require_real()
        fix = REAL["A"]
        result = tf.fit(fix["raw"], fix["source"], fix["upstream"], 16.0,
                        REFERENCE, (True, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["candidate_commands"], fix["upstream"])

    def test_malformed_axes_abstains(self):
        _require_real()
        fix = REAL["A"]
        result = tf.fit(fix["raw"], fix["source"], fix["upstream"], 16.0,
                        REFERENCE, ("x",))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "malformed-native-axes")
        self.assertIs(result["candidate_commands"], fix["upstream"])

    def test_broken_correspondence_abstains(self):
        _require_real()
        fix = REAL["A"]
        broken = [dict(c) for c in fix["upstream"][:-1]]
        result = tf.fit(fix["raw"], fix["source"], broken, 16.0,
                        REFERENCE, (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "no-correspondence")
        self.assertIs(result["candidate_commands"], broken)

    def test_missing_reference_abstains(self):
        _require_real()
        if not topology_binary_present():
            raise unittest.SkipTest(TOPOLOGY_BINARY_REASON)
        result = fit_real("A")
        self.assertTrue(result["applied"])
        fix = REAL["A"]
        denied = tf.fit(fix["raw"], fix["source"], fix["upstream"], 16.0,
                        {}, (False, False))
        self.assertFalse(denied["applied"])
        self.assertEqual(denied["reason"], "no-reference-anchors")
        self.assertIs(denied["candidate_commands"], fix["upstream"])

    def test_disjoint_cap_does_not_rewrite_a_stroke_without_flat_references(self):
        rect = [{"op": "move_to", "x": 0.0, "y": -50.0},
                {"op": "line_to", "x": 10.0, "y": -50.0},
                {"op": "line_to", "x": 10.0, "y": 150.0},
                {"op": "line_to", "x": 0.0, "y": 150.0},
                {"op": "close"},
                {"op": "move_to", "x": 30.0, "y": 0.0},
                {"op": "line_to", "x": 50.0, "y": 100.0},
                # Hobby 3.3's horizontal-region condition: these two
                # slanted end edges create no local height constraints.
                {"op": "line_to", "x": 60.0, "y": 101.0},
                {"op": "line_to", "x": 40.0, "y": 1.0},
                {"op": "close"}]
        up = shift(rect, dx=2.0)
        reference = {"anchors": [{"source_width": 10.0, "fitted_width": 8.0,
                                  "rel": -0.2, "length": 100.0,
                                  "tangent": (0.0, 1.0)}]}
        result = tf.fit(rect, rect, up, 16.0, reference, (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "cap-not-involved")
        self.assertEqual(result["cap_vertices"], [0, 1, 2, 3])
        self.assertEqual(result["candidate_commands"], up)

    def test_default_topology_applies_without_callback(self):
        _require_real()
        if not topology_binary_present():
            raise unittest.SkipTest(TOPOLOGY_BINARY_REASON)
        result = fit_real("A")
        self.assertTrue(result["applied"])
        self.assertTrue(result["validity"]["topology"])

    def test_rejecting_callback_abstains(self):
        _require_real()
        if not topology_binary_present():
            raise unittest.SkipTest(TOPOLOGY_BINARY_REASON)
        fix = REAL["A"]
        for checker in (lambda *a: False, lambda *a: {"ok": False},
                        lambda *a: 1 / 0):
            result = tf.fit(fix["raw"], fix["source"], fix["upstream"], 16.0,
                            REFERENCE, (False, False),
                            topology_checker=checker)
            self.assertFalse(result["applied"])
            self.assertEqual(result["reason"], "invalid-candidate")
            self.assertEqual(result["validity"]["stage"],
                             "topology-rejected")
            self.assertIs(result["candidate_commands"], fix["upstream"])


class UprightControl(unittest.TestCase):

    STEM = [(0.0, 0.0), (0.0, 100.0), (10.0, 100.0), (10.0, 0.0)]
    BAR = [(30.0, 0.0), (50.0, 100.0), (60.0, 100.0), (40.0, 0.0)]
    REFERENCE = {"anchors": [{"source_width": 9.0, "fitted_width": 7.2,
                               "rel": -0.2, "length": 100.0,
                               "tangent": (0.4, 0.9)}]}

    @classmethod
    def outline(cls):
        raw = [{"op": "move_to", "x": cls.STEM[0][0], "y": cls.STEM[0][1]}]
        for x, y in cls.STEM[1:]:
            raw.append({"op": "line_to", "x": x, "y": y})
        raw.append({"op": "close"})
        raw.append({"op": "move_to", "x": cls.BAR[0][0], "y": cls.BAR[0][1]})
        for x, y in cls.BAR[1:]:
            raw.append({"op": "line_to", "x": x, "y": y})
        raw.append({"op": "close"})
        return raw

    def test_detect_uprights_only_shared_verticals(self):
        raw = self.outline()
        found = tf.detect_uprights(raw, shift(raw, dx=2.0))
        self.assertEqual([u["vertices"] for u in found], [(0, 1), (2, 3)])
        self.assertEqual([u["source_x"] for u in found], [0.0, 10.0])
        self.assertEqual([u["upstream_x"] for u in found], [2.0, 12.0])
        # Slanted bar edges share no vertical and create no constraint.
        bar = raw[5:10]
        self.assertEqual(tf.detect_uprights(bar, shift(bar, dx=2.0)), [])

    def test_split_upstream_x_excluded(self):
        raw = self.outline()
        up = shift(raw, dx=2.0)
        up[1]["x"] += 1.0
        found = tf.detect_uprights(raw, up)
        self.assertEqual([u["vertices"] for u in found], [(2, 3)])

    def test_shared_diagonal_moves_around_pinned_stem(self):
        if not topology_binary_present():
            raise unittest.SkipTest(TOPOLOGY_BINARY_REASON)
        raw = self.outline()
        up = shift(raw, dx=2.0)
        result = tf.fit(raw, raw, up, 16.0, self.REFERENCE, (False, False))
        self.assertTrue(result["applied"], result["reason"])
        self.assertEqual(result["upright_vertices"], [0, 1, 2, 3])
        self.assertTrue(result["validity"]["upright_exact"])
        self.assertTrue(result["validity"]["cap_exact"])
        cand = parse_commands(result["candidate_commands"])["oncurve"]
        ups = parse_commands(up)["oncurve"]
        for v in range(4):
            self.assertEqual(tuple(cand[v]), tuple(ups[v]))
        self.assertTrue(any(tuple(cand[v]) != tuple(ups[v])
                            for v in range(4, 8)))

    def test_malformed_anchors_abstain(self):
        raw = self.outline()
        up = shift(raw, dx=2.0)
        bad_refs = [
            {"anchors": [{"source_width": float("nan"), "fitted_width": 7.2,
                          "rel": -0.2, "length": 100.0,
                          "tangent": (0.4, 0.9)}]},
            {"anchors": [{"source_width": 9.0, "fitted_width": 7.2,
                          "rel": -0.2, "length": 0.0,
                          "tangent": (0.4, 0.9)}]},
            {"anchors": [{"source_width": 9.0, "fitted_width": 7.2,
                          "rel": -0.2, "length": 100.0,
                          "tangent": (0.0, 0.0)}]},
            {"anchors": [{"source_width": 9.0, "fitted_width": 7.2,
                          "rel": -0.2, "length": 100.0}]},
            {"anchors": ["upright"]},
        ]
        for reference in bad_refs:
            result = tf.fit(raw, raw, up, 16.0, reference, (False, False))
            self.assertFalse(result["applied"], reference)
            self.assertEqual(result["reason"], "malformed-anchors")
            self.assertIs(result["candidate_commands"], up)

    def test_string_coordinate_abstains(self):
        raw = self.outline()
        broken = [dict(c) for c in raw]
        broken[1]["x"] = "oops"
        up = shift(raw, dx=2.0)
        result = tf.fit(broken, raw, up, 16.0, self.REFERENCE, (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "malformed-commands")
        self.assertIs(result["candidate_commands"], up)


def explicit_dup(commands):
    """Append an explicit zero-length closing edge before each close."""
    out, start = [], None
    for cmd in commands:
        if cmd["op"] == "move_to":
            start = (cmd["x"], cmd["y"])
            out.append(dict(cmd))
        elif cmd["op"] == "close":
            out.append({"op": "line_to", "x": start[0], "y": start[1]})
            out.append(dict(cmd))
        else:
            out.append(dict(cmd))
    return out


class EmptyAndInvalidInputs(unittest.TestCase):

    def test_space_empty_outline_abstains_exact_up(self):
        _require_real()
        empty = []
        result = tf.fit(empty, empty, empty, 16.0, REFERENCE, (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "all-abstained")
        self.assertIs(result["candidate_commands"], empty)

    def test_nonpositive_or_nonfinite_size_abstains(self):
        _require_real()
        fix = REAL["A"]
        for bad in (0, 0.0, -1, -16.0, float("nan"), float("inf"),
                    float("-inf"), "16", None, True):
            result = tf.fit(fix["raw"], fix["source"], fix["upstream"], bad,
                            REFERENCE, (False, False))
            self.assertFalse(result["applied"], bad)
            self.assertEqual(result["reason"], "malformed-size", bad)
            self.assertIs(result["candidate_commands"], fix["upstream"])

    def test_nonfinite_raw_abstains_without_feature(self):
        _require_real()
        fix = REAL["A"]
        raw = [dict(c) for c in fix["raw"]]
        raw[1]["x"] = float("nan")
        result = tf.fit(raw, fix["source"], fix["upstream"], 16.0,
                        REFERENCE, (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "malformed-commands")
        self.assertIs(result["candidate_commands"], fix["upstream"])

    def test_nonfinite_captured_abstains_without_feature(self):
        _require_real()
        fix = REAL["A"]
        captured = [dict(c) for c in fix["source"]]
        captured[2]["y"] = float("inf")
        result = tf.fit(fix["raw"], captured, fix["upstream"], 16.0,
                        REFERENCE, (False, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "malformed-commands")
        self.assertIs(result["candidate_commands"], fix["upstream"])


class WeldConstraints(unittest.TestCase):

    def test_skips_alias_free_of_variables(self):
        base = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)]
        rows, merged, conflict = tf._weld_constraints({2: 0}, {1}, set(),
                                                      base)
        self.assertEqual((rows, merged, conflict), ([], set(), None))

    def test_merges_free_alias_of_plain_canonical(self):
        base = [(0.0, 0.0), (10.0, 5.0), (30.0, 0.0), (0.0, 0.0)]
        rows, merged, conflict = tf._weld_constraints({3: 0}, {3}, set(),
                                                      base)
        self.assertIsNone(conflict)
        self.assertEqual(merged, {3})
        self.assertEqual(len(rows), 2)
        for axis in (0, 1):
            self.assertEqual(rows[axis][0][2 * 3 + axis], 1.0)
            self.assertEqual(rows[axis][0][2 * 0 + axis], -1.0)
            self.assertAlmostEqual(rows[axis][1],
                                   base[0][axis] - base[3][axis])

    def test_conflicts_when_canonical_is_variable(self):
        base = [(0.0, 0.0), (10.0, 5.0), (0.0, 0.0)]
        _, _, conflict = tf._weld_constraints({2: 0}, {0, 2}, set(), base)
        self.assertEqual(conflict, (2, 0))

    def test_conflicts_when_alias_is_pinned(self):
        base = [(0.0, 0.0), (10.0, 5.0), (0.0, 0.0)]
        _, _, conflict = tf._weld_constraints({2: 0}, {2}, {(2, 0)}, base)
        self.assertEqual(conflict, (2, 0))


class ExplicitClosureAndRotation(unittest.TestCase):

    def test_rotation_preserves_stated_geometry(self):
        _require_real()
        if not topology_binary_present():
            raise unittest.SkipTest(TOPOLOGY_BINARY_REASON)
        fix = REAL["y"]
        rotated = [rotate_commands(cmds, 2)
                   for cmds in (fix["raw"], fix["source"], fix["upstream"])]
        result = tf.fit(*rotated, 16.0, REFERENCE, (False, False))
        self.assertTrue(result["applied"], result["reason"])
        base = fit_real("y")
        assert_same_geometry(self, base["candidate_commands"],
                             result["candidate_commands"])
        self.assertTrue(result["validity"]["weld_exact"])
        up = parse_commands(rotated[2])["oncurve"]
        cand = parse_commands(result["candidate_commands"])["oncurve"]
        for v in result["cap_vertices"]:
            self.assertEqual(cand[v][1], up[v][1])

    def test_explicit_closure_alias_remains_exact(self):
        _require_real()
        fix = REAL["y"]
        duped = [explicit_dup(cmds)
                 for cmds in (fix["raw"], fix["source"], fix["upstream"])]
        parsed = parse_commands(duped[1])
        weld = scf._weld_map(parsed,
                             parsed["oncurve"] + parsed["offcurve"])
        self.assertTrue(weld)
        result = tf.fit(*duped, 16.0, REFERENCE, (False, False))
        if result['applied']:
            self.assertTrue(result['validity']['weld_exact'])
            self.assertTrue(result['validity']['cap_exact'])
        else:
            self.assertIs(result["candidate_commands"], duped[2])
        # Additional local references can make the constrained fit feasible;
        # success and rejection must both retain the exact shared closure.
        cand = parse_commands(result["candidate_commands"])
        points = cand["oncurve"] + cand["offcurve"]
        for dup, canon in weld.items():
            self.assertEqual(tuple(points[dup]), tuple(points[canon]))

    def test_cubic_first_alias_never_splits(self):
        raw = [{"op": "move_to", "x": 0.0, "y": 50.0},
               {"op": "curve_to", "x1": 1.0, "y1": 58.0,
                "x2": 4.0, "y2": 58.0, "x": 5.0, "y": 50.0},
               {"op": "line_to", "x": 45.0, "y": 100.0},
               {"op": "line_to", "x": 55.0, "y": 100.0},
               {"op": "line_to", "x": 0.0, "y": 50.0},
               {"op": "close"}]
        parsed = parse_commands(raw)
        points = parsed["oncurve"] + parsed["offcurve"]
        # The first-line/quad lookup misses the cubic-first alias.
        self.assertEqual(scf._weld_map(parsed, points), {})
        self.assertEqual(tf._closure_aliases(parsed, points), {4: 0})
        reference = {"anchors": [{"source_width": 2.5, "fitted_width": 2.0,
                                  "rel": -0.2, "length": 100.0,
                                  "tangent": (0.62, 0.78)}]}
        up = shift(raw, dx=2.0)
        result = tf.fit(raw, raw, up, 16.0, reference, (False, False))
        self.assertFalse(result["applied"])
        self.assertIs(result["candidate_commands"], up)
        self.assertTrue(result["validity"]["weld_exact"])
        cand = parse_commands(result["candidate_commands"])
        cand_points = cand["oncurve"] + cand["offcurve"]
        self.assertEqual(tuple(cand_points[4]), tuple(cand_points[0]))
        # A split upstream alias is a mismatch, never a solved guess.
        split = shift(raw, dx=2.0)
        split[4]["x"] += 1.0
        denied = tf.fit(raw, raw, split, 16.0, reference, (False, False))
        self.assertFalse(denied["applied"])
        self.assertEqual(denied["reason"], "weld-mismatch")
        self.assertIs(denied["candidate_commands"], split)

    def test_merged_alias_moves_with_canonical(self):
        if not topology_binary_present():
            raise unittest.SkipTest(TOPOLOGY_BINARY_REASON)
        s, q, a, b, d = ((0.0, 50.0), (5.0, 50.0), (45.0, 100.0),
                         (55.0, 100.0), (0.0, 50.0))
        raw = [{"op": "move_to", "x": s[0], "y": s[1]},
               {"op": "line_to", "x": q[0], "y": q[1]},
               {"op": "line_to", "x": a[0], "y": a[1]},
               {"op": "line_to", "x": b[0], "y": b[1]},
               {"op": "line_to", "x": d[0], "y": d[1]},
               {"op": "close"}]
        self.assertEqual(len(primitives(raw)), 4)
        up = shift(raw, dx=2.0)
        parsed = parse_commands(raw)
        self.assertEqual(scf._weld_map(parsed, parsed["oncurve"]
                                       + parsed["offcurve"]), {4: 0})
        reference = {"anchors": [{"source_width": 2.5, "fitted_width": 2.0,
                                  "rel": -0.2, "length": 100.0,
                                  "tangent": (0.62, 0.78)}]}
        result = tf.fit(raw, raw, up, 16.0, reference, (False, False))
        self.assertTrue(result["applied"], result["reason"])
        self.assertTrue(result["validity"]["weld_exact"])
        self.assertTrue(result["validity"]["cap_exact"])
        cand = parse_commands(result["candidate_commands"])
        points = cand["oncurve"] + cand["offcurve"]
        self.assertEqual(tuple(points[4]), tuple(points[0]))


if __name__ == "__main__":
    unittest.main()
