import unittest
import importlib.util
from pathlib import Path
# Load the evidence-only module without the mechanics facade (NumPy).
spec=importlib.util.spec_from_file_location("r10g_evidence",Path(__file__).resolve().parents[1]/"rc_fire/mechanics/sp2026_r10g_evidence.py")
e=importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)

def row(t):
    return {"time_minutes":t,"status":"EQUILIBRATED_RESEARCH_SECTION","max_conjugate_residual_kN":0.,
      "concrete_actions_kN_kNm":[50.,1.,1.],"condensed_D_kNm2":[[100.,0.],[0.,100.]],
      "frozen_elastic_unloading_D_kNm2":[[100.,0.],[0.,100.]],"area_weighted_damage":0.,
      "q":[0.,0.,0.],"compressed_net_area_m2":.03,"thermal_inactive_net_area_m2":0.}
def run(times):return {"status":"DIAGNOSTIC_COMPLETE","rows":[row(t) for t in times]}

class TestEvidence(unittest.TestCase):
 def test_missing_and_duplicate_checkpoints(self):
    a=run(e.COARSE);b=run(e.COARSE)
    self.assertTrue(e.compare(a,b,e.COARSE,e.COARSE)["strict_pass"])
    b["rows"].pop(3)
    self.assertFalse(e.compare(a,b,e.COARSE,e.COARSE)["complete"])
    b["rows"].insert(3,row(2))
    self.assertFalse(e.compare(a,b,e.COARSE,e.COARSE)["complete"])
 def test_distinct_algorithmic_time_diagnostic(self):
    a=run(e.COARSE);b=run(e.FINE)
    b["rows"][0]["condensed_D_kNm2"]=[[80.,0.],[0.,80.]]
    r=e.compare(a,b,e.COARSE,e.FINE,time_refinement=True)
    self.assertEqual(r["common_checkpoints"],27)
    self.assertFalse(r["strict_pass"]);self.assertTrue(r["state_unloading_diagnostic_pass"])
 def test_receipt_fail_closed(self):
    id,sha=e.SOURCES["E"]
    r=e.read_evidence("E",{"id":id,"head_sha":sha,"status":"in_progress","conclusion":None},"")
    self.assertIsNone(r["evidence"])
    self.assertFalse(e.consolidate({"E":r})["numerical_section_admitted"])
    with self.assertRaises(ValueError):e.read_evidence("E",{"id":id,"head_sha":"bad"},"")
    with self.assertRaises(ValueError):e.read_evidence("E",{"id":id,"head_sha":sha,"status":"completed","conclusion":"success"},"")
 def test_cost_identity(self):
    a=run([0]);a["rows"][0].update(trial_counts={"concrete_trials":300,"reused_trials":2},concrete_integration_points=100)
    a.update(efficiency={"accepted_concrete_trial_calls":300,"avoided_redundant_concrete_trial_calls":200},mechanical_wall_s=1.)
    self.assertAlmostEqual(e.cost(a)["call_reduction_fraction"],.4)
    a["efficiency"]["avoided_redundant_concrete_trial_calls"]=201
    with self.assertRaises(ValueError):e.cost(a)
 def test_no_cross_candidate_promotion(self):
    r=e.consolidate({})
    self.assertFalse(r["cross_stage_pass_transfer_allowed"])
    self.assertFalse(r["member_solver_admitted"]);self.assertIsNone(r["actual_t_R_minutes"])
