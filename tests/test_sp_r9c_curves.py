import json
import unittest
from rc_fire.verification.sp2026_r9c_curves import campaign,shape,normalized_curve,load_data
class TestR9C(unittest.TestCase):
    def test_strict_shape_domain(self):
        self.assertIsNone(shape(2.,"SP_RATIONAL"))
        self.assertAlmostEqual(shape(1.,"POPOVICS"),1.)
        self.assertAlmostEqual(shape(1.,"SP_RATIONAL"),1.)
    def test_no_extension_as_strain(self):
        with self.assertRaises(ValueError):normalized_curve(load_data()["steel"][0])
    def test_no_ultimate_from_truncation(self):
        r=campaign()
        self.assertTrue(all(x["postpeak_20pct_crossing"] is None for x in r["curves"]))
        self.assertFalse(r["SP_model_admitted"])
    def test_actual_evidence(self):
        r=campaign()
        self.assertEqual(len(r["curves"]),3)
        self.assertEqual(len(r["holdout_ids"]),2)
        self.assertTrue(all(x["models"]["SP_RATIONAL"]["unsupported_anchors"]>=0 for x in r["curves"]))
        self.assertEqual(r["independent_primary_full_concrete_curves"],0)
        print("SP_R9C_EVIDENCE",json.dumps(r,allow_nan=False))
