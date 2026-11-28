import json
import unittest
from rc_fire.materials import sp2026_r13b_strains as b

class TestR13B(unittest.TestCase):
 def test_rational_compatibility_and_tangent(self):
    f,E,p,u=38.,30000.,.0022,.0035
    d=b.rational_domain(f,E,p,u);self.assertTrue(d["admissible"])
    self.assertAlmostEqual(b.rational_stress(f,E,p,u,p)[0],f)
    self.assertAlmostEqual(b.rational_stress(f,E,p,u,p)[1],0.)
    self.assertAlmostEqual(b.rational_stress(f,E,p,u,0.)[1],1.1*E)
    e=.001;h=1e-8
    self.assertAlmostEqual((b.rational_stress(f,E,p,u,e+h)[0]-b.rational_stress(f,E,p,u,e-h)[0])/(2*h),b.rational_stress(f,E,p,u,e)[1],delta=.001)
    self.assertFalse(b.rational_domain(f,5000.,p,u)["admissible"])
    with self.assertRaises(ValueError):b.rational_stress(f,E,p,u,u+.001)
 def test_shape_scaling_and_active_kernel_endpoints(self):
    for family in ("siliceous","calcareous"):
        r=b.concrete_audit(family)["rows"];k=r[0]["constant_shape"]["k"]
        for v in r:
            self.assertAlmostEqual(v["constant_shape"]["k"],k)
            self.assertTrue(v["constant_shape"]["admissible"])
            for p in v["history_kernel"]:
                self.assertAlmostEqual(p["computed_peak_stress_MPa"],p["fc_MPa"],places=8)
                self.assertAlmostEqual(p["computed_end_stress_MPa"],0.,places=8)
                self.assertEqual(p["end_damage"],1.)
                self.assertFalse(p["measured_ultimate"])
        self.assertFalse(r[6]["fixed"]["admissible"])
 def test_experimental_protocol_guard(self):
    import json
    d=json.loads(b.DATA.read_text());r=b.fracture_screen(d)
    self.assertEqual(len(r["rows"]),14)
    self.assertTrue(all(v["SP_epsilon_uk"] is None and v["SP_epsilon_ud"] is None for v in r["rows"]))
    self.assertFalse(r["grade_transfer_admitted"])
    with self.assertRaises(ValueError):b.fracture_screen({**d,"protocol":"residual_tension"})
 def test_campaign(self):
    q=b.campaign()
    self.assertFalse(q["concrete_hot_ultimate_qualified"]);self.assertFalse(q["steel_hot_uniform_elongation_qualified"])
    self.assertIsNone(q["actual_t_R_minutes"])
    print("SP_R13B_EVIDENCE",json.dumps(q,allow_nan=False))
