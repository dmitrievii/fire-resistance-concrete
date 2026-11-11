"""Mechanical-kernel verification is distinct from normative fire ULS.

Analytic Euler/PDelta independent of SP heated RC; FD Jacobian verifies
implemented SP fibre algebra, not external hot constitutive validity.
"""
import copy
import unittest

from test_sp_r3_member import SPR3ActualMemberNumerics
from rc_fire.thermal.sp2026_heat import select_sp2026_snapshot
from rc_fire.mechanics.sp2026_section import prepare_sp2026_section
from rc_fire.member.sp2026_mechanical_qualification import (
    verify_euler_critical_load,
    verify_pdelta_midspan,
    verify_hot_section_jacobian,
    verify_condensed_hot_member_tangent,
    mechanical_uls_admissibility,
)


class TestAnalyticalMechanicalBenchmarks(unittest.TestCase):
    def test_pinned_pinned_euler_both_axes_refines_to_analytic(self):
        coarse=verify_euler_critical_load(
            node_count=3, EI_x_kNm2=1200., EI_y_kNm2=800.)
        fine=verify_euler_critical_load(
            node_count=17, EI_x_kNm2=1200., EI_y_kNm2=800.)
        for axis in ("x","y"):
            with self.subTest(axis=axis):
                x=coarse["axes"][axis]
                y=fine["axes"][axis]
                self.assertGreater(x["Ncrit_FE_kN"],0.)
                self.assertLess(abs(y["relative_error"]),.005)
                self.assertLessEqual(abs(y["relative_error"]),
                                     abs(x["relative_error"])+1.e-9)
        self.assertFalse(fine["normative_mechanical_fire_qualified"])

    def test_fixed_fixed_euler_critical_4_times_pin_pin(self):
        for mode in (("pinned","pinned"),("fixed","fixed")):
            result=verify_euler_critical_load(
                node_count=17,left_kind=mode[0],right_kind=mode[1],
                EI_x_kNm2=1200.,EI_y_kNm2=800.)
            for axis in ("x","y"):
                self.assertLess(abs(result["axes"][axis]["relative_error"]),.005)

    def test_analytic_pdelta_midspan_from_independent_ODE(self):
        for ratio in (.1,.4,.7):
            with self.subTest(N_by_Ncr=ratio):
                result=verify_pdelta_midspan(
                    axial_ratio_to_euler=ratio,node_count=17)
                self.assertLess(result["relative_error"],.005)
                self.assertLess(result["other_axis_leakage_m"],1.e-9)
                self.assertGreater(result["midspan_FE_m"],0.)

    def test_benchmark_rejects_invalid_domains_and_unsupported_restraining(self):
        with self.assertRaises(ValueError):
            verify_euler_critical_load(left_kind="guided",right_kind="fixed")
        with self.assertRaises(ValueError):
            verify_euler_critical_load(node_count=2)
        with self.assertRaises(ValueError):
            verify_pdelta_midspan(axial_ratio_to_euler=.99)
        with self.assertRaises(ValueError):
            verify_pdelta_midspan(node_count=8)


class TestSourceHotFibreAndGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SPR3ActualMemberNumerics.setUpClass()
        cls.column=copy.deepcopy(SPR3ActualMemberNumerics.column)
        cls.heat=SPR3ActualMemberNumerics.heat

    def test_actual_SP_hot_fibre_jacobian_finite_difference(self):
        snap=select_sp2026_snapshot(self.heat,5.)
        prepared=prepare_sp2026_section(self.column,snap,grid=8)
        result=verify_hot_section_jacobian(
            prepared,state=(.001,.0002,-.0001),perturbation=1.e-7)
        self.assertLess(result["max_relative_global_scale_error"],.001)
        self.assertEqual(result["status"],
                         "SP_FIBRE_JACOBIAN_FINITE_DIFFERENCE_COMPUTED")
        self.assertFalse(result["material_law_is_experimentally_validated"])

    def test_physical_member_tangent_schur_matches_numerical_derivative(self):
        snap=select_sp2026_snapshot(self.heat,5.)
        prepared=prepare_sp2026_section(self.column,snap,grid=8)
        N=self.column["sections"][0]["N_kN"]
        tested=verify_condensed_hot_member_tangent(
            prepared,N,curvature_1pm=(1.e-5,-2.e-5),
            perturbation_1pm=1.e-7)
        self.assertLess(tested["relative_global_scale_error"],.001)
        self.assertLess(tested["relative_symmetry_error"],1.e-5)
        self.assertTrue(tested["axial_force_solved_on_every_trial"])
        self.assertFalse(tested["normative_mechanical_fire_qualified"])

    def test_numerical_verification_cannot_promote_false_normative_R(self):
        snap=select_sp2026_snapshot(self.heat,5.)
        prepared=prepare_sp2026_section(self.column,snap,grid=8)
        numeric={
            "euler":verify_euler_critical_load(node_count=17),
            "pdelta":verify_pdelta_midspan(node_count=17),
            "jacobian":verify_hot_section_jacobian(prepared),
            "condensed_tangent":verify_condensed_hot_member_tangent(
                prepared,self.column["sections"][0]["N_kN"])}
        result=mechanical_uls_admissibility(
            self.column,self.column["member_spec"],
            numeric_evidence=numeric,
            external_evidence={
                "beta_e_reconciled":True,
                "first_global_stability_verified":True,
                "experimental_validation_pass":True,
            })
        self.assertEqual(result["numerical_pass_count"],4)
        self.assertFalse(result["normative_mechanical_uls_qualified"])
        self.assertFalse(result["source_qualified_fire_R"])
        self.assertIsNone(result["U_member_t"])
        self.assertIsNone(result["t_R"])
        self.assertEqual(result["regulatory_result"],"NOT_ESTABLISHED")
        self.assertIn("SP_BETA_ELASTIC_VS_CONSTITUTIVE_STIFFNESS",
                      result["remaining_blockers"])
        self.assertIn("GLOBAL_FIRST_STABILITY_AND_POSTPEAK",
                      result["remaining_blockers"])
        self.assertIn("INDEPENDENT_STRUCTURAL_FIRE_EXPERIMENTS",
                      result["remaining_blockers"])
        self.assertTrue(result["material_evidence_cannot_be_replaced_with_user_assertions"])

    def test_missing_benchmarks_fail_closed(self):
        result=mechanical_uls_admissibility(
            self.column,self.column["member_spec"])
        self.assertEqual(result["numerical_pass_count"],0)
        self.assertIsNone(result["U_member_t"])
        self.assertFalse(result["normative_mechanical_uls_qualified"])


class TestPublicAndExternalEvidence(unittest.TestCase):
    def test_experimental_source_metadata_is_not_model_validation(self):
        import json
        from pathlib import Path
        file=Path(__file__).resolve().parents[1]/"validation"/(
            "sp_r4q_fire_column_reference_cases.json")
        record=json.loads(file.read_text(encoding="utf-8"))
        self.assertEqual(record["schema_version"],
                         "SP-R4Q-EXPERIMENT-CATALOG-v1")
        self.assertEqual([x["id"] for x in record["cases"]],
                         ["I3","T3","II10"])
        self.assertEqual([x["observed_fire_failure_time_min"]
                          for x in record["cases"]],[218,221,262])
        self.assertTrue(record["no_assumed_equivalence_with_SP_standard_fire"])
        self.assertTrue(record["no_model_fitting_or_tuning_to_measured_failures"])
        for case in record["cases"]:
            self.assertEqual(case["sp_r4q_test_execution"],"NOT_EXECUTED")
            self.assertEqual(case["independent_full_validation"],"NOT_ESTABLISHED")
            self.assertGreaterEqual(len(case["missing_preanalysis"]),5)

    def test_public_report_retains_mechanical_qualification_gates(self):
        from test_r07_public_workflow import user_inputs
        from rc_fire.integration.r07_inputs import (
            make_column,explicit_pinned_uniform_sp2026_member)
        from rc_fire.integration.r07_public import fire_assessment
        c=make_column(user_inputs())
        c["fire_minutes"]=30.
        c["member_spec"]=explicit_pinned_uniform_sp2026_member(
            c,confirmed_pinned_uniform_action_model=True,
            confirmed_uniform_longitudinal_fire=True,
            imperfection_x_mm=6.,imperfection_y_mm=3.)
        r=fire_assessment(
            c,required_minutes=30.,steel_route="hot_rolled",
            ductility_class="B",moisture_mass_pct=1.5,
            grid=8,dt_minutes=3.)
        q=r["sp2026_stage4q_mechanical_qualification"]
        self.assertIsNotNone(
            q,r["sp2026_stage4q_mechanical_qualification_blocker"])
        self.assertEqual(len(q["gate_results"]),12)
        self.assertIn(q["numerical_pass_count"],range(5))
        self.assertFalse(q["normative_mechanical_uls_qualified"])
        self.assertFalse(r["sp2026_stage4q_mechanical_uls_qualified"])
        self.assertIn("SP_BETA_ELASTIC_VS_CONSTITUTIVE_STIFFNESS",
                      q["remaining_blockers"])
        self.assertIsNone(q["U_member_t"])
        self.assertIsNone(r["R_t_minutes"])
        self.assertEqual(r["regulatory_result"],"NOT_ESTABLISHED")


if __name__=="__main__":
    unittest.main()
