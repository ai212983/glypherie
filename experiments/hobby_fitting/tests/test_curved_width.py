import struct
import unittest

from experiments.hobby_fitting import curved_width as cw


def _mv(p):
    return {"op": "move_to", "x": p[0], "y": p[1]}


def _qu(c, p):
    return {"op": "quad_to", "x1": c[0], "y1": c[1], "x": p[0], "y": p[1]}


def _ln(p):
    return {"op": "line_to", "x": p[0], "y": p[1]}


def _bits(cmds):
    for c in cmds:
        for key in ("x", "y", "x1", "y1", "x2", "y2"):
            if key in c:
                c[key + "_bits"] = struct.unpack(">I", struct.pack(">f", c[key]))[0]
    return cmds


def lens(dx=0.0):
    """Closed lens: two opposing diagonal quads, exact medial x-offset."""
    a0, ca, a1 = (0.0, 0.0), (0.5, 1.0), (2.0, 2.0)
    b0 = (a1[0] + 1.5, a1[1])
    cb = (ca[0] + 1.5, ca[1])
    b1 = (a0[0] + 1.5, a0[1])
    cmds = [_mv(a0), _qu(ca, a1), _ln(b0), _qu(cb, b1), {"op": "close"}]
    if dx:
        for c in cmds:
            for key in ("x", "x1"):
                if key in c:
                    c[key] += dx
    return _bits(cmds)


def lens_pair(width=1.5, dx=0.1):
    t = 0.5
    base = [(0.0, 0.0), (2.0, 2.0), (3.5, 2.0), (1.5, 0.0),
            (0.5, 1.0), (2.0, 1.0)]
    pa = cw._eval([base[0], base[4], base[1]], t)
    pb = cw._eval([base[2], base[5], base[3]], t)
    medial = list((pa + pb) / 2)
    return [{"a_ctrl": [0, 4, 1], "b_ctrl": [2, 5, 3], "a_t": t, "b_t": t,
             "medial": medial, "arc": 2.0}]


def bar():
    """Closed bar: opposing horizontal quads, vertical thickness."""
    cmds = [_mv((0.0, 2.0)), _qu((2.0, 3.0), (4.0, 2.0)), _ln((4.0, 0.0)),
            _qu((2.0, -1.0), (0.0, 0.0)), {"op": "close"}]
    return _bits(cmds)


def bar_pair():
    return [{"a_ctrl": [0, 4, 1], "b_ctrl": [2, 5, 3], "a_t": 0.5,
             "b_t": 0.5, "medial": [2.0, 1.0], "arc": 2.0}]


REF = {"anchors": [{"source_width": 1.5, "fitted_width": 1.0,
                    "rel": -1.0 / 3.0, "length": 9.875,
                    "tangent": [0.0, 1.0]}],
       "size_px": 16.0}


class CurvedWidthTests(unittest.TestCase):

    def test_moved_joins_reject_kinked_candidate(self):
        # Negative control: width coupling moves join controls, which
        # rotates join legs; the exact tangent gate must refuse to
        # publish the kinked candidate and return upstream exactly.
        src, up, pairs = lens(), lens(dx=0.1), lens_pair()
        out = cw.fit(src, up, 16.0, REF, (False, True), pairs)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "tangent-join-changed")
        self.assertIs(out["candidate_commands"], up)

    def test_join_gate_units(self):
        parsed = {"oncurve": [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0)],
                  "offcurve": [(2.0, 0.0)],
                  "contours": [[("quad", 0, 0, 1),
                                ("line", 1, 2)]]}
        base = parsed["oncurve"] + parsed["offcurve"]
        flags = [False]
        kinked = [list(p) for p in base]
        kinked[1] = (4.0, 0.5)
        self.assertFalse(cw._joins_preserved(parsed, base, kinked, flags))
        same = [list(p) for p in base]
        self.assertTrue(cw._joins_preserved(parsed, base, same, flags))
        moved_along = [list(p) for p in base]
        moved_along[3] = (3.0, 0.0)
        self.assertTrue(cw._joins_preserved(parsed, base, moved_along,
                                            flags))

    def test_bits_refreshed_to_f32(self):
        from experiments.hobby_fitting.real_outline import parse_commands
        up = lens()
        parsed = parse_commands(up)
        no = len(parsed["oncurve"])
        cand = [list(p) for p in parsed["oncurve"] + parsed["offcurve"]]
        cand[no][0] += 1.0 / 64.0
        out = cw._emit(up, cand, no)
        for c in out:
            for key in ("x", "y", "x1", "y1"):
                if key in c and key + "_bits" in c:
                    self.assertEqual(
                        c[key + "_bits"],
                        struct.unpack(">I", struct.pack(">f", c[key]))[0])
        self.assertEqual(out[1]["x1"], up[1]["x1"] + 1.0 / 64.0)

    def test_horizontal_walls_ineffectible_in_x(self):
        src, up, pairs = bar(), bar(), bar_pair()
        out = cw.fit(src, up, 16.0, REF, (False, True), pairs)
        for before, after in zip(up, out["candidate_commands"]):
            for key in ("y", "y1"):
                if key in before:
                    self.assertEqual(before[key], after[key])
        if out["applied"]:
            w = out["widths"][0]
            self.assertLess(abs(w["candidate"] - w["upstream"]), 1e-6)

    def test_unequal_medial_radii_abstains_exact(self):
        src, up, pairs = lens(), lens(dx=0.1), lens_pair()
        pairs[0]["medial"] = [pairs[0]["medial"][0] + 0.25,
                              pairs[0]["medial"][1]]
        out = cw.fit(src, up, 16.0, REF, (False, True), pairs)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "unequal-medial-radii")
        self.assertIs(out["candidate_commands"], up)

    def test_mismatched_commands_abstain_exact(self):
        src, up, pairs = lens(), lens(dx=0.1), lens_pair()
        bad = [dict(c) for c in up]
        bad[1] = {"op": "line_to", "x": 0.0, "y": 0.0}
        out = cw.fit(src, bad, 16.0, REF, (False, True), pairs)
        self.assertFalse(out["applied"])
        self.assertIs(out["candidate_commands"], bad)

    def test_no_pairs_abstains(self):
        src, up = lens(), lens(dx=0.1)
        out = cw.fit(src, up, 16.0, REF, (False, True), [])
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "no-supplied-pairs")

    def test_all_axes_native_abstains(self):
        src, up, pairs = lens(), lens(dx=0.1), lens_pair()
        out = cw.fit(src, up, 16.0, REF, (True, True), pairs)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "all-axes-native")

    def test_malformed_native_axes_abstains(self):
        src, up, pairs = lens(), lens(dx=0.1), lens_pair()
        for bad_axes in ((0, 1), "xy", (True,), (True, True, False)):
            out = cw.fit(src, up, 16.0, REF, bad_axes, pairs)
            self.assertFalse(out["applied"], bad_axes)
            self.assertEqual(out["reason"], "malformed-native-axes")
            self.assertIs(out["candidate_commands"], up)

    def test_quad_interval_curvature_gate(self):
        src = [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)]
        flipped = [(0.0, 0.0), (1.0, -1.0), (2.0, 0.0)]
        ok, why = cw._quad_interval_ok(src, flipped)
        self.assertFalse(ok)
        self.assertEqual(why, "curvature-sign")

    def test_quad_interval_tangent_gate(self):
        src = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        cand = [(0.0, 0.0), (1.0, -0.1), (1.0, 1.0)]
        ok, why = cw._quad_interval_ok(src, cand)
        self.assertFalse(ok)
        self.assertEqual(why, "tangent-reversed")

    def test_rigid_translation_is_identity(self):
        rel0 = {"anchors": [dict(REF["anchors"][0], rel=0.0,
                                 fitted_width=1.5)],
                "size_px": 16.0}
        src, _, pairs = lens(), lens(dx=0.1), lens_pair()
        up = lens(dx=0.375)
        out = cw.fit(src, up, 16.0, rel0, (False, True), pairs)
        self.assertTrue(out["applied"], out["reason"])
        self.assertEqual(out["candidate_commands"], up)
        self.assertEqual(out["reason"], "fitted")

    def test_achieved_anchor_is_identity(self):
        rel0 = {"anchors": [dict(REF["anchors"][0], rel=0.0,
                                 fitted_width=1.5)],
                "size_px": 16.0}
        src, up, pairs = lens(), lens(), lens_pair()
        out = cw.fit(src, up, 16.0, rel0, (False, True), pairs)
        self.assertTrue(out["applied"], out["reason"])
        self.assertEqual(out["candidate_commands"], up)

    def test_native_y_pin_no_x_drift(self):
        src, up, pairs = bar(), bar(), bar_pair()
        out = cw.fit(src, up, 16.0, REF, (False, True), pairs)
        for before, after in zip(up, out["candidate_commands"]):
            self.assertEqual(before, after)

    def test_measure_contacts_finds_opposition(self):
        m = cw.measure_contacts(lens())
        self.assertGreaterEqual(m["summary"]["n_measured"], 1)
        for c in m["contacts"]:
            self.assertLess(c["antiparallel_dot"], 0.0)


if __name__ == "__main__":
    unittest.main()
