import unittest
import json
from rc_fire.member import sp2026_r12a_campaign as c
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR12AActual(unittest.TestCase):
 def test_targeted_history(self):
    q=c.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertTrue(q["history"])
    self.assertEqual(q["history"][0]["t"],0.)
    self.assertIsNone(q["actual_t_R_minutes"]);self.assertIsNone(q["physical_failure_bracket_min"])
    self.assertTrue(all(v["normative_U"] is None for v in q["history"]))
    print("SP_R12A_ACTUAL_EVIDENCE",json.dumps(q,allow_nan=False))
