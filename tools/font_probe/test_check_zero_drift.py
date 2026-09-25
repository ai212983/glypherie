import unittest
from check_zero_drift import audit_drift


def ink(*cells):
    return frozenset(cells)


class ZeroDriftTests(unittest.TestCase):
    def test_exact_kept_is_clean(self):
        settled = {'f-16': {'A': ink((0, 0), (1, 0)), 'B': ink((0, 0))}}
        base = {'f-16': {'A': ink((0, 0), (1, 0)), 'B': ink((0, 0))}}
        new = {'f-16': {'A': ink((0, 0), (1, 0)), 'B': ink((0, 0))}}
        report = audit_drift(settled, base, new)
        self.assertEqual(report['violations'], [])
        self.assertEqual(report['moved'], [])
        self.assertEqual(report['missing'], [])

    def test_exact_broken_is_violation(self):
        # v35 shape: settled-exact capitals knocked far off.
        settled = {'f-20': {'H': ink((0, 0), (1, 0))}}
        base = {'f-20': {'H': ink((0, 0), (1, 0))}}
        new = {'f-20': {'H': ink((5, 5), (6, 5))}}
        report = audit_drift(settled, base, new)
        self.assertEqual(len(report['violations']), 1)
        face, char, old, dist = report['violations'][0]
        self.assertEqual((face, char, old), ('f-20', 'H', 0))
        self.assertEqual(dist, 4)

    def test_waived_exact_move_is_reported_not_failed(self):
        # v36 shape: intentional oracle-approved move carries a reason.
        settled = {'f-16': {'S': ink((0, 0), (1, 0))}}
        base = {'f-16': {'S': ink((0, 1), (1, 1))}}
        new = {'f-16': {'S': ink((0, 2), (1, 2))}}
        report = audit_drift(settled, base, new,
                             {'f-16 S': 'stray top row fix, oracle APPROVE'})
        self.assertEqual(report['violations'], [])
        self.assertEqual(len(report['moved']), 1)

    def test_nonexact_move_is_info_only(self):
        settled = {'f-16': {'S': ink((0, 0))}}
        base = {'f-16': {'S': ink((0, 1))}}
        new = {'f-16': {'S': ink((0, 2))}}
        report = audit_drift(settled, base, new)
        self.assertEqual(report['violations'], [])
        self.assertEqual(len(report['moved']), 1)

    def test_missing_is_reported_not_failed(self):
        settled = {'f-16': {'A': ink((0, 0))}}
        base = {'f-16': {'A': ink((0, 0))}}
        new = {'f-16': {}}
        report = audit_drift(settled, base, new)
        self.assertEqual(report['violations'], [])
        self.assertEqual(report['missing'], [('f-16', 'A')])

    def test_base_only_glyph_ignored(self):
        # Glyph with no settled counterpart is outside the contract.
        settled = {'f-16': {}}
        base = {'f-16': {'Z': ink((0, 0))}}
        new = {'f-16': {'Z': ink((9, 9))}}
        report = audit_drift(settled, base, new)
        self.assertEqual(report['violations'], [])
        self.assertEqual(report['moved'], [])


if __name__ == '__main__':
    unittest.main()
