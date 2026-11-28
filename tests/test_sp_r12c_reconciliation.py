import unittest
import numpy as np
from types import SimpleNamespace
from rc_fire.member import sp2026_r12b_endpoint as b
from rc_fire.member import sp2026_r12c_reconciliation as c

def fixture(peak,center):
    beam=SimpleNamespace(n=1,N=1500.,free=np.array([0]),initial=np.array([0.]),scale=np.array([1.]))
    def op(x,l):
        u=1000*x[0]
        return np.array([peak-.0005*(u-center)**2-l]),np.array([[-(u-center)]]),np.array([-1.]),None
    verify=lambda sol:{"axial_residual_kN":np.float64(0.)}
    seed=(np.array([.01]),1.)
    pts,scan=b.scan_from_seed(beam,op,verify,seed,step_mm=.5,negative_mm=1.,positive_mm=1.)
    return beam,op,verify,pts,scan

class TestR12C(unittest.TestCase):
 def test_matched_sample_crossing_and_adaptive_peak(self):
    a=fixture(1.002,10.125);z=fixture(.998,10.125)
    r=c.reconcile([(83.75,*a),(83.875,*z)],levels=2)
    self.assertIsNone(r["stop"])
    self.assertEqual(len(r["levels"]),3)
    self.assertTrue(r["refined_sampled_threshold_supported"])
    self.assertEqual(r["sampled_threshold_pair"]["observed_sampled_crossing"],[83.75,83.875])
    self.assertAlmostEqual(r["levels"][-1]["samples"][0]["sampled_peak_lambda"],1.002)
    self.assertIsNone(r["actual_t_R_minutes"])
 def test_incomplete_base_does_not_promote(self):
    a=fixture(1.002,10.125);z=fixture(.998,10.125)
    z[-1]["complete"]=False
    r=c.reconcile([(83.75,*a),(83.875,*z)])
    self.assertEqual(r["stop"],"INCOMPLETE_BASE_SCAN")
    self.assertIsNone(r["sampled_threshold_pair"])
    self.assertFalse(r["refined_sampled_threshold_supported"])
 def test_nonmatching_grid_does_not_promote(self):
    a=fixture(1.002,10.125);z=fixture(.998,10.125)
    z[3][0][0][0][0]-=.0001
    r=c.reconcile([(83.75,*a),(83.875,*z)])
    self.assertEqual(r["stop"],"NONMATCHING_CONTROL_GRID")
