"""Geometry invariants and native raster checks for axis coordination."""
import unittest
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from axis_consistency import candidates,fit,mismatch
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels

class AxisTests(unittest.TestCase):
    def data(self,key,ch):
        path=Path(__file__).resolve().parent/'out/cumulative-hinter-v7'/f'{key}-candidate.ttf'
        if not path.exists():self.skipTest('frozen specimen unavailable')
        size=int(key.rsplit('-',1)[1]);face=ft.Face(str(path))
        with TTFont(path) as f:
            p,e,t=f['glyf'][f.getBestCmap()[ord(ch)]].getCoordinates(f['glyf']);scale=size/f['head'].unitsPerEm
        q=coords(face,ch,size)
        return p,e,t,q,scale,lambda v:pixels(render(face,ch,size,hinted=True,points=v))

    def test_collinear_source_sides_share_grid_level(self):
        p,e,t,q,s,raster=self.data('source-sans-3-16','+')
        after,audit=fit(p,e,t,q,s,raster)
        self.assertEqual(audit['status'],'candidate');self.assertEqual(mismatch(raster(after),[0,1]),0)
        p=np.asarray(p)
        for axis in (0,1):
            for value in np.unique(p[:,axis]):
                self.assertEqual(np.ptp(after[p[:,axis]==value,axis]),0)

    def test_coaxial_component_raster_symmetry(self):
        p,e,t,q,s,raster=self.data('roboto-16','!')
        after,audit=fit(p,e,t,q,s,raster)
        self.assertEqual(audit['status'],'candidate');self.assertEqual(mismatch(raster(after),[0]),0)

    def test_already_symmetric_is_exact_noop(self):
        p,e,t,q,s,raster=self.data('literata-16','+')
        after,audit=fit(p,e,t,q,s,raster)
        self.assertEqual(audit['status'],'already-symmetric');np.testing.assert_array_equal(after,q)

    def test_ownership_blocks_every_coordinate_change(self):
        p,e,t,q,s,raster=self.data('source-sans-3-16','+')
        owners=[dict(point=i,axis=a) for i in range(len(q)) for a in (0,1)]
        after,audit=fit(p,e,t,q,s,raster,owners)
        np.testing.assert_array_equal(after,q);self.assertEqual(audit['status'],'held')

if __name__=='__main__':unittest.main()
