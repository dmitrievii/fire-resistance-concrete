import json
import unittest
import numpy as np
from rc_fire.mechanics import sp2026_r10d_front as d
from rc_fire.mechanics import sp2026_r10c_quadrature as q
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR10D(unittest.TestCase):
 def test_time_aligned_front_and_unknown(self):
    self.assertEqual(d.classify([(0,1),(0,1)]),(False,False))
    self.assertEqual(d.classify([(0,1),(1,1)]),(True,False))
    self.assertEqual(d.classify([(0,2),(0,None)]),(False,True))
    self.assertEqual(d.classify([(0,1),(3,None)]),(True,True))
    with self.assertRaises(ValueError):d.classify([(0,),(1,2)])
 def test_fixed_front_refinement_and_conservation(self):
    c=fixture();f=build_annex_k_snapshot(c,0.)
    p=prepare_sp2026_design_section(c,f,grid=8)
    def front(points):
        v=[x<.231 for x,y in points]
        return any(v) and not all(v),False
    a=q.build(p,[f],max_level=2,boundary_band_mm=0.,delta_C=100.,front_indicator=front)
    b=q.build(p,[f],max_level=4,boundary_band_mm=0.,delta_C=100.,front_indicator=front)
    self.assertGreater(a.front_refined_cells,0)
    self.assertLess(b.unresolved_front_gross_area_m2,a.unresolved_front_gross_area_m2)
    self.assertAlmostEqual(sum(x[2] for x in a.points)+p.bar_area.sum(),p.b_m*p.h_m,places=10)
    self.assertAlmostEqual(sum(x[2] for x in b.points),sum(x[2] for x in a.points),places=10)
 def test_actual_probe_replay(self):
    c=fixture();fs=[build_annex_k_snapshot(c,t) for t in (0.,2.)]
    p=prepare_sp2026_design_section(c,fs[0],grid=8)
    seed=h.make_initial(c,fs[0],grid=8,mode=hot.MODIFIED_AT,length_mm=50.,Gwork_N_mm=5.,
                     yield_fraction=.4,strength_basis="SP5_ACCIDENTAL_FCD").concrete[0]
    rows=[{"status":"EQUILIBRATED_RESEARCH_SECTION","time_minutes":t,"q":[0.,0.,0.]} for t in (0.,2.)]
    ind,probe=d.make_front_indicator(seed,fs,rows,width_m=p.b_m,height_m=p.h_m)
    self.assertEqual(probe(p.b_m/2,p.h_m/2),(0,0))
    self.assertEqual(len(probe(0.,0.)),2)
    self.assertEqual(seed.time_s,0.)
    self.assertFalse(ind(((p.b_m/2,p.h_m/2),(p.b_m/2,p.h_m/2)))[0])
 def test_actual_campaign(self):
    r=d.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertIn(r["status"],("DIAGNOSTIC_COMPLETE","BLOCKED_PILOT"))
    self.assertFalse(r["section_history_qualification_closed"])
    self.assertIsNone(r["actual_t_R_minutes"])
    for run in r["runs"]:
        for row in run["rows"]:
            if row["status"]=="EQUILIBRATED_RESEARCH_SECTION":
                self.assertLessEqual(row["max_conjugate_residual_kN"],1e-6)
    # Explicitly report unresolved or failed convergence, no forced PASS.
    print("SP_R10D_EVIDENCE",json.dumps(r,allow_nan=False))
