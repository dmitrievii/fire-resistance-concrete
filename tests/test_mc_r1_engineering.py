import copy,json,math,unittest
from rc_fire.integration import mc_r1_engineering as m
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot,reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

CONTRACT={k:True for k in ("first_order_fire_actions","imperfections_and_minimum_eccentricity_reconciled",
    "effective_lengths_and_critical_sections_confirmed","uniform_longitudinal_heating_confirmed")}
KW=dict(basis=m.CHARACTERISTIC,creep_by_axis={"x":.2,"y":.4},action_contract=CONTRACT,grid=8)
def case(b=600,h=600,d=20):
    c=fixture();c.update(b_mm=b,h_mm=h,fire_minutes=10.,length_m=3.,mu_x=.8,mu_y=1.2)
    c["bars"]=[{"id":str(i),"x_mm":x*b,"y_mm":y*h,"diameter_mm":d} for i,(x,y) in enumerate(
      [(1/12,1/12),(.5,1/12),(11/12,1/12),(1/12,.5),(11/12,.5),(1/12,11/12),(.5,11/12),(11/12,11/12)])]
    c["sections"]=[{"id":"bottom","z_m":0.,"N_kN":50.,"Mx_kNm":2.,"My_kNm":-2.},
                   {"id":"top","z_m":3.,"N_kN":100.,"Mx_kNm":5.,"My_kNm":-4.}]
    return c
def heat(c):
    return solve_sp2026_2d_heat(c,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
        cell_count_x=16,cell_count_y=16,max_step_minutes=1.,sample_times_minutes=[0.,5.,10.])

class TestMC1(unittest.TestCase):
 def test_original_mathcad_region_parity(self):
    r=m.replay()["v2"]
    for a,Md,Mr in (("x",162.67566821423009,421.350648996387),("y",175.02390560348997,421.35064939232279)):
        self.assertAlmostEqual(r[a]["M_Ed_kNm"],Md,places=6)
        self.assertAlmostEqual(r[a]["M_Rd_kNm"],Mr,places=6)
    print("MC_R1_SOURCE_REPLAY",json.dumps(r))
 def test_actual_variable_geometry_bar_duration_and_actions(self):
    runs=[]
    for c in (case(),case(500,700,25)):
        f=heat(c)
        r=m.history(c,f,[0,5,10],**KW)
        self.assertEqual(len(r["samples"]),3)
        self.assertTrue(all(x["status"]=="ALL_SAMPLED_SECTIONS_WITHIN_MODEL_LIMITS" for x in r["samples"]))
        for x in r["samples"]:
            self.assertEqual(x["section_count"],2);self.assertEqual(len(x["bar_temperatures_C"]),8)
            for s in x["sections"]:
                self.assertLess(s["section"]["relative_residual"],1e-6)
                self.assertEqual(s["nominal"]["x"]["phi_eff"] if "phi_eff" in s["nominal"]["x"] else KW["creep_by_axis"]["x"],.2)
                self.assertLess(s["M2_kNm"]["y"],0.)
                self.assertAlmostEqual(s["M2_kNm"]["x"],s["M0_kNm"]["x"]*s["nominal"]["x"]["eta_a"])
            self.assertIsNone(x["actual_t_R_minutes"])
        self.assertNotEqual(r["samples"][0]["bar_temperatures_C"],r["samples"][-1]["bar_temperatures_C"])
        runs.append(r)
    self.assertNotEqual(runs[0]["samples"][-1]["bar_temperatures_C"],runs[1]["samples"][-1]["bar_temperatures_C"])
    print("MC_R1_VARIABLE_EVIDENCE",json.dumps([{"samples":[{"t":s["time_minutes"],"status":s["status"],
         "bars":s["bar_temperatures_C"],"governing":s["governing_sampled_strain_section"],
         "sections":[{"id":x["id"],"N":x["N_kN"],"M2":x["M2_kNm"],"ratio":x["section"]["critical_ratio"],
             "Ncr":[x["nominal"][a]["Ncrit_kN"] for a in ("x","y")]} for x in s["sections"]]} for s in r["samples"]]} for r in runs],allow_nan=False))
 def test_explicit_action_contract_and_invalid_bar(self):
    c=case();f=select_sp2026_snapshot(heat(c),0.)
    with self.assertRaises(ValueError):m.assess(c,f,**{**KW,"action_contract":{}})
    c["bars"][0]["x_mm"]=1.
    with self.assertRaises(ValueError):m.assess(c,f,**KW)
 def test_source_method_and_unknown_never_rating(self):
    c=case();f=heat(c)
    c["sections"][1]["N_kN"]=1e8
    r=m.assess(c,select_sp2026_snapshot(f,0.),**KW)
    self.assertEqual(r["status"],"UNRESOLVED")
    self.assertIsNone(r["actual_t_R_minutes"])
    self.assertFalse(r["normative_claim"])
