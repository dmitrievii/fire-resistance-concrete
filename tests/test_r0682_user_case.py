"""R0.6.8.2 regression for the user's 600x600 mm, R90 Streamlit case.

Checks:
- Ecm=41 GPa is the SAME in catalog and heated-section solver;
- positive default natural-sand scenario is provisional, never R90 proof;
- cement 100 kg/m3, RH 44% uses formula L.5 with explicit unit/scope caveats;
- explicit refusal of natural sand remains fail-closed;
- 90-min high-temperature table boundary is not bypassed.
"""
import math
import unittest
from pathlib import Path

from multicolumn_r05.project_model import (
    new_project, update_annex_l_spec, update_material_spec,
    update_thermal_spec, update_column, update_section,
)
from multicolumn_r05.project_calculator import evaluate_column
from rc_fire.materials import resolve_materials
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.mechanics.normative import (
    prepare_section, evaluate_column_mechanics, SectionMechanicsError,
    RESOLVED_MATERIAL_COUPLING,
)
from rc_fire.spalling import evaluate_annex_l, physical_inputs
from rc_fire.spalling.annex_l import DEFAULT_SAND_POLICY, moisture_wc


def sample(*, minutes=90.):
    project = new_project()
    update_material_spec(project, 'c1', {'concrete': {
        'aggregate_family':'siliceous', 'consistency':'S3_S5',
        'curing':'natural', 'modulus_aggregate':'gravel_granite_upto40'},
        'steel':{'product_type':'weldable_bar'}})
    update_thermal_spec(project, 'c1', {
        'concrete_family':'siliceous', 'dry_density_kg_m3':2200.,
        'exposed_faces':['left','right','bottom','top']})
    update_column(project, 'c1', {'fire_minutes':minutes})
    update_section(project, 'c1', 'center',
                   {'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
    update_annex_l_spec(project,'c1',{
        'coarse_aggregate_volume_pct':40.,
        'max_aggregate_mm':40.,
        'cement_kg_m3':100.,
        'water_cement_ratio':.4,
        'relative_humidity_pct':44.,
        'moisture_mode':'auto'})
    return project


class R0682SandEcmCouplingTests(unittest.TestCase):
    def test_user_example_catalog_matches_heated_section_Ecm(self):
        p=sample(minutes=10.)
        c=p['columns'][0]
        catalog=resolve_materials(c)
        self.assertEqual(catalog['status'],'resolved_for_property_lookup')
        self.assertAlmostEqual(catalog['concrete']['E_cm_GPa'],41.)
        self.assertEqual(RESOLVED_MATERIAL_COUPLING,
                         'R0.6.8.2-central-material-resolution-v1')
        thermal=evaluate_rectangular_column(c,grid=12)
        section=prepare_section(c,thermal,grid=12)
        self.assertAlmostEqual(section.strength_data['Ecm_ambient_GPa'],41.)
        self.assertNotEqual(section.strength_data['Ecm_ambient_GPa'],34.85)

    def test_90min_mechanics_does_not_falsely_block_Ecm(self):
        p=sample(minutes=90.)
        c=p['columns'][0]
        result=evaluate_column(c,grid=16)
        mech=result['mechanics_r063']
        self.assertNotIn('Ecm не определён', ' '.join(mech['issues']))
        self.assertEqual(mech['status'],'blocked')
        self.assertTrue(any('800' in x for x in mech['issues']),mech['issues'])
        self.assertFalse(result['normative_claim'])
        self.assertEqual(result['fire_resistance_status'],'not_demonstrated')
        self.assertEqual(result['load_summary']['ready'],1)

    def test_default_positive_sand_calculates_F_but_remains_unverified(self):
        p=sample()
        c=p['columns'][0]
        self.assertNotIn('natural_sand_confirmed',c['annex_l_spec'])
        inputs=physical_inputs(c)
        self.assertTrue(inputs['natural_sand_confirmed'])
        self.assertEqual(inputs['natural_sand_source'],'default_assumption_not_verified')
        self.assertEqual(DEFAULT_SAND_POLICY,
                         'R0.6.8.2-traceable-positive-default-v1')
        result=evaluate_annex_l(c)
        self.assertEqual(result['status'],'calculated_method_scope',result)
        self.assertTrue(math.isfinite(result['F']))
        self.assertFalse(result['natural_sand_verified'])
        self.assertEqual(result['natural_sand_verification_source'],
                         'default_assumption_not_verified')
        self.assertFalse(result['moisture_method_qualified'])
        out=evaluate_column(c,grid=16)
        codes={x['code'] for x in out['normative_preflight']['issues']}
        self.assertIn('ANNEX_L_NATURAL_SAND_UNVERIFIED',codes)
        self.assertIn('ANNEX_L_MOISTURE_METHOD_UNQUALIFIED',codes)
        self.assertFalse(out['normative_claim'])

    def test_real_user_cement_100_RH44_L5_is_not_blocked_by_table_range(self):
        wc,src,meta=moisture_wc(100,44,water_cement_ratio=.4)
        self.assertEqual(src,'formula_L5_unit_interpretation')
        self.assertAlmostEqual(wc,.004408798338148611)
        self.assertTrue(meta['outside_table_L2_domain'])
        self.assertTrue(meta['interpretation_requires_review'])
        out=evaluate_annex_l(sample()['columns'][0])
        self.assertEqual(out['status'],'calculated_method_scope',out)
        self.assertEqual(out['coefficients']['Wc_kg_kg'],wc)
        self.assertTrue(out['provenance']['Wc_details']['outside_table_L2_domain'])

    def test_explicit_no_sand_blocks_instead_of_default_overriding(self):
        p=sample()
        update_annex_l_spec(p,'c1',{'natural_sand_confirmed':False})
        result=evaluate_annex_l(p['columns'][0])
        self.assertEqual(result['status'],'blocked_input_or_scope')
        self.assertIn('природного песка',result['reason'])
        self.assertIsNone(result['F'])

    def test_user_confirmed_sand_clears_default_warning_only(self):
        p=sample()
        update_annex_l_spec(p,'c1',{'natural_sand_confirmed':True})
        r=evaluate_column(p['columns'][0],grid=16)
        self.assertTrue(r['annex_l']['natural_sand_verified'])
        codes={x['code'] for x in r['normative_preflight']['issues']}
        self.assertNotIn('ANNEX_L_NATURAL_SAND_UNVERIFIED',codes)
        self.assertIn('ANNEX_L_MOISTURE_METHOD_UNQUALIFIED',codes)
        self.assertFalse(r['normative_claim'])

    def test_streamlit_checkbox_checked_by_default_without_silent_confirmation(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest('Streamlit testing dependency unavailable')
        path=Path(__file__).resolve().parents[1]/'streamlit_app.py'
        app=AppTest.from_file(str(path),default_timeout=120).run()
        self.assertFalse(app.exception,list(app.exception))
        next(r for r in app.radio if r.label=='Разделы').set_value('c1').run()
        self.assertFalse(app.exception,list(app.exception))
        checks=[x for x in app.checkbox
                if x.label.startswith('В составе заполнителя действительно')]
        self.assertEqual(len(checks),1)
        self.assertTrue(checks[0].value)
        self.assertNotIn('natural_sand_confirmed',
                         app.session_state['project']['columns'][0]['annex_l_spec'])


if __name__=='__main__':
    unittest.main()
