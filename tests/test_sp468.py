"""SP 468.1325800.2019 (amendment 1, 2023) tables 9.1–9.6 regression tests."""
import math
import unittest

from multicolumn_r05.sp468 import assessment, SOURCE, _interpolate
from multicolumn_r05.project_model import new_project, update_spalling, export_json, load_json
from multicolumn_r05.project_calculator import evaluate_column
from multicolumn_r05.r056_engine import spalling_assessment, SPALLING_FIELDS


def mixture(**kwargs):
    base=dict(method='sp468',aggregate_type='granite',strength_class_B='B30',
              curing='normal',aggregate_pct=40,dry_density_kg_m3=2500,
              cement_kg_m3=400,water_cement_ratio=.5,
              design_relative_humidity_pct=75,max_aggregate_mm=20)
    base.update(kwargs)
    return base


class SP468Tests(unittest.TestCase):
    def test_table_values_formula_and_units(self):
        a=assessment(mixture())
        self.assertEqual(a['status'],'index_at_or_below_threshold')
        c=a['coefficients']
        self.assertAlmostEqual(c['alpha_bt_per_C'],9.2e-6)
        self.assertAlmostEqual(c['E_bt_MPa'],20000)
        self.assertAlmostEqual(c['lambda_W_mK'],1.9)
        self.assertAlmostEqual(c['K1_prime_MN_m_neg1p5'],(.42+(40-20)/30*(.53-.42))*1.14)
        self.assertAlmostEqual(c['porosity_fraction'],.12)
        self.assertAlmostEqual(c['W_b_mass_fraction'],.03)
        self.assertAlmostEqual(c['W_e_fraction'],.075)
        self.assertAlmostEqual(a['F'],3.1210226847345957,places=8)
        self.assertFalse(a['claim_of_fire_resistance'])
        self.assertEqual(a['source_type'],'SP468_reference')

    def test_interpolation_and_bounds(self):
        a=assessment(mixture(aggregate_pct=50,design_relative_humidity_pct=62.5,cement_kg_m3=450))
        self.assertEqual(a['status'],'index_at_or_below_threshold')
        self.assertAlmostEqual(a['coefficients']['alpha_bt_per_C'],9.25e-6)
        self.assertAlmostEqual(a['coefficients']['lambda_W_mK'],2.1)
        self.assertAlmostEqual(a['coefficients']['K1_prime_MN_m_neg1p5'],.53*1.14)
        self.assertEqual(assessment(mixture(aggregate_pct=65))['status'],'invalid')
        self.assertEqual(assessment(mixture(water_cement_ratio=.9))['status'],'invalid')

    def test_sp468_three_outcomes_are_separate(self):
        low=assessment(mixture())
        middle=assessment(mixture(cement_kg_m3=300,water_cement_ratio=.4))
        high=assessment(mixture(aggregate_type='limestone_gravel',strength_class_B='B60',
            cement_kg_m3=300,water_cement_ratio=.3,max_aggregate_mm=10))
        self.assertLessEqual(low['F'],4)
        self.assertEqual(middle['status'],'requires_structural_check')
        self.assertGreater(middle['F'],4)
        self.assertLess(middle['F'],6)
        self.assertEqual(high['status'],'protection_required')
        self.assertGreaterEqual(high['F'],6)

    def test_curing_modifiers(self):
        a=assessment(mixture(max_aggregate_mm=10))
        b=assessment(mixture(curing='steam_atmospheric',max_aggregate_mm=10))
        self.assertAlmostEqual(b['coefficients']['alpha_bt_per_C']/a['coefficients']['alpha_bt_per_C'],1.1)
        self.assertAlmostEqual(b['coefficients']['E_bt_MPa']/a['coefficients']['E_bt_MPa'],.9)
        self.assertAlmostEqual(b['coefficients']['K1_prime_MN_m_neg1p5']/a['coefficients']['K1_prime_MN_m_neg1p5'],1/1.4)
        c=assessment(mixture(curing='autoclave',max_aggregate_mm=10))
        self.assertAlmostEqual(c['coefficients']['E_bt_MPa']/a['coefficients']['E_bt_MPa'],.77)

    def test_missing_and_unsupported_mix_do_not_invent_F(self):
        self.assertEqual(spalling_assessment({'method':'sp468'})['status'],'not_evaluated')
        self.assertIn('dry_density_kg_m3',spalling_assessment({'method':'sp468'})['missing'])
        a=assessment(mixture(aggregate_type='limestone_all'))
        self.assertEqual(a['status'],'not_evaluated')
        self.assertIsNone(a['F'])
        clay=assessment(mixture(aggregate_type='expanded_clay'))
        self.assertEqual(clay['status'],'not_evaluated')
        self.assertIn('aggregate_porosity_fraction',clay['missing'])

    def test_project_save_load_and_isolated_columns(self):
        p=new_project(2)
        self.assertEqual(p['columns'][0]['spalling']['method'],'sp468')
        update_spalling(p,'c1',mixture())
        sp=evaluate_column(p['columns'][0])['spalling']
        self.assertEqual(sp['status'],'index_at_or_below_threshold')
        self.assertEqual(evaluate_column(p['columns'][1])['spalling']['status'],'not_evaluated')
        loaded=load_json(export_json(p))
        self.assertAlmostEqual(evaluate_column(loaded['columns'][0])['spalling']['F'],sp['F'])
        self.assertFalse(evaluate_column(loaded['columns'][0])['normative_claim'])

    def test_manual_legacy_lambda_first_power_and_percent_fraction(self):
        p={k:1.0 for k in SPALLING_FIELDS}
        p.update({'method':'manual_k18','E_c_MPa':20.,'rho_kg_m3':2.,'lambda_250_W_mK':2.,'n_p_percent':20.})
        x=spalling_assessment(p)
        self.assertAlmostEqual(x['F'],100.)
        self.assertEqual(x['status'],'protection_required')
        p['alpha_F']=.001
        self.assertEqual(spalling_assessment(p)['status'],'index_at_or_below_threshold')


if __name__=='__main__':unittest.main()