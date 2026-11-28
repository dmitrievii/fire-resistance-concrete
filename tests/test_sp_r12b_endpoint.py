import unittest
import json
import numpy as np
from rc_fire.member import sp2026_r12b_endpoint as b
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR12B(unittest.TestCase):
 def test_controlled_load_seed_and_fold(self):
    # lambda=u-u^3-t, independent analytical thermal-offset model.
    x=np.array([.5]);lam=.375
    for t in (0.,.01,.02):
        def op(x,l):
            u=x[0];return np.array([u-u**3-t-l]),np.array([[1.-3*u*u]]),np.array([-1.]),None
        sol,rep=b.correct(op,x,lam,[0],0,.5)
        self.assertIsNotNone(sol);x,lam=sol[:2]
        self.assertAlmostEqual(lam,.375-t)
        self.assertLessEqual(rep["residual_kNm"],1e-7)
    for u in (.55,.58,.65):
        sol,rep=b.correct(op,x,lam,[0],0,u)
        self.assertAlmostEqual(sol[1],u-u**3-.02)
        x,lam=sol[:2]
 def test_rejection_does_not_mutate_seed(self):
    x=np.array([.5,0.])
    def op(x,l):raise ValueError("domain")
    sol,rep=b.correct(op,x,1.,[0,1],0,.6)
    self.assertIsNone(sol);self.assertEqual(x.tolist(),[.5,0.])
    self.assertEqual(rep["status"],"UNRESOLVED_CONTROLLED_TRIAL")
 def test_native_numeric_endpoint_contract(self):
    from types import SimpleNamespace
    from rc_fire.member import sp2026_r12a_resistance as r
    beam=SimpleNamespace(n=1,free=np.array([0]),initial=np.array([0.]),scale=np.array([1.]))
    def op(x,l):
        u=x[0]
        return np.array([u-u**3-l]),np.array([[1.-3*u*u]]),np.array([-1.]),None
    seed=(np.array([.5]),.375)
    rows=[]
    for u in (.5,.58,.65):
        sol,row=b.controlled(beam,op,lambda sol:{"axial_residual_kN":0.},seed,u)
        self.assertIsNotNone(sol)
        self.assertIs(type(row["midspan_x_mm"]),float)
        rows.append(row);seed=sol
    sample=r.endpoint({"rows":rows,"stop":None},N=1500.,expected_count=3)
    self.assertEqual(sample["status"],"INTERIOR_SAMPLED_MAXIMUM")
    self.assertAlmostEqual(sample["sampled_peak_lambda"],.58-.58**3)
    json.dumps(sample,allow_nan=False)
 def test_actual_coupled_endpoint(self):
    q=b.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertIsNotNone(q["last_accepted_minute"])
    self.assertIsNone(q["actual_t_R_minutes"])
    for row in q["envelopes"]:
        for v in row["homotopy"]["rows"]:
            self.assertLessEqual(v["residual_kNm"],1e-7)
            self.assertLessEqual(v["axial_residual_kN"],1e-6)
        for v in row.get("scan",{}).get("rows",[]):
            self.assertLessEqual(v["residual_kNm"],1e-7)
    print("SP_R12B_EVIDENCE",json.dumps(q,allow_nan=False))
