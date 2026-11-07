"""R0.5: checks bi-directional binding, source of truth, reports and modelling restrictions."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
import pandas as pd
from docx import Document
from multicolumn_r05.project_model import (new_project,set_count,default_bars,update_column,update_section,
        load_json,export_json,add_section,remove_section,update_from_overview,
        overview_rows,update_from_section_overview,section_overview_rows,
        replace_bars,reset_auto_bars,load_state,validate_column)
from multicolumn_r05.project_calculator import evaluate_column,evaluate_project
from multicolumn_r05.project_reports import combined_report,single_report,make_exports,verify_footer_unchanged,MASTER

def legacy_project(count=1):
    """Explicit two-end legacy fixture, retained for backward compatibility."""
    project=new_project(count)
    for c in project['columns']:
        c['sections']=[
            {'id':'bottom','name':'Низ','z_m':0.0,'N_kN':None,'Mx_kNm':None,'My_kNm':None},
            {'id':'top','name':'Верх','z_m':c['length_m'],'N_kN':None,'Mx_kNm':None,'My_kNm':None}]
    return project


class ProjectTests(unittest.TestCase):
    def test_initial_defaults_and_no_loads(self):
        p=new_project(3)
        self.assertEqual(len(p['columns']),3)
        for c in p['columns']:
            self.assertEqual((c['b_mm'],c['h_mm'],c['length_m'],c['cover_mm'],c['stirrup_mm'],c['bar_diameter_mm'],c['mu_x'],c['mu_y']),
                (600,600,3,20,10,20,1,1))
            self.assertEqual(c['bars'][0]['x_mm'],40)
            self.assertEqual(c['bars'][-1]['y_mm'],560)
            self.assertEqual([load_state(x) for x in c['sections']],['empty'])
            self.assertEqual(c['sections'][0]['id'],'center')
            self.assertAlmostEqual(c['sections'][0]['z_m'],c['length_m']/2)
        self.assertTrue(all(v['status']=='pending' for v in evaluate_project(p).values()))

    def test_add_remove_unique_identity_and_shared_state(self):
        p=new_project(3);set_count(p,2);set_count(p,4)
        self.assertEqual(len(p['columns']),4)
        self.assertEqual(len(set(c['id'] for c in p['columns'])),4)
        self.assertEqual(p['columns'][0]['id'],'c1')

    def test_overview_to_column_two_way(self):
        p=new_project(2)
        table=overview_rows(p);table[0]['b, мм']=720;table[0]['Ø, мм']=25
        update_from_overview(p,table)
        self.assertEqual(p['columns'][0]['b_mm'],720)
        self.assertEqual(p['columns'][0]['bars'][-1]['x_mm'],720-20-10-12.5)
        update_column(p,'c1',{'b_mm':650})
        self.assertEqual(overview_rows(p)[0]['b, мм'],650)
        self.assertEqual(overview_rows(p)[1]['b, мм'],600)

    def test_sections_overview_two_way(self):
        p=legacy_project(2)
        rows=section_overview_rows(p)
        rows[0]['N, кН']=520;rows[0]['Mx, кН·м']=2.;rows[0]['My, кН·м']=0.
        rows[1]['N, кН']=540;rows[1]['Mx, кН·м']=3.;rows[1]['My, кН·м']=4.
        update_from_section_overview(p,rows)
        self.assertEqual(p['columns'][0]['sections'][0]['N_kN'],520)
        update_section(p,'c1','bottom',{'N_kN':700})
        self.assertEqual(section_overview_rows(p)[0]['N, кН'],700)
        self.assertIsNone(p['columns'][1]['sections'][0]['N_kN'])

    def test_change_length_moves_top_and_auto_rebar(self):
        p=legacy_project()
        update_column(p,'c1',{'length_m':5,'cover_mm':25,'bar_diameter_mm':25})
        c=p['columns'][0]
        self.assertEqual(c['sections'][-1]['z_m'],5)
        self.assertEqual(c['bars'][0]['x_mm'],25+10+12.5)
        self.assertFalse(validate_column(c))

    def test_manual_bars_not_silently_moved_and_invalid_cover_detected(self):
        p=new_project();bars=copy.deepcopy(p['columns'][0]['bars'])
        replace_bars(p,'c1',bars)
        update_column(p,'c1',{'cover_mm':45})
        self.assertEqual(p['columns'][0]['bars'][0]['x_mm'],40)
        self.assertTrue(validate_column(p['columns'][0]))
        reset_auto_bars(p,'c1')
        self.assertEqual(p['columns'][0]['bars'][0]['x_mm'],65)

    def test_extra_sections_and_limits(self):
        p=new_project();add_section(p,'c1')
        self.assertEqual(len(p['columns'][0]['sections']),2)
        remove_section(p,'c1','mid1')
        self.assertEqual(len(p['columns'][0]['sections']),1)
        with self.assertRaises(ValueError):remove_section(p,'c1','center')

    def test_save_load_roundtrip(self):
        p=legacy_project(2);update_section(p,'c2','top',{'N_kN':1000,'Mx_kNm':0,'My_kNm':0})
        q=load_json(export_json(p))
        self.assertEqual(q['columns'][1]['sections'][1]['N_kN'],1000)
        self.assertEqual(q['columns'][0]['bars'],p['columns'][0]['bars'])

    def test_incomplete_no_fabricated_zero_loads(self):
        p=new_project();update_section(p,'c1','center',{'N_kN':200})
        r=evaluate_column(p['columns'][0])
        self.assertEqual(r['status'],'pending')
        self.assertIn('incomplete',r['section_statuses'].values())
        self.assertFalse(r['results'])

    def test_steel_envelope_blocks_unverified_class(self):
        p=new_project();update_column(p,'c1',{'steel_grade':'S400'})
        self.assertTrue(validate_column(p['columns'][0]))
        self.assertEqual(evaluate_column(p['columns'][0])['status'],'invalid')

    def test_two_sections_one_calculation_and_critical(self):
        p=legacy_project()
        update_section(p,'c1','bottom',{'N_kN':500,'Mx_kNm':6,'My_kNm':0})
        update_section(p,'c1','top',{'N_kN':510,'Mx_kNm':8,'My_kNm':4})
        result=evaluate_column(p['columns'][0],grid=48)
        self.assertEqual(result['status'],'calculated')
        self.assertEqual(set(result['results']),{'top','bottom'})
        self.assertIn(result['worst']['section_id'],('top','bottom'))
        self.assertFalse(result['normative_claim'])
        self.assertLess(result['worst']['u'],1)

    def test_recalc_after_load_edit(self):
        p=legacy_project()
        for s in p['columns'][0]['sections']:
            update_section(p,'c1',s['id'],{'N_kN':500,'Mx_kNm':5,'My_kNm':0})
        a=evaluate_column(p['columns'][0])
        update_section(p,'c1','top',{'N_kN':650,'Mx_kNm':20,'My_kNm':7})
        b=evaluate_column(p['columns'][0])
        self.assertNotEqual(a['results']['top']['axes']['x']['M_Ed_kNm'],b['results']['top']['axes']['x']['M_Ed_kNm'])
        self.assertEqual(a['results']['bottom']['axes']['x']['M_Ed_kNm'],b['results']['bottom']['axes']['x']['M_Ed_kNm'])

    def test_draft_report_and_combined_original_frame(self):
        p=legacy_project(2)
        update_section(p,'c1','bottom',{'N_kN':500,'Mx_kNm':6,'My_kNm':0})
        update_section(p,'c1','top',{'N_kN':510,'Mx_kNm':8,'My_kNm':4})
        results=evaluate_project(p)
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'combined.docx';combined_report(p,results,target)
            self.assertTrue(verify_footer_unchanged(MASTER,target))
            doc=Document(target)
            self.assertGreaterEqual(len(doc.inline_shapes),2)
            text=' '.join(x.text for x in doc.paragraphs)
            self.assertIn('К1',text)
            self.assertIn('К2',text)
            self.assertIn('НЕ выдаётся',text)
            q=Path(td)/'draft.docx';single_report(p['columns'][1],results['c2'],q)
            self.assertTrue(verify_footer_unchanged(MASTER,q))
            self.assertIn('ЧЕРНОВИК',' '.join(x.text for x in Document(q).paragraphs))

    def test_export_zip_contains_both_docx_formats_and_project(self):
        p=new_project(1)
        calc=evaluate_project(p)
        blob=make_exports(p,calc,pdf=False)
        with ZipFile(io.BytesIO(blob)) as z:
            self.assertIn('Общий_отчет.docx',z.namelist())
            self.assertTrue(any(x.startswith('Конструкции/') for x in z.namelist()))
            self.assertIn('project.json',z.namelist())
            self.assertIn('summary.json',z.namelist())

if __name__=='__main__':unittest.main(verbosity=2)