"""Independent source-based adjudication tests; not fire-resistance certification."""
import math
import unittest
from rc_fire.mechanics.normative_resolution import (
    elevated_strength_comparison, constitutive_closure_decisions)
from rc_fire.mechanics import evaluate_column_mechanics
from test_r063_mechanics import sample_column

class R063CQualificationTests(unittest.TestCase):
    def test_literal_fire_strength_is_characteristic_times_reduction(self):
        r=elevated_strength_comparison(theta_C=500,concrete_family='siliceous',
            steel_group='S240_S500', fck_MPa=30,fcd_MPa=25,fyk_MPa=500,fyd_MPa=500)
        self.assertAlmostEqual(r['concrete']['literal_SP_8_2_18_MPa'],24.)
        self.assertAlmostEqual(r['concrete']['legacy_accidental_fcd_times_kc_MPa'],20.)
        self.assertAlmostEqual(r['concrete']['difference_MPa'],4.)
        self.assertAlmostEqual(r['steel']['literal_SP_8_2_18_MPa'],300.)
        self.assertFalse(r['normative_claim'])

    def test_ambient_reference_and_table_only_steel(self):
        common=dict(concrete_family='siliceous',steel_group='S240_S500',
                    fck_MPa=30,fcd_MPa=25,fyk_MPa=500,fyd_MPa=500)
        t20=elevated_strength_comparison(theta_C=20,**common)
        self.assertEqual(t20['steel_status'],'ambient_reference')
        t110=elevated_strength_comparison(theta_C=110,**common)
        self.assertIsNone(t110['steel'])
        self.assertEqual(t110['steel_status'],'TABLE_10_NO_DEFINED_COEFFICIENT')
        t200=elevated_strength_comparison(theta_C=200,**common)
        self.assertEqual(t200['steel_status'],'table_10_evaluated')
        self.assertAlmostEqual(t200['steel']['ks'],1.)

    def test_strength_evidence_not_silently_gamma_reduced(self):
        r=elevated_strength_comparison(theta_C=600,concrete_family='calcareous',
                 steel_group='S240_S500',fck_MPa=30,fcd_MPa=25,fyk_MPa=500,fyd_MPa=500)
        self.assertAlmostEqual(r['concrete']['literal_SP_8_2_18_MPa'],19.5)
        self.assertAlmostEqual(r['concrete']['legacy_accidental_fcd_times_kc_MPa'],16.25)

    def test_beta_and_parabola_tangent_remain_distinct(self):
        r=constitutive_closure_decisions(concrete_temperatures_C=[500],steel_temperatures_C=[110],
            concrete_family='siliceous',steel_group='S240_S500',fck_MPa=30,
            fcd_MPa=25,fyk_MPa=500,fyd_MPa=500,Ecm_MPa=33000,eps_c2=.002,n=2)
        s=r['stiffness_comparison']
        self.assertAlmostEqual(s['beta_Ecm_MPa'],9900.)
        self.assertAlmostEqual(s['parabola_initial_tangent_legacy_MPa'],20000.)
        self.assertFalse(s['constitutive_stiffness_verified'])
        self.assertIn('C03_HOT_CONCRETE_STRAINS',r['unresolved_codes'])
        self.assertEqual(r['steel_bars_needing_non_normative_bridge'],1)
        self.assertFalse(r['normative_claim'])

    def test_inputs_fail_closed(self):
        kw=dict(theta_C=500,concrete_family='siliceous',steel_group='S240_S500',
            fck_MPa=30,fcd_MPa=25,fyk_MPa=500,fyd_MPa=500)
        for val in (0,-1,float('nan'),float('inf')):
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    elevated_strength_comparison(**{**kw,'fck_MPa':val})
        with self.assertRaises(ValueError):
            elevated_strength_comparison(**{**kw,'theta_C':900})

    def test_integrated_section_includes_new_resolution_and_remains_diagnostic(self):
        c=sample_column();c['fire_minutes']=10
        r=evaluate_column_mechanics(c,grid=20)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        cl=r['constitutive_closure_r063c']
        self.assertEqual(cl['status'],'PARTIAL_TEXTUAL_CLOSURE_NO_CONSTITUTIVE_QUALIFICATION')
        self.assertFalse(cl['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

if __name__=='__main__': unittest.main()
