import json
import math
import unittest
import numpy as np
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.member import sp2026_r11b_extended_member as b
from rc_fire.member.coupled import EndSupport
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR11B(unittest.TestCase):
 def test_generalized_geometric_margin_and_supports(self):
    D=np.array([[1000.,120.],[120.,700.]])
    S=np.array([.3,.3]);Q=np.zeros((3,3));Q[0,0]=1e6;Q[1:,1:]=D/np.outer(S,S)
    L=3.;z=np.linspace(0,L,17);rows=[]
    for support,factor in (("pinned",1.),("fixed",4.)):
        exact=factor*math.pi**2*np.linalg.eigvalsh(D)[0]/L**2
        for frac in (.5,.95,1.05):
            beam=m.Beam(z,frac*exact,EndSupport(support),EndSupport(support),
                        np.zeros((len(z),2)),np.zeros(4*len(z)),np.zeros(4*len(z)),S)
            law=lambda i,q:(Q@q,Q,None)
            _,K,_=beam.assemble(beam.zero(),law)
            margin=beam.geometric_margin(K)
            self.assertLess(abs(margin["frozen_tangent_eigenload_kN"]/exact-1),.005)
            sol,r=beam.solve(beam.zero(),law)
            if frac<1:self.assertEqual(r["status"],"EQUILIBRATED_RESEARCH_MEMBER")
            else:
                self.assertIsNone(sol);self.assertEqual(r["status"],"UNRESOLVED_NONPOSITIVE_GLOBAL_ALGORITHMIC_TANGENT")
                self.assertTrue(r["converged_equilibrium"])
            rows.append({"support":support,"load_fraction":frac,"exact_kN":exact,
                        "computed_kN":margin["frozen_tangent_eigenload_kN"],
                        "margin_kN":margin["additive_geometric_margin_kN"],"status":r["status"]})
    print("SP_R11B_LINEAR_EVIDENCE",json.dumps(rows))
 def test_actual_extended_campaign(self):
    r=b.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertEqual(len(r["runs"]),6)
    self.assertEqual(len(r["comparisons"]),2)
    for a in r["runs"]:
        self.assertTrue(a["accepted"],a)
        self.assertEqual(a["accepted"][0]["t"],0.)
        self.assertIsNone(a["actual_t_R_minutes"])
        for x in a["accepted"]:
            self.assertLessEqual(x["max_axial_residual_kN"],1e-6)
            self.assertLessEqual(x["scaled_free_residual_kNm"],1e-6)
    self.assertFalse(r["section_numerically_admitted"])
    print("SP_R11B_EXTENDED_EVIDENCE",json.dumps(r,allow_nan=False))
 def test_comparison_does_not_promote_truncated_histories(self):
    r={"id":"a","status":"UNRESOLVED_HISTORY_STOP","accepted":[]}
    s=b.compare(r,{**r,"id":"b"},[0.,90.],axis="time")
    self.assertFalse(s["complete"]);self.assertFalse(s["strict_research_pass"])
