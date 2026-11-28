import json
import unittest
from dataclasses import dataclass
import numpy as np
from rc_fire.member import sp2026_r11d_sequential as d
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR11D(unittest.TestCase):
 def test_history_dependent_fold_and_step_refinement(self):
    @dataclass(frozen=True)
    class State:
        peak:float=0.
        count:int=0
    def operator(s):
        def ev(y):
            u,l=y;z=max(s.peak,u)
            return np.array([u-z**3-l]),np.array([[1-3*u*u if u>=s.peak else 1.,-1.]]),z
        return ev
    def commit(s,y,z):return State(z,s.count+1),{"history_peak":z}
    s0=State()
    for ds,steps in ((.055,24),(.0275,48)):
        s,r=d.sequential(s0,[0.,0.],operator,commit,steps=steps,ds=ds,min_ds=ds/8)
        self.assertIsNone(r["stop"]);self.assertEqual(s.count,steps)
        self.assertTrue(r["sampled_maximum_intervals"])
        self.assertLess(abs(max(x["lambda"] for x in r["rows"])-2/(3*np.sqrt(3))),.003)
        self.assertEqual(s0.count,0)
        self.assertTrue(all(y["history_peak"]>=x["history_peak"] for x,y in zip(r["rows"][1:],r["rows"][2:])))
        print("SP_R11D_FOLD_EVIDENCE",json.dumps({"ds":ds,"peak":max(x["lambda"] for x in r["rows"]),"commits":s.count,"turns":r["sampled_maximum_intervals"]}))
 def test_rejected_commit_rollback_and_mechanisms(self):
    @dataclass(frozen=True)
    class State:count:int=0
    def op(s):
        return lambda y:(np.array([y[0]-y[1]]),np.array([[1.,-1.]]),None)
    def reject(s,y,tr):raise ValueError("test rejection")
    s=State();n,r=d.sequential(s,[0.,0.],op,reject,steps=2,ds=.1,min_ds=.025)
    self.assertIs(s,n);self.assertEqual(len(r["rows"]),1)
    self.assertEqual(len(r["attempts"]),3)
    self.assertEqual(d.classify_stop({"status":"UNRESOLVED_GLOBAL_LINE_SEARCH"}),"NUMERICAL_EQUILIBRIUM_STOP")
    self.assertEqual(d.classify_stop({"status":"UNRESOLVED_MEMBER_INPUT_OR_DOMAIN","reason":"SP Table 10 steel temperature outside supported"}),"STEEL_TEMPERATURE_DOMAIN")
    self.assertEqual(d.classify_stop({"status":"UNRESOLVED_NONPOSITIVE_GLOBAL_ALGORITHMIC_TANGENT","converged_equilibrium":True}),"EQUILIBRATED_NONPOSITIVE_TANGENT")
 def test_localization_uses_stored_snapshots_and_preserves_history(self):
    @dataclass(frozen=True)
    class State:thermal_minutes:float
    def advance(s,t):
        if t>=84.75:return s,{"status":"UNRESOLVED_GLOBAL_LINE_SEARCH"}
        return State(t),{"status":d.c.OK,"time_minutes":t}
    s=State(84.)
    stop={"status":"UNRESOLVED_GLOBAL_LINE_SEARCH","last_accepted_minute":84.,"unresolved_minute":85.}
    n,r=d.refine_interval(s,stop,[84.,84.25,84.5,84.75,85.],advance)
    self.assertEqual(n.thermal_minutes,84.5)
    self.assertEqual(r["stop"]["unresolved_minute"],84.75)
    self.assertEqual(s.thermal_minutes,84.)
    n,r=d.refine_interval(s,stop,[84.,85.],advance)
    self.assertIs(s,n);self.assertEqual(r["status"],"NO_DENSE_THERMAL_SNAPSHOTS")
 def test_actual_localization_and_sequential_paths(self):
    r=d.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertTrue(r["accepted"]);self.assertEqual(r["accepted"][0]["t"],0.)
    self.assertIsNone(r["actual_t_R_minutes"])
    for key in ("path_coarse","path_fine"):
        a=r[key];self.assertTrue(a["anchor_unchanged"])
        for x in a["path"]["rows"][1:]:
            self.assertLessEqual(x["axial_residual_kN"],1e-6)
            self.assertLessEqual(x["global_residual_kNm"],1e-6)
        self.assertEqual(a["committed_path_increments"],max(0,len(a["path"]["rows"])-1))
    print("SP_R11D_ACTUAL_EVIDENCE",json.dumps(r,allow_nan=False))
