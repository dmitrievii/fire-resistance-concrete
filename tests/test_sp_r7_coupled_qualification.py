"""SP-R7: source 3x3 secant vs beta, coupled nominal and real SP heat.

The positive tests verify a numerical method, not certification of R(t).
"""
import copy
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

from rc_fire.materials.normative import (
    ConcreteMix,Reinforcement,normal_concrete,normal_reinforcement)
from rc_fire.mechanics.sp2026_nominal_member import (
    design_parameters,exact_sp5_nominal_axis,
    prepare_sp2026_design_section)
from rc_fire.mechanics.sp2026_coupled_rigidity import (
    coupled_sp5_hot_section_stiffness,
    magnify_coupled_first_order_moments,
    audit_independent_global_coupled_euler)
from rc_fire.mechanics.sp2026_coupled_first_limit import (
    assess_coupled_sp5_nominal_at_time,
    scan_coupled_first_model_limit,
    refine_first_coupled_model_limit_with_new_sp_heat,
    WITHIN,EXCEEDED,NOMINAL,UNKNOWN)
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat,reference_sp2026_boundary,
    select_sp2026_snapshot)
from rc_fire.verification.sp2026_r7_qualification import (
    audit_sp2026_heat_mesh_and_time,audit_effective_creep_source,
    load_existing_fire_column_catalog,qualification_ledger)


def synthetic_source_section():
    concrete=ConcreteMix(
        "C30/37",aggregate_family="siliceous",
        independently_measured_Ecm_GPa=32.)
    steel=Reinforcement(grade="S500")
    nc=normal_concrete(concrete);ns=normal_reinforcement(steel)
    b=.4;h=.5;grid=8
    xx=(np.arange(grid)+.5)*b/grid
    yy=(np.arange(grid)+.5)*h/grid
    X,Y=np.meshgrid(xx,yy,indexing="xy")
    bx=np.array([.05,.35,.05,.35])
    by=np.array([.05,.05,.45,.45])
    area=np.full(grid*grid,b*h/(grid**2))
    bars=np.full(4,math.pi*.02**2/4.)
    return SimpleNamespace(
        b_m=b,h_m=h,x=X.ravel(),y=Y.ravel(),
        area=area,theta_c=np.full(grid**2,20.),
        bar_x=bx,bar_y=by,bar_area=bars,
        theta_s=np.full(4,20.),theta_cb=np.full(4,20.),
        sp_concrete=concrete,sp_steel=steel,
        sp_concrete_normal=nc,sp_steel_normal=ns,
        sp5_design_parameters=design_parameters(nc,ns))


class TestCoupledSP5SourceMatrix(unittest.TestCase):
    def test_isothermal_3x3_exactly_reduces_to_both_scalar_SP5_axes(self):
        p=synthetic_source_section()
        N=200.;L=3.;phi=.5
        r=coupled_sp5_hot_section_stiffness(
            p,N_kN=N,length_m=L,effective_creep_phi=phi)
        D=np.asarray(r["nominal_2x2_D_kNm2"])
        K=np.asarray(r["full_3x3_K"])
        self.assertEqual(K.shape,(3,3))
        self.assertTrue(np.allclose(K,K.T))
        self.assertTrue(np.all(np.linalg.eigvalsh(D)>0.))
        self.assertAlmostEqual(D[0,1],0.,delta=1e-9)
        self.assertAlmostEqual(K[0,1],0.,delta=1e-8)
        self.assertAlmostEqual(K[0,2],0.,delta=1e-8)
        self.assertFalse(r["cross_axis_coupling_present"])
        for i,axis,Ic,coord in (
            (0,"x",p.b_m*p.h_m**3/12,p.bar_y-p.h_m/2),
            (1,"y",p.h_m*p.b_m**3/12,p.bar_x-p.b_m/2)):
            Is=float(np.dot(p.bar_area,coord**2))
            scalar=exact_sp5_nominal_axis(
                N_kN=N,fck_MPa=30.,fcd_MPa=25.,
                Ecd_MPa=32000./1.2,Es_MPa=200000.,
                Ic_m4=Ic,Is_m4=Is,Ac_m2=p.b_m*p.h_m,
                length_m=L,mu=1.,effective_creep_phi=phi)
            self.assertAlmostEqual(D[i,i],scalar["Bnom_kNm2"],delta=1e-7)
        self.assertTrue(np.allclose(
            np.sort(r["principal_Euler_Ncrit_kN"]),
            np.sort(math.pi**2*np.diag(D)/L**2),
            atol=1e-8,rtol=1e-12))

    def test_nonuniform_diagonal_cell_hot_EIxy_and_axial_coupling_are_preserved(self):
        p=synthetic_source_section()
        p.theta_c[0]=500.
        r=coupled_sp5_hot_section_stiffness(
            p,N_kN=100.,length_m=3.,effective_creep_phi=.3)
        D=np.asarray(r["nominal_2x2_D_kNm2"])
        self.assertTrue(r["cross_axis_coupling_present"])
        self.assertGreater(abs(D[0,1]),1e-6)
        self.assertGreater(max(abs(x) for x in
            r["nominal_axial_flexural_offsets_m"]),1e-9)
        self.assertTrue(np.all(np.linalg.eigvalsh(D)>0))
        self.assertTrue(np.allclose(D,D.T,atol=1e-8))
        self.assertFalse(r["SP5_8_1_6_nonuniform_fire_method_qualified"])
        # If first-mode Euler criterion is reached, there is NO negative
        # arbitrary eta and no claim a physical fire failure happened.
        over=coupled_sp5_hot_section_stiffness(
            p,N_kN=100000.,length_m=3.,effective_creep_phi=.3)
        self.assertIsNone(over["coupled_amplification_matrix"])
        status=magnify_coupled_first_order_moments(over,[5.,10.])
        self.assertIsNone(status["M2_kNm"])
        self.assertFalse(status["normative_claim"])

    def test_full_global_FE_eigen_solver_qualifies_first_coupled_ideal_mode(self):
        p=synthetic_source_section()
        p.theta_c[0]=300.
        r=coupled_sp5_hot_section_stiffness(
            p,N_kN=100.,length_m=3.,effective_creep_phi=.3)
        audit=audit_independent_global_coupled_euler(
            r,length_m=3.,node_counts=(9,17))
        self.assertEqual(audit["status"],
                         "GLOBAL_COUPLED_FE_FIRST_MODE_NUMERICALLY_VERIFIED")
        self.assertEqual([row["beam_nodes"] for row in audit[
            "global_FE_grid_study"]],[9,17])
        self.assertLess(audit["max_relative_error"],.005)
        self.assertFalse(audit["complete_hot_RC_member_first_failure_qualified"])
        self.assertFalse(audit["regulatory_claim"])

    def test_coupled_amplification_eigenvalues_match_exact_principal_modes(self):
        p=synthetic_source_section()
        p.theta_c[0]=300.
        r=coupled_sp5_hot_section_stiffness(
            p,N_kN=100.,length_m=3.,effective_creep_phi=.3)
        if r["coupled_amplification_matrix"] is None:
            self.skipTest("source nominal N already exceeds first coupled Euler mode")
        D=np.asarray(r["nominal_2x2_D_kNm2"])
        ncrit=np.asarray(r["principal_Euler_Ncrit_kN"])
        calculated=np.asarray(r["coupled_amplification_matrix"])
        exact=np.linalg.inv(np.eye(2)-100.*3.**2/math.pi**2*
                            np.linalg.inv(D))
        self.assertTrue(np.allclose(calculated,exact,rtol=1e-10,atol=1e-10))
        self.assertTrue(np.allclose(
            np.sort(ncrit),np.sort(math.pi**2*np.linalg.eigvalsh(D)/9.)))
        m=magnify_coupled_first_order_moments(r,[15.,7.])
        self.assertTrue(np.allclose(m["M2_kNm"],exact@np.array([15.,7.])))


class TestSP5RealFireSecantAndModelLimit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_sp_r3_member import SPR3ActualMemberNumerics,make_explicit_spec
        SPR3ActualMemberNumerics.setUpClass()
        cls.column=copy.deepcopy(SPR3ActualMemberNumerics.column)
        cls.heat=SPR3ActualMemberNumerics.heat
        cls.snap=select_sp2026_snapshot(cls.heat,5.)
        cls.member_spec=make_explicit_spec(cls.column)

    def test_SP5_design_section_mode_actually_enforces_steel_10permille_ULS(self):
        p=prepare_sp2026_design_section(self.column,self.snap,grid=8)
        _,_,small=p.force_and_tangent([.0006,0.,0.])
        _,_,large=p.force_and_tangent([-.02,0.,0.])
        self.assertIsInstance(small["model_only_strain_limits_satisfied"],bool)
        self.assertFalse(large["model_only_strain_limits_satisfied"])
        self.assertIsNotNone(large["steel_check_tension_ratio"])
        self.assertGreater(large["steel_check_tension_ratio"],1.)
        self.assertTrue(large["model_uls_evidence_complete"])
        self.assertFalse(large["normative_claim"])

    def test_source_section_secant_and_hot_elastic_beta_are_not_same_quantity(self):
        p=prepare_sp2026_design_section(self.column,self.snap,grid=8)
        u=np.array([.0005,0.,0.])
        F,J,meta=p.force_and_tangent(u)
        self.assertTrue(np.all(np.isfinite(J)))
        E=coupled_sp5_hot_section_stiffness(
            p,N_kN=100.,length_m=3.,effective_creep_phi=0.)
        S=coupled_sp5_hot_section_stiffness(
            p,N_kN=100.,length_m=3.,effective_creep_phi=0.,
            kind="SP5_8_1_2_SOURCE_SECANT_AT_EQUILIBRIUM",
            unknowns=u)
        self.assertFalse(np.allclose(
            E["full_3x3_K"],S["full_3x3_K"]))
        self.assertTrue(S["source_section_secant_requires_solved_state"])
        self.assertFalse(S["SP5_8_1_6_nonuniform_fire_method_qualified"])

    def test_true_SP_two_face_field_biaxial_matrix_no_fake_independent_eta(self):
        case=copy.deepcopy(self.column)
        case["thermal_spec"]["exposed_faces"]=["left","top"]
        source=solve_sp2026_2d_heat(
            case,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
            cell_count_x=8,cell_count_y=8,max_step_minutes=2.5,
            sample_times_minutes=[10.])
        snap=select_sp2026_snapshot(source,10.)
        p=prepare_sp2026_design_section(case,snap,grid=8)
        r=coupled_sp5_hot_section_stiffness(
            p,N_kN=100.,length_m=3.,
            effective_creep_phi=0.)
        self.assertTrue(r["cross_axis_coupling_present"])
        self.assertTrue(np.allclose(
            r["nominal_2x2_D_kNm2"],
            np.array(r["nominal_2x2_D_kNm2"]).T))
        self.assertFalse(r["actual_first_physical_failure_qualified"])

    def test_nominal_model_first_event_scan_has_no_certified_failure_time(self):
        mapping={5.:WITHIN,10.:EXCEEDED,15.:WITHIN}
        with patch("rc_fire.mechanics.sp2026_coupled_first_limit."
                   "select_sp2026_snapshot",
                   side_effect=lambda heat,t:{"snapshot":{"time_minutes":t}}):
            with patch("rc_fire.mechanics.sp2026_coupled_first_limit."
                       "assess_coupled_sp5_nominal_at_time",
                       side_effect=lambda col,snap,spec,**kw:{
                           "status":mapping[snap["snapshot"]["time_minutes"]],
                           "time_minutes":snap["snapshot"]["time_minutes"]}):
                r=scan_coupled_first_model_limit(
                    self.column,{},self.member_spec,[5.,10.,15.],
                    grid=8,effective_creep_phi=0.)
        self.assertEqual(r["status"],
                         "OBSERVED_BRACKET_FIRST_MODEL_LIMIT_AFTER_FIRST_SAMPLE")
        self.assertEqual(r["observed_first_model_limit_interval"][
            "last_sampled_model_within_min"],5.)
        self.assertEqual(r["observed_first_model_limit_interval"][
            "first_sampled_model_limit_min"],10.)
        self.assertIsNone(r["t_R_minutes"])
        self.assertTrue(r["unobserved_0_to_first_sample"])
        self.assertFalse(r["normative_claim"])
        mapping[10.]=UNKNOWN
        with patch("rc_fire.mechanics.sp2026_coupled_first_limit."
                   "select_sp2026_snapshot",
                   side_effect=lambda heat,t:{"snapshot":{"time_minutes":t}}):
            with patch("rc_fire.mechanics.sp2026_coupled_first_limit."
                       "assess_coupled_sp5_nominal_at_time",
                       side_effect=lambda col,snap,spec,**kw:{
                           "status":mapping[snap["snapshot"]["time_minutes"]],
                           "time_minutes":snap["snapshot"]["time_minutes"]}):
                r2=scan_coupled_first_model_limit(
                    self.column,{},self.member_spec,[5.,10.,15.],
                    grid=8,effective_creep_phi=0.)
        self.assertIsNone(r2["observed_first_model_limit_interval"])
        self.assertIsNone(r2["t_R_minutes"])

    def test_first_model_event_refines_with_new_FVM_not_time_interpolation(self):
        original=self.heat
        history={
            "observed_first_model_limit_interval":{
                "last_sampled_model_within_min":5.,
                "first_sampled_model_limit_min":10.},
            "samples":[{"time_minutes":5.,"status":WITHIN},
                       {"time_minutes":10.,"status":EXCEEDED}]}
        new_heat_calls=[]
        def heat_solver(col,*,boundary,cell_count_x,cell_count_y,
                        max_step_minutes,sample_times_minutes):
            t=float(col["fire_minutes"])
            new_heat_calls.append(t)
            self.assertEqual(sample_times_minutes,[t])
            self.assertEqual(cell_count_x,original["grid"]["nx"])
            return {"source_fresh_time":t}
        with patch("rc_fire.thermal.sp2026_heat.solve_sp2026_2d_heat",
                   side_effect=heat_solver):
            with patch("rc_fire.mechanics.sp2026_coupled_first_limit."
                       "select_sp2026_snapshot",
                       side_effect=lambda heat,t:{"snapshot":{"time_minutes":t}}):
                with patch("rc_fire.mechanics.sp2026_coupled_first_limit."
                           "assess_coupled_sp5_nominal_at_time",
                           side_effect=lambda col,snap,spec,**kw:{
                               "status":WITHIN if snap["snapshot"]["time_minutes"]<7.5
                               else EXCEEDED}):
                    result=refine_first_coupled_model_limit_with_new_sp_heat(
                        self.column,original,self.member_spec,history,
                        effective_creep_phi=0.,
                        mechanical_grid=8,time_step_minutes=2.,
                        max_refinements=6,time_bracket_tolerance_minutes=.25)
        self.assertEqual(result["status"],
                         "FRESH_SP_FVM_FIRST_MODEL_EVENT_BRACKET_REFINED")
        bracket=result["strict_refined_model_event_interval_min"]
        self.assertLess(bracket[0],7.5)
        self.assertGreaterEqual(bracket[1],7.5)
        self.assertLess(bracket[1]-bracket[0],.26)
        self.assertGreater(len(new_heat_calls),1)
        self.assertTrue(all(v["fresh_SP_FVM_solve"] for v in result["attempts"]))
        self.assertIsNone(result["actual_t_R_minutes"])
        self.assertFalse(result["normative_claim"])

    def test_public_single_time_coupled_model_fails_closed_for_physical_R(self):
        r=assess_coupled_sp5_nominal_at_time(
            self.column,self.snap,self.member_spec,
            grid=8,effective_creep_phi=0.)
        self.assertIn(r["status"],(WITHIN,EXCEEDED,NOMINAL,UNKNOWN))
        self.assertIsNotNone(r["nominal_coupled_evidence"])
        self.assertTrue(r["SP5_8_1_2_source_secant_not_equal_8_1_6_nominal"])
        self.assertIsNone(r["R_t_minutes"])
        self.assertIsNone(r["U_member_t"])
        self.assertFalse(r["normative_claim"])


class TestThermalCreepAndExperimentalAdmissibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_sp_r3_member import SPR3ActualMemberNumerics
        SPR3ActualMemberNumerics.setUpClass()
        cls.c=copy.deepcopy(SPR3ActualMemberNumerics.column)

    def test_real_fvm_heat_mesh_and_time_separated_from_boundary_validation(self):
        boundary=reference_sp2026_boundary(moisture_mass_pct=1.5)
        audit=audit_sp2026_heat_mesh_and_time(
            self.c,boundary,time_minutes=5.,
            coarse_grid=4,fine_grid=6,
            coarse_step_minutes=2.,fine_step_minutes=1.,
            numerical_temperature_tolerance_C=50.)
        self.assertEqual(len(audit["run_evidence"]),3)
        self.assertIsNotNone(audit["mesh_comparison"]["max_difference_C"])
        self.assertIsNotNone(audit["time_comparison"]["max_difference_C"])
        self.assertTrue(audit["boundary_is_comparison_assumption"])
        self.assertFalse(audit["SP_Annex_Zh_pointwise_reference_compared"])
        self.assertFalse(audit["SP2026_external_boundary_normative_qualified"])
        self.assertIsNone(audit["R_t_minutes"])

    def test_sp5_864_independent_per_axis_creep_cannot_qualify_hot_history(self):
        audit=audit_effective_creep_source(
            phi_infty=2.,
            first_order_M0Eqp_x_kNm=40.,
            first_order_M0Ed_x_kNm=100.,
            first_order_M0Eqp_y_kNm=12.,
            first_order_M0Ed_y_kNm=60.)
        self.assertAlmostEqual(audit["axes"]["x"]["phi_eff"],.8)
        self.assertAlmostEqual(audit["axes"]["y"]["phi_eff"],.4)
        self.assertFalse(audit["hot_concrete_transient_creep_qualified"])
        with self.assertRaises(ValueError):
            audit_effective_creep_source(
                phi_infty=2.,
                first_order_M0Eqp_x_kNm=-40.,
                first_order_M0Ed_x_kNm=100.,
                first_order_M0Eqp_y_kNm=12.,
                first_order_M0Ed_y_kNm=60.)

    def test_existing_fire_column_reference_cases_cannot_be_used_as_validation(self):
        catalog=load_existing_fire_column_catalog()
        self.assertEqual(catalog["source_case_count"],3)
        self.assertEqual(catalog["source_matched_cases_ready"],0)
        self.assertEqual(catalog["validated_model_failure_predictions"],0)
        self.assertEqual({x["id"] for x in catalog["cases"]},
                         {"I3","T3","II10"})
        for item in catalog["cases"]:
            self.assertIsNone(item["model_prediction_min"])
            self.assertIsNone(item["error_min"])
            self.assertGreater(len(item["admissibility_blockers"]),0)
        combined=qualification_ledger(
            coupled_model={"nominal_coupled_evidence":{"some":"number"}},
            experiment_audit=catalog)
        self.assertIsNone(combined["actual_t_R_minutes"])
        self.assertFalse(combined["normative_claim"])
        self.assertEqual(combined["regulatory_result"],"NOT_ESTABLISHED")


class TestSP7PublicEndToEnd(unittest.TestCase):
    def test_source_coupled_and_thermal_and_experiment_public_workflow(self):
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
        spec.update({
            "nominal_sp5_requested":True,
            "nominal_sp5_phi_eff":0.,
            "nominal_sp5_creep_provenance":
                "explicit research short-term phi=0, not derived from real load history",
            "coupled_sp5_requested":True,
            "coupled_sp5_history_requested":True,
            "coupled_sp5_thermal_audit_requested":True,
            "coupled_sp5_experiment_audit_requested":True})
        c["member_spec"]=spec
        report=fire_assessment(
            c,required_minutes=30.,steel_route="hot_rolled",
            ductility_class="B",moisture_mass_pct=1.5,
            grid=8,dt_minutes=3.)
        self.assertIn(report["sp2026_stage7_coupled_status"],
                      (WITHIN,EXCEEDED,NOMINAL,UNKNOWN),
                      report["sp2026_stage7_coupled_blocker"])
        model=report["sp2026_stage7_coupled_at_required_time"]
        self.assertIsNotNone(model)
        eigen=model["independent_global_FE_Euler_evidence"]
        self.assertIsNotNone(eigen)
        self.assertLess(eigen["max_relative_error"],.005)
        history=report["sp2026_stage7_first_model_limit_history"]
        self.assertIsNotNone(history,
                             report["sp2026_stage7_first_model_limit_blocker"])
        self.assertEqual([round(v["time_minutes"])
                          for v in history["samples"]],[10,20,30])
        self.assertIsNone(history["t_R_minutes"])
        thermal=report["sp2026_stage7_thermal_mesh_time_audit"]
        self.assertIsNotNone(
            thermal,report["sp2026_stage7_thermal_mesh_time_audit_blocker"])
        self.assertEqual(thermal["time_minutes"],15.)
        self.assertFalse(thermal["thermal_regulatory_qualification"])
        experiments=report["sp2026_stage7_experiment_admissibility"]
        self.assertEqual(experiments["source_matched_cases_ready"],0)
        ledger=report["sp2026_stage7_qualification_ledger"]
        self.assertEqual(ledger["status"],"NORMATIVE_FIRE_R_QUALIFICATION_BLOCKED")
        self.assertIsNone(report["sp2026_stage7_actual_U_t"])
        self.assertIsNone(report["sp2026_stage7_actual_t_R_minutes"])
        self.assertIsNone(report["R_t_minutes"])
        self.assertEqual(report["regulatory_result"],"NOT_ESTABLISHED")

    def test_schema_rejects_independent_audits_without_coupled_branch(self):
        from test_r07_public_workflow import user_inputs
        from rc_fire.integration.r07_inputs import (
            make_column,explicit_pinned_uniform_sp2026_member)
        from rc_fire.integration.r067 import validate_member_spec
        c=make_column(user_inputs())
        spec=explicit_pinned_uniform_sp2026_member(
            c,confirmed_pinned_uniform_action_model=True,
            confirmed_uniform_longitudinal_fire=True,
            imperfection_x_mm=6.,imperfection_y_mm=3.)
        spec["coupled_sp5_requested"]=True
        with self.assertRaises(ValueError):
            validate_member_spec(spec)
        spec["nominal_sp5_requested"]=True
        spec["nominal_sp5_phi_eff"]=0.
        spec["nominal_sp5_creep_provenance"]="explicit user scenario"
        self.assertTrue(validate_member_spec(spec)["coupled_sp5_requested"])
        spec["coupled_sp5_requested"]=False
        spec["coupled_sp5_thermal_audit_requested"]=True
        with self.assertRaises(ValueError):
            validate_member_spec(spec)


if __name__=="__main__":
    unittest.main()
