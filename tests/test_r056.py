"""R0.5.6 regression and physical/method boundary checks."""
import copy
import json
import math
import unittest
from pathlib import Path

from multicolumn_r05.project_model import (
    new_project, update_column, update_spalling, update_section,
    to_engine_input, overview_rows,
)
from multicolumn_r05.project_calculator import evaluate_column, evaluate_project
from multicolumn_r05.parametric_engine import GeneralInput, compute_general, concrete_grid
from multicolumn_r05.r056_engine import (
    SPALLING_FIELDS, spalling_assessment, member_envelope,
    enrich_with_biaxial, solve_biaxial_equilibrium, check_provenance,
)
from multicolumn_r05.calculation_engine import Inputs, compute, Geometry, Fire, Material, Mechanics, Variant


ROOT=Path(__file__).resolve().parents[1]


def fully_loaded():
    project=new_project(2)
    update_section(project,'c1','bottom',{'N_kN':500,'Mx_kNm':20,'My_kNm':15})
    update_section(project,'c1','top',{'N_kN':520,'Mx_kNm':25,'My_kNm':20})
    return project


class R056Tests(unittest.TestCase):
    def test_legacy_worksheet_44_reference_numerics(self):
        # Fixed historical K18 is regression data, not a new national method.
        spec=Inputs(Geometry(),Fire(),Material(),Mechanics(),(
            Variant('v1',496.7,3.83,0,20),
            Variant('v2',527.16,6.5,0,25)))
        e=compute(spec)
        a=e['variants']['v2']['axes']['x']
        self.assertAlmostEqual(a['M_Rd_kNm'],421.350648996387,places=7)
        self.assertAlmostEqual(a['M_Ed_kNm'],162.675668214,places=6)
        self.assertAlmostEqual(e['thermal']['raw_steel_temperatures_C'][0],596.4654931806213,places=7)
        self.assertFalse(check_provenance()['certification'])

    def test_spalling_missing_never_passes_and_formula(self):
        p=new_project()
        self.assertEqual(evaluate_column(p['columns'][0])['spalling']['status'],'not_evaluated')
        vals=dict.fromkeys(SPALLING_FIELDS,1.0)
        vals['E_c_MPa']=20.0;vals['rho_kg_m3']=2.0
        F=spalling_assessment(vals)
        self.assertEqual(F['status'],'protection_required')
        self.assertAlmostEqual(F['F'],40.0)
        vals['n_p_percent']=20.0
        self.assertEqual(spalling_assessment(vals)['status'],'index_at_or_below_threshold')
        vals['alpha_F']=0
        self.assertEqual(spalling_assessment(vals)['status'],'invalid')

    def test_change_spalling_two_way_project_and_report(self):
        p=fully_loaded()
        data=dict.fromkeys(SPALLING_FIELDS,1.0)
        data['E_c_MPa']=20
        update_spalling(p,'c1',data)
        self.assertEqual(evaluate_project(p)['c1']['spalling']['status'],'protection_required')
        self.assertEqual(evaluate_project(p)['c2']['spalling']['status'],'not_evaluated')
        update_spalling(p,'c1',{'W_e_volume_fraction':None})
        self.assertIn('W_e_volume_fraction',evaluate_column(p['columns'][0])['spalling']['missing'])

    def test_member_reuses_column_axial_max_for_every_section(self):
        p=fully_loaded();c=p['columns'][0]
        result=evaluate_column(c)
        self.assertEqual(result['status'],'calculated')
        self.assertEqual(result['member']['status'],'evaluated')
        self.assertEqual(result['biaxial']['status'],'evaluated')
        self.assertAlmostEqual(result['member']['Nmax_kN'],520)
        for sid in ('bottom','top'):
            self.assertEqual(result['member']['sections'][sid]['x']['eta_member'],
                             result['member']['sections']['top']['x']['eta_member'])
        self.assertEqual(result['worst']['source'],'member_envelope_diagnostic')
        self.assertFalse(result['normative_claim'])
        self.assertEqual(result['fire_resistance_status'],'not_demonstrated')

    def test_biaxial_equilibrium_for_two_axes_and_asymmetric_rebar(self):
        p=fully_loaded();c=p['columns'][0]
        c['bars'][0]['diameter_mm']=25.0
        c['bars'][0]['x_mm']=50.0
        c['bars'][0]['y_mm']=50.0
        one=evaluate_column(c)
        self.assertEqual(one['status'],'calculated',one['issues'])
        for s in one['biaxial']['sections'].values():
            self.assertTrue(s['equilibrium'],s)
            self.assertLess(s['residual_norm'],1e-5)
            self.assertFalse(s['normative_claim'])

    def test_biaxial_high_moment_never_claims_pass(self):
        p=fully_loaded();c=p['columns'][0]
        update_section(p,c['id'],'bottom',{'Mx_kNm':20000,'My_kNm':15000})
        z=evaluate_column(c)
        row=z['biaxial']['sections'].get('bottom',{})
        self.assertNotEqual(row.get('status'),'equilibrium_within_strain',row)
        self.assertFalse(z['normative_claim'])

    def test_changed_geometry_cover_changes_thermal_results(self):
        p=fully_loaded();c=p['columns'][0]
        a=evaluate_column(c)
        t0=a['results']['bottom']['bars'][0]['temperature_C']
        update_column(p,'c1',{'b_mm':700,'h_mm':500,'cover_mm':30,'bar_diameter_mm':25})
        b=evaluate_column(c)
        self.assertEqual(b['status'],'calculated',b['issues'])
        t1=b['results']['bottom']['bars'][0]['temperature_C']
        self.assertNotEqual(t0,t1)
        self.assertEqual(overview_rows(p)[0]['b, мм'],700)
        self.assertEqual(c['bars'][0]['x_mm'],52.5)

    def test_empty_loads_do_not_fabricate_results(self):
        p=new_project(3)
        out=evaluate_project(p)
        for x in out.values():
            self.assertEqual(x['status'],'pending')
            self.assertFalse(x['results'])
            self.assertEqual(x['biaxial']['status'],'not_evaluated')
            self.assertFalse(x['normative_claim'])

    def test_partial_sections_do_not_approve_r90(self):
        p=new_project(1)
        update_section(p,'c1','bottom',{'N_kN':350,'Mx_kNm':10,'My_kNm':5})
        x=evaluate_column(p['columns'][0])
        self.assertEqual(x['status'],'partial')
        self.assertEqual(x['fire_resistance_status'],'not_demonstrated')
        self.assertEqual(x['section_statuses']['top'],'empty')


if __name__=='__main__': unittest.main()