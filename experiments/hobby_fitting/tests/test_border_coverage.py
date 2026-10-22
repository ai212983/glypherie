"""Border-interval ownership: shared borders at interval resolution.

Hobby 3.2 owns each medial point by its nearest sites, so adjacent
branches hand off at shared boundary events; whole-portion ambiguity
is coarser than that evidence. Interval ownership keeps disjoint
contact-foot subranges and drops provable overlap, with arithmetic
touch failing closed. Reference discovery keeps portion ownership,
so frozen anchors cannot move with this slice. No pixel counts.
"""

import unittest

from experiments.hobby_fitting import direct_diagonal as dd
from experiments.hobby_fitting import intervals
from experiments.hobby_fitting import real_outline


def _portion(contour, seg, p0, p1):
    return {"contour": contour, "seg": seg, "t0": 0.0, "t1": 1.0,
            "p0": p0, "p1": p1, "i0": 0, "i1": 1}


def _dom(a, b):
    return intervals.dominance((tuple(a["p0"]), tuple(a["p1"])),
                               (tuple(b["p0"]), tuple(b["p1"])),
                               [], None)


def _combos(shared, others):
    return [{"a": shared, "b": b, "dom": _dom(shared, b)}
            for b in others]


def _borders(portions):
    out = []
    for p in portions:
        key = (p["contour"], p["seg"], p["t0"], p["t1"])
        out.append({"seg": (tuple(p["p0"]), tuple(p["p1"])),
                    "tag": "edge(%d,%d,%.6f,%.6f)" % key, "key": key})
    return out


def _resolve(portions, combos):
    return dd._resolve_interval(combos, [], _borders(portions), None)


class FootRangeTests(unittest.TestCase):
    def test_affine_ranges_bound_station_feet(self):
        # Feet are affine in corridor-t, so endpoint evaluation bounds
        # every interior station foot on both sides.
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 100, "y": 100},
               {"op": "line_to", "x": 114, "y": 100},
               {"op": "line_to", "x": 14, "y": 0},
               {"op": "close"}]
        parsed = real_outline.parse_commands(src)
        portions, _, loops, _ = dd._split_visible(parsed)
        pairs, _ = dd._recognize(portions, loops,
                                 ownership="interval")
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]
        seg_a = (tuple(pair["a"]["p0"]), tuple(pair["a"]["p1"]))
        seg_b = (tuple(pair["b"]["p0"]), tuple(pair["b"]["p1"]))
        borders = dd._visible_borders(portions)
        stations = dd._station_contacts(
            seg_a, seg_b, pair["dom"],
            [o for o in borders
             if o["key"] != (pair["a"]["contour"], pair["a"]["seg"],
                             pair["a"]["t0"], pair["a"]["t1"])
             and o["key"] != (pair["b"]["contour"], pair["b"]["seg"],
                              pair["b"]["t0"], pair["b"]["t1"])],
            loops)
        self.assertIsNotNone(stations)
        for side, key in (("a", "sa"), ("b", "sb")):
            lo = min(r[side][0] for r in pair["feet"])
            hi = max(r[side][1] for r in pair["feet"])
            self.assertLess(lo, hi)
            for st in stations:
                self.assertLessEqual(lo, st["hit"][key])
                self.assertLessEqual(st["hit"][key], hi)

    def test_degenerate_kept_fails_closed(self):
        # Empty kept input yields no ranges rather than a guess.
        self.assertEqual(
            intervals.foot_ranges(((0.0, 0.0), (0.0, 100.0)),
                                  ((10.0, 0.0), (10.0, 100.0)), []),
            [])


class ConflictTests(unittest.TestCase):
    def test_strict_overlap_or_touch_conflicts(self):
        # After trimming, any remaining contact between certified
        # cores is claimed shared ownership: overlap and exact touch
        # both fail closed, and only a strict gap keeps.
        self.assertTrue(dd._strict_overlap((0.0, 0.6), (0.4, 1.0)))
        self.assertTrue(dd._strict_overlap((0.0, 0.5), (0.5, 1.0)))
        self.assertFalse(dd._strict_overlap((0.0, 0.4), (0.6, 1.0)))

    def test_sub_band_real_overlap_conflicts(self):
        # A real overlap below the arithmetic band is still double
        # ownership: comparison never erodes ranges to hide it.
        self.assertTrue(dd._strict_overlap((0.0, 0.5),
                                           (0.5 - 1e-10, 1.0)))


class TrimTests(unittest.TestCase):
    def test_core_clips_uncertainty_neighborhoods(self):
        # Each kept end retreats by the module guard over the span;
        # the surviving midpoint is rechecked with full guards.
        seg_a = ((0.0, 0.0), (0.0, 100.0))
        seg_b = ((10.0, 0.0), (10.0, 100.0))
        dom = intervals.dominance(seg_a, seg_b, [], None)
        raw = dom["intervals"]
        self.assertTrue(raw)
        span = max(v["hi"] for v in raw) - min(v["lo"] for v in raw)
        core = intervals.core_intervals(seg_a, seg_b, raw, [], None)
        self.assertEqual(len(core), len(raw))
        trim = intervals.EPS * span
        for kept, kept_core in zip(raw, core):
            self.assertAlmostEqual(kept_core["lo"] - kept["lo"],
                                   trim, delta=1e-12)
            self.assertAlmostEqual(kept["hi"] - kept_core["hi"],
                                   trim, delta=1e-12)

    def test_sub_trim_interval_drops(self):
        # An interval narrower than both uncertainty neighborhoods
        # owns no certifiable core and fails closed.
        seg_a = ((0.0, 0.0), (0.0, 100.0))
        seg_b = ((10.0, 0.0), (10.0, 100.0))
        tiny = [{"lo": 60.0, "hi": 60.0 + 1e-12}]
        self.assertEqual(
            intervals.core_intervals(seg_a, seg_b, tiny, [], None),
            [])

    def test_trimmed_abutment_separates(self):
        # Borders handing off at one shared event keep both combos:
        # the trimmed cores are strictly separated even though the
        # raw foot ranges touch at the boundary event.
        shared = _portion(0, 0, (0.0, 0.0), (0.0, 100.0))
        upper = _portion(1, 0, (10.0, 50.0), (10.0, 100.0))
        lower = _portion(2, 0, (10.0, 0.0), (10.0, 50.0))
        portions = [shared, upper, lower]
        pairs, skipped = _resolve(
            portions, _combos(shared, (upper, lower)))
        self.assertEqual(len(pairs), 2)
        self.assertEqual(skipped, [])
        first = pairs[0]["feet"][0]["a"]
        second = pairs[1]["feet"][0]["a"]
        self.assertTrue(first[1] < second[0]
                        or second[1] < first[0])

    def test_ownership_survives_translation(self):
        # Trim margins and strict verdicts live in normalized space,
        # so translation cannot change ownership decisions.
        def run(dx, dy):
            shift = lambda p: (p[0] + dx, p[1] + dy)
            shared = _portion(0, 0, shift((0.0, 0.0)),
                              shift((0.0, 100.0)))
            upper = _portion(1, 0, shift((10.0, 50.0)),
                             shift((10.0, 100.0)))
            lower = _portion(2, 0, shift((10.0, 0.0)),
                             shift((10.0, 50.0)))
            portions = [shared, upper, lower]
            return _resolve(portions,
                            _combos(shared, (upper, lower)))

        pairs, _ = run(0.0, 0.0)
        moved, _ = run(17.5, -3.25)
        self.assertEqual(len(moved), len(pairs))
        for plain, shifted in zip(pairs, moved):
            for key in ("a", "b"):
                for raw, again in zip(plain["feet"][0][key],
                                      shifted["feet"][0][key]):
                    self.assertAlmostEqual(raw, again, places=6)


class OwnershipTests(unittest.TestCase):
    def test_disjoint_subranges_both_kept(self):
        shared = _portion(0, 0, (0.0, 0.0), (0.0, 100.0))
        upper = _portion(1, 0, (10.0, 60.0), (10.0, 100.0))
        lower = _portion(2, 0, (10.0, 0.0), (10.0, 40.0))
        portions = [shared, upper, lower]
        pairs, skipped = _resolve(
            portions, _combos(shared, (upper, lower)))
        self.assertEqual(len(pairs), 2)
        self.assertEqual(skipped, [])

    def test_grazed_core_abstains_survivor_kept(self):
        # A combo whose disks graze the third border owns no core
        # and abstains, while the clear combo survives: finer than
        # portion ownership, which drops both without looking.
        shared = _portion(0, 0, (0.0, 0.0), (0.0, 100.0))
        wide = _portion(1, 0, (10.0, 60.0), (10.0, 100.0))
        span = _portion(3, 0, (10.0, 5.0), (10.0, 95.0))
        portions = [shared, wide, span]
        pairs, skipped = _resolve(
            portions, _combos(shared, (wide, span)))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["b"]["contour"], 3)
        self.assertEqual([s["reason"] for s in skipped],
                         ["foot-uncertain"])

    def test_overlapping_cores_both_dropped(self):
        # Backstop isolation: with rechecks passing elsewhere,
        # overlapping certified cores still drop both combos rather
        # than assigning one border stretch twice.
        shared = _portion(0, 0, (0.0, 0.0), (0.0, 100.0))
        first = _portion(1, 0, (10.0, 0.0), (10.0, 100.0))
        second = _portion(2, 0, (10.0, 0.0), (10.0, 100.0))
        far = _portion(9, 0, (50.0, 0.0), (50.0, 100.0))
        portions = [shared, first, second, far]

        def combo(side):
            seg_a = (tuple(shared["p0"]), tuple(shared["p1"]))
            seg_b = (tuple(side["p0"]), tuple(side["p1"]))
            dom = intervals.dominance(seg_a, seg_b, [], None)
            dom = dict(dom)
            dom["intervals"] = [{"lo": 20.0, "hi": 80.0}]
            return {"a": shared, "b": side, "dom": dom}

        pairs, skipped = dd._resolve_interval(
            [combo(first), combo(second)], [],
            _borders([shared, far]), None)
        self.assertEqual(pairs, [])
        self.assertEqual([s["reason"] for s in skipped],
                         ["ambiguous-portion"] * 2)

    def test_default_recognition_is_portion_owned(self):
        # build_reference discovery keeps the frozen portion rule:
        # the default call matches it exactly, never interval mode.
        shared = _portion(0, 0, (0.0, 0.0), (0.0, 100.0))
        upper = _portion(1, 0, (10.0, 60.0), (10.0, 100.0))
        lower = _portion(2, 0, (10.0, 0.0), (10.0, 40.0))
        portions = [{"contour": 0, "seg": 0, "t0": 0.0, "t1": 1.0,
                     "p0": (0.0, 0.0), "p1": (0.0, 100.0),
                     "hidden": False, "unknown": False},
                    {"contour": 1, "seg": 0, "t0": 0.0, "t1": 1.0,
                     "p0": (10.0, 60.0), "p1": (10.0, 100.0),
                     "hidden": False, "unknown": False},
                    {"contour": 2, "seg": 0, "t0": 0.0, "t1": 1.0,
                     "p0": (10.0, 0.0), "p1": (10.0, 40.0),
                     "hidden": False, "unknown": False}]
        default, _ = dd._recognize(portions, None)
        explicit, _ = dd._recognize(portions, None,
                                    ownership="portion")
        self.assertEqual(len(default), 0)
        self.assertEqual(len(explicit), 0)
        refined, _ = dd._recognize(portions, None,
                                   ownership="interval")
        self.assertEqual(len(refined), 2)
        self.assertTrue(all("feet" in p for p in refined))


class ReportingTests(unittest.TestCase):
    def test_fit_reports_feet_and_peaks(self):
        # Delivered pairs carry identities, foot intervals, bounds
        # and per-pair movement for coverage review.
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 100, "y": 100},
               {"op": "line_to", "x": 114, "y": 100},
               {"op": "line_to", "x": 14, "y": 0},
               {"op": "close"},
               {"op": "move_to", "x": 140, "y": 0},
               {"op": "line_to", "x": 150, "y": 0},
               {"op": "line_to", "x": 150, "y": 100},
               {"op": "line_to", "x": 140, "y": 100},
               {"op": "close"}]
        fit = [dict(c) for c in src]
        for c in fit:
            if c.get("x") == 150:
                c["x"] = 149.0
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False),
                            False)
        self.assertTrue(out["applied"], out["reason"])
        self.assertEqual(len(out["pairs"]), 1)
        pair = out["pairs"][0]
        self.assertIn("feet", pair)
        self.assertIn("peak", pair)
        self.assertIn("bound", pair)
        self.assertLessEqual(pair["peak"], pair["bound"])


def cross_rect():
    """Rectangle crossed by a triangle leg at exactly (50, 0)."""
    return [{"op": "move_to", "x": 0, "y": 0},
            {"op": "line_to", "x": 100, "y": 0},
            {"op": "line_to", "x": 100, "y": 100},
            {"op": "line_to", "x": 0, "y": 100},
            {"op": "close"},
            {"op": "move_to", "x": 50, "y": -50},
            {"op": "line_to", "x": 50, "y": 50},
            {"op": "line_to", "x": 150, "y": 50},
            {"op": "close"}]


class CanonicalDiscoveryTests(unittest.TestCase):
    def test_shared_crossing_single_identity(self):
        # One geometric crossing yields bit-identical portion
        # endpoints on both edges, so normalized coincidence is
        # exact rather than tolerance-merged.
        parsed = real_outline.parse_commands(cross_rect())
        portions, _, _, _ = dd._split_visible(parsed, canonical=True)
        bottoms = [p for p in portions
                   if p["contour"] == 0 and p["seg"] == 0]
        legs = [p for p in portions
                if p["contour"] == 1 and p["seg"] == 0]
        self.assertEqual(len(bottoms), 2)
        self.assertEqual(len(legs), 2)
        joint = bottoms[0]["p1"]
        self.assertEqual(joint, bottoms[1]["p0"])
        self.assertEqual(joint, legs[0]["p1"])
        self.assertEqual(joint, legs[1]["p0"])
        self.assertEqual(joint, (50.0, 0.0))

    def test_legacy_default_preserved(self):
        # Cut-free input discovers identical portions either way;
        # the default call keeps legacy float discovery exactly.
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 100, "y": 100},
               {"op": "line_to", "x": 114, "y": 100},
               {"op": "line_to", "x": 14, "y": 0},
               {"op": "close"}]
        parsed = real_outline.parse_commands(src)
        legacy, _, _, _ = dd._split_visible(parsed)
        explicit, _, _, _ = dd._split_visible(parsed, canonical=False)
        canon, _, _, _ = dd._split_visible(parsed, canonical=True)
        for old, same in zip(legacy, explicit):
            self.assertEqual(old["p0"], same["p0"])
            self.assertEqual(old["p1"], same["p1"])
        for old, new in zip(legacy, canon):
            self.assertEqual(old["p0"], new["p0"])
            self.assertEqual(old["p1"], new["p1"])

    def test_site_permutation_invariance(self):
        # Edge input order cannot change canonical sites: identity
        # is geometric, never positional.
        parsed = real_outline.parse_commands(cross_rect())
        oncurve = parsed["oncurve"]
        edges = []
        for ci, contour in enumerate(parsed["contours"]):
            for si, seg in enumerate(contour):
                if seg[0] == "line":
                    edges.append({"contour": ci, "seg": si,
                                  "p0": oncurve[seg[1]],
                                  "p1": oncurve[seg[2]]})
        forward = dd._exact_cut_sites(edges)
        backward = dd._exact_cut_sites(list(reversed(edges)))

        def keyed(sites, order):
            out = {}
            for pos, edge in enumerate(order):
                key = (edge["contour"], edge["seg"])
                out[key] = sorted(
                    (float(t), pt) for t, pt in sites[pos].items())
            return out

        self.assertEqual(keyed(forward, edges),
                         keyed(backward, list(reversed(edges))))

    def test_nearby_distinct_vertices_stay_distinct(self):
        # Crossings 0.01 apart are unrelated sites, never merged.
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 100, "y": 0},
               {"op": "line_to", "x": 100, "y": 100},
               {"op": "line_to", "x": 0, "y": 100},
               {"op": "close"},
               {"op": "move_to", "x": 50, "y": -50},
               {"op": "line_to", "x": 50, "y": 50},
               {"op": "line_to", "x": 50.01, "y": 50},
               {"op": "line_to", "x": 50.01, "y": -50},
               {"op": "close"}]
        parsed = real_outline.parse_commands(src)
        portions, _, _, _ = dd._split_visible(parsed, canonical=True)
        bottoms = sorted(
            (p for p in portions
             if p["contour"] == 0 and p["seg"] == 0),
            key=lambda p: p["t0"])
        self.assertEqual(len(bottoms), 3)
        cuts = [bottoms[0]["p1"], bottoms[1]["p1"]]
        self.assertNotEqual(cuts[0], cuts[1])
        self.assertEqual(cuts[0], (50.0, 0.0))
        self.assertEqual(len({bottoms[0]["p1"], bottoms[1]["p0"],
                              bottoms[1]["p1"], bottoms[2]["p0"]}), 2)

    def test_reflection_and_scaling_keep_decisions(self):
        # Ownership verdicts and foot fractions are geometric, so
        # reflection and uniform scaling preserve them.
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 100, "y": 100},
               {"op": "line_to", "x": 114, "y": 100},
               {"op": "line_to", "x": 14, "y": 0},
               {"op": "close"}]

        def run(cmds):
            parsed = real_outline.parse_commands(cmds)
            portions, _, loops, _ = dd._split_visible(
                parsed, canonical=True)
            return dd._recognize(portions, loops,
                                 ownership="interval")[0]

        def mapped(cmds, fn):
            out = []
            for c in cmds:
                c = dict(c)
                for k in ("x", "x1", "x2", "y", "y1", "y2"):
                    if k in c:
                        c[k] = fn(c[k])
                out.append(c)
            return out

        base = run(src)
        mirrored = run(mapped(src, lambda v: -v))
        scaled = run(mapped(src, lambda v: 2.5 * v))
        self.assertEqual(len(base), 1)
        for other in (mirrored, scaled):
            self.assertEqual(len(other), 1)
            for key in ("a", "b"):
                for plain, again in zip(base[0]["feet"][0][key],
                                        other[0]["feet"][0][key]):
                    self.assertAlmostEqual(plain, again, places=6)


def bar_with_curve(curve, stem_fit=9.0):
    """Slanted bar plus fitted upright stem plus one curve contour."""
    src = [{"op": "move_to", "x": 0, "y": 0},
           {"op": "line_to", "x": 100, "y": 100},
           {"op": "line_to", "x": 114, "y": 100},
           {"op": "line_to", "x": 14, "y": 0},
           {"op": "close"},
           {"op": "move_to", "x": 140, "y": 0},
           {"op": "line_to", "x": 150, "y": 0},
           {"op": "line_to", "x": 150, "y": 100},
           {"op": "line_to", "x": 140, "y": 100},
           {"op": "close"}]
    if curve:
        src = src + curve
    fit = [dict(c) for c in src]
    for c in fit:
        if c.get("x") == 150:
            c["x"] = 150 - (150 - stem_fit)
    return src, fit


def stub_topology(source, fitted, candidate):
    """Harness-supplied curve wrapper stand-in: topology ok."""
    return {"supported": True, "ok": True, "reason": "stub"}


class CurveNeighborTests(unittest.TestCase):
    def test_distant_curve_applies(self):
        curve = [{"op": "move_to", "x": 0, "y": -30},
                 {"op": "quad_to", "x1": 50, "y1": -25,
                  "x": 100, "y": -30},
                 {"op": "close"}]
        src, fit = bar_with_curve(curve)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False),
                            False, topology_checker=stub_topology,
                            curve_clearance=True)
        self.assertTrue(out["applied"], out.get("reason"))
        self.assertEqual(len(out["pairs"]), 1)

    def test_curve_in_station_disk_abstains(self):
        # A lens hole around station two overlaps its medial disk,
        # so the pair owns no certified core and the glyph stays.
        lens = [{"op": "move_to", "x": 52, "y": 48},
                {"op": "quad_to", "x1": 57, "y1": 55,
                 "x": 62, "y": 48},
                {"op": "quad_to", "x1": 57, "y1": 41,
                 "x": 52, "y": 48},
                {"op": "close"}]
        src, fit = bar_with_curve(lens)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False),
                            False, topology_checker=stub_topology,
                            curve_clearance=True)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "all-abstained")
        self.assertIn("curved-neighbor",
                      [s["reason"] for s in out["skipped"]])

    def test_sweep_into_curve_rejected(self):
        # Station disks clear, but the solved motion drives borders
        # into the curve: the swept homotopy gate rejects it.
        curve = [{"op": "move_to", "x": 0, "y": 40},
                 {"op": "quad_to", "x1": 50, "y1": 45,
                  "x": 100, "y": 40},
                 {"op": "close"}]
        src, fit = bar_with_curve(curve)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False),
                            False, topology_checker=stub_topology,
                            curve_clearance=True)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "invalid-candidate")
        self.assertEqual(out["validity"]["stage"], "curve-contact")

    def test_sweep_uses_fitted_curves(self):
        # The sweep runs upstream to candidate, so it must certify
        # against the fitted fixed curves: a collision present only
        # in fitted geometry rejects, while the source-geometry sweep
        # over the same candidate clears.
        far = [{"op": "move_to", "x": 0, "y": -30},
               {"op": "quad_to", "x1": 50, "y1": -25,
                "x": 100, "y": -30},
               {"op": "close"}]
        near = [{"op": "move_to", "x": 0, "y": 40},
                {"op": "quad_to", "x1": 50, "y1": 45,
                 "x": 100, "y": 40},
                {"op": "close"}]
        src, fit = bar_with_curve(far)
        fitted_only = fit[:-3] + near
        ref = dd.build_reference(
            [{"source_commands": src, "fitted_commands": fitted_only}],
            16.0)
        out = dd.fit_glyph(src, fitted_only, 16.0, ref,
                            (False, False), False,
                            topology_checker=stub_topology,
                            curve_clearance=True)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "invalid-candidate")
        self.assertEqual(out["validity"]["stage"], "curve-contact")
        candidate = out["attempt"]["attempted_commands"]
        parsed = real_outline.parse_commands(src)
        fitted = real_outline.parse_commands(fitted_only)
        ok, _ = dd._curve_sweep_ok(parsed, fitted, candidate,
                                   dd._curve_controls(parsed))
        self.assertTrue(ok)

    def test_curve_mode_needs_topology_wrapper(self):
        # No sampled fallback: without a curve-capable checker the
        # mode abstains instead of guessing topology.
        src, fit = bar_with_curve(None)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False),
                            False, curve_clearance=True)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "no-curve-topology")


if __name__ == "__main__":
    unittest.main()
