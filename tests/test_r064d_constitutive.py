import unittest
from tools.validate_constitutive_r064d import evaluate_materials

class ConstitutiveIndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=evaluate_materials()
    def test_concrete_all_original_table_nodes(self):
        self.assertEqual(len(self.a['concrete']),9)
        self.assertAlmostEqual(self.a['concrete'][5]['fck_kc_MPa'],24)
        self.assertAlmostEqual(self.a['concrete'][5]['legacy_fcd_kc_MPa'],20)
    def test_steel_all_original_table_nodes(self):
        self.assertEqual(len(self.a['steel']),7)
        self.assertAlmostEqual(self.a['steel'][3]['fy_theta_MPa'],300)
    def test_strength_vs_stiffness_is_not_silently_identical(self):
        q=self.a['concrete'][5]
        self.assertAlmostEqual(q['tabulated_beta_Ecm_GPa'],9.9)
        self.assertAlmostEqual(q['stress_law_initial_tangent_GPa'],24)
        self.assertGreater(q['initial_tangent_to_beta_Ecm'],2)
    def test_interpolation_gap_and_hot_strain_not_qualified(self):
        self.assertEqual(self.a['steel_20_200_C'],'UNDEFINED_BY_TABULATED_NODES')
        self.assertEqual(self.a['hot_eps_cu2'],'NOT_ESTABLISHED_BY_CITED_TABLES')
        self.assertFalse(self.a['normative_claim'])
