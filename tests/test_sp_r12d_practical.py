import json
import unittest
from dataclasses import dataclass
from pathlib import Path
from rc_fire.member import sp2026_r12d_practical as p
from rc_fire.member import sp2026_r12a_resistance as r
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.member import sp2026_r11b_extended_member as b
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot,reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

@dataclass(frozen=True)
class State:
    thermal_minutes:float

class TestR12D(unittest.TestCase):
 def test_schedule(self):
    self.assertEqual(p.schedule(89,near_start=83),list(range(0,83,5))+list(range(83,90)))
    with self.assertRaises(ValueError):p.schedule(83.875)
 def test_practical_rollback_no_seconds(self):
    def advance(s,t):
        if t>=84 or t-s.thermal_minutes>5:return s,{"status":"UNRESOLVED_GLOBAL_LINE_SEARCH"}
        return State(t),{"status":p.c.OK}
    last,q=p.run(State(0),advance,end=90)
    self.assertEqual(last.thermal_minutes,83.)
    self.assertEqual(q["computational_stop_interval_min"],[83,84])
    self.assertTrue(all(int(a["to_minute"])==a["to_minute"] for a in q["attempts"]))
    self.assertIsNone(q["actual_t_R_minutes"])
    self.assertEqual([x["time_minutes"] for x in q["accepted"]][-4:],[80,81,82,83])
 def test_existing_receipts_no_recalculation(self):
    for name in ("sp_r12a_r11d_receipt.json","sp_r12a_r11e_receipt.json"):
        f=Path("validation")/name
        if not f.exists() and "r11d" in name:
            f=next(Path("validation").glob("sp_r12a*r11d*.json"),f)
        if not f.exists() and "r11d" in name:continue
        v=p.review_archived(r.extract(json.loads(f.read_text())))
        self.assertTrue(v["engineering_time_resolution_met"])
        self.assertEqual(v["last_accepted_whole_minute_diagnostic"],83)
        self.assertFalse(v["further_time_localization_needed"])
        self.assertIsNone(v["actual_t_R_minutes"])
        print("SP_R12D_ARCHIVED_EVIDENCE",json.dumps(v))
 def test_actual_strength_basis_at_ambient(self):
    c=fixture();cc,spec=b.fixture_spec(c,length=3.,N=50.,nodes=3,support="pinned")
    heat=solve_sp2026_2d_heat(cc,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
        cell_count_x=8,cell_count_y=8,max_step_minutes=1.,sample_times_minutes=[0.,1.])
    f=select_sp2026_snapshot(heat,0.)
    rows=[]
    for basis,expected in (("SP5_ACCIDENTAL_FCD",25.),("SP_CHARACTERISTIC_FCK",30.)):
        a=m.initial(cc,spec,f,grid=8,strength_basis=basis)
        self.assertTrue(all(abs(v.active.parameters.fc20_MPa-expected)<1e-10 for g in a.sections for v in g.concrete))
        x,rep=m.advance(a,cc,spec,f)
        self.assertEqual(rep["status"],p.c.OK)
        rows.append({"basis":basis,"fc20_MPa":expected,"fc_at_600_MPa":expected*.60,
            "axial_residual_kN":rep["max_axial_residual_kN"],"midspan_x_mm":1000*rep["total_w_x_m"][1]})
    print("SP_R12D_STRENGTH_EVIDENCE",json.dumps(rows))
