import json
import unittest
import importlib.util
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("r12a_evidence",root/"rc_fire/member/sp2026_r12a_resistance.py")
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def scan(values,complete=True,family="one_thermal_increment"):
    rows=[{"midspan_x_mm":float(i),"lambda":v,"residual_kNm":0.,"axial_residual_kN":0.} for i,v in enumerate(values)]
    return r.sample(rows,family=family,expected_count=3,complete=complete,N=1500.)

class TestR12A(unittest.TestCase):
 def test_archive_actual(self):
    a=r.from_r11d(json.loads((root/"validation/sp_r12a_r11d_receipt.json").read_text()))
    self.assertEqual(a["computational_stop_interval_min"],[83.75,84.])
    self.assertAlmostEqual(a["history"][-2]["U_sample"],1/1.002476638349519)
    self.assertTrue(all(x["U_sample"] is None for x in a["history"][:-2]))
    self.assertIsNone(a["history"][-1]["U_sample"]);self.assertIsNone(a["actual_t_R_minutes"])
    print("SP_R12A_ARCHIVED_EVIDENCE",json.dumps(a,allow_nan=False))
 def test_open_or_partial_scan_no_U(self):
    for x in (scan([.9,1.,1.1]),scan([1.,1.1,1.],False),scan([1.,1.1,1.1])):
        self.assertIsNone(x["U_sample"])
        self.assertIsNone(x["continuous_capacity_upper_bound"])
 def test_observed_crossing_not_physical(self):
    a,b=scan([.9,1.01,.9]),scan([.9,.99,.9])
    p=r.sampled_threshold_pair(a,b,t0=83.75,t1=84.,same_anchor_and_scan=True)
    self.assertEqual(p["observed_sampled_crossing"],[83.75,84.]);self.assertIsNone(p["actual_t_R_minutes"])
    self.assertIsNone(r.sampled_threshold_pair(a,b,t0=83.75,t1=84.,same_anchor_and_scan=False)["observed_sampled_crossing"])
    self.assertIsNone(r.sampled_threshold_pair({**a,"family":"sequential_isothermal"},b,t0=83.75,t1=84.,same_anchor_and_scan=True)["observed_sampled_crossing"])
 def test_missing_and_invalid_residual(self):
    self.assertIsNone(scan([1.,1.01])["U_sample"])
    with self.assertRaises(ValueError):
        r.sample([{"midspan_x_mm":0.,"lambda":1.,"residual_kNm":1.,"axial_residual_kN":0.}],family="one_thermal_increment",expected_count=3,complete=True,N=1500.)

 def test_latest_archive_actual(self):
    a=r.extract(json.loads((root/"validation/sp_r12a_r11e_receipt.json").read_text()))
    self.assertEqual(a["quarter_interval_min"],[83.75,84.])
    self.assertEqual(a["computational_stop_interval_min"],[83.75,83.875])
    self.assertAlmostEqual(a["U_sample"],1/1.0023617861460141)
    self.assertFalse(a["path_convergence"]["research_pass"])
    self.assertEqual(a["endpoint"]["sample_count"],0)
    self.assertIsNone(a["endpoint"]["U_sample"])
    self.assertIsNone(a["observed_sampled_crossing"])
    self.assertIsNone(a["actual_t_R_minutes"])
    print("SP_R12A_LATEST_ARCHIVED_EVIDENCE",json.dumps(a,allow_nan=False))
