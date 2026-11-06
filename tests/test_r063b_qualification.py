"""Independent R0.6.3B primary-table and numerical constitutive checks."""
import unittest
import math
import numpy as np
from rc_fire.mechanics import (concrete_parabolic_linear, steel_bilinear,
    evaluate_column_mechanics, concrete_table_evidence, steel_table_evidence,
    steel_bridge_diagnostic, assess_constitutive_qualification)
from test_r063_mechanics import sample_column

class ConstitutiveQualificationTests(unittest.TestCase):
    def test_table_9_siliceous_exact_nodes(self):
        nodes=[(20,1.,1.),(100,.99,.85),(200,.98,.70),
             (300,.95,.5),(400,.85,.4),(500,.8,.3),
             (600,.6,.2),(700,.2,.1),(800,.1,.05)]
        for t,k,b in nodes:
            with self.subTest(T=t):
                e=concrete_table_evidence(t,'siliceous')
                self.assertEqual(e.provenance,'exact_table_node')
                self.assertEqual((e.k_strength,e.beta_modulus),(k,b))

    def test_table_9_calcareous_and_high_strength_no_beta(self):
        self.assertEqual(concrete_table_evidence(600,'calcareous').k_strength,.65)
        self.assertEqual(concrete_table_evidence(800,'calcareous').beta_modulus,.1)
        e=concrete_table_evidence(500,'high_C55_60')
        self.assertEqual(e.k_strength,.6)
        self.assertIsNone(e.beta_modulus)

    def test_table_10_s500_exact_nodes(self):
        nodes=[(200,1.,.92),(300,1.,.90),(400,.85,.85),
               (500,.60,.80),(600,.37,.77),(700,.22,.72),(800,.10,.65)]
        for t,k,b in nodes:
            e=steel_table_evidence(t,'S240_S500')
            self.assertEqual(e.provenance,'exact_table_node')
            self.assertEqual((e.k_strength,e.beta_modulus),(k,b))

    def test_unqualified_steel_interval_rejects_strict_lookups(self):
        self.assertEqual(steel_table_evidence(20,'S240_S500').provenance,
                         'ambient_reference_not_table_10')
        for t in [20.0001,50,100,199.999]:
            with self.assertRaisesRegex(ValueError,'20..200'):
                steel_table_evidence(t,'S240_S500')
        e=steel_bridge_diagnostic(110,'S240_S500')
        self.assertEqual(e.provenance,'non_normative_linear_bridge_ambient_to_200')
        self.assertAlmostEqual(e.beta_modulus,.96)

    def test_between_nodes_flagged_as_engineering(self):
        self.assertEqual(steel_table_evidence(350,'S240_S500').provenance,
                         'engineering_linear_between_nodes')
        self.assertAlmostEqual(steel_table_evidence(350,'S240_S500').k_strength,.925)
        self.assertAlmostEqual(concrete_table_evidence(450,'siliceous').k_strength,.825)

    def test_outside_table_prevent_fabrication(self):
        for t in [-10,0,801,1200,float('nan')]:
            with self.assertRaises(ValueError):
                concrete_table_evidence(t,'siliceous')
                
        for t in [801,1200,float('nan')]:
            with self.assertRaises(ValueError):
                steel_table_evidence(t,'S240_S500')

    def test_temperature_changes_strength_and_bilinear_tangent(self):
        # Pure analytic law check independent of the section/Newton solver.
        k=concrete_table_evidence(500,'siliceous').k_strength
        s,t=concrete_parabolic_linear(np.array([.001]),25*k,.002,.0035,2)
        self.assertAlmostEqual(float(s[0]),15.)
        self.assertAlmostEqual(float(t[0]),10000.)
        st=steel_table_evidence(500,'S240_S500')
        s,t=steel_bilinear(np.array([.001]),500*st.k_strength,200000*st.beta_modulus)
        self.assertAlmostEqual(float(s[0]),160.)
        self.assertAlmostEqual(float(t[0]),160000.)

    def test_concrete_beta_not_actual_tangent_of_parabola(self):
        c=concrete_table_evidence(500,'siliceous')
        _, tangent=concrete_parabolic_linear(np.array([1e-8]),25*c.k_strength,.002,.0035,2)
        # 25*0.8*2/0.002 = 20 GPa; Ecm=33 GPa *0.3 = 9.9 GPa.
        # Deliberately flag this incompatibility; do NOT silently alter law.
        self.assertAlmostEqual(float(tangent[0]),20000.,delta=.2)
        self.assertNotAlmostEqual(float(tangent[0]),33000*c.beta_modulus,delta=1000)

    def test_reference_strength_ambiguity_is_unresolved(self):
        r=assess_constitutive_qualification(concrete_temperatures_C=[20,500],
           steel_temperatures_C=[20,200],concrete_family='siliceous',
           steel_group='S240_S500',ambient_fck_MPa=30,ambient_fcd_MPa=25)
        self.assertEqual(r['reference_strength_options_MPa']['ratio_fck_over_fcd'],1.2)
        self.assertIn('REFERENCE_STRENGTH_FCK_VERSUS_FCD_UNADJUDICATED',r['issues'])
        self.assertIn('HOT_CONCRETE_ULTIMATE_STRAINS_UNQUALIFIED',r['issues'])
        self.assertFalse(r['normative_claim'])

    def test_full_column_engine_carries_qualification_and_no_r90(self):
        c=sample_column();c['fire_minutes']=15.
        r=evaluate_column_mechanics(c,grid=20)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertIn('constitutive_qualification',r)
        q=r['constitutive_qualification']
        self.assertFalse(q['normative_claim'])
        self.assertGreater(q['counts']['steel_bridge_20_200'],0)
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

    def test_boundary_only_above_800_is_diagnostic(self):
        c=sample_column();c['fire_minutes']=30.
        r=evaluate_column_mechanics(c,grid=16,above_800_policy='zero_strength_diagnostic')
        q=r['constitutive_qualification']
        self.assertEqual(q['status'],'DIAGNOSTIC_ABOVE_TABLE_RANGE')
        self.assertEqual(q['counts']['boundary_samples_above_800'],1)
        self.assertEqual(q['counts']['above_800'],0)

    def test_cutoff_remains_diagnostic(self):
        c=sample_column();c['fire_minutes']=90.
        r=evaluate_column_mechanics(c,grid=20,
                       above_800_policy='zero_strength_diagnostic')
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['constitutive_qualification']['status'],
                         'DIAGNOSTIC_ABOVE_TABLE_RANGE')
        self.assertGreater(r['constitutive_qualification']['counts']['above_800'],0)

if __name__=='__main__': unittest.main()
