"""Targeted SP-R.8 numerical evidence. Residuals are reported, not fitted."""
import copy
import json
import unittest
from rc_fire.verification.sp2026_r8_thermal import (
    annex_k_point_evidence, compare_annex_zh_selected, audit_heat_to_mechanics,
    REFERENCE, SOURCE_ANOMALIES, FACES)
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat, reference_sp2026_boundary)
from test_sp_r3_member import make_column, user_inputs, make_explicit_spec

def thermal_column(side):
    return {"b_mm":side,"h_mm":side,"fire_minutes":120.,
            "thermal_spec":{"concrete_family":"siliceous",
            "dry_density_kg_m3":2400.,"exposed_faces":list(FACES),
            "a_red_mode":"table_K1","moisture_mass_pct":2.5}}

class TestSPR8(unittest.TestCase):
    def test_annex_k_equation_against_independent_scalar(self):
        import math
        c=thermal_column(400)
        t=90.
        a=.00133
        l=math.sqrt(12*a*t/60)
        p=lambda d:(1-min(1.,(d+.63*math.sqrt(a))/l))**2
        expected=1220-1200*(1-p(.04)-p(.36))*(1-p(.2)-p(.2))
        r=annex_k_point_evidence(c,40,200,t)
        self.assertAlmostEqual(r["temperature_C"],expected,places=10)
        self.assertTrue(r["K11_source_wording_conflict"])
        self.assertFalse(r["normative_claim"])
    def test_annex_k_steel_diameter_is_not_concrete_point_temperature(self):
        c=thermal_column(400)
        p=annex_k_point_evidence(c,40,40,90)
        s=annex_k_point_evidence(c,40,40,90,bar_diameter_mm=20)
        # At tabulated rho=2400 phi2=.5, diameter offset cancels
        # under the existing clear-cover interpretation of K.5.
        self.assertAlmostEqual(p["temperature_C"],s["temperature_C"])
        self.assertEqual(s["bar_diameter_mm"],20)
        self.assertIn("clear",s["K5_distance_convention"])
    def test_zh_reference_diagnostics_on_real_heat(self):
        boundary=reference_sp2026_boundary(moisture_mass_pct=2.5)
        for side,times in ((200,[90.]),(400,[30.,60.,90.,120.])):
            c=thermal_column(side)
            c["fire_minutes"]=times[-1]
            heat=solve_sp2026_2d_heat(c,boundary=boundary,
                cell_count_x=12,cell_count_y=12,max_step_minutes=3.,
                sample_times_minutes=times)
            for t in times:
                r=compare_annex_zh_selected(heat,c,t)
                self.assertEqual(len(r["points"]),len(REFERENCE[(side,t)][1]))
                self.assertEqual(r["point_class_metrics"]["corner_reconstructed"]["FVM"]["count"],1)
                self.assertFalse(r["source_boundary_matched"])
                self.assertFalse(r["normative_claim"])
                print("SP_R8_ZH_EVIDENCE",json.dumps(r,ensure_ascii=True))
        self.assertEqual(len(SOURCE_ANOMALIES),3)
    def test_real_coupled_heat_to_mechanics_refinement(self):
        c=make_column(user_inputs())
        spec=make_explicit_spec(c)
        r=audit_heat_to_mechanics(c,spec,
            boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
            time_minutes=5.,thermal_grids=(4,6,8),time_steps=(2.,1.),
            mechanical_grids=(8,12),effective_creep_phi=0.)
        self.assertEqual(len(r["runs"]),5)
        self.assertEqual(r["comparisons"]["mechanical_quadrature"]["max_point_delta_C"],0.)
        self.assertTrue(all(x["mechanics"]["D_kNm2"] is not None for x in r["runs"]))
        self.assertIsNone(r["actual_t_R_minutes"])
        self.assertFalse(r["normative_claim"])
        print("SP_R8_COUPLED_EVIDENCE",json.dumps(r,ensure_ascii=True))

if __name__=="__main__":
    unittest.main()
