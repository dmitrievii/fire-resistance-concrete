"""SP-R.1 source tables and explicitly user-selected concrete zero tail.

Tests assert source SP Tables 9-12 and Eq6, *not* Eurocode factors.
The advanced column t_R remains unqualified until later SP-R stages.
"""
from __future__ import annotations

import math
import unittest

import numpy as np

from rc_fire.materials.normative import ConcreteMix,Reinforcement,normal_concrete
from rc_fire.materials.sp2026_fire import (
    concrete_at_sp_fire,steel_at_sp_fire,
    concrete_stress_sp,steel_stress_sp,
    concrete_free_thermal_strain_sp,steel_free_thermal_strain_sp,
    SPFireMaterialError,ZERO_POLICY,qualification_status)
from rc_fire.mechanics.sp2026_section import (
    evaluate_sp2026_section_at_time,prepare_sp2026_section)
from rc_fire.thermal.tkp_heat import (
    solve_tkp_2d_heat,select_tkp_snapshot,reference_annex_a_boundary)
from rc_fire.integration.r07_inputs import make_column
from rc_fire.integration.r07_public import fire_assessment
from test_r07_public_workflow import user_inputs


class SP2026SourceAndZeroPolicyTests(unittest.TestCase):
    def setUp(self):
        self.concrete=ConcreteMix("C30/37",aggregate_family="siliceous")
        self.concrete_norm={
            **normal_concrete(ConcreteMix("C30/37",aggregate_family="siliceous",
                  independently_measured_Ecm_GPa=41.))}
        self.steel=Reinforcement(grade="S500")

    def test_concrete_exactly_at_800_retains_SP_table9_capacity(self):
        m=concrete_at_sp_fire(self.concrete,800.,self.concrete_norm)
        self.assertAlmostEqual(m.strength_factor,.10)
        self.assertAlmostEqual(m.modulus_factor,.05)
        self.assertAlmostEqual(m.strength_MPa,3.)
        self.assertAlmostEqual(m.elastic_modulus_MPa,2050.)
        self.assertIsNone(m.policy)

    def test_concrete_strictly_over_800_is_zero_not_extrapolation(self):
        for T in (800.000001,801.,900.,990.5,1100.,1200.,1500.):
            m=concrete_at_sp_fire(self.concrete,T,self.concrete_norm)
            self.assertEqual(m.strength_factor,0.)
            self.assertEqual(m.modulus_factor,0.)
            self.assertEqual(m.strength_MPa,0.)
            self.assertEqual(m.elastic_modulus_MPa,0.)
            self.assertEqual(m.policy,ZERO_POLICY)
            self.assertEqual(m.status,"ZERO_ABOVE_SP_TABLE9")
            for strain in (-.02,0.,.001,.1):
                sigma,Et,epsu,_=concrete_stress_sp(
                    strain,T,self.concrete,self.concrete_norm)
                self.assertEqual((sigma,Et,epsu),(0.,0.,None))

    def test_sp_siliceous_factors_are_not_eurocode_at_500(self):
        m=concrete_at_sp_fire(self.concrete,500.,self.concrete_norm)
        self.assertAlmostEqual(m.strength_factor,.80)
        self.assertAlmostEqual(m.modulus_factor,.30)
        self.assertAlmostEqual(m.strength_MPa,24.)
        self.assertAlmostEqual(m.elastic_modulus_MPa,12300.)
        self.assertNotAlmostEqual(m.strength_factor,.60)

    def test_sp_tables_linear_between_nodes_is_recorded_as_assumption(self):
        m=concrete_at_sp_fire(self.concrete,550.,self.concrete_norm)
        self.assertAlmostEqual(m.strength_factor,.7)
        self.assertEqual(m.status,"linear_between_tabulated")

    def test_steel_is_not_zeroed_beyond_800_by_concrete_user_choice(self):
        m=steel_at_sp_fire(self.steel,500.)
        self.assertAlmostEqual(m.strength_factor,.60)
        self.assertAlmostEqual(m.modulus_factor,.80)
        self.assertAlmostEqual(m.strength_MPa,300.)
        self.assertAlmostEqual(m.elastic_modulus_MPa,160000.)
        at800=steel_at_sp_fire(self.steel,800.)
        self.assertAlmostEqual(at800.strength_factor,.10)
        self.assertAlmostEqual(at800.modulus_factor,.65)
        with self.assertRaisesRegex(SPFireMaterialError,"800"):
            steel_at_sp_fire(self.steel,800.001)

    def test_normal_20_C_and_low_temperature_bridge(self):
        m=steel_at_sp_fire(self.steel,20.)
        self.assertAlmostEqual(m.strength_factor,1.)
        self.assertAlmostEqual(m.modulus_factor,1.)
        mid=steel_at_sp_fire(self.steel,100.)
        self.assertAlmostEqual(mid.strength_factor,1.)
        self.assertLess(mid.modulus_factor,1.)
        self.assertIn("bridge",mid.status)

    def test_parabolic_linear_concrete_SP5_permitted_branch(self):
        p=concrete_at_sp_fire(self.concrete,500.,self.concrete_norm)
        eps2=self.concrete_norm["eps_c2_permille"]/1000.
        epsu=self.concrete_norm["eps_cu2_permille"]/1000.
        sigma,tan,u,mat=concrete_stress_sp(
            eps2/2.,500.,self.concrete,self.concrete_norm)
        self.assertAlmostEqual(sigma,p.strength_MPa*(1.-.5**2),places=8)
        self.assertGreater(tan,0.)
        self.assertAlmostEqual(u,epsu)
        peak,Et,_,_=concrete_stress_sp(
            eps2,500.,self.concrete,self.concrete_norm)
        self.assertAlmostEqual(peak,p.strength_MPa)
        self.assertEqual(Et,0.)
        above,_,_,_=concrete_stress_sp(
            epsu+.0001,500.,self.concrete,self.concrete_norm)
        self.assertAlmostEqual(above,p.strength_MPa) # model-only outside ULS

    def test_sp_steel_bilinear_hard_horizontal_branch(self):
        sigma,Et,_=steel_stress_sp(.0001,500.,self.steel)
        self.assertAlmostEqual(sigma,16.)
        self.assertAlmostEqual(Et,160000.)
        plus,Et,_=steel_stress_sp(.1,500.,self.steel)
        minus,_,_=steel_stress_sp(-.1,500.,self.steel)
        self.assertEqual(plus,300.)
        self.assertEqual(minus,-300.)
        self.assertEqual(Et,0.)

    def test_sp_thermal_strain_integral_equation6(self):
        self.assertAlmostEqual(steel_free_thermal_strain_sp(20.),0.)
        self.assertAlmostEqual(steel_free_thermal_strain_sp(500.),.006144)
        self.assertAlmostEqual(steel_free_thermal_strain_sp(800.),.010569)
        with self.assertRaises(SPFireMaterialError):
            steel_free_thermal_strain_sp(801.)

    def test_sp_concrete_alpha_has_explicit_signed_interpretation(self):
        sil=concrete_free_thermal_strain_sp(500.,"siliceous")
        cal=concrete_free_thermal_strain_sp(500.,"calcareous")
        self.assertGreater(sil,0.)
        self.assertGreater(cal,0.)
        self.assertGreater(sil,concrete_free_thermal_strain_sp(200.,"siliceous"))
        self.assertIsNone(concrete_free_thermal_strain_sp(801.,"siliceous"))
        self.assertNotAlmostEqual(
            sil,concrete_free_thermal_strain_sp(
                500.,"siliceous",signed_shrinkage=False),places=8)

    def test_qualification_explicitly_denies_R_t(self):
        q=qualification_status()
        self.assertTrue(q["sp_table9_above_800_is_assumption_not_normative"])
        self.assertFalse(q["thermal_transport_qualified_sp2026"])
        self.assertFalse(q["full_member_capacity_U_t_qualified"])
        self.assertFalse(q["first_failure_t_R_qualified"])
        self.assertFalse(q["normative_claim"])


class HeatedSPSectionCouplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column=make_column(user_inputs())
        cls.column["fire_minutes"]=30.
        cls.thermal=solve_tkp_2d_heat(cls.column,
            boundary=reference_annex_a_boundary(moisture_mass_pct=1.5),
            cell_count_x=8,cell_count_y=8,
            sample_times_minutes=[30.],max_step_minutes=3.)
        cls.snap=select_tkp_snapshot(cls.thermal,30.)
        cls.prepared=prepare_sp2026_section(cls.column,cls.snap,grid=8)

    def test_field_is_time_matched_and_actual_eight_bars(self):
        p=self.prepared
        self.assertEqual(len(p.theta_c),64)
        self.assertEqual(len(p.theta_s),8)
        self.assertEqual(len(p.bar_ids),8)
        self.assertEqual(p.source["SP_fire"][:2],"СП")
        self.assertIn("UNQUALIFIED_AS_SP",p.source["thermal"])
        self.assertTrue(np.all(p.theta_s<=800.))

    def test_force_tangent_and_result_are_finite(self):
        p=self.prepared
        F,J,info=p.force_and_tangent(np.array([-.001,0.,0.]),include_maps=True)
        self.assertEqual(F.shape,(3,))
        self.assertEqual(J.shape,(3,3))
        self.assertTrue(np.all(np.isfinite(F)))
        self.assertTrue(np.all(np.isfinite(J)))
        self.assertEqual(len(info["map"]["concrete_stress_MPa"]),64)
        self.assertEqual(len(info["map"]["steel_stress_MPa"]),8)
        self.assertFalse(info["normative_claim"])
        self.assertTrue(info["user_zero_tail_not_SP_tabulated"])

    def test_zero_tail_is_applied_to_real_2D_fibre_stress_and_tangent(self):
        import copy
        p=copy.deepcopy(self.prepared)
        # Isolate exactly one hot concrete fibre without changing actual
        # reinforcement temperatures and material-source resolution.
        p.theta_c[:]=20.
        p.eps_th_c[:]=0.
        p.theta_cb[:]=20.
        p.eps_th_cb[:]=0.
        p.theta_s[:]=20.
        p.eps_th_s[:]=0.
        p.theta_c[0]=800.
        before,_,meta_before=p.force_and_tangent(
            np.array([.001,0.,0.]),include_maps=True)
        self.assertGreater(meta_before['map']['concrete_stress_MPa'][0],0.)
        self.assertEqual(meta_before['zero_strength_concrete_fibre_count'],0)
        p.theta_c[0]=800.000001
        after,J,meta_after=p.force_and_tangent(
            np.array([.001,0.,0.]),include_maps=True)
        self.assertEqual(meta_after['map']['concrete_stress_MPa'][0],0.)
        self.assertEqual(meta_after['zero_strength_concrete_fibre_count'],1)
        self.assertAlmostEqual(
            before[0]-after[0],
            meta_before['map']['concrete_stress_MPa'][0]
                *p.area[0]*1000.,places=7)
        self.assertTrue(np.all(np.isfinite(J)))

    def test_mechanism_integration_never_certifies_member(self):
        report=evaluate_sp2026_section_at_time(
            self.column,self.snap,grid=8)
        self.assertEqual(report["time_minutes"],30.)
        self.assertIsNone(report["R_t_minutes"])
        self.assertIsNone(report["member_utilization_U_t"])
        self.assertFalse(report["normative_claim"])
        self.assertEqual(report["regulatory_result"],"NOT_ESTABLISHED")
        self.assertEqual(len(report["sections"]),1)

    def test_only_concrete_zero_no_steel_above800_allowed(self):
        # The explicit >800 concrete zero state does NOT prescribe a steel
        # extension. This surface-temperature domain check belongs to SP-R.2.
        self.assertTrue(all(t<=800 for t in self.prepared.theta_s))


if __name__=="__main__":
    unittest.main()
