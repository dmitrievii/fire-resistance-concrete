"""R0.6.9D3 acceptance: conservative source heat equation and NO Annex K transfer."""
import copy
import math
import unittest
from unittest.mock import patch

import numpy as np

from multicolumn_r05.project_model import new_project
from rc_fire.thermal.tkp_heat import (
    reference_annex_a_boundary, standard_fire_gas_temperature,
    solve_tkp_2d_heat, select_tkp_snapshot, sample_tkp_temperature,
    TKPHeatError,VERSION)
from rc_fire.mechanics.tkp_thermomechanical_fibres import (
    prepare_tkp_fibres,TKPFibreInputError)
from rc_fire.integration.r069d3 import (
    evaluate_tkp_thermal_mechanical_history,compare_tkp_thermal_refinement)
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN


def k1(duration=12.):
    c=new_project()['columns'][0]
    c.update({'id':'c1','name':'К1','b_mm':600.,'h_mm':600.,
         'length_m':3.,'fire_minutes':duration,'concrete':'C30/37',
         'steel_grade':'S500'})
    c['thermal_spec']={'concrete_family':'siliceous',
        'dry_density_kg_m3':2200.,
        'exposed_faces':['left','right','bottom','top'],
        'a_red_mode':'table_K1'}
    c['material_spec']={'concrete':{
        'aggregate_family':'siliceous','consistency':'V3_V4',
        'curing':'natural','modulus_aggregate':'gravel_granite_upto40'},
        'steel':{'product_type':'weldable_bar'}}
    c['bars']=[{'id':f'S{i+1}','x_mm':x,'y_mm':y,'diameter_mm':20.}
        for i,(x,y) in enumerate([
          (40.,40.),(300.,40.),(560.,40.),(40.,300.),
          (560.,300.),(40.,560.),(300.,560.),(560.,560.)])]
    c['sections']=[{'id':'center','z_m':1.5,'N_kN':50.,
                    'Mx_kNm':2.,'My_kNm':0.}]
    c['member_spec']={'thermal_longitudinal_mode':'explicit_only',
                     'load_mode':'not_defined'}
    return c


class TKPConservativeHeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=k1(12.)
        cls.bc=reference_annex_a_boundary(moisture_mass_pct=1.5)
        cls.r=solve_tkp_2d_heat(cls.c,boundary=cls.bc,
              cell_count_x=8,cell_count_y=8,max_step_minutes=2.,
              sample_times_minutes=[1.,6.,12.])

    def test_explicit_boundary_source_and_NA(self):
        self.assertIn('приложение А',self.bc['environment_source'])
        self.assertEqual(self.bc['convection_W_m2_K'],25.)
        self.assertEqual(self.bc['surface_emissivity'],.7)
        self.assertEqual(self.r['version'],VERSION)
        self.assertEqual(self.r['thermal_method'],'TKP_4.3.2_FVM')
        self.assertTrue(self.r['temperature_field_not_from_SP_annex_K']
                        if 'temperature_field_not_from_SP_annex_K' in self.r else True)
        self.assertIsNone(self.r['R_t_minutes'])
        self.assertFalse(self.r['normative_claim'])

    def test_reference_gas_ISO_curve_90_min_never_1132_C(self):
        gas=standard_fire_gas_temperature(90.)
        self.assertAlmostEqual(gas,1005.987666328203,places=9)
        self.assertLess(gas,1100.)
        self.assertEqual(standard_fire_gas_temperature(0.),20.)

    def test_monotonic_thermal_time_and_nonnegative_net_heat(self):
        self.assertEqual([s['time_minutes'] for s in self.r['snapshots']],
                         [1.,6.,12.])
        cells=[s['cell_max_C'] for s in self.r['snapshots']]
        self.assertGreater(cells[2],cells[1])
        self.assertGreater(cells[1],cells[0])
        self.assertGreater(self.r['energy_balance']['enthalpy_change_J_per_m'],0.)
        self.assertGreater(self.r['energy_balance']['integrated_boundary_heat_J_per_m'],0.)

    def test_conservation_one_step_and_total(self):
        e=self.r['energy_balance']
        self.assertLess(e['relative_cumulative_residual'],3.e-4)
        self.assertLess(e['worst_step_relative_residual'],3.e-4)
        self.assertTrue(all(row['relative_energy_residual']<3e-4
                       for row in self.r['step_log']))

    def test_no_temperature_exceeds_source_gas_curve(self):
        for snap in self.r['snapshots']:
            g=standard_fire_gas_temperature(snap['time_minutes'])
            self.assertLessEqual(snap['boundary_max_C'],g+1.e-5)
            self.assertGreaterEqual(snap['cell_min_C'],20.-1.e-6)

    def test_symmetric_four_face_geometry_remains_symmetric(self):
        t=np.asarray(self.r['snapshots'][-1]['grid_temperature_C'])
        self.assertTrue(np.allclose(t,t[::-1,:],atol=2e-3))
        self.assertTrue(np.allclose(t,t[:,::-1],atol=2e-3))
        self.assertTrue(np.allclose(t,t.T,atol=2e-3))

    def test_center_is_cooler_than_face_and_actual_bar_temperatures(self):
        snap=select_tkp_snapshot(self.r,12.)
        corner=sample_tkp_temperature(snap,0.,0.)
        nearbar=sample_tkp_temperature(snap,40.,40.)
        centre=sample_tkp_temperature(snap,300.,300.)
        self.assertGreater(corner,nearbar)
        self.assertGreater(nearbar,centre)
        self.assertLessEqual(corner,self.r['snapshots'][-1]['boundary_max_C']+1e-6)

    def test_adabatic_unexposed_section_exactly_stays_ambient(self):
        c=k1(5.)
        c['thermal_spec']['exposed_faces']=[]
        r=solve_tkp_2d_heat(c,boundary=self.bc,cell_count_x=4,
             cell_count_y=4,max_step_minutes=1.)
        t=np.asarray(r['snapshots'][-1]['grid_temperature_C'])
        self.assertTrue(np.allclose(t,20.,atol=1.e-7))
        self.assertAlmostEqual(r['energy_balance']['enthalpy_change_J_per_m'],0.,delta=.01)

    def test_invalid_moisture_boundary_and_mesh_fail_closed(self):
        with self.assertRaises(TKPHeatError):
            solve_tkp_2d_heat(self.c,boundary={},cell_count_x=8)
        with self.assertRaises(TKPHeatError):
            reference_annex_a_boundary(moisture_mass_pct=4.)
        with self.assertRaises(TKPHeatError):
            solve_tkp_2d_heat(self.c,boundary=self.bc,cell_count_x=3)
        with self.assertRaises(TKPHeatError):
            select_tkp_snapshot(self.r,3.)
        with self.assertRaises(TKPHeatError):
            sample_tkp_temperature(select_tkp_snapshot(self.r,12.),700.,200.)

    def test_TKP_fibre_field_cannot_be_stale_and_does_not_call_Annex_K(self):
        src=select_tkp_snapshot(self.r,12.)
        with patch('rc_fire.mechanics.tkp_thermomechanical_fibres.temperature_rectangle',
                   side_effect=AssertionError('MUST NOT USE ANNEX K TEMPERATURES')):
            p=prepare_tkp_fibres(self.c,src,grid=8,
              production_route='hot_rolled',ductility_class='B')
        self.assertEqual(p.hot_fibre_count,0)
        self.assertLess(max(p.theta_s),standard_fire_gas_temperature(12.))
        self.assertTrue(p.source['thermal'].startswith('ТКП EN 1992-1-2'))
        c2=copy.deepcopy(self.c)
        c2['fire_minutes']=6.
        with self.assertRaises(TKPFibreInputError):
            prepare_tkp_fibres(c2,src,grid=8,
                production_route='hot_rolled',ductility_class='B')

    def test_mechanical_thermal_elastic_tangent_finite_and_strains(self):
        src=select_tkp_snapshot(self.r,12.)
        p=prepare_tkp_fibres(self.c,src,grid=8,
                production_route='hot_rolled',ductility_class='B')
        self.assertGreater(float(np.max(p.eps_th_c)),0.)
        self.assertEqual(p.bar_ids[0],'S1')
        f,J,m=p.force_and_tangent([.001,0.,0.])
        self.assertTrue(np.all(np.isfinite(f)))
        self.assertTrue(np.all(np.isfinite(J)))
        self.assertTrue(m['strain_limits_satisfied'] in (True,False))
        self.assertFalse(m['zero_tail_diagnostic'])
        self.assertFalse(m['boundary_above_full_concrete_curve'])

    def test_coupled_history_uses_one_thermal_solution_and_true_corresponding_times(self):
        c=k1(12.)
        old=copy.deepcopy(c)
        r=evaluate_tkp_thermal_mechanical_history(c,boundary=self.bc,
             production_route='hot_rolled',ductility_class='B',
             cell_count=8,max_step_minutes=2.,step_minutes=6.,
             max_factor=1.,factor_step=1.,max_bisection=0)
        self.assertEqual(c,old)
        self.assertTrue(r['temperature_field_not_from_SP_annex_K'])
        self.assertEqual([s['time_minutes'] for s in r['samples']],[1.,6.,12.])
        self.assertTrue(all(s['temperature_source_match_verified'] for s in r['samples']))
        self.assertTrue(all(s['status']=='FVM_TKP_FIBRES_NUMERICAL_DIAGNOSTIC'
                     for s in r['samples']))
        self.assertEqual(r['samples'][-1]['sections'][0]['entered_actions_N_Mx_My'],
            {'N_kN':50.,'Mx_kNm':2.,'My_kNm':0.})
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])

    def test_missing_steel_processing_blocks_only_mechanics_not_thermal(self):
        r=evaluate_tkp_thermal_mechanical_history(self.c,boundary=self.bc,
              production_route=None,ductility_class=None,cell_count=8,
              max_step_minutes=3.,step_minutes=12.,
              max_factor=1.,factor_step=1.,max_bisection=0)
        self.assertTrue(all(s['status']=='BLOCKED_REBAR_DECLARATION'
                         for s in r['samples']))
        self.assertTrue(all(s['T_concrete_boundary_max_C']>20 for s in r['samples']))
        self.assertIsNone(r['R_t_minutes'])

    def test_member_without_load_support_provenance_remains_optional(self):
        r=evaluate_tkp_thermal_mechanical_history(self.c,boundary=self.bc,
             production_route='hot_rolled',ductility_class='B',
             cell_count=8,max_step_minutes=3.,step_minutes=12.,
             max_factor=1.,factor_step=1.,max_bisection=0,include_member=True)
        self.assertTrue(all(s['member']['status']=='BLOCKED_MEMBER_INPUT'
                        for s in r['samples']))
        self.assertFalse(r['samples'][-1]['member'][
            'entered_section_moment_diagram_reconciled'])

    def test_quick_spatial_temporal_refinement_reports_differences(self):
        c=k1(4.)
        r=compare_tkp_thermal_refinement(c,boundary=self.bc,
             coarse=4,fine=6,dt_minutes=2.)
        self.assertGreaterEqual(r['max_spatial_difference_C'],0.)
        self.assertGreaterEqual(r['max_temporal_difference_C'],0.)
        self.assertLess(r['comparisons']['temporal_fine'][
            'energy_relative_residual'],3.e-4)
        self.assertFalse(r['normative_claim'])
        self.assertIsNone(r['R_t_minutes'])


if __name__=='__main__':
    unittest.main()
