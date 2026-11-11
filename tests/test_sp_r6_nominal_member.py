"""SP-R6 exact SP5 nominal stiffness and separate nonuniform fire extension.

Numerical verification is not the legal/physical release of fire R(t).
"""
import copy
import math
import unittest
import numpy as np
from types import SimpleNamespace

from rc_fire.materials.normative import (
    ConcreteMix,Reinforcement,normal_concrete,normal_reinforcement)
from rc_fire.thermal.sp2026_heat import select_sp2026_snapshot
from rc_fire.mechanics.sp2026_nominal_member import (
    SP5FireDesignFactors,SP5NominalMemberError,
    design_parameters,exact_sp5_nominal_axis,
    effective_creep_coefficient_sp5,
    prepare_sp2026_design_section,nonuniform_sp5_nominal_axis,
    assess_sp5_nominal_column_at_fire,scan_sp5_nominal_member_history,
    verify_sp5_nominal_grid_convergence,
    WITHIN,EXCEEDED,UNKNOWN)


class SP5LiteralNominalStiffness(unittest.TestCase):
    def test_sp5_special_design_materials_not_characteristic_strength(self):
        c=normal_concrete(ConcreteMix("C30/37",
            aggregate_family="siliceous",
            independently_measured_Ecm_GPa=32.))
        s=normal_reinforcement(Reinforcement(grade="S500"))
        p=design_parameters(c,s)
        self.assertAlmostEqual(p["alpha_cc"],1.)
        self.assertAlmostEqual(p["gamma_c"],1.2)
        self.assertAlmostEqual(p["gamma_s"],1.)
        self.assertAlmostEqual(p["fcd_20_MPa"],25.)
        self.assertAlmostEqual(p["fyd_20_MPa"],500.)
        self.assertAlmostEqual(p["Ecd_20_MPa"],32000./1.2)
        self.assertAlmostEqual(p["Es_20_MPa"],200000.)
        with self.assertRaises(ValueError):
            design_parameters(c,s,SP5FireDesignFactors(gamma_c=1.5))

    def test_sp5_854_864_against_closed_form(self):
        Ac=.4*.6
        Ic=.4*.6**3/12
        Is=4*(math.pi*(.02**2)/4)*.2**2
        N=250.
        L=3.
        fck=30.; fcd=25.;ec=26666.6666666667
        es=200000.;phi=.6
        r=exact_sp5_nominal_axis(
            N_kN=N,fck_MPa=fck,fcd_MPa=fcd,
            Ecd_MPa=ec,Es_MPa=es,Ic_m4=Ic,Is_m4=Is,
            Ac_m2=Ac,length_m=L,mu=1.,
            effective_creep_phi=phi)
        lam=L/math.sqrt(Ic/Ac)
        n=N/(1000*Ac*fcd)
        kc=math.sqrt(fck/20.)*min(.2,n*lam/170.)/(1+phi)
        B=(kc*ec*Ic+es*Is)*1000
        ncr=math.pi**2*B/L**2
        self.assertAlmostEqual(r["lambda_a"],lam)
        self.assertAlmostEqual(r["k1a"],math.sqrt(fck/20.))
        self.assertAlmostEqual(r["k2a"],n*lam/170.)
        self.assertAlmostEqual(r["kc_nominal"],kc)
        self.assertAlmostEqual(r["Bnom_kNm2"],B)
        self.assertAlmostEqual(r["Ncr_kN"],ncr)
        self.assertAlmostEqual(r["eta_a"],1./(1.-N/ncr))
        self.assertFalse(r["normative_claim"])

    def test_sp5_864_creep_from_actual_first_order_moment_ratio(self):
        calculated=effective_creep_coefficient_sp5(
            phi_infty=2.,M0Eqp_kNm=40.,M0Ed_kNm=100.)
        self.assertAlmostEqual(calculated["phi_eff"],.8)
        self.assertAlmostEqual(calculated["moment_ratio"],.4)
        self.assertFalse(calculated["fire_temperature_creep_history_qualified"])
        for par in (
            dict(phi_infty=2.,M0Eqp_kNm=40.,M0Ed_kNm=0.),
            dict(phi_infty=2.,M0Eqp_kNm=-40.,M0Ed_kNm=100.),
            dict(phi_infty=-.2,M0Eqp_kNm=40.,M0Ed_kNm=100.)):
            with self.subTest(params=par):
                with self.assertRaises(ValueError):
                    effective_creep_coefficient_sp5(**par)

    def test_no_amplification_factor_on_or_beyond_nominal_critical(self):
        r=exact_sp5_nominal_axis(
            N_kN=100000.,fck_MPa=30.,fcd_MPa=25.,
            Ecd_MPa=20000.,Es_MPa=200000.,
            Ic_m4=.002,Is_m4=.00005,Ac_m2=.16,
            length_m=6.,mu=1.,effective_creep_phi=0.)
        self.assertFalse(r["N_below_nominal_critical"])
        self.assertIsNone(r["eta_a"])
        self.assertEqual(r["when_N_at_or_above_Ncr"],
                         "OUTSIDE_NOMINAL_AMPLIFICATION_DOMAIN")

    def test_exact_homogeneous_temperature_quadrature_matches_closed_form(self):
        family="siliceous"
        concrete=ConcreteMix("C30/37",aggregate_family=family,
                             independently_measured_Ecm_GPa=32.)
        steel=Reinforcement(grade="S500")
        normalc=normal_concrete(concrete)
        normals=normal_reinforcement(steel)
        params=design_parameters(normalc,normals)
        b=.4;h=.5;g=8;T=20.
        xx=(np.arange(g)+.5)*b/g
        yy=(np.arange(g)+.5)*h/g
        X,Y=np.meshgrid(xx,yy,indexing="xy")
        bars_x=np.asarray([.05,.35,.05,.35])
        bars_y=np.asarray([.05,.05,.45,.45])
        As=np.full(4,math.pi*.02**2/4.)
        p=SimpleNamespace(
            b_m=b,h_m=h,area=np.full(g*g,b*h/(g*g)),
            x=X.ravel(),y=Y.ravel(),theta_c=np.full(g*g,T),
            bar_area=As,bar_x=bars_x,bar_y=bars_y,
            theta_s=np.full(4,T),
            sp_concrete=concrete,sp_steel=steel,
            sp_concrete_normal=normalc,sp_steel_normal=normals,
            sp5_design_parameters=params)
        r=nonuniform_sp5_nominal_axis(
            p,N_kN=200.,length_m=3.,mu_x=1.,mu_y=1.,
            effective_creep_phi=0.5)
        self.assertEqual(r["scope"],"ISOTHERMAL_NUMERIC_QUADRATURE")
        for axis,Ic,coordinate in (
            ("x",b*h**3/12,bars_y-h/2.),
            ("y",h*b**3/12,bars_x-b/2.)):
            Is=float(np.dot(As,coordinate**2))
            exact=exact_sp5_nominal_axis(
                N_kN=200.,fck_MPa=30.,
                fcd_MPa=params["fcd_20_MPa"],
                Ecd_MPa=params["Ecd_20_MPa"],
                Es_MPa=params["Es_20_MPa"],
                Ic_m4=Ic,Is_m4=Is,Ac_m2=b*h,
                length_m=3.,mu=1.,effective_creep_phi=.5)
            self.assertAlmostEqual(r[axis]["Bnom_kNm2"],
                                   exact["Bnom_kNm2"],delta=1e-7)
            self.assertAlmostEqual(r[axis]["eta_a"],
                                   exact["eta_a"],delta=1e-10)
        # Different surface temperatures must NOT be mislabelled as
        # uniform even though the same material source functions apply.
        p.theta_c[0]=500.
        other=nonuniform_sp5_nominal_axis(
            p,N_kN=200.,length_m=3.,effective_creep_phi=.5)
        self.assertEqual(other["scope"],
                         "NONUNIFORM_NUMERICAL_EXTENSION_NOT_PRESCRIBED")
        self.assertFalse(other["normative_nonuniform_member_method_qualified"])
        self.assertFalse(other["axis_decoupling_verified_numerically"])
        self.assertEqual(other["x"]["status"],"AXIS_COUPLING_UNRESOLVED")
        self.assertEqual(other["y"]["status"],"AXIS_COUPLING_UNRESOLVED")
        self.assertIsNone(other["x"]["eta_a"])
        self.assertIsNone(other["y"]["Ncrit_kN"])
        self.assertIn("EIxy",other["qualification_blocker"])


class SP5ActualHeatedColumn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_sp_r3_member import SPR3ActualMemberNumerics,make_explicit_spec
        SPR3ActualMemberNumerics.setUpClass()
        cls.column=copy.deepcopy(SPR3ActualMemberNumerics.column)
        cls.snapshot=select_sp2026_snapshot(
            SPR3ActualMemberNumerics.heat,5.)
        cls.spec=make_explicit_spec(cls.column)

    def test_real_hot_section_design_source_reduces_forces_at_same_strain(self):
        from rc_fire.mechanics.sp2026_section import prepare_sp2026_section
        p0=prepare_sp2026_section(self.column,self.snapshot,grid=8)
        p1=prepare_sp2026_design_section(self.column,self.snapshot,grid=8)
        self.assertEqual(p1.sp_constitutive_mode,
                         "SP5_6_1_5_4_DESIGN_SECTION_AT_FIRE")
        f0,_,_=p0.force_and_tangent([.001,0.,0.])
        f1,_,meta=p1.force_and_tangent([.001,0.,0.])
        self.assertLess(f1[0],f0[0])
        self.assertFalse(meta["normative_claim"])

    def test_actual_SP_heat_nominal_B_eta_and_section_equilibrium(self):
        r=assess_sp5_nominal_column_at_fire(
            self.column,self.snapshot,self.spec,grid=8,
            effective_creep_phi=0.)
        self.assertIn(r["status"],(WITHIN,EXCEEDED,UNKNOWN,
           "N_AT_OR_ABOVE_NOMINAL_NCR_UNRESOLVED_MEMBER_CAPACITY"))
        self.assertEqual(r["nominal_second_order"]["scope"],
                         "NONUNIFORM_NUMERICAL_EXTENSION_NOT_PRESCRIBED")
        self.assertIn("x",r["nominal_second_order"])
        self.assertIn("y",r["nominal_second_order"])
        self.assertIsNone(r["actual_t_R_minutes"])
        self.assertIsNone(r["actual_member_capacity_U_t"])
        self.assertEqual(r["regulatory_result"],"NOT_ESTABLISHED")
        self.assertFalse(r["normative_claim"])

    def test_true_asymmetric_sp_heat_blocks_independent_scalar_eta(self):
        from rc_fire.thermal.sp2026_heat import (
            solve_sp2026_2d_heat,reference_sp2026_boundary)
        from test_sp_r3_member import make_explicit_spec
        case=copy.deepcopy(self.column)
        case["thermal_spec"]["exposed_faces"]=["left","top"]
        actual=solve_sp2026_2d_heat(
            case,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
            cell_count_x=8,cell_count_y=8,max_step_minutes=2.5,
            sample_times_minutes=[10.])
        local=select_sp2026_snapshot(actual,10.)
        result=assess_sp5_nominal_column_at_fire(
            case,local,make_explicit_spec(case),grid=8,
            effective_creep_phi=0.)
        nominal=result["nominal_second_order"]
        self.assertEqual(result["status"],
                         "BLOCKED_BIAXIAL_NOMINAL_AXIS_COUPLING")
        self.assertFalse(nominal["axis_decoupling_verified_numerically"])
        self.assertIsNone(nominal["x"]["eta_a"])
        self.assertIsNone(nominal["y"]["Ncrit_kN"])
        self.assertIsNone(result["actual_t_R_minutes"])
        self.assertFalse(result["normative_claim"])

    def test_actual_thermal_fibre_resolution_three_mesh_qualification(self):
        result=verify_sp5_nominal_grid_convergence(
            self.column,self.snapshot,self.spec,grids=(8,12,16),
            effective_creep_phi=0.,relative_tolerance=.05)
        self.assertEqual([p["fibre_grid"] for p in result["grids"]],
                         [8,12,16])
        self.assertEqual(len(result["pairwise_comparisons"]),4)
        self.assertTrue(result["source_SP2D_thermal_grid_is_frozen"])
        self.assertFalse(result["independent_heat_mesh_or_time_convergence_qualified"])
        self.assertFalse(result["normative_member_qualification"])
        self.assertIsNone(result["actual_t_R_minutes"])
        self.assertFalse(result["normative_claim"])

    def test_reject_non_pin_or_unreconciled_eccentricity(self):
        spec=copy.deepcopy(self.spec)
        spec["left_support"]["x"]="fixed"
        with self.assertRaises(ValueError):
            assess_sp5_nominal_column_at_fire(
                self.column,self.snapshot,spec,grid=8)
        with self.assertRaises(ValueError):
            assess_sp5_nominal_column_at_fire(
                self.column,self.snapshot,self.spec,grid=8,
                minimum_eccentricity_enforced=False)


class SP5PublicSP2026Workflow(unittest.TestCase):
    def test_full_facade_nominal_route_and_independent_fire_history(self):
        from test_r07_public_workflow import user_inputs
        from rc_fire.integration.r07_inputs import (
            make_column,explicit_pinned_uniform_sp2026_member)
        from rc_fire.integration.r07_public import fire_assessment
        c=make_column(user_inputs())
        c["fire_minutes"]=30.
        spec=explicit_pinned_uniform_sp2026_member(
            c,confirmed_pinned_uniform_action_model=True,
            confirmed_uniform_longitudinal_fire=True,
            imperfection_x_mm=6.,imperfection_y_mm=3.)
        spec["nominal_sp5_requested"]=True
        spec["nominal_sp5_phi_eff"]=0.
        spec["nominal_sp5_creep_provenance"]=(
            "explicit short-term fire phi=0 numerical comparison scenario")
        spec["nominal_sp5_history_requested"]=True
        spec["nominal_sp5_grid_study_requested"]=True
        c["member_spec"]=spec
        report=fire_assessment(
            c,required_minutes=30.,steel_route="hot_rolled",
            ductility_class="B",moisture_mass_pct=1.5,
            grid=8,dt_minutes=3.)
        result=report["sp2026_stage6_sp5_nominal_at_required_time"]
        self.assertIsNotNone(result,report["sp2026_stage6_sp5_nominal_blocker"])
        self.assertIn(result["status"],(WITHIN,EXCEEDED,UNKNOWN,
             "N_AT_OR_ABOVE_NOMINAL_NCR_UNRESOLVED_MEMBER_CAPACITY"))
        self.assertIn(result["nominal_second_order"]["scope"],(
            "NONUNIFORM_NUMERICAL_EXTENSION_NOT_PRESCRIBED",
            "ISOTHERMAL_NUMERIC_QUADRATURE"))
        self.assertFalse(result["nominal_second_order"]["normative_claim"])
        self.assertEqual(result["effective_creep_phi_provenance"],
                         spec["nominal_sp5_creep_provenance"])
        history=report["sp2026_stage6_sp5_nominal_history"]
        self.assertIsNotNone(history,report["sp2026_stage6_sp5_nominal_history_blocker"])
        self.assertEqual([round(s["time_minutes"]) for s in history["samples"]],
                         [10,20,30])
        convergence=report["sp2026_stage6_sp5_nominal_grid_study"]
        self.assertIsNotNone(
            convergence,report["sp2026_stage6_sp5_nominal_grid_blocker"])
        self.assertEqual([p["fibre_grid"] for p in convergence["grids"]],
                         [8,12,16])
        self.assertFalse(convergence["normative_member_qualification"])
        self.assertIsNone(history["actual_t_R"])
        self.assertIsNone(report["sp2026_stage6_certified_U_member_t"])
        self.assertIsNone(report["sp2026_stage6_certified_R_t_minutes"])
        self.assertIsNone(report["R_t_minutes"])
        self.assertEqual(report["regulatory_result"],"NOT_ESTABLISHED")

    def test_nominal_route_requires_explicit_phi_source(self):
        from test_r07_public_workflow import user_inputs
        from rc_fire.integration.r07_inputs import (
            make_column,explicit_pinned_uniform_sp2026_member)
        from rc_fire.integration.r067 import MemberEvidenceInputError,validate_member_spec
        c=make_column(user_inputs())
        spec=explicit_pinned_uniform_sp2026_member(
            c,confirmed_pinned_uniform_action_model=True,
            confirmed_uniform_longitudinal_fire=True,
            imperfection_x_mm=6.,imperfection_y_mm=3.)
        spec["nominal_sp5_requested"]=True
        with self.assertRaises((MemberEvidenceInputError,ValueError)):
            validate_member_spec(spec)
        spec["nominal_sp5_phi_eff"]=0.
        with self.assertRaises((MemberEvidenceInputError,ValueError)):
            validate_member_spec(spec)
        spec["nominal_sp5_creep_provenance"]="explicit research short-term"
        self.assertTrue(validate_member_spec(spec)["nominal_sp5_requested"])
        invalid=copy.deepcopy(spec)
        invalid["nominal_sp5_requested"]=False
        invalid["nominal_sp5_grid_study_requested"]=True
        with self.assertRaises((MemberEvidenceInputError,ValueError)):
            validate_member_spec(invalid)

    def test_stored_SP_thermal_time_history_keeps_nominal_assumptions(self):
        from test_sp_r3_member import SPR3ActualMemberNumerics,make_explicit_spec
        SPR3ActualMemberNumerics.setUpClass()
        c=SPR3ActualMemberNumerics.column
        spec=make_explicit_spec(c)
        out=scan_sp5_nominal_member_history(
            c,SPR3ActualMemberNumerics.heat,spec,[5.,10.],
            grid=8,effective_creep_phi=0.)
        self.assertEqual([s["time_minutes"] for s in out["samples"]],
                         [5.,10.])
        self.assertFalse(out["temperature_interpolation_used"])
        self.assertIsNone(out["actual_U_t"])
        self.assertIsNone(out["actual_t_R"])
        self.assertFalse(out["normative_claim"])
        with self.assertRaises(ValueError):
            scan_sp5_nominal_member_history(
                c,SPR3ActualMemberNumerics.heat,spec,[5.,7.],
                grid=8,effective_creep_phi=0.)


if __name__=="__main__":
    unittest.main()
