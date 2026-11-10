"""R0.6.8 Belarus Annex L: source, unit, data ownership and fail-closed regression."""
import copy
import unittest
from docx import Document

from multicolumn_r05.project_model import (new_project,update_material_spec,
    update_thermal_spec,update_annex_l_spec,export_json,load_json)
from multicolumn_r05.project_calculator import evaluate_column
from multicolumn_r05.r056_reporting import add_r056_diagnostics
from rc_fire.spalling import (TABLE_L1,TABLE_L2,coefficient_K1c,moisture_wc,
    porosity_np,physical_inputs,evaluate_annex_l,AnnexLError)


def prepared_project():
    p=new_project()
    update_material_spec(p,'c1',{'concrete':{
        'aggregate_family':'siliceous','consistency':'S3_S5',
        'curing':'natural','modulus_aggregate':'gravel_granite_upto40',
        'fine_grained':False},
        'steel':{'product_type':'weldable_bar'}})
    update_thermal_spec(p,'c1',{'concrete_family':'siliceous',
        'dry_density_kg_m3':2200.,
        'exposed_faces':['left','right','bottom','top']})
    update_annex_l_spec(p,'c1',{
        'natural_sand_confirmed':True,
        'coarse_aggregate_volume_pct':50.,
        'max_aggregate_mm':40.,
        'cement_kg_m3':500.,
        'water_cement_ratio':0.4,
        'relative_humidity_pct':50.})
    return p


class BelarusAnnexLTests(unittest.TestCase):
    def test_no_foreign_spalling_default(self):
        p=new_project()
        c=p['columns'][0]
        self.assertEqual(c['spalling'],{})
        self.assertEqual(c['annex_l_spec'],{})
        r=evaluate_column(c,grid=16)
        self.assertIn('annex_l',r)
        self.assertEqual(r['annex_l']['status'],'blocked_input_or_scope')
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

    def test_dry_density_and_family_are_single_sourced(self):
        p=prepared_project()
        c=p['columns'][0]
        x=physical_inputs(c)
        self.assertEqual(x['dry_density_kg_m3'],2200)
        self.assertEqual(x['aggregate_family'],'siliceous')
        self.assertNotIn('dry_density_kg_m3',c['annex_l_spec'])
        self.assertNotIn('aggregate_family',c['annex_l_spec'])
        result=evaluate_annex_l(c)
        self.assertEqual(result['status'],'calculated_method_scope',result.get('reason'))
        self.assertEqual(result['resolved_inputs']['dry_density_kg_m3'],2200)
        self.assertEqual(result['source'].split(',')[0],'СП 2.02.05-2026')
        self.assertIn('F',result)
        self.assertTrue(result['F']>0)
        self.assertFalse(result['normative_claim'])
        self.assertEqual(result['fire_resistance_status'],'not_demonstrated')

    def test_belarus_table_L1_and_L2_exact_nodes(self):
        self.assertEqual(TABLE_L1['siliceous'][35.],0.47)
        self.assertEqual(TABLE_L1['calcareous'][50.],0.44)
        self.assertAlmostEqual(coefficient_K1c('siliceous',42.5,12.)[0],
                               ((.47+.53)/2)*1.14)
        self.assertEqual(TABLE_L2[500.][50.],2.7)
        wc,src,_=moisture_wc(500.,50.)
        self.assertEqual(src,'table_L2_exact')
        self.assertAlmostEqual(wc,0.027)
        w,src,note=moisture_wc(500.,55.,water_cement_ratio=.4)
        self.assertEqual(src,"formula_L5_unit_interpretation")
        self.assertAlmostEqual(w,0.024619110145109882)
        self.assertTrue(note["interpretation_requires_review"])

    def test_porosity_both_source_equations(self):
        self.assertAlmostEqual(porosity_np(500.,.4)[0],.1)
        self.assertEqual(porosity_np(500.,.4)[1],'Л.2')
        self.assertAlmostEqual(porosity_np(500.,.3)[0],.12)
        self.assertEqual(porosity_np(500.,.3)[1],'Л.3')

    def test_no_wrong_legacy_F_reuse(self):
        p=prepared_project()
        c=p['columns'][0]
        c['spalling']={'method':'sp468','aggregate_type':'granite',
            'aggregate_pct':35.,'cement_kg_m3':700.,
            'water_cement_ratio':.3,'design_relative_humidity_pct':75.,
            'max_aggregate_mm':5.0,'F':0.1,'K_1C':1.e7}
        r=evaluate_annex_l(c)
        self.assertEqual(r['status'],'calculated_method_scope')
        # The canonical composition overrides archived foreign-method inputs.
        self.assertAlmostEqual(r['resolved_inputs']['cement_kg_m3'],500.)
        self.assertNotAlmostEqual(r['F'],0.1,places=2)
        self.assertNotIn('F',r['resolved_inputs'])

    def test_old_user_inputs_migrate_only_as_physical_data(self):
        p=new_project();c=p['columns'][0]
        c['spalling']={'method':'sp468','aggregate_type':'granite',
            'aggregate_pct':50.,'cement_kg_m3':500.,
            'water_cement_ratio':0.4,'design_relative_humidity_pct':50.,
            'max_aggregate_mm':40.,'F':2.3903}
        update_material_spec(p,'c1',{'concrete':{
            'aggregate_family':'siliceous','consistency':'S3_S5',
            'curing':'natural','modulus_aggregate':'gravel_granite_upto40',
            'fine_grained':False},'steel':{'product_type':'weldable_bar'}})
        update_thermal_spec(p,'c1',{'concrete_family':'siliceous',
            'dry_density_kg_m3':2200.})
        x=physical_inputs(c)
        self.assertTrue(x['natural_sand_confirmed'])
        self.assertEqual(x['cement_kg_m3'],500.)
        self.assertEqual(x['dry_density_kg_m3'],2200.)
        r=evaluate_annex_l(c)
        self.assertEqual(r['status'],'calculated_method_scope')
        self.assertNotAlmostEqual(r['F'],2.3903,places=3)
        self.assertEqual(r['provenance']['Wc'],'table_L2_exact')

    def test_fine_grained_is_derived_and_conflicting_data_blocks(self):
        from rc_fire.materials.normative import classify_fine_grained
        p=prepared_project()
        c=p['columns'][0]
        c['material_spec']['concrete']['fine_grained']=True
        self.assertIs(classify_fine_grained(c)['fine_grained'],False)
        self.assertEqual(evaluate_annex_l(c)['status'],'calculated_method_scope')
        # Actual 0% aggregate conflicts with explicitly selected granite for Ecm.
        update_annex_l_spec(p,'c1',{'coarse_aggregate_volume_pct':0.})
        r=evaluate_annex_l(c)
        self.assertEqual(r['status'],'blocked_input_or_scope')
        self.assertIn('0 % крупного',r['reason'])
        self.assertIsNone(r['F'])

    def test_L5_intermediate_RH_and_explicit_non_normative_L2_interpolation(self):
        p=prepared_project()
        update_annex_l_spec(p,'c1',{'relative_humidity_pct':55.})
        r=evaluate_annex_l(p['columns'][0])
        self.assertEqual(r['status'],'calculated_method_scope',r.get('reason'))
        self.assertEqual(r['provenance']['Wc'],'formula_L5_unit_interpretation')
        self.assertAlmostEqual(r['coefficients']['Wc_kg_kg'],.024619110145109882)
        self.assertFalse(r['moisture_method_qualified'])
        report=evaluate_column(p['columns'][0],grid=16)
        self.assertIn('ANNEX_L_MOISTURE_METHOD_UNQUALIFIED',
                      {x['code'] for x in report['normative_preflight']['issues']})
        update_annex_l_spec(p,'c1',{'moisture_mode':'linear_L2_exploratory'})
        other=evaluate_annex_l(p['columns'][0])
        self.assertEqual(other['status'],'calculated_method_scope')
        self.assertEqual(other['provenance']['Wc'],'linear_L2_engineering_not_normative')
        self.assertAlmostEqual(other['coefficients']['Wc_kg_kg'],.0292)
        self.assertNotAlmostEqual(other['coefficients']['Wc_kg_kg'],
                                  r['coefficients']['Wc_kg_kg'],places=3)
        self.assertFalse(other['moisture_method_qualified'])
        update_annex_l_spec(p,'c1',{'measured_Wc_kg_kg':.027,
            'moisture_measurement_source':'Измерено на образце'})
        measured=evaluate_annex_l(p['columns'][0])
        self.assertEqual(measured['status'],'calculated_method_scope')
        self.assertEqual(measured['provenance']['Wc'],'documented_measurement')
        self.assertTrue(measured['moisture_method_qualified'])

    def test_unknown_kind_is_not_fabricated_from_strength_or_density(self):
        from rc_fire.materials.normative import classify_fine_grained,resolve_materials
        p=new_project()
        c=p['columns'][0]
        c['material_spec']={'concrete':{'consistency':'S3_S5','curing':'natural',
                                'aggregate_family':'siliceous','modulus_aggregate':'other'},
                            'steel':{'product_type':'weldable_bar'}}
        c['thermal_spec']['dry_density_kg_m3']=2400.
        kind=classify_fine_grained(c)
        self.assertEqual(kind['status'],'unknown')
        self.assertIsNone(kind['fine_grained'])
        self.assertIsNone(resolve_materials(c)['concrete']['E_cm_GPa'])
        update_annex_l_spec(p,'c1',{'coarse_aggregate_volume_pct':0.})
        self.assertIs(classify_fine_grained(c)['fine_grained'],True)

    def test_material_Ecm_does_not_use_archived_wrong_fine_grained_switch(self):
        from rc_fire.materials.normative import resolve_materials
        p=prepared_project()
        c=p['columns'][0]
        c['material_spec']['concrete']['fine_grained']=True  # bad legacy flag
        m=resolve_materials(c)
        self.assertEqual(m['fine_grained_classification']['status'],'resolved')
        self.assertIs(m['fine_grained_classification']['fine_grained'],False)
        self.assertAlmostEqual(m['concrete']['E_cm_GPa'],33.)  # S3–S5 C30/37
        self.assertNotAlmostEqual(m['concrete']['E_cm_GPa'],33.*.85)

    def test_streamlit_no_fine_checkbox_and_moisture_method_available(self):
        from pathlib import Path
        try:from streamlit.testing.v1 import AppTest
        except ImportError:self.skipTest('Streamlit testing not installed')
        entry=Path(__file__).resolve().parents[1]/'streamlit_legacy_app.py'
        app=AppTest.from_file(str(entry),default_timeout=100).run()
        self.assertFalse(app.exception,list(app.exception))
        nav=next(r for r in app.radio if r.label=='Разделы')
        nav.set_value('c1').run()
        self.assertFalse(app.exception,list(app.exception))
        self.assertNotIn('Мелкозернистый бетон',[x.label for x in app.selectbox])
        self.assertIn('Метод определения влажности Wc',[x.label for x in app.selectbox])

    def test_export_roundtrip_and_preflight_no_foreign_F(self):
        p=prepared_project()
        q=load_json(export_json(p))
        c=q['columns'][0]
        self.assertEqual(c['annex_l_spec'],p['columns'][0]['annex_l_spec'])
        out=evaluate_column(c,grid=16)
        self.assertEqual(out['annex_l']['status'],'calculated_method_scope')
        codes={x['code'] for x in out['normative_preflight']['issues']}
        self.assertNotIn('ANNEX_L_NOT_EVALUATED',codes)
        self.assertEqual(out['normative_preflight']['status'],'NOT_QUALIFIED')
        self.assertFalse(out['normative_claim'])
        self.assertNotIn('spalling',out['provenance'])
        self.assertIn('СП 2.02.05-2026',out['provenance']['annex_l'])

    def test_explicit_belarus_save_migrates_and_clears_duplicate_legacy_card(self):
        p=prepared_project()
        c=p['columns'][0]
        c['spalling']={'method':'sp468','F':2.3903,
            'aggregate_pct':45.,'cement_kg_m3':500.}
        update_annex_l_spec(p,'c1',{'coarse_aggregate_volume_pct':47.})
        self.assertEqual(c['spalling'],{})
        self.assertAlmostEqual(c['annex_l_spec']['coarse_aggregate_volume_pct'],47.)
        self.assertNotIn('F',physical_inputs(c))

    def test_word_report_displays_Belarus_F_only(self):
        p=prepared_project()
        c=p['columns'][0]
        calc=evaluate_column(c,grid=16)
        d=Document()
        add_r056_diagnostics(d,c,calc)
        plain=' '.join(x.text for x in d.paragraphs)
        self.assertIn('приложение Л СП 2.02.05-2026',plain)
        self.assertNotIn('СП 468',plain)
        self.assertIn('F = ',plain)
        self.assertIn('R90',plain)


if __name__=='__main__':
    unittest.main()
