"""SP-R3 explicit physical member contract, SP-fibre beam law, time evidence.

All tests use the actual SP-R2 heat field and SP-R1 material law. Passing
test cases demonstrate numerical coupling, not normative fire endurance.
"""
import copy
import unittest

import numpy as np

from test_r07_public_workflow import user_inputs
from rc_fire.integration.r07_inputs import make_column
from rc_fire.member.sp2026_member import (
    SP2026MemberInputError, SP2026MemberFiberLaw,
    evaluate_sp2026_member_at_time, scan_sp2026_member_history,
    WITHIN, EXCEEDED, UNKNOWN)
from rc_fire.mechanics.sp2026_section import prepare_sp2026_section
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat, select_sp2026_snapshot,
    reference_sp2026_boundary)


def make_explicit_spec(column):
    L = float(column["length_m"])
    n = 3
    return {
        "load_mode": "explicit_sp2026_beam",
        "z_m": [0., L/2., L],
        "left_support": {"x": "pinned", "y": "pinned"},
        "right_support": {"x": "pinned", "y": "pinned"},
        "axial_restraint_mode": "free_axial_expansion",
        "fire_design_action_source": "user-entered already combined fire actions",
        "N_kN": column["sections"][0]["N_kN"],
        "distributed_load_kNpm": [[0., 0.]]*n,
        "nodal_forces": [0.] * (4*n),
        "transverse_action_source": "user declared zero transverse distributed/nodal actions",
        "initial_imperfection": [0.] * (4*n),
        "imperfection_source": "explicit zero for diagnostic numerical baseline only",
        "entered_section_moments_reconciled": True,
        "longitudinal_thermal_mode": "explicit_uniform_full_length",
        "uniform_exposure_confirmed": True,
    }


class SPR3ActualMemberNumerics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column = make_column(user_inputs())
        cls.column["fire_minutes"] = 10.
        cls.boundary = reference_sp2026_boundary(moisture_mass_pct=1.5)
        cls.heat = solve_sp2026_2d_heat(
            cls.column, boundary=cls.boundary, cell_count_x=8,
            cell_count_y=8, max_step_minutes=2.5,
            sample_times_minutes=[5., 10.])
        cls.spec = make_explicit_spec(cls.column)

    def test_fibre_axial_equilibrium_and_schur_member_tangent(self):
        snap = select_sp2026_snapshot(self.heat, 5.)
        section = prepare_sp2026_section(self.column, snap, grid=8)
        law = SP2026MemberFiberLaw(section)
        moments, D, meta = law.evaluate([0., 0.], self.spec["N_kN"])
        self.assertEqual(moments.shape, (2,))
        self.assertEqual(D.shape, (2,2))
        self.assertTrue(np.allclose(D, D.T, atol=1.e-5))
        self.assertGreater(np.linalg.eigvalsh(D).min(),0.)
        self.assertTrue(np.all(np.isfinite(moments)))
        self.assertFalse(meta["normative_claim"])
        self.assertLess(meta["critical_mechanical_strain_ratio"],1.)

    def test_nonlinear_sp_member_has_real_gauss_and_nodal_evidence(self):
        snap = select_sp2026_snapshot(self.heat, 5.)
        data = evaluate_sp2026_member_at_time(
            self.column, snap, self.spec, grid=8)
        self.assertEqual(data["temperature_method"], "SP2026_8.2.23_FVM")
        self.assertEqual(data["station_count"], 3*2+3)
        self.assertEqual(data["member"]["status"], "evaluated_diagnostic")
        self.assertEqual(data["status"], WITHIN)
        self.assertEqual(data["uls"]["gauss_count"], 6)
        self.assertEqual(data["uls"]["node_side_count"], 4)
        self.assertTrue(data["uls"]["node_coverage"])
        self.assertIsNone(data["U_member_t"])
        self.assertIsNone(data["R_t_minutes"])
        self.assertEqual(data["regulatory_result"], "NOT_ESTABLISHED")
        self.assertFalse(data["normative_claim"])
        self.assertLess(data["member"]["relative_equilibrium_residual"],1.e-7)

    def test_real_nonzero_displacement_imperfection_and_biaxial_load(self):
        snap = select_sp2026_snapshot(self.heat, 5.)
        s = copy.deepcopy(self.spec)
        L = self.column["length_m"]
        # Pinned endpoints: zero imposed translations; nonzero initial
        # rotations/displacement are an explicitly supplied shape.
        amp = .001
        slope = np.pi*amp/L
        s["initial_imperfection"] = [
            0., slope, amp, 0., 0., -slope,
            0., slope/2, amp/2, 0., 0., -slope/2]
        s["imperfection_source"] = "user supplied initial two-axis half-sine profile"
        s["distributed_load_kNpm"] = [[.02,.01]] * 3
        s["transverse_action_source"] = "user supplied biaxial distributed fire actions"
        data = evaluate_sp2026_member_at_time(
            self.column, snap, s, grid=8)
        self.assertIn(data["status"], (WITHIN, EXCEEDED, UNKNOWN))
        self.assertIsNone(data["R_t_minutes"])
        if data["status"] != UNKNOWN:
            self.assertGreater(max(abs(x) for x in data["member"]["total_w_x_m"]),0.)

    def test_public_facade_requires_explicit_member_contract_and_integrates(self):
        from rc_fire.integration.r07_public import fire_assessment
        c = copy.deepcopy(self.column)
        c["fire_minutes"] = 30.
        standard = dict(required_minutes=30.,steel_route="hot_rolled",
                        ductility_class="B",moisture_mass_pct=1.5,
                        grid=8,dt_minutes=3.)
        missing = fire_assessment(c,**standard)
        self.assertEqual(missing["sp2026_stage3_member_status"],
                         "SP_R3_EXPLICIT_MEMBER_INPUT_REQUIRED")
        self.assertIsNone(missing["sp2026_stage3_member_at_required_time"])
        c["member_spec"] = copy.deepcopy(self.spec)
        # Explicitly evaluate the available SP field at the true required
        # time, no generic TKP member result recast as SP.
        report = fire_assessment(c,**standard)
        state = report["sp2026_stage3_member_at_required_time"]
        self.assertIsNotNone(state,report["sp2026_stage3_member_blocker"])
        self.assertEqual(state["temperature_method"],"SP2026_8.2.23_FVM")
        self.assertIn(state["status"],(WITHIN,EXCEEDED,UNKNOWN))
        self.assertIsNone(report["R_t_minutes"])
        self.assertEqual(report["regulatory_result"],"NOT_ESTABLISHED")

    def test_uniformity_and_end_fixity_never_assumed(self):
        snap = select_sp2026_snapshot(self.heat, 5.)
        for field, value in (
            ("uniform_exposure_confirmed", False),
            ("left_support", None),
            ("initial_imperfection", None),
            ("axial_restraint_mode", "axially_restrained"),
            ("transverse_action_source", None),
            ("fire_design_action_source", None),
            ("entered_section_moments_reconciled", False),
        ):
            with self.subTest(field=field):
                s = copy.deepcopy(self.spec)
                s[field] = value
                with self.assertRaises(SP2026MemberInputError):
                    evaluate_sp2026_member_at_time(
                        self.column, snap, s, grid=8)

    def test_foreign_tkp_temperature_or_mismatched_time_rejected(self):
        snap = select_sp2026_snapshot(self.heat, 5.)
        wrong = dict(snap, thermal_method="TKP_4.3.2_FVM")
        with self.assertRaises(SP2026MemberInputError):
            evaluate_sp2026_member_at_time(
                self.column, wrong, self.spec, grid=8)
        wrong_time = dict(snap, fire_minutes=10.)
        with self.assertRaises(SP2026MemberInputError):
            evaluate_sp2026_member_at_time(
                self.column, wrong_time, self.spec, grid=8)

    def test_no_silent_longitudinal_interpolation_or_missing_stations(self):
        snap = select_sp2026_snapshot(self.heat, 5.)
        s = copy.deepcopy(self.spec)
        s["longitudinal_thermal_mode"] = "explicit_per_station"
        with self.assertRaises(SP2026MemberInputError):
            evaluate_sp2026_member_at_time(self.column, snap, s, grid=8)
        data = evaluate_sp2026_member_at_time(
            self.column, snap, s, grid=8,
            node_snapshots=[snap]*3,
            gauss_snapshots=[[snap]*3 for _ in range(2)])
        self.assertIn(data["status"], (WITHIN, EXCEEDED, UNKNOWN))
        self.assertEqual(data["member_thermal_longitudinal_mode"],"explicit_per_station")

    def test_two_time_history_never_invents_t_R_or_failure_from_nonconvergence(self):
        data = scan_sp2026_member_history(
            self.column,self.heat,self.spec,[5.,10.],grid=8)
        self.assertEqual([x["time_minutes"] for x in data["samples"]],[5.,10.])
        self.assertIsNone(data["t_R"])
        self.assertIsNone(data["U_t"])
        self.assertEqual(data["regulatory_result"],"NOT_ESTABLISHED")
        self.assertFalse(data["normative_claim"])
        self.assertNotIn("R_t_minutes",data["samples"][0])
        with self.assertRaises(Exception):
            scan_sp2026_member_history(
                self.column,self.heat,self.spec,[5.,7.],grid=8)


if __name__ == "__main__":
    unittest.main()
