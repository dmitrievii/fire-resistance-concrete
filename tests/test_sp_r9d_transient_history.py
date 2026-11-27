import unittest
import json
from rc_fire.mechanics.sp2026_transient_history import (
 Parameters,State,trial_step,strain_controlled_trial,run_path,benchmark_paths,
 screen_reproduced_tests,HistoryDomainError,IMPLICIT)
from rc_fire.materials.sp2026_fire import concrete_free_thermal_strain_sp
class TestR9D(unittest.TestCase):
 def setUp(self):self.p=Parameters("siliceous",30.,30000.)
 def step(self,s,t,T,sig):return trial_step(self.p,s,time_s=t,temperature_C=T,stress_MPa=sig)
 def test_constant_load_integral_and_no_load(self):
    a,_=self.step(State(),1,20,9)
    b,r=self.step(a,2,500,9)
    expected=2.35*.3*concrete_free_thermal_strain_sp(500,"siliceous",signed_shrinkage=False)
    self.assertAlmostEqual(b.transient_compression,expected,places=13)
    self.assertAlmostEqual(b.thermal_work_MPa,9*expected,places=12)
    z,_=self.step(State(),2,500,0)
    self.assertEqual(z.transient_compression,0)
 def test_cooling_and_reheating_retention(self):
    s,_=self.step(State(),1,20,9)
    a,_=self.step(s,2,400,9)
    b,_=self.step(a,3,200,0)
    c,_=self.step(b,4,400,9)
    self.assertEqual(a.transient_compression,b.transient_compression)
    self.assertEqual(a.transient_compression,c.transient_compression)
    d,_=self.step(c,5,500,9)
    self.assertGreater(d.transient_compression,c.transient_compression)
 def test_path_refinement_and_trial_immutability(self):
    a,_=self.step(State(),1,20,0)
    coarse,_=self.step(a,3,500,9)
    mid,_=self.step(a,2,260,4.5)
    fine,_=self.step(mid,3,500,9)
    self.assertAlmostEqual(coarse.transient_compression,fine.transient_compression,places=13)
    self.assertAlmostEqual(coarse.thermal_work_MPa,fine.thermal_work_MPa,places=12)
    self.assertEqual(a.transient_compression,0.)
 def test_strain_control_and_fail_closed(self):
    s,r=strain_controlled_trial(self.p,State(),time_s=60,temperature_C=200,total_compression_strain=0.)
    self.assertGreater(s.stress_MPa,0)
    self.assertLess(abs(r["compatibility_residual"]),1e-11)
    with self.assertRaises(HistoryDomainError):
      self.step(s,120,600,0)
    with self.assertRaises(HistoryDomainError):Parameters("siliceous",30,30000,mode=IMPLICIT).validate()
    self.assertEqual(s.maximum_temperature_C,200.)
 def test_experimental_screening_and_benchmarks(self):
    r=screen_reproduced_tests()
    self.assertEqual(len(r["summary"]),18)
    self.assertTrue(all(x["count"]==19 for x in r["summary"]))
    self.assertFalse(r["coefficient_independent_holdout"])
    b=benchmark_paths()
    self.assertGreater(b["loaded_heating_unload_reheat"]["committed_state"]["transient_compression"],
                       b["unloaded_first_heating"]["committed_state"]["transient_compression"])
    print("SP_R9D_EVIDENCE",json.dumps({"screen":r["summary"],"benchmarks":b},allow_nan=False))
