import json
import math
import unittest
import numpy as np
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r10b_steel_history as st
from rc_fire.mechanics import sp2026_r10b_convergence as c
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR10B(unittest.TestCase):
 def test_circle_tangent_and_partition(self):
    for r in (1.,.01):
        self.assertAlmostEqual(h._circle_rectangle_area(0,0,r,-r,r,-r,r),math.pi*r*r,places=12)
        for n in (3,4,7):
            a=np.linspace(-r,r,n+1)
            total=sum(h._circle_rectangle_area(0,0,r,x,y,z,w)
                      for x,y in zip(a,a[1:]) for z,w in zip(a,a[1:]))
            self.assertAlmostEqual(total,math.pi*r*r,places=12)
 def test_steel_signed_history_and_reverse_yield(self):
    s=st.SteelState()
    def f(s,e):return st.trial(s,temperature_C=20,mechanical_strain=e,E_MPa=200000,fy_MPa=500,mode=st.PLASTIC)
    a,C,_=f(s,.005);self.assertAlmostEqual(a.stress_MPa,500)
    self.assertAlmostEqual(a.plastic_strain,.0025);self.assertEqual(C,0.)
    b,C,_=f(a,.0025);self.assertAlmostEqual(b.stress_MPa,0.)
    self.assertEqual(C,200000);self.assertEqual(a.plastic_strain,b.plastic_strain)
    d,C,_=f(b,-.003);self.assertAlmostEqual(d.stress_MPa,-500)
    self.assertGreater(d.accumulated_plastic_strain,a.accumulated_plastic_strain)
    self.assertEqual(s.plastic_strain,0.)
 def test_heating_yield_and_guard(self):
    s=st.SteelState()
    a,_,_=st.trial(s,temperature_C=400,mechanical_strain=.005,E_MPa=170000,fy_MPa=425,mode=st.PLASTIC)
    b,_,_=st.trial(a,temperature_C=600,mechanical_strain=.005,E_MPa=154000,fy_MPa=185,mode=st.PLASTIC)
    self.assertAlmostEqual(b.stress_MPa,185)
    self.assertGreater(b.plastic_strain,a.plastic_strain)
    self.assertFalse(st.admitted(b,st.PLASTIC,185,diagnostic_strain_limit=.001))
    with self.assertRaises(ValueError):
        st.trial(b,temperature_C=801,mechanical_strain=.005,E_MPa=1,fy_MPa=1,mode=st.PLASTIC)
 def test_matched_actual_campaign(self):
    r=c.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertEqual(len(r["runs"]),10);self.assertEqual(len(r["comparisons"]),4)
    for run in r["runs"]:
        self.assertEqual(run["rows"][0]["status"],"EQUILIBRATED_RESEARCH_SECTION")
        for a in run["rows"]:
            if a["status"]=="EQUILIBRATED_RESEARCH_SECTION":
                self.assertLessEqual(a["max_conjugate_residual_kN"],1e-6)
                self.assertIsNone(a["actual_t_R_minutes"])
    # Do not assert convergence when actual evidence may fail.
    print("SP_R10B_EVIDENCE",json.dumps(r,allow_nan=False))
