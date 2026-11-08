"""R0.6.9D4 — first integrated main-branch K18 acceptance, no false fire class.

This is an actual replay of the previously provided K18_project.json values
using the existing privacy-preserving fixture, and both Annex K audit and the
standalone TKP thermal + mechanics chain after PR14–PR17 are merged.
Synthetic time-response cases establish that unknown/nonmonotone transitions
cannot become a claimed physical failure time.
"""
from __future__ import annotations
import copy
import json
import unittest

import numpy as np

from test_k18_user_case_audit import actual_k18_user_input
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN
from rc_fire.integration.r069d4_first_crossing import (
    summarize_observed_strain_history,refine_observed_interval)
from rc_fire.integration.r069d3 import evaluate_tkp_thermal_mechanical_history
from rc_fire.thermal.tkp_heat import (
    reference_annex_a_boundary,standard_fire_gas_temperature)
from rc_fire.integration.project_audit import audit_rc_fire_project_column


class TimeTransitionQualificationTests(unittest.TestCase):
    def test_valid_adjacent_within_exceeded_and_refinement(self):
        rows=[{'time_minutes':1.,'reference_classification':WITHIN},
              {'time_minutes':30.,'reference_classification':EXCEEDED},
              {'time_minutes':60.,'reference_classification':EXCEEDED}]
        r=refine_observed_interval(rows,lambda t:{
               'reference_classification':WITHIN if t<17. else EXCEEDED},
               max_refinements=7,tolerance_minutes=.5)
        bracket=r['refined_first_diagnostic_interval']
        self.assertLessEqual(bracket['sampled_within_time_minutes'],17.)
        self.assertGreaterEqual(bracket['sampled_strain_exceeded_time_minutes'],17.)
        self.assertLessEqual(bracket['width_minutes'],.5)
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])
        self.assertFalse(bracket['normative_first_loss'])

    def test_unknown_prevents_bridge_and_never_confirms_failure(self):
        rows=[{'time_minutes':1.,'reference_classification':WITHIN},
              {'time_minutes':15.,'reference_classification':UNKNOWN},
              {'time_minutes':30.,'reference_classification':EXCEEDED}]
        r=summarize_observed_strain_history(rows)
        self.assertEqual(r['observed_within_to_exceeded_intervals'],[])
        self.assertEqual(r['unknown_time_points_minutes'],[15.])
        self.assertEqual(r['first_observed_strain_exceedance_minutes'],30.)
        self.assertIsNone(r['normative_R_t_minutes'])
        self.assertFalse(r['monotonic_failure_hypothesis_proved'])

    def test_nonmonotone_recoveries_are_retained_not_discarded(self):
        vals=(WITHIN,EXCEEDED,WITHIN,EXCEEDED)
        rows=[{'time_minutes':i+1.,'reference_classification':st}
               for i,st in enumerate(vals)]
        r=summarize_observed_strain_history(rows)
        self.assertEqual(len(r['observed_within_to_exceeded_intervals']),2)
        self.assertEqual(len(r['observed_exceeded_to_within_reversals']),1)
        self.assertTrue(r['observed_within_to_exceeded_intervals'][1][
            'earlier_unknown_or_exceedance'])
        self.assertIsNone(r['R_t_minutes'])

    def test_bisection_stops_at_unknown_without_shrinking_arbitrarily(self):
        rows=[{'time_minutes':1.,'reference_classification':WITHIN},
              {'time_minutes':31.,'reference_classification':EXCEEDED}]
        calls=[]
        def evaluate(t):
            calls.append(t)
            return {'reference_classification':UNKNOWN,
                    'reason':'full member tangent nonpositive'}
        r=refine_observed_interval(rows,evaluate,max_refinements=10)
        self.assertEqual(len(calls),1)
        self.assertEqual(r['refined_first_diagnostic_interval'][
            'sampled_within_time_minutes'],1.)
        self.assertEqual(r['refined_first_diagnostic_interval'][
            'sampled_strain_exceeded_time_minutes'],31.)
        self.assertTrue(r['refined_first_diagnostic_interval'][
            'interrupted_by_unknown_state'])
        self.assertFalse(r['normative_claim'])

    def test_no_observed_exceedance_is_not_R90_or_infinite_capacity(self):
        rows=[{'time_minutes':1.,'reference_classification':WITHIN},
              {'time_minutes':90.,'reference_classification':WITHIN}]
        r=refine_observed_interval(rows,lambda t:None)
        self.assertIsNone(r['refined_first_diagnostic_interval'])
        self.assertIsNone(r['R_t_minutes'])
        self.assertIsNone(r['first_observed_strain_exceedance_minutes'])
        self.assertEqual(r['status'],'NO_ADJACENT_WITHIN_TO_EXCEEDED_TRANSITION')

    def test_reject_duplicate_nonfinite_or_decreasing_times(self):
        for times in ([1.,1.],[2.,1.],[float('nan'),2.],[-1.,2.]):
            rows=[{'time_minutes':t,'reference_classification':WITHIN}
                  for t in times]
            with self.subTest(times=times), self.assertRaises(ValueError):
                summarize_observed_strain_history(rows)


class K18SourceFullIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column=actual_k18_user_input()
        cls.original=copy.deepcopy(cls.column)
        cls.boundary=reference_annex_a_boundary(moisture_mass_pct=1.5)
        cls.history=evaluate_tkp_thermal_mechanical_history(
            cls.column,boundary=cls.boundary,
            production_route='hot_rolled',ductility_class='B',
            cell_count=12,fibre_grid=12,max_step_minutes=5.,
            step_minutes=90.,max_factor=1.,factor_step=1.,
            max_bisection=0,include_member=True)
        cls.k18audit=audit_rc_fire_project_column(
            cls.column,grid=12,test_high_temp_model=False,
            density_sensitivity=False)

    def test_full_input_not_mutated_and_fire_actions_not_recombined(self):
        self.assertEqual(self.column,self.original)
        self.assertTrue(self.history['fire_design_actions_used_without_recombination'])
        self.assertEqual(self.history['samples'][-1]['sections'][0][
            'entered_actions_N_Mx_My'],{
                 'N_kN':50.,'Mx_kNm':2.,'My_kNm':0.})
        self.assertTrue(self.k18audit['summary']['source_inputs_preserved'])
        self.assertTrue(self.history['temperature_field_not_from_SP_annex_K'])

    def test_actual_K18_thermal_source_90min_below_material_domain(self):
        last=self.history['samples'][-1]
        self.assertEqual(last['time_minutes'],90.)
        self.assertAlmostEqual(last['T_gas_C'],
                               standard_fire_gas_temperature(90.))
        self.assertLessEqual(last['T_concrete_boundary_max_C'],
                             last['T_gas_C']+1e-6)
        self.assertLess(last['T_concrete_boundary_max_C'],1100.)
        self.assertLess(last['T_reinforcement_C']['S1'],1100.)
        self.assertLess(last['T_reinforcement_C']['S2'],1100.)
        self.assertEqual(last['status'],'FVM_TKP_FIBRES_NUMERICAL_DIAGNOSTIC')

    def test_integrated_energy_balance_and_mechanical_audit(self):
        err=self.history['thermal_energy_balance']
        self.assertLess(err['relative_cumulative_residual'],3e-4)
        self.assertLess(err['worst_step_relative_residual'],3e-4)
        states=[r['reference_classification'] for r in self.history['samples']]
        self.assertTrue(all(s in (WITHIN,EXCEEDED,UNKNOWN) for s in states))
        self.assertEqual(self.history['thermal_field_source_method'],
                         'TKP_4.3.2_FVM')
        self.assertTrue(all(s['temperature_source_match_verified']
                            for s in self.history['samples']))

    def test_optional_spatial_member_is_not_silently_invented(self):
        self.assertEqual(self.history['samples'][-1]['member']['status'],
                         'BLOCKED_MEMBER_INPUT')
        self.assertFalse(self.history['samples'][-1]['member'][
            'entered_section_moment_diagram_reconciled'])
        self.assertFalse(self.history['normative_claim'])
        self.assertIsNone(self.history['R_t_minutes'])
        self.assertIsNone(self.history['normative_first_failure_time_minutes'])

    def test_tkp_and_SP_K_isotherm_are_separate_provenanced_methods(self):
        k27=self.k18audit['thermal']['critical_section']
        self.assertIsNotNone(k27.get('remaining_area_m2'))
        self.assertNotEqual(self.history['thermal_field_source_method'],
                            self.k18audit['thermal']['status'])
        # Different heat-transfer boundary/assumptions: no unjustified
        # equality or claim that either is experimentally validated.
        self.assertTrue(self.history['temperature_field_not_from_SP_annex_K'])
        self.assertFalse(self.history['normative_claim'])

    def test_first_observation_never_certifies_normative_fire_class(self):
        first=self.history['observed_section_strain_transition']
        self.assertFalse(first['normative_claim'])
        self.assertIsNone(first['R_t_minutes'])
        self.assertFalse(first['monotonic_failure_hypothesis_proved'])
        self.assertIsNone(self.history['R_t_minutes'])
        self.assertEqual(self.history['fire_resistance_status'],
                         'not_demonstrated')

    def test_emit_exact_source_case_summary_for_engineering_review(self):
        r=self.history
        last=r['samples'][-1]
        report={
            'name':'K1',
            'method':'TKP EN1992-1-2 Belarus temperature and fibres',
            'fire_min':90.,
            'fire_design_N_kN':50.,
            'fire_design_Mx_kNm':2.,
            'fire_design_My_kNm':0.,
            'steel_route_scenario_not_confirmed':'hot_rolled',
            'steel_ductility_scenario_not_confirmed':'B',
            'moisture_scenario_mass_pct_not_confirmed':1.5,
            'T_gas90_C':round(last['T_gas_C'],2),
            'T_boundary90_C':round(last['T_concrete_boundary_max_C'],2),
            'T_center90_C':round(last['T_concrete_center_C'],2),
            'T_bar_S1_90_C':round(last['T_reinforcement_C']['S1'],2),
            'T_bar_S2_90_C':round(last['T_reinforcement_C']['S2'],2),
            'section_state_at_90':last['reference_classification'],
            'section_model_status_at_90':last['sections'][0]['at_lambda_1']['model_status'],
            'node_member_status':last['member']['status'],
            'thermal_energy_relative_error':r['thermal_energy_balance'][
                'relative_cumulative_residual'],
            'observed_transition_brackets':r['observed_section_strain_transition'][
                'observed_within_to_exceeded_intervals'],
            'R_t_minutes':None,'normative_claim':False}
        print("R069D4_K18_SCENARIO_REPORT "+json.dumps(report,ensure_ascii=False))
        self.assertIsNone(report['R_t_minutes'])
        self.assertFalse(report['normative_claim'])


if __name__=='__main__':
    unittest.main()
