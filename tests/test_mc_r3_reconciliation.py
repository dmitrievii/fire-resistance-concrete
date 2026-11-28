import json,unittest,copy
from rc_fire.integration import mc_r3_reconciliation as m
from test_mc_r2_reduced import column,KW

def inputs():
    c=column();c["annex_l_spec"]={"natural_sand_confirmed":True,
        "coarse_aggregate_volume_pct":50.,"max_aggregate_mm":20.,
        "cement_kg_m3":300.,"water_cement_ratio":.5,"relative_humidity_pct":75.}
    return c

class TestMC3(unittest.TestCase):
 def test_original_moment_reference_and_margin(self):
    q=m.historical_reference()
    for x in q["axes"].values():
        self.assertAlmostEqual(x["legacy_centroid_reference_MRd_kNm"]-x["legacy_centroid_reference_MEd_kNm"],x["moment_margin_kNm"])
    self.assertAlmostEqual(q["axes"]["x"]["steel_reference_MRd_kNm"],421.350648996387)
    print("MC_R3_LEGACY",json.dumps(q,allow_nan=False))
 def test_matched_square_and_area_identity(self):
    c=inputs();q=m.compare(c,90.,**KW)
    a,b=q["methods"]["contour"],q["methods"]["k27_cross"]
    print("MC_R3_MATCHED",json.dumps(q,allow_nan=False))
    self.assertEqual(a["status"],"ALL_MODEL_CHECKS_WITHIN",a)
    self.assertEqual(b["status"],"ALL_MODEL_CHECKS_WITHIN",b)
    self.assertAlmostEqual(b["geometry"]["gross_area_m2"],b["geometry"]["K27"]["remaining_area_m2"],places=10)
    self.assertLess(b["geometry"]["gross_area_m2"],a["geometry"]["gross_area_m2"])
    self.assertEqual(a["bars"],b["bars"])
    self.assertTrue(all(x["capacity"]["axial_residual_kN"]<1e-5 for x in b["sections"]))
    self.assertIsNotNone(q["annex_l"]["F"])
 def test_whole_minute_limit_and_unknown_separate(self):
    c=inputs();c["sections"][1]["Mx_kNm"]=200.
    q=m.history(c,end_minute=90,required_minutes=90,**KW)
    k=m.history(c,end_minute=90,area_method="k27_cross",required_minutes=90,**KW)
    for h in (q,k):
        print("MC_R3_HISTORY",json.dumps({key:val for key,val in h.items() if key!="samples"} | {
           "rows":[{key:val for key,val in row.items() if key!="sections"} for row in h["samples"]]},allow_nan=False))
        self.assertIsNone(h["actual_t_R_minutes"])
        self.assertFalse(h["normative_claim"])
    self.assertIsNotNone(q["sampled_limit_interval_min"],q)
    self.assertEqual(q["sampled_limit_interval_min"][1]-q["sampled_limit_interval_min"][0],1)
    self.assertEqual(q["required_model_check"],"MODEL_LIMIT_EXCEEDED")
    if k["first_unknown_minute"] is not None:
        self.assertIsNone(k["sampled_limit_interval_min"])
        self.assertIsNone(k["whole_minute_model_result"])
    z=copy.deepcopy(c);z["sections"][0]["My_kNm"]=1.
    h=m.history(z,end_minute=90,**KW)
    self.assertEqual(h["first_unknown_minute"],0)
    self.assertIsNone(h["whole_minute_model_result"])
 def test_k27_not_generalized_to_rectangle(self):
    q=m.compare(column(500,700,25),90.,**KW)
    self.assertEqual(q["methods"]["k27_cross"]["status"],"UNRESOLVED")
    self.assertEqual(q["methods"]["contour"]["status"],"ALL_MODEL_CHECKS_WITHIN")
 def test_missing_annex_l_not_pass(self):
    c=inputs();c["annex_l_spec"].pop("cement_kg_m3")
    c.pop("spalling",None)
    self.assertEqual(m.spalling(c)["status"],"UNRESOLVED_ANNEX_L")
