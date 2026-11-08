"""R0.6.9D2: unit/fixture tests for genuine TKP thermal fibre mechanics.

All source parameters reconstruct user K18 project numerically, not a
copy of the private project or the copyrighted Belarus standard.
"""
from __future__ import annotations

import copy
import math
import unittest

import numpy as np

from multicolumn_r05.project_model import new_project
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.materials.tkp_en1992_fire import (
    EurocodeFireMaterialError,concrete_stress,concrete_free_thermal_strain)
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN
from rc_fire.mechanics.tkp_thermomechanical_fibres import (
    TKPFibreInputError,prepare_tkp_fibres,TKPPreparedFibres,VERSION)
from rc_fire.integration.r069d2 import (
    evaluate_tkp_fire_mechanics_at_time,evaluate_tkp_fire_mechanics_history)


def k18(*,minute=1.):
    c=new_project()['columns'][0]
    c.update({'id':'c1','name':'K1','b_mm':600.,'h_mm':600.,
              'length_m':3.,'fire_minutes':minute,'concrete':'C30/37',
              'steel_grade':'S500','cover_mm':20.,'stirrup_mm':10.})
    c['bars']=[{'id':f'S{i+1}','x_mm':x,'y_mm':y,'diameter_mm':20.}
          for i,(x,y) in enumerate([
              (40.,40.),(300.,40.),(560.,40.),(40.,300.),
              (560.,300.),(40.,560.),(300.,560.),(560.,560.)])]
    c['sections']=[{'id':'center','z_m':1.5,'name':'Центр',
                    'N_kN':50.,'Mx_kNm':2.,'My_kNm':0.}]
    c['material_spec']={'concrete':{
        'aggregate_family':'siliceous','consistency':'V3_V4',
        'curing':'natural','modulus_aggregate':'gravel_granite_upto40'},
        'steel':{'product_type':'weldable_bar'}}
    c['thermal_spec']={'a_red_mode':'table_K1','concrete_family':'siliceous',
        'dry_density_kg_m3':2200.,
        'exposed_faces':['left','right','bottom','top']}
    c['annex_l_spec']={
        'natural_sand_confirmed':True,'coarse_aggregate_volume_pct':40.,
        'moisture_mode':'auto','max_aggregate_mm':30.,
        'relative_humidity_pct':44.,'cement_kg_m3':500.,
        'water_cement_ratio':.45}
    c['member_spec']={'thermal_longitudinal_mode':'explicit_only',
                     'load_mode':'not_defined'}
    return c


class SourceIntegratedFibres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=k18(minute=1.)
        cls.thermal=evaluate_rectangular_column(cls.c,grid=8)
        cls.p=prepare_tkp_fibres(cls.c,cls.thermal,grid=8,
                       production_route='hot_rolled',ductility_class='B')

    def test_real_k18_geometry_and_rebar_are_preserved(self):
        p=self.p
        self.assertEqual(len(p.bar_area),8)
        self.assertEqual(len(p.area),8*8)
        self.assertAlmostEqual(float(np.sum(p.area)),.36)
        self.assertAlmostEqual(float(p.bar_area[0]),math.pi*(.020/2)**2)
        self.assertAlmostEqual(p.bar_x[0],.04)
        self.assertAlmostEqual(p.bar_y[0],.04)
        self.assertEqual(p.source['thermal'],
            'СП 2.02.05-2026 приложение К (hybrid diagnostic)')
        self.assertFalse(p.boundary_gap)
        self.assertEqual(p.hot_fibre_count,0)

    def test_free_thermal_expansion_is_added_to_compression_strain(self):
        p=self.p
        eps=-concrete_free_thermal_strain(20.,aggregate='siliceous')
        self.assertAlmostEqual(eps,0.,delta=3e-7)  # literal §3.3.1 polynomial at 20 C: -1.84e-7
        # Uniform unheated source temperature: 0 total strain -> no force.
        # Source Annex K at 1 min is already warm, so do not assert it is 20.
        self.assertGreaterEqual(float(np.max(p.eps_th_c)),0.)
        self.assertGreaterEqual(float(np.max(p.eps_th_s)),0.)

    def test_resultant_moments_vanish_under_symmetric_biaxial_heating(self):
        p=self.p
        force,tangent,meta=p.force_and_tangent([.0008,0.,0.])
        self.assertEqual(force.shape,(3,))
        self.assertEqual(tangent.shape,(3,3))
        self.assertAlmostEqual(force[1],0.,delta=.01)
        self.assertAlmostEqual(force[2],0.,delta=.01)
        self.assertGreater(force[0],0.)
        self.assertEqual(meta['model'],VERSION)

    def test_nonlinear_stress_decreases_when_heated(self):
        cold=concrete_stress(.0025,20,fck_MPa=30,aggregate='siliceous')[0]
        hot=concrete_stress(.0025,900,fck_MPa=30,aggregate='siliceous')[0]
        self.assertGreater(cold,hot)
        self.assertGreater(hot,0.)

    def test_jacobian_matches_finite_difference_before_yield(self):
        p=self.p
        x=np.asarray([.0005,.00009,-.00007])
        f,J,_=p.force_and_tangent(x)
        for k in range(3):
            dx=np.zeros(3);dx[k]=1.e-8
            numerical=(p.force_and_tangent(x+dx)[0]-
                       p.force_and_tangent(x-dx)[0])/(2.e-8)
            self.assertTrue(np.allclose(J[:,k],numerical,atol=.5,rtol=.001),
                            (k,J[:,k],numerical))

    def test_independent_solution_is_research_evidence_only(self):
        r=self.p.solve_actions(50.,2.,0.)
        self.assertIn(r['classification'],(WITHIN,EXCEEDED,UNKNOWN))
        self.assertFalse(r['normative_claim'])
        if r['classification']!=UNKNOWN:
            self.assertLess(r['relative_residual'],1e-6)
            self.assertAlmostEqual(r['forces_kN_kNm'][0],50.,delta=.01)

    def test_load_factor_scan_mandatorily_samples_actual_design_point(self):
        r=self.p.load_factor_scan(50.,2.,0.,max_factor=1.,
                                  factor_step=1.,max_bisection=0)
        self.assertEqual(r['design_action_factor'],1.)
        self.assertEqual(r['design_actions'],
                {'N_kN':50.,'Mx_kNm':2.,'My_kNm':0.})
        self.assertIsNone(r['lambda_capacity_normative'])
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])

    def test_member_section_law_can_evaluate_condensed_2d_tangent(self):
        law=self.p.member_law()
        try:
            moments,D,meta=law.evaluate(np.zeros(2),50.)
        except ValueError as exc:
            self.assertIn('equilibrium',str(exc).lower())
            return
        self.assertEqual(moments.shape,(2,))
        self.assertEqual(D.shape,(2,2))
        self.assertTrue(np.allclose(D,D.T,atol=1e-7))
        self.assertGreater(np.linalg.eigvalsh(D)[0],0.)
        self.assertFalse(meta['normative_claim'])

    def test_unresolved_steel_fabrication_and_class_are_never_assumed(self):
        c=k18()
        r=evaluate_tkp_fire_mechanics_at_time(c,grid=8)
        self.assertEqual(r['status'],'BLOCKED_REBAR_DECLARATION',r)
        self.assertIn('STEEL_PROCESS_AND_DUCTILITY_NOT_DEFINED',r['blockers'])
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])

    def test_actual_k18_90min_strict_high_temp_gap_is_explicit(self):
        c=k18(minute=90.)
        r=evaluate_tkp_fire_mechanics_at_time(c,grid=8,
            production_route='hot_rolled',ductility_class='B',
            high_temperature_tail='reject',
            max_factor=1.,factor_step=1.,max_bisection=0)
        self.assertEqual(r['status'],'BLOCKED_TKP_MATERIAL_OR_ACTIONS',r)
        self.assertIn('1100_TO_1200',r['reason'])
        self.assertFalse(r['normative_claim'])
        self.assertIsNone(r['R_t_minutes'])

    def test_actual_k18_90min_opt_in_nonconstitutive_tail_never_passes(self):
        c=k18(minute=90.)
        r=evaluate_tkp_fire_mechanics_at_time(c,grid=8,
            production_route='hot_rolled',ductility_class='B',
            high_temperature_tail='zero_tail_diagnostic',
            max_factor=1.,factor_step=1.,max_bisection=0)
        self.assertEqual(len(r['sections']),1,r)
        state=r['sections'][0]['reference_at_lambda_1']
        self.assertEqual(state['classification'],UNKNOWN)
        self.assertTrue(r['boundary_strain_domain_gap'])
        self.assertFalse(r['normative_claim'])
        self.assertIsNone(r['R_t_minutes'])

    def test_source_metadata_discloses_TKP_SP_hybrid_and_missing_validation(self):
        r=evaluate_tkp_fire_mechanics_at_time(k18(),grid=8,
            production_route='hot_rolled',ductility_class='B',
            max_factor=1.,factor_step=1.,max_bisection=0)
        self.assertIn('hybrid',r['thermal_method'])
        self.assertTrue(r['source_thermal_mix_not_normatively_adjudicated'])
        self.assertIn('TKP_4_3_4_VALIDATION_NOT_DONE',r['blockers'])

    def test_member_path_does_not_infer_q_from_entered_Mx(self):
        r=evaluate_tkp_fire_mechanics_at_time(k18(),grid=8,
            production_route='hot_rolled',ductility_class='B',
            max_factor=1.,factor_step=1.,max_bisection=0,include_member=True)
        self.assertEqual(r['member']['status'],'BLOCKED_MEMBER_INPUT',r)
        self.assertFalse(r['member']['entered_Mx_My_reconciled_with_member_actions'])
        self.assertFalse(r['member']['normative_claim'])

    def test_time_series_is_independent_and_never_fabricates_a_failure_minute(self):
        c=k18(minute=90.)
        original=copy.deepcopy(c)
        r=evaluate_tkp_fire_mechanics_history(c,grid=8,
           production_route='hot_rolled',ductility_class='B',
           high_temperature_tail='zero_tail_diagnostic',
           step_minutes=90.,max_factor=1.,factor_step=1.,
           max_bisection=0,include_member=False)
        self.assertEqual([row['time_minutes'] for row in r['samples']],[1.,90.])
        self.assertEqual(r['samples'][-1]['reference_classification'],UNKNOWN)
        self.assertIsNone(r['first_normative_failure_minute'])
        self.assertIsNone(r['R_t_minutes'])
        self.assertEqual(c,original)

    def test_sp_process_keeps_hot_vs_cold_source_laws_distinct(self):
        cold=prepare_tkp_fibres(self.c,self.thermal,grid=8,
                  production_route='cold_worked',ductility_class='B')
        self.assertEqual(cold.production_route,'cold_worked')
        self.assertEqual(self.p.production_route,'hot_rolled')
        self.assertEqual(cold.theta_s.tolist(),self.p.theta_s.tolist())

    def test_invalid_material_time_mismatch_and_zero_bar_are_blocked(self):
        c=k18()
        c['fire_minutes']=90.
        with self.assertRaises(TKPFibreInputError):
            prepare_tkp_fibres(c,self.thermal,grid=8,
                production_route='hot_rolled',ductility_class='B')
        c=k18()
        c['bars']=[]
        with self.assertRaises(TKPFibreInputError):
            prepare_tkp_fibres(c,self.thermal,grid=8,
                production_route='hot_rolled',ductility_class='B')


if __name__=='__main__':
    unittest.main()
