import unittest
from vtt_dependencies import schedule


def op(name,reads=(),writes=()):
    return dict(id=name,reads=set(reads),writes=set(writes))


class DependencyTests(unittest.TestCase):
    def test_support_before_consumer(self):
        operations=[op('diagonal',[(11,0)],[(1,0)]),op('stem',[(0,0)],[(11,0)])]
        order,audit=schedule(operations)
        self.assertEqual(order,[1,0])
        self.assertEqual(audit['dependencies'][0]['after'],['stem'])

    def test_separate_axes_and_stable_order(self):
        order,audit=schedule([op('a',[(2,1)],[(1,0)]),op('b',(),[(2,0)])])
        self.assertEqual(order,[0,1]);self.assertFalse(audit['conflicts'])

    def test_multiple_writers_are_explicit(self):
        order,audit=schedule([op('a',(),[(1,0)]),op('b',(),[(1,0)])])
        self.assertIsNone(order)
        self.assertEqual(audit['conflicts'][0]['kind'],'multiple-writers')

    def test_cycle_is_held_without_discarding_relations(self):
        order,audit=schedule([op('a',[(2,0)],[(1,0)]),op('b',[(1,0)],[(2,0)])])
        self.assertIsNone(order)
        self.assertEqual(audit['conflicts'][0]['kind'],'dependency-cycle')
        self.assertEqual(len(audit['dependencies']),2)
