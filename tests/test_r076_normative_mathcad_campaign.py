"""R0.7.6 — three-way audit, NOT a normative certification.

Sources (examined externally, intentionally NOT committed):
- user K18 Mathcad XMCD, 2026-11-04: saved regions 625/2909,
  lower section and upper load definitions; Mathcad itself not rerun.
- user Пример.docx: tables 3.3.* / last conclusions, variants 1/2.
- SP 2.02.05-2026 §§8.1.11,8.2.16-8.2.24, Appendix L;
  SP 5.03.01-2020 concrete/RC material provisions;
  Belarus ТКП EN 1992-1-2-2009 with NA Table НП.1,
  §§3.2.2,3.2.3,4.3.2-4.3.4,4.5.1.

PASS of these tests establishes implementation / fixed-output parity
only, not validation of the normative structural fire model.
No copyrighted source documents are included.
"""
from __future__ import annotations

import json
import math
import unittest

from multicolumn_r05.calculation_engine import (
    Inputs, Geometry, Fire, Material, Mechanics, Variant,
    ModelError, compute)
from rc_fire.materials.tkp_en1992_fire import (
    GAMMA_M_FI, REBAR_FIRE_CLASS, CONDUCTIVITY_NORMAL,
    concrete_parameters, reinforcement_parameters, concrete_stress,
    EurocodeFireMaterialError)
from rc_fire.thermal.tkp_heat import standard_fire_gas_temperature
from rc_fire.integration.r07_inputs import make_column
from rc_fire.integration.r07_public import fire_assessment
from rc_fire.integration.r075_bounded_utilisation import (
    section_interaction_upper_bound)
from rc_fire.materials.normative import resolve_materials
from test_r07_public_workflow import user_inputs


# User's originally saved Mathcad workbook, lower K18 section v2,
# not a measured fire-test case and not the new K1 geometry.
MATHCAD_SAVED = {
    "L_m":13.7,"mu_x":.8,"mu_y":1.2,
    "N_bottom_kN":527.16,"Mx_bottom_kNm":6.5,"My_bottom_kNm":0.,
    "N_top_kN":1134.,"Mx_top_kNm":16.,"My_top_kNm":-38.9,
    "E_cm_GPa":29.,
    "steel_corner_T_C":596.4654931806213,
    "steel_midface_T_C":354.991,
    "v2_M_Rd_x_kNm":421.350648996387,
    "v2_M_Rd_y_kNm":421.35064939232279,
    "v2_M_Ed_x_kNm":162.67566821423009,
    "v2_M_Ed_y_kNm":175.02390560348997,
    "v2_Ncr_x_kN":3098.90,
    "v2_Ncr_y_kN":1376.7257095048969,
}


class MathcadLegacyVsCurrentCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Same fixed dual variant reference as existing test_r056.
        cls.legacy=compute(Inputs(Geometry(),Fire(),Material(),Mechanics(),(
            Variant('v1',496.7,3.83,0.,20.),
            Variant('v2',527.16,6.5,0.,25.))))

    def test_exact_source_saved_90min_lower_X_strength_and_action(self):
        x=self.legacy['variants']['v2']['axes']['x']
        self.assertAlmostEqual(x['M_Rd_kNm'],
            MATHCAD_SAVED['v2_M_Rd_x_kNm'],places=8)
        self.assertAlmostEqual(x['M_Ed_kNm'],
            MATHCAD_SAVED['v2_M_Ed_x_kNm'],places=7)
        self.assertAlmostEqual(x['utilization'],
            MATHCAD_SAVED['v2_M_Ed_x_kNm']/
            MATHCAD_SAVED['v2_M_Rd_x_kNm'],places=7)

    def test_exact_source_saved_90min_lower_Y_strength_and_action(self):
        y=self.legacy['variants']['v2']['axes']['y']
        self.assertAlmostEqual(y['M_Rd_kNm'],
            MATHCAD_SAVED['v2_M_Rd_y_kNm'],places=6)
        self.assertAlmostEqual(y['M_Ed_kNm'],
            MATHCAD_SAVED['v2_M_Ed_y_kNm'],places=6)
        self.assertAlmostEqual(y['N_cr_kN'],
            MATHCAD_SAVED['v2_Ncr_y_kN'],places=5)

    def test_legacy_thermal_reference_matches_saved_mathcad_corner(self):
        t=self.legacy['thermal']['raw_steel_temperatures_C']
        self.assertAlmostEqual(t[0],MATHCAD_SAVED['steel_corner_T_C'],places=7)
        self.assertAlmostEqual(t[1],MATHCAD_SAVED['steel_midface_T_C'],
                               delta=.15)

    def test_original_word_report_variant1_and2_are_historical_not_external_fire_tests(self):
        # Tables 14/15 in original user Word example, rounded to 0.1 kN*m.
        for version,capacity_x,action_x,action_y in (
            ('v1',338.4,153.9,183.2),('v2',421.3,162.6,175.0)):
            v=self.legacy['variants'][version]['axes']
            self.assertAlmostEqual(v['x']['M_Rd_kNm'],capacity_x,delta=.5)
            self.assertAlmostEqual(v['x']['M_Ed_kNm'],action_x,delta=.5)
            self.assertAlmostEqual(v['y']['M_Ed_kNm'],action_y,delta=.5)
        # This is reproduction of legacy arithmetic, not validation of its
        # coordinate geometry, use of common kc, or two-axis interaction.
        self.assertIsNone(self.legacy.get('validated_normative_R_t_minutes'))

    def test_original_worksheet_legacy_mechanics_not_general_time_to_collapse(self):
        # The old report text R90 is hard-coded; original worksheet supplies
        # only one standard-fire state and cannot be used as continuous t_R.
        case=Inputs(Geometry(),Fire(),Material(),Mechanics(),
            (Variant('v1',496.7,3.83,0.,20.),
             Variant('v2',527.16,6.5,0.,25.)))
        self.assertEqual(case.fire.minutes,90.)
        self.assertIn('fixed',self.legacy['assumptions'][0].lower()+
                      self.legacy['assumptions'][1].lower())
        self.assertNotIn('physical_first_failure_time_minutes',self.legacy)

    def test_legacy_mathcad_is_not_identical_to_current_public_k1(self):
        current=make_column(user_inputs())
        self.assertNotEqual(current['length_m'],MATHCAD_SAVED['L_m'])
        self.assertNotEqual(current['sections'][0]['N_kN'],
                            MATHCAD_SAVED['N_bottom_kN'])
        self.assertNotEqual(current['sections'][0]['Mx_kNm'],
                            MATHCAD_SAVED['Mx_bottom_kNm'])
        self.assertEqual(current['sections'][0]['My_kNm'],0.)
        self.assertEqual(len(current['bars']),8)
        self.assertEqual(len(current['sections']),1)


class BelarusSourceBranch(unittest.TestCase):
    def test_national_annex_2_3_and_3_2_3_and_3_3_3_choices_are_literal(self):
        self.assertEqual(GAMMA_M_FI,1.)
        self.assertEqual(REBAR_FIRE_CLASS,'N')
        self.assertEqual(CONDUCTIVITY_NORMAL,'lower_bound')

    def test_tkp_and_sp_2026_fire_strength_values_are_not_interchangeable(self):
        # Belarus TKP tables 3.1 and 3.2a (hot-rolled Class N), theta=500.
        c=concrete_parameters(500.,aggregate='siliceous')
        s=reinforcement_parameters(500.,fyk_MPa=500.,Es_MPa=200000.,
             production_route='hot_rolled',ductility_class='B')
        self.assertAlmostEqual(c.k_c,.60)
        self.assertAlmostEqual(s.k_sy,.78)
        # SP 2.02.05-2026 tables 9/10 independently give kc=.80,
        # ks_S500=.60; historical Mathcad also uses steel coefficient .60.
        self.assertNotEqual(c.k_c,.80)
        self.assertNotEqual(s.k_sy,.60)

    def test_material_table_does_not_hide_1100_1200_strain_gap(self):
        c=concrete_parameters(1150.,aggregate='siliceous')
        self.assertIsNone(c.eps_c1)
        self.assertIsNone(c.eps_cu1)
        self.assertFalse(c.full_stress_strain_defined)
        with self.assertRaises(EurocodeFireMaterialError):
            concrete_stress(.002,1150.,fck_MPa=30.,aggregate='siliceous')

    def test_standard_fire_90_minutes_is_1006_C_not_1132_C(self):
        self.assertAlmostEqual(standard_fire_gas_temperature(90.),
                               1005.987666328203,places=6)

    def test_K1_SP_normal_temperature_modulus_differs_from_original_worksheet(self):
        c=make_column(user_inputs())
        m=resolve_materials(c)
        self.assertEqual(m['status'],'resolved_for_property_lookup',m.get('issues'))
        self.assertAlmostEqual(m['concrete']['E_cm_GPa'],41.)
        self.assertNotEqual(m['concrete']['E_cm_GPa'],MATHCAD_SAVED['E_cm_GPa'])


class QualificationOfCurrentPublicRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column=make_column(user_inputs())
        cls.result=fire_assessment(cls.column,required_minutes=30.,
           steel_route='hot_rolled',ductility_class='B',
           moisture_mass_pct=1.5,grid=8,dt_minutes=3.)
        print('R076_NORMATIVE_MATHCAD_AUDIT_DIGEST '+json.dumps({
            'source':'Mathcad 2025 saved x/y R90, not live Mathcad recalc',
            'legacy_v2_Mrd_x':MathcadLegacyVsCurrentCode.legacy[
                 'variants']['v2']['axes']['x']['M_Rd_kNm']
                 if hasattr(MathcadLegacyVsCurrentCode,'legacy') else None,
            'current_sample_K1':{'fire_min':30,'N_kN':50,'Mx_kNm':2,
                                  'My_kNm':0},
            'solver':'TKP EN 1992-1-2 with Belarus NA',
            'time_points':len(cls.result['timeline']),
            'thermal_points':len(cls.result.get('thermal_timeline') or []),
            'R_t_minutes':cls.result.get('R_t_minutes'),
            'regulatory_result':cls.result.get('regulatory_result'),
            'normative_blocker_count':len(cls.result[
                'remaining_normative_blockers']),
            'member_load_mode':cls.column['member_spec']['load_mode'],
            'steel_confirmed':cls.result['steel_material_confirmed']
        },ensure_ascii=False,sort_keys=True),flush=True)

    def test_public_R_t_is_not_derived_from_converged_section(self):
        r=self.result
        self.assertIsNone(r['R_t_minutes'])
        self.assertIsNone(r['calculated_member_failure_time_minutes'])
        self.assertEqual(r['regulatory_result'],'NOT_ESTABLISHED')
        self.assertIsNone(r['rating_matches_requirement'])
        self.assertIsNone(r['normative_R_at_least_required'])

    def test_actual_member_supports_action_path_are_unavailable(self):
        self.assertEqual(self.column['member_spec']['load_mode'],
                         'not_defined')
        self.assertEqual(self.column['member_spec']['thermal_longitudinal_mode'],
                         'explicit_only')
        self.assertIn('LONGITUDINAL_SUPPORT_RESTRAINT_AND_ACTION_PATH_MUST_BE_QUALIFIED',
                      self.result['remaining_normative_blockers'])
        self.assertIn('FULL_MEMBER_EQUILIBRIUM_NOT_SOLVED',
                      self.result['remaining_normative_blockers'])

    def test_scenario_assumptions_are_not_fabricated_material_certificates(self):
        self.assertFalse(self.result['steel_material_confirmed'])
        self.assertTrue(self.result['numerical_scenario_only'])
        self.assertIn('STEEL_S500_PRODUCTION_AND_DUCTILITY_NOT_DOCUMENTED',
                      self.result['remaining_normative_blockers'])

    def test_member_pdelta_and_tkp_434_test_validation_remain_required(self):
        blockers=self.result['remaining_normative_blockers']
        for key in ('FULL_COLUMN_FIRE_ULS_NOT_VALIDATED_TKP_4_3_4',
                    'TEMPERATURE_AND_MECHANICAL_MESH_CONVERGENCE_NOT_ESTABLISHED',
                    'SPALLING_ANNEX_L_OR_TKP_4_5_NOT_INDEPENDENTLY_CLOSED'):
            self.assertIn(key,blockers)

    def test_stress_relaxed_section_bound_is_explicitly_not_normative_U(self):
        b=self.result['section_interaction_utilisation_bound_at_required_time']
        self.assertEqual(b['status'],'STRESS_ENVELOPE_UPPER_BOUND_SOLVED')
        self.assertGreater(b['section_utilization_lower_bound_pct'],0.)
        self.assertFalse(b['member_utilization_known'])
        self.assertFalse(b['normative_claim'])

    def test_loaded_fire_actions_remain_literal_without_second_combination(self):
        actions=self.result['fire_design_actions'][0]
        self.assertEqual(actions['N_kN'],50.)
        self.assertEqual(actions['Mx_kNm'],2.)
        self.assertEqual(actions['My_kNm'],0.)
        self.assertIsNone(self.result['R_t_minutes'])

    def test_end_of_Rrequired_is_evaluated_not_guessed_from_plot(self):
        self.assertEqual(self.result['required_rating_minutes'],30.)
        self.assertIn(30.,[r['minute'] for r in self.result['timeline']])
        self.assertIn(0.,[r['minute'] for r in self.result['thermal_timeline']])
        self.assertIn(30.,[r['minute'] for r in self.result['thermal_timeline']])


if __name__=='__main__':
    unittest.main()
