"""R0.6.9B: literal §8.2.21 applicability and K.27 area provenance."""
import copy
import math
import unittest
from unittest.mock import patch

from multicolumn_r05.project_model import (
    new_project, update_column, update_thermal_spec, update_material_spec,
    update_section,
)
from rc_fire.mechanics.critical_isotherm import (
    evaluate_critical_isotherm_section, evaluate_critical_isotherm_history,
    _action_plane, _bar_layout_scope, VERSION,
)


def case(*, minutes=90., mx=4., my=0., two_layers=True):
    p=new_project()
    update_column(p,'c1',{'fire_minutes':minutes})
    update_material_spec(p,'c1',{'concrete':{
        'aggregate_family':'siliceous','consistency':'S3_S5',
        'curing':'natural','modulus_aggregate':'gravel_granite_upto40'},
        'steel':{'product_type':'weldable_bar'}})
    update_thermal_spec(p,'c1',{'concrete_family':'siliceous',
        'dry_density_kg_m3':2400.,
        'exposed_faces':['left','right','bottom','top']})
    update_section(p,'c1','center',{'N_kN':100.,'Mx_kNm':mx,'My_kNm':my})
    c=p['columns'][0]
    if two_layers:
        # True 2-face reinforcement, mirrored in both axes. No side-centre bars.
        c['bars']=[
            {'id':'S1','x_mm':40.,'y_mm':40.,'diameter_mm':20.},
            {'id':'S2','x_mm':560.,'y_mm':40.,'diameter_mm':20.},
            {'id':'S3','x_mm':40.,'y_mm':560.,'diameter_mm':20.},
            {'id':'S4','x_mm':560.,'y_mm':560.,'diameter_mm':20.},
        ]
    return c


class CriticalIsothermScopeTests(unittest.TestCase):
    def test_true_uniaxial_two_layer_candidate_at_90(self):
        c=case()
        r=evaluate_critical_isotherm_section(c,grid=40)
        self.assertEqual(r['version'], VERSION)
        self.assertEqual(r['status'],'K27_SECTION_SCOPE_CANDIDATE_DIAGNOSTIC',r)
        self.assertEqual(r['scope']['bending_axis'],'x')
        self.assertTrue(r['scope']['conditions_8_2_21_verified'])
        self.assertGreater(r['remaining_area_m2'],0)
        self.assertLess(r['remaining_area_m2'],.36)
        self.assertAlmostEqual(
            r['remaining_area_m2'],
            r['analytic_K27']['psi']*(.6-2*r['analytic_K27']['lc_m'])**2,
            places=9)
        self.assertEqual(len(r['bar_evidence']),4)
        self.assertGreater(r['N_optimistic_upper_kN'],0)
        self.assertEqual(r['axial_necessary_condition'],'NOT_VIOLATED_NO_STRENGTH_PROOF')
        self.assertIsNone(r['N_Rd_kN'])
        self.assertIsNone(r['R_t_minutes'])
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

    def test_real_default_eight_perimeter_bars_are_not_two_face_reinforcement(self):
        c=case(two_layers=False)
        r=evaluate_critical_isotherm_section(c)
        self.assertEqual(r['status'],'K27_GEOMETRY_ONLY_SECTION_SCOPE_BLOCKED')
        self.assertIn('REINFORCEMENT_NOT_IN_TWO_EXTREME_FACE_LAYERS',r['blockers'])
        self.assertIsNone(r['N_optimistic_upper_kN'])
        self.assertGreater(r['remaining_area_m2'],0)

    def test_real_biaxial_actions_keep_geometric_area_only(self):
        c=case(my=2.)
        r=evaluate_critical_isotherm_section(c)
        self.assertEqual(r['status'],'K27_GEOMETRY_ONLY_SECTION_SCOPE_BLOCKED')
        self.assertIn('BIAXIAL_OR_MIXED_AXIS_BENDING_OUTSIDE_8_2_21',r['blockers'])
        self.assertFalse(r['scope']['conditions_8_2_21_verified'])
        self.assertIsNone(r['N_Rd_kN'])
        self.assertGreater(r['remaining_area_m2'],0)

    def test_missing_actions_do_not_become_zero_and_pure_axial_not_inferred(self):
        c=case(mx=0.)
        r=evaluate_critical_isotherm_section(c)
        self.assertIn('BENDING_SYMMETRY_PLANE_NOT_ESTABLISHED_PURE_AXIAL',r['blockers'])
        c['sections'][0]['My_kNm']=None
        self.assertIn('SECTION_0_ACTION_INCOMPLETE_OR_INVALID',
                      evaluate_critical_isotherm_section(c)['blockers'])

    def test_square_four_face_formula_does_not_cover_rectangles_or_3_faces(self):
        c=case()
        c['b_mm']=650.
        self.assertIn('K27_REQUIRES_SQUARE_SECTION',
                      evaluate_critical_isotherm_section(c)['blockers'])
        c=case()
        c['thermal_spec']['exposed_faces']=['left','right','bottom']
        self.assertIn('K27_REQUIRES_FOUR_HEATED_FACES',
                      evaluate_critical_isotherm_section(c)['blockers'])

    def test_unmirrored_or_extra_bar_layer_is_blocked(self):
        c=case()
        c['bars'][3]['x_mm']-=10.
        self.assertIn('REINFORCEMENT_MIRROR_SYMMETRY_NOT_VERIFIED',
                      _bar_layout_scope(c,'x'))
        c=case()
        c['bars'].append({'id':'S5','x_mm':40.,'y_mm':300.,'diameter_mm':20.})
        self.assertIn('REINFORCEMENT_NOT_IN_TWO_EXTREME_FACE_LAYERS',
                      _bar_layout_scope(c,'x'))

    def test_force_plane_checks_every_section_and_flags_axis_mixing(self):
        c=case()
        c['sections'].append({'id':'top','N_kN':100.,'Mx_kNm':0.,'My_kNm':2.})
        axis,issues=_action_plane(c)
        self.assertIsNone(axis)
        self.assertIn('BIAXIAL_OR_MIXED_AXIS_BENDING_OUTSIDE_8_2_21',issues)

    def test_above_800_bar_temperature_does_not_get_extrapolated(self):
        c=case()
        # Keep symmetric two extreme layers, move them close to fire.
        for bar in c['bars']:
            bar['x_mm']=15. if bar['x_mm']<300 else 585.
            bar['y_mm']=15. if bar['y_mm']<300 else 585.
            bar['diameter_mm']=10.
        r=evaluate_critical_isotherm_section(c)
        self.assertEqual(r['status'],'K27_GEOMETRY_ONLY_STRENGTH_UNRESOLVED',r)
        self.assertIn('MATERIAL_OR_REINFORCEMENT_TABLE_UNRESOLVED',r['blockers'])
        self.assertIsNone(r['N_optimistic_upper_kN'])
        self.assertGreater(r['remaining_area_m2'],0)

    def test_temperature_time_mismatch_prevents_stale_field_reuse(self):
        c=case()
        from rc_fire.thermal import evaluate_rectangular_column
        th=evaluate_rectangular_column(c,grid=40)
        c['fire_minutes']=60.
        r=evaluate_critical_isotherm_section(c,grid=40,thermal=th)
        self.assertIn('THERMAL_TIME_OR_EXPOSURE_MISMATCH',r['blockers'])

    def test_history_is_immutable_and_cannot_infer_R_t(self):
        c=case()
        original=copy.deepcopy(c)
        hist=evaluate_critical_isotherm_history(c,step_minutes=30.,grid=40)
        self.assertEqual(hist['status'],'DIAGNOSTIC_TIME_SERIES_ONLY')
        self.assertEqual([s['time_minutes'] for s in hist['samples']],[1.,30.,60.,90.])
        self.assertEqual(c,original)
        self.assertFalse(hist['normative_claim'])
        self.assertIsNone(hist['R_t_minutes'])
        self.assertEqual(hist['fire_resistance_status'],'not_demonstrated')

    def test_model_never_promotes_a_favourable_axial_ceiling_to_N_Rd(self):
        c=case()
        c['sections'][0]['N_kN']=1.
        r=evaluate_critical_isotherm_section(c)
        self.assertEqual(r['status'],'K27_SECTION_SCOPE_CANDIDATE_DIAGNOSTIC',r)
        self.assertGreater(r['N_optimistic_upper_kN']/c['sections'][0]['N_kN'],1.)
        self.assertIsNone(r['N_Rd_kN'])
        self.assertFalse(r['normative_claim'])


if __name__ == '__main__':
    unittest.main()
