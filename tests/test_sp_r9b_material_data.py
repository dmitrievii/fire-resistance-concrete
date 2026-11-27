import copy
import json
import unittest
from rc_fire.verification.sp2026_r9b_material_data import (
    load_anchors,compare_concrete_series,compare_steel_modulus,run_material_campaign)

class TestR9BMaterials(unittest.TestCase):
    def test_published_anchors_and_same_geometry_normalization(self):
        r=run_material_campaign()
        rows=r["concrete"][0]["rows"]
        self.assertEqual(len(rows),5)
        self.assertAlmostEqual(rows[-1]["measured_peak_strain_ratio"],7.28/2.06)
        self.assertAlmostEqual(rows[-1]["measured_strength_ratio"],16.60/58.43)
        self.assertAlmostEqual(rows[-1]["SP_constant_k_peak_ratio"],1.5)
        self.assertIsNone(rows[-1]["measured_ultimate_strain"])
        self.assertFalse(r["SP_only_model_admitted"])
    def test_residual_not_admitted(self):
        s=copy.deepcopy(load_anchors()["concrete"][0])
        s["protocol"]="residual_after_cooling"
        with self.assertRaises(ValueError):compare_concrete_series(s)
    def test_steel_reading_uncertainty_and_conflict(self):
        r=compare_steel_modulus(load_anchors()["steel"])
        self.assertEqual(len(r["rows"]),9)
        self.assertEqual(r["transient_undisputed_count"],7)
        conflict=next(x for x in r["transient_records"] if x["id"]=="D8A")
        self.assertTrue(conflict["disputed"])
        self.assertEqual((conflict["rupture_temperature_C"],conflict["text_alternative_C"]),(487,482))
        self.assertFalse(r["rupture_prediction_performed"])
    def test_real_evidence_emitted_and_no_fitting(self):
        r=run_material_campaign()
        self.assertEqual(r["parameters_fitted"],0)
        self.assertIsNone(r["actual_t_R_minutes"])
        self.assertFalse(r["independent_full_curve_validation_completed"])
        print("SP_R9B_EVIDENCE",json.dumps(r,allow_nan=False,ensure_ascii=True))
