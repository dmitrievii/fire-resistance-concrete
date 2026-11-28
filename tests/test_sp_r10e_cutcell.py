import json
import unittest
import numpy as np
from rc_fire.mechanics import sp2026_r10e_cutcell as c
from rc_fire.mechanics import sp2026_r10e_campaign as campaign
from rc_fire.mechanics import sp2026_r10c_quadrature as q
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from test_sp_r10a_history_section import fixture

class TestR10E(unittest.TestCase):
 def test_exact_affine_cut_and_moments(self):
    for v,inside,expected in (([-.385,.615,.615,-.385],lambda x,y:x<.385,.385),
                               ([-1.,0.,1.,0.],lambda x,y:x+y<1.,.5)):
        p,n=c.partition_rectangle([v]);self.assertEqual(n,0)
        self.assertAlmostEqual(sum(a for x,y,a in p if inside(x,y)),expected,places=12)
        self.assertAlmostEqual(sum(a*x for x,y,a in p),.5,places=12)
        self.assertAlmostEqual(sum(a*y for x,y,a in p),.5,places=12)
    p,n=c.partition_rectangle([[-.2,.8,.8,-.2],[-.7,-.7,.3,.3]])
    self.assertAlmostEqual(sum(a for x,y,a in p if x<.2 and y<.7),.14,places=12)
 def test_net_geometry_and_unknown(self):
    col=fixture();f=build_annex_k_snapshot(col,0.)
    p=prepare_sp2026_design_section(col,f,grid=8)
    m=q.build(p,[f],max_level=0)
    def probe(x,y):return ((x-.231,780.,False),)
    k=c.build(m,probe,selected_times=(0.,))
    self.assertGreater(k.cut_cells,0);self.assertGreater(k.bar_fallback_cells,0)
    self.assertAlmostEqual(sum(a for x,y,a in k.points),sum(a for x,y,a in m.points),places=10)
    z=c.build(m,lambda x,y:None,selected_times=(0.,))
    self.assertGreater(z.unknown_cells,0)
    self.assertEqual(z.cut_cells,0)
 def test_admission_fail_closed(self):
    kw=dict(thermal_spatial=True,thermal_temporal=True,mechanical_spatial=True,
        mechanical_temporal=True,full_duration=True,front_evidence=True)
    r=campaign.admission(**kw)
    self.assertTrue(r["numerical_section_admitted"]);self.assertFalse(r["member_solver_admitted"])
    kw["thermal_spatial"]=False
    self.assertFalse(campaign.admission(**kw)["numerical_section_admitted"])
 def test_actual_campaign(self):
    r=campaign.campaign(fixture(),reference_sp2026_boundary(moisture_mass_pct=1.5))
    self.assertFalse(r["admission"]["member_solver_admitted"])
    self.assertIsNone(r["actual_t_R_minutes"])
    for run in r["runs"]:
        for row in run["rows"]:
            if row["status"]=="EQUILIBRATED_RESEARCH_SECTION":
                self.assertLessEqual(row["max_conjugate_residual_kN"],1e-6)
    print("SP_R10E_EVIDENCE",json.dumps(r,allow_nan=False))
