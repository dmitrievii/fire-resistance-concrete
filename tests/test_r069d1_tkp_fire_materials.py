"""Independent literal-node and constitutive continuity checks for Belarus TKP."""
import math
import unittest

from rc_fire.materials.tkp_en1992_fire import (
    TEMP, CONCRETE_K, CONCRETE_EPS_C1, CONCRETE_EPS_CU,
    STEEL_N, GAMMA_M_FI, CONDUCTIVITY_NORMAL, REBAR_FIRE_CLASS,
    EurocodeFireMaterialError, concrete_parameters, concrete_stress,
    reinforcement_parameters, reinforcement_stress,
    concrete_free_thermal_strain,rebar_free_thermal_strain,qualification,
)


class BelarusFireSourceTests(unittest.TestCase):
    def test_NA_choices_are_literal_and_contained_in_user_document(self):
        self.assertEqual(GAMMA_M_FI,1.)
        self.assertEqual(CONDUCTIVITY_NORMAL,'lower_bound')
        self.assertEqual(REBAR_FIRE_CLASS,'N')
        q=qualification()
        self.assertFalse(q['normative_member_R_t_claim'])
        self.assertEqual(q['concrete_constitutive_domain_C'],[20,1100])
        self.assertEqual(q['concrete_1100_to_1200'],'strength_only_strain_curve_unresolved')

    def test_every_siliceous_table_3_1_coefficient_exact(self):
        expected=[1,1,.95,.85,.75,.6,.45,.3,.15,.08,.04,.01,0]
        self.assertEqual(list(CONCRETE_K['siliceous']),expected)
        for t,k in zip(TEMP,expected):
            with self.subTest(t=t):
                self.assertAlmostEqual(concrete_parameters(t,aggregate='siliceous').k_c,k)

    def test_every_calcareous_coefficient_exact(self):
        expected=[1,1,.97,.91,.85,.74,.6,.43,.27,.15,.06,.02,0]
        self.assertEqual(list(CONCRETE_K['calcareous']),expected)
        for t,k in zip(TEMP,expected):
            self.assertAlmostEqual(concrete_parameters(t,aggregate='calcareous').k_c,k)

    def test_concrete_deformation_parameters_exact_to_1100(self):
        self.assertEqual(CONCRETE_EPS_C1[0],.0025)
        self.assertEqual(CONCRETE_EPS_C1[-1],.025)
        self.assertEqual(CONCRETE_EPS_CU[0],.02)
        self.assertEqual(CONCRETE_EPS_CU[-1],.0475)
        for t,e1,eu in zip(TEMP[:-1],CONCRETE_EPS_C1,CONCRETE_EPS_CU):
            p=concrete_parameters(t,aggregate='siliceous')
            self.assertAlmostEqual(p.eps_c1,e1)
            self.assertAlmostEqual(p.eps_cu1,eu)

    def test_intermediate_concrete_table_values_linearly_interpolated(self):
        p=concrete_parameters(950,aggregate='siliceous')
        self.assertAlmostEqual(p.k_c,.06)
        self.assertAlmostEqual(p.eps_cu1,.04375)
        p=concrete_parameters(750,aggregate='calcareous')
        self.assertAlmostEqual(p.k_c,.35)

    def test_source_distinction_between_reduced_strength_and_undefined_curve(self):
        p=concrete_parameters(1150,aggregate='siliceous')
        self.assertAlmostEqual(p.k_c,.005)
        self.assertIsNone(p.eps_c1)
        self.assertIsNone(p.eps_cu1)
        self.assertFalse(p.full_stress_strain_defined)
        with self.assertRaises(EurocodeFireMaterialError):
            concrete_stress(.01,1150,fck_MPa=30,aggregate='siliceous')
        self.assertEqual(concrete_stress(.01,1200,fck_MPa=30,aggregate='siliceous'),(0.,0.))

    def test_concrete_fig_3_1_reaches_correct_peak_and_tangent(self):
        for t in (20,450,700,1100):
            p=concrete_parameters(t,aggregate='siliceous')
            stress,tangent=concrete_stress(p.eps_c1,t,
                                           fck_MPa=30,aggregate='siliceous')
            self.assertAlmostEqual(stress,p.k_c*30,places=10)
            self.assertAlmostEqual(tangent,0.,places=7)

    def test_concrete_descending_is_continuous_and_reaches_zero(self):
        p=concrete_parameters(700,aggregate='siliceous')
        mid=(p.eps_c1+p.eps_cu1)/2
        stress,tangent=concrete_stress(mid,700,fck_MPa=30,aggregate='siliceous')
        self.assertAlmostEqual(stress,30*p.k_c/2,places=10)
        self.assertLess(tangent,0)
        self.assertEqual(concrete_stress(p.eps_cu1,700,fck_MPa=30,
                                         aggregate='siliceous'),(0.,0.))

    def test_no_concrete_tension_strength_assumed(self):
        for t in (20,500,1100,1200):
            self.assertEqual(concrete_stress(-.001,t,fck_MPa=30,
                         aggregate='siliceous'),(0.,0.))

    def test_hot_rolled_table_class_N_nodes(self):
        check={20:(1,1,1),400:(1,.42,.7),700:(.23,.07,.13),
               900:(.06,.04,.07),1100:(.02,.01,.02),1200:(0,0,0)}
        for t,(y,p,E) in check.items():
            data=reinforcement_parameters(t,fyk_MPa=500,Es_MPa=200000,
                       production_route='hot_rolled',ductility_class='B')
            self.assertAlmostEqual(data.k_sy,y)
            self.assertAlmostEqual(data.k_sp,p)
            self.assertAlmostEqual(data.k_E,E)
            self.assertEqual(data.class_N,'N')

    def test_cold_worked_table_class_N_nodes(self):
        check={100:(1,.96,1),400:(.94,.63,.56),700:(.12,.08,.08),
               900:(.08,.05,.05),1100:(.03,.02,.02),1200:(0,0,0)}
        for t,(y,p,E) in check.items():
            data=reinforcement_parameters(t,fyk_MPa=500,Es_MPa=200000,
                     production_route='cold_worked',ductility_class='A')
            self.assertAlmostEqual(data.k_sy,y)
            self.assertAlmostEqual(data.k_sp,p)
            self.assertAlmostEqual(data.k_E,E)

    def test_steel_rounded_branch_continuous_and_stress_yield(self):
        for route in ('hot_rolled','cold_worked'):
            for t in (100,400,700,1100):
                data=reinforcement_parameters(t,fyk_MPa=500,Es_MPa=200000,
                     production_route=route,ductility_class='B')
                at_p,_=reinforcement_stress(data.eps_sp,t,fyk_MPa=500,Es_MPa=200000,
                     production_route=route,ductility_class='B')
                at_y,_=reinforcement_stress(data.eps_sy,t,fyk_MPa=500,Es_MPa=200000,
                     production_route=route,ductility_class='B')
                self.assertAlmostEqual(at_p,data.f_sp_MPa,places=8)
                self.assertAlmostEqual(at_y,data.f_sy_MPa,places=7)

    def test_steel_symmetry_and_softening(self):
        k={'fyk_MPa':500,'Es_MPa':200000,'production_route':'hot_rolled',
           'ductility_class':'B'}
        for eps in (.001,.006,.05,.17):
            x=reinforcement_stress(eps,700,**k)
            y=reinforcement_stress(-eps,700,**k)
            self.assertAlmostEqual(x[0],-y[0],places=9)
            self.assertAlmostEqual(x[1],y[1],places=9)
        self.assertEqual(reinforcement_stress(.20,700,**k),(0.,0.))
        self.assertEqual(reinforcement_stress(.23,700,**k),(0.,0.))

    def test_ductility_class_A_strain_cutoff(self):
        p=reinforcement_parameters(700,fyk_MPa=500,Es_MPa=200000,
                  production_route='cold_worked',ductility_class='A')
        self.assertEqual((p.eps_sy,p.eps_st,p.eps_su),(.02,.05,.10))
        self.assertEqual(reinforcement_stress(.10,700,
                  fyk_MPa=500,Es_MPa=200000,production_route='cold_worked',
                  ductility_class='A'),(0.,0.))

    def test_steel_at_1200_zero_but_no_extrapolation(self):
        self.assertEqual(reinforcement_stress(.015,1200,fyk_MPa=500,
              Es_MPa=200000,production_route='hot_rolled',
              ductility_class='C'),(0.,0.))
        with self.assertRaises(EurocodeFireMaterialError):
            reinforcement_parameters(1201,fyk_MPa=500,Es_MPa=200000,
                        production_route='hot_rolled',ductility_class='C')

    def test_product_route_and_ductility_are_required_not_guessed_from_S500(self):
        for args in ({'production_route':'weldable_bar','ductility_class':'B'},
                     {'production_route':'hot_rolled','ductility_class':'unknown'}):
            with self.assertRaises(EurocodeFireMaterialError):
                reinforcement_parameters(720,fyk_MPa=500,Es_MPa=200000,**args)

    def test_rebar_K18_hot_and_cold_curves_differ_and_are_not_automatically_selected(self):
        hot=reinforcement_parameters(720,fyk_MPa=500,Es_MPa=200000,
                production_route='hot_rolled',ductility_class='B')
        cold=reinforcement_parameters(720,fyk_MPa=500,Es_MPa=200000,
                production_route='cold_worked',ductility_class='B')
        self.assertGreater(hot.f_sy_MPa,cold.f_sy_MPa)
        self.assertAlmostEqual(hot.f_sy_MPa,500*(.23+.2*(.11-.23)),places=9)
        self.assertAlmostEqual(cold.f_sy_MPa,500*(.12+.2*(.11-.12)),places=9)

    def test_concrete_thermal_expansion_formula_nodes(self):
        self.assertAlmostEqual(concrete_free_thermal_strain(700,aggregate='siliceous'),.014,delta=.00002)
        self.assertAlmostEqual(concrete_free_thermal_strain(800,aggregate='siliceous'),.014)
        self.assertAlmostEqual(concrete_free_thermal_strain(900,aggregate='calcareous'),.012)
        self.assertAlmostEqual(concrete_free_thermal_strain(805,aggregate='calcareous'),.012,delta=.00002)

    def test_rebar_thermal_strain_is_continuous_at_750_and_860(self):
        self.assertAlmostEqual(rebar_free_thermal_strain(20),0.,delta=1e-8)
        self.assertAlmostEqual(rebar_free_thermal_strain(750),.011,delta=.00002)
        self.assertAlmostEqual(rebar_free_thermal_strain(860),.011)
        self.assertAlmostEqual(rebar_free_thermal_strain(1200),.0178)

    def test_bad_values_and_unknown_aggregate_fail_closed(self):
        for bad in (-1,0,math.nan,math.inf,True,None):
            with self.assertRaises(EurocodeFireMaterialError):
                reinforcement_parameters(700,fyk_MPa=bad,Es_MPa=200000,
                      production_route='hot_rolled',ductility_class='C')
        with self.assertRaises(EurocodeFireMaterialError):
            concrete_parameters(100,aggregate='granite_ambiguous')
        with self.assertRaises(EurocodeFireMaterialError):
            concrete_parameters(19.9,aggregate='siliceous')
        with self.assertRaises(EurocodeFireMaterialError):
            concrete_stress(math.nan,500,fck_MPa=30,aggregate='siliceous')

if __name__=='__main__':unittest.main()
