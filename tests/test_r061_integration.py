"""R0.6.1 backward-compatible project/catalog integration."""
import unittest
from rc_fire.materials import resolve_materials
from multicolumn_r05.project_model import (new_project,update_material_spec,export_json,load_json,to_engine_input,update_section)
from multicolumn_r05.project_calculator import evaluate_column

class R061IntegrationTests(unittest.TestCase):
    def fill(self,project):
        update_material_spec(project,'c1',{'concrete':{
            'aggregate_family':'siliceous','consistency':'S3_S5',
            'curing':'natural','modulus_aggregate':'gravel_granite_upto40',
            'fine_grained':False},'steel':{'product_type':'weldable_bar'}})

    def test_default_keeps_unknown_properties_unresolved(self):
        p=new_project(2)
        a=evaluate_column(p['columns'][0])
        self.assertEqual(a['material_preflight']['status'],'incomplete')
        self.assertFalse(a['normative_claim'])
        self.assertIsNone(a['material_preflight']['concrete']['E_cm_GPa'])

    def test_material_editor_project_json_and_engine_numeric_link(self):
        p=new_project(1)
        self.fill(p)
        m=resolve_materials(p['columns'][0])
        self.assertEqual(m['status'],'resolved_for_property_lookup')
        self.assertAlmostEqual(m['concrete']['E_cm_GPa'],33)
        update_section(p,'c1','center',{'N_kN':500,'Mx_kNm':20,'My_kNm':15})
        model=to_engine_input(p['columns'][0],[p['columns'][0]['sections'][0]])
        self.assertAlmostEqual(model['material']['E_cm_GPa'],33)
        self.assertEqual(model['material_resolution']['E_cm_source'],'SP 5.03.01-2020 table 6.3')
        copied=load_json(export_json(p))
        self.assertEqual(copied['columns'][0]['material_spec']['concrete']['consistency'],'S3_S5')
        c=evaluate_column(p['columns'][0])
        self.assertFalse(c['normative_claim'])
        self.assertFalse(c['material_preflight']['numeric_engine_qualified'])

    def test_legacy_json_preserved_and_not_certified(self):
        p=new_project()
        p['columns'][0].pop('material_spec',None)
        copied=load_json(export_json(p))
        self.assertEqual(evaluate_column(copied['columns'][0])['material_preflight']['status'],'incomplete')

    def test_unqualified_data_cannot_trigger_normative_pass(self):
        p=new_project()
        self.fill(p)
        p['columns'][0]['material_spec']['concrete']['aggregate_family']='calcareous'
        c=evaluate_column(p['columns'][0])
        self.assertFalse(c['normative_claim'])
        self.assertEqual(c['fire_resistance_status'],'not_demonstrated')

if __name__=='__main__':unittest.main()