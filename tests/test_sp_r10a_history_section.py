import json
import unittest
import numpy as np
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r3_member import make_column,user_inputs

def fixture():
    c=make_column(user_inputs());c["fire_minutes"]=10.
    c["thermal_spec"].update(a_red_mode="formula_K1_450C",moisture_mass_pct=1.5)
    return c

class TestR10A(unittest.TestCase):
 def setUp(self):
    self.c=fixture();self.f=build_annex_k_snapshot(self.c,0.)
 def initial(self):
    return h.make_initial(self.c,self.f,grid=8,mode=hot.MODIFIED_AT,length_mm=50.,
                          Gwork_N_mm=5.,yield_fraction=.4,strength_basis="SP5_ACCIDENTAL_FCD")
 def test_exact_circle_and_net_area(self):
    self.assertAlmostEqual(h._circle_rectangle_area(0,0,1,-1,1,-1,1),np.pi)
    self.assertAlmostEqual(h._circle_rectangle_area(0,0,1,0,1,0,1),np.pi/4)
    for n in (8,12,24):
        p=prepare_sp2026_design_section(self.c,self.f,grid=n)
        A=h.net_areas(p,n)
        self.assertTrue(np.all(A>=0))
        self.assertAlmostEqual(A.sum()+p.bar_area.sum(),p.b_m*p.h_m,places=12)
 def test_ambient_biaxial_and_tangent(self):
    s=self.initial()
    a,r=h.advance(s,self.c,self.f,(50.,1.,1.),time_s=1.)
    self.assertEqual(r["status"],"EQUILIBRATED_RESEARCH_SECTION")
    self.assertTrue(np.allclose(r["actions_kN_kNm"],[50.,1.,1.],atol=1e-6))
    p,A,C,B,E,fy=h._prepare(a,self.c,self.f)
    q=np.asarray(a.q);F,J,*_=h._trial(a,p,A,C,B,E,fy,2.,q)
    for i in range(3):
        d=np.eye(3)[i]*1e-8
        lo=h._trial(a,p,A,C,B,E,fy,2.,q-d)[0]
        hi=h._trial(a,p,A,C,B,E,fy,2.,q+d)[0]
        self.assertTrue(np.allclose((hi-lo)/2e-8,J[:,i],rtol=1e-5,atol=.02))
    self.assertTrue(np.allclose(J,J.T))
 def test_rejected_state_unchanged(self):
    s=self.initial()
    a,r=h.advance(s,self.c,self.f,(1e8,0.,0.),time_s=1.,max_iterations=3)
    self.assertIs(a,s);self.assertNotEqual(r["status"],"EQUILIBRATED_RESEARCH_SECTION")
    self.assertTrue(all(x.time_s==0 for x in s.concrete))
 def test_actual_history_campaign(self):
    r=h.campaign(self.c,reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertEqual(len(r["runs"]),10)
    self.assertTrue(any(x["status"]=="DIAGNOSTIC_COMPLETE" for x in r["runs"]))
    for run in r["runs"]:
        self.assertEqual(run["rows"][0]["status"],"EQUILIBRATED_RESEARCH_SECTION")
        for a in run["rows"]:
            if a["status"]=="EQUILIBRATED_RESEARCH_SECTION":
                self.assertLessEqual(a["max_conjugate_residual_kN"],1e-6)
                self.assertIsNone(a["actual_t_R_minutes"])
    print("SP_R10A_EVIDENCE",json.dumps(r,allow_nan=False))
