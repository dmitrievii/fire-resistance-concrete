"""SP-R4: distinguish observed deformations, actual FE, unknown, and R(t)."""
import copy
import unittest

from test_sp_r3_member import SPR3ActualMemberNumerics, make_explicit_spec
from rc_fire.member.sp2026_resistance import (
    WITHIN, EXCEEDED, UNKNOWN, _known_state,
    bracket_model_resistance, PreparedSP2026MemberResistance,
    evaluate_sp2026_member_resistance,scan_sp2026_resistance_time_history)
from rc_fire.thermal.sp2026_heat import select_sp2026_snapshot


class SPR4Classification(unittest.TestCase):
    def test_sampled_model_state_is_not_iterative_solver_convergence(self):
        base={
            "z_m":[0.,1.,2.],
            "member":{"status":"evaluated_diagnostic",
                      "any_strain_limit_exceeded":False},
            "uls":{"status":"SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS",
                   "gauss_count":6,"node_side_count":4,
                   "node_coverage":True,
                   "all_sampled_limits_resolved":True,
                   "exceeded_count":0}}
        self.assertEqual(_known_state(base)[0],WITHIN)
        bad=copy.deepcopy(base)
        bad["member"]["status"]="critical_or_nonpositive_tangent"
        bad["uls"]["status"]="DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED"
        bad["uls"]["exceeded_count"]=1
        self.assertEqual(_known_state(bad)[0],UNKNOWN)
        bad=copy.deepcopy(base)
        bad["uls"]["status"]="DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED"
        bad["uls"]["exceeded_count"]=1
        self.assertEqual(_known_state(bad)[0],EXCEEDED)
        bad=copy.deepcopy(base)
        bad["uls"]["node_side_count"]=3
        self.assertEqual(_known_state(bad)[0],UNKNOWN)

    def test_clean_synthetic_bracket_and_inverse_load_path_interval(self):
        threshold=1.38
        def f(lam):
            return {"state":WITHIN if lam<threshold else EXCEEDED,
                    "critical_sample":{"z_m":1.5} if lam>=threshold else None}
        r=bracket_model_resistance(
            f,first_factor=.25,step=.25,max_factor=2.,
            relative_tolerance=.0005,max_refinements=15)
        self.assertEqual(r["status"],"OBSERVED_MODEL_STRAIN_LIMIT_BRACKET")
        bracket=r["observed_model_resistance_bracket"]
        self.assertLess(bracket["last_admissible_sample_factor"],threshold)
        self.assertGreaterEqual(bracket["first_observed_exceedance_factor"],threshold)
        self.assertLess(bracket["relative_bracket_width"],.0005)
        util=bracket["model_only_utilisation_interval"]
        self.assertLessEqual(util["lower"],1./threshold)
        self.assertGreaterEqual(util["upper"],1./threshold)
        self.assertIsNone(r["U_member_t"])
        self.assertIsNone(r["R_t_minutes"])
        self.assertFalse(r["normative_claim"])

    def test_unknown_sandwiched_between_states_does_not_fabricate_capacity(self):
        def f(lam):
            if abs(lam-1.25)<1.e-7:
                return {"state":UNKNOWN,"reason":"Newton line-search failed"}
            return {"state":WITHIN if lam<1.5 else EXCEEDED}
        r=bracket_model_resistance(f,first_factor=.25,step=.25,max_factor=2.)
        self.assertEqual(r["status"],"UNRESOLVED_BEFORE_BRACKET")
        self.assertIsNone(r["observed_model_resistance_bracket"])
        self.assertIsNone(r["U_member_t"])

    def test_refinement_unknown_terminates_without_reported_capacity(self):
        def f(lam):
            if abs(lam-1.125)<1.e-8:
                return {"state":UNKNOWN}
            return {"state":WITHIN if lam<1.2 else EXCEEDED}
        r=bracket_model_resistance(f,first_factor=.5,step=.25,max_factor=1.5,
                                   relative_tolerance=.001,max_refinements=10)
        self.assertEqual(r["status"],"UNRESOLVED_DURING_BRACKET_REFINEMENT")
        self.assertIsNone(r["observed_model_resistance_bracket"])

    def test_first_trial_exceeded_cannot_prove_physical_capacity(self):
        r=bracket_model_resistance(lambda v:{"state":EXCEEDED},
                                   first_factor=.25,step=.25,max_factor=1.5)
        self.assertEqual(r["status"],"EXCEEDED_AT_FIRST_EVALUATED_FACTOR")
        self.assertIsNone(r["observed_model_resistance_bracket"])

    def test_scan_rejects_malformed_factor_settings(self):
        for kwargs in (
            {"first_factor":0.},
            {"step":0.},
            {"max_factor":11.},
            {"relative_tolerance":0.2},
            {"max_refinements":-1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    bracket_model_resistance(lambda v:{"state":WITHIN},**kwargs)


class SPR4TrueHotMember(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse already-proven source-grounded physical SP-R2 case.
        SPR3ActualMemberNumerics.setUpClass()
        cls.column=copy.deepcopy(SPR3ActualMemberNumerics.column)
        cls.spec=make_explicit_spec(cls.column)
        cls.thermal=select_sp2026_snapshot(
            SPR3ActualMemberNumerics.heat,5.)

    def test_boundary_face_and_corner_strains_checked_not_only_cell_centres(self):
        from rc_fire.mechanics.sp2026_section import prepare_sp2026_section
        p=prepare_sp2026_section(self.column,self.thermal,grid=8)
        _,_,evidence=p.force_and_tangent([0.,.006,0.])
        self.assertEqual(evidence["concrete_boundary_check_points"],8)
        self.assertGreater(
            evidence["maximum_concrete_boundary_ratio"],
            evidence["maximum_concrete_fibre_ratio"])
        self.assertFalse(evidence["concrete_boundary_continuum_qualified"])
        self.assertGreaterEqual(
            evidence["critical_mechanical_strain_ratio"],
            evidence["maximum_concrete_boundary_ratio"])

    def test_actual_hot_biaxial_member_evaluates_two_distinct_load_factors(self):
        prepared=PreparedSP2026MemberResistance(
            self.column,self.thermal,self.spec,grid=8)
        axial=prepared.axial_stress_relaxed_upper_bound
        self.assertGreater(axial["source_model_N_kN_upper_bound"],0.)
        self.assertGreater(axial["source_model_axial_utilisation_lower_bound"],0.)
        self.assertFalse(axial["discretization_continuum_and_material_qualified"])
        self.assertFalse(axial["normative_claim"])
        low=prepared.evaluate_factor(.25)
        higher=prepared.evaluate_factor(.5)
        self.assertAlmostEqual(low["load_factor"],.25)
        self.assertAlmostEqual(higher["load_factor"],.5)
        self.assertIn(low["state"],(WITHIN,EXCEEDED,UNKNOWN))
        self.assertIn(higher["state"],(WITHIN,EXCEEDED,UNKNOWN))
        if low["state"]!=UNKNOWN:
            self.assertEqual(low["checked_gauss_count"],6)
            self.assertEqual(low["checked_node_sides"],4)
        self.assertFalse(low["normative_claim"])

    def test_full_hot_resistance_scan_exposes_minimum_eccentricity(self):
        report=evaluate_sp2026_member_resistance(
            self.column,self.thermal,self.spec,grid=8,
            first_factor=.25,step=.25,max_factor=.75,max_refinements=2)
        self.assertEqual(report["temperature_station_count"],9)
        self.assertEqual(report["beam_node_count"],3)
        self.assertAlmostEqual(
            report["minimum_eccentricity_check"]["minimum_eccentricity_about_x_mm"],20.)
        self.assertAlmostEqual(
            report["minimum_eccentricity_check"]["minimum_eccentricity_about_y_mm"],20.)
        self.assertFalse(report["minimum_eccentricity_check"][
            "already_included_in_action_and_imperfection_input_verified"])
        self.assertIn(report["at_declared_design_actions"]["state"],
                      (WITHIN,EXCEEDED,UNKNOWN))
        self.assertIsNone(report["U_member_t"])
        self.assertIsNone(report["actual_U_member_t"])
        self.assertIsNone(report["R_t_minutes"])
        self.assertFalse(report["normative_claim"])
        axial=report["stress_relaxed_axial_strength_upper_bound"]
        self.assertGreater(axial["source_model_N_kN_upper_bound"],0.)
        self.assertFalse(axial["normative_claim"])

    def test_time_dependent_load_envelope_uses_only_stored_sp_heat(self):
        heat=SPR3ActualMemberNumerics.heat
        result=scan_sp2026_resistance_time_history(
            self.column,heat,self.spec,[5.,10.],grid=8,
            first_factor=.25,step=.25,max_factor=.5,max_refinements=2)
        self.assertEqual([r["time_minutes"] for r in result["samples"]],
                         [5.,10.])
        self.assertTrue(result["no_temporal_interpolation"])
        self.assertIsNone(result["U_t"])
        self.assertIsNone(result["t_R"])
        self.assertIsNone(result["R_t_minutes"])
        self.assertEqual(result["regulatory_result"],"NOT_ESTABLISHED")
        self.assertFalse(result["normative_claim"])
        with self.assertRaises(ValueError):
            scan_sp2026_resistance_time_history(
                self.column,heat,self.spec,[5.,7.],grid=8,
                first_factor=.25,step=.25,max_factor=.5)

    def test_mismatched_temperature_and_unconfirmed_thermal_mode_rejected(self):
        bad=dict(self.thermal,thermal_method="TKP_4.3.2_FVM")
        with self.assertRaises(ValueError):
            PreparedSP2026MemberResistance(
                self.column,bad,self.spec,grid=8)
        spec=copy.deepcopy(self.spec)
        spec["uniform_exposure_confirmed"]=False
        with self.assertRaises(ValueError):
            PreparedSP2026MemberResistance(
                self.column,self.thermal,spec,grid=8)


class SPR4PublicFacade(unittest.TestCase):
    def test_explicit_pinned_case_reaches_resistance_output_without_fake_U(self):
        from test_r07_public_workflow import user_inputs
        from rc_fire.integration.r07_inputs import (
            make_column, explicit_pinned_uniform_sp2026_member)
        from rc_fire.integration.r07_public import fire_assessment
        c=make_column(user_inputs())
        c["fire_minutes"]=30.
        c["member_spec"]=explicit_pinned_uniform_sp2026_member(
            c,confirmed_pinned_uniform_action_model=True,
            confirmed_uniform_longitudinal_fire=True,
            imperfection_x_mm=6.,imperfection_y_mm=3.)
        spec=c["member_spec"]
        spec["resistance_scan_requested"]=True
        spec["resistance_time_history_requested"]=True
        spec["resistance_scan_first_factor"]=.25
        spec["resistance_scan_step"]=.25
        spec["resistance_scan_max_factor"]=.75
        report=fire_assessment(
            c,required_minutes=30.,steel_route="hot_rolled",
            ductility_class="B",moisture_mass_pct=1.5,
            grid=8,dt_minutes=3.)
        self.assertEqual(report["regulatory_result"],"NOT_ESTABLISHED")
        self.assertIsNone(report["R_t_minutes"])
        self.assertIsNone(report["sp2026_stage4_actual_member_utilisation_U_t"])
        data=report["sp2026_stage4_resistance_scan_at_required_time"]
        self.assertIsNotNone(
            data,report["sp2026_stage4_resistance_scan_blocker"])
        self.assertEqual(data["temperature_station_count"],9)
        self.assertGreaterEqual(len(data["evaluations"]),1)
        self.assertIsNone(data["actual_U_member_t"])
        self.assertIsNone(data["R_t_minutes"])
        self.assertFalse(data["normative_claim"])
        history=report["sp2026_stage4_resistance_time_history"]
        self.assertIsNotNone(
            history,report["sp2026_stage4_resistance_time_history_blocker"])
        self.assertEqual([s["time_minutes"] for s in history["samples"]],
                         [10.,20.,30.])
        self.assertIsNone(history["t_R"])
        self.assertIsNone(history["U_t"])

    def test_absent_member_contract_never_launches_sp_r4_scan(self):
        from test_r07_public_workflow import user_inputs
        from rc_fire.integration.r07_inputs import make_column
        from rc_fire.integration.r07_public import fire_assessment
        c=make_column(user_inputs())
        r=fire_assessment(c,required_minutes=30.,steel_route="hot_rolled",
                ductility_class="B",moisture_mass_pct=1.5,
                grid=8,dt_minutes=3.)
        self.assertEqual(r["sp2026_stage4_resistance_scan_status"],
                         "SP_R4_NOT_REQUESTED")
        self.assertIsNone(r["sp2026_stage4_resistance_scan_at_required_time"])
        self.assertIsNone(r["R_t_minutes"])


if __name__=="__main__":
    unittest.main()
