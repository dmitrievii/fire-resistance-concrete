import json
import unittest
from rc_fire.mechanics import sp2026_r10f_reconcile as f
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR10F(unittest.TestCase):
 def test_equal_areas_do_not_mean_equal_front(self):
    pts=[(.1,.2,.01),(.2,.2,.01)]
    left=lambda x,y:((1e-4 if x<.15 else -1e-4,780.,False),)
    right=lambda x,y:((-1e-4 if x<.15 else 1e-4,780.,False),)
    r=f.audit_signatures(pts,[1.],left,right)
    self.assertAlmostEqual(r["rows"][0]["pilot_active_m2"],r["rows"][0]["final_active_m2"])
    self.assertAlmostEqual(r["max"]["disagreement_m2"],.02)
    self.assertFalse(r["sample_agreement"])
    u=f.audit_signatures(pts,[1.],left,lambda x,y:None)
    self.assertAlmostEqual(u["max"]["unknown_m2"],.02)
    self.assertFalse(u["sample_agreement"])
    self.assertTrue(f.audit_signatures(pts,[1.],left,left)["sample_agreement"])
 def test_accepted_trial_reuse_exact(self):
    c=fixture();fields=[build_annex_k_snapshot(c,t) for t in (0.,1.,2.)]
    kw=dict(grid=8,mode=hot.MODIFIED_AT)
    a=h.run_history(c,fields,(50.,1.,1.),**kw)
    b=h.run_history(c,fields,(50.,1.,1.),**kw,reuse_line_search=True)
    self.assertEqual(a["status"],"DIAGNOSTIC_COMPLETE")
    self.assertEqual(b["status"],a["status"])
    for u,v in zip(a["rows"],b["rows"]):
        self.assertEqual({k:x for k,x in u.items() if k!="trial_counts"},
                         {k:x for k,x in v.items() if k!="trial_counts"})
    x=f.efficiency(a);y=f.efficiency(b)
    self.assertGreater(y["avoided_redundant_concrete_trial_calls"],0)
    self.assertEqual(x["accepted_concrete_trial_calls"]-y["accepted_concrete_trial_calls"],
                     y["avoided_redundant_concrete_trial_calls"])
    print("SP_R10F_REUSE_EVIDENCE",json.dumps({"reference":x,"reuse":y}))
 def test_actual_reconciliation(self):
    r=f.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertFalse(r["admission"]["member_solver_admitted"])
    self.assertIsNone(r["actual_t_R_minutes"])
    for run in r["runs"]:
        for row in run["rows"]:
            if row["status"]=="EQUILIBRATED_RESEARCH_SECTION":
                self.assertLessEqual(row["max_conjugate_residual_kN"],1e-6)
    print("SP_R10F_EVIDENCE",json.dumps(r,allow_nan=False))
