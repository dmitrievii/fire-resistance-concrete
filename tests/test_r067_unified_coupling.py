"""R0.6.7 independent evidence, coupling and backward-compatibility tests."""
import copy
import json
import unittest

from multicolumn_r05.project_model import (new_project, update_column, update_section,
    update_thermal_spec, update_material_spec, update_member_spec, export_json, load_json,
    validate_column)
from multicolumn_r05.project_calculator import evaluate_column
from rc_fire.materials import resolve_materials
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.normative import audit_column, prevent_normative_claim, NormativeQualificationError
from rc_fire.integration.r064d import _signature, MemberEvidenceInputError
from rc_fire.integration.r067 import (build_uniform_fire_bundle,
    evaluate_uniform_fire_member, validate_member_spec, VERSION)


def prepared_column(*, time=10., N=100., Mx=0., My=0.):
    p=new_project()
    update_thermal_spec(p,'c1',{'concrete_family':'siliceous',
        'dry_density_kg_m3':2400.,'exposed_faces':['left','right','bottom','top']})
    update_material_spec(p,'c1',{'concrete':{'aggregate_family':'siliceous',
        'consistency':'S3_S5','curing':'natural',
        'modulus_aggregate':'gravel_granite_upto40','fine_grained':False},
        'steel':{'product_type':'weldable_bar'}})
    update_column(p,'c1',{'fire_minutes':float(time)})
    update_section(p,'c1','center',{'N_kN':N,'Mx_kNm':Mx,'My_kNm':My})
    return p


def configured(p, mode='axial_only', **kwargs):
    fields={'thermal_longitudinal_mode':'uniform_assumed',
        'uniform_fire_basis':'same exposed faces, atmosphere and surface coefficients for entire length',
        'left_support':'pinned','right_support':'pinned',
        'support_provenance':'explicit idealized pinned supports, not yet structurally verified',
        'load_mode':mode,'fire_actions_source':'user supplied actions, fire combination not qualified',
        'node_count':2}
    fields.update(kwargs)
    update_member_spec(p,'c1',fields)
    return p['columns'][0]


class R067CouplingTests(unittest.TestCase):
    def test_unconfigured_is_fail_closed_and_does_not_invent_heating(self):
        p=prepared_column()
        c=p['columns'][0]
        self.assertEqual(c['member_spec']['thermal_longitudinal_mode'],'explicit_only')
        with self.assertRaisesRegex(MemberEvidenceInputError,'UNIFORM_HEATING_ASSUMPTION_REQUIRED'):
            build_uniform_fire_bundle(c)
        r=evaluate_uniform_fire_member(c)
        self.assertEqual(r['status'],'BLOCKED_INPUT')
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

    def test_real_K_field_is_reused_by_declared_uniformity_only(self):
        p=prepared_column()
        c=configured(p)
        th=evaluate_rectangular_column(c,grid=12)
        b=build_uniform_fire_bundle(c,thermal=th)
        self.assertEqual(len(b['node_stations']),2)
        self.assertEqual(len(b['gauss_stations']),1)
        self.assertEqual(len(b['gauss_stations'][0]),3)
        self.assertTrue(all(x['thermal']['status'] in ('evaluated','evaluated_with_scope_warnings')
                for x in b['node_stations']+b['gauss_stations'][0]))
        self.assertEqual(b['distributed_load_kNpm'],[[0.,0.],[0.,0.]])
        self.assertEqual(b['left_support']['kind'],'pinned')
        self.assertEqual(b['right_support']['kind'],'pinned')
        self.assertEqual(b['N_kN'],100.)
        self.assertEqual(b['temperature_time_minutes'],10.)
        self.assertEqual(b['r067_assumptions']['longitudinal_temperature_model'],
                         'uniform_cross_section_user_assumed')
        self.assertTrue(b['r067_assumptions']['temperature_source_sha256'])
        self.assertFalse(b['r067_assumptions']['normative_claim'])
        self.assertFalse(b['r067_assumptions']['section_moments_not_converted_to_transverse_loads'] is False)

    def test_explicit_transverse_load_not_derived_from_section_moments(self):
        p=prepared_column(Mx=3.,My=2.)
        c=configured(p,mode='uniform_transverse_load',q_x_kNpm=1.25,q_y_kNpm=-0.5)
        b=build_uniform_fire_bundle(c)
        self.assertEqual(b['distributed_load_kNpm'],[[1.25,-.5],[1.25,-.5]])
        self.assertEqual(b['section_actions_reference_only'][0]['Mx_kNm'],3.)
        self.assertEqual(b['section_actions_reference_only'][0]['My_kNm'],2.)
        self.assertTrue(b['r067_assumptions']['section_moments_not_converted_to_transverse_loads'])

    def test_axial_only_refuses_nonzero_section_moment(self):
        p=prepared_column(Mx=3.,My=2.)
        c=configured(p)
        with self.assertRaisesRegex(MemberEvidenceInputError,'AXIAL_ONLY_CONFLICTS'):
            build_uniform_fire_bundle(c)

    def test_unconfirmed_supports_and_uniform_basis_are_blocked(self):
        p=prepared_column()
        c=configured(p)
        update_member_spec(p,'c1',{'uniform_fire_basis':None})
        with self.assertRaisesRegex(MemberEvidenceInputError,'uniform_fire_basis'):
            build_uniform_fire_bundle(c)
        update_member_spec(p,'c1',{'uniform_fire_basis':'all faces exposed',
                                  'left_support':None})
        with self.assertRaisesRegex(MemberEvidenceInputError,'both physical end'):
            build_uniform_fire_bundle(c)

    def test_inconsistent_n_is_not_silently_averaged(self):
        p=prepared_column()
        c=configured(p)
        c['sections'].append({'id':'other','z_m':2.5,'N_kN':120.,
                              'Mx_kNm':0.,'My_kNm':0.})
        with self.assertRaisesRegex(MemberEvidenceInputError,'CONSTANT_N_REQUIRED'):
            build_uniform_fire_bundle(c)

    def test_stale_temperatures_mismatched_time_rejected(self):
        p=prepared_column()
        c=configured(p)
        th=evaluate_rectangular_column(c,grid=12)
        c['fire_minutes']=20.
        with self.assertRaisesRegex(MemberEvidenceInputError,'fire time differs'):
            build_uniform_fire_bundle(c,thermal=th)

    def test_input_validation_and_member_result_cache_signature(self):
        p=prepared_column()
        c=p['columns'][0]
        sig=_signature(c)
        configured(p)
        self.assertNotEqual(sig,_signature(c))
        with self.assertRaises(MemberEvidenceInputError):
            validate_member_spec({'q_x_kNpm':float('nan')})
        with self.assertRaises(MemberEvidenceInputError):
            validate_member_spec({'arbitrary_option':'yes'})
        with self.assertRaises(MemberEvidenceInputError):
            validate_member_spec({'node_count':1})

    def test_preflight_current_canonical_values_no_obsolete_false_blockers(self):
        p=prepared_column()
        c=configured(p)
        mat=resolve_materials(c)
        th=evaluate_rectangular_column(c,grid=12)
        audit=audit_column(c,material_result=mat,thermal_result=th)
        self.assertEqual(audit['status'],'NOT_QUALIFIED')
        codes={x['code'] for x in audit['issues']}
        for old in ('ASSUMED_FOUR_SIDES','E_CM_NOT_PROVEN','MATERIAL_THERMAL_SCOPE_MISSING',
                    'INCOMPLETE_SECTION_ACTIONS','NO_FIRE_LOAD_SOURCE'):
            self.assertNotIn(old,codes)
        self.assertIn('R060_CONTRACT_ONLY',codes)
        self.assertIn('EXPOSURE_PHYSICAL_PROVENANCE_MISSING',codes)
        self.assertIn('FIRE_ACTION_COMBINATION_NOT_QUALIFIED',codes)
        self.assertEqual(audit['scope_check']['temperature_C'],500)
        self.assertEqual(audit['resolved_inputs']['exposed_faces'],['left','right','bottom','top'])
        self.assertIsNotNone(audit['resolved_inputs']['E_cm_GPa'])
        self.assertFalse(audit['normative_claim'])
        with self.assertRaises(NormativeQualificationError):
            prevent_normative_claim(audit)

    def test_preflight_auto_resolves_kind_but_blocks_real_mix_conflict(self):
        p=prepared_column()
        c=p['columns'][0]
        c['material_spec']['concrete']['fine_grained']=True
        normal=resolve_materials(c)
        self.assertIs(normal['fine_grained_classification']['fine_grained'],False)
        c['annex_l_spec']={'coarse_aggregate_volume_pct':0.}
        a=audit_column(c,material_result=resolve_materials(c),
                       thermal_result=evaluate_rectangular_column(c,grid=12))
        code={x['code']:x for x in a['issues']}
        self.assertIn('MATERIAL_MIX_CONFLICT',code)
        self.assertEqual(code['MATERIAL_MIX_CONFLICT']['severity'],'BLOCKER')
        self.assertFalse(a['normative_claim'])

    def test_project_json_roundtrip_persists_explicit_assumptions(self):
        p=prepared_column()
        configured(p)
        q=load_json(export_json(p))
        self.assertEqual(q['columns'][0]['member_spec'],
                         p['columns'][0]['member_spec'])
        self.assertFalse(validate_column(q['columns'][0]))
        # Existing project JSONs without member_spec remain usable.
        legacy=copy.deepcopy(q)
        legacy['columns'][0].pop('member_spec')
        parsed=load_json(json.dumps(legacy).encode())
        self.assertNotIn('member_spec',parsed['columns'][0])

    def test_heated_90min_remains_blocked_above_property_table(self):
        p=prepared_column(time=90.)
        c=configured(p)
        r=evaluate_uniform_fire_member(c)
        self.assertEqual(r['status'],'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT',r)
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

    def test_integrated_10min_diagnostic_never_r90(self):
        p=prepared_column(time=10.)
        c=configured(p)
        r=evaluate_uniform_fire_member(c)
        self.assertIn(r['status'],('SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS',
                                  'DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED',
                                  'INSUFFICIENT_ULS_EVIDENCE',
                                  'MODEL_NOT_SOLVED',
                                  'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT'),r)
        self.assertIn('r067_assumptions',r)
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')

    def test_calculation_facade_uses_resolved_preflight(self):
        p=prepared_column(time=10.)
        r=evaluate_column(p['columns'][0],grid=48)
        a=r['normative_preflight']
        self.assertEqual(a['resolved_inputs']['thermal_status'],r['thermal_normative']['status'])
        self.assertEqual(a['resolved_inputs']['material_status'],r['material_preflight']['status'])
        self.assertNotIn('ASSUMED_FOUR_SIDES',{x['code'] for x in a['issues']})
        self.assertFalse(r['normative_claim'])


if __name__=="__main__":
    unittest.main()
