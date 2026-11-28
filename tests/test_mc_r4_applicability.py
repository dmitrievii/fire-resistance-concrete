import json
import unittest

from rc_fire.integration import mc_r4_applicability as m
from rc_fire.thermal.normative import RectangularExposure, ThermalProfile, resolve_profile
from test_mc_r3_reconciliation import inputs
from test_mc_r2_reduced import KW


class TestMC4(unittest.TestCase):
    def setUp(self):
        self.ex=RectangularExposure(600.,600.,("left","right","bottom","top"))
        self.co=resolve_profile(ThermalProfile("siliceous",2400.))

    def test_corner_and_face_onset(self):
        rows=[m.early_heating_audit(self.ex,self.co,t,500.) for t in (0,7,8,14,15,90)]
        self.assertEqual([q["state"] for q in rows],[
            "NO_CONCRETE_ABOVE_CRITICAL","NO_CONCRETE_ABOVE_CRITICAL",
            "CORNER_ONLY_K27_DOMAIN_UNRESOLVED","CORNER_ONLY_K27_DOMAIN_UNRESOLVED",
            "K27_DOMAIN_UNRESOLVED",  # legacy helper also requires K.23 delta >= 0
            "K27_AREA_AVAILABLE_NOT_MECHANICAL_QUALIFICATION"])
        self.assertAlmostEqual(rows[2]["corner_onset_min"],7.193602619254521)
        self.assertAlmostEqual(rows[2]["side_onset_min"],14.690322240671279)
        self.assertAlmostEqual(rows[-1]["literal_K27"]["remaining_area_m2"],.20063101731132252)
        self.assertTrue(all(q["actual_t_R_minutes"] is None for q in rows))
        print("MC_R4_THERMAL",json.dumps(rows,allow_nan=False))

    def test_clipping_is_counterfactual(self):
        q=m.early_heating_audit(self.ex,self.co,8.,500.)
        self.assertLess(q["raw_lc_m"],0.)
        self.assertGreater(q["raw_ld_m"],0.)
        self.assertLess(q["unauthorized_clip_counterfactual_m2"],.288)
        self.assertEqual(q["literal_K27"]["status"],"out_of_scope")
        self.assertFalse(q["normative_claim"])

    def test_k18_biaxial_gate(self):
        q=m.k18_action_scope()
        self.assertIsNone(q["axis"])
        self.assertIn("BIAXIAL_OR_MIXED_AXIS_BENDING_OUTSIDE_8_2_21",q["scope_issues"])
        self.assertAlmostEqual(q["effective_lengths_m"]["y"],16.44)
        self.assertFalse(q["complete_legacy_top_check"])
        print("MC_R4_K18",json.dumps(q,allow_nan=False))

    def test_matched_governing_load_campaign(self):
        c=inputs()
        rows=[]
        for N,M in ((100.,5.),(527.16,6.5),(1134.,16.),(1134.,38.9),(2000.,100.)):
            for t in (0.,30.,60.,90.):
                q=m.governing_load_comparator(c,time_minutes=t,axial_kN=N,moment_kNm=M,**KW)
                self.assertIsNone(q["actual_t_R_minutes"])
                self.assertFalse(q["normative_claim"])
                a,b=(q["comparison"]["methods"][v] for v in ("contour","k27_cross"))
                for method in (a,b):
                    self.assertFalse(method["normative_claim"])
                    for s in method.get("sections",[]):
                        self.assertEqual(s["N_kN"],N)
                        self.assertEqual(s["M0_kNm"],M)
                        self.assertAlmostEqual(s["nominal"]["x"]["l0_m"],10.96)
                        self.assertAlmostEqual(s["nominal"]["y"]["l0_m"],16.44)
                if a.get("bars") is not None and b.get("bars") is not None:
                    self.assertEqual(a["bars"],b["bars"])
                if N==100. and t==90.:
                    self.assertIn(a["status"],("ALL_MODEL_CHECKS_WITHIN","MODEL_LIMIT_OR_UNRESOLVED"))
                    self.assertIn(b["status"],("ALL_MODEL_CHECKS_WITHIN","MODEL_LIMIT_OR_UNRESOLVED"))
                rows.append(q)
        self.assertEqual(len(rows),20)
        print("MC_R4_LOAD_CAMPAIGN",json.dumps(rows,allow_nan=False))

    def test_non_square_rejected(self):
        with self.assertRaisesRegex(ValueError,"K27_REQUIRES"):
            m.early_heating_audit(RectangularExposure(500,600,self.ex.faces),self.co,8.,500.)
