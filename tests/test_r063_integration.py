"""R0.6.3 integrated project/Word regression; no R90 on successful Newton."""
import unittest
from docx import Document

from multicolumn_r05.project_model import (new_project, update_column,
     update_section, update_material_spec, update_thermal_spec)
from multicolumn_r05.project_calculator import evaluate_project, evaluate_column
from rc_fire.mechanics.report import add_mechanics_section


class R063IntegrationTests(unittest.TestCase):
    def make_project(self):
        p=new_project(2)
        c=p['columns'][0]
        c['sections']=[
            {'id':'bottom','name':'Низ','z_m':0.,'N_kN':None,'Mx_kNm':None,'My_kNm':None},
            {'id':'top','name':'Верх','z_m':c['length_m'],'N_kN':None,'Mx_kNm':None,'My_kNm':None}]
        update_material_spec(p,'c1',{
            'concrete':{
                'aggregate_family':'siliceous',
                'consistency':'S3_S5',
                'curing':'natural',
                'modulus_aggregate':'gravel_granite_upto40',
                'fine_grained':False,
            },
            'steel':{'product_type':'weldable_bar'},
        })
        update_thermal_spec(p,'c1',{
            'concrete_family':'siliceous','dry_density_kg_m3':2400.,
            'exposed_faces':['left','right','bottom','top'],
            'a_red_mode':'table_K1',
        })
        update_column(p,'c1',{'fire_minutes':10.})
        update_section(p,'c1','bottom',{'N_kN':500,'Mx_kNm':30,'My_kNm':-20})
        update_section(p,'c1','top',{'N_kN':650,'Mx_kNm':-22,'My_kNm':10})
        return p

    def test_two_column_independence_and_three_component_equilibrium(self):
        p=self.make_project()
        results=evaluate_project(p,grid=24)
        a=results['c1']['mechanics_r063']
        b=results['c2']['mechanics_r063']
        self.assertEqual(a['status'],'evaluated_diagnostic')
        self.assertEqual(b['status'],'not_evaluated')
        self.assertFalse(a['normative_claim'])
        for sid in ('bottom','top'):
            self.assertTrue(a['sections'][sid]['equilibrium'])
            self.assertLess(a['sections'][sid]['relative_residual'],1e-6)
        self.assertEqual(results['c1']['fire_resistance_status'],'not_demonstrated')
        self.assertEqual(results['c2']['fire_resistance_status'],'not_demonstrated')

    def test_missing_mix_and_hot_boundary_do_not_claim_r90(self):
        p=self.make_project()
        update_column(p,'c1',{'fire_minutes':90.})
        z=evaluate_column(p['columns'][0],grid=24)
        mech=z['mechanics_r063']
        self.assertEqual(mech['status'],'blocked')
        self.assertTrue(any('800' in x for x in mech['issues']))
        self.assertFalse(z['normative_claim'])
        self.assertFalse(mech['normative_claim'])

    def test_report_section_keeps_normative_warning(self):
        p=self.make_project()
        r=evaluate_column(p['columns'][0],grid=24)
        doc=Document()
        add_mechanics_section(doc,p['columns'][0],r)
        body=' '.join(x.text for x in doc.paragraphs)
        self.assertIn('R0.6.3',body)
        self.assertIn('НЕ подтверждает',body)
        self.assertIn('R90',body)


if __name__=='__main__':unittest.main()
