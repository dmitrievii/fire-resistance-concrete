"""Project-regression: same physical and action inputs as uploaded K18_project.json.

The original user JSON is NOT copied to the public repository. A deterministic
minimal reconstruction checks concrete, Annex L, K.27, steel temperatures,
high-temperature diagnostic mode and cache invalidation.
"""
import copy
import math
import unittest

from multicolumn_r05.project_model import new_project
from rc_fire.integration.r064d import _signature
from rc_fire.integration.project_audit import audit_rc_fire_project_column
from rc_fire.integration.r069c import (
    evaluate_fire_action_capacity_at_time, evaluate_fire_action_capacity_history)
from rc_fire.mechanics.action_capacity import UNKNOWN


def actual_k18_user_input():
    c=new_project()['columns'][0]
    c['id']='c1'
    c['name']='К1'
    c['b_mm']=600.
    c['h_mm']=600.
    c['length_m']=3.
    c['fire_minutes']=90.
    c['concrete']='C30/37'
    c['steel_grade']='S500'
    c['cover_mm']=20.
    c['stirrup_mm']=10.
    c['bar_diameter_mm']=20.
    c['mu_x']=c['mu_y']=1.
    c['sections']=[{
        'id':'center','name':'Центр','z_m':1.5,'auto_midspan':True,
        'N_kN':50.,'Mx_kNm':2.,'My_kNm':0.}]
    c['bars']=[
        {'id':f'S{i+1}','x_mm':x,'y_mm':y,'diameter_mm':20.}
        for i,(x,y) in enumerate([
            (40.,40.),(300.,40.),(560.,40.),(40.,300.),
            (560.,300.),(40.,560.),(300.,560.),(560.,560.)])]
    c['annex_l_spec']={
        'natural_sand_confirmed':True,
        'coarse_aggregate_volume_pct':40.,
        'moisture_mode':'auto','max_aggregate_mm':30.,
        'relative_humidity_pct':44.,
        'cement_kg_m3':500.,
        'water_cement_ratio':.45}
    c['material_spec']={
        'concrete':{
            'aggregate_family':'siliceous','consistency':'V3_V4',
            'curing':'natural','modulus_aggregate':'gravel_granite_upto40'},
        'steel':{'product_type':'weldable_bar'}}
    c['thermal_spec']={
        'a_red_mode':'table_K1',
        'exposed_faces':['left','right','bottom','top'],
        'concrete_family':'siliceous',
        'dry_density_kg_m3':2200.}
    c['member_spec']={'thermal_longitudinal_mode':'explicit_only',
                     'load_mode':'not_defined'}
    return c


class UploadedK18SourceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=actual_k18_user_input()
        cls.r=audit_rc_fire_project_column(cls.c,grid=12,
                                            test_high_temp_model=True)

    def test_material_mix_inputs_are_sufficient_no_false_missing_blockers(self):
        self.assertEqual(self.r['material']['status'],'resolved_for_property_lookup',
                         self.r['material'])
        self.assertEqual(self.r['material']['E_cm_GPa'],41.)
        self.assertFalse(self.r['summary']['hard_input_blockers'])

    def test_annex_l_f_is_computed_below_4_with_documented_uncertainty(self):
        self.assertEqual(self.r['annex_L']['status'],'calculated_method_scope')
        self.assertTrue(self.r['annex_L']['natural_sand_verified'])
        self.assertAlmostEqual(self.r['annex_L']['F'],3.453966951393796,delta=.03)
        self.assertFalse(self.r['annex_L']['protection_required_method_indicator'])
        self.assertFalse(self.r['annex_L']['moisture_method_qualified'])
        self.assertIn('ANNEX_L5_WC_UNIT_INTERPRETATION',
                      self.r['summary']['normative_method_gaps'])

    def test_annex_k_thermal_fields_and_analytical_K27(self):
        self.assertIn(self.r['thermal']['status'],
                      ('evaluated','evaluated_with_scope_warnings'))
        self.assertAlmostEqual(
            self.r['critical_isotherm']['remaining_area_m2'],
            .20004593371839693,delta=.005)
        steel=self.r['thermal']['bar_temperatures_C']
        self.assertEqual(len(steel),8)
        self.assertAlmostEqual(steel['S1'],719.8911517344056,delta=8.)
        self.assertAlmostEqual(steel['S2'],445.3190218427245,delta=8.)
        self.assertLess(max(steel.values()),800.)
        self.assertAlmostEqual(
            self.r['strict_section_capacity']['thermal_boundary_max_C'],
            1131.9,delta=8.)

    def test_real_2200_density_retained_and_tabular_sensitivity_exposed(self):
        self.assertEqual(self.r['thermal']['density_kg_m3'],2200.)
        self.assertIn('ANNEX_K2_INTERMEDIATE_DENSITY',
                      self.r['summary']['normative_method_gaps'])
        sensitivity=self.r['thermal']['K2_neighbor_sensitivity_not_design_value']
        self.assertEqual([x['density_kg_m3'] for x in sensitivity],[2000.,2400.])
        self.assertTrue(all(x['K27_area_m2'] is not None for x in sensitivity))
        self.assertEqual(self.c['thermal_spec']['dry_density_kg_m3'],2200.)

    def test_strict_fibre_calculation_rejected_for_real_hot_concrete(self):
        self.assertEqual(self.r['strict_section_capacity']['status'],
                         'BLOCKED_SECTION_MATERIAL_DOMAIN')
        self.assertIn('FULL_SECTION_MATERIALS_GT_800_NOT_TABULATED',
                      self.r['summary']['normative_method_gaps'])

    def test_model_only_above_800_does_not_erase_physical_unknown(self):
        m=self.r['high_temperature_research_only']
        self.assertEqual(m['status'],'UNQUALIFIED_HIGH_TEMPERATURE_MODEL_ONLY',m)
        self.assertGreater(m['zero_strength_concrete_cells_count'],0)
        self.assertEqual(m['steel_above_800_count'],0)
        self.assertEqual(len(m['raw_numerical_sections']),1)
        self.assertEqual(m['raw_numerical_sections'][0][
            'physical_reference_classification'],UNKNOWN)
        self.assertFalse(m['normative_claim'])
        self.assertIsNone(m['R_t_minutes'])

    def test_member_is_optional_not_a_new_blocker_for_section(self):
        self.assertEqual(self.r['member']['status'],
                         'OPTIONAL_MEMBER_MODEL_NOT_CONFIGURED')
        self.assertFalse(self.r['member']['is_blocker_for_section_calculation'])
        self.assertIn('MEMBER_PATH_NOT_DEFINED',
                      self.r['summary']['optional_model_inputs_not_set'])
        self.assertNotIn('MEMBER_PATH_NOT_DEFINED',
                         self.r['summary']['hard_input_blockers'])

    def test_scope_of_k27_does_not_approve_perimeter8_uls(self):
        self.assertEqual(self.r['critical_isotherm']['scope'][
            'conditions_8_2_21_verified'],False)
        self.assertIn('CRITICAL_ISOTHERM_SECTION_SCOPE_UNQUALIFIED',
                      self.r['summary']['normative_method_gaps'])
        self.assertIsNone(self.r['R_t_minutes'])
        self.assertFalse(self.r['normative_claim'])

    def test_user_column_unchanged_by_audit_and_no_false_R90(self):
        c=actual_k18_user_input()
        original=copy.deepcopy(c)
        z=audit_rc_fire_project_column(c,grid=12,test_high_temp_model=False,
                                        density_sensitivity=False)
        self.assertEqual(c,original)
        self.assertFalse(z['normative_claim'])
        self.assertIsNone(z['summary']['R_t_minutes'])

    def test_cache_signature_changes_on_annex_L_mixture_revision(self):
        c=actual_k18_user_input()
        old=_signature(c)
        c['annex_l_spec']['water_cement_ratio']=.55
        self.assertNotEqual(_signature(c),old)
        old=_signature(c)
        c['annex_l_spec']['relative_humidity_pct']=50.
        self.assertNotEqual(_signature(c),old)
        old=_signature(c)
        c['bar_mode']='manual'
        self.assertNotEqual(_signature(c),old)

    def test_audited_90min_r069c_strict_and_diagnostic_are_distinct(self):
        c=actual_k18_user_input()
        a=evaluate_fire_action_capacity_at_time(c,grid=12,
               max_factor=1.,factor_step=1.,max_bisection=0,
               include_member=False,material_policy='reject')
        b=evaluate_fire_action_capacity_at_time(c,grid=12,
               max_factor=1.,factor_step=1.,max_bisection=0,
               include_member=False,material_policy='zero_strength_diagnostic')
        self.assertEqual(a['status'],'BLOCKED_SECTION_MATERIAL_DOMAIN')
        self.assertEqual(b['status'],'UNQUALIFIED_HIGH_TEMPERATURE_MODEL_ONLY')
        self.assertEqual(b['sections'][0]['at_design_actions']['classification'],UNKNOWN)
        self.assertTrue(b['material_response_model_only'])
        self.assertIsNone(b['R_t_minutes'])
        self.assertFalse(b['normative_claim'])

    def test_history_with_model_only_hot_zones_never_infers_rating(self):
        c=actual_k18_user_input()
        r=evaluate_fire_action_capacity_history(c,step_minutes=90.,
              max_factor=1.,factor_step=1.,max_bisection=0,
              grid=12,include_member=False,material_policy='zero_strength_diagnostic')
        self.assertEqual([x['time_minutes'] for x in r['samples']],[1.,90.])
        self.assertEqual(r['samples'][-1]['section_classification_at_lambda_1'],UNKNOWN)
        self.assertIn(90.,r['unresolved_times_minutes'])
        self.assertFalse(r['normative_claim'])
        self.assertIsNone(r['R_t_minutes'])

    def test_unrecognized_policy_fails_closed(self):
        c=actual_k18_user_input()
        r=evaluate_fire_action_capacity_at_time(c,material_policy='extrapolate')
        self.assertEqual(r['status'],'BLOCKED_INPUT')
        self.assertFalse(r['normative_claim'])


if __name__=='__main__':
    unittest.main()
