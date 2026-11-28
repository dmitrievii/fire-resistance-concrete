import json,unittest,math
import numpy as np
from rc_fire.mechanics.sp_prod1_bounded_section import Section,utilization,PASS,FAIL,UNKNOWN
from rc_fire.mechanics.sp_prod1_geometry import circle_rectangle_area
from rc_fire.integration import sp_prod1_engineering as p
from rc_fire.integration.r07_inputs import make_column
from test_r07_public_workflow import user_inputs

CONTRACT={k:True for k in p.CONTRACT}
KW=dict(grid=8,creep_by_axis={"x":.2,"y":.4},action_contract=CONTRACT,bar_distance_convention="clear")
def case(N=3000.):
    c=make_column(user_inputs());c["fire_minutes"]=90.
    c["thermal_spec"].update(dry_density_kg_m3=2400.,a_red_mode="table_K1",moisture_mass_pct=None)
    c["sections"]=[{"id":"bottom","z_m":0.,"N_kN":N,"Mx_kNm":N*.02,"My_kNm":N*.02},
                   {"id":"top","z_m":3.,"N_kN":N*.8,"Mx_kNm":N*.016,"My_kNm":-N*.016}]
    return c
class TestProd1(unittest.TestCase):
 def test_bounded_section_analytic_axial(self):
    C=np.array([[1.,-1.,-1.],[1.,-1.,1.],[1.,1.,-1.],[1.,1.,1.]])
    s=Section(C,[.01]*4,[30.]*4,[0.]*4,C,[.0001]*4,[500.]*4,[200000.]*4,[0.]*4,
              np.vstack([C,-C]),[3.5]*4+[10.]*4,2.,3.5,2.)
    cap=1000*(.04*30+.0004*500)
    q=s.check([cap*.5,0.,0.]);self.assertEqual(q["status"],PASS,q)
    q=s.check([cap*1.1,0.,0.]);self.assertEqual(q["status"],FAIL,q)
    self.assertGreater(q["certificate_margin"],q["numerical_allowance"])
    u=utilization(s,[cap*.8,0.,0.])
    self.assertIsNotNone(u["U_interval"],u)
    self.assertLessEqual(u["U_interval"][0],.8+1e-7)
    self.assertGreaterEqual(u["U_interval"][1],.8-1e-7)
 def test_ambient_biaxial_nominal_and_mathcad_strains(self):
    c=case(1000.)
    q=p.assess(c,0.,**KW)
    self.assertEqual(q["status"],p.WITHIN,q)
    g=q["geometry"];self.assertAlmostEqual(g["Ac"]+8*math.pi*.01**2,.36)
    self.assertEqual(g["strain_parameters_permille"],{"eps_c2":2.,"eps_cu2":3.5,"steel_tension":10.})
    for s in q["sections"]:
        for a,depth in (("x",.6),("y",.6)):
            v=s["nominal"][a]
            self.assertAlmostEqual(v["Ncrit_kN"],math.pi**2*v["B_nom_kNm2"]/v["l0_m"]**2)
            self.assertAlmostEqual(s["M2_kNm"][a],s["M0_kNm"][a]/(1-v["N_over_Ncrit"]))
        self.assertEqual(s["section"]["applied"]["status"],PASS)
    self.assertIsNotNone(q["U"])
    self.assertAlmostEqual(circle_rectangle_area(0,0,1,-1,1,-1,1),math.pi)
 def test_actual_annex_k_and_first_limit(self):
    c=case(5000.)
    # Full temperature field at each whole minute, no isotherm.
    q=p.history(c,end_minute=90,required_minutes=45,calculate_U=False,**KW)
    rows=q["samples"]
    print("SP_PROD1_HISTORY",json.dumps({"summary":{k:v for k,v in q.items() if k!="samples"},
          "rows":[{"t":r["t"],"status":r["status"],"reason":r.get("reason"),
          "sections":[{"id":s["id"],"status":s["status"],"reason":s.get("reason"),"section":s.get("section")} for s in r["sections"]],
          "bar_temperatures_C":r.get("geometry",{}).get("bar_temperatures_C")} for r in rows]},allow_nan=False),flush=True)
    self.assertEqual(rows[0]["status"],p.WITHIN,rows[0])
    self.assertIsNone(q["actual_t_R_minutes"])
    self.assertGreater(len(rows),1)
    if q["model_limit_interval_min"]:
        lo,hi=q["model_limit_interval_min"]
        self.assertEqual(hi-lo,1);self.assertEqual(rows[-1]["status"],p.EXCEEDED)
        for t in (lo,hi):
            r=p.assess(c,t,**KW)
            print("SP_PROD1_ENDPOINT",json.dumps(r,allow_nan=False),flush=True)
            self.assertEqual(r["status"],rows[t]["status"])
 def test_scope_and_unknown_no_rating(self):
    c=case()
    self.assertEqual(p.assess(c,0.,**{**KW,"action_contract":{}})["status"],p.UNRESOLVED)
    c["bars"][0]["x_mm"]+=1
    self.assertEqual(p.assess(c,0.,**KW)["status"],p.UNRESOLVED)
 def test_no_research_imports(self):
    import ast
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    for name in ("rc_fire/integration/sp_prod1_engineering.py","rc_fire/mechanics/sp_prod1_bounded_section.py","rc_fire/mechanics/sp_prod1_geometry.py"):
        for n in ast.walk(ast.parse((root/name).read_text())):
            if isinstance(n,ast.ImportFrom):
                self.assertFalse(any(v in (n.module or "") for v in ("r9","r10","r11","r12","r13","tkp","damage","creep_history")))
