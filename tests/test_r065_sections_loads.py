"""R0.6.5: one midspan default, arbitrary longitudinal stations and action transfer."""
import copy
import unittest

from multicolumn_r05.project_model import (
    new_project, add_section, remove_section, update_column, update_section,
    update_from_section_overview, section_overview_rows,
    update_thermal_spec, load_state, validate_column,
    export_json, load_json, to_engine_input,
)
from multicolumn_r05.project_calculator import evaluate_column
from rc_fire.integration.r064d import sample_station_bundle


class CenterSectionsAndActionsTests(unittest.TestCase):
    def test_new_columns_have_one_center_section_not_two_ends(self):
        p=new_project(3)
        for c in p['columns']:
            self.assertEqual(len(c['sections']),1)
            s=c['sections'][0]
            self.assertEqual(s['id'],'center')
            self.assertAlmostEqual(s['z_m'],c['length_m']/2)
            self.assertEqual(load_state(s),'empty')
            self.assertFalse(validate_column(c))

    def test_auto_midspan_follows_length_until_position_is_edited(self):
        p=new_project()
        update_column(p,'c1',{'length_m':5.0})
        self.assertAlmostEqual(p['columns'][0]['sections'][0]['z_m'],2.5)
        update_section(p,'c1','center',{'z_m':1.8})
        update_column(p,'c1',{'length_m':6.0})
        self.assertAlmostEqual(p['columns'][0]['sections'][0]['z_m'],1.8)

    def test_as_many_sections_as_needed_with_unique_positions(self):
        p=new_project()
        for _ in range(19):
            add_section(p,'c1')
        c=p['columns'][0]
        self.assertEqual(len(c['sections']),20)
        positions=[s['z_m'] for s in c['sections']]
        self.assertEqual(len(positions),len(set(positions)))
        self.assertTrue(all(0<=z<=c['length_m'] for z in positions))
        self.assertFalse(validate_column(c))
        for sid in [s['id'] for s in c['sections'] if s['id']!='center']:
            remove_section(p,'c1',sid)
        self.assertEqual([s['id'] for s in c['sections']],['center'])
        with self.assertRaisesRegex(ValueError,'хотя бы одно'):
            remove_section(p,'c1','center')

    def test_overview_loads_reach_engine_and_section_editor_bidirectionally(self):
        p=new_project()
        rows=section_overview_rows(p)
        self.assertEqual(len(rows),1)
        rows[0].update({'N, кН':50.0,'Mx, кН·м':3.0,'My, кН·м':2.0})
        changed=update_from_section_overview(p,rows)
        self.assertEqual(changed,[('c1','center')])
        c=p['columns'][0]
        self.assertEqual(load_state(c['sections'][0]),'ready')
        i=to_engine_input(c)
        self.assertEqual(len(i['variants']),1)
        self.assertEqual(i['variants'][0]['id'],'center')
        self.assertEqual(i['variants'][0]['N_kN'],50.0)
        self.assertEqual(i['variants'][0]['M_x_kNm'],3.0)
        self.assertEqual(i['variants'][0]['M_y_kNm'],2.0)
        update_section(p,'c1','center',{'My_kNm':0})
        self.assertEqual(section_overview_rows(p)[0]['My, кН·м'],0)
        result=evaluate_column(c,grid=48)
        self.assertEqual(result['status'],'calculated',result['issues'])
        self.assertIn('center',result['results'])
        self.assertEqual(result['load_summary']['ready'],1)
        self.assertEqual(result['load_summary']['total'],1)
        self.assertIn('center',result['section_statuses'])
        self.assertFalse(result['normative_claim'])
        self.assertEqual(result['fire_resistance_status'],'not_demonstrated')

    def test_k2_warning_retains_actual_coefficients_and_loads_diagnostically(self):
        p=new_project()
        update_thermal_spec(p,'c1',{
            'concrete_family':'siliceous','dry_density_kg_m3':2300.,
            'exposed_faces':['left','right','bottom','top']})
        update_column(p,'c1',{'fire_minutes':30.0})
        update_section(p,'c1','center',{'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
        c=p['columns'][0]
        out=evaluate_column(c,grid=48)
        thermal=out['thermal_normative']
        self.assertEqual(thermal['status'],'evaluated_with_scope_warnings',thermal.get('issues'))
        self.assertTrue(all(x.startswith('К.2:') for x in thermal.get('issues',[])))
        self.assertEqual(out['load_summary']['ready'],1)
        self.assertEqual(out['status'],'calculated',out['issues'])
        self.assertEqual(out['engine_inputs']['thermal_resolution']['source'],'SP_2026_Annex_K')
        self.assertTrue(out['engine_inputs']['thermal_resolution']['scope_warnings'])
        self.assertIn('center',out['results'])
        self.assertFalse(out['normative_claim'])

    def test_unsupported_legacy_exposure_does_not_erase_entered_loads(self):
        p=new_project()
        update_thermal_spec(p,'c1',{'concrete_family':'siliceous',
            'dry_density_kg_m3':2400.,'exposed_faces':['left','bottom']})
        update_section(p,'c1','center',{'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
        out=evaluate_column(p['columns'][0],grid=16)
        self.assertEqual(out['status'],'pending')
        self.assertEqual(out['load_summary']['ready'],1)
        self.assertEqual(out['section_statuses']['center'],'ready')
        self.assertTrue(any('нагрузки введены' in msg.lower() for msg in out['issues']))
        self.assertFalse(out['normative_claim'])

    def test_template_copies_section_actions_without_fabricating_bending_diagram(self):
        p=new_project()
        c=p['columns'][0]
        update_section(p,'c1','center',{'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
        bundle=sample_station_bundle(c)
        self.assertEqual(bundle['N_kN'],50.)
        self.assertEqual(bundle['section_actions_reference_only'][0]['Mx_kNm'],3.)
        self.assertEqual(bundle['section_actions_reference_only'][0]['My_kNm'],2.)
        self.assertIsNone(bundle['distributed_load_kNpm'])
        self.assertIsNone(bundle['fire_actions_source'])
        self.assertIsNone(bundle['node_stations'][0]['thermal'])
        add_section(p,'c1')
        bundle=sample_station_bundle(c)
        self.assertIsNone(bundle['N_kN'])
        update_section(p,'c1','mid1',{'N_kN':60.,'Mx_kNm':0.,'My_kNm':0.})
        bundle=sample_station_bundle(c)
        self.assertIsNone(bundle['N_kN'])
        self.assertEqual(len(bundle['section_actions_reference_only']),2)
        self.assertNotEqual(bundle['section_actions_reference_only'][0]['N_kN'],
                            bundle['section_actions_reference_only'][1]['N_kN'])

    def test_legacy_bottom_top_json_roundtrip_and_member_length(self):
        p=new_project()
        c=p['columns'][0]
        c['sections']=[
            {'id':'bottom','name':'Низ','z_m':0.,'N_kN':500.,'Mx_kNm':6.,'My_kNm':0.},
            {'id':'top','name':'Верх','z_m':3.,'N_kN':510.,'Mx_kNm':8.,'My_kNm':4.}]
        q=load_json(export_json(p))
        self.assertEqual([s['id'] for s in q['columns'][0]['sections']],['bottom','top'])
        update_column(q,'c1',{'length_m':5.})
        self.assertEqual(q['columns'][0]['sections'][1]['z_m'],5.)
        self.assertEqual(q['columns'][0]['sections'][0]['N_kN'],500.)
        self.assertFalse(validate_column(q['columns'][0]))


if __name__=='__main__':
    unittest.main()
