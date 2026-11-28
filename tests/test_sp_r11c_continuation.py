import json
import unittest
from dataclasses import dataclass
import numpy as np
from rc_fire.member import sp2026_r11c_continuation as c
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR11C(unittest.TestCase):
 def test_fold_continuation(self):
    # lambda = u-u^3, exact fold u=1/sqrt(3).
    def residual(y):
        u,l=y
        return np.array([u-u**3-l]),np.array([[1-3*u*u,-1.]])
    r=c.trace(residual,[0.,0.],steps=24,ds=.055)
    self.assertIsNone(r["stop"]);self.assertEqual(len(r["rows"]),25)
    self.assertTrue(r["turning_intervals"])
    peak=max(x["lambda"] for x in r["rows"])
    self.assertLess(abs(peak-2/(3*np.sqrt(3))),.003)
    self.assertLess(r["rows"][-1]["lambda"],peak)
    print("SP_R11C_FOLD_EVIDENCE",json.dumps(r))
 def test_adaptive_no_skip_and_rollback(self):
    @dataclass(frozen=True)
    class State:thermal_minutes:float
    def advance(s,t):
        if t>=7 or t-s.thermal_minutes>2:return s,{"status":"UNRESOLVED"}
        return State(t),{"status":c.OK,"time_minutes":t}
    s,r=c.adaptive(State(0),[0,4,8],range(9),advance)
    self.assertEqual(s.thermal_minutes,6)
    self.assertEqual(r["stop"]["unresolved_minute"],7)
    self.assertGreater(r["recovered_attempts"],0)
    self.assertEqual([x["time_minutes"] for x in r["accepted"]],[0,2,4,6])
 def test_actual_adaptive_and_anchored(self):
    r=c.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertEqual(len(r["runs"]),2)
    for a in r["runs"]:
        self.assertTrue(a["accepted"])
        self.assertEqual(a["accepted"][0]["t"],0.)
        self.assertIsNotNone(a["anchor"])
        self.assertFalse(a["anchor"]["committed_state_changed"])
        for x in a["accepted"]:
            self.assertLessEqual(x["max_axial_residual_kN"],1e-6)
        for x in a["anchor"]["continuation"]["rows"]:
            self.assertLessEqual(x["scaled_force_residual_kNm"],1e-5)
        self.assertIsNone(a["anchor"]["actual_t_R_minutes"])
    print("SP_R11C_ACTUAL_EVIDENCE",json.dumps(r,allow_nan=False))
