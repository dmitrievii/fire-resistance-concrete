"""Independent R0.6.9 time history / Belarus Table 3 acceptance tests."""
import copy
import math
import unittest
from unittest.mock import patch
from docx import Document

from multicolumn_r05.project_model import (
    new_project,update_material_spec,update_thermal_spec,
    update_section,update_column,update_fire_resistance_reference)
from rc_fire.resistance import (
    R_CLASSES,TABLE_3,evaluate_table3_class,evaluate_resistance_history,
    evaluate_station,GOOD,EXCEEDED,SCOPE)
from rc_fire.resistance.ui import history_signature
from rc_fire.resistance.report import add_resistance_history_note


def example(*,minutes=90.):
    p=new_project()
    update_material_spec(p,'c1',{'concrete':{
        'aggregate_family':'siliceous','consistency':'V3_V4',
        'curing':'natural','modulus_aggregate':'gravel_granite_upto40'},
        'steel':{'product_type':'weldable_bar'}})
    update_thermal_spec(p,'c1',{
        'concrete_family':'siliceous','dry_density_kg_m3':2200.,
        'exposed_faces':['left','right','bottom','top']})
    update_column(p,'c1',{'fire_minutes':minutes})
    update_section(p,'c1','center',{'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
    p['columns'][0]['annex_l_spec']={
        'coarse_aggregate_volume_pct':40.,'max_aggregate_mm':40.,
        'cement_kg_m3':100.,'water_cement_ratio':.4,
        'relative_humidity_pct':44.,'natural_sand_confirmed':True,
        'moisture_mode':'auto'}
    return p


def dummy(time,state):
    return {'time_min':float(time),'state':state,'thermal_status':'evaluated',
            'temperature_max_C':250.,'bar_temperature_max_C':100.,
            'area_after_critical_isotherm_m2':.36,
            'thermal_warnings':[], 'reasons':[],'member_status':None}


class R069TimeHistoryTests(unittest.TestCase):
    def test_table3_exact_source_values(self):
        self.assertEqual(R_CLASSES,(30,60,90,120,180))
        self.assertEqual(TABLE_3[0.3][120],((250,40),(350,35)))
        self.assertEqual(TABLE_3[0.5][120],((350,45),(450,40)))
        self.assertEqual(TABLE_3[0.7][90],((350,53),(450,40)))
        self.assertEqual(TABLE_3[0.3][180],((350,45),))

    def test_K1_geometry_yields_conditional_R120_for_eta_below_03(self):
        p=example()
        c=p['columns'][0]
        update_fire_resistance_reference(p,'c1',{
            'N_Rd_normal_temperature_kN':1000.,
            'effective_length_provenance':'user geometry per project',
            'fire_exposure_provenance':'all four faces on the project drawing'})
        r=evaluate_table3_class(c)
        self.assertAlmostEqual(r['eta'],.05)
        self.assertEqual(r['eta_band'],.3)
        self.assertEqual(r['min_bar_axis_distance_mm'],40.)
        self.assertEqual(r['conditional_class_max_min'],120)
        self.assertNotIn(180,r['conditional_classes_min'])
        self.assertTrue(r['two_axis_actions'])
        self.assertFalse(r['normative_claim'])
        self.assertIsNone(r['exact_failure_time_min'])
        self.assertTrue(any('simultaneous Mx/My' in x for x in r['missing_or_unverified']))

    def test_no_Nrd_cannot_create_eta_or_tabular_approval(self):
        r=evaluate_table3_class(example()['columns'][0])
        self.assertIsNone(r['eta'])
        self.assertIsNone(r['conditional_class_max_min'])
        self.assertIn('N_Rd_normal_temperature_kN for η=Nfi/NRd',
                      r['missing_or_unverified'])
        self.assertIn(120,r['geometric_classes_by_eta_band']['0.3'])
        self.assertFalse(r['normative_claim'])

    def test_table3_05_and_outside_07(self):
        p=example()
        c=p['columns'][0]
        update_fire_resistance_reference(p,'c1',{
            'N_Rd_normal_temperature_kN':100.,
            'effective_length_provenance':'design effective length',
            'fire_exposure_provenance':'exposure geometry checked'})
        a=evaluate_table3_class(c)
        self.assertEqual(a['eta_band'],.5)
        self.assertEqual(a['conditional_class_max_min'],120)
        update_fire_resistance_reference(p,'c1',{'N_Rd_normal_temperature_kN':70.})
        a=evaluate_table3_class(c)
        self.assertIsNone(a['eta_band'])
        self.assertEqual(a['status'],'OUTSIDE_TABLE_SCOPE')
        self.assertIsNone(a['conditional_class_max_min'])

    def test_time_grid_and_first_800_scope_is_never_tR(self):
        c=example()['columns'][0]
        r=evaluate_resistance_history(c,step_minutes=30.,grid=8)
        self.assertEqual([x['time_min'] for x in r['samples']],[0.,30.,60.,90.])
        self.assertIsNone(r['computed_exact_R_min'])
        self.assertIsNone(r['normative_class_approved'])
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')
        self.assertTrue(any(x['state']==SCOPE for x in r['samples']))
        self.assertEqual(r['first_outside_scope_min'],
                         min(x['time_min'] for x in r['samples'] if x['state']==SCOPE))

    def test_no_fabricated_time_when_model_does_not_converge(self):
        c=example(minutes=30.)['columns'][0]
        def model(col,t,**kw):
            return dummy(t,GOOD if t==0 else 'UNRESOLVED_NUMERICAL_EVIDENCE')
        with patch('rc_fire.resistance.history.evaluate_station',side_effect=model):
            r=evaluate_resistance_history(c,step_minutes=15.,grid=8)
        self.assertIsNone(r['diagnostic_limit_bracket_min'])
        self.assertIsNone(r['computed_exact_R_min'])
        self.assertEqual(r['status'],'INCOMPLETE_EVIDENCE')

    def test_first_strain_limit_bracket_is_not_normative_failure(self):
        c=example(minutes=30.)['columns'][0]
        def model(col,t,**kw):return dummy(t,GOOD if t<20 else EXCEEDED)
        with patch('rc_fire.resistance.history.evaluate_station',side_effect=model):
            r=evaluate_resistance_history(c,step_minutes=15.,grid=8,refine_passes=2)
        self.assertEqual(r['status'],'DIAGNOSTIC_LIMIT_BRACKETED')
        self.assertEqual(r['diagnostic_limit_bracket_min'],[18.75,22.5])
        self.assertIsNone(r['computed_exact_R_min'])
        self.assertFalse(r['normative_claim'])

    def test_gap_in_history_must_not_form_a_failure_bracket(self):
        c=example(minutes=30.)['columns'][0]
        def model(col,t,**kw):
            return dummy(t,GOOD if t==0 else
                      'UNRESOLVED_NUMERICAL_EVIDENCE' if t==15 else EXCEEDED)
        with patch('rc_fire.resistance.history.evaluate_station',side_effect=model):
            r=evaluate_resistance_history(c,step_minutes=15.,grid=8)
        self.assertIsNone(r['diagnostic_limit_bracket_min'])

    def test_requested_member_branch_never_invents_supports_or_load_diagram(self):
        c=example(minutes=10.)['columns'][0]
        row=evaluate_station(c,0.,grid=8,with_member=True)
        self.assertEqual(row['member_status'],'BLOCKED_INPUT')
        self.assertFalse(row['member_normative_claim'])
        # A member model is not inferred from a single section's Mx/My.
        self.assertEqual(c['member_spec']['thermal_longitudinal_mode'],'explicit_only')

    def test_explicit_member_model_runs_in_temporal_station(self):
        c=example(minutes=10.)['columns'][0]
        c['member_spec']={
            'thermal_longitudinal_mode':'uniform_assumed',
            'uniform_fire_basis':'same fire exposure in all longitudinal planes',
            'left_support':'pinned','right_support':'pinned',
            'support_provenance':'explicit idealized hinge-hinge member',
            'load_mode':'uniform_transverse_load',
            'q_x_kNpm':0.0,'q_y_kNpm':0.0,'node_count':2}
        row=evaluate_station(c,0.,grid=8,with_member=True)
        self.assertIsNotNone(row['member_status'],row)
        self.assertFalse(row['member_normative_claim'])

    def test_invalid_options_and_61_point_guard(self):
        c=example()['columns'][0]
        for kw in ({'step_minutes':0},{'grid':5},{'policy':'extrapolate'},
                   {'horizon_minutes':241},{'step_minutes':.5,'horizon_minutes':90}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                evaluate_resistance_history(c,**kw)

    def test_history_signature_tracks_reference_and_time(self):
        p=example()
        c=p['columns'][0];old=history_signature(c)
        update_fire_resistance_reference(p,'c1',{'N_Rd_normal_temperature_kN':1500.})
        self.assertNotEqual(old,history_signature(c))
        old=history_signature(c)
        update_column(p,'c1',{'fire_minutes':60.})
        self.assertNotEqual(old,history_signature(c))

    def test_word_annotation_only_diagnostic(self):
        c=example(minutes=15.)['columns'][0]
        h=evaluate_resistance_history(c,step_minutes=15.,grid=8)
        doc=Document()
        add_resistance_history_note(doc,{'resistance_r069':h})
        text=' '.join(x.text for x in doc.paragraphs)
        self.assertIn('R0.6.9',text)
        self.assertIn('НЕ установлены',text)
        self.assertIn('НЕ ВРЕМЯ РАЗРУШЕНИЯ',text if h['first_outside_scope_min'] is not None else text+' НЕ ВРЕМЯ РАЗРУШЕНИЯ')


if __name__=="__main__":
    unittest.main()
