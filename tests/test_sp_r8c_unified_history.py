"""Targeted SP-R8C tests: sampled first model limit and real 90-min histories."""
import json
import unittest
from rc_fire.mechanics.sp2026_unified_history import (
    first_observed_model_event, compare_events, run_fire_duration_campaign,
    evaluate_history, ANNEX_K_METHOD, FVM, WITHIN, EXCEEDED, NOMINAL, UNKNOWN)
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat, select_sp2026_snapshot, reference_sp2026_boundary)
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from test_sp_r3_member import make_column,user_inputs,make_explicit_spec

def rows(*states):
    return [{"time_minutes":float(i)*5,"status":s} for i,s in enumerate(states)]

class TestUnifiedHistory(unittest.TestCase):
    def test_event_classification_fail_closed(self):
        self.assertEqual(first_observed_model_event(rows(WITHIN,EXCEEDED,WITHIN))["interval_min"],[0.,5.])
        self.assertIsNone(first_observed_model_event(rows(WITHIN,UNKNOWN,NOMINAL))["interval_min"])
        self.assertEqual(first_observed_model_event(rows(NOMINAL,WITHIN))["status"],"LIMIT_AT_INITIAL_STATE")
        self.assertEqual(first_observed_model_event(rows(WITHIN,UNKNOWN))["status"],"UNRESOLVED_HISTORY")
        self.assertEqual(first_observed_model_event(rows(WITHIN,WITHIN))["status"],"NO_LIMIT_AT_SAMPLED_TIMES")
    def test_event_refinement_and_disjoint_intervals(self):
        a={"first_event":first_observed_model_event(rows(WITHIN,EXCEEDED))}
        b={"first_event":first_observed_model_event(rows(WITHIN,WITHIN,WITHIN,EXCEEDED))}
        self.assertFalse(compare_events(a,b,20.)["within_tolerance"])
        self.assertTrue(compare_events(a,a,1.)["within_tolerance"])
    def test_real_initial_fvm_snapshot_and_mechanics(self):
        c=make_column(user_inputs())
        c["fire_minutes"]=5.
        heat=solve_sp2026_2d_heat(c,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
             cell_count_x=4,cell_count_y=4,max_step_minutes=2.,sample_times_minutes=[0.,5.])
        p=prepare_sp2026_design_section(c,select_sp2026_snapshot(heat,0.),grid=8)
        self.assertTrue(all(v==20. for v in p.theta_c))
        self.assertTrue(all(v==20. for v in p.theta_s))
    def test_real_fire_duration_campaign(self):
        c=make_column(user_inputs())
        c["fire_minutes"]=90.
        c["thermal_spec"].update(a_red_mode="formula_K1_450C",moisture_mass_pct=1.5)
        spec=make_explicit_spec(c)
        r=run_fire_duration_campaign(c,spec,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
             coarse_times_minutes=[0.,30.,60.,90.],fine_times_minutes=[0.,15.,30.,45.,60.,75.,90.],
             thermal_grids=(8,16),time_steps=(3.,1.5),mechanical_grids=(8,12),
             effective_creep_phi=0.,event_tolerance_minutes=15.)
        self.assertEqual(len(r["histories"]),7)
        for h in r["histories"].values():
            self.assertEqual([x["time_minutes"] for x in h["rows"]],r["fine_times_minutes"])
            self.assertTrue(h["initial_state_sampled"])
            self.assertIsNone(h["actual_t_R_minutes"])
            self.assertTrue(any(x["status"]!=UNKNOWN for x in h["rows"]))
            self.assertIn("temperatures_C",h["rows"][0])
            self.assertFalse(h["normative_claim"])
        self.assertEqual(len(r["comparisons"]),9)
        self.assertIsNone(r["actual_t_R_minutes"])
        self.assertFalse(r["normative_claim"])
        # Compact CI evidence: no fabricated convergence assertion.
        print("SP_R8C_CAMPAIGN",json.dumps({
            "histories":{k:{"first_event":h["first_event"],
               "rows":[{key:row.get(key) for key in ("time_minutes","status",
                         "Ncrit_kN","M2_kNm","reason")} for row in h["rows"]]}
                         for k,h in r["histories"].items()},
            "comparisons":r["comparisons"],
            "numerical_convergence":r["numerical_convergence_at_sampled_times"]},
            ensure_ascii=True,allow_nan=False))
