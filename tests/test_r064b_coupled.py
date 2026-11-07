"""R0.6.4B independently derived elastic benchmarks, nonlinear-fibre checks and guards."""
import math
import unittest
import numpy as np
from rc_fire.member.coupled import (EndSupport,LinearSectionLaw,FiberSectionLaw,
    CoupledMemberError,integrated_free_strains_diagnostic,linear_laws_at_gauss,
    fibre_laws_at_gauss,solve_coupled_beam)


def reference(n=11,L=3.,EI=3000.,N=0.,q_x=0.,q_y=0.,
              left='pinned',right='pinned',**kwargs):
    z=np.linspace(0,L,n)
    law=linear_laws_at_gauss(z,np.ones(n)*EI,np.ones(n)*EI)
    q=np.column_stack((np.ones(n)*q_x,np.ones(n)*q_y))
    return solve_coupled_beam(z,N,law_at_gauss=law,
                    left=EndSupport(left),right=EndSupport(right),distributed_load_kNpm=q,**kwargs)


class TestCoupledMember(unittest.TestCase):
    def test_pin_uniform_load_exact_deflection(self):
        q=10.;L=3.;EI=3000.
        r=reference(21,q_x=q)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(r['w_x_m'][10],5*q*L**4/(384*EI),delta=2e-6)
        self.assertLess(max(abs(v) for v in r['w_y_m']),1e-10)

    def test_fixed_fixed_uniform_load_exact(self):
        q=10.;L=3.;EI=3000.
        r=reference(15,q_x=q,left='fixed',right='fixed')
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(max(r['w_x_m']),q*L**4/(384*EI),delta=4e-6)
        self.assertAlmostEqual(r['theta_x_rad'][0],0.,places=10)
        self.assertAlmostEqual(r['theta_x_rad'][-1],0.,places=10)

    def test_cantilever_tip_force_exact(self):
        L=3.;F=10.;EI=3000.;n=12;z=np.linspace(0,L,n)
        ff=np.zeros(4*n);ff[2*(n-1)]=F
        law=linear_laws_at_gauss(z,np.ones(n)*EI,np.ones(n)*EI)
        r=solve_coupled_beam(z,0.,law_at_gauss=law,left=EndSupport('fixed'),
                             right=EndSupport('free'),nodal_forces=ff)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(r['w_x_m'][-1],F*L**3/(3*EI),delta=2e-7)
        self.assertAlmostEqual(r['theta_x_rad'][-1],F*L**2/(2*EI),delta=2e-7)

    def test_sway_prescribed_translation_exact(self):
        L=3.;EI=3000.;n=10;z=np.linspace(0,L,n);shift=.02
        law=linear_laws_at_gauss(z,np.ones(n)*EI,np.ones(n)*EI)
        r=solve_coupled_beam(z,0.,law_at_gauss=law,left=EndSupport('fixed'),
                    right=EndSupport('fixed',displacement_m=shift))
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(r['w_x_m'][-1],shift)
        self.assertAlmostEqual(r['theta_x_rad'][0],0)
        self.assertAlmostEqual(r['theta_x_rad'][-1],0)
        self.assertAlmostEqual(r['w_x_m'][n//2],shift*(3*(z[n//2]/L)**2-2*(z[n//2]/L)**3),delta=2e-7)

    def test_pinned_first_buckling_and_sensitivity(self):
        L=3.;EI=3000.;n=20
        q=10.;Pcr=math.pi**2*EI/L**2
        base=reference(n,q_x=q)
        half=reference(n,N=.5*Pcr,q_x=q)
        self.assertEqual(half['status'],'evaluated_diagnostic')
        self.assertGreater(max(half['w_x_m']),1.6*max(base['w_x_m']))
        critical=reference(n,N=1.01*Pcr,q_x=q)
        self.assertEqual(critical['status'],'critical_or_nonpositive_tangent')

    def test_cantilever_critical_load(self):
        L=3.;EI=3000.;Pcr=math.pi**2*EI/(4*L**2)
        c=reference(20,N=1.01*Pcr,q_x=5,left='fixed',right='free')
        self.assertEqual(c['status'],'critical_or_nonpositive_tangent')

    def test_fixed_fixed_critical_load(self):
        L=3.;EI=3000.;Pcr=4*math.pi**2*EI/L**2
        a=reference(20,N=.9*Pcr,q_x=5,left='fixed',right='fixed')
        b=reference(20,N=1.01*Pcr,q_x=5,left='fixed',right='fixed')
        self.assertEqual(a['status'],'evaluated_diagnostic')
        self.assertEqual(b['status'],'critical_or_nonpositive_tangent')

    def test_thermal_free_curvature(self):
        L=3.;n=13;z=np.linspace(0,L,n);kappa=.001
        law=linear_laws_at_gauss(z,np.ones(n)*3000,np.ones(n)*3000,
                                  free_curvature_x=np.ones(n)*kappa)
        r=solve_coupled_beam(z,0.,law_at_gauss=law)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(r['w_x_m'][n//2],kappa*L**2/8,delta=2e-7)

    def test_biaxial_stiffness_off_diagonal_couples_deflections(self):
        n=12;z=np.linspace(0,3,n)
        dxy=np.ones(n)*900
        law=linear_laws_at_gauss(z,np.ones(n)*3000,np.ones(n)*3000,D_xy_kNm2=dxy)
        r=solve_coupled_beam(z,0.,law_at_gauss=law,
                     distributed_load_kNpm=np.column_stack((np.ones(n)*10,np.zeros(n))))
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertGreater(max(abs(v) for v in r['w_y_m']),1e-4)
        self.assertLess(np.mean(r['w_y_m']),0)  # positive Dxy -> opposite bending axis response

    def test_unequal_axis_stiffness_and_loading(self):
        n=10;z=np.linspace(0,3,n)
        law=linear_laws_at_gauss(z,np.ones(n)*4000,np.ones(n)*1000)
        r=solve_coupled_beam(z,0.,law_at_gauss=law,
                          distributed_load_kNpm=np.ones((n,2))*5)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(max(r['w_y_m'])/max(r['w_x_m']),4.,delta=.001)

    def test_imperfection_pdelta_amplification(self):
        n=11;L=3.;z=np.linspace(0,L,n);EI=3000.;N=1000.
        law=linear_laws_at_gauss(z,np.ones(n)*EI,np.ones(n)*EI)
        imp=np.zeros(4*n)
        imp[:2*n:2]=.01*np.sin(math.pi*z/L)
        imp[1:2*n:2]=.01*(math.pi/L)*np.cos(math.pi*z/L)
        r=solve_coupled_beam(z,N,law_at_gauss=law,initial_imperfection=imp)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        expected=.01/(1-N/(math.pi**2*EI/L**2))
        self.assertAlmostEqual(r['total_w_x_m'][n//2],expected,delta=4e-5)

    def test_elastic_spring_increases_stiffness(self):
        n=13;z=np.linspace(0,3,n);law=linear_laws_at_gauss(z,np.ones(n)*3000,np.ones(n)*3000)
        base=solve_coupled_beam(z,0.,law_at_gauss=law,left=EndSupport('fixed'),
                right=EndSupport('free'),distributed_load_kNpm=np.ones((n,2))*5)
        stiff=solve_coupled_beam(z,0.,law_at_gauss=law,left=EndSupport('fixed'),
                right=EndSupport('elastic',lateral_spring_kNpm=1000.),
                distributed_load_kNpm=np.ones((n,2))*5)
        self.assertEqual(stiff['status'],'evaluated_diagnostic')
        self.assertLess(stiff['w_x_m'][-1],base['w_x_m'][-1])

    def test_axis_specific_support_conditions(self):
        n=12;z=np.linspace(0,3,n)
        laws=linear_laws_at_gauss(z,np.ones(n)*3000,np.ones(n)*3000)
        r=solve_coupled_beam(z,0,law_at_gauss=laws,
              left=(EndSupport('fixed'),EndSupport('pinned')),
              right=(EndSupport('free'),EndSupport('pinned')),
              distributed_load_kNpm=np.ones((n,2))*3)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(r['theta_x_rad'][0],0)
        self.assertAlmostEqual(r['w_y_m'][-1],0)
        self.assertGreater(r['w_x_m'][-1],0)

    def test_restrained_sway_in_one_axis_only(self):
        n=11;z=np.linspace(0,3,n)
        laws=linear_laws_at_gauss(z,np.ones(n)*3000,np.ones(n)*3000)
        r=solve_coupled_beam(z,0,law_at_gauss=laws,
          left=EndSupport('fixed'),
          right=EndSupport('fixed',displacement_m=(.01,0.)))
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(r['w_x_m'][-1],.01)
        self.assertTrue(np.allclose(r['w_y_m'],0,atol=1e-12))

    def test_fibre_biaxial_tangent_matches_external_difference(self):
        from tests.test_r063_mechanics import SectionMechanicsTests
        p=SectionMechanicsTests().pre(g=12)
        law=FiberSectionLaw(p,free_concrete=np.zeros_like(p.concrete_temperature_C),
            free_steel=np.zeros_like(p.bar_temperature_C),
            free_concrete_at_bars=np.zeros_like(p.bar_temperature_C),provenance='verified ambient')
        k=np.array([1e-5,-2e-5]);M,D,_=law.evaluate(k,600.)
        step=1e-7
        for j in (0,1):
            e=np.eye(2)[j]*step
            Mp=law.evaluate(k+e,600.)[0]
            Mm=law.evaluate(k-e,600.)[0]
            np.testing.assert_allclose((Mp-Mm)/(2*step),D[:,j],rtol=2e-4,atol=.05)

    def test_affine_thermal_eigenstrain_is_stress_free_at_matching_curvatures(self):
        from tests.test_r063_mechanics import SectionMechanicsTests
        p=SectionMechanicsTests().pre(g=12)
        a=.0005;gx=.0002;gy=-.0003
        # With compression positive, an affine positive extension is balanced
        # exactly by negative total strain and negative curvature.
        ec=a+gx*(p.y_m-p.h_m/2)+gy*(p.x_m-p.b_m/2)
        es=a+gx*(p.bar_y_m-p.h_m/2)+gy*(p.bar_x_m-p.b_m/2)
        law=FiberSectionLaw(p,free_concrete=ec,free_steel=es,
               free_concrete_at_bars=es,provenance='analytic affine expansion')
        M,D,meta=law.evaluate(np.array([-gx,-gy]),0.)
        self.assertLess(np.linalg.norm(M),1e-6)
        self.assertAlmostEqual(meta['axial_compressive_strain_e0'],-a,delta=1e-7)

    def test_global_tangent_agrees_with_finite_differences(self):
        from rc_fire.member.coupled import _beam_assembly
        n=3;z=np.linspace(0,3,n);law=linear_laws_at_gauss(z,np.ones(n)*3000,np.ones(n)*1800,
                 D_xy_kNm2=np.ones(n)*350,free_curvature_x=np.ones(n)*.0001)
        d=np.linspace(0,.001,4*n);initial=np.zeros(4*n); q=np.zeros((n,2));ext=np.zeros(4*n)
        N=150.
        f,K,G,F,_=_beam_assembly(z,N,law,d,initial,q,ext)
        residual=f-N*G@d-F
        T=K-N*G
        h=1e-7
        for j in (0,3,7,11):
            dd=np.zeros(4*n);dd[j]=h
            fp,Kp,Gp,Fp,_=_beam_assembly(z,N,law,d+dd,initial,q,ext)
            fm,Km,Gm,Fm,_=_beam_assembly(z,N,law,d-dd,initial,q,ext)
            numeric=((fp-N*Gp@(d+dd)-Fp)-(fm-N*Gm@(d-dd)-Fm))/(2*h)
            np.testing.assert_allclose(numeric,T[:,j],rtol=3e-7,atol=1e-4)

    def test_biaxial_tangent_symmetry_in_full_section(self):
        from tests.test_r063_mechanics import SectionMechanicsTests
        p=SectionMechanicsTests().pre(g=12)
        law=FiberSectionLaw(p,free_concrete=np.zeros_like(p.concrete_temperature_C),
            free_steel=np.zeros_like(p.bar_temperature_C),
            free_concrete_at_bars=np.zeros_like(p.bar_temperature_C),provenance='ambient reference')
        _,D,_=law.evaluate([1e-5,-3e-5],400)
        np.testing.assert_allclose(D,D.T,atol=1e-8)
        self.assertGreater(np.linalg.eigvalsh(D)[0],0.)

    def test_missing_eigenstrains_cannot_enter_nonlinear_fire_law(self):
        from tests.test_r063_mechanics import SectionMechanicsTests
        p=SectionMechanicsTests().pre(g=12)
        with self.assertRaises(TypeError):FiberSectionLaw(p,provenance='missing actual temperature')
        with self.assertRaises(CoupledMemberError):
            FiberSectionLaw(p,free_concrete=np.zeros_like(p.concrete_temperature_C),
                free_steel=np.zeros_like(p.bar_temperature_C),
                free_concrete_at_bars=np.zeros(1),provenance='bad steel geometry')

    def test_explicit_thermal_station_validation(self):
        from tests.test_r063_mechanics import sample_column
        from rc_fire.thermal import evaluate_rectangular_column
        from rc_fire.member.coupled import heated_laws_from_explicit_thermal_stations
        c=sample_column();c['fire_minutes']=10.
        th=evaluate_rectangular_column(c,grid=12)
        with self.assertRaises(CoupledMemberError):
            heated_laws_from_explicit_thermal_stations([[{'column':c,'thermal':th}]*3])
        with self.assertRaises(CoupledMemberError):
            heated_laws_from_explicit_thermal_stations([[{'column':c,'thermal':th}]*2],accept_integration_convention=True)
        wrong=dict(th);wrong['fire_minutes']=20.
        with self.assertRaises(CoupledMemberError):
            heated_laws_from_explicit_thermal_stations([[{'column':c,'thermal':wrong}]*3],accept_integration_convention=True)

    def test_real_annex_K_heated_fibre_beam(self):
        from tests.test_r063_mechanics import sample_column
        from rc_fire.thermal import evaluate_rectangular_column
        from rc_fire.member.coupled import heated_laws_from_explicit_thermal_stations
        c=sample_column();c['fire_minutes']=10.
        th=evaluate_rectangular_column(c,grid=12)
        row=[{'column':c,'thermal':th} for _ in range(3)]
        evidence=heated_laws_from_explicit_thermal_stations([row,row],grid=12,
                                             accept_integration_convention=True)
        z=np.linspace(0,3,3);q=np.ones((3,2))*1
        r=solve_coupled_beam(z,100,law_at_gauss=evidence['law_at_gauss'],
                             distributed_load_kNpm=q,max_iterations=9)
        self.assertEqual(r['status'],'strain_limits_exceeded_diagnostic')
        self.assertTrue(r['any_strain_limit_exceeded'])
        self.assertTrue(any(v['max_boundary_C']>20 for v in evidence['evidence']))
        self.assertFalse(evidence['normative_claim'])
        self.assertFalse(r['normative_claim'])

    def test_heating_changes_deflection_and_is_not_auto_normative(self):
        from tests.test_r063_mechanics import sample_column
        from rc_fire.thermal import evaluate_rectangular_column
        from rc_fire.member.coupled import heated_laws_from_explicit_thermal_stations
        output=[]
        for t in (0.,10.):
            c=sample_column();c['fire_minutes']=t
            th=evaluate_rectangular_column(c,grid=12)
            row=[{'column':c,'thermal':th} for _ in range(3)]
            ev=heated_laws_from_explicit_thermal_stations([row,row],grid=12,
                                          accept_integration_convention=True)
            z=np.linspace(0,3,3)
            r=solve_coupled_beam(z,100,law_at_gauss=ev['law_at_gauss'],
                                 distributed_load_kNpm=np.ones((3,2)),max_iterations=9)
            self.assertEqual(r['status'], 'evaluated_diagnostic' if t==0. else 'strain_limits_exceeded_diagnostic')
            output.append(r['w_x_m'][1])
        self.assertGreater(output[1],output[0]*1.1)

    def test_two_face_thermal_eigenstrain_and_thermal_curvature(self):
        from tests.test_r063_mechanics import sample_column
        from rc_fire.thermal import evaluate_rectangular_column
        from rc_fire.member.coupled import heated_laws_from_explicit_thermal_stations
        c=sample_column();c['fire_minutes']=10.
        c['thermal_spec']['exposed_faces']=['left','bottom']
        th=evaluate_rectangular_column(c,grid=12)
        ev=heated_laws_from_explicit_thermal_stations([[{'column':c,'thermal':th}]*3],grid=12,
                                                    accept_integration_convention=True)
        r=solve_coupled_beam([0.,3.],100,law_at_gauss=ev['law_at_gauss'],max_iterations=9)
        self.assertEqual(r['status'],'strain_limits_exceeded_diagnostic')
        self.assertTrue(any(abs(v['curvature_1pm'][0])>1e-8 for v in r['integration_stations']))
        self.assertTrue(any(abs(v['curvature_1pm'][1])>1e-8 for v in r['integration_stations']))

    def test_temperature_above_material_limit_fails_closed(self):
        from tests.test_r063_mechanics import sample_column
        from rc_fire.thermal import evaluate_rectangular_column
        from rc_fire.member.coupled import heated_laws_from_explicit_thermal_stations
        c=sample_column();c['fire_minutes']=30.
        th=evaluate_rectangular_column(c,grid=12)
        with self.assertRaises(Exception) as ctx:
            heated_laws_from_explicit_thermal_stations([[{'column':c,'thermal':th}]*3],grid=12,
                                                   accept_integration_convention=True)
        self.assertIn('800',str(ctx.exception))

    def test_section_strain_limit_exceeded_cannot_be_called_evaluated(self):
        class LimitExceededLaw:
            def evaluate(self,kappa,N):
                D=np.eye(2)*3000.
                return D@kappa,D,{'model':'test_synthetic','source':'test',
                    'strain_limits_satisfied':False}
        r=solve_coupled_beam([0.,1.5,3.],100,
                             law_at_gauss=lambda i,j: LimitExceededLaw())
        self.assertEqual(r['status'],'strain_limits_exceeded_diagnostic')
        self.assertTrue(r['any_strain_limit_exceeded'])
        self.assertFalse(r['normative_claim'])

    def test_invalid_input_and_r90_gate(self):
        n=9;z=np.linspace(0,3,n);law=linear_laws_at_gauss(z,np.ones(n)*3000,np.ones(n)*3000)
        with self.assertRaises(CoupledMemberError):
            EndSupport('fake').validate()
        with self.assertRaises(CoupledMemberError):
            EndSupport('elastic',lateral_spring_kNpm=-5).validate()
        with self.assertRaises(CoupledMemberError):
            LinearSectionLaw([[100,300],[300,100]])
        with self.assertRaises(CoupledMemberError):
            solve_coupled_beam([0,1,1],0,law_at_gauss=law)
        r=solve_coupled_beam(z,0,law_at_gauss=law)
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

    def test_free_free_mechanism_not_pretended_stable(self):
        n=9;z=np.linspace(0,3,n);law=linear_laws_at_gauss(z,np.ones(n)*3000,np.ones(n)*3000)
        r=solve_coupled_beam(z,0,law_at_gauss=law,left=EndSupport('free'),right=EndSupport('free'))
        self.assertEqual(r['status'],'critical_or_nonpositive_tangent')

    def test_fibre_model_ambient_axial_equilibrium_and_tangent(self):
        from tests.test_r063_mechanics import SectionMechanicsTests
        p=SectionMechanicsTests().pre(g=12)
        zeros_c=np.zeros_like(p.concrete_temperature_C)
        zeros_s=np.zeros_like(p.bar_temperature_C)
        law=FiberSectionLaw(p,free_concrete=zeros_c,free_steel=zeros_s,
                       free_concrete_at_bars=zeros_s,provenance='known ambient reference')
        M,D,meta=law.evaluate(np.zeros(2),500.)
        self.assertAlmostEqual(M[0],0,delta=1e-5)
        self.assertAlmostEqual(M[1],0,delta=1e-5)
        self.assertTrue(np.all(np.linalg.eigvalsh(D)>0))
        self.assertEqual(meta['model'],'nonlinear_R063C_fibres_with_explicit_eigenstrains')
        self.assertFalse(meta['normative_claim'])

    def test_fibre_model_thermal_expansion_uniform_free(self):
        from tests.test_r063_mechanics import SectionMechanicsTests
        p=SectionMechanicsTests().pre(g=12)
        eps=np.ones_like(p.concrete_temperature_C)*.0005
        eb=np.ones_like(p.bar_temperature_C)*.0005
        law=FiberSectionLaw(p,free_concrete=eps,free_steel=eb,
                         free_concrete_at_bars=eb,provenance='synthetic matched expansion')
        M,D,meta=law.evaluate(np.zeros(2),0.)
        self.assertLess(np.linalg.norm(M),1e-6)
        self.assertAlmostEqual(meta['axial_compressive_strain_e0'],-.0005,delta=1e-7)

    def test_integrator_requires_optin_and_no_temperature_extrapolation(self):
        from tests.test_r063_mechanics import SectionMechanicsTests
        p=SectionMechanicsTests().pre(g=12)
        with self.assertRaises(CoupledMemberError):
            integrated_free_strains_diagnostic(p,concrete_at_bars_C=p.bar_temperature_C,
                                               source_provenance='synthetic')
        v=integrated_free_strains_diagnostic(p,concrete_at_bars_C=p.bar_temperature_C,
                                  source_provenance='synthetic',accept_integration_convention=True)
        self.assertFalse(v['normative_claim'])
        np.testing.assert_allclose(v['free_concrete'],0,atol=1e-12)

    def test_coupled_nonlin_fibre_full_beam_zero_actions(self):
        from tests.test_r063_mechanics import SectionMechanicsTests
        p=SectionMechanicsTests().pre(g=12)
        law=FiberSectionLaw(p,free_concrete=np.zeros_like(p.concrete_temperature_C),
            free_steel=np.zeros_like(p.bar_temperature_C),
            free_concrete_at_bars=np.zeros_like(p.bar_temperature_C),provenance='ambient')
        z=np.linspace(0,3,4)
        res=solve_coupled_beam(z,100.,law_at_gauss=lambda i,j: law)
        self.assertEqual(res['status'],'evaluated_diagnostic')
        self.assertFalse(res['any_strain_limit_exceeded'])

if __name__=='__main__':unittest.main()
