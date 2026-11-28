import copy,json,math,unittest
import numpy as np
from rc_fire.integration import mc_r2_reduced as r
from test_mc_r1_engineering import case,CONTRACT
from rc_fire.thermal.normative import RectangularExposure

def column(b=600,h=600,d=20):
    c=case(b,h,d);c["fire_minutes"]=90.
    c["thermal_spec"].update(dry_density_kg_m3=2400.,a_red_mode="table_K1",moisture_mass_pct=None)
    c["bars"]=[v for v in c["bars"] if v["y_mm"]!=h/2]
    for s in c["sections"]:s["My_kNm"]=0.
    return c
KW=dict(selected=True,action_contract=CONTRACT,creep_by_axis={"x":.2,"y":.4})
class TestMC2(unittest.TestCase):
 def test_ambient_independent_rectangle_and_axial_limit(self):
    c=column();q=r.assess(c,0.,**KW)
    self.assertEqual(q["status"],"ALL_MODEL_CHECKS_WITHIN",q)
    A=6*math.pi*.01**2
    self.assertAlmostEqual(q["geometry"]["gross_area_m2"],.36,places=10)
    self.assertAlmostEqual(q["geometry"]["net_area_m2"],.36-A,delta=2e-7)
    I=.6**4/12-A*.25**2-6*math.pi*.01**4/4
    self.assertAlmostEqual(q["geometry"]["I_bending_m4"],I,delta=2e-8)
    c["sections"][0]["N_kN"]=1e6
    q=r.assess(c,0.,**KW)
    self.assertEqual(q["sections"][0]["capacity"]["status"],"AXIAL_DOMAIN_EXCEEDED")
 def test_actual_variable_time_geometry_and_strip_convergence(self):
    for c in (column(),column(500,700,25)):
        rows=[]
        for t in (0,30,60,90):
            q=r.assess(c,t,strips=48,**KW)
            fine=r.assess(c,t,strips=96,**KW)
            print("MC_R2_EVIDENCE",json.dumps({"geometry":[c["b_mm"],c["h_mm"]],"t":t,"coarse":q,"fine":fine},allow_nan=False),flush=True)
            self.assertEqual(q["status"],"ALL_MODEL_CHECKS_WITHIN",q)
            self.assertEqual(fine["status"],"ALL_MODEL_CHECKS_WITHIN",fine)
            self.assertGreaterEqual(fine["geometry"]["gross_area_m2"]+1e-10,q["geometry"]["gross_area_m2"])
            self.assertLess(abs(fine["geometry"]["gross_area_m2"]-q["geometry"]["gross_area_m2"])/fine["geometry"]["gross_area_m2"],.025)
            for s in fine["sections"]:
                self.assertLess(s["capacity"]["axial_residual_kN"],1e-5)
                self.assertLessEqual(s["capacity"]["max_concrete_strain"],.0035+1e-10)
                self.assertLessEqual(s["capacity"]["max_steel_tension_strain"],.010+1e-10)
                self.assertGreater(s["capacity"]["M_Rd_kNm"],0)
            rows.append(fine)
        self.assertGreater(rows[0]["geometry"]["gross_area_m2"],rows[-1]["geometry"]["gross_area_m2"])
        self.assertGreater(rows[-1]["bars"][0]["T_C"],20.)
        self.assertIsNone(rows[-1]["actual_t_R_minutes"])
 def test_scope_and_explicit_choice(self):
    c=column()
    self.assertEqual(r.assess(c,30.,**{**KW,"selected":False})["status"],"UNRESOLVED")
    c["sections"][0]["My_kNm"]=1.
    self.assertIn("BIAXIAL",r.assess(c,30.,**KW)["reason"])
    c=case();c["sections"][0]["My_kNm"]=c["sections"][1]["My_kNm"]=0.
    self.assertIn("TWO_EXTREME",r.assess(c,5.,**KW)["reason"])
 def test_independent_pure_bending_rectangle(self):
    # N fixed by an independent exact integral of the parabola with
    # e(top)=.0035, e(bottom)=-.010. Steel at the two extreme layers
    # is fully yielded with equal and opposite force.
    H=.3;b=.6;eu=.0035;et=.010;ep=.002;k=(eu+et)/(2*H);e=(eu-et)/2
    from scipy.integrate import quad
    stress=lambda z:30*(1-(1-min(1.,max(0.,(e+k*z)/ep)))**2)
    N=1000*b*quad(stress,-H,H,points=[-e/k,(ep-e)/k],epsabs=1e-11)[0]
    M=1000*b*quad(lambda z:z*stress(z),-H,H,points=[-e/k,(ep-e)/k],epsabs=1e-11)[0]+2*1000*.001*500*H
    x,w=np.polynomial.legendre.leggauss(120)
    g={"z":x*H,"A":w*H*b,"zmax":H}
    bars=[{"z":z,"A":.001,"fy":500.,"E":200000.} for z in (-H,H)]
    q=r.capacity(g,bars,N,30.,ep,eu,2.)
    self.assertAlmostEqual(q["M_Rd_kNm"],M,delta=.1)
    self.assertAlmostEqual(q["N_kN"],N,delta=1e-5)
