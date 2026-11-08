"""Independent event oracles, actual FE buckling, and source-to-export checks."""
import copy
import csv
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np

from rc_fire.member.time_history import classify_member_state, scan_fire_history
from rc_fire.member.coupled import LinearSectionLaw, solve_coupled_beam
from rc_fire.member.uls import audit_heated_member_uls
from rc_fire.integration.r069 import evaluate_uniform_fire_history, history_input_sha256
from rc_fire.integration.time_ui import restore_history_results, time_history_csv
from multicolumn_r05.project_model import (new_project, update_material_spec,
    update_thermal_spec, update_member_spec, update_section)


def evidence(ratio=.5):
    exceeded = ratio > 1 + 1e-8
    sample = {'maximum_ratio': ratio,
              'limit_check': 'exceeded' if exceeded else 'within_diagnostic_limits'}
    return {'status': 'evidence', 'member': {
        'status': 'strain_limits_exceeded_diagnostic' if exceeded else 'evaluated_diagnostic',
        'any_strain_limit_exceeded': exceeded,
        'relative_equilibrium_residual': 1e-12, 'tangent_min_eigenvalue': 50.},
        'uls': {'status': 'DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED' if exceeded
                else 'SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS',
                'gauss_count': 3, 'node_side_count': 2, 'sampled_locations': 5,
                'node_coverage': True, 'all_sampled_limits_resolved': True,
                'exceeded_count': 5 if exceeded else 0,
                'samples': [copy.deepcopy(sample) for _ in range(5)],
                'critical_sample': sample,
                'blockers': ['FULL_FIRE_R_T_NOT_IMPLEMENTED', 'SPALLING_NOT_QUALIFIED']}}


def configured_column():
    p = new_project()
    update_material_spec(p, 'c1', {'concrete': {'aggregate_family': 'siliceous',
        'consistency': 'S3_S5', 'curing': 'natural',
        'modulus_aggregate': 'gravel_granite_upto40'},
        'steel': {'product_type': 'weldable_bar'}})
    update_thermal_spec(p, 'c1', {'concrete_family': 'siliceous',
        'dry_density_kg_m3': 2400., 'exposed_faces': ['left', 'right', 'bottom', 'top']})
    update_section(p, 'c1', 'center', {'N_kN': 100., 'Mx_kNm': 0., 'My_kNm': 0.})
    update_member_spec(p, 'c1', {'thermal_longitudinal_mode': 'uniform_assumed',
        'uniform_fire_basis': 'same exposure and section along full length',
        'left_support': 'pinned', 'right_support': 'pinned',
        'support_provenance': 'explicit test model', 'load_mode': 'axial_only',
        'node_count': 2})
    return p


class TimeSearchTests(unittest.TestCase):
    def test_known_strain_crossing_refined_by_new_solves(self):
        calls = []
        def run(t):
            calls.append(t)
            return evidence(.25 + .75 * t / 7.3)
        r = scan_fire_history(run, end_minutes=30., step_minutes=5., tolerance_minutes=.01)
        lo, hi = r['observed_limit_bracket_minutes']
        self.assertLessEqual(lo, 7.3)
        self.assertGreaterEqual(hi, 7.3)
        self.assertLessEqual(hi - lo, .01)
        self.assertEqual(r['status'], 'OBSERVED_STRAIN_LIMIT_BRACKETED')
        self.assertEqual(len(calls), len(set(calls)))
        self.assertEqual(r['evaluation_count'], len(calls))
        self.assertEqual(calls[0], 0.)
        self.assertTrue(any(x['phase'] == 'refinement' for x in r['samples']))
        self.assertIsNone(r['fire_resistance_minutes'])
        self.assertFalse(r['continuous_lower_bound_proven'])
        self.assertNotIn('FULL_FIRE_R_T_NOT_IMPLEMENTED', r['blockers'])
        self.assertIn('SPALLING_NOT_QUALIFIED', r['blockers'])

    def test_exact_horizon_included_when_not_a_step_multiple(self):
        calls = []
        def run(t):
            calls.append(t)
            return evidence()
        r = scan_fire_history(run, end_minutes=12.3, step_minutes=5.)
        self.assertEqual(calls, [0., 5., 10., 12.3])
        self.assertTrue(r['sampled_horizon_completed'])
        self.assertFalse(r['normative_claim'])
        self.assertFalse(r['continuous_time_coverage'])
        self.assertIsNone(r['observed_limit_bracket_minutes'])
        json.dumps(r, allow_nan=False)

    def test_domain_stop_is_not_fire_failure(self):
        def run(t):
            return evidence() if t < 6.7 else {
                'status': 'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT', 'reason': 'T>800 C'}
        r = scan_fire_history(run, end_minutes=90., tolerance_minutes=.05)
        self.assertEqual(r['status'], 'MODEL_DOMAIN_REACHED')
        self.assertIsNone(r['observed_limit_bracket_minutes'])
        self.assertLessEqual(r['boundary']['last_admitted_minutes'], 6.7)
        self.assertGreaterEqual(r['boundary']['first_nonadmitted_minutes'], 6.7)

    def test_earlier_unknown_state_supersedes_later_strain_event(self):
        def run(t):
            if t >= 8.:
                return evidence(2.)
            if t >= 5.:
                return {'member': {'status': 'line_search_failed'}}
            return evidence()
        r = scan_fire_history(run, end_minutes=20., step_minutes=10.)
        self.assertEqual(r['status'], 'NUMERICAL_SOLUTION_UNRESOLVED')
        self.assertIsNone(r['observed_limit_bracket_minutes'])

    def test_initial_limit_is_not_an_admissible_baseline(self):
        r = scan_fire_history(lambda t: evidence(2.), end_minutes=90.)
        self.assertEqual(r['status'], 'LIMIT_AT_INITIAL_STATE_DIAGNOSTIC')
        self.assertIsNone(r['last_admitted_time_minutes'])
        self.assertIsNone(r['observed_limit_bracket_minutes'])
        self.assertEqual(r['evaluation_count'], 1)

    def test_missing_input_stops_at_initial_state(self):
        r = scan_fire_history(lambda t: {'status': 'BLOCKED_INPUT', 'reason': 'N missing'},
                              end_minutes=90.)
        self.assertEqual(r['status'], 'INPUT_NOT_READY')
        self.assertEqual(r['evaluation_count'], 1)
        self.assertIsNone(r['fire_resistance_minutes'])

    def test_refinement_exhaustion_does_not_claim_requested_precision(self):
        r = scan_fire_history(lambda t: evidence(.5 + t / 10.), end_minutes=20.,
            step_minutes=10., tolerance_minutes=.001, max_refinements=1)
        self.assertEqual(r['status'], 'LIMIT_BRACKET_TOLERANCE_NOT_REACHED')
        self.assertFalse(r['boundary']['tolerance_reached'])
        self.assertIsNone(r['observed_limit_bracket_minutes'])

    def test_controls_reject_nonfinite_bools_and_runaway_work(self):
        bad = [{'end_minutes': x} for x in (0, -1, 241, True, float('nan'), float('inf'))]
        bad += [{'step_minutes': x} for x in (0, -1, True, 1e-300)]
        bad += [{'tolerance_minutes': x} for x in (0, True, 6.)]
        bad += [{'max_refinements': x} for x in (-1, 51, True, 1.5)]
        for controls in bad:
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                scan_fire_history(lambda t: evidence(), **{'end_minutes': 90., **controls})

    def test_programming_errors_are_not_converted_into_R(self):
        with self.assertRaisesRegex(RuntimeError, 'broken evaluator'):
            scan_fire_history(lambda t: (_ for _ in ()).throw(RuntimeError('broken evaluator')),
                              end_minutes=10.)


class StateEvidenceTests(unittest.TestCase):
    def test_missing_end_or_gauss_evidence_cannot_admit_time(self):
        mutations = [{'node_coverage': False}, {'gauss_count': 0},
                     {'all_sampled_limits_resolved': False}, {'samples': []},
                     {'node_side_count': 1}, {'sampled_locations': 4}]
        for change in mutations:
            r = evidence()
            r['uls'].update(change)
            with self.subTest(change=change):
                self.assertEqual(classify_member_state(r)['state'], 'evidence_incomplete')

    def test_nonfinite_ratio_residual_and_negative_tangent_are_not_admitted(self):
        for field, val in (('relative_equilibrium_residual', float('nan')),
                           ('relative_equilibrium_residual', .1),
                           ('tangent_min_eigenvalue', -1.)):
            r = evidence()
            r['member'][field] = val
            self.assertEqual(classify_member_state(r)['state'], 'evidence_incomplete')
        r = evidence(float('nan'))
        self.assertEqual(classify_member_state(r)['state'], 'evidence_incomplete')

    def test_nonpositive_trial_tangent_requires_equilibrium(self):
        r = {'member': {'status': 'critical_or_nonpositive_tangent',
            'tangent_min_eigenvalue': -1., 'relative_equilibrium_residual': .4,
            'equilibrium_at_instability': False}}
        self.assertEqual(classify_member_state(r)['state'], 'numerical_unresolved')
        r['member'].update(relative_equilibrium_residual=0., equilibrium_at_instability=True)
        self.assertEqual(classify_member_state(r)['state'], 'stability_limit')

    def test_nonpositive_node_tangent_cannot_be_hidden_by_global_convergence(self):
        r = evidence()
        r['uls']['blockers'].append('NODE_SECTION_TANGENT_NOT_POSITIVE')
        self.assertEqual(classify_member_state(r)['state'], 'evidence_incomplete')

    def test_unresolved_nonfinite_limits_still_export_as_valid_JSON(self):
        r = scan_fire_history(lambda t: evidence(float('nan')), end_minutes=10.)
        self.assertEqual(r['status'], 'ULS_EVIDENCE_INCOMPLETE')
        json.dumps(r, allow_nan=False)

    def test_actual_beam_buckling_time_matches_Euler_oracle(self):
        # EI(t)=EI0*(1-t/100); N=0.5*pi^2*EI0/L^2 -> exact tcrit=50.
        z = np.linspace(0., 3., 9)
        class StrainCheckedLinearLaw(LinearSectionLaw):
            def evaluate(self, kappa, N_kN):
                M, D, meta = super().evaluate(kappa, N_kN)
                meta.update(max_concrete_compressive_strain=0., max_steel_tensile_strain=0.,
                            eps_cu2=.0035, tensile_steel_limit=.01)
                return M, D, meta
        def run(t):
            law = StrainCheckedLinearLaw(np.eye(2) * 1000. * (1. - t / 100.))
            N = .5 * math.pi**2 * 1000. / 9.
            solved = solve_coupled_beam(z, N, law_at_gauss=lambda i, j: law)
            uls = audit_heated_member_uls(solved, z, N, node_laws=[law] * len(z))
            return {'member': solved, 'uls': uls}
        r = scan_fire_history(run, end_minutes=80., step_minutes=10., tolerance_minutes=.01)
        self.assertEqual(r['status'], 'OBSERVED_STABILITY_LIMIT_BRACKETED')
        lo, hi = r['observed_limit_bracket_minutes']
        self.assertAlmostEqual((lo + hi) / 2., 50., delta=.02)
        self.assertLessEqual(hi - lo, .01)


class HistoryIntegrationTests(unittest.TestCase):
    def test_actual_AnnexK_member_chain_and_source_are_reproducible(self):
        c = configured_column()['columns'][0]
        original = copy.deepcopy(c)
        r = evaluate_uniform_fire_history(c, end_minutes=10., step_minutes=5.,
                                          tolerance_minutes=.05)
        self.assertEqual(c, original)
        self.assertEqual(r['source_sha256'], history_input_sha256(c))
        self.assertEqual(r['samples'][0]['state'], 'admitted_sample')
        self.assertEqual(r['status'], 'OBSERVED_STRAIN_LIMIT_BRACKETED')
        self.assertEqual(r['section_actions'], original['sections'])
        self.assertEqual(r['input_column'], original)
        self.assertFalse(r['fire_combination_recalculated'])
        self.assertFalse(r['normative_claim'])
        self.assertIn('HOT_CONCRETE_ULTIMATE_STRAIN_NOT_QUALIFIED', r['blockers'])
        self.assertNotIn('NO_FIRE_LOAD_SOURCE', r['blockers'])
        again = evaluate_uniform_fire_history(c, **r['controls'])
        self.assertEqual(r, again)
        json.dumps(r, allow_nan=False)

    def test_every_snapshot_recomputes_thermal_preserving_signed_actions(self):
        c = configured_column()['columns'][0]
        c['sections'][0].update(Mx_kNm=-3., My_kNm=2.)
        snapshots = []
        def run(snapshot, *, thermal):
            snapshots.append((copy.deepcopy(snapshot), thermal))
            return evidence()
        with patch('rc_fire.integration.r069.evaluate_uniform_fire_member', side_effect=run):
            r = evaluate_uniform_fire_history(c, end_minutes=12., step_minutes=5.)
        self.assertEqual([s['fire_minutes'] for s, th in snapshots], [0., 5., 10., 12.])
        for snapshot, thermal in snapshots:
            self.assertEqual(snapshot['fire_minutes'], thermal['fire_minutes'])
            self.assertEqual(snapshot['sections'], c['sections'])
        self.assertNotEqual(snapshots[0][1]['max_temperature_C'], snapshots[-1][1]['max_temperature_C'])
        self.assertEqual(r['section_actions'][0]['Mx_kNm'], -3.)

    def test_unconfigured_or_missing_N_cannot_run_history(self):
        r = evaluate_uniform_fire_history(new_project()['columns'][0])
        self.assertEqual(r['status'], 'INPUT_NOT_READY')
        self.assertEqual(r['evaluation_count'], 1)
        c = configured_column()['columns'][0]
        c['sections'][0]['N_kN'] = None
        self.assertEqual(evaluate_uniform_fire_history(c)['status'], 'INPUT_NOT_READY')

    def test_90min_material_stop_never_becomes_strain_or_stability_failure(self):
        from rc_fire.integration.r067 import evaluate_uniform_fire_member
        c = configured_column()['columns'][0]
        r = evaluate_uniform_fire_member(c)
        self.assertEqual(r['status'], 'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT')
        self.assertEqual(classify_member_state(r)['state'], 'model_domain_stop')

    def test_cached_results_expire_on_any_source_change_or_deleted_column(self):
        p = configured_column()
        c = p['columns'][0]
        r = evaluate_uniform_fire_history(c, end_minutes=1.)
        state = {'r069_result_c1': r, 'exports': b'old zip'}
        calcs = {'c1': {}}
        restore_history_results(state, p['columns'], calcs)
        self.assertIs(calcs['c1']['fire_history_r069'], r)
        c['sections'][0]['Mx_kNm'] = -5.
        restore_history_results(state, p['columns'], {'c1': {}})
        self.assertNotIn('r069_result_c1', state)
        self.assertIsNone(state['exports'])
        state.update(r069_result_c99=r, exports=b'other zip')
        restore_history_results(state, p['columns'], {'c1': {}})
        self.assertNotIn('r069_result_c99', state)
        self.assertIsNone(state['exports'])

    def test_csv_and_Word_ZIP_exports_include_history(self):
        from docx import Document
        from multicolumn_r05.project_calculator import evaluate_project
        from multicolumn_r05.project_reports import combined_report, single_report, make_exports
        p = configured_column()
        c = p['columns'][0]
        result = evaluate_uniform_fire_history(c, end_minutes=1.)
        rows = list(csv.DictReader(io.StringIO(time_history_csv(result))))
        self.assertEqual(len(rows), result['evaluation_count'])
        calcs = evaluate_project(p, grid=16)
        calcs['c1']['fire_history_r069'] = result
        with TemporaryDirectory() as td:
            for generator in (combined_report, single_report):
                path = Path(td) / (generator.__name__ + '.docx')
                args = (p, calcs) if generator is combined_report else (c, calcs['c1'])
                generator(*args, path)
                text = '\n'.join(x.text for x in Document(path).paragraphs)
                self.assertIn('R0.6.9', text)
                self.assertIn('НЕ подтверждён', text)
            blob = make_exports(p, calcs, pdf=False)
        with ZipFile(io.BytesIO(blob)) as z:
            self.assertEqual(json.loads(z.read('time_history/c1.json')), result)
            self.assertEqual(z.read('time_history/c1.csv').decode(), time_history_csv(result))


if __name__ == '__main__':
    unittest.main()
