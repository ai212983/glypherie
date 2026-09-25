"""Focused checks for the shared stem-width table (CVT analogue)."""
import math
import unittest

import stem_width_table as T


def entry(char, width_units, index=0):
    return (char, index, width_units)


class ClusterTests(unittest.TestCase):
    def test_one_design_stem_forms_one_cluster(self):
        clusters = T.cluster_widths([entry('T', 190.0), entry('H', 193.0),
                                     entry('H', 192.0), entry('n', 185.0),
                                     entry('n', 186.0)])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 5)

    def test_distant_widths_split(self):
        clusters = T.cluster_widths([entry('a', 190.0), entry('b', 376.0)])
        self.assertEqual(len(clusters), 2)


class CapAnchorTests(unittest.TestCase):
    def maxima(self):
        # Roboto y-maximum modes: caps 1456u, figure overshoots
        # 1476/1477u, ascenders 1536/1557u, x-height 1165u.
        return {1456: 123, 1476: 35, 1477: 17, 1536: 25, 1557: 10,
                1165: 76}

    def test_cap_grid_matches_native(self):
        # No scalar rounding rule fits all four native cap rows
        # (10/12/13/14 at .09/.375/.797/.219 fractions); the voted
        # class does: unanimous everywhere except 16px, where the
        # overshoot members straddle and snap outward.
        for size, want in ((14, 10), (16, 12), (18, 13), (20, 14)):
            anchor = T.vote_cap_anchor(self.maxima(), size, 2048)
            self.assertEqual(anchor['mode_units'], 1456)
            self.assertEqual(anchor['target_px'], want)

    def test_ascenders_do_not_move_target(self):
        plain = T.vote_cap_anchor({1456: 123, 1476: 35, 1477: 17},
                                  16, 2048)
        self.assertEqual(plain['target_px'], 12)
        self.assertEqual(plain['members'], 175)

    def test_empty_maxima_returns_none(self):
        self.assertIsNone(T.vote_cap_anchor({}, 16, 2048))

    def test_mode_tie_breaks_deterministic(self):
        first = T.vote_cap_anchor({100: 5, 200: 5}, 16, 1000)
        second = T.vote_cap_anchor({200: 5, 100: 5}, 16, 1000)
        self.assertEqual(first['mode_units'], second['mode_units'])


class CapTableTests(unittest.TestCase):
    def vote(self):
        return {'mode_units': 1456.0, 'target_px': 12,
                'reason': 'test', 'members': 175}

    def test_entries_carry_vote(self):
        table = T.build_cap_table(self.vote(), None, 16, 2048)
        by_name = {e['name']: e for e in table['entries']}
        self.assertEqual(set(by_name), {'flat_cap'})
        self.assertEqual(by_name['flat_cap']['design_units'], 1456.0)
        self.assertEqual(by_name['flat_cap']['target_px'], 12)
        self.assertEqual(table['band_rel'], T.CAP_BAND_TOL)

    def test_ascender_entries_need_taller_vote(self):
        asc = {'mode_units': 1536.0, 'target_px': 12,
               'reason': 'test', 'members': 25}
        table = T.build_cap_table(self.vote(), asc, 16, 2048)
        by_name = {e['name']: e for e in table['entries']}
        self.assertEqual(set(by_name),
                         {'flat_cap', 'flat_ascender'})
        self.assertEqual(by_name['flat_ascender']['design_units'],
                         1536.0)
        # A vote at or below the cap line adds no ascender rows.
        low = dict(asc, mode_units=1400.0)
        table = T.build_cap_table(self.vote(), low, 16, 2048)
        self.assertEqual(len(table['entries']), 1)

    def test_no_vote_returns_none(self):
        self.assertIsNone(T.build_cap_table(None, None, 16, 2048))
        self.assertIsNone(T.build_cap_table(
            {'mode_units': 0, 'target_px': 10}, None, 16, 2048))


class TargetTests(unittest.TestCase):
    def records(self):
        return {
            'T': {'features': [{'kind': 'stem', 'width': 190.0}]},
            'H': {'features': [{'kind': 'stem', 'width': 193.0},
                               {'kind': 'stem', 'width': 192.0}]},
            'n': {'features': [{'kind': 'stem', 'width': 185.0},
                               {'kind': 'stem', 'width': 186.0}]},
        }

    def test_straddling_class_snaps_outward_with_reason(self):
        table = T.build_table(self.records(), 16, 2048)
        self.assertEqual(len(table['clusters']), 1)
        cluster = table['clusters'][0]
        self.assertEqual(cluster['target_px'], 2)
        self.assertIn('straddling', cluster['reason'])
        for width in (190.0, 193.0, 192.0, 185.0, 186.0):
            self.assertEqual(T.lookup(table, width), 2)

    def test_unanimous_cluster_keeps_rounding(self):
        records = {'a': {'features': [{'kind': 'stem', 'width': 376.0}]}}
        table = T.build_table(records, 16, 2048)
        self.assertEqual(table['clusters'][0]['target_px'], 3)
        self.assertIn('unanimous', table['clusters'][0]['reason'])

    def test_cut_in_rejects_distant_width(self):
        table = {'ppem': 16, 'em': 2048, 'cut_in_px': 1.0, 'clusters': [
            {'design_mean_units': 190.0, 'members': [],
             'target_px': 4, 'reason': 'hand-built far target'}]}
        # Within the cluster band but beyond cut-in: own rounding (1).
        self.assertEqual(T.lookup(table, 190.0), 1)

    def test_unknown_width_falls_back_to_own_rounding(self):
        table = T.build_table(self.records(), 16, 2048)
        self.assertEqual(T.lookup(table, 1125.0),
                         int(math.floor(1125.0 * 16 / 2048 + 0.5)))

    def test_no_table_is_an_error(self):
        with self.assertRaises(ValueError):
            T.lookup(None, 190.0)

    def test_sub_main_width_keeps_own_rounding(self):
        # Regression guard: no single-width floor in lookup. A
        # floor rejoining sub-main widths to the face main was
        # tried and rejected by oracle adjudication (77
        # both-witness deltas against, vs 17 for, incl. literata
        # O/Q/e/u and thin plus-sign arms). A 64u stem keeps its
        # 1px cluster target here; per-glyph thick/thin calibration
        # belongs in optical work, not in this choke point.
        table = {'ppem': 16, 'em': 1000, 'cut_in_px': 1.0, 'clusters': [
            {'design_mean_units': 95.0, 'members': [{}] * 12,
             'target_px': 2, 'reason': 'main stem class'},
            {'design_mean_units': 64.0, 'members': [{}, {}],
             'target_px': 1, 'reason': 'thin stem class'}]}
        self.assertEqual(T.main_stem_target(table), 2)
        self.assertEqual(T.lookup(table, 64.0), 1)

    def test_class_of_matches_band(self):
        table = T.build_table({
            'a': {'features': [{'kind': 'stem', 'width': 190.0}]},
            'b': {'features': [{'kind': 'stem', 'width': 376.0}]},
        }, 16, 2048)
        self.assertEqual(T.class_of(table, 190.0)['target_px'], 1)
        self.assertEqual(T.class_of(table, 376.0)['target_px'], 3)
        self.assertIsNone(T.class_of(table, 1125.0))


def shared_table():
    return {'ppem': 16, 'em': 2048, 'cut_in_px': 1.0, 'clusters': [
        {'design_mean_units': 189.2, 'members': [],
         'target_px': 2, 'reason': 'shared test class'}]}


def cap_table(mode, target, asc_mode=None, asc_target=None,
              members=175):
    """Cap-height CVT for tests: flat cap plus optional ascender."""
    entries = [
        {'name': 'flat_cap', 'design_units': float(mode),
         'target_px': target, 'reason': 'test', 'members': members},
    ]
    if asc_mode is not None:
        entries.append(
            {'name': 'flat_ascender', 'design_units': float(asc_mode),
             'target_px': asc_target, 'reason': 'test',
             'members': members})
    return {'ppem': 16, 'em': 2048, 'band_rel': 0.025,
            'entries': entries}


class ProjectionTests(unittest.TestCase):
    def constraints(self):
        return [
            dict(kind='Abs', point=0, normal=[1.0, 0.0], sources=[],
                 value=512.0, round=False),
            dict(kind='Dist', point=1, normal=[1.0, 0.0], sources=[0],
                 value=190.0),
        ]

    def test_derived_anchor_uses_shared_target(self):
        from shamir_reorientation import projected_anchors
        derived = projected_anchors(self.constraints(), 16 / 2048,
                                    shared_table())
        self.assertEqual(len(derived), 1)
        # root 4px + shared 2px, in font units.
        self.assertAlmostEqual(derived[0]['value'], 768.0)
        self.assertEqual(derived[0]['shared_target_px'], 2)

    def test_no_table_rounds_per_segment(self):
        from shamir_reorientation import projected_anchors
        derived = projected_anchors(self.constraints(), 16 / 2048, None)
        self.assertAlmostEqual(derived[0]['value'], 640.0)
        self.assertNotIn('shared_target_px', derived[0])


class JointSubstitutionTests(unittest.TestCase):
    def record(self, table):
        return {
            'features': [{'kind': 'stem', 'width': 190.0,
                          'normal': [1, 0], 'groups': [0, 1],
                          'points': [0, 1]}],
            'width_table': table,
            'graph': {'constraints': []},
        }

    def test_hard_width_takes_shared_target(self):
        from joint_stroke_fit import standardize_hard_widths
        record = self.record(shared_table())
        cs = [dict(kind='Dist', point=1, normal=[1.0, 0.0], sources=[0],
                   value=190.0, feature='width-0', id=8)]
        hard_values = [1.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1456.0)
        self.assertEqual(hard_values, [2.0])
        self.assertAlmostEqual(cs[0]['value'], 256.0)
        self.assertTrue(cs[0]['width_standardized'])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 2.0)

    def test_closed_loop_falls_back_to_unstandardized(self):
        import json
        from pathlib import Path
        from shamir_reorientation import prototype
        fixture = (Path(__file__).resolve().parent / 'fixtures'
                   / 'roboto-14-r-prototype.json')
        record = json.loads(fixture.read_text())
        # Real roboto-14 R equations: sharing breaks a closed loop that
        # per-segment rounding closes. Generated once from build_font
        # (baseline profile, ppem 14); prototype needs no fonts.
        record['width_table'] = {
            'ppem': 14, 'em': 2048, 'cut_in_px': 1.0, 'clusters': [
                {'design_mean_units': 170.0, 'members': [],
                 'target_px': 2, 'reason': 'shared test class'}]}
        out = prototype(record)
        self.assertIsNotNone(out.get('width_fallback'))
        self.assertEqual(out.get('width_changes'), [])

    def test_no_table_leaves_hard_values(self):
        from joint_stroke_fit import standardize_hard_widths
        record = self.record(None)
        cs = [dict(kind='Dist', point=1, normal=[1.0, 0.0], sources=[0],
                   value=190.0, feature='width-0', id=8)]
        hard_values = [1.0]
        self.assertEqual(
            standardize_hard_widths(record, cs, [0], hard_values,
                                    16 / 2048, 1456.0), [])
        self.assertEqual(hard_values, [1.0])
        self.assertNotIn('width_standardized', cs[0])

    def test_full_height_extent_keeps_solver_rhs(self):
        # Roboto 16px H: the 1456u cap-height equation spans the whole
        # glyph, so it determines the raster extent itself. The solver's
        # outward rounding (12px) stands; the stem table (11px) is
        # withheld.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'bar', 'width': 1456.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=11, normal=[0.0, 1.0], sources=[3],
                   value=1456.0, feature='width-0', id=4, extent='max')]
        hard_values = [12.0]
        self.assertEqual(
            standardize_hard_widths(record, cs, [0], hard_values,
                                    16 / 2048, 1456.0), [])
        self.assertEqual(hard_values, [12.0])
        self.assertNotIn('width_standardized', cs[0])

    def test_partial_bar_keeps_legacy_table_value(self):
        # Roboto 16px T: the 158u bar underside is a partial span, so
        # the legacy table value (1px) still applies. It places the
        # interior edge cap-relatively, which absolute rounding does
        # not do. Withheld pending zone-alignment research; the
        # resulting left/right asymmetry is tracked separately.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'bar', 'width': 158.0,
                          'normal': [0.0, 1.0]}],
            'width_table': {'ppem': 16, 'em': 2048, 'cut_in_px': 1.0,
                            'clusters': [
                                {'design_mean_units': 150.0, 'members': [],
                                 'target_px': 1,
                                 'reason': 'partial-bar test class'}]},
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=7, normal=[0.0, 1.0], sources=[6],
                   value=158.0, feature='width-0', id=6, extent='max')]
        hard_values = [2.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1456.0)
        self.assertEqual(hard_values, [1.0])
        self.assertEqual(len(changes), 1)

    def test_protected_diagonal_keeps_legacy_table_value(self):
        # Source-sans 18px 4: a protected oblique diagonal inside a
        # stem band by value keeps the legacy table target (2px),
        # which matches native widths. Withheld from withholding:
        # only full-height extents and arcs skip the table.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'stem', 'width': 185.0,
                          'normal': [0.7, 0.7]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=3, normal=[0.7, 0.7],
                   sources=[1], value=185.0, feature='width-0', id=9)]
        hard_values = [1.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1456.0)
        self.assertEqual(hard_values, [2.0])
        self.assertEqual(len(changes), 1)

    def test_cap_band_fullspan_redirects_to_anchor(self):
        # Roboto 14px '0': the 1496u apex span ends at 1476u, inside
        # the flat_cap band, so the entry integer (10px) replaces
        # the solver's outward ceil (11px).
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'bar', 'width': 1496.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Abs', point=3, normal=[0.0, 1.0], sources=[],
                   value=-20.0, id=0),
              dict(kind='PDist', point=11, normal=[0.0, 1.0], sources=[3],
                   value=1496.0, feature='width-0', id=4, extent='max')]
        hard_values = [11.0]
        changes = standardize_hard_widths(record, cs, [1], hard_values,
                                          14 / 2048, 1496.0)
        self.assertEqual(hard_values, [10.0])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 10.0)

    def test_cap_band_arc_apex_redirects_to_anchor(self):
        # Roboto 14px '0': the 152u curved apex span is partial, but
        # its point (1476u) sits in the cap band, so the span becomes
        # entry target - round(source) = 10 - 9 = 1px instead of the
        # solver's outward ceil (2px). The point routes to the
        # flat_cap entry (round entries omitted: overshoot sits
        # inside the flat band with the same integer); the pin
        # holds the ResYAnchor pattern on the entry integer.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 152.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Abs', point=49, normal=[0.0, 1.0], sources=[],
                   value=1324.0, id=0),
              dict(kind='PDist', point=28, normal=[0.0, 1.0], sources=[49],
                   value=152.0, feature='width-0', id=5, extent='max')]
        hard_values = [2.0]
        pins = []
        changes = standardize_hard_widths(record, cs, [1], hard_values,
                                          14 / 2048, 1496.0, pins)
        self.assertEqual(hard_values, [1.0])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 1.0)
        self.assertEqual(pins, [dict(point=28, axis=1, value_px=10.0,
                                     span_constraint=5)])

    def test_metric_top_bound_redirects_to_anchor(self):
        # Roboto 14px '1': the featureless metric top bound (tip at
        # 1464u, in the cap band) takes entry target - round(source)
        # = 10 instead of the solver's outward ceil (11). The
        # source has no Abs row, so the design outline coordinate
        # fills in. The tip meets the flat_cap entry.
        import numpy as np
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'bar', 'width': 1464.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=0, normal=[0.0, 1.0], sources=[1],
                   value=1464.0, id=11, metric=True,
                   metric_role='glyph-y-bound')]
        hard_values = [11.0]
        pins = []
        # Design max (1464u, in-band) marks the glyph top
        # attached; sources[1] still reads 0.0 as the source
        # coordinate, as before.
        design = np.array([[0., 1464.], [0., 0.], [0., 0.]])
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          14 / 2048, 1464.0, pins, design)
        self.assertEqual(hard_values, [10.0])
        self.assertEqual(len(changes), 1)
        self.assertEqual(pins, [dict(point=0, axis=1, value_px=10.0,
                                     span_constraint=11)])

    def test_segment_apex_abs_redirects_to_anchor(self):
        # Literata 20px 'C': the segment apex PAbs (717u, in the cap
        # band around mode 700u) takes the entry integer (14px)
        # instead of the solver's outward ceil (15px).
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [],
            'width_table': shared_table(),
            'cap_table': cap_table(700.0, 14, members=150),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='PAbs', point=19, normal=[0.0, 1.0], sources=[],
                   value=717.0, id=3, extent='max', feature='segment-7')]
        hard_values = [15.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          20 / 1000, 730.0)
        self.assertEqual(hard_values, [14.0])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 14.0)

    def test_ascender_abs_keeps_solver_value(self):
        # A maximum Abs above every band (ascender, no ascender
        # entries in this table) keeps the solver value. In
        # production the ascender entries route such tops to
        # the ascender integer instead (nearest-wins).
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='PAbs', point=5, normal=[0.0, 1.0], sources=[],
                   value=1600.0, id=9, extent='max')]
        hard_values = [11.0]
        self.assertEqual(
            standardize_hard_widths(record, cs, [0], hard_values,
                                    14 / 2048, 1600.0), [])
        self.assertEqual(hard_values, [11.0])

    def test_taller_glyph_between_lines_stands_down(self):
        # An 'f'-shaped tall glyph whose top (1600u) attaches to
        # no entry band: zone attachment at glyph level stands
        # the whole glyph down (solver value kept, no pins).
        # Per-row bands alone overfired here (ss3-14 `(`/`)`
        # redirects both settled witnesses reject); ascender
        # tops route instead (next test).
        import numpy as np
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 152.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Abs', point=49, normal=[0.0, 1.0], sources=[],
                   value=1324.0, id=0),
              dict(kind='PDist', point=28, normal=[0.0, 1.0], sources=[49],
                   value=152.0, feature='width-0', id=5, extent='max')]
        hard_values = [2.0]
        pins = []
        design = np.array([[0., 1600.], [0., 1324.], [0., 0.]])
        changes = standardize_hard_widths(record, cs, [1], hard_values,
                                          14 / 2048, 1496.0, pins, design)
        self.assertEqual(hard_values, [2.0])
        self.assertEqual(changes, [])
        self.assertEqual(pins, [])

    def test_taller_ascender_glyph_redirects(self):
        # Same shape, but the top (1550u) attaches to the
        # ascender entry: the cap-height arc apex takes the
        # flat_cap integer with a pin. Mechanism pin only —
        # production tables carry no ascender entries (the
        # above-band vote is punctuation-contaminated; see
        # ledger), so this path is dormant there.
        import numpy as np
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 152.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10,
                                   asc_mode=1536.0, asc_target=11),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Abs', point=49, normal=[0.0, 1.0], sources=[],
                   value=1324.0, id=0),
              dict(kind='PDist', point=28, normal=[0.0, 1.0], sources=[49],
                   value=152.0, feature='width-0', id=5, extent='max')]
        hard_values = [2.0]
        pins = []
        design = np.array([[0., 1550.], [0., 1324.], [0., 0.]])
        changes = standardize_hard_widths(record, cs, [1], hard_values,
                                          14 / 2048, 1496.0, pins, design)
        self.assertEqual(hard_values, [1.0])
        self.assertEqual(len(changes), 1)
        self.assertEqual(pins, [dict(point=28, axis=1, value_px=10.0,
                                     span_constraint=5)])

    def test_zero_align_twin_gets_pinned(self):
        # The pinned apex drags its zero-aligned twin onto the
        # entry integer too (literata-20 'C' apex pair; twin pins
        # kept as the VTT-anchor attachment pattern).
        import numpy as np
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 152.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Abs', point=49, normal=[0.0, 1.0], sources=[],
                   value=1324.0, id=0),
              dict(kind='PDist', point=28, normal=[0.0, 1.0], sources=[49],
                   value=152.0, feature='width-0', id=5, extent='max'),
              dict(kind='Dist', point=29, normal=[0.0, 1.0], sources=[28],
                   value=0.0, feature='align-3', id=24)]
        hard_values = [2.0]
        pins = []
        design = np.array([[0., 1324.], [0., 1476.], [0., 1476.]])
        changes = standardize_hard_widths(record, cs, [1], hard_values,
                                          14 / 2048, 1496.0, pins, design)
        self.assertEqual(hard_values, [1.0])
        self.assertEqual(len(changes), 1)
        self.assertEqual(pins, [dict(point=28, axis=1, value_px=10.0,
                                     span_constraint=5),
                                dict(point=29, axis=1, value_px=10.0,
                                     span_constraint=24)])

    def test_small_contour_abs_keeps_solver_value(self):
        # Roboto 20px 'j' dot: its top sits in the cap band, but the
        # dot contour (~2px tall) is no cap crown, so the solver's
        # ceiling (15) stands. Guard carried over, same threshold.
        import numpy as np
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 14, members=194),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='PAbs', point=28, normal=[0.0, 1.0], sources=[],
                   value=1476.0, id=6, extent='max')]
        hard_values = [15.0]
        pins = []
        design = np.zeros((30, 2))
        design[:, 1] = 1400.0
        design[18:30, 1] = np.linspace(1265.0, 1476.0, 12)
        self.assertEqual(
            standardize_hard_widths(record, cs, [0], hard_values,
                                    20 / 2048, 1519.0, pins, design,
                                    [17, 29]), [])
        self.assertEqual(hard_values, [15.0])
        self.assertEqual(pins, [])

    def test_abs_band_reads_design_not_lifted_value(self):
        # Source-sans 14px 't': the equation value was lifted into
        # the band, but the source design (638u) sits below it, so
        # no entry matches and natural rounding is kept. (638u
        # also misses the round entry: zone identity stays
        # design-relative.)
        import numpy as np
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [],
            'width_table': shared_table(),
            'cap_table': cap_table(656.0, 9, members=234),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='PAbs', point=9, normal=[0.0, 1.0], sources=[],
                   value=700.0, id=2, extent='max')]
        hard_values = [10.0]
        design = np.zeros((10, 2))
        design[9, 1] = 638.0
        self.assertEqual(
            standardize_hard_widths(record, cs, [0], hard_values,
                                    14 / 1000, 798.0, [],
                                    design_points=design), [])
        self.assertEqual(hard_values, [10.0])

    def test_partial_bar_in_cap_band_keeps_table(self):
        # Roboto 16px T: a partial bar whose point is the cap itself
        # still keeps the legacy table value (1px): bars are not
        # apexes, and the table places the interior edge
        # cap-relatively. No entry redirects it (bar + non-fullspan
        # gating preserved).
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'bar', 'width': 158.0,
                          'normal': [0.0, 1.0]}],
            'width_table': {'ppem': 16, 'em': 2048, 'cut_in_px': 1.0,
                            'clusters': [
                                {'design_mean_units': 150.0, 'members': [],
                                 'target_px': 1,
                                 'reason': 'partial-bar test class'}]},
            'cap_table': cap_table(1456.0, 12),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Abs', point=6, normal=[0.0, 1.0], sources=[],
                   value=1298.0, id=0),
              dict(kind='Dist', point=7, normal=[0.0, 1.0], sources=[6],
                   value=158.0, feature='width-0', id=6, extent='max')]
        hard_values = [2.0]
        changes = standardize_hard_widths(record, cs, [1], hard_values,
                                          16 / 2048, 1456.0)
        self.assertEqual(hard_values, [1.0])
        self.assertEqual(len(changes), 1)

    def test_ascender_fullspan_keeps_solver_value(self):
        # A full-height span ending above the cap band keeps the
        # solver value (no ascender entries in production tables).
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'bar', 'width': 1556.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Abs', point=3, normal=[0.0, 1.0], sources=[],
                   value=0.0, id=0),
              dict(kind='PDist', point=11, normal=[0.0, 1.0], sources=[3],
                   value=1556.0, feature='width-0', id=4, extent='max')]
        hard_values = [11.0]
        self.assertEqual(
            standardize_hard_widths(record, cs, [1], hard_values,
                                    14 / 2048, 1556.0), [])
        self.assertEqual(hard_values, [11.0])

    def test_ascender_top_routes_to_ascender_entry(self):
        # With ascender entries present, a top nearer the
        # ascender line than the cap line takes the ascender
        # integer (nearest-wins): 1520u meets flat_ascender
        # 1536u (11px) rather than flat_cap 1456u.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [],
            'width_table': shared_table(),
            'cap_table': cap_table(1456.0, 10,
                                   asc_mode=1536.0, asc_target=11),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='PAbs', point=5, normal=[0.0, 1.0], sources=[],
                   value=1520.0, id=9, extent='max')]
        hard_values = [12.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          14 / 2048, 1520.0)
        self.assertEqual(hard_values, [11.0])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 11.0)

    def test_redirect_needs_anchor(self):
        # Without a cap table the same row keeps legacy behavior
        # (here: withheld as a full-height extent).
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'bar', 'width': 1496.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Abs', point=3, normal=[0.0, 1.0], sources=[],
                   value=-20.0, id=0),
              dict(kind='PDist', point=11, normal=[0.0, 1.0], sources=[3],
                   value=1496.0, feature='width-0', id=4, extent='max')]
        hard_values = [11.0]
        self.assertEqual(
            standardize_hard_widths(record, cs, [1], hard_values,
                                    14 / 2048, 1496.0), [])
        self.assertEqual(hard_values, [11.0])

    def test_arc_height_keeps_solver_rounding(self):
        # Roboto 16px O: the 164u curved apex height resolves to 2px
        # either way (solver rounding and the 2px stem target agree),
        # so no rewrite is recorded. Span, not direction, decides
        # sharing now: only full-span arc extents withhold (next
        # test but one).
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 164.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=29, normal=[0.0, 1.0], sources=[6],
                   value=164.0, feature='width-0', id=11, extent='max')]
        hard_values = [2.0]
        self.assertEqual(
            standardize_hard_widths(record, cs, [0], hard_values,
                                    16 / 2048, 1496.0), [])
        self.assertEqual(hard_values, [2.0])
        self.assertNotIn('width_standardized', cs[0])

    def test_arc_shared_target_never_thickens(self):
        # A 160u vertical arc band (design 1.25px) inside the 2px stem
        # class keeps the solver value: curved sharing thins only
        # (Shamir 2003 §3.5), so a heavier shared target is withheld
        # with no recorded change.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 160.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=29, normal=[0.0, 1.0], sources=[6],
                   value=160.0, feature='width-0', id=11)]
        hard_values = [1.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [1.0])
        self.assertNotIn('width_standardized', cs[0])
        self.assertEqual(changes, [])

    def test_arc_shared_target_thins_only(self):
        # A 160u arc band (design 1.25px) above a 1px shared class
        # narrows to it: 2.0 -> 1.0 with a recorded change.
        from joint_stroke_fit import standardize_hard_widths
        thin_table = {'ppem': 16, 'em': 2048, 'cut_in_px': 1.0,
                      'clusters': [
                          {'design_mean_units': 140.0, 'members': [],
                           'target_px': 1, 'reason': 'thin test class'}]}
        record = {
            'features': [{'kind': 'arc', 'width': 160.0,
                          'normal': [0.0, 1.0]}],
            'width_table': thin_table,
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=29, normal=[0.0, 1.0], sources=[6],
                   value=160.0, feature='width-0', id=11)]
        hard_values = [2.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [1.0])
        self.assertTrue(cs[0]['width_standardized'])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 1.0)

    def test_arc_full_span_keeps_solver_rounding(self):
        # A vertical arc span covering the whole glyph height still
        # keeps the solver's protective rounding: it determines the
        # raster extent itself.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 1496.0,
                          'normal': [0.0, 1.0]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=29, normal=[0.0, 1.0], sources=[6],
                   value=1496.0, feature='width-0', id=11, extent='max')]
        hard_values = [11.0]
        self.assertEqual(
            standardize_hard_widths(record, cs, [0], hard_values,
                                    16 / 2048, 1496.0), [])
        self.assertEqual(hard_values, [11.0])
        self.assertNotIn('width_standardized', cs[0])

    def test_arc_out_of_band_hardens_honest_rounding(self):
        # A 300u arc band matches no cluster: instead of keeping the
        # raw 2.34px design (phase-ambiguous downstream), it hardens
        # the honest half-up rounding.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 300.0,
                          'normal': [1.0, 0.0]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=9, normal=[1.0, 0.0], sources=[2],
                   value=300.0, feature='width-0', id=12)]
        hard_values = [3.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [2.0])
        self.assertTrue(cs[0]['width_standardized'])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 2.0)

    def test_arc_symmetric_sides_harden_symmetrically(self):
        # Literata-16 O: near-boundary side designs (1.56/1.64px)
        # whose shared 2px target is withheld must still harden to
        # the same integer (own rounding 2/2), never split by phase.
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 200.0,
                          'normal': [1.0, 0.0]},
                         {'kind': 'arc', 'width': 210.0,
                          'normal': [1.0, 0.0]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=9, normal=[1.0, 0.0], sources=[2],
                   value=200.0, feature='width-0', id=12),
              dict(kind='Dist', point=10, normal=[1.0, 0.0], sources=[3],
                   value=210.0, feature='width-1', id=13)]
        hard_values = [3.0, 3.0]
        changes = standardize_hard_widths(record, cs, [0, 1], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [2.0, 2.0])
        self.assertEqual(len(changes), 2)

    def test_arc_opted_out_vertical_spans_keep_solver(self):
        # Faces above 14px opt out of curved-band sharing
        # (arc_sharing False): vertical spans keep the solver value
        # outright. The previous expectation fired the plain shared
        # target here (1.0 to 2.0); the census against frozen
        # source-bitmap-v1 shows that grows a row both oracle
        # witnesses reject (source-sans-3-18 o apex), while every
        # v1-hardened row is a horizontal side width (see below).
        from joint_stroke_fit import standardize_hard_widths
        table = dict(shared_table(), arc_sharing=False)
        record = {
            'features': [{'kind': 'arc', 'width': 160.0,
                          'normal': [0.0, 1.0]}],
            'width_table': table,
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=29, normal=[0.0, 1.0], sources=[6],
                   value=160.0, feature='width-0', id=11)]
        hard_values = [1.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [1.0])
        self.assertNotIn('width_standardized', cs[0])
        self.assertEqual(changes, [])

    def test_arc_opted_out_sides_widen_to_target(self):
        # Same opted-out face, horizontal side width: side widths
        # widen up to the shared target (roboto-16 8 sides 1.0 to
        # 2.0px) but never narrow (see the next test).
        from joint_stroke_fit import standardize_hard_widths
        table = dict(shared_table(), arc_sharing=False)
        record = {
            'features': [{'kind': 'arc', 'width': 160.0,
                          'normal': [1.0, 0.0]}],
            'width_table': table,
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=29, normal=[1.0, 0.0], sources=[6],
                   value=160.0, feature='width-0', id=11)]
        hard_values = [1.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [2.0])
        self.assertTrue(cs[0]['width_standardized'])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 2.0)

    def test_arc_opted_out_sides_never_narrow(self):
        # Same opted-out face, horizontal side width already above
        # the shared target: the solver value stands (roboto-20 O
        # keeps its solver 3px instead of thinning to 2px).
        from joint_stroke_fit import standardize_hard_widths
        table = dict(shared_table(), arc_sharing=False)
        record = {
            'features': [{'kind': 'arc', 'width': 300.0,
                          'normal': [1.0, 0.0]}],
            'width_table': table,
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=29, normal=[1.0, 0.0], sources=[6],
                   value=300.0, feature='width-0', id=11)]
        hard_values = [3.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [3.0])
        self.assertNotIn('width_standardized', cs[0])
        self.assertEqual(changes, [])

    def test_arc_below_main_target_keeps_solver(self):
        # A 160u arc band (honest rounding 1px) below the face's
        # main 2px stem target keeps the solver's outward 2px:
        # curved bands join the main stem weight, never undercut
        # it (roboto-16 O apex vs roboto-14 e).
        from joint_stroke_fit import standardize_hard_widths
        record = {
            'features': [{'kind': 'arc', 'width': 160.0,
                          'normal': [1.0, 0.0]}],
            'width_table': shared_table(),
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=9, normal=[1.0, 0.0], sources=[2],
                   value=160.0, feature='width-0', id=12)]
        hard_values = [2.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [2.0])
        self.assertNotIn('width_standardized', cs[0])
        self.assertEqual(changes, [])

    def test_main_stem_target_prefers_populated_classes(self):
        from stem_width_table import main_stem_target
        table = {'ppem': 14, 'em': 1000, 'cut_in_px': 1.0, 'clusters': [
            {'design_mean_units': 65.0, 'target_px': 1,
             'members': [{}] * 5},
            {'design_mean_units': 95.0, 'target_px': 1,
             'members': [{}] * 41},
            {'design_mean_units': 263.0, 'target_px': 4,
             'members': [{}] * 46}]}
        self.assertEqual(main_stem_target(table), 1)
        self.assertIsNone(main_stem_target({'clusters': []}))
        thin = {'clusters': [{'design_mean_units': 60.0, 'target_px': 1,
                              'members': []}]}
        self.assertEqual(main_stem_target(thin), 1)

    def test_arc_side_width_takes_shared_target(self):
        # Literata 14px O/Q sides: a horizontal arc side width above
        # the shared 1px class narrows to it instead of keeping the
        # solver's outward rounding (2.0 -> 1.0). A shared target
        # heavier than the design width is withheld (see the vertical
        # never-thickens test above); only full-span arc extents keep
        # the protective withhold.
        from joint_stroke_fit import standardize_hard_widths
        thin_table = {'ppem': 16, 'em': 2048, 'cut_in_px': 1.0,
                      'clusters': [
                          {'design_mean_units': 180.0, 'members': [],
                           'target_px': 1, 'reason': 'thin test class'}]}
        record = {
            'features': [{'kind': 'arc', 'width': 200.0,
                          'normal': [1.0, 0.0]}],
            'width_table': thin_table,
            'graph': {'constraints': []},
        }
        cs = [dict(kind='Dist', point=9, normal=[1.0, 0.0], sources=[2],
                   value=200.0, feature='width-0', id=12)]
        hard_values = [2.0]
        changes = standardize_hard_widths(record, cs, [0], hard_values,
                                          16 / 2048, 1496.0)
        self.assertEqual(hard_values, [1.0])
        self.assertTrue(cs[0]['width_standardized'])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['to_px'], 1.0)


class PhaseTests(unittest.TestCase):
    def test_even_target_rejects_half_phase(self):
        import numpy as np
        from joint_stroke_fit import mirror_phase_ok
        record = {'width_table': shared_table()}
        p = np.array([[50.0, 0.0], [1175.0, 0.0]])
        # stem pair in the shared class (design ~190u).
        stem = np.array([[517.0, 0.0], [707.0, 0.0]])
        self.assertTrue(mirror_phase_ok(5.0, [(0, 1)], stem, record))
        self.assertFalse(mirror_phase_ok(4.5, [(0, 1)], stem, record))

    def test_pairs_outside_any_class_pass(self):
        import numpy as np
        from joint_stroke_fit import mirror_phase_ok
        record = {'width_table': shared_table()}
        p = np.array([[0.0, 0.0], [3000.0, 0.0]])
        self.assertTrue(mirror_phase_ok(4.5, [(0, 1)], p, record))

    def test_no_table_passes_everything(self):
        import numpy as np
        from joint_stroke_fit import mirror_phase_ok
        p = np.array([[517.0, 0.0], [707.0, 0.0]])
        self.assertTrue(mirror_phase_ok(4.5, [(0, 1)], p, {}))

    def test_distributed_curve_pairs_pass_through(self):
        import numpy as np
        from joint_stroke_fit import mirror_phase_ok
        record = {'width_table': shared_table()}
        p = np.array([[517.0, 0.0], [707.0, 0.0]])
        weighted = [(np.array([1.0, 0.0]), np.array([0.0, 1.0]))]
        self.assertTrue(mirror_phase_ok(4.5, weighted, p, record))


if __name__ == '__main__':
    unittest.main()
