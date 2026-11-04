"""Contract tests: engineering inputs -> geometry -> solver -> printed report."""
import copy
from math import pi
import unittest

from app_core import load_example, execute, reference_compatible, input_fingerprint
from calculation_engine import ModelError
from reinforcement_layout import (
    active_definition, definition_rows, generate_perimeter, infer_perimeter,
)
from section_drawing import bar_schedule, section_svg
from print_report import make_printable_html


class ReinforcementLayoutTests(unittest.TestCase):
    def setUp(self):
        self.base = load_example('k18')
        self.spec = copy.deepcopy(self.base['variants'][1]['reinforcement'])

    def test_reference_layout_and_solver_are_preserved(self):
        bars, p = generate_perimeter(600,600,self.spec)
        self.assertEqual(len(bars), 8)
        self.assertEqual([(round(b['x_m']*1000),round(b['y_m']*1000)) for b in bars],
            [(50,50),(300,50),(550,50),(50,300),(550,300),
             (50,550),(300,550),(550,550)])
        self.assertAlmostEqual(p['area_mm2'], 8*pi*25**2/4)
        self.assertEqual(p['clear_cover_left_mm'], 37.5)
        modified = copy.deepcopy(self.base)
        modified['variants'][1]['bars'] = bars
        self.assertTrue(reference_compatible(modified))
        self.assertEqual(input_fingerprint(self.base),input_fingerprint(modified))
        self.assertAlmostEqual(execute(modified)['variants']['v2']['axes']['x']['M_Rd_kNm'],
                               421.350648996,places=5)

    def test_resize_from_600_to_400_regenerates_bars_inside_section(self):
        bars, p = generate_perimeter(400,600,self.spec)
        self.assertEqual(p['spacing_x_mm'], 150)
        self.assertEqual(p['spacing_y_mm'], 250)
        self.assertEqual(max(b['x_m']*1000 for b in bars),350)
        self.assertEqual(min(b['x_m']*1000 for b in bars),50)
        changed = copy.deepcopy(self.base)
        changed['geometry']['b_m']=.4
        for variant in changed['variants']:
            generated,ps=generate_perimeter(400,600,variant['reinforcement'])
            variant['bars']=generated
            variant['reinforcement']=ps
        self.assertFalse(reference_compatible(changed))
        self.assertEqual(max(x['X [mm]'] for x in bar_schedule(changed,1)),350)
        self.assertIn('b = 400 mm',section_svg(changed,1))
        self.assertEqual(execute(changed)['engine'],'k18-parametric-experimental')

    def test_spacing_driven_symmetric_layout(self):
        spec={**self.spec,'basis':'spacing','spacing_x_mm':200,'spacing_y_mm':180}
        bars,p=generate_perimeter(600,600,spec)
        self.assertEqual((p['left_mm'],p['right_mm']), (100,100))
        self.assertEqual((p['bottom_mm'],p['top_mm']), (120,120))
        self.assertEqual(len(bars),8)

    def test_asymmetric_edge_distances(self):
        spec={**self.spec,'symmetric':False,'left_mm':45,'right_mm':65,
              'bottom_mm':55,'top_mm':85,'nx':4,'ny':3}
        bars,p=generate_perimeter(720,500,spec)
        self.assertEqual(len(bars),10)
        self.assertAlmostEqual(p['spacing_x_mm'],(720-45-65)/3)
        self.assertEqual(p['spacing_y_mm'],180)
        self.assertEqual(len({b['id'] for b in bars}),10)
        inf=infer_perimeter(720,500,bars)
        self.assertIsNotNone(inf)
        self.assertFalse(inf['symmetric'])
        self.assertEqual(inf['nx'],4)
        self.assertEqual(inf['ny'],3)

    def test_asymmetric_spacing_driven_last_edges(self):
        spec={**self.spec,'basis':'spacing','symmetric':False,'left_mm':40,
              'bottom_mm':60,'spacing_x_mm':210,'spacing_y_mm':170}
        _,p=generate_perimeter(600,500,spec)
        self.assertEqual((p['right_mm'],p['top_mm']), (140,100))

    def test_custom_layout_is_not_mistaken_for_regular_perimeter(self):
        v=copy.deepcopy(self.base)
        v['variants'][1]['bars'][2]['x_m']-=.011
        self.assertIsNone(infer_perimeter(600,600,v['variants'][1]['bars']))
        v['variants'][1]['reinforcement']={'mode':'custom'}
        self.assertEqual(active_definition(v,1),{'mode':'custom'})
        self.assertIn(('Layout','Custom bar coordinates'),definition_rows(v,1))

    def test_invalid_overlap_cover_and_counts_fail_closed(self):
        bad_cases=[
            (400,600,{**self.spec,'nx':20}),
            (400,600,{**self.spec,'left_mm':200}),
            (400,600,{**self.spec,'left_mm':12.5}),
            (400,600,{**self.spec,'diameter_mm':55}),
            (600,600,{**self.spec,'nx':33,'ny':33}),
            (600,600,{**self.spec,'basis':'spacing','spacing_x_mm':5}),
        ]
        for b,h,spec in bad_cases:
            with self.subTest(spec=spec):
                with self.assertRaises(ModelError):
                    generate_perimeter(b,h,spec)

    def test_engineering_definition_in_print_output(self):
        output=make_printable_html(self.base,execute(self.base)).decode('utf-8')
        self.assertIn('Reinforcement definition',output)
        self.assertIn('Bars along x / y',output)
        self.assertIn('250 / 250 mm',output)
        self.assertIn('3926.99 mm²',output)
        self.assertIn('nx=3, ny=3',output)


if __name__ == '__main__': unittest.main()
