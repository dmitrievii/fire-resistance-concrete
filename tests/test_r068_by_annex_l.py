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
        with self.assertRaises(AnnexLError):
            moisture_wc(500.,55.)

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

    def test_fine_grained_and_coarse_mix_conflict_blocks(self):
        p=prepared_project()
        p['columns'][0]['material_spec']['concrete']['fine_grained']=True
        r=evaluate_annex_l(p['columns'][0])
        self.assertEqual(r['status'],'blocked_input_or_scope')
        self.assertIn('Мелкозернистый',r['reason'])
        self.assertIsNone(r['F'])

    def test_annex_L_uses_only_source_supported_moisture(self):
        p=prepared_project()
        update_annex_l_spec(p,'c1',{'relative_humidity_pct':55.})
        r=evaluate_annex_l(p['columns'][0])
        self.assertEqual(r['status'],'blocked_input_or_scope')
        self.assertIn('Л.2',r['reason'])
        update_annex_l_spec(p,'c1',{'measured_Wc_kg_kg':.027,
            'moisture_measurement_source':'Измерено на образце'})
        r=evaluate_annex_l(p['columns'][0])
        self.assertEqual(r['status'],'calculated_method_scope')
        self.assertEqual(r['provenance']['Wc'],'documented_measurement')

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
