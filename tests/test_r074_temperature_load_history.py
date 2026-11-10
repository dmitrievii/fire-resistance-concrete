"""R0.7.4 thermal vs mechanical output and actual load sensitivity.

Important physical contract: temperatures at a prescribed ISO heating
boundary are INDEPENDENT of applied structural design actions.  Actual
N/Mx/My control the fibre equilibrium and its mechanical strain demand,
but that is not yet a validated first-loss-of-member-capacity R(t).
"""
from __future__ import annotations

import math
import unittest
import numpy as np

from test_r07_public_workflow import user_inputs
from rc_fire.integration.r07_inputs import make_column
from rc_fire.integration.r07_public import fire_assessment
from rc_fire.integration.r073_plot_contract import (
    prepare_temperature_chart,split_temperature_chart)
from rc_fire.thermal.tkp_heat import (
    solve_tkp_2d_heat,select_tkp_snapshot,reference_annex_a_boundary)
from rc_fire.mechanics.tkp_thermomechanical_fibres import prepare_tkp_fibres
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN


class ThermalMechanicalSeparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column=make_column(user_inputs())
        cls.result=fire_assessment(cls.column,required_minutes=30.,
            steel_route='hot_rolled',ductility_class='B',
            moisture_mass_pct=1.5,grid=8,dt_minutes=3.)

    def test_temperature_curve_has_actual_thermal_samples_including_time_zero(self):
        r=self.result
        thermal=r['thermal_timeline']
        mechanical=r['timeline']
        self.assertTrue(r['thermal_timeline_independent_of_mechanics'])
        self.assertGreater(len(thermal),len(mechanical))
        self.assertEqual(thermal[0]['minute'],0.)
        self.assertEqual(thermal[0]['gas_C'],20.)
        self.assertEqual(thermal[0]['concrete_surface_C'],20.)
        self.assertEqual(thermal[0]['concrete_centre_C'],20.)
        self.assertTrue(all(v==20. for v in thermal[0]['bars_C'].values()))
        self.assertIn(30.,[r['minute'] for r in thermal])
        self.assertEqual(mechanical[0]['minute'],1.)
        self.assertEqual(mechanical[-1]['minute'],60.)
        self.assertTrue(all(s['temperature_source'] for s in thermal))

    def test_exact_same_temperature_for_independent_thermal_and_mechanical_at_shared_times(self):
        r=self.result
        by_t={row['minute']:row for row in r['thermal_timeline']}
        for m in r['timeline']:
            self.assertIn(m['minute'],by_t)
            t=by_t[m['minute']]
            for key in ('gas_C','concrete_surface_C','concrete_centre_C'):
                self.assertAlmostEqual(t[key],m[key],places=10)
            self.assertEqual(set(m['bars_C']),set(t['bars_C']))
            for k in m['bars_C']:
                self.assertAlmostEqual(m['bars_C'][k],t['bars_C'][k],places=10)
        at=by_t[30.]
        self.assertAlmostEqual(at['concrete_surface_C'],r[
            'required_time_temperatures']['concrete_surface_max_C'],places=10)

    def test_concrete_and_all_bars_have_thermally_consistent_temperature_ranges(self):
        r=self.result
        for row in r['thermal_timeline']:
            self.assertGreaterEqual(row['gas_C'],20.)
            self.assertGreaterEqual(row['concrete_surface_C'],20.-1e-6)
            self.assertLessEqual(row['concrete_surface_C'],row['gas_C']+1e-5)
            self.assertLessEqual(row['concrete_centre_C'],row['gas_C']+1e-5)
            self.assertEqual(len(row['bars_C']),8)
            for val in row['bars_C'].values():
                self.assertTrue(math.isfinite(val))
                self.assertGreaterEqual(val,20.-1e-6)
                self.assertLessEqual(val,row['gas_C']+1e-5)

    def test_temperature_chart_uses_thermal_samples_and_groups_symmetric_rods(self):
        report=self.result
        ids=[x['id'] for x in self.column['bars']]
        chart,missing,source=prepare_temperature_chart(report,ids)
        self.assertFalse(missing)
        self.assertEqual(source,0)
        self.assertEqual(list(chart.index)[0],0.)
        self.assertEqual(len(chart),len(report['thermal_timeline']))
        self.assertGreater(len(chart),len(report['timeline']))
        concrete,steel=split_temperature_chart(chart)
        self.assertEqual(len(concrete.columns),3)
        # Four-sided symmetric heating has only two unique bar curves:
        # corner bars and side-midpoint bars.
        self.assertEqual(len(steel.columns),2)
        seen=set()
        for group in steel.columns:
            seen.update(group.replace('Стержни ','').replace(
                'Стержень ','').replace(' ','').split(','))
        self.assertEqual(seen,set(ids))
        self.assertTrue(all(steel.iloc[0].values==20.))

    def test_public_loaded_demand_is_distinct_from_load_independent_material_loss(self):
        r=self.result
        self.assertIn('design_action_strain_demand_pct_at_required_time',r)
        self.assertIn('design_action_strain_demand_pct',r['timeline'][0])
        self.assertEqual(r['regulatory_result'],'NOT_ESTABLISHED')
        self.assertIsNone(r['R_t_minutes'])
        self.assertIn('not verified',r['capacity_scope'])

    def test_compatibility_falls_back_to_old_mechanics_timeline(self):
        legacy={'timeline':self.result['timeline']}
        ids=[x['id'] for x in self.column['bars']]
        chart,missing,_=prepare_temperature_chart(legacy,ids)
        self.assertFalse(missing)
        self.assertEqual(len(chart),len(self.result['timeline']))


class ActualAppliedLoadMechanicalResponse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=make_column(user_inputs())
        cls.c['fire_minutes']=30.
        cls.heat=solve_tkp_2d_heat(cls.c,
             boundary=reference_annex_a_boundary(moisture_mass_pct=1.5),
             cell_count_x=8,cell_count_y=8,max_step_minutes=3.,
             sample_times_minutes=[30.])
        cls.p=prepare_tkp_fibres(cls.c,select_tkp_snapshot(cls.heat,30.),
             grid=8,production_route='hot_rolled',ductility_class='B')

    def test_N_and_M_affect_fibre_equilibrium_but_not_heat_field(self):
        p=self.p
        initial_temperature=p.theta_s.copy()
        low=p.solve_actions(50.,2.,0.)
        high=p.solve_actions(500.,20.,0.)
        self.assertEqual(low['target_N_Mx_My'],[50.,2.,0.])
        self.assertEqual(high['target_N_Mx_My'],[500.,20.,0.])
        self.assertTrue(np.array_equal(p.theta_s,initial_temperature))
        # When both solutions converge, different actual N/M MUST generate
        # different section strain states (and hence potentially capacity).
        if ('unknowns' in low and 'unknowns' in high):
            self.assertFalse(np.allclose(
                low['unknowns'],high['unknowns'],atol=1e-8,rtol=1e-6))
        else:
            # A failed nonlinear solver is an UNKNOWN, never R(t) or failure.
            self.assertIn(low['classification'],(WITHIN,EXCEEDED,UNKNOWN))
            self.assertIn(high['classification'],(WITHIN,EXCEEDED,UNKNOWN))

    def test_public_load_strain_demand_is_from_design_point_not_material_reduction(self):
        for x in self.p.load_factor_scan(50.,2.,0.,max_factor=2.,
                     factor_step=.5,max_bisection=0)['samples']:
            if x['lambda']==1.:
                self.assertIn('critical_ratio',x)
                if x['classification'] in (WITHIN,EXCEEDED):
                    self.assertIsNotNone(x['critical_ratio'])



if __name__=="__main__":
    unittest.main()
