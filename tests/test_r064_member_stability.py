"""R0.6.4 independent deterministic checks and explicit qualification guards."""
import unittest
from math import pi,sqrt,sin
import numpy as np
from rc_fire.member import (MemberInputError,NominalStiffnessInput,nominal_stiffness,
    effective_length,imperfection_eccentricity,slenderness_screen,amplify_moment,
    second_order_pin_pin,evaluate_member_diagnostic,section_checks_at_stations)

class TestMember(unittest.TestCase):
    def test_effective_length_conditions(self):
        cases={'pinned_pinned':1.,'fixed_free':2.,'pinned_fixed_non_sway':.7,
               'fixed_fixed_non_sway':.5,'partially_fixed_both_non_sway':.8}
        for key,k in cases.items():
            self.assertAlmostEqual(effective_length(3,condition=key)['effective_length_m'],3*k)
    def test_effective_length_fails_closed(self):
        with self.assertRaises(MemberInputError):effective_length(3)
        with self.assertRaises(MemberInputError):effective_length(3,condition='unknown')
        with self.assertRaises(MemberInputError):effective_length(3,condition='pinned_pinned',k=1)
    def test_imperfection_source_for_3m(self):
        r=imperfection_eccentricity(3,3)
        self.assertAlmostEqual(r['alpha_h'],1)
        self.assertAlmostEqual(r['alpha_m'],1)
        self.assertAlmostEqual(r['e_i_m'],.0075)
        s=imperfection_eccentricity(3,3,method='braced_column_l0_over_400')
        self.assertAlmostEqual(s['e_i_m'],.0075)
    def test_imperfection_alpha_m_and_h(self):
        r=imperfection_eccentricity(100,50,m=4)
        self.assertAlmostEqual(r['alpha_h'],.4)
        self.assertAlmostEqual(r['alpha_m'],sqrt(.5*(1+.25)))
    def test_slenderness_screen_sqrt_n_and_defaults(self):
        r=slenderness_screen(N_kN=1000,Ac_m2=.36,Ic_m4=.0108,effective_length_m=3,fcd_MPa=25)
        self.assertAlmostEqual(r['lambda_lim'],20*.7*1.1*.7/sqrt(1000/(.36*25*1000)))
        self.assertFalse(r['fire_qualification'])
    def test_slenderness_screen_with_defined_omega(self):
        r=slenderness_screen(N_kN=1000,Ac_m2=.36,Ic_m4=.0108,effective_length_m=3,fcd_MPa=25,
                            phi_eff=0,omega=.25,moment_ratio=-.5)
        self.assertAlmostEqual(r['bN'],sqrt(1.5))
        self.assertAlmostEqual(r['cN'],2.2)
    def test_nominal_stiffness_illustrative_manual(self):
        Ac=.6*.6; Ic=.6*.6**3/12
        d=NominalStiffnessInput(30,25,1000,Ac,Ic,0,33000,200000,3,0)
        r=nominal_stiffness(d)
        slender=3/sqrt(Ic/Ac)
        n=1000/(1000*Ac*25)
        k2=min(.2,n*slender/170)
        B=sqrt(30/20)*k2*(33000/1.2)*Ic*1000
        self.assertAlmostEqual(r['k1a'],sqrt(1.5))
        self.assertAlmostEqual(r['Bnom_kNm2'],B)
        self.assertAlmostEqual(r['Ncrit_kN'],pi*pi*B/9)
    def test_nominal_does_not_fabricate_creep(self):
        d=NominalStiffnessInput(30,25,1000,.36,.0108,0,33000,200000,3,None)
        with self.assertRaises(MemberInputError):nominal_stiffness(d)
    def test_amplifier_critical_block(self):
        self.assertAlmostEqual(amplify_moment(20,500,1000)['M_second_kNm'],40)
        self.assertEqual(amplify_moment(20,1000,1000)['status'],'critical_or_beyond')
    def test_zero_axial_exact_linear_pinned_bvp(self):
        z=np.linspace(0,3,121); M=100*np.sin(pi*z/3); B=np.ones_like(z)*3000
        r=second_order_pin_pin(z,M,0,B)
        exact=100/(3000*(pi/3)**2)*np.sin(pi*z/3)
        self.assertLess(np.max(np.abs(np.asarray(r['w_m'])-exact)),2e-5)
        self.assertTrue(np.allclose(r['M_total_kNm'],M))
    def test_uniform_EI_pdelta_exact_sinusoid(self):
        z=np.linspace(0,3,121);B=np.ones_like(z)*3000
        Ncrit=pi*pi*3000/9;N=.5*Ncrit
        M=100*np.sin(pi*z/3)
        r=second_order_pin_pin(z,M,N,B)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertAlmostEqual(r['max_abs_M_total_kNm'],200,delta=.06)
    def test_critical_eigenvalue_refuses_false_positive(self):
        z=np.linspace(0,3,101); B=np.ones_like(z)*3000
        r=second_order_pin_pin(z,np.ones_like(z)*10,pi*pi*3000/9*1.01,B)
        self.assertEqual(r['status'],'critical_or_beyond')
        self.assertIsNone(r['M_total_kNm'])
    def test_mesh_convergence(self):
        def run(n):
            z=np.linspace(0,3,n);B=np.ones(n)*3000;N=1000
            M=100*np.sin(pi*z/3)
            return second_order_pin_pin(z,M,N,B)['max_abs_M_total_kNm']
        exact=100/(1-1000/(pi*pi*3000/9))
        self.assertLess(abs(run(129)-exact),abs(run(33)-exact))
        self.assertLess(abs(run(129)-exact),.015)
    def test_variable_stiffness_and_two_axes(self):
        z=np.linspace(0,3,81); bx=3000*(1+.2*np.sin(pi*z/3));by=bx*.8
        r=evaluate_member_diagnostic(z,400,30*np.sin(pi*z/3),20*np.sin(pi*z/3),bx,by)
        self.assertEqual(r['status'],'evaluated_diagnostic')
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')
    def test_temperature_curvature_zero_load(self):
        z=np.linspace(0,3,81);B=np.ones_like(z)*3000
        kth=np.ones_like(z)*.001
        r=second_order_pin_pin(z,np.zeros_like(z),0,B,thermal_curvature_1pm=kth)
        self.assertAlmostEqual(abs(r['w_m'][40]),.001*3*3/8,delta=1e-6)
        self.assertEqual(r['thermal_curvature_source'],'externally_specified_not_qualified')
    def test_bad_grid_and_stiffness_blocked(self):
        z=np.linspace(0,3,81);B=np.ones_like(z)*3000
        with self.assertRaises(MemberInputError):second_order_pin_pin(z,np.zeros_like(z),100,-B)
        with self.assertRaises(MemberInputError):second_order_pin_pin(z**2,np.zeros_like(z),100,B)
    def test_section_coupling_missing_station_blocks(self):
        z=np.linspace(0,3,9);B=np.ones_like(z)*3000
        r=evaluate_member_diagnostic(z,100,np.ones_like(z)*5,np.ones_like(z)*3,B,B)
        coupled=section_checks_at_stations(r,z,{0.0:object()},100,
             solver=lambda s,n,mx,my:{'equilibrium':True})
        self.assertEqual(coupled['status'],'blocked')
        self.assertEqual(coupled['checked_stations'],1)
    def test_section_coupling_biaxial_total_moments(self):
        z=np.linspace(0,3,9);B=np.ones_like(z)*3000
        r=evaluate_member_diagnostic(z,100,np.ones_like(z)*5,np.ones_like(z)*3,B,B)
        calls=[]
        def fake_solver(section,n,mx,my):
            calls.append((n,mx,my));return {'equilibrium':True,'normative_claim':False}
        coupled=section_checks_at_stations(r,z,{float(v):object() for v in z},100,
                                           solver=fake_solver)
        self.assertEqual(len(calls),len(z))
        self.assertTrue(coupled['all_equilibria_solved'])
        self.assertGreater(calls[4][1],5)
        self.assertGreater(calls[4][2],3)
        self.assertFalse(coupled['normative_claim'])
    def test_member_unevaluated_R90(self):
        z=np.linspace(0,3,81); B=np.ones_like(z)*3000
        r=evaluate_member_diagnostic(z,100,np.zeros_like(z),np.zeros_like(z),B,B)
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

if __name__=='__main__':unittest.main()
