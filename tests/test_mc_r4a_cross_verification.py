import json
import unittest
from rc_fire.integration import mc_r4a_cross_verification as m
from rc_fire.integration import mc_r1_engineering as full
from rc_fire.thermal.normative import RectangularExposure,ThermalProfile,resolve_profile
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from test_mc_r3_reconciliation import inputs
from test_mc_r2_reduced import KW

KW4={k:KW[k] for k in ("action_contract","creep_by_axis")}

def compact(row):
    out={"t":row["time_minutes"]}
    for method,rec in row["results"].items():
        e=rec["evidence"];s=(e.get("sections") or [{}])[0]
        n=s.get("nominal",{})
        out[method]={"state":rec["state"],"reason":e.get("reason"),
            "Ncr_y":n.get("y",{}).get("Ncrit_kN"),
            "Ncr_x":n.get("x",{}).get("Ncrit_kN"),
            "moment_ratio":s.get("moment_ratio"),
            "strain_index":(s.get("section") or {}).get("critical_ratio"),
            "section_status":s.get("status")}
    return out

class TestMC4A(unittest.TestCase):
    def test_independent_integral_and_literal_area(self):
        ex=RectangularExposure(600.,600.,("left","right","bottom","top"))
        co=resolve_profile(ThermalProfile("siliceous",2400.))
        times=(0,7,8,14,15,30,60,90)
        aa=[m.integrated_isotherm_area(ex,co,t,500.) for t in times]
        ka=[m.k27_area_only(ex,co,t,500.) for t in times]
        for x,y in zip(aa,(.36,.36,.35998702079148626,.35914343928753073,
                         .3583508353531594,.3345882640094964,.3016183700449716,.2768244844700493)):
            self.assertAlmostEqual(x,y,places=9)
        self.assertIsNone(ka[2]["area_m2"]);self.assertIsNone(ka[3]["area_m2"])
        self.assertAlmostEqual(ka[4]["area_m2"],.27559446915879615,places=9)
        self.assertEqual(ka[4]["legacy_helper_status"],"out_of_scope")
        self.assertAlmostEqual(ka[-1]["area_m2"],.20063101731132252,places=9)

    def test_explicit_full_temperature_source(self):
        c=m.matched_column(inputs(),527.16,6.5)
        f=build_annex_k_snapshot(c,0.)
        with self.assertRaises(ValueError):
            full.assess(c,f,basis=full.CHARACTERISTIC,**KW4)
        q=m.compare_at_time(c,0,**KW4)
        r=q["results"]["full_temperature"]["evidence"]
        self.assertEqual(r.get("thermal_method"),"SP2026_ANNEX_K_ANALYTICAL",r)
        self.assertEqual(q["results"]["full_temperature"]["state"],"WITHIN",r)
        self.assertIsNone(q["actual_t_R_minutes"])

    def test_governing_load_common_field(self):
        rows=[]
        for N,Mx in ((100.,5.),(527.16,6.5),(1134.,16.),(1134.,38.9),(2000.,100.)):
            c=m.matched_column(inputs(),N,Mx)
            for t in (0,30,60,90):
                q=m.compare_at_time(c,t,**KW4)
                self.assertFalse(q["normative_claim"])
                self.assertEqual(set(q["results"]),set(m.METHODS))
                rf=q["results"]["full_temperature"]["evidence"]
                rc=q["results"]["contour"]["evidence"]
                if "bar_temperatures_C" in rf and "bars" in rc:
                    for bar in rc["bars"]:
                        self.assertAlmostEqual(rf["bar_temperatures_C"][bar["id"]],bar["T_C"],places=9)
                self.assertIsNone(q["actual_t_R_minutes"])
                rows.append({"N":N,"M":Mx,**compact(q)})
        self.assertEqual(len(rows),20)
        print("MC_R4A_MATCHED",json.dumps(rows,allow_nan=False))

    def test_complete_whole_minute_histories(self):
        for N,M in ((527.16,6.5),(1134.,16.)):
            c=m.matched_column(inputs(),N,M)
            h=m.history(c,end_minute=90,grid=12,**KW4)
            self.assertEqual([r["time_minutes"] for r in h["samples"]],list(range(91)))
            self.assertEqual(h["first_nonwithin"]["k27_cross"]["minute"],8)
            self.assertTrue(h["unknowns_not_interpolated"])
            self.assertIsNone(h["actual_t_R_minutes"])
            print("MC_R4A_HISTORY",json.dumps({"N":N,"M":M,"transitions":h["transitions"],
                  "first_nonwithin":h["first_nonwithin"],"rows":[compact(r) for r in h["samples"]]},allow_nan=False))

    def test_biaxial_not_silently_split(self):
        c=m.matched_column(inputs(),1134.,16.,-38.9)
        q=m.compare_at_time(c,0,**KW4)
        self.assertEqual(q["results"]["contour"]["state"],"UNKNOWN")
        self.assertEqual(q["results"]["k27_cross"]["state"],"UNKNOWN")
        f=q["results"]["full_temperature"]["evidence"]
        self.assertEqual(f.get("thermal_method"),"SP2026_ANNEX_K_ANALYTICAL",f)
        self.assertEqual(f["sections"][0]["M0_kNm"],{"x":16.,"y":-38.9})
        self.assertIsNone(q["actual_t_R_minutes"])
        print("MC_R4A_BIAXIAL",json.dumps(compact(q),allow_nan=False))
