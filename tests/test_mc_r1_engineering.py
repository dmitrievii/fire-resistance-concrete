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
        # Independent requested-duration section checks, not a continuous
        # fire history. Export every computed state BEFORE assertions.
        rows=[m.assess(c,select_sp2026_snapshot(f,t),**KW) for t in (0,5,10)]
        compact={"geometry":[c["b_mm"],c["h_mm"]],"bar_diameter_mm":c["bars"][0]["diameter_mm"],
          "samples":[{"t":s["time_minutes"],"status":s["status"],"bars":s["bar_temperatures_C"],
            "governing":s["governing_sampled_strain_section"],"sections":[{"id":x["id"],"N":x["N_kN"],
            "status":x["status"],"M2":x["M2_kNm"],"ratio":(x["section"] or {}).get("critical_ratio"),
            "residual":(x["section"] or {}).get("relative_residual"),
            "reason":(x["section"] or {}).get("reason"),
            "scope":{k:(x["section"] or {}).get("scope",{}).get(k) for k in ("maximum_concrete_fibre_ratio","maximum_concrete_boundary_ratio","steel_check_tension_ratio")},
            "Ncr":[x["nominal"][a].get("Ncrit_kN") for a in ("x","y")],
            "eta":[x["nominal"][a].get("eta_a") for a in ("x","y")]} for x in s["sections"]]} for s in rows]}
        print("MC_R1_VARIABLE_EVIDENCE",json.dumps(compact,allow_nan=False),flush=True)
        self.assertEqual(rows[0]["status"],"ALL_SAMPLED_SECTIONS_WITHIN_MODEL_LIMITS")
        for s in rows:
            self.assertEqual(s["section_count"],2);self.assertEqual(len(s["bar_temperatures_C"]),8)
            self.assertEqual([x["id"] for x in s["sections"]],["bottom","top"])
            for x in s["sections"]:
                self.assertEqual(x["nominal"]["x"]["phi_eff_input"],.2)
                self.assertEqual(x["nominal"]["y"]["phi_eff_input"],.4)
                self.assertEqual(x["nominal"]["x"]["mu_input"],.8)
                self.assertEqual(x["nominal"]["y"]["mu_input"],1.2)
                if x["M2_kNm"] is not None:
                    self.assertLess(x["M2_kNm"]["y"],0.)
                    for a in ("x","y"):
                        self.assertAlmostEqual(x["M2_kNm"][a],x["M0_kNm"][a]*x["nominal"][a]["eta_a"])
                if x["status"] in ("SECTION_MODEL_WITHIN","SECTION_MODEL_LIMIT_EXCEEDED"):
                    self.assertLess(x["section"]["relative_residual"],1e-6)
                    self.assertEqual(x["status"]=="SECTION_MODEL_WITHIN",x["section"]["critical_ratio"]<=1.+1e-12)
                else:self.assertTrue(x["status"].startswith("UNRESOLVED"))
            self.assertIsNone(s["actual_t_R_minutes"])
        self.assertNotEqual(rows[0]["bar_temperatures_C"],rows[-1]["bar_temperatures_C"])
        history=m.history(c,f,[0,5,10],**KW)["samples"]
        expected=[]
        for row in rows:
            expected.append(row["status"])
            if row["status"]!="ALL_SAMPLED_SECTIONS_WITHIN_MODEL_LIMITS":break
        self.assertEqual([s["status"] for s in history],expected)
        runs.append(rows)
    self.assertNotEqual(runs[0][-1]["bar_temperatures_C"],runs[1][-1]["bar_temperatures_C"])
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
