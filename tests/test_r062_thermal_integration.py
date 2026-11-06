"""Live-code integration tests for R0.6.2 with the R0.5 multi-column facade."""
import unittest

from multicolumn_r05.project_model import (new_project, update_thermal_spec,
        export_json,load_json,to_engine_input)
from multicolumn_r05.project_calculator import evaluate_column
from rc_fire.thermal import evaluate_rectangular_column


class ThermalProjectIntegrationTests(unittest.TestCase):
    def test_legacy_project_stays_diagnostic_no_fabricated_density(self):
        c=new_project()['columns'][0]
        self.assertEqual(evaluate_rectangular_column(c)['status'],'not_evaluated')
        out=evaluate_column(c,grid=48)
        self.assertFalse(out['normative_claim'])
        self.assertEqual(out['thermal_normative']['status'],'not_evaluated')

    def test_project_persistence_and_rebar_temperatures(self):
        p=new_project()
        update_thermal_spec(p,'c1',{'concrete_family':'siliceous',
            'dry_density_kg_m3':2400.,'exposed_faces':['left','right','bottom','top']})
        c=p['columns'][0]
        x=evaluate_rectangular_column(c,20)
        self.assertEqual(x['status'],'evaluated')
        self.assertEqual(len(x['reinforcement']),len(c['bars']))
        restored=load_json(export_json(p))
        self.assertEqual(restored['columns'][0]['thermal_spec']['dry_density_kg_m3'],2400.)
        self.assertEqual(restored['columns'][0]['thermal_spec']['exposed_faces'],['left','right','bottom','top'])

    def test_normative_thermal_parameters_feed_diagnostic_only_when_four_face(self):
        p=new_project();c=p['columns'][0]
        update_thermal_spec(p,'c1',{'concrete_family':'calcareous',
            'dry_density_kg_m3':2400.,'exposed_faces':['left','right','bottom','top']})
        for s in c['sections']:
            s.update(N_kN=120.,Mx_kNm=10.,My_kNm=5.)
        d=to_engine_input(c,c['sections'],48)
        self.assertAlmostEqual(d['fire']['a_red_m2_h'],.00116)
        self.assertAlmostEqual(d['fire']['critical_concrete_C'],600.)
        self.assertEqual(d['thermal_resolution']['source'],'SP_2026_Annex_K')
        self.assertFalse(d['thermal_resolution']['normative_engine_qualified'])
        r=evaluate_column(c,grid=48)
        self.assertEqual(r['thermal_normative']['status'],'evaluated')
        self.assertFalse(r['normative_claim'])

    def test_partial_fire_exposure_blocks_legacy_mechanical_result(self):
        p=new_project();c=p['columns'][0]
        update_thermal_spec(p,'c1',{'concrete_family':'siliceous','dry_density_kg_m3':2400.,
                                   'exposed_faces':['left','bottom']})
        for s in c['sections']:s.update(N_kN=150.,Mx_kNm=5.,My_kNm=2.)
        r=evaluate_column(c,48)
        self.assertEqual(r['thermal_normative']['formula'],'К.8')
        self.assertNotEqual(r['status'],'calculated')
        self.assertFalse(r['results'])
        self.assertFalse(r['normative_claim'])

    def test_invalid_density_does_not_get_legacy_replacement(self):
        p=new_project();c=p['columns'][0]
        with self.assertRaises(ValueError):
            update_thermal_spec(p,'c1',{'dry_density_kg_m3':2500.})

    def test_default_diagnostic_compared_with_k18_reference_k10(self):
        p=new_project();c=p['columns'][0]
        update_thermal_spec(p,'c1',{'concrete_family':'siliceous','dry_density_kg_m3':2400.})
        c['cover_mm']=20.;c['stirrup_mm']=10.;c['bar_diameter_mm']=20.
        t=evaluate_rectangular_column(c)
        self.assertEqual(t['formula'],'К.10')
        self.assertEqual(t['critical_temperature_C'],500.)

if __name__=='__main__':unittest.main()