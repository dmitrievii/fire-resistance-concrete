import json
import unittest
import numpy as np
from rc_fire.materials.sp2026_constitutive_closure import (
    concrete_envelope_parameters,evaluate_concrete_envelope,compare_materials,
    replay_section_strain,PARABOLA,RATIONAL,SCALED,TKP)
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from test_sp_r3_member import make_column,user_inputs

def prepared():
    c=make_column(user_inputs())
    c["fire_minutes"]=10.
    c["thermal_spec"].update(a_red_mode="formula_K1_450C",moisture_mass_pct=1.5)
    return prepare_sp2026_design_section(c,build_annex_k_snapshot(c,10.),grid=24)

class TestR9A(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=prepared()
    def params(self,T,mode):
        p=self.p
        return concrete_envelope_parameters(p.sp_concrete,p.sp_concrete_normal,p.sp_steel_normal,T,mode)
    def test_strict_SP_domain_not_zero_stress(self):
        p=self.params(600.,PARABOLA)
        self.assertAlmostEqual(evaluate_concrete_envelope(p,p["peak_strain"])["stress_MPa"],p["strength_MPa"])
        self.assertIsNone(evaluate_concrete_envelope(p,p["ultimate_strain"]+1e-6)["stress_MPa"])
        self.assertEqual(evaluate_concrete_envelope(self.params(801.,PARABOLA),.01)["stress_MPa"],0.)
    def test_TKP_source_nodes_and_peak(self):
        p=self.params(600.,TKP)
        self.assertAlmostEqual(p["peak_strain"],.025)
        self.assertAlmostEqual(p["ultimate_strain"],.035)
        self.assertAlmostEqual(p["strength_MPa"],.45*30.)
        self.assertAlmostEqual(evaluate_concrete_envelope(p,.025)["stress_MPa"],p["strength_MPa"])
        self.assertEqual(evaluate_concrete_envelope(p,.035)["stress_MPa"],0.)
    def test_scaled_shape_invariance_and_tangent(self):
        ambient=self.params(20.,SCALED)
        for t in (100.,300.,500.,600.,700.,800.):
            p=self.params(t,SCALED)
            self.assertAlmostEqual(p["shape_k"],ambient["shape_k"])
            self.assertAlmostEqual(p["ultimate_strain"]/p["peak_strain"],ambient["ultimate_strain"]/ambient["peak_strain"])
            if not p["defined"]:continue
            e=.3*p["peak_strain"];h=1e-8
            f=lambda x:evaluate_concrete_envelope(p,x)["stress_MPa"]
            d=evaluate_concrete_envelope(p,e)["tangent_MPa"]
            self.assertAlmostEqual((f(e+h)-f(e-h))/(2*h),d,delta=max(1e-4,abs(d)*1e-6))
            self.assertAlmostEqual(evaluate_concrete_envelope(p,p["peak_strain"])["stress_MPa"],p["strength_MPa"])
    def test_independent_comparison_and_actual_strain_replay(self):
        p=self.p
        r=compare_materials(p.sp_concrete,p.sp_concrete_normal,p.sp_steel,p.sp_steel_normal,
                            production_route="hot_rolled",ductility_class="B")
        self.assertEqual(len(r["rows"]),9)
        s=p.solve_actions(50.,1.,1.)
        self.assertIsNotNone(s.get("unknowns"))
        replay=replay_section_strain(p,s["unknowns"])
        self.assertEqual(len(replay["replay"]),4)
        self.assertFalse(replay["normative_claim"])
        print("SP_R9A_EVIDENCE",json.dumps({"materials":r,"section_replay":replay},
                                          allow_nan=False,ensure_ascii=True))
