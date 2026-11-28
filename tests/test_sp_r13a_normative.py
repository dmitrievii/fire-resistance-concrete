import json
import unittest
from rc_fire.materials.normative import ConcreteMix,Reinforcement
from rc_fire.materials.sp2026_fire import SPFireMaterialError
from rc_fire.materials.sp2026_full_nonlinear import SP5RebarDuctility,steel_sp5_ascending_stress
from rc_fire.materials import sp2026_r13a_normative as a

class TestR13A(unittest.TestCase):
 def setUp(self):
    self.c=ConcreteMix("C30/37",aggregate_family="siliceous",independently_measured_Ecm_GPa=41.)
    self.s=Reinforcement("S500")
 def test_table9_10_all_nodes_and_distinct_modulus(self):
    r=a.audit(self.c,self.s)
    kc=[1,.99,.98,.95,.85,.80,.60,.20,.10]
    beta=[1,.85,.70,.50,.40,.30,.20,.10,.05]
    ks=[1,1,1,1,.85,.60,.37,.22,.10]
    for v,k,b,s in zip(r["rows"],kc,beta,ks):
        self.assertAlmostEqual(v["fc_characteristic_MPa"],30*k)
        self.assertAlmostEqual(v["fc_accidental_MPa"],25*k)
        self.assertAlmostEqual(v["beta_E_MPa"],41000*b)
        self.assertAlmostEqual(v["steel_yield_MPa"],500*s)
    self.assertFalse(r["hot_peak_ultimate_strains_qualified"])
    print("SP_R13A_MATERIAL_EVIDENCE",json.dumps(r,allow_nan=False))
 def test_bounded_section_and_derivative(self):
    f=lambda e:a.section_concrete(self.c,600.,e)
    self.assertAlmostEqual(f(.002)["stress_MPa"],18.)
    self.assertEqual(f(.0035)["status"],"AT_ASSUMED_SECTION_LIMIT")
    self.assertIsNone(f(.0035001)["stress_MPa"])
    e=.001;h=1e-8
    self.assertAlmostEqual((f(e+h)["stress_MPa"]-f(e-h)["stress_MPa"])/(2*h),f(e)["tangent_MPa"],delta=1e-4)
    self.assertAlmostEqual(a.section_concrete(self.c,800.,.002)["stress_MPa"],3.)
    self.assertEqual(a.section_concrete(self.c,800.001,.1)["stress_MPa"],0.)
    with self.assertRaises(SPFireMaterialError):a.steel_section(self.s,800.001,0.)
 def test_steel_section_vs_member_and_correct_hardening(self):
    x=a.steel_section(self.s,600.,-.010001)
    self.assertTrue(x["section_tension_limit_exceeded"])
    self.assertIsNone(x["member_hot_rupture_strain"])
    self.assertFalse(a.steel_section(self.s,600.,.02)["section_tension_limit_exceeded"])
    d=SP5RebarDuctility(1.08,.05,1.,material_certificate="synthetic ambient benchmark")
    fy=500.;ey=fy/200000.;eu=.045
    v=steel_sp5_ascending_stress(eu,20.,self.s,ductility=d)
    self.assertAlmostEqual(v[0],fy+(1.08*fy-fy)*(eu-ey)/(.05-ey))
    self.assertLess(v[0],540.)
    with self.assertRaises(SPFireMaterialError):steel_sp5_ascending_stress(eu+1e-6,20.,self.s,ductility=d)
    print("SP_R13A_STEEL_EVIDENCE",json.dumps({"yield_MPa":fy,"epsilon_uk":.05,"epsilon_ud":eu,
          "corrected_sigma_at_ud_MPa":v[0],"old_sigma_at_ud_MPa":540.}))
