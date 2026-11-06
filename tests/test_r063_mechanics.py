"""R0.6.3 numerical and normative-contract regression tests."""
import copy
import math
import unittest

import numpy as np

from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.mechanics import (alpha_cc, design_strengths, concrete_parabolic_linear,
    steel_bilinear, prepare_section, solve_load, evaluate_column_mechanics,
    SectionMechanicsError)


def sample_column():
    locations=[(40,40),(300,40),(560,40),(40,300),(560,300),
               (40,560),(300,560),(560,560)]
    return {
      'id':'c1','name':'K1','b_mm':600.,'h_mm':600.,'fire_minutes':0.,
      'steel_grade':'S500','concrete':'C30/37','bars':[
        {'id':f'S{i+1}','x_mm':x,'y_mm':y,'diameter_mm':20.}
        for i,(x,y) in enumerate(locations)],
      'material_spec':{'concrete':{'aggregate_family':'siliceous',
          'consistency':'S3_S5','curing':'natural',
          'modulus_aggregate':'gravel_granite_upto40','fine_grained':False},
           'steel':{'product_type':'weldable_bar'}},
      'thermal_spec':{'concrete_family':'siliceous','dry_density_kg_m3':2400.,
          'exposed_faces':['left','right','bottom','top'],
          'a_red_mode':'table_K1'},
      'sections':[{'id':'bottom','N_kN':500.,'Mx_kNm':25.,'My_kNm':-20.},
                  {'id':'top','N_kN':300.,'Mx_kNm':10.,'My_kNm':5.}],
    }


class SectionMechanicsTests(unittest.TestCase):
    def pre(self,c=None,g=20,policy='reject'):
        c=c or sample_column()
        t=evaluate_rectangular_column(c,grid=20)
        return prepare_section(c,t,grid=g,above_800_policy=policy)

    def test_accidental_partial_factors_and_alpha_cc(self):
        f=design_strengths(30.,500.)
        self.assertEqual((f['gamma_c'],f['gamma_s']), (1.2,1.0))
        self.assertAlmostEqual(f['f_cd_MPa'],25.)
        self.assertEqual(f['f_yd_MPa'],500.)
        self.assertAlmostEqual(alpha_cc(80.),(40/80)**(1/3))

    def test_parabolic_linear_concrete_eq_6_17_6_18(self):
        strain=np.array([-.001,0,.001,.002,.003,.0035,.004])
        stress,tan=concrete_parabolic_linear(strain,25.,.002,.0035,2.)
        np.testing.assert_allclose(stress,[0,0,18.75,25,25,25,25])
        self.assertAlmostEqual(tan[2],12500.)
        self.assertEqual(tan[5],0)

    def test_bilinear_steel_plateau_eq_6_2_2_13(self):
        x=np.array([-.005,-.001,0.,.001,.005])
        stress,tan=steel_bilinear(x,500.,200000.)
        np.testing.assert_allclose(stress,[-500,-200,0,200,500])
        self.assertEqual(tan[1],200000.)
        self.assertEqual(tan[-1],0.)

    def test_uniform_compression_and_replaced_bar_concrete(self):
        p=self.pre()
        e=np.array([.002,0.,0.])
        forces,J,meta=p.response(e)
        abar=sum(p.bar_area_m2)
        expected=1000*(25*p.b_m*p.h_m+(400-25)*abar)
        self.assertAlmostEqual(forces[0],expected,delta=2.)
        self.assertAlmostEqual(forces[1],0,delta=1e-7)
        self.assertAlmostEqual(forces[2],0,delta=1e-7)
        self.assertAlmostEqual(meta['max_concrete_compression'],.002)

    def test_biaxial_equilibrium_residual_and_strain_limit(self):
        p=self.pre()
        r=solve_load(p,500.,25.,-20.)
        self.assertEqual(r['status'],'equilibrium_within_strain_limits')
        self.assertTrue(r['equilibrium'])
        self.assertFalse(r['normative_claim'])
        self.assertFalse(r['fire_resistance_status']=='demonstrated')
        for k,target in [('N_kN',500.),('Mx_kNm',25.),('My_kNm',-20.)]:
            self.assertAlmostEqual(r['internal'][k],target,delta=1e-3)

    def test_2axis_sign_reversal(self):
        p=self.pre()
        plus=solve_load(p,600.,30.,20.)
        minus=solve_load(p,600.,-30.,-20.)
        self.assertTrue(plus['equilibrium'])
        self.assertTrue(minus['equilibrium'])
        self.assertAlmostEqual(plus['unknown_strains'][0],minus['unknown_strains'][0],delta=1e-6)
        self.assertAlmostEqual(plus['unknown_strains'][1],-minus['unknown_strains'][1],delta=1e-6)
        self.assertAlmostEqual(plus['unknown_strains'][2],-minus['unknown_strains'][2],delta=1e-6)

    def test_analytic_section_jacobian_against_finite_difference(self):
        p=self.pre()
        x=np.array([.0006,.00025,-.00015]);f,J,_=p.response(x)
        delta=1e-7
        for i in range(3):
            d=np.zeros(3);d[i]=delta
            fd=(p.response(x+d)[0]-p.response(x-d)[0])/(2*delta)
            np.testing.assert_allclose(J[:,i],fd,rtol=5e-5,atol=1e-2)

    def test_thermally_weakened_section_response(self):
        c=sample_column();p0=self.pre(c)
        f0,_,_=p0.response([.001,0.,0.])
        c['fire_minutes']=10.
        p10=self.pre(c)
        f10,_,_=p10.response([.001,0.,0.])
        self.assertLess(f10[0],f0[0])
        self.assertGreater(max(p10.concrete_temperature_C),20)
        # R0.6.3A: reject the unqualified 30-minute hot boundary
        # even if fibre centroids are colder than 800 °C.
        c['fire_minutes']=30.
        t30=evaluate_rectangular_column(c,grid=20)
        with self.assertRaisesRegex(SectionMechanicsError,'800'):
            prepare_section(c,t30,grid=20)

    def test_section_grid_refinement(self):
        p24=self.pre(g=24);p48=self.pre(g=48)
        f24=p24.response([.001,.0002,-.0001])[0]
        f48=p48.response([.001,.0002,-.0001])[0]
        np.testing.assert_allclose(f24,f48,rtol=.008,atol=4.)

    def test_out_of_table_temperature_rejected_no_extrapolation(self):
        c=sample_column();c['fire_minutes']=90.
        t=evaluate_rectangular_column(c,grid=20)
        with self.assertRaisesRegex(SectionMechanicsError,'800'):
            prepare_section(c,t,grid=20)
        result=evaluate_column_mechanics(c,t,grid=20)
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(result['normative_claim'])

    def test_explicit_cutoff_option_keeps_diagnostic_provenance(self):
        c=sample_column();c['fire_minutes']=90.
        t=evaluate_rectangular_column(c,grid=20)
        p=prepare_section(c,t,grid=20,above_800_policy='zero_strength_diagnostic')
        self.assertGreater(p.out_of_table_concrete_cells,0)
        self.assertTrue(any('норматив' in s.lower() for s in p.issues))
        z=evaluate_column_mechanics(c,t,grid=20,above_800_policy='zero_strength_diagnostic')
        self.assertFalse(z['normative_claim'])
        self.assertIn('diagnostic',z['status'])

    def test_missing_concrete_properties_fail_closed(self):
        c=sample_column();c['material_spec']['concrete']={}
        result=evaluate_column_mechanics(c,grid=20)
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(result['normative_claim'])

    def test_high_strength_missing_beta_fails_closed(self):
        c=sample_column();c['concrete']='C55/67'
        c['material_spec']['concrete']['consistency']='S1_S2'
        z=evaluate_column_mechanics(c,grid=20)
        self.assertEqual(z['status'],'blocked')
        self.assertIn('beta',z['issues'][0])

    def test_nonconvergence_does_not_mean_positive_or_negative_certification(self):
        p=self.pre()
        r=solve_load(p,90000,0,0)
        self.assertFalse(r['equilibrium'])
        self.assertFalse(r['normative_claim'])
        self.assertIn('not_converged',r['status'])

    def test_missing_section_loads_do_not_become_zeros(self):
        c=sample_column();c['sections'][0]['N_kN']=None
        result=evaluate_column_mechanics(c,grid=20)
        self.assertEqual(result['sections']['bottom']['status'],'loads_missing')
        self.assertIn('top',result['sections'])
        self.assertFalse(result['normative_claim'])

    def test_maps_match_stress_and_bars(self):
        p=self.pre(g=20)
        r=solve_load(p,500,25,-20,with_maps=True)
        m=r['details']['map']
        self.assertEqual(len(m['concrete_stress_MPa']),20)
        self.assertEqual(len(m['steel_stress_MPa']),8)
        self.assertEqual(m['grid'],20)


if __name__=='__main__': unittest.main()