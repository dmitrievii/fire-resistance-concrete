"""R0.6.9A time-history correctness and fail-closed regressions."""
import copy
import unittest
from unittest.mock import patch

from rc_fire.member.time_scan import (
    timeline_points, scan_member_time_history, classify_evidence, WITHIN, EXCEEDED, UNKNOWN)
from rc_fire.integration.r069 import evaluate_uniform_fire_time_history
from multicolumn_r05.project_model import (
    new_project, update_column, update_section, update_member_spec)


def evidence(kind):
    if kind == 'blocked':
        return {'status': 'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT',
                'reason': 'table values above 800 C unavailable'}
    if kind == 'nonconvergence':
        return {'status': 'MODEL_NOT_SOLVED', 'uls': {'status': 'MODEL_NOT_SOLVED'}}
    label, exceeded, ratio = {
        'within': ('SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS', 0, 0.7),
        'exceeded': ('DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED', 1, 1.1),
    }[kind]
    return {'status': label, 'uls': {
        'status': label, 'node_coverage': True, 'all_sampled_limits_resolved': True,
        'exceeded_count': exceeded, 'critical_sample': {'maximum_ratio': ratio}},
        'material_audit': {'blockers': ['FIRE_MATERIAL_R90_VALIDATION_MISSING',
                         'SECTION_CONSTITUTIVE_LAW_NOT_NORMATIVELY_QUALIFIED']}}


class R069ATimeHistoryTests(unittest.TestCase):
    def test_regular_points_and_no_invented_zero(self):
        self.assertEqual(timeline_points(90, step_minutes=10),
                         [1., 10., 20., 30., 40., 50., 60., 70., 80., 90.])
        self.assertEqual(timeline_points(9, step_minutes=10), [1., 9.])
        with self.assertRaises(ValueError):
            timeline_points(100, step_minutes=.01)
        with self.assertRaises(ValueError):
            scan_member_time_history([1, 1], lambda t: {})
        with self.assertRaises(ValueError):
            scan_member_time_history([float('nan')], lambda t: {})

    def test_observed_adjoining_bracket_not_normative_time(self):
        inputs = {1: 'within', 10: 'within', 20: 'exceeded'}
        r = scan_member_time_history([1, 10, 20], lambda t: evidence(inputs[t]))
        self.assertEqual(r['status'], 'SAMPLED_TRANSITION_BRACKET_FOUND')
        self.assertEqual(r['observed_transition_brackets_minutes'], [
            {'last_sampled_within_minutes': 10., 'first_sampled_exceeded_minutes': 20.}])
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'], 'not_demonstrated')

    def test_temperature_above_table_breaks_bracket(self):
        inputs = {1: 'within', 10: 'blocked', 20: 'exceeded'}
        r = scan_member_time_history([1, 10, 20], lambda t: evidence(inputs[t]))
        self.assertEqual(r['observed_transition_brackets_minutes'], [])
        self.assertEqual(r['unresolved_times_minutes'], [10.])
        self.assertIsNone(r['R_t_minutes'])

    def test_nonlinear_nonconvergence_not_failure(self):
        self.assertEqual(classify_evidence(evidence('nonconvergence'))['class'], UNKNOWN)
        r = scan_member_time_history([1], lambda t: (_ for _ in ()).throw(RuntimeError('solver failed')))
        self.assertEqual(r['status'], 'UNRESOLVED_HISTORY')
        self.assertIsNone(r['first_observed_exceedance_minutes'])

    def test_nonmonotone_does_not_hide_multiple_brackets(self):
        inputs = {1: 'within', 10: 'exceeded', 20: 'within', 30: 'exceeded'}
        r = scan_member_time_history([1, 10, 20, 30], lambda t: evidence(inputs[t]))
        self.assertEqual(len(r['observed_transition_brackets_minutes']), 2)
        self.assertIsNone(r['R_t_minutes'])

    def test_missing_nodal_samples_are_unknown(self):
        self.assertEqual(classify_evidence({'uls': {
            'status': 'SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS'}})['class'], UNKNOWN)

    def test_material_table_exceedance_is_unknown(self):
        d = evidence('within')
        d['material_audit']['blockers'].append('MATERIAL_TABLE_DOMAIN_EXCEEDED')
        self.assertEqual(classify_evidence(d)['class'], UNKNOWN)
        self.assertEqual(classify_evidence(evidence('within'))['class'], WITHIN)
        self.assertEqual(classify_evidence(evidence('exceeded'))['class'], EXCEEDED)

    def test_integrated_recalculation_uses_independent_column_at_each_time(self):
        p = new_project()
        update_column(p, 'c1', {'fire_minutes': 20.})
        update_section(p, 'c1', 'center', {'N_kN': 100., 'Mx_kNm': 0., 'My_kNm': 0.})
        update_member_spec(p, 'c1', {
            'thermal_longitudinal_mode': 'uniform_assumed',
            'uniform_fire_basis': 'four sides exposed for the full height',
            'left_support': 'pinned', 'right_support': 'pinned',
            'support_provenance': 'explicit project input', 'load_mode': 'axial_only',
            'node_count': 2})
        c = p['columns'][0]
        original = copy.deepcopy(c)
        seen = []
        def fake_thermal(column, grid):
            seen.append(('thermal', column['fire_minutes'], grid))
            return {'status': 'evaluated', 'fire_minutes': column['fire_minutes']}
        def fake_member(column, *, thermal, member_spec):
            seen.append(('member', column['fire_minutes'], thermal['fire_minutes']))
            return evidence('within')
        with (patch('rc_fire.integration.r069.evaluate_rectangular_column', side_effect=fake_thermal),
              patch('rc_fire.integration.r069.evaluate_uniform_fire_member', side_effect=fake_member)):
            result = evaluate_uniform_fire_time_history(c, step_minutes=10)
        self.assertEqual(result['sample_count'], 3)
        self.assertEqual([x[1] for x in seen if x[0] == 'thermal'], [1., 10., 20.])
        self.assertEqual(c, original)
        self.assertTrue(result['fire_design_actions_reused_without_recombination'])
        self.assertIsNone(result['R_t_minutes'])
        self.assertFalse(result['normative_claim'])


if __name__ == '__main__':
    unittest.main()
