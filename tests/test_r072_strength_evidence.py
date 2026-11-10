"""R0.7.2 public material loss and load-reserve plots: no invented ULS."""
from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

from rc_fire.integration.r072_strength_evidence import (
    material_strength_retention, sampled_action_reserve,VERSION)
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN
from rc_fire.integration.r07_inputs import make_column


def fake_prepared():
    return SimpleNamespace(
        theta_c=[20.,700.],area=[.18,.18],aggregate='siliceous',
        theta_s=[20.,700.],bar_area=[.000314159,.000314159],
        bar_ids=('S1','S2'),fyk_MPa=500.,Es_MPa=200000.,
        production_route='hot_rolled',ductility_class='B')


def scanned(*states):
    return {'sampled_scale_path':{'samples':[
        {'lambda':lam,'classification':category}
        for lam,category in states]}}


class SourceMaterialStrengthRetention(unittest.TestCase):
    def test_actual_temperature_strength_coefficients_are_area_weighted(self):
        s=material_strength_retention(fake_prepared())
        self.assertEqual(s['version'],VERSION)
        # TKP Table 3.1: 20 C ->1, 700 C ->.30.
        self.assertAlmostEqual(s['concrete_uniaxial_strength_retained_pct'],65.,places=9)
        # TKP Table 3.2a class N hot rolled: 20 C ->1, 700 C ->.23.
        self.assertAlmostEqual(s['steel_yield_strength_retained_pct'],61.5,places=9)
        self.assertAlmostEqual(s['steel_bar_yield_strength_retained_pct']['S1'],100.)
        self.assertAlmostEqual(s['steel_bar_yield_strength_retained_pct']['S2'],23.)
        self.assertFalse(s['is_member_capacity'])
        self.assertFalse(s['is_normative_resistance_check'])

    def test_material_strength_is_not_strain_ratio_or_N_Mx_capacity(self):
        p=fake_prepared()
        p.theta_c=[20.,20.]
        p.theta_s=[20.,20.]
        s=material_strength_retention(p)
        self.assertAlmostEqual(s['concrete_uniaxial_strength_retained_pct'],100.)
        self.assertAlmostEqual(s['steel_yield_strength_retained_pct'],100.)
        self.assertNotIn('R_t_minutes',s)
        self.assertNotIn('member_utilization',s)

    def test_different_bar_process_changes_fy_retention(self):
        p=fake_prepared()
        hot=material_strength_retention(p)
        p.production_route='cold_worked'
        cold=material_strength_retention(p)
        self.assertGreater(hot['steel_yield_strength_retained_pct'],
                           cold['steel_yield_strength_retained_pct'])

    def test_zero_area_rejected(self):
        p=fake_prepared()
        p.bar_area=[0.,0.]
        with self.assertRaises(ValueError):
            material_strength_retention(p)


class SampledSectionReserveTests(unittest.TestCase):
    def test_known_five_loading_states_display_only_discrete_checked_factor(self):
        a=scanned((0.,WITHIN),(.5,WITHIN),(1.,WITHIN),
                  (1.5,WITHIN),(2.,WITHIN))
        r=sampled_action_reserve([a])
        self.assertEqual(r['max_consecutively_checked_load_factor'],2.)
        self.assertEqual(r['discrete_extra_load_tested_pct'],100.)
        self.assertEqual(r['ratio_to_max_checked_load_pct'],50.)
        self.assertFalse(r['true_capacity_or_utilization_known'])
        self.assertFalse(r['is_normative_capacity'])

    def test_stop_at_first_unknown_even_if_later_root_is_found(self):
        a=scanned((1.,WITHIN),(1.5,UNKNOWN),(2.,WITHIN))
        r=sampled_action_reserve([a])
        self.assertEqual(r['max_consecutively_checked_load_factor'],1.)
        self.assertIsNone(r['discrete_extra_load_tested_pct'])
        self.assertIsNone(r['ratio_to_max_checked_load_pct'])

    def test_member_capacity_not_inferred_from_strain_limit_exceeded(self):
        a=scanned((1.,WITHIN),(1.5,EXCEEDED),(2.,WITHIN))
        r=sampled_action_reserve([a])
        self.assertEqual(r['max_consecutively_checked_load_factor'],1.)
        self.assertIsNone(r['ratio_to_max_checked_load_pct'])
        self.assertFalse(r['is_normative_capacity'])

    def test_unknown_at_actual_design_point_has_no_numerical_capacity(self):
        for status in (UNKNOWN,EXCEEDED):
            r=sampled_action_reserve([scanned((1.,status),(2.,WITHIN))])
            self.assertEqual(r['status'],'UNRESOLVED')
            self.assertIsNone(r['max_consecutively_checked_load_factor'])
            self.assertIsNone(r['discrete_extra_load_tested_pct'])

    def test_common_checked_multiplier_is_minimum_across_sections(self):
        one=scanned((1.,WITHIN),(1.5,WITHIN),(2.,WITHIN))
        two=scanned((1.,WITHIN),(1.5,WITHIN),(2.,UNKNOWN))
        r=sampled_action_reserve([one,two])
        self.assertEqual(r['max_consecutively_checked_load_factor'],1.5)
        self.assertEqual(r['discrete_extra_load_tested_pct'],50.)
        self.assertAlmostEqual(r['ratio_to_max_checked_load_pct'],100./1.5)

    def test_no_input_never_defaults_to_100_percent_usage(self):
        r=sampled_action_reserve([])
        self.assertIsNone(r['ratio_to_max_checked_load_pct'])
        self.assertIsNone(r['discrete_extra_load_tested_pct'])


if __name__=='__main__':
    unittest.main()
