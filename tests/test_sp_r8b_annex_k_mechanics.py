"""SP-R8B: actual analytical to mechanics integration and fail-closed provenance."""
import copy
import math
import unittest
from rc_fire.thermal.sp2026_annex_k_field import (
    ANNEX_K_METHOD,build_annex_k_snapshot,sample_annex_k_temperature)
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.mechanics.sp2026_coupled_first_limit import assess_coupled_sp5_nominal_at_time
from rc_fire.verification.sp2026_r8b_cross import compare_annex_k_fvm_mechanics
from test_sp_r3_member import make_column,user_inputs,make_explicit_spec

def column():
    c=make_column(user_inputs())
    c["fire_minutes"]=90.
    c["thermal_spec"].update(a_red_mode="formula_K1_450C",moisture_mass_pct=1.5)
    return c

class TestAnnexKMechanical(unittest.TestCase):
    def test_exact_K5_centre_clear_scalar(self):
        c=column()
        c["thermal_spec"].update(dry_density_kg_m3=2400.,a_red_mode="table_K1",moisture_mass_pct=2.5)
        clear=build_annex_k_snapshot(c,90.)
        centre=build_annex_k_snapshot(c,90.,bar_distance_convention="centre")
        a=.00133
        l=math.sqrt(12*a*1.5)
        p=lambda d:(1-min(1.,(d+.63*math.sqrt(a))/l))**2
        expected=1220-1200*(1-p(.04)-p(.56))**2
        concrete=sample_annex_k_temperature(clear,40.,40.)
        self.assertAlmostEqual(concrete,expected,places=9)
        self.assertAlmostEqual(concrete,sample_annex_k_temperature(clear,40.,40.,bar_diameter_mm=20.),places=9)
        self.assertLess(sample_annex_k_temperature(centre,40.,40.,bar_diameter_mm=20.),concrete)
    def test_actual_design_section_and_coupled_member(self):
        c=column()
        k=build_annex_k_snapshot(c,30.,bar_distance_convention="centre")
        p=prepare_sp2026_design_section(c,k,grid=8)
        self.assertTrue(any(abs(a-b)>1e-6 for a,b in zip(p.theta_s,p.theta_cb)))
        self.assertEqual(p.source["thermal_method"],ANNEX_K_METHOD)
        m=assess_coupled_sp5_nominal_at_time(c,k,make_explicit_spec(c),
                                            grid=8,effective_creep_phi=0.)
        self.assertEqual(m["temperature_method"],ANNEX_K_METHOD)
        self.assertIsNotNone(m["nominal_coupled_evidence"])
        self.assertIsNone(m["R_t_minutes"])
        self.assertFalse(m["normative_claim"])
    def test_changed_profile_and_one_face_rejected(self):
        c=column()
        k=build_annex_k_snapshot(c,30.)
        wrong=copy.deepcopy(c)
        wrong["thermal_spec"]["dry_density_kg_m3"]=2400.
        with self.assertRaises(ValueError):
            prepare_sp2026_design_section(wrong,k,grid=8)
        wrong=copy.deepcopy(c)
        wrong["thermal_spec"]["exposed_faces"]=["left"]
        with self.assertRaises(ValueError):
            build_annex_k_snapshot(wrong,30.)
    def test_time_zero_analytical_ambient(self):
        c=column()
        k=build_annex_k_snapshot(c,0.)
        p=prepare_sp2026_design_section(c,k,grid=8)
        self.assertTrue(all(v==20. for v in p.theta_s))
        self.assertTrue(all(v==20. for v in p.theta_c))
    def test_real_cross_route(self):
        c=column()
        r=compare_annex_k_fvm_mechanics(c,make_explicit_spec(c),
              time_minutes=10.,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
              grid=8,heat_grid=8,step_minutes=2.,effective_creep_phi=0.)
        self.assertTrue(r["K_vs_FVM"]["resolved"])
        self.assertTrue(r["K5_convention_sensitivity"]["resolved"])
        self.assertIsNone(r["actual_t_R_minutes"])
        self.assertFalse(r["normative_claim"])
        import json
        print("SP_R8B_CROSS_EVIDENCE",json.dumps(r,ensure_ascii=True))
