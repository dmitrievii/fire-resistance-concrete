import unittest
import json
from pathlib import Path
from rc_fire.member import sp2026_r12c_reconciliation as c
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR12CActual(unittest.TestCase):
 def test_targeted_endpoint_campaign(self):
    p=Path("r12c_endpoint_evidence.jsonl")
    with p.open("w") as f:
        def emit(event,payload):
            line=json.dumps({"event":event,"payload":payload},allow_nan=False)
            f.write(line+"\n");f.flush()
            print("SP_R12C_CHECKPOINT",line,flush=True)
        q=c.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5),emit=emit)
        emit("final",q)
    self.assertIsNotNone(q["last_accepted_minute"])
    self.assertIsNone(q["actual_t_R_minutes"])
    for row in q["envelopes"]:
        self.assertNotIn("evidence_error",row)
        for v in row["homotopy"]["rows"]+row.get("scan",{}).get("rows",[]):
            self.assertLessEqual(v["residual_kNm"],1e-7)
            self.assertLessEqual(v["axial_residual_kN"],1e-6)
