"""Independent R0.6.4C numerical/qualification tests.

Designed to catch false approval on incomplete material/ULS evidence.
"""
import copy
import unittest
import numpy as np

from rc_fire.mechanics.normative import prepare_section
from rc_fire.mechanics.fire_strength import select_fire_reference_strength,LITERAL,HISTORIC
from rc_fire.member.coupled import (FiberSectionLaw, LinearSectionLaw,
    linear_laws_at_gauss,solve_coupled_beam, EndSupport,CoupledMemberError)
from rc_fire.member.uls import audit_heated_member_uls,_node_curvature
from rc_fire.member.full_uls import run_heated_member_uls_evidence
from rc_fire.thermal import evaluate_rectangular_column
from test_r063_mechanics import sample_column


class BadLaw:
    def __init__(self,e=0.,fail=False):self.e=e;self.fail=fail
    def evaluate(self,kappa,N):
        if self.fail:raise CoupledMemberError('independent node-law failed')
        return np.zeros(2),np.eye(2)*3000.,{
          'model':'reference_affine_diagnostic','source':'test-only',
          'max_concrete_compressive_strain':self.e,'max_steel_tensile_strain':0.,
          'eps_cu2':.0035,'tensile_steel_limit':.010,
          'strain_limits_satisfied':self.e<=.0035}


class TestR064C(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c=sample_column();th=evaluate_rectangular_column(c,grid=20)
        cls.p=prepare_section(c,th,grid=12)
        cls.column=c;cls.thermal=th

    def test_literal_fire_concrete_reference_at_ambient(self):
        p,e=select_fire_reference_strength(self.p,mode=LITERAL)
        self.assertAlmostEqual(p.concrete_fcd_MPa[0],30.,places=8)
        self.assertAlmostEqual(self.p.concrete_fcd_MPa[0],25.,places=8)
        self.assertAlmostEqual(e['concrete_strength_factor'],1.2)
        self.assertFalse(e['normative_claim'])

    def test_literal_steel_reference_unmodified_gamma1(self):
        p,e=select_fire_reference_strength(self.p,mode=LITERAL)
        np.testing.assert_allclose(p.bar_fyd_MPa,self.p.bar_fyd_MPa)
        self.assertEqual(e['steel_strength_factor'],1.)

    def test_displaced_concrete_same_reference_conversion(self):
        p,_=select_fire_reference_strength(self.p,mode=LITERAL)
        np.testing.assert_allclose(p.bar_displaced_concrete_fcd_MPa,
                                   1.2*self.p.bar_displaced_concrete_fcd_MPa)

    def test_original_material_inventory_not_mutated(self):
        old=copy.deepcopy(self.p.strength_data)
        p,_=select_fire_reference_strength(self.p,mode=LITERAL)
        p.concrete_fcd_MPa[0]=7
        self.assertEqual(old,self.p.strength_data)
        self.assertNotEqual(self.p.concrete_fcd_MPa[0],7)

    def test_invalid_reference_mode_fails_closed(self):
        with self.assertRaises(ValueError):
            select_fire_reference_strength(self.p,mode='guess')

    def _run_synthetic(self,n=3):
        z=np.linspace(0.,3.,n)
        law=linear_laws_at_gauss(z,np.full(n,3000.),np.full(n,3000.))
        r=solve_coupled_beam(z,100,law_at_gauss=law,
            distributed_load_kNpm=np.column_stack((np.ones(n)*1.,np.ones(n)*1.)))
        self.assertEqual(r['status'],'evaluated_diagnostic')
        return z,r

    def test_not_approved_even_if_numerically_satisfied(self):
        z,r=self._run_synthetic()
        u=audit_heated_member_uls(r,z,100,node_laws=[BadLaw(.001) for _ in z],
             action_provenance='externally calculated',material_provenance='only test')
        # Linear Gauss laws have no strength/strain evidence; can't pass ULS.
        self.assertEqual(u['status'],'INSUFFICIENT_ULS_EVIDENCE')
        self.assertFalse(u['normative_claim'])
        self.assertTrue(u['node_coverage'])
        self.assertEqual(u['node_side_count'],2+2*(len(z)-2))

    def test_unavailable_nodes_block(self):
        z,r=self._run_synthetic()
        u=audit_heated_member_uls(r,z,100)
        self.assertFalse(u['node_coverage'])
        self.assertIn('END_AND_INTERIOR_NODES_NOT_ASSESSED',u['blockers'])

    def test_high_strain_detected_at_nodal_section(self):
        z,r=self._run_synthetic()
        # Numerical gauss laws are deliberately linear, with no strain metadata.
        laws=[BadLaw(.001),BadLaw(.004),BadLaw(.001)]
        u=audit_heated_member_uls(r,z,100,node_laws=laws)
        self.assertEqual(u['status'],'DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED')
        self.assertGreaterEqual(u['exceeded_count'],2)
        self.assertEqual(u['critical_sample']['z_m'],z[1])

    def test_node_law_failure_blocks_not_approves(self):
        z,r=self._run_synthetic()
        u=audit_heated_member_uls(r,z,100,node_laws=[BadLaw(),BadLaw(fail=True),BadLaw()])
        self.assertIn('NODE_SECTION_EQUILIBRIUM_NOT_RESOLVED',u['blockers'])
        self.assertEqual(u['status'],'INSUFFICIENT_ULS_EVIDENCE')

    def test_wrong_number_of_node_laws_is_error(self):
        z,r=self._run_synthetic()
        with self.assertRaisesRegex(CoupledMemberError,'exactly one'):
            audit_heated_member_uls(r,z,100,node_laws=[BadLaw()])

    def test_nonsolved_member_never_passes(self):
        u=audit_heated_member_uls({'status':'critical_or_nonpositive_tangent'},[0,3],100)
        self.assertEqual(u['status'],'MODEL_NOT_SOLVED')
        self.assertFalse(u['normative_claim'])

    def test_node_curvature_matches_hermite_constant_curvature(self):
        z=np.array([0.,1.5,3.])
        k=.005;w=-.5*k*z**2;ang=-k*z
        r={'w_x_m':w.tolist(),'theta_x_rad':ang.tolist(),
           'w_y_m':w.tolist(),'theta_y_rad':ang.tolist()}
        for i in range(3):
            for side in ('left','right'):
                if (i==0 and side=='left') or (i==2 and side=='right'):continue
                v=_node_curvature(r,z,i,side)
                np.testing.assert_allclose(v,[k,k],atol=1e-12)

    def test_real_fibre_full_uls_observability(self):
        n=2;z=np.array([0.,3.])
        zeros=np.zeros_like(self.p.concrete_temperature_C)
        barzero=np.zeros_like(self.p.bar_temperature_C)
        laws=[FiberSectionLaw(self.p,free_concrete=zeros,free_steel=barzero,
            free_concrete_at_bars=barzero,free_concrete_at_corners=np.zeros(4),provenance='ambient test') for _ in range(5)]
        # Three Gauss section laws, two independent node laws.
        r=solve_coupled_beam(z,100.,law_at_gauss=lambda i,j:laws[j],
            distributed_load_kNpm=np.ones((2,2))*.001)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        u=audit_heated_member_uls(r,z,100,node_laws=laws[3:5],
            action_provenance='external',material_provenance='diagnostic')
        self.assertEqual(u['status'],'SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS')
        self.assertEqual(u['gauss_count'],3)
        self.assertEqual(u['node_side_count'],2)
        self.assertGreater(u['critical_sample']['maximum_ratio'],0.)
        self.assertFalse(u['normative_claim'])

    def test_full_pipeline_requires_all_thermal_sections(self):
        with self.assertRaisesRegex(CoupledMemberError,'Gauss row'):
            run_heated_member_uls_evidence([0.,3.],100,
                gauss_stations=[],node_stations=[])

    def test_full_pipeline_explicit_ambient(self):
        entry={'column':self.column,'thermal':self.thermal}
        r=run_heated_member_uls_evidence([0.,3.],100,
            gauss_stations=[[entry,entry,entry]],node_stations=[entry,entry],
            distributed_load_kNpm=np.ones((2,2))*.001,grid=12,
            fire_actions_source='external test actions',temperature_time_minutes=0.)
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['thermal_station_count'],5)
        self.assertEqual(r['material_strength_mode'],LITERAL)
        self.assertEqual(r['uls']['gauss_count'],3)
        self.assertEqual(r['uls']['node_side_count'],2)
        self.assertNotEqual(r['status'],'MODEL_NOT_SOLVED')

    def test_hot_10min_references_strength_and_retains_blockers(self):
        c=copy.deepcopy(self.column);c['fire_minutes']=10.
        th=evaluate_rectangular_column(c,grid=16)
        p=prepare_section(c,th,grid=12)
        pp,ev=select_fire_reference_strength(p,mode=LITERAL)
        self.assertGreater(max(p.concrete_temperature_C),20.)
        self.assertGreater(float(np.max(pp.concrete_fcd_MPa/p.concrete_fcd_MPa)),1.19)
        self.assertFalse(ev['normative_claim'])


if __name__=='__main__':unittest.main()

class TestR064CAdditional(unittest.TestCase):
    def test_corner_uls_bound_catches_subgrid_peak(self):
        c=sample_column();th=evaluate_rectangular_column(c,grid=16)
        p=prepare_section(c,th,grid=12)
        f=FiberSectionLaw(p,free_concrete=np.zeros_like(p.concrete_temperature_C),
            free_steel=np.zeros_like(p.bar_temperature_C),
            free_concrete_at_bars=np.zeros_like(p.bar_temperature_C),
            provenance='test')
        e0=.0002;cur=np.array([.0058,.0058])
        centre=e0+cur[0]*(p.y_m-p.h_m/2)+cur[1]*(p.x_m-p.b_m/2)
        self.assertLess(np.max(centre),p.eps_cu2)
        _,_,bound,_=f._force_and_tangent(e0,cur)
        self.assertGreater(bound,p.eps_cu2)

    def test_r90_out_of_range_is_structured_block(self):
        c=sample_column();c['fire_minutes']=90.
        th=evaluate_rectangular_column(c,grid=16)
        e={'column':c,'thermal':th}
        r=run_heated_member_uls_evidence([0.,3.],100,
            gauss_stations=[[e]*3],node_stations=[e,e],grid=12,
            temperature_time_minutes=90.)
        self.assertEqual(r['status'],'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT')
        self.assertFalse(r['normative_claim'])
        self.assertIn('800',r['reason'])

    def test_full_pipeline_json_serializable(self):
        c=sample_column();th=evaluate_rectangular_column(c,grid=12)
        e={'column':c,'thermal':th}
        r=run_heated_member_uls_evidence([0.,3.],100,
            gauss_stations=[[e]*3],node_stations=[e,e],grid=12,
            distributed_load_kNpm=np.ones((2,2))*.001)
        import json
        json.dumps(r)
        self.assertIn('SECTION_CONSTITUTIVE_LAW_NOT_NORMATIVELY_QUALIFIED',r['material_audit']['blockers'])

class TestR064CLimitScan(unittest.TestCase):
    def test_euler_pin_pin_numerical_limit_bracket(self):
        import math
        from rc_fire.member.limit_scan import scan_diagnostic_load_factor
        z=np.linspace(0.,3.,15)
        EI=3000.;N=1000.
        law=linear_laws_at_gauss(z,np.ones(len(z))*EI,np.ones(len(z))*EI)
        r=scan_diagnostic_load_factor(z,N,law_at_gauss=law,
            distributed_load_kNpm=np.column_stack((np.ones(len(z)),np.zeros(len(z)))),
            factor_step=.5,max_factor=5.,relative_bracket_tolerance=.002)
        self.assertEqual(r['status'],'FIRST_OBSERVED_NUMERICAL_LIMIT_BRACKETED')
        expected=math.pi**2*EI/(9.*N)
        self.assertAlmostEqual(r['lambda_low_diagnostic'],expected,delta=.03)
        self.assertAlmostEqual(r['lambda_high_diagnostic'],expected,delta=.03)
        self.assertFalse(r['normative_claim'])

    def test_limit_scan_without_limit_is_not_normative_pass(self):
        from rc_fire.member.limit_scan import scan_diagnostic_load_factor
        z=np.linspace(0.,3.,4)
        law=linear_laws_at_gauss(z,np.ones(len(z))*1e5,np.ones(len(z))*1e5)
        r=scan_diagnostic_load_factor(z,100.,law_at_gauss=law,
            factor_step=.5,max_factor=2.)
        self.assertEqual(r['status'],'NO_NUMERICAL_LIMIT_THROUGH_MAX_FACTOR')
        self.assertFalse(r['normative_claim'])

class TestR064CCornerField(unittest.TestCase):
    def test_missing_corner_data_is_unqualified_in_uls(self):
        c=sample_column();th=evaluate_rectangular_column(c,grid=12)
        p=prepare_section(c,th,grid=12)
        f=FiberSectionLaw(p,free_concrete=np.zeros_like(p.concrete_temperature_C),
            free_steel=np.zeros_like(p.bar_temperature_C),
            free_concrete_at_bars=np.zeros_like(p.bar_temperature_C),provenance='legacy')
        r=solve_coupled_beam([0.,3.],100,law_at_gauss=lambda i,j:f)
        u=audit_heated_member_uls(r,[0.,3.],100,node_laws=[f,f])
        self.assertEqual(u['status'],'INSUFFICIENT_ULS_EVIDENCE')
        self.assertIn('LOCAL_STRAIN_LIMIT_INFORMATION_MISSING',u['blockers'])

    def test_hot_corner_field_causes_diagnostic_exceedance(self):
        c=sample_column();c['fire_minutes']=10.
        th=evaluate_rectangular_column(c,grid=12);e={'column':c,'thermal':th}
        r=run_heated_member_uls_evidence([0.,1.5,3.],100.,
            gauss_stations=[[e]*3,[e]*3],node_stations=[e]*3,
            distributed_load_kNpm=np.ones((3,2)),grid=12,
            fire_actions_source='synthetic case',temperature_time_minutes=10.)
        self.assertEqual(r['status'],'DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED')
        self.assertEqual(r['member']['status'],'strain_limits_exceeded_diagnostic')
        self.assertGreater(r['uls']['critical_sample']['maximum_ratio'],1.)
        self.assertFalse(r['normative_claim'])
