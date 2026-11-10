"""R0.7.5 — physical stress-envelope capacity and utilization lower bound.

This is a mathematical verification of the source-temperature, real N-M
interaction LP: unlike the previous flat 50% curve, this depends on
load magnitude, bending moment and temperature independently of Newton
failure. It is a rigorous LOWER bound on first-order fibre-section U,
not a certified member-capacity calculation or R(t).
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from rc_fire.integration.r075_bounded_utilisation import (
    section_interaction_upper_bound)
from test_r07_public_workflow import user_inputs
from rc_fire.integration.r07_inputs import make_column
from rc_fire.integration.r07_public import fire_assessment


def square_fibres(temperature=20.):
    concrete_x=[.15,.45,.15,.45]
    concrete_y=[.15,.15,.45,.45]
    bar_x=[.04,.56,.04,.56]
    bar_y=[.04,.04,.56,.56]
    return SimpleNamespace(
        x=np.array(concrete_x),y=np.array(concrete_y),
        area=np.full(4,.09),
        bar_x=np.array(bar_x),bar_y=np.array(bar_y),
        bar_area=np.full(4,.000314159),
        theta_c=np.full(4,temperature),
        theta_s=np.full(4,temperature),
        theta_cb=np.full(4,temperature),
        b_m=.6,h_m=.6,fck_MPa=30.,fyk_MPa=500.,Es_MPa=200000.,
        aggregate='siliceous',production_route='hot_rolled',
        ductility_class='B')


class RigorousLoadBound(unittest.TestCase):
    def test_ambient_pure_axial_limit_is_gross_material_stress_upper(self):
        p=square_fibres(20.)
        axial_cap=4*.09*1000*30+4*.000314159*1000*500.
        r=section_interaction_upper_bound(p,50.,0.,0.)
        self.assertEqual(r['status'],'STRESS_ENVELOPE_UPPER_BOUND_SOLVED')
        self.assertAlmostEqual(
            r['max_possible_load_factor_upper_bound'],axial_cap/50.,places=5)
        self.assertAlmostEqual(
            r['section_utilization_lower_bound_pct'],100*50/axial_cap,
            places=5)
        self.assertFalse(r['definite_section_overload_in_source_model'])
        self.assertFalse(r['actual_section_utilization_known'])

    def test_unrealistic_500000_kN_is_provably_overloaded_without_newton(self):
        p=square_fibres(20.)
        r=section_interaction_upper_bound(p,500000.,20.,4.)
        self.assertTrue(r['definite_section_overload_in_source_model'])
        self.assertLess(r['max_possible_load_factor_upper_bound'],1.)
        self.assertGreater(r['section_utilization_lower_bound_pct'],1000.)
        self.assertFalse(r['actual_member_utilization_known'])
        self.assertIsNone(r['normative_member_R_t_minutes'])

    def test_sensitivity_to_actual_load_is_linear_and_not_flat_50pct(self):
        p=square_fibres(300.)
        small=section_interaction_upper_bound(p,100.,20.,4.)
        double=section_interaction_upper_bound(p,200.,40.,8.)
        self.assertAlmostEqual(
            double['max_possible_load_factor_upper_bound'],
            small['max_possible_load_factor_upper_bound']/2.,places=7)
        self.assertAlmostEqual(
            double['section_utilization_lower_bound_pct'],
            small['section_utilization_lower_bound_pct']*2.,places=7)
        self.assertNotAlmostEqual(small['section_utilization_lower_bound_pct'],50.)

    def test_heating_decreases_available_stress_envelope_capacity(self):
        ambient=section_interaction_upper_bound(square_fibres(20.),100.,20.,4.)
        heated=section_interaction_upper_bound(square_fibres(700.),100.,20.,4.)
        self.assertGreater(
            heated['section_utilization_lower_bound_pct'],
            ambient['section_utilization_lower_bound_pct'])

    def test_biaxial_bending_reduces_stress_envelope_limit(self):
        p=square_fibres()
        cent=section_interaction_upper_bound(p,100.,0.,0.)
        biax=section_interaction_upper_bound(p,100.,100.,100.)
        self.assertLess(
            biax['max_possible_load_factor_upper_bound'],
            cent['max_possible_load_factor_upper_bound'])
        self.assertTrue(biax['includes_biaxial_interaction'])

    def test_invalid_load_never_yields_safe_percent(self):
        for load in (0.,-100.,float("nan"),float("inf")):
            with self.assertRaises(ValueError):
                section_interaction_upper_bound(square_fibres(),load,0.,0.)


class PublicCaseShowsRealLoadSensitivity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column=make_column(user_inputs())
        cls.r=fire_assessment(cls.column,required_minutes=30.,
             steel_route='hot_rolled',ductility_class='B',
             moisture_mass_pct=1.5,grid=8,dt_minutes=3.)

    def test_every_solved_mechanical_time_has_physical_load_bound(self):
        self.assertEqual(self.r['regulatory_result'],'NOT_ESTABLISHED')
        self.assertIsNone(self.r['R_t_minutes'])
        for row in self.r['timeline']:
            lower=row['section_minimum_possible_utilisation_pct']
            self.assertIsNotNone(lower,row)
            self.assertGreater(lower,0.)
            self.assertLess(lower,100.)
            self.assertFalse(row['section_stress_envelope_overload'])
        self.assertGreater(self.r['section_interaction_utilisation_bound_at_required_time'][
            'section_utilization_lower_bound_pct'],0.)

    def test_extreme_load_is_reported_as_proven_overload_not_newton_failure(self):
        c=make_column(user_inputs())
        c['sections'][0]['N_kN']=500000.
        # No heat recomputation: temperature does not depend on applied N.
        # Test the already resolved 30 min source field in a standalone
        # stress-envelope bound with the actual extreme load.
        from rc_fire.thermal.tkp_heat import (
            solve_tkp_2d_heat,select_tkp_snapshot,reference_annex_a_boundary)
        from rc_fire.mechanics.tkp_thermomechanical_fibres import prepare_tkp_fibres
        c['fire_minutes']=30.
        heat=solve_tkp_2d_heat(c,
            boundary=reference_annex_a_boundary(moisture_mass_pct=1.5),
            cell_count_x=8,cell_count_y=8,max_step_minutes=3.,
            sample_times_minutes=[30.])
        prep=prepare_tkp_fibres(c,select_tkp_snapshot(heat,30.),grid=8,
            production_route='hot_rolled',ductility_class='B')
        res=section_interaction_upper_bound(prep,500000.,20.,4.)
        self.assertTrue(res['definite_section_overload_in_source_model'])
        self.assertGreater(res['section_utilization_lower_bound_pct'],1000.)


if __name__=='__main__':
    unittest.main()
