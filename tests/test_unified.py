import copy
from pathlib import Path
import unittest
from app_core import (load_example,execute,reference_compatible,generate_docx,
                      summary_rows,input_fingerprint,legacy_to_parametric)
from section_drawing import dimensioned_figure,bar_schedule,steel_legend,section_svg
from print_report import make_printable_html


class UnifiedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.base=load_example('k18')

    def test_k18_is_parametric_input_with_8_distinct_bars(self):
        self.assertEqual(self.base['schema'],'k18-parametric-r04')
        self.assertEqual(len(self.base['variants']),2)
        self.assertTrue(all(len(v['bars'])==8 for v in self.base['variants']))
        self.assertTrue(reference_compatible(self.base))
        self.assertEqual(steel_legend(self.base,0),'8 × Ø20 mm')
        self.assertEqual(steel_legend(self.base,1),'8 × Ø25 mm')

    def test_reference_numerics_appear_from_one_schema(self):
        r=execute(self.base)
        self.assertEqual(r['engine'],'independent-k18-python')
        self.assertAlmostEqual(r['variants']['v2']['axes']['x']['M_Rd_kNm'],421.350648996,places=6)
        self.assertAlmostEqual(r['variants']['v2']['axes']['x']['M_Ed_kNm'],162.675672,places=3)
        self.assertEqual(len(summary_rows(r)),4)

    def test_new_geometry_routes_to_new_engine(self):
        changed=copy.deepcopy(self.base)
        changed['geometry']['b_m']=.72
        changed['geometry']['h_m']=.50
        for v in changed['variants']:
            for bar in v['bars']:
                bar['x_m']*=.72/.6
                bar['y_m']*=.5/.6
        self.assertFalse(reference_compatible(changed))
        r=execute(changed)
        self.assertEqual(r['engine'],'k18-parametric-experimental')
        self.assertNotAlmostEqual(r['variants']['v2']['axes']['x']['M_Rd_kNm'],421.35065,places=1)

    def test_diameter_change_recomputes_not_stale(self):
        changed=copy.deepcopy(self.base)
        changed['variants'][1]['bars'][0]['diameter_mm']=28
        r=execute(changed)
        self.assertEqual(r['engine'],'k18-parametric-experimental')
        self.assertEqual(r['variants']['v2']['bars'][0]['diameter_mm'],28)

    def test_load_changes_remain_reference_compatible(self):
        changed=copy.deepcopy(self.base)
        changed['variants'][1]['N_kN']=540
        self.assertTrue(reference_compatible(changed))
        r=execute(changed)
        self.assertEqual(r['engine'],'independent-k18-python')
        self.assertNotAlmostEqual(r['variants']['v2']['axes']['x']['M_Ed_kNm'],162.675672,places=3)

    def test_reference_schedule_real_dimensions_and_temperatures(self):
        s=bar_schedule(self.base,1,execute(self.base))
        self.assertEqual(s[0]['X [mm]'],50)
        self.assertEqual(s[0]['Ø [mm]'],25)
        self.assertEqual(s[0]['Cover left [mm]'],37.5)
        self.assertEqual(s[0]['T [°C]'],597)
        self.assertEqual(s[1]['T [°C]'],355)
        self.assertIn('b = 600 mm',section_svg(self.base,1))
        fig=dimensioned_figure(self.base,1)
        self.assertTrue(len(fig.layout.shapes)>8)

    def test_print_html_contains_computed_values_and_geometry(self):
        r=execute(self.base)
        p=make_printable_html(self.base,r).decode('utf-8')
        self.assertIn('421.351',p)
        self.assertIn('162.676',p)
        self.assertIn('b = 600 mm',p)
        self.assertIn('Ø25',p)
        self.assertIn('window.print()',p)
        modified=copy.deepcopy(self.base)
        modified['variants'][1]['N_kN']=540
        p2=make_printable_html(modified,execute(modified)).decode('utf-8')
        self.assertIn('540.00',p2)
        self.assertNotIn('162.676',p2)

    def test_digest_numeric_normalization_for_initial_web_render(self):
        a=copy.deepcopy(self.base)
        a['fire']['minutes']=90.0
        a['material']['f_ck_MPa']=30.0
        self.assertEqual(input_fingerprint(self.base),input_fingerprint(a))

    def test_legacy_json_converts_to_parametric(self):
        transformed=legacy_to_parametric(load_example('legacy'))
        self.assertEqual(transformed,self.base)

    def test_master_original_and_diagnostic_report(self):
        template=Path(__file__).resolve().parents[2]/'Пример.docx'
        if not template.is_file():
            self.skipTest('Original client Word master is intentionally absent in GitHub CI')
        source=template.read_bytes()
        r=execute(self.base)
        generated,_=generate_docx(self.base,r,source)
        self.assertEqual(generated,source)
        change=copy.deepcopy(self.base)
        change['variants'][1]['bars'][0]['diameter_mm']=28
        diag,_=generate_docx(change,execute(change),source)
        self.assertTrue(diag.startswith(b'PK'))
        self.assertNotEqual(diag,source)

if __name__=='__main__':unittest.main()
