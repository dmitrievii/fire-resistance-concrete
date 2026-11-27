"""SP-R8D targeted numerical tests; no fabricated convergence result."""
import json
import unittest
import numpy as np
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat,select_sp2026_snapshot,sample_sp2026_temperature,
    reference_sp2026_boundary)
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.mechanics.sp2026_spatial_qualification import (
    prepare_fixed_probes,evaluate_fixed_probes,run_spatial_recovery)
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from test_sp_r3_member import make_column,user_inputs,make_explicit_spec

def column():
    c=make_column(user_inputs())
    c["fire_minutes"]=10.
    c["thermal_spec"].update(a_red_mode="formula_K1_450C",moisture_mass_pct=1.5)
    return c

class TestSPR8D(unittest.TestCase):
    def test_constant_ambient_field_exact_for_arbitrary_coordinates(self):
        c=column()
        h=solve_sp2026_2d_heat(c,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
             cell_count_x=4,cell_count_y=4,max_step_minutes=2.,sample_times_minutes=[0.,10.])
        f=select_sp2026_snapshot(h,0.)
        for x in np.linspace(0,600,29):
            for y in np.linspace(0,600,31):
                self.assertEqual(sample_sp2026_temperature(f,x,y),20.)
        self.assertLess(h["energy_balance"]["relative_cumulative_residual"],3e-4)
    def test_fixed_probe_replay_identical_across_quadrature(self):
        c=column()
        f=build_annex_k_snapshot(c,5.)
        p0=prepare_sp2026_design_section(c,f,grid=8)
        p1=prepare_sp2026_design_section(c,f,grid=12)
        probes=prepare_fixed_probes(c,f,p0,divisions=10)
        a=evaluate_fixed_probes(p0,[-.001,.0001,.0002],probes)
        b=evaluate_fixed_probes(p1,[-.001,.0001,.0002],probes)
        self.assertEqual(a["critical_ratio"],b["critical_ratio"])
        self.assertFalse(a["continuum_qualified"])
    def test_real_targeted_spatial_recovery(self):
        c=column()
        r=run_spatial_recovery(c,make_explicit_spec(c),
            boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
            times_minutes=(5.,10.),thermal_grids=(16,32,64),step_minutes=1.,
            mechanical_grids=(8,16,24),probe_divisions=(20,40),effective_creep_phi=0.)
        self.assertEqual(len(r["runs"]),3)
        self.assertEqual(len(r["thermal_comparisons"]),4)
        self.assertEqual(len(r["classification_diagnostics"]),4)
        self.assertTrue(all(x["energy_balance"]["relative_cumulative_residual"]<=3e-4
                            for x in r["runs"]))
        self.assertIsNone(r["actual_t_R_minutes"])
        self.assertFalse(r["normative_claim"])
        print("SP_R8D_EVIDENCE",json.dumps({
            "thermal_comparisons":r["thermal_comparisons"],
            "classification_diagnostics":r["classification_diagnostics"],
            "fine_thermal_comparisons_within_tolerances":r["fine_thermal_comparisons_within_tolerances"]},
            ensure_ascii=True,allow_nan=False))
