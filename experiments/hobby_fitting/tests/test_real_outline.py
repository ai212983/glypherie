"""Real-outline straight-stroke coupling; geometric evidence only.

The restricted segment-Voronoi guard rejects flank stations whose disk
touches an end-cap corner pocket; interior dominance intervals, Hobby
section 3.2, keep the middle spans, so the Roboto Flex '1' head applies
with movement inside half the narrowest retained sample 2r. Point
quadratics at shared paired endpoints are skipped by the Pythagorean
identity; adjacent kept cells merge across strictly-clear boundaries.
"""

import json
import math
import struct
import unittest
from pathlib import Path

import experiments.hobby_fitting.real_outline as ro

ROOT = Path(__file__).resolve().parents[3]
CAPTURES = ROOT / "out/diagnostics/roboto-flex-terminals-20261020/captures.json"


def cmds(points, close=True):
    out = [{"op": "move_to", "x": points[0][0], "y": points[0][1]}]
    out += [{"op": "line_to", "x": x, "y": y} for x, y in points[1:]]
    if close:
        out.append({"op": "close"})
    return out


def bits(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def records(size=16):
    with open(CAPTURES) as fh:
        data = json.load(fh)
    entry = [e for e in data
             if (e.get("size_px", e.get("size"))) == size][0]
    src = [r for r in entry["source"]["records"] if r["codepoint"] == 49][0]
    up = [r for r in entry["upstream"]["records"] if r["codepoint"] == 49][0]
    return src["fitted_commands"], up["fitted_commands"]


def tall_stem():
    """Tall stem anchor plus long related bar; flank disks clear caps."""
    source = cmds([(0, 0), (2, 0), (2, 12), (10, 12), (10, 14.5), (0, 14)])
    fitted = cmds([(0, 0), (3, 0), (3, 12), (10, 12), (10, 14.5), (0, 14)])
    return source, fitted


def assert_fixed_contract(testcase, result, source, fitted):
    """Anchor and unowned vertices stay bit-exact; only related move.

    Fixed-set semantics: every anchor vertex plus every vertex outside
    all coupled related pairs keeps exact upstream coordinates. The
    base stays all-source while fixed displacements join the constants.
    """
    parsed = ro.parse_commands(source)
    fitted_coords = ro._oncurve_coords(fitted)
    sel = ro.select_anchor(ro.recognize(parsed), parsed, fitted_coords)
    testcase.assertIsNone(sel["reason"])
    anchor = sel["anchor"]
    anchor_verts = {anchor["a"]["i0"], anchor["a"]["i1"],
                    anchor["b"]["i0"], anchor["b"]["i1"]}
    rel_verts = set()
    for pair in result["pairs"]:
        for edge in pair["edges"]:
            rel_verts.update(edge)
    all_verts = set(range(len(fitted_coords)))
    testcase.assertEqual(set(result["fixed"]),
                         anchor_verts | (all_verts - rel_verts))
    cand = [(c["x"], c["y"]) for c in result["candidate_commands"]
            if c["op"] in ("move_to", "line_to")]
    testcase.assertEqual(len(cand), len(fitted_coords))
    for v in result["fixed"]:
        testcase.assertEqual(
            tuple(cand[v]), (fitted_coords[v][0], fitted_coords[v][1]),
            "vertex %d must keep exact upstream coordinates" % v)
    for v in all_verts - set(result["fixed"]):
        testcase.assertIn(v, rel_verts)


class RecognitionTests(unittest.TestCase):
    def test_real_stem_and_head_found_with_shared_attachment(self):
        # Hobby (4): width is twice the medial radius across the stroke.
        if not CAPTURES.exists():
            self.skipTest("capture data absent")
        source, _ = records(16)
        recognition = ro.recognize(ro.parse_commands(source))
        self.assertIsNone(recognition["reason"])
        self.assertEqual(recognition["ambiguous"], [])
        self.assertEqual(len(recognition["pairs"]), 2)
        widths = sorted(c["width"] for c in recognition["pairs"])
        self.assertAlmostEqual(widths[0], 1.277, places=3)
        self.assertAlmostEqual(widths[1], 1.5, places=3)
        verts = [{c["a"]["i0"], c["a"]["i1"], c["b"]["i0"], c["b"]["i1"]}
                 for c in recognition["pairs"]]
        self.assertTrue(verts[0] & verts[1])

    def test_anchor_is_rectilinear_stem_with_integral_fit(self):
        # Hobby (3.3): source opposite parallel axis-aligned sides with
        # fitted boundaries integral on the same axis. Never the slant.
        if not CAPTURES.exists():
            self.skipTest("capture data absent")
        source, fitted = records(16)
        parsed = ro.parse_commands(source)
        sel = ro.select_anchor(ro.recognize(parsed), parsed,
                               ro._oncurve_coords(fitted))
        self.assertIsNone(sel["reason"])
        self.assertAlmostEqual(sel["ws"], 1.5, places=3)
        self.assertAlmostEqual(sel["wf"], 1.0, places=3)
        self.assertAlmostEqual(sel["rel"], -1.0 / 3.0, places=6)
        fitted_coords = ro._oncurve_coords(fitted)
        anchor = sel["anchor"]
        for v in (anchor["a"]["i0"], anchor["a"]["i1"],
                  anchor["b"]["i0"], anchor["b"]["i1"]):
            self.assertTrue(float(fitted_coords[v][0]).is_integer())

    def test_mismatched_ops_abstain(self):
        if not CAPTURES.exists():
            self.skipTest("capture data absent")
        source, fitted = records(16)
        broken = [dict(c) for c in fitted]
        broken[1] = {"op": "quad_to", "x": broken[1]["x"], "y": broken[1]["y"],
                     "x1": 0.0, "y1": 0.0}
        result = ro.run_glyph(source, broken, 16)
        self.assertEqual(result["reason"], "no-correspondence")
        self.assertFalse(result["applied"])

    def test_slice_rejects_curves_multi_and_self_intersection(self):
        loop = ([{"op": "move_to", "x": 0.0, "y": 0.0},
                 {"op": "line_to", "x": 0.0, "y": 10.0},
                 {"op": "quad_to", "x": 0.0, "y": 0.0,
                  "x1": 8.0, "y1": 10.0},
                 {"op": "close"}])
        self.assertEqual(
            ro.recognize(ro.parse_commands(loop))["reason"],
            "unsupported-curves")
        two = cmds([(0, 0), (2, 0), (2, 2), (0, 2)])[:-1]
        two += [{"op": "move_to", "x": 5.0, "y": 0.0},
                {"op": "line_to", "x": 7.0, "y": 0.0},
                {"op": "line_to", "x": 7.0, "y": 2.0},
                {"op": "line_to", "x": 5.0, "y": 2.0},
                {"op": "close"}]
        self.assertEqual(ro.recognize(ro.parse_commands(two))["reason"],
                         "multi-contour")
        bow = cmds([(0, 0), (2, 2), (2, 0), (0, 2)])
        self.assertEqual(ro.recognize(ro.parse_commands(bow))["reason"],
                         "self-intersecting")

    def test_exact_tie_abstains_with_diagnostics(self):
        # Equal competitors for one border must not resolve arbitrarily.
        comb = cmds([(0, 0), (0, 10), (4, 10), (4, 8), (1, 8), (1, 6),
                     (4, 6), (4, 4), (1, 4), (1, 2), (4, 2), (4, 0)])
        recognition = ro.recognize(ro.parse_commands(comb))
        self.assertTrue(recognition["ambiguous"])
        result = ro.run_glyph(comb, comb, 16)
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "ambiguous-pairing")

    def test_single_notch_keeps_one_pair(self):
        # The full-width pairing crosses a third border and is rejected;
        # one border pair remains and stacked intervals stay unhandled.
        comb = cmds([(0, 0), (0, 10), (4, 10), (4, 6), (1, 6), (1, 4),
                     (4, 4), (4, 0)])
        recognition = ro.recognize(ro.parse_commands(comb))
        self.assertEqual(len(recognition["pairs"]), 1)
        self.assertAlmostEqual(recognition["pairs"][0]["width"], 1.0)


class LimitationTests(unittest.TestCase):
    def test_sixteen_applies_inside_movement_bound(self):
        # The head keeps its interior dominance intervals while flank
        # spans touching the closing edge stay rejected. The candidate
        # restores contrast inside half the narrowest retained 2r with
        # strictly decreased weighted width-coupling cost.
        if not CAPTURES.exists():
            self.skipTest("capture data absent")
        source, fitted = records(16)
        result = ro.run_glyph(source, fitted, 16,
                              geometry_reference="upstream")
        self.assertTrue(result["applied"], result.get("reason"))
        self.assertLessEqual(result["movement"], result["bound"])
        self.assertLess(result["cost_candidate"], result["cost_upstream"])
        for key in ("signs", "crossings", "containment"):
            self.assertTrue(result["validity"][key])
        anchor = result["anchor"]
        self.assertAlmostEqual(anchor["ws"], 1.5, places=3)
        self.assertTrue(anchor["intervals"])
        head = result["widths"][0]
        self.assertLess(head["candidate_rounded"], head["wf_upstream"])
        self.assertTrue(result["pairs"][0]["intervals"])
        self.assertTrue(result["pairs"][0]["stations"])
        dropped = [s for s in result["pairs"][0]["spans"] if not s["kept"]]
        self.assertTrue(dropped)
        assert_fixed_contract(self, result, source, fitted)

    def test_flank_span_rejects_adjacent_end_cap(self):
        # Clearance holds against every other border, including an
        # adjacent cap sharing a pair vertex. Interior spans stay kept
        # while the corner-pocket span reports its third contact.
        source = cmds([(0, 0), (2, 0), (2, 6), (4, 9), (2, 9), (0, 6)])
        parsed = ro.parse_commands(source)
        recognition = ro.recognize(parsed)
        heads = [c for c in recognition["pairs"]
                 if {c["a"]["i0"], c["a"]["i1"],
                     c["b"]["i0"], c["b"]["i1"]} == {2, 3, 4, 5}]
        self.assertEqual(len(heads), 1)
        dom = heads[0]["dom"]
        self.assertTrue(dom["intervals"])
        self.assertTrue(any(s["kept"] for s in dom["spans"]))
        flank = [s for s in dom["spans"] if not s["kept"]]
        self.assertTrue(flank)
        self.assertTrue(all(s["stage"] == "third-contact" for s in flank))
        self.assertIn("edge(0,3)", [s["tag"] for s in flank])

    def test_sizes_behave_deterministically(self):
        # Every size either applies inside all gates or abstains at a
        # known geometric gate; the 16px upstream arm is the fixed head.
        if not CAPTURES.exists():
            self.skipTest("capture data absent")
        for size in range(12, 25):
            source, fitted = records(size)
            for arm in ("upstream", "source"):
                result = ro.run_glyph(source, fitted, size,
                                      geometry_reference=arm)
                if result["applied"]:
                    self.assertLessEqual(result["movement"],
                                         result["bound"], (size, arm))
                    self.assertLess(result["cost_candidate"],
                                    result["cost_upstream"], (size, arm))
                else:
                    self.assertIn(result["reason"],
                                  {"no-cost-decrease",
                                   "station-invalid-related",
                                   "station-invalid-anchor",
                                   "no-rectilinear-anchor",
                                   "ambiguous-pairing"},
                                  (size, arm))
        source, fitted = records(16)
        fixed = ro.run_glyph(source, fitted, 16,
                             geometry_reference="upstream")
        self.assertTrue(fixed["applied"], fixed.get("reason"))


class CouplingTests(unittest.TestCase):
    def test_clean_geometry_follows_anchor_change(self):
        # Tall stem anchor 2->3 (integral); long bar follows +50%.
        source, fitted = tall_stem()
        result = ro.run_glyph(source, fitted, 16,
                              geometry_reference="upstream")
        self.assertTrue(result["applied"], result.get("reason"))
        head = result["anchor"]
        bar = result["widths"][0]
        self.assertAlmostEqual(head["ws"], 2.0, places=3)
        self.assertLess(abs(head["rel"] - 0.5), 1e-9)
        self.assertAlmostEqual(bar["ws"], 2.268, places=3)
        self.assertAlmostEqual(bar["candidate_rounded"], bar["expected"],
                               delta=0.2 * bar["expected"])
        self.assertLessEqual(result["movement"], result["bound"])
        self.assertLess(result["cost_candidate"], result["cost_upstream"])
        for key in ("signs", "crossings", "containment"):
            self.assertTrue(result["validity"][key])
        assert_fixed_contract(self, result, source, fitted)
        out = result["candidate_commands"]
        self.assertEqual([c["op"] for c in out], [c["op"] for c in source])
        for cmd in out:
            for key in ("x", "y"):
                if key in cmd:
                    self.assertEqual(cmd[key] * 64, round(cmd[key] * 64))
                    self.assertEqual(cmd[key + "_bits"], bits(cmd[key]))

    def test_bystander_vertex_stays_bitexact(self):
        # A vertex in no surviving pair is unowned: it keeps exact
        # upstream coordinates while only coupled related vertices move.
        # The (0.5, 0) split stays off the stem midline, so no pinned
        # projection poisons the anchor's dominance.
        source = cmds([(0, 0), (0.5, 0), (2, 0), (2, 12), (10, 12),
                       (10, 14.5), (0, 14)])
        fitted = cmds([(0, 0), (0.5, 0), (3, 0), (3, 12), (10, 12),
                       (10, 14.5), (0, 14)])
        result = ro.run_glyph(source, fitted, 16,
                              geometry_reference="upstream")
        self.assertTrue(result["applied"], result.get("reason"))
        self.assertLessEqual(result["movement"], result["bound"])
        self.assertLess(result["cost_candidate"], result["cost_upstream"])
        for key in ("signs", "crossings", "containment"):
            self.assertTrue(result["validity"][key])
        assert_fixed_contract(self, result, source, fitted)
        # Vertex 1 is the bystander: in no anchor or related edge.
        self.assertIn(1, result["fixed"])
        fitted_coords = ro._oncurve_coords(fitted)
        cand = [(c["x"], c["y"]) for c in result["candidate_commands"]
                if c["op"] in ("move_to", "line_to")]
        self.assertEqual(tuple(cand[1]),
                         (fitted_coords[1][0], fitted_coords[1][1]))

    def test_rotation_abstains_outside_rectilinear_slice(self):
        source, fitted = tall_stem()
        angle = math.radians(30)

        def xf(command_list):
            out = []
            for cmd in command_list:
                cmd = dict(cmd)
                for xk, yk in (("x", "y"), ("x1", "y1"), ("x2", "y2")):
                    if xk in cmd:
                        x, y = cmd[xk], cmd[yk]
                        cmd[xk] = (x * math.cos(angle) - y * math.sin(angle))
                        cmd[yk] = (x * math.sin(angle) + y * math.cos(angle))
                out.append(cmd)
            return out
        result = ro.run_glyph(xf(source), xf(fitted), 16,
                              geometry_reference="upstream")
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "no-rectilinear-anchor")

    def test_scale_and_translate_preserve_ratio(self):
        source, fitted = tall_stem()

        def xf(command_list):
            out = []
            for cmd in command_list:
                cmd = dict(cmd)
                for xk, yk in (("x", "y"), ("x1", "y1"), ("x2", "y2")):
                    if xk in cmd:
                        cmd[xk] = cmd[xk] * 2 + 3.0
                        cmd[yk] = cmd[yk] * 2 - 1.0
                out.append(cmd)
            return out
        result = ro.run_glyph(xf(source), xf(fitted), 16,
                              geometry_reference="upstream")
        self.assertTrue(result["applied"], result.get("reason"))
        bar = result["widths"][0]
        self.assertAlmostEqual(bar["candidate_rounded"], bar["expected"],
                               delta=0.2 * bar["expected"])

    def test_bits_convention_matches_captures(self):
        # Float32 bit patterns recomputed from floats equal the records.
        if not CAPTURES.exists():
            self.skipTest("capture data absent")
        for size in (12, 16, 24):
            source, fitted = records(size)
            for command in source + fitted:
                for key in ("x", "y", "x1", "y1", "x2", "y2"):
                    if key in command:
                        self.assertEqual(command[key + "_bits"],
                                         bits(command[key]))

    def test_station_count_must_be_positive(self):
        source, fitted = tall_stem()
        with self.assertRaises(ValueError):
            ro.run_glyph(source, fitted, 16, stations=0)
        with self.assertRaises(ValueError):
            ro.run_glyph(source, fitted, 16, geometry_reference="diagonal")


class IntervalsTests(unittest.TestCase):
    def test_parallel_closed_form(self):
        # Hobby (3.2): the bisector of opposed parallels is the
        # midpoint line, so width is twice the radius everywhere.
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (10.0, 0.0))
        b = ((0.0, 2.0), (10.0, 2.0))
        loop = [(0, 0), (10, 0), (10, 2), (0, 2)]
        out = iv.dominance(a, b, [], [loop])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(len(out["intervals"]), 1)
        span = out["intervals"][0]
        self.assertAlmostEqual(span["lo"], 0.0)
        self.assertAlmostEqual(span["hi"], 10.0)
        self.assertAlmostEqual(span["speed"], 1.0)
        hit = iv.contact(a, b, 5.0, [], [loop])
        self.assertEqual(hit["stage"], "clear")
        self.assertAlmostEqual(hit["hit"]["r"], 1.0)
        self.assertAlmostEqual(hit["hit"]["width"], 2.0)
        self.assertEqual(hit["hit"]["center"], (5.0, 1.0))

    def test_translation_invariance(self):
        # Canonical f over translated coordinates: the verdict and
        # the shifted intervals match exactly.
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (10.0, 0.0))
        b = ((0.0, 2.0), (10.0, 2.0))
        loop = [(0, 0), (10, 0), (10, 2), (0, 2)]
        shift = (1000.0, -500.0)
        mv = lambda p: (p[0] + shift[0], p[1] + shift[1])
        a2 = (mv(a[0]), mv(a[1]))
        b2 = (mv(b[0]), mv(b[1]))
        out = iv.dominance(a2, b2, [], [[mv(p) for p in loop]])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(len(out["intervals"]), 1)
        span = out["intervals"][0]
        self.assertAlmostEqual(span["lo"], 1000.0)
        self.assertAlmostEqual(span["hi"], 1010.0)
        self.assertAlmostEqual(span["speed"], 1.0)

    def test_scale_invariance(self):
        # Uniform scaling scales intervals and radii, never verdicts.
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (10.0, 0.0))
        b = ((0.0, 2.0), (10.0, 2.0))
        out = iv.dominance(a, b, [], None)
        k = 2.5
        sc = lambda p: (p[0] * k, p[1] * k)
        out2 = iv.dominance((sc(a[0]), sc(a[1])),
                               (sc(b[0]), sc(b[1])), [], None)
        self.assertEqual(out2["status"], out["status"])
        self.assertEqual(len(out2["intervals"]), len(out["intervals"]))
        for s0, s1 in zip(out["intervals"], out2["intervals"]):
            self.assertAlmostEqual(s1["lo"], k * s0["lo"])
            self.assertAlmostEqual(s1["hi"], k * s0["hi"])
            self.assertAlmostEqual(s1["speed"], s0["speed"])

    def test_bisector_property_on_taper(self):
        # Every reported contact is equidistant: width is 2r, not the
        # chord between the feet.
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (8.0, 0.0))
        b = ((0.0, 1.3), (8.0, 1.1))
        out = iv.dominance(a, b, [], None)
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["intervals"])
        for span in out["intervals"]:
            mid = (span["lo"] + span["hi"]) / 2
            hit = iv.contact(a, b, mid, [], None)
            self.assertEqual(hit["stage"], "clear")
            c, r = hit["hit"]["center"], hit["hit"]["r"]
            self.assertGreater(r, 0)
            for q in (hit["hit"]["qa"], hit["hit"]["qb"]):
                self.assertAlmostEqual(math.dist(c, q), r, places=9)
            self.assertAlmostEqual(hit["hit"]["width"], 2 * r)

    def test_taper_hands_off_at_endpoint_foot(self):
        # Vertex-dominated cells are unsupported: dominance ends where
        # a foot reaches a segment endpoint.
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (8.0, 0.0))
        b = ((0.0, 1.3), (8.0, 1.1))
        out = iv.dominance(a, b, [], None)
        self.assertEqual(out["status"], "ok")
        self.assertLess(out["intervals"][-1]["hi"], 8.0)
        self.assertEqual(out["spans"][-1]["stage"], "endpoint-foot-b")

    def test_adjacent_cap_rejects(self):
        # Clearance holds against every other segment: caps whose
        # pocket the disk touches disqualify the span.
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (0.0, 1.5))
        b = ((2.0, 0.0), (2.0, 1.5))
        caps = [{"seg": ((0.0, 0.0), (2.0, 0.0)), "tag": "cap0"},
                {"seg": ((0.0, 1.5), (2.0, 1.5)), "tag": "cap1"}]
        loop = [(0, 0), (2, 0), (2, 1.5), (0, 1.5)]
        out = iv.dominance(a, b, caps, [loop])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["intervals"], [])
        self.assertTrue(out["spans"])
        for span in out["spans"]:
            self.assertEqual(span["stage"], "third-contact")
            self.assertIn(span["tag"], ("cap0", "cap1"))

    def test_corner_pruned_by_opposition(self):
        # Hobby (3.2) Figure 18b: pairs opposed by less than 157
        # degrees are corner branches, not strokes.
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (4.0, 0.0))
        b = ((0.0, 3.0), (2.0, 1.0))
        out = iv.dominance(a, b, [], None)
        self.assertEqual(out["status"], "opposition-pruned")
        self.assertGreater(out["opp"], math.cos(math.radians(157.0)))

    def test_bisector_singularity_bands(self):
        # Exact zero determinant is degenerate; the noise band is
        # uncertain. Neither may produce coefficients.
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (10.0, 0.0))
        b = ((0.0, 2.0), (10.0, 2.0))
        cor = iv.corridor(a, b)
        exact = dict(cor, u=(cor["d"][0], cor["d"][1]))
        self.assertEqual(iv.frame(a, b, exact)["status"],
                         "degenerate-bisector")
        ux = cor["u"]
        tiny = 1e-10
        bad = (cor["d"][0] + tiny * ux[0], cor["d"][1] + tiny * ux[1])
        norm = math.hypot(*bad)
        near = dict(cor, u=(bad[0] / norm, bad[1] / norm))
        self.assertEqual(iv.frame(a, b, near)["status"],
                         "uncertain-bisector")

    def test_disjoint_pair_has_no_overlap(self):
        import experiments.hobby_fitting.intervals as iv
        a = ((0.0, 0.0), (1.0, 0.0))
        b = ((5.0, 0.0), (6.0, 0.0))
        out = iv.dominance(a, b, [], None)
        self.assertEqual(out["status"], "no-overlap")
        hit = iv.contact(a, b, 3.0, [], None)
        self.assertEqual(hit["stage"], "outside-overlap")

    def test_head_like_taper_off_origin(self):
        # Synthetic head analog at capture-like coordinates: a valid
        # open pair with positive radius must exist before coupling.
        import experiments.hobby_fitting.intervals as iv
        ox, oy = 100.0, 50.0
        a = ((ox, oy), (ox + 8.0, oy))
        b = ((ox, oy + 1.3), (ox + 8.0, oy + 1.1))
        out = iv.dominance(a, b, [], None)
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["intervals"])
        self.assertAlmostEqual(out["speed"], 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
