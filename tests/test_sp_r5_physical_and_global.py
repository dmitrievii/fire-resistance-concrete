"""SP-R5 material law and equilibrium GLOBAL eigen stability verification.

Physical-law SOURCE vs source-unsupported hot peak/creep assumptions
are deliberately separate from numerical exact-solution benchmarks.
No test can emit a normative structural-fire R(t) certificate.
"""
import copy
import math
import unittest
import numpy as np

from test_sp_r3_member import SPR3ActualMemberNumerics

from rc_fire.materials.normative import ConcreteMix,Reinforcement,normal_concrete
from rc_fire.materials.sp2026_fire import SPFireMaterialError
from rc_fire.materials.sp2026_full_nonlinear import (
    full_concrete_sp_parameters, concrete_full_nonlinear_stress_sp,
    SP5RebarDuctility,steel_sp5_ascending_stress,MODE)
from rc_fire.mechanics.sp2026_section import (
    prepare_sp2026_section,prepare_sp2026_full_nonlinear_section)
from rc_fire.member.sp2026_global_stability import (
    STABLE,UNSTABLE,UNKNOWN,
    perfect_elastic_euler_global_stability,
    bracket_perfect_euler_first_global_instability,
    check_global_equilibrium_tangent)
from rc_fire.member.coupled import EndSupport,LinearSectionLaw
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat,select_sp2026_snapshot,reference_sp2026_boundary)


class TestSP5PhysicalSourceConstitutive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.concrete=ConcreteMix("C30/37",aggregate_family="siliceous",
                                 independently_measured_Ecm_GPa=32.)
        cls.normal=normal_concrete(cls.concrete)

    def test_full_source_613_peak_and_tangent_615(self):
        pars=full_concrete_sp_parameters(20.,self.concrete,self.normal)
        e1=pars["epsilon_c1_assumed_temperature_invariant"]
        k=pars["shape_parameter_k"]
        self.assertGreater(k,1.)
        s,ds,eu,mat=concrete_full_nonlinear_stress_sp(
            e1,20.,self.concrete,self.normal)
        self.assertAlmostEqual(s,pars["fcm_theta_MPa"],places=5)
        self.assertAlmostEqual(ds,0.,delta=1.e-5)
        self.assertGreater(eu,e1)
        h=1.e-7
        qplus=concrete_full_nonlinear_stress_sp(
            .0008+h,20.,self.concrete,self.normal)[0]
        qminus=concrete_full_nonlinear_stress_sp(
            .0008-h,20.,self.concrete,self.normal)[0]
        fd=(qplus-qminus)/(2*h)
        deriv=concrete_full_nonlinear_stress_sp(
            .0008,20.,self.concrete,self.normal)[1]
        self.assertLess(abs(fd-deriv)/max(1.,abs(deriv)),1.e-6)
        self.assertAlmostEqual(
            1.1*pars["Ecm_n_hot_MPa"],
            k*pars["fcm_theta_MPa"]/e1,places=4)
        self.assertFalse(pars["temperature_peak_strain_qualified"])

    def test_hot_beta_strength_reduction_cannot_keep_ambient_peak_if_singular(self):
        # The *source-absent* hot eps_c1 is a physical blocker, NOT a
        # numeric parameter silently fixed to make the full law fit.
        pars=full_concrete_sp_parameters(500.,self.concrete,self.normal)
        self.assertLessEqual(pars["shape_parameter_k"],1.)
        with self.assertRaises(SPFireMaterialError):
            concrete_full_nonlinear_stress_sp(
                .001,500.,self.concrete,self.normal)
        # Independent user-selected concrete zero strength above Table 9.
        value=concrete_full_nonlinear_stress_sp(
            .01,801.,self.concrete,self.normal)
        self.assertEqual(value[0],0.)
        self.assertEqual(value[1],0.)
        self.assertIsNone(value[2])

    def test_source_complete_rising_steel_is_continuous_and_strain_bounded(self):
        steel=Reinforcement(grade="S500")
        measured=SP5RebarDuctility(
            1.08,.05,1.15,
            material_certificate="research fixture, NOT actual hot material validation")
        E=200000.
        fy=500./1.15
        ey=fy/E
        s,Et,eu,mat,evidence=steel_sp5_ascending_stress(
            ey,20.,steel,ductility=measured)
        self.assertAlmostEqual(s,fy,places=4)
        self.assertAlmostEqual(Et,E,places=4)
        self.assertAlmostEqual(eu,.045,places=8)
        s2,_,_,_,_=steel_sp5_ascending_stress(
            ey+1.e-7,20.,steel,ductility=measured)
        self.assertLess(abs(s2-s),.005)
        peak,_,_,_,_=steel_sp5_ascending_stress(
            eu,20.,steel,ductility=measured)
        self.assertAlmostEqual(peak,fy*1.08,places=4)
        with self.assertRaises(SPFireMaterialError):
            steel_sp5_ascending_stress(
                eu+1.e-5,20.,steel,ductility=measured)
        self.assertFalse(evidence["hot_ductility_temperature_qualified"])

    def test_full_nonlinear_section_remains_distinct_from_simplified_SP5_section(self):
        SPR3ActualMemberNumerics.setUpClass()
        c=copy.deepcopy(SPR3ActualMemberNumerics.column)
        c["fire_minutes"]=1.
        heat=solve_sp2026_2d_heat(
            c,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
            cell_count_x=8,cell_count_y=8,max_step_minutes=1.,
            sample_times_minutes=[1.])
        snapshot=select_sp2026_snapshot(heat,1.)
        simplified=prepare_sp2026_section(c,snapshot,grid=8)
        full=prepare_sp2026_full_nonlinear_section(c,snapshot,grid=8)
        F,J,meta=full.force_and_tangent([.0008,0.,0.])
        self.assertTrue(np.all(np.isfinite(F)))
        self.assertTrue(np.all(np.isfinite(J)))
        self.assertEqual(meta["constitutive_mode"],MODE)
        self.assertFalse(meta["temperature_dependent_peak_and_ultimate_strain_qualified"])
        Fs,Js,ms=simplified.force_and_tangent([.0008,0.,0.])
        self.assertNotEqual(ms["constitutive_mode"],MODE)
        self.assertFalse(np.allclose(F,Fs))
        self.assertFalse(meta["normative_claim"])


class TestGlobalStructuralStability(unittest.TestCase):
    def test_global_energy_eigenvalue_detects_both_sides_of_Euler_failure(self):
        left=perfect_elastic_euler_global_stability(axial_ratio=.70,node_count=13)
        right=perfect_elastic_euler_global_stability(axial_ratio=1.20,node_count=13)
        self.assertEqual(left["status"],STABLE)
        self.assertEqual(right["status"],UNSTABLE)
        self.assertTrue(left["is_equilibrium"])
        self.assertTrue(right["is_equilibrium"])
        self.assertGreater(left["smallest_relative_global_tangent_eigenvalue"],0.)
        self.assertLess(right["smallest_relative_global_tangent_eigenvalue"],0.)
        self.assertFalse(left["is_first_global_physical_failure"])
        self.assertFalse(right["constitutive_stiffness_independently_validated"])

    def test_independent_first_Euler_bifurcation_spectral_bracket(self):
        result=bracket_perfect_euler_first_global_instability(
            node_count=13,start_ratio=.75,end_ratio=1.25,
            tolerance_ratio=.002,max_refinements=16)
        self.assertIn(result["status"],(
            "EULER_FIRST_GLOBAL_SPECTRAL_BRACKET",
            "EULER_BIFURCATION_NEAR_SINGULAR_REFINEMENT_STOP"))
        self.assertLess(result["last_strictly_stable_N_by_Ncrit"],1.01)
        self.assertGreater(result["first_unstable_N_by_Ncrit"],.99)
        self.assertLess(
            result["first_unstable_N_by_Ncrit"]
            -result["last_strictly_stable_N_by_Ncrit"],.005)
        self.assertFalse(result["normative_claim"])

    def test_global_tangent_at_non_equilibrium_cannot_claim_instability(self):
        n=5;z=np.linspace(0.,3.,n)
        D=LinearSectionLaw(np.diag([900.,900.]),
            provenance="independent elastic diagnostic")
        evidence=check_global_equilibrium_tangent(
            z,200.,lambda i,j:D,
            left=EndSupport("pinned"),right=EndSupport("pinned"),
            distributed_load_kNpm=[[3.,0.]]*n,
            nodal_forces=np.zeros(4*n),
            initial_imperfection=np.zeros(4*n),
            displacements=np.zeros(4*n))
        self.assertEqual(evidence["status"],UNKNOWN)
        self.assertFalse(evidence["is_equilibrium"])
        self.assertFalse(evidence["normative_claim"])


if __name__=="__main__":
    unittest.main()
