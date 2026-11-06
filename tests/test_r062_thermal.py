"""R0.6.2 tests: independent Annex K equation anchors and fail-closed limits."""
import math
import unittest

import numpy as np
from rc_fire.thermal import (
    TABLE_K1, TABLE_K2, ThermalError, ThermalProfile, RectangularExposure,
    resolve_profile, property_K1, heating_depth_m, temperature_rectangle,
    critical_temperature_C, square_four_face_reduced_section,
    evaluate_rectangular_column,
)


class AnnexKThermalTests(unittest.TestCase):
    def setUp(self):
        self.profile=ThermalProfile('siliceous',2400.)
        self.coeff=resolve_profile(self.profile)
        self.square=RectangularExposure(600.,600.,('left','right','bottom','top'))

    def test_K1_K2_exact_and_no_extrapolation(self):
        self.assertAlmostEqual(self.coeff['a_red_m2_h'],.00133)
        self.assertAlmostEqual(self.coeff['phi_1'],.63)
        self.assertAlmostEqual(self.coeff['phi_2'],.5)
        self.assertTrue(self.coeff['normative_table_nodes'])
        self.assertEqual(TABLE_K1['calcareous']['a_red_m2_h'],.00116)
        self.assertEqual(TABLE_K1['expanded_clay']['a_red_m2_h'],.000734)
        with self.assertRaises(ThermalError):resolve_profile(ThermalProfile('siliceous',2500))
        intermediate=resolve_profile(ThermalProfile('siliceous',1850))
        self.assertAlmostEqual(intermediate['phi_1'],.60)
        self.assertFalse(intermediate['normative_table_nodes'])

    def test_K1_formula_uses_hours_and_water_mass_percent(self):
        c=resolve_profile(ThermalProfile('siliceous',2400.,'formula_K1_450C',2.5))
        expect=3.6*(1.2-.00035*450)/((.71+.00083*450+.05*2.5)*2400)
        self.assertAlmostEqual(c['a_red_m2_h'],expect,places=12)
        self.assertAlmostEqual(property_K1('calcareous',450)['lambda_W_mK'],1.14-.00055*450)
        with self.assertRaises(ThermalError):
            resolve_profile(ThermalProfile('siliceous',2400.,'table_K1',3.0))

    def test_K12_length_and_zero_heat(self):
        self.assertAlmostEqual(heating_depth_m(.00133,90),math.sqrt(12*.00133*1.5))
        z,meta=temperature_rectangle(self.square,self.coeff,0.,[0,100,300],[0,100,300])
        self.assertTrue(np.all(z==20.))
        with self.assertRaises(ThermalError):heating_depth_m(.00133,-1)
        with self.assertRaises(ThermalError):heating_depth_m(.00133,300)

    def test_K6_one_side_and_0_7_depth_domain(self):
        e=RectangularExposure(600,600,('left',))
        l=math.sqrt(12*.00133*1.5)
        rel=min(1.,(.06+.63*math.sqrt(.00133))/l)
        a,m=temperature_rectangle(e,self.coeff,90,60,300)
        self.assertAlmostEqual(float(a),20+1200*(1-rel)**2,places=7)
        self.assertEqual(m['K_equation'],'К.6')
        self.assertTrue(bool(m['in_one_face_0_7h']))
        _,m2=temperature_rectangle(e,self.coeff,90,480,300)
        self.assertFalse(bool(m2['in_one_face_0_7h']))

    def test_K7_two_parallel_and_K8_perpendicular(self):
        e=RectangularExposure(600,600,('left','right'))
        t,m=temperature_rectangle(e,self.coeff,90,150,210)
        l=heating_depth_m(.00133,90)
        a=lambda d:(1-min(1.,(d+.63*math.sqrt(.00133))/l))**2
        self.assertAlmostEqual(float(t),20+1200*(a(.150)+a(.450)))
        self.assertEqual(m['K_equation'],'К.7')
        e=RectangularExposure(600,600,('left','bottom'))
        t,m=temperature_rectangle(e,self.coeff,90,40,60)
        self.assertAlmostEqual(float(t),1220-1200*(1-a(.04))*(1-a(.06)))
        self.assertEqual(m['K_equation'],'К.8')

    def test_K9_three_and_K10_four(self):
        x=.04;y=.06
        a=lambda d:(1-min(1.,(d+.63*math.sqrt(.00133))/heating_depth_m(.00133,90)))**2
        t,m=temperature_rectangle(RectangularExposure(600,600,('left','right','bottom')),
                                  self.coeff,90,40,60)
        self.assertAlmostEqual(float(t),1220-1200*(1-a(x)-a(.6-x))*(1-a(y)))
        self.assertEqual(m['K_equation'],'К.9')
        t,m=temperature_rectangle(self.square,self.coeff,90,40,60)
        self.assertAlmostEqual(float(t),1220-1200*(1-a(x)-a(.6-x))*(1-a(y)-a(.6-y)))
        self.assertEqual(m['K_equation'],'К.10')

    def test_K5_rebar_outer_surface_and_individual_diameters(self):
        ex=self.square
        d=.02
        l=heating_depth_m(.00133,90)
        reff=(.04-d/2+.63*math.sqrt(.00133)+.5*d)/l
        p=(1-min(1.,reff))**2
        temp,m=temperature_rectangle(ex,self.coeff,90,40,40,20)
        self.assertAlmostEqual(float(temp),1220-1200*(1-p)**2)
        # With phi2=0.5 (2400 kg/m3), -d/2+phi2*d cancels exactly
        # under the standard interpretation of y_i as bar-surface depth.
        other,_=temperature_rectangle(ex,self.coeff,90,40,40,40)
        self.assertAlmostEqual(float(temp),float(other))
        light=resolve_profile(ThermalProfile('siliceous',1400.))
        t20,_=temperature_rectangle(ex,light,90,40,40,20)
        t40,_=temperature_rectangle(ex,light,90,40,40,40)
        self.assertNotAlmostEqual(float(t20),float(t40))
        with self.assertRaises(ThermalError):
            temperature_rectangle(ex,self.coeff,90,8,40,20)

    def test_K20_K22_K27_K28_square_area(self):
        self.assertEqual(critical_temperature_C('C30/37','siliceous'),500)
        self.assertEqual(critical_temperature_C('C30/37','calcareous'),600)
        self.assertEqual(critical_temperature_C('C60/75','siliceous'),460)
        self.assertEqual(critical_temperature_C('C80/95','siliceous'),400)
        self.assertIsNone(critical_temperature_C('C90/105','siliceous'))
        r=square_four_face_reduced_section(self.square,self.coeff,90,500)
        self.assertEqual(r['status'],'evaluated')
        self.assertTrue(0<r['remaining_area_m2']<.36)
        self.assertAlmostEqual(r['remaining_area_m2'],r['psi']*(.6-2*r['lc_m'])**2)
        self.assertAlmostEqual(r['lost_area_m2']+r['remaining_area_m2'],.36)
        r2=square_four_face_reduced_section(RectangularExposure(600,400,('left','right','bottom','top')),
                                             self.coeff,90,500)
        self.assertEqual(r2['status'],'not_applicable')

    def test_K18_temperature_crosscheck_and_corrected_K24(self):
        """Independent K18 90 min benchmark; new K.24 uses 1200w, not 1220w."""
        corner,_=temperature_rectangle(self.square,self.coeff,90,50,50,25)
        middle,_=temperature_rectangle(self.square,self.coeff,90,250,50,25)
        self.assertAlmostEqual(float(corner),596.4654931806213,places=6)
        self.assertAlmostEqual(float(middle),354.99051555300593,places=6)
        reduced=square_four_face_reduced_section(self.square,self.coeff,90,500)
        l=heating_depth_m(.00133,90)
        expected_r3=1-math.sqrt(500/1200)  # w=1, K.24 denominator = 1200w
        legacy_r3=1-math.sqrt(500/1220)    # deprecated K18 denominator
        self.assertAlmostEqual(reduced['r3'],expected_r3,places=12)
        self.assertGreater(abs(reduced['r3']-legacy_r3),.004)
        self.assertAlmostEqual(reduced['delta_m'],expected_r3*l-.63*math.sqrt(.00133))

    def test_annex_Zh_is_separate_route_not_falsely_forced_equal(self):
        """Table Ж.6 (400 mm R60) and Annex K are distinct approved methods."""
        e=RectangularExposure(400,400,('left','right','bottom','top'))
        analytic,_=temperature_rectangle(e,self.coeff,60,0,0)
        tabulated_Zh6_400_R60_corner=933.0  # Table Ж.6, PDF p.125
        self.assertAlmostEqual(float(analytic),1088.8005,delta=0.2)
        self.assertGreater(float(analytic)-tabulated_Zh6_400_R60_corner,150)

    def test_profile_covers_material_and_column(self):
        bars=[{'id':f'B{i}','x_mm':x,'y_mm':y,'diameter_mm':20}
              for i,(x,y) in enumerate([(40,40),(300,40),(560,40),(40,300),(560,300),(40,560),(300,560),(560,560)])]
        c={'concrete':'C30/37','b_mm':600,'h_mm':600,'fire_minutes':90,'bars':bars,
           'material_spec':{'concrete':{'aggregate_family':'siliceous'}},
           'thermal_spec':{'a_red_mode':'table_K1','dry_density_kg_m3':2400,
                           'exposed_faces':['left','right','bottom','top']}}
        out=evaluate_rectangular_column(c,24)
        self.assertEqual(out['status'],'evaluated')
        self.assertFalse(out['qualified_mechanics'])
        self.assertEqual(len(out['reinforcement']),8)
        self.assertEqual(out['critical_temperature_C'],500)
        self.assertEqual(out['critical_section']['status'],'evaluated')
        self.assertEqual(out['field']['grid'],24)
        self.assertAlmostEqual(out['reinforcement'][0]['theta_C'],out['reinforcement'][2]['theta_C'])
        c['thermal_spec'].pop('dry_density_kg_m3')
        self.assertEqual(evaluate_rectangular_column(c)['status'],'not_evaluated')
        c['thermal_spec']['dry_density_kg_m3']=2400
        c['thermal_spec']['concrete_family']='calcareous'
        self.assertEqual(evaluate_rectangular_column(c)['status'],'invalid')

    def test_rectangular_and_one_face_scope_disclosed(self):
        c={'concrete':'C30/37','b_mm':600,'h_mm':400,'fire_minutes':90,
           'bars':[{'id':'B1','x_mm':550,'y_mm':30,'diameter_mm':20}],
           'thermal_spec':{'concrete_family':'siliceous','dry_density_kg_m3':2400,
                           'exposed_faces':['left']}}
        out=evaluate_rectangular_column(c,10)
        self.assertEqual(out['status'],'evaluated_with_scope_warnings')
        self.assertEqual(out['critical_section']['status'],'not_applicable')
        self.assertTrue(any('К.6' in note for note in out['issues']))
        self.assertEqual(out['reinforcement'][0]['in_scope_K6'],False)

    def test_no_extrapolation_and_invalid_options(self):
        with self.assertRaises(ThermalError):
            temperature_rectangle(self.square,self.coeff,90,-1,0)
        with self.assertRaises(ThermalError):
            temperature_rectangle(RectangularExposure(600,600,('left','left')),self.coeff,90,20,20)
        with self.assertRaises(ThermalError):
            temperature_rectangle(self.square,self.coeff,90,30,30,-20)
        self.assertEqual(evaluate_rectangular_column({'thermal_spec':{}},20)['status'],'not_evaluated')

if __name__=='__main__':unittest.main()