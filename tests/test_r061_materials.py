"""R0.6.1 literal table anchors, numerical boundaries, and fail-closed selection."""
import unittest
from rc_fire.materials import (ConcreteMix, Reinforcement, MaterialError,
    normal_concrete, concrete_at_temperature, reinforcement_at_temperature,
    concrete_thermal_strain_coefficients, steel_thermal_expansion, resolve_materials)


class MaterialCatalogTests(unittest.TestCase):
    def sample(self, **changes):
        d=dict(strength_class='C30/37',aggregate_family='siliceous',
               consistency='S3_S5',curing='natural',modulus_aggregate='gravel_granite_upto40',
               fine_grained=False)
        d.update(changes)
        return ConcreteMix(**d)

    def test_table_6_1_anchor(self):
        x=normal_concrete(self.sample())
        self.assertEqual(x['f_ck_MPa'],30)
        self.assertEqual(x['f_cm_MPa'],38)
        self.assertEqual(x['eps_cu2_permille'],3.5)
        self.assertEqual(x['E_cm_GPa'],33)

    def test_table_6_3_all_consistency_branches(self):
        self.assertEqual(normal_concrete(self.sample(consistency='V3_V4'))['E_cm_GPa'],41)
        self.assertEqual(normal_concrete(self.sample(consistency='V1_V2'))['E_cm_GPa'],40)
        self.assertEqual(normal_concrete(self.sample(consistency='S1_S2'))['E_cm_GPa'],37)
        self.assertEqual(normal_concrete(self.sample(consistency='S3_S5'))['E_cm_GPa'],33)
        self.assertIsNone(normal_concrete(self.sample(strength_class='C80/95'))['E_cm_GPa'])

    def test_table_6_3_curing_fine_and_freeze(self):
        x=normal_concrete(self.sample(curing='heat',fine_grained=True,saturated_freeze_C=-30))
        self.assertAlmostEqual(x['E_cm_GPa'],33*.9*.85*.85)

    def test_no_unannounced_modulus_from_class(self):
        missing=normal_concrete(ConcreteMix('C30/37'))
        self.assertIsNone(missing['E_cm_GPa'])
        self.assertGreaterEqual(len(missing['missing']),3)
        bad=normal_concrete(self.sample(modulus_aggregate='other'))
        self.assertIsNone(bad['E_cm_GPa'])

    def test_table_9_concrete(self):
        s=self.sample()
        at500=concrete_at_temperature(s,500)
        self.assertAlmostEqual(at500['k_c'],.80)
        self.assertAlmostEqual(at500['beta_E'],.30)
        self.assertAlmostEqual(at500['f_ck_theta_MPa'],24)
        self.assertAlmostEqual(at500['E_cm_theta_GPa'],9.9)
        at350=concrete_at_temperature(s,350)
        self.assertAlmostEqual(at350['k_c'],.90)
        self.assertEqual(at350['mode'],'linear_between_tabulated')
        carbonate=concrete_at_temperature(self.sample(aggregate_family='calcareous'),500)
        self.assertAlmostEqual(carbonate['k_c'],.85)
        self.assertAlmostEqual(carbonate['beta_E'],.35)

    def test_high_strength_beta_not_in_table_9(self):
        s=self.sample(strength_class='C60/75')
        z=concrete_at_temperature(s,600)
        self.assertAlmostEqual(z['k_c'],.45)
        self.assertIsNone(z['beta_E'])
        self.assertIsNone(z['E_cm_theta_GPa'])
        self.assertEqual(z['beta_status'],'table9_no_high_strength_beta')

    def test_table_10_all_reinforcement_groups(self):
        self.assertAlmostEqual(reinforcement_at_temperature(Reinforcement(),500)['k_s'],.60)
        self.assertAlmostEqual(reinforcement_at_temperature(Reinforcement(),500)['beta_E'],.80)
        self.assertAlmostEqual(reinforcement_at_temperature(Reinforcement(grade='S1000'),500)['k_s'],.55)
        self.assertAlmostEqual(reinforcement_at_temperature(Reinforcement(grade='S500',product_type='wire_or_heat_treated',fyk_MPa=500),500)['k_s'],.35)
        self.assertEqual(reinforcement_at_temperature(Reinforcement(),100)['mode'],
                         'engineering_bridge_20_200_not_tabulated')
        self.assertAlmostEqual(reinforcement_at_temperature(Reinforcement(),20)['beta_E'],1)

    def test_no_extrapolation_or_uncited_steel_grade(self):
        with self.assertRaises(MaterialError):concrete_at_temperature(self.sample(),810)
        with self.assertRaises(MaterialError):reinforcement_at_temperature(Reinforcement(),801)
        with self.assertRaises(MaterialError):reinforcement_at_temperature(Reinforcement(grade='S600'),500)
        with self.assertRaises(MaterialError):reinforcement_at_temperature(Reinforcement(product_type='corrosion_resistant_bar'),500)

    def test_tables_11_12_steel_alpha(self):
        sil=concrete_thermal_strain_coefficients('siliceous',500)
        self.assertAlmostEqual(sil['alpha_bt_per_C'],11e-6)
        self.assertAlmostEqual(sil['alpha_cs_per_C'],-1.8e-6)
        self.assertAlmostEqual(concrete_thermal_strain_coefficients('calcareous',900)['alpha_bt_per_C'],15.5e-6)
        self.assertAlmostEqual(steel_thermal_expansion(500)['alpha_s_per_C'],14e-6)
        with self.assertRaises(MaterialError):steel_thermal_expansion(801)

    def test_missing_data_block_property_resolution(self):
        c={'concrete':'C30/37','steel_grade':'S500','material_spec':{}}
        x=resolve_materials(c)
        self.assertEqual(x['status'],'incomplete')
        self.assertIsNone(x['concrete']['E_cm_GPa'])
        self.assertFalse(x['numeric_engine_qualified'])
        c['material_spec']={'concrete':dict(aggregate_family='siliceous',
          consistency='S3_S5',curing='natural',modulus_aggregate='gravel_granite_upto40',fine_grained=False)}
        x=resolve_materials(c)
        self.assertEqual(x['status'],'resolved_for_property_lookup')
        self.assertEqual(x['concrete']['E_cm_GPa'],33)
        self.assertFalse(x['numeric_engine_qualified'])

if __name__=='__main__':unittest.main()