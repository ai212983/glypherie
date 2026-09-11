import json
import string
import unittest
from pathlib import Path
from shapely.geometry import box
from source_constraints import assess,raster_counters,select
from paper_gridfit import ft,load,pairs,width_table,generate
from stem_gridfit import stems

ROOT=Path(__file__).resolve().parents[2]


def glyph(rows):
    return dict(left=0,top=-len(rows),width=len(rows[0]),height=len(rows),pixels=[int(c) for row in rows for c in row],advance_26_6=256)


class SourceConstraintTests(unittest.TestCase):
    def test_corner_contact_keeps_white_counter_enclosed(self):
        g=glyph(['010','101','010'])
        self.assertEqual(len(raster_counters(g)),1)

    def test_spurious_hole_is_distinct_from_missing_counter(self):
        ring=glyph(['111','101','111']);filled=glyph(['111','111','111'])
        solid=box(0,0,3,3);source_ring=solid.difference(box(1,1,2,2))
        self.assertEqual(assess(solid,ring)['extra_counters'],1)
        self.assertEqual(assess(source_ring,filled)['missing_counters'],1)
        self.assertEqual(assess(source_ring,ring)['defect_count'],0)

    def test_split_counter_cannot_match_twice(self):
        source=box(0,0,5,3).difference(box(1,1,4,2))
        result=assess(source,glyph(['11111','10101','11111']))
        self.assertEqual(result['matched_counters'],1)
        self.assertEqual(result['extra_counters'],1)

    def test_removing_spurious_hole_is_accepted(self):
        ring=glyph(['111','101','111']);solid=glyph(['111','111','111'])
        def unexpected(_):self.fail('sound candidate must not trigger alignment search')
        result,d=select(box(0,0,3,3),ring,solid,unexpected)
        self.assertEqual(result,solid)
        self.assertEqual(d['selected']['extra_counters'],0)

    def face_and_tables(self,name,size):
        jobpath=ROOT/f'tools/font_generator/examples/{name}.json'
        job=json.loads(jobpath.read_text());face=ft.Face(str((jobpath.parent/job['font']).resolve()))
        face.set_var_design_coords([{'wght':400,'opsz':size}.get(a.tag,a.default) for a in face.get_variation_info().axes])
        face.set_pixel_sizes(0,size);diagonal=[];vertical=[]
        for char in string.ascii_uppercase+string.ascii_lowercase+string.digits:
            source,_,tags,ends=load(face,char,size)
            diagonal.extend(p['width'] for p in pairs(source,tags,ends,size))
            vertical.extend(p['width'] for p in stems(source,tags,ends,size))
        return face,width_table(diagonal),width_table(vertical)

    def test_e_opens_with_bounded_outline_alignment(self):
        face,d,v=self.face_and_tables('literata',14)
        g,info=generate(face,'E',14,d,v,True,True)
        evidence=info['source_constraints']
        self.assertEqual(evidence['unshifted_candidate']['extra_counters'],1)
        self.assertEqual(evidence['selected']['defect_count'],0)
        self.assertEqual(abs(evidence['selected_shift_26_6']),16)
        before,_=generate(face,'E',14,d,v,True)
        self.assertEqual(g['advance_26_6'],before['advance_26_6'])

    def test_approved_roboto_groups_unchanged(self):
        for size in (16,18):
            face,d,v=self.face_and_tables('roboto',size)
            for char in 'bhmnpdqX':
                before,_=generate(face,char,size,d,v,True)
                after,_=generate(face,char,size,d,v,True,True)
                self.assertEqual(before,after,(char,size))


if __name__=='__main__':unittest.main()
