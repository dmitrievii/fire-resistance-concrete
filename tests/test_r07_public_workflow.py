"""R0.7 product acceptance: only physical input, one engine and honest R status."""
from __future__ import annotations

import copy
import math
import unittest
from unittest.mock import patch

from rc_fire.integration.r07_inputs import make_column,perimeter_bars
from rc_fire.integration.r07_public import fire_assessment,PublicFireInputError
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN
from multicolumn_r05.project_model import validate_column


def user_inputs():
    """K1-like user inputs for scenario tests, not a documented K18 fire test."""
    return dict(name='К1',b_mm=600.,h_mm=600.,length_m=3.,
        cover_mm=20.,stirrup_mm=10.,bar_diameter_mm=20.,
        mu_x=1.,mu_y=1.,bars_horizontal=3,bars_vertical=3,
        concrete_class='C30/37',aggregate_family='siliceous',
        consistency='V3_V4',curing='natural',
        modulus_aggregate='gravel_granite_upto40',measured_Ecm_GPa=None,
        dry_density_kg_m3=2200.,
        coarse_aggregate_pct=40.,max_aggregate_mm=30.,
        cement_kg_m3=500.,water_cement_ratio=.45,
        relative_humidity_pct=44.,natural_sand_confirmed=True,
        steel_route='hot_rolled',ductility_class='B',
        moisture_mass_pct=1.5,exposed_faces=['left','right','bottom','top'],
        required_minutes=30.,N_kN=50.,Mx_kNm=2.,My_kNm=0.)


class CleanPhysicalInputsTest(unittest.TestCase):
    def test_center_cover_to_stirrup_and_bars_are_literal(self):
        c=make_column(user_inputs())
        self.assertEqual(len(c['bars']),8)
        self.assertEqual((c['bars'][0]['x_mm'],c['bars'][0]['y_mm']),(40.,40.))
        self.assertEqual(c['bars'][1]['x_mm'],300.)
        self.assertEqual(c['bars'][2]['x_mm'],560.)
        self.assertEqual(c['bars'][3]['y_mm'],300.)
        self.assertEqual(c['bars'][-1]['x_mm'],40.)
        self.assertEqual(c['bars'][-1]['y_mm'],300.)
        self.assertEqual(c['steel_grade'],'S500')
        self.assertEqual(c['sections'][0]['Mx_kNm'],2.)
        self.assertEqual(c['sections'][0]['My_kNm'],0.)

    def test_zero_is_a_deliberate_valid_moment(self):
        d=user_inputs()
        d['Mx_kNm']=d['My_kNm']=0.
        self.assertEqual(make_column(d)['sections'][0]['Mx_kNm'],0.)

    def test_missing_load_or_invalid_steel_never_becomes_default(self):
        for k,v in [('N_kN',None),('Mx_kNm',None),('My_kNm',None),
                    ('steel_route','unknown'),('ductility_class',None),
                    ('natural_sand_confirmed',None)]:
            d=user_inputs();d[k]=v
            with self.subTest(k=k),self.assertRaises((ValueError,TypeError)):
                make_column(d)

    def test_non_natural_sand_is_allowed_as_input_not_a_spalling_pass(self):
        d=user_inputs();d['natural_sand_confirmed']=False
        c=make_column(d)
        self.assertIs(c['annex_l_spec']['natural_sand_confirmed'],False)

    def test_carbonate_material_requires_independently_verified_Ecm(self):
        d=user_inputs();d['aggregate_family']='calcareous'
        with self.assertRaises(ValueError):
            make_column(d)
        d['modulus_aggregate']='measured';d['measured_Ecm_GPa']=35.
        c=make_column(d)
        self.assertEqual(c['material_spec']['concrete'][
            'independently_measured_Ecm_GPa'],35.)
        self.assertIsNone(c['material_spec']['concrete']['modulus_aggregate'])

    def test_default_steel_material_is_explicitly_unconfirmed(self):
        d=user_inputs()
        c=make_column(d)
        steel=c['material_spec']['steel']
        self.assertEqual(steel['production_route'],'hot_rolled')
        self.assertEqual(steel['ductility_class'],'B')
        self.assertFalse(steel['selection_confirmed'])
        self.assertEqual(steel['selection_provenance'],
                         'user_visible_demonstration_defaults_unconfirmed')
        d['steel_material_confirmed']=True
        confirmed=make_column(d)['material_spec']['steel']
        self.assertTrue(confirmed['selection_confirmed'])
        self.assertEqual(confirmed['selection_provenance'],'user_documented')

    def test_variable_bar_counts_and_validation(self):
        d=user_inputs();d['bars_horizontal']=4;d['bars_vertical']=4
        c=make_column(d)
        self.assertEqual(len(c['bars']),12)
        self.assertEqual(validate_column(c),[])

    def test_overlapping_rebar_rejected(self):
        with self.assertRaises(ValueError):
            perimeter_bars(b_mm=250,h_mm=250,cover_mm=90,
                tie_d_mm=10,bar_d_mm=20,bars_horizontal=4,bars_vertical=4)

    def test_input_conversion_does_not_create_a_member_load_diagram(self):
        c=make_column(user_inputs())
        self.assertEqual(c['member_spec']['load_mode'],'not_defined')
        self.assertEqual(c['member_spec']['thermal_longitudinal_mode'],'explicit_only')

    def test_material_normative_provenance(self):
        c=make_column(user_inputs())
        self.assertEqual(c['material_spec']['concrete']['consistency'],'V3_V4')
        self.assertEqual(c['thermal_spec']['dry_density_kg_m3'],2200.)
        self.assertEqual(c['annex_l_spec']['natural_sand_confirmed'],True)
        self.assertEqual(c['annex_l_spec']['relative_humidity_pct'],44.)
        self.assertEqual(c['thermal_spec']['moisture_mass_pct'],1.5)


class OneFireResultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=make_column(user_inputs())
        cls.original=copy.deepcopy(cls.c)
        cls.r=fire_assessment(cls.c,required_minutes=30.,
            steel_route='hot_rolled',ductility_class='B',
            moisture_mass_pct=1.5,grid=8,dt_minutes=3.)

    def test_result_contains_exact_required_minute_and_full_inputs(self):
        r=self.r
        self.assertEqual(r['required_rating_minutes'],30.)
        self.assertEqual(r['fire_design_actions'][0]['N_kN'],50.)
        self.assertEqual(r['fire_design_actions'][0]['Mx_kNm'],2.)
        self.assertEqual(r['fire_design_actions'][0]['My_kNm'],0.)
        self.assertEqual([v['minute'] for v in r['timeline']][-1],60.)
        self.assertIn(30.,[v['minute'] for v in r['timeline']])
        self.assertEqual(self.c,self.original)

    def test_method_truly_computes_heat_and_eigenstrain_sections(self):
        r=self.r
        self.assertGreater(r['required_time_temperatures']['gas_C'],20.)
        self.assertGreater(r['required_time_temperatures'][
            'concrete_surface_max_C'],20.)
        self.assertEqual(len(r['required_time_temperatures']['bars_C']),8)
        self.assertIn(r['numerical_section_at_required_time'],
                      (WITHIN,EXCEEDED,UNKNOWN))
        self.assertLess(r['energy_balance']['relative_cumulative_residual'],3e-4)

    def test_never_certify_member_R_by_section_equilibrium(self):
        r=self.r
        self.assertEqual(r['regulatory_result'],'NOT_ESTABLISHED')
        self.assertIsNone(r['calculated_member_failure_time_minutes'])
        self.assertIsNone(r['R_t_minutes'])
        self.assertIsNone(r['rating_matches_requirement'])
        self.assertIsNone(r['normative_R_at_least_required'])
        self.assertIn('FULL_MEMBER_EQUILIBRIUM_NOT_SOLVED',
                      r['remaining_normative_blockers'])

    def test_belarus_spalling_is_a_real_separate_calculation_not_a_rating(self):
        sp=self.r['spalling_annex_L']
        self.assertIn(sp['status'],('calculated_method_scope','blocked_input_or_scope'))
        self.assertIn('source',sp)
        self.assertIsNone(self.r['R_t_minutes'])
        if sp['status']=='calculated_method_scope':
            self.assertGreaterEqual(sp['F'],0.)
            self.assertEqual(sp['normative_claim'],False)

    def test_default_steel_scenario_calculates_without_claiming_certification(self):
        r=self.r
        self.assertFalse(r['steel_material_confirmed'])
        self.assertTrue(r['numerical_scenario_only'])
        self.assertEqual(r['steel_material_provenance'],
                         'user_visible_demonstration_defaults_unconfirmed')
        self.assertIn('STEEL_S500_PRODUCTION_AND_DUCTILITY_NOT_DOCUMENTED',
                      r['remaining_normative_blockers'])
        self.assertGreater(r['required_time_temperatures']['gas_C'],20.)
        self.assertIsNone(r['R_t_minutes'])

    def test_missing_steel_and_outside_engine_scope_fail_before_heat(self):
        with self.assertRaises(PublicFireInputError):
            fire_assessment(self.c,required_minutes=30.,
                steel_route=None,ductility_class='B',
                moisture_mass_pct=1.5,grid=8)
        with self.assertRaises(PublicFireInputError):
            fire_assessment(self.c,required_minutes=180.,
                steel_route='hot_rolled',ductility_class='B',
                moisture_mass_pct=1.5,grid=8)

    def test_user_selected_moisture_and_material_are_never_backfilled(self):
        self.assertEqual(self.r['materials']['moisture_mass_pct'],1.5)
        self.assertEqual(self.r['materials']['steel_route'],'hot_rolled')


if __name__=='__main__':
    unittest.main()
