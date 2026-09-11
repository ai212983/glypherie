"""Executed-font checks for coordinate-hint ablation."""
import tempfile
import unittest
from pathlib import Path

import freetype as ft
import numpy as np

from shamir_prototype import build_font
from trace_shamir_cases import axis_program, axis_font, hinted_points
from test_shamir_prototype import fixture


class TraceTests(unittest.TestCase):
    def test_axis_blocks_keep_setup_and_selected_interpolation(self):
        program=['RTG[ ]','SVTCA[1]','MDAP[1]','IUP[1]',
                 'SVTCA[0]','MIAP[1]','IUP[0]']
        self.assertEqual(axis_program(program,0),program[:4])
        self.assertEqual(axis_program(program,1),[program[0]]+program[4:])

    def test_removed_axis_stays_at_source_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttf';base=Path(tmp)/'base.ttf';fixture(source)
            build_font(source,base,16,{},'AB')
            for axis in (0,1):
                target=Path(tmp)/f'{axis}.ttf';axis_font(base,target,axis)
                points=hinted_points(ft.Face(str(target)),'A',16)
                original=np.array([[103,0],[203,0],[203,700],[103,700]])*.016
                np.testing.assert_allclose(points[:,1-axis],original[:,1-axis],atol=1/64)
                self.assertGreater(float(np.max(np.abs(points[:,axis]-original[:,axis]))),.1)


if __name__=='__main__':unittest.main()
