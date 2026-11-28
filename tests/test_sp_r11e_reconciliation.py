import json
import unittest
import numpy as np
from rc_fire.member import sp2026_r11e_reconciliation as e
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR11E(unittest.TestCase):
 def test_displacement_control_across_fold(self):
    def op(x,l):
        u=x[0]
        return np.array([u-u**3-l]),np.array([[1.-3*u*u]]),np.array([-1.]),None
    r=e.displacement_scan(op,[0.],[0],0,np.linspace(0,1,101))
    self.assertIsNone(r["stop"]);self.assertEqual(len(r["rows"]),101)
    self.assertTrue(r["sampled_maxima_indices"])
    self.assertLess(abs(max(x["lambda"] for x in r["rows"])-2/(3*np.sqrt(3))),.0001)
 def test_reserve_not_total_load(self):
    def path(peak):
        return {"anchor_minute":83.75,"initial_inventory":{},"path":{"stop":None,
            "rows":[{"lambda":1.},{"midspan_x_mm":2.,"lambda":peak},{"midspan_x_mm":3.,"lambda":1.}],
            "sampled_maximum_intervals":[{}]}}
    r=e.compare_paths(path(1.002),path(1.0025),1.,N=1500.)
    self.assertTrue(r["sampled_turns_on_both"]);self.assertFalse(r["research_pass"])
    self.assertAlmostEqual(r["peak_reserve_relative_delta"],.2)
    self.assertTrue(e.compare_paths(path(1.0025),path(1.0025),1.,N=1500.)["research_pass"])
 def test_actual_matched_reconciliation(self):
    r=e.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertFalse(r["physical_failure_proven"]);self.assertIsNone(r["actual_t_R_minutes"])
    if r["endpoint"] and "rows" in r["endpoint"]:
        for x in r["endpoint"]["rows"]:
            self.assertLessEqual(x["axial_residual_kN"],1e-6)
            self.assertLessEqual(x["residual_kNm"],1e-7)
    print("SP_R11E_EVIDENCE",json.dumps(r,allow_nan=False))
