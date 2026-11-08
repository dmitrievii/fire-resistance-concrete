"""R0.6.9C: proportional N/M and separate nonlinear N+q time-history contract."""
from __future__ import annotations

import copy
import math
import unittest
from unittest.mock import patch

from multicolumn_r05.project_model import (
    new_project, update_column, update_material_spec, update_section,
    update_thermal_spec)
from rc_fire.mechanics.action_capacity import (
    WITHIN, EXCEEDED, UNKNOWN, scan_action_path)
from rc_fire.integration.r069c import (
    evaluate_fire_action_capacity_at_time,
    evaluate_fire_action_capacity_history, _action_sections,
    _member_load_path_at_time)
from rc_fire.thermal import evaluate_rectangular_column


def column(*, minutes=1., N=100., Mx=10., My=5.):
    project=new_project()
    update_column(project,'c1',{'fire_minutes':minutes})
    update_material_spec(project,'c1',{'concrete':{
        'aggregate_family':'siliceous',
        'consistency':'S3_S5','curing':'natural',
        'modulus_aggregate':'gravel_granite_upto40'},
        'steel':{'product_type':'weldable_bar'}})
    update_thermal_spec(project,'c1',{
        'concrete_family':'siliceous',
        'dry_density_kg_m3':2400.,
        'exposed_faces':['left','right','bottom','top']})
    update_section(project,'c1','center',{
        'N_kN':N,'Mx_kNm':Mx,'My_kNm':My})
    return project['columns'][0]


class FixedActionPathTests(unittest.TestCase):
    def test_design_action_factor_one_is_always_tested(self):
        tested=[]
        def fn(lam):
            tested.append(lam)
            return {'classification':WITHIN if lam<=1.3 else EXCEEDED,
                    'model_status':'synthetic_converged'}
        r=scan_action_path(fn,max_factor=2.,factor_step=.6,max_bisection=5)
        self.assertIn(1.,tested)
        self.assertEqual(r['design_action_evidence']['classification'],WITHIN)
        self.assertTrue(r['transition_brackets_diagnostic'])
        bracket=r['transition_brackets_diagnostic'][0]
        self.assertLess(bracket['lower_observed_within'],1.3+1.e-12)
        self.assertGreater(bracket['upper_observed_exceeded'],1.3-1.e-12)
        self.assertLess(bracket['upper_observed_exceeded']-bracket['lower_observed_within'],.05)
        self.assertIsNone(r['lambda_capacity_normative'])
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])

    def test_unknown_nonlinear_solver_stop_never_proves_capacity(self):
        r=scan_action_path(lambda lam: {
            'classification':UNKNOWN if 1.3<=lam<=1.6 else
                             WITHIN if lam<1.3 else EXCEEDED,
            'model_status':'line_search_failed' if 1.3<=lam<=1.6 else 'converged'},
            max_factor=2.,factor_step=.25,max_bisection=4)
        self.assertEqual(r['transition_brackets_diagnostic'],[])
        self.assertTrue(r['unresolved_factors'])
        self.assertIsNone(r['lambda_capacity_normative'])

    def test_nonmonotone_load_response_not_replaced_by_first_failure(self):
        r=scan_action_path(lambda l: {
            'classification':WITHIN if l<.5 or 1.<=l<1.5 else EXCEEDED,
            'model_status':'synthetic'},
            max_factor=2.,factor_step=.25,max_bisection=1)
        self.assertEqual(len(r['transition_brackets_diagnostic']),2)
        self.assertEqual(r['first_observed_exceedance_factor'],.5)
        self.assertEqual(r['design_action_evidence']['classification'],WITHIN)

    def test_refinement_unknown_cannot_make_a_false_precise_bracket(self):
        r=scan_action_path(lambda l: {
            'classification':WITHIN if l<1.2 else
                             EXCEEDED if l>1.3 else UNKNOWN,
            'model_status':'synthetic'},
            max_factor=1.5,factor_step=.5,max_bisection=5)
        self.assertEqual(len(r['transition_brackets_diagnostic']),1)
        self.assertTrue(r['transition_brackets_diagnostic'][0]['refinement_interrupted_by_unknown'])
        self.assertIsNone(r['lambda_capacity_normative'])

    def test_invalid_factor_budget_and_inputs_are_rejected(self):
        for kwargs in ({'max_factor':.9},{'factor_step':0.},
                       {'max_bisection':-1},{'max_factor':math.nan},
                       {'max_factor':10.,'factor_step':.001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                scan_action_path(lambda _: {'classification':WITHIN},**kwargs)

    def test_evaluation_exception_is_not_failure(self):
        def fn(lam):
            if lam==1.:
                raise ValueError('solver did not converge')
            return {'classification':WITHIN}
        r=scan_action_path(fn,max_factor=1.5,factor_step=.5,max_bisection=1)
        self.assertEqual(r['design_action_evidence']['classification'],UNKNOWN)
        self.assertIsNone(r['first_observed_exceedance_factor'])


class IntegratedFireCapacityTests(unittest.TestCase):
    def test_real_1minute_biaxial_section_uses_entered_design_efforts(self):
        c=column()
        old=copy.deepcopy(c)
        r=evaluate_fire_action_capacity_at_time(c,grid=12,
            max_factor=1.5,factor_step=.5,max_bisection=2,
            include_member=False)
        self.assertEqual(c,old)
        self.assertEqual(r['design_action_sections_count'],1,r)
        self.assertEqual(r['sections'][0]['entered_fire_design_actions'],
                         {'N_kN':100.,'Mx_kNm':10.,'My_kNm':5.})
        self.assertEqual(r['sections'][0]['action_path']['model'],
                         'first_order_biaxial_N_Mx_My_fibre_section')
        self.assertEqual(r['sections'][0]['action_path']['strength_reference'],
                         'literal_8_2_18_normative_strength')
        self.assertIsNone(r['member'])
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])

    def test_each_section_gets_its_own_independent_loading_ray(self):
        c=column()
        c['sections'].append({'id':'top','z_m':3.,'N_kN':110.,
                             'Mx_kNm':-7.,'My_kNm':8.})
        r=evaluate_fire_action_capacity_at_time(c,grid=12,
             max_factor=1.,factor_step=1.,max_bisection=0,include_member=False)
        self.assertEqual([s['section_id'] for s in r['sections']],['center','top'])
        self.assertEqual(r['sections'][1]['entered_fire_design_actions']['Mx_kNm'],-7.)
        self.assertEqual(r['sections'][1]['entered_fire_design_actions']['N_kN'],110.)

    def test_missing_or_negative_compression_is_not_automatically_zero(self):
        c=column()
        c['sections'][0]['Mx_kNm']=None
        r=evaluate_fire_action_capacity_at_time(c)
        self.assertEqual(r['status'],'BLOCKED_INPUT')
        self.assertEqual(r['sections'],[])
        with self.assertRaises(ValueError):
            evaluate_fire_action_capacity_history(c)
        c['sections'][0]['Mx_kNm']=0.
        c['sections'][0]['N_kN']=-100.
        self.assertEqual(evaluate_fire_action_capacity_at_time(c)['status'],'BLOCKED_INPUT')

    def test_90minute_hot_boundary_blocks_fibre_capacity_but_K27_remains(self):
        c=column(minutes=90.)
        r=evaluate_fire_action_capacity_at_time(c,grid=12,
              max_factor=1.,factor_step=1.,max_bisection=0,include_member=False)
        self.assertEqual(r['status'],'BLOCKED_SECTION_MATERIAL_DOMAIN',r)
        self.assertIn('SECTION_MATERIAL_TEMPERATURE_UNSUPPORTED',r['blockers'])
        self.assertIsNotNone(r['K27_area_m2_geometry_only'])
        self.assertEqual(r['sections'],[])
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])

    def test_member_path_cannot_be_inferred_from_section_moments(self):
        c=column()
        thermal=evaluate_rectangular_column(c,grid=12)
        r=_member_load_path_at_time(c,thermal,factor_step=.5,
                                     max_factor=1.5,max_bisection=1)
        self.assertEqual(r['status'],'BLOCKED_MEMBER_PATH_OR_MATERIAL')
        self.assertFalse(r['entered_section_Mx_My_used_as_member_loads'])
        self.assertIn('EXPLICIT_MEMBER_PATH_OR_SUPPORTED_MATERIAL_REQUIRED',
                      r['blockers'])

    def test_time_history_recomputes_independently_and_preserves_column(self):
        c=column(minutes=90.)
        original=copy.deepcopy(c)
        def synthetic(col,**kwargs):
            t=col['fire_minutes']
            return {'status':'synthetic','sections':[
                {'section_id':'center','at_design_actions':{
                    'classification':WITHIN if t<=30. else
                                     EXCEEDED if t==60. else UNKNOWN},
                 'action_path':{'transition_brackets_diagnostic':[]}}],
                'member':None,'K27_area_m2_geometry_only':.2,
                'temperature_max_C':t,'steel_temperature_max_C':t/2}
        with patch('rc_fire.integration.r069c.evaluate_fire_action_capacity_at_time',
                   side_effect=synthetic) as mock:
            result=evaluate_fire_action_capacity_history(c,step_minutes=30.,
                    include_member=False,max_factor=1.,factor_step=1.,
                    max_bisection=0)
        self.assertEqual([x['time_minutes'] for x in result['samples']],
                         [1.,30.,60.,90.])
        self.assertEqual(mock.call_count,4)
        self.assertEqual(c,original)
        self.assertEqual(result['observed_section_reference_transitions_minutes'],
            [{'sampled_within_minutes':30.,
              'sampled_exceeded_minutes':60.,
              'proves_normative_failure':False}])
        self.assertEqual(result['unresolved_times_minutes'],[90.])
        self.assertIsNone(result['R_t_minutes'])
        self.assertFalse(result['normative_claim'])

    def test_history_overload_rejected_and_source_action_remains_unrecombined(self):
        c=column(minutes=120.)
        with self.assertRaises(ValueError):
            evaluate_fire_action_capacity_history(c,step_minutes=1.,
                       include_member=False)
        with patch('rc_fire.integration.r069c.evaluate_fire_action_capacity_at_time',
                   return_value={'status':'blocked','sections':[],'member':None}):
            r=evaluate_fire_action_capacity_history(c,step_minutes=60.,
                       include_member=False)
        self.assertTrue(r['source_fire_design_actions_used_without_recombination'])
        self.assertTrue(r['member_section_moment_equivalence_not_inferred'])

    def test_member_time_path_keeps_zero_link_to_entered_bending_moments(self):
        c=column()
        c['member_spec']={
          'thermal_longitudinal_mode':'uniform_assumed',
          'uniform_fire_basis':'equal fire exposure at all longitudinal stations',
          'left_support':'pinned','right_support':'pinned',
          'support_provenance':'declared end restraint',
          'load_mode':'uniform_transverse_load',
          'q_x_kNpm':1.,'q_y_kNpm':0.,'node_count':2}
        # One real model point; don't assume its first try always converges
        # or that member q produces the independently entered section moments.
        r=evaluate_fire_action_capacity_at_time(c,grid=12,
             max_factor=1.,factor_step=1.,max_bisection=0,include_member=True)
        self.assertIsInstance(r['member'],dict)
        self.assertFalse(r['member']['entered_section_Mx_My_used_as_member_loads'])
        self.assertFalse(r['member']['entered_section_moments_reconciled_with_explicit_q'])
        self.assertFalse(r['member']['normative_claim'])
        self.assertIsNone(r['member']['R_t_minutes'])


if __name__=='__main__':
    unittest.main()
