import json
import math
import unittest
import numpy as np
from rc_fire.mechanics import sp2026_r10c_quadrature as q
from rc_fire.mechanics import sp2026_r10c_campaign as c
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR10C(unittest.TestCase):
 def test_circle_area_first_moments(self):
    a,x,y=q.circle_moments(0,0,1,0,1,0,1)
    self.assertAlmostEqual(a,math.pi/4)
    self.assertAlmostEqual(x,1/3);self.assertAlmostEqual(y,1/3)
    r=.01;cx=.123;cy=.234
    xx=np.linspace(cx-r,cx+r,8);yy=np.linspace(cy-r,cy+r,9)
    total=np.sum([q.circle_moments(cx,cy,r,a,b,d,e) for a,b in zip(xx,xx[1:]) for d,e in zip(yy,yy[1:])],axis=0)
    self.assertTrue(np.allclose(total,math.pi*r*r*np.array([1.,cx,cy]),rtol=0,atol=1e-12))
 def test_fixed_net_centroids_and_identity(self):
    col=fixture();f=build_annex_k_snapshot(col,0.);f10=build_annex_k_snapshot(col,10.)
    p=prepare_sp2026_design_section(col,f,grid=8)
    mesh=q.build(p,[f10],base_grid=8,max_level=2,delta_C=100.)
    A=q.apply_quadrature(p,f,mesh)
    self.assertTrue(np.all(A>0));self.assertTrue(np.all(p.theta_c==20.))
    self.assertAlmostEqual(A.sum()+p.bar_area.sum(),p.b_m*p.h_m,places=11)
    self.assertAlmostEqual(A@p.x+p.bar_area@p.bar_x,p.b_m*p.h_m*p.b_m/2,places=11)
    self.assertAlmostEqual(A@p.y+p.bar_area@p.bar_y,p.b_m*p.h_m*p.h_m/2,places=11)
    s=h.make_initial(col,f,grid=8,mode=hot.MODIFIED_AT,length_mm=50.,Gwork_N_mm=5.,
                     yield_fraction=.4,strength_basis="SP5_ACCIDENTAL_FCD",quadrature=mesh)
    n,r=h.advance(s,col,f,(50.,1.,1.),time_s=1.)
    self.assertEqual(r["status"],"EQUILIBRATED_RESEARCH_SECTION")
    self.assertIs(n.quadrature,mesh);self.assertEqual(n.geometry,s.geometry)
    self.assertEqual(len(n.concrete),len(mesh.points))
    self.assertTrue(all(x.time_s==0. for x in s.concrete))
 def test_actual_campaign(self):
    r=c.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertEqual(len(r["runs"]),8);self.assertEqual(len(r["comparisons"]),4)
    for run in r["runs"]:
        self.assertEqual(run["rows"][0]["status"],"EQUILIBRATED_RESEARCH_SECTION")
        for a in run["rows"]:
            if a["status"]=="EQUILIBRATED_RESEARCH_SECTION":
                self.assertLessEqual(a["max_conjugate_residual_kN"],1e-6)
                self.assertIsNone(a["actual_t_R_minutes"])
    self.assertIsNone(r["actual_t_R_minutes"])
    # Honest diagnostic: no asserted convergence for a real failed comparison.
    print("SP_R10C_EVIDENCE",json.dumps(r,allow_nan=False))
