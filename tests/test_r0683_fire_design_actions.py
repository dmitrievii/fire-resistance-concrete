"""R0.6.8.3: user supplies fire-design actions, without separate provenance blocker."""
import unittest
from multicolumn_r05.project_model import new_project, update_section
from rc_fire.normative.actions import (
    ACTION_INPUT_CONTRACT, DEFAULT_ACTION_PROVENANCE, action_source)
from rc_fire.normative.preflight import audit_column, evaluate_tabular_column_scope
from rc_fire.integration.r064d import sample_station_bundle, pending_member_evidence
from rc_fire.integration.r067 import build_uniform_fire_bundle, MemberEvidenceInputError
from rc_fire.member.uls import audit_heated_member_uls


class FireActionInputContractTests(unittest.TestCase):
    def test_preflight_no_fire_combination_blocker_even_without_source(self):
        p=new_project()
        c=p['columns'][0]
        update_section(p,'c1','center',{'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
        self.assertNotIn('fire_action_provenance',c)
        a=audit_column(c)
        codes={x['code'] for x in a['issues']}
        self.assertNotIn('NO_FIRE_LOAD_SOURCE',codes)
        self.assertNotIn('FIRE_ACTION_COMBINATION_NOT_QUALIFIED',codes)
        self.assertNotIn('INCOMPLETE_SECTION_ACTIONS',codes)
        self.assertTrue(a['resolved_inputs']['fire_actions_are_design_values'])
        self.assertFalse(a['resolved_inputs']['fire_combination_recalculated'])
        self.assertEqual(a['resolved_inputs']['fire_action_input_contract'],
                         ACTION_INPUT_CONTRACT)
        self.assertEqual(a['resolved_inputs']['fire_actions_source'],
                         DEFAULT_ACTION_PROVENANCE)
        self.assertFalse(a['normative_claim'])
        self.assertEqual(a['status'],'NOT_QUALIFIED')

    def test_incomplete_actions_still_block_without_source_requirement(self):
        p=new_project()
        a=audit_column(p['columns'][0])
        codes={x['code'] for x in a['issues']}
        self.assertIn('INCOMPLETE_SECTION_ACTIONS',codes)
        self.assertNotIn('NO_FIRE_LOAD_SOURCE',codes)

    def test_table_3_scope_no_external_load_combinations_needed(self):
        p=new_project()
        c=p['columns'][0]
        update_section(p,'c1','center',{'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
        c['effective_length_provenance']='user-entered mu values'
        c['N_Rd_normal_temperature_kN']=1000.
        x=evaluate_tabular_column_scope(c)
        self.assertNotIn('fire_action_provenance',x['missing'])
        self.assertNotIn('fire action: center',x['missing'])
        self.assertFalse(x['normative_approval'])

    def test_member_template_supplies_conventional_action_provenance(self):
        p=new_project()
        c=p['columns'][0]
        update_section(p,'c1','center',{'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
        template=sample_station_bundle(c)
        self.assertEqual(template['N_kN'],50.)
        self.assertEqual(template['fire_actions_source'],DEFAULT_ACTION_PROVENANCE)
        self.assertEqual(template['fire_action_input_contract'],ACTION_INPUT_CONTRACT)
        self.assertEqual(template['section_actions_reference_only'][0]['Mx_kNm'],3.)
        self.assertEqual(template['section_actions_reference_only'][0]['My_kNm'],2.)
        self.assertIsNone(template['distributed_load_kNpm'])
        self.assertFalse(pending_member_evidence()['normative_claim'])
        self.assertNotIn('FIRE_ACTIONS_AND_CONSTITUTIVE_QUALIFICATION_REQUIRED',
                         pending_member_evidence()['blockers'])

    def test_member_audit_no_source_blocker_for_explicit_N(self):
        result=audit_heated_member_uls(
            {'status':'not_evaluated'},[0.,3.],50.,action_provenance=None,
            material_provenance='diagnostic material status')
        self.assertEqual(result['status'],'MODEL_NOT_SOLVED')
        self.assertNotIn('FIRE_ACTIONS_NOT_DOCUMENTED',result['blockers'])
        self.assertFalse(result['normative_claim'])
        self.assertEqual(action_source(None),DEFAULT_ACTION_PROVENANCE)
        self.assertEqual(action_source('  custom trace  '),'custom trace')

    def test_missing_member_load_diagram_is_still_independently_blocked(self):
        p=new_project()
        c=p['columns'][0]
        update_section(p,'c1','center',{'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.})
        c['member_spec']={
            'thermal_longitudinal_mode':'uniform_assumed',
            'uniform_fire_basis':'explicitly uniform heating',
            'left_support':'pinned','right_support':'pinned',
            'load_mode':'not_defined'}
        with self.assertRaisesRegex(MemberEvidenceInputError,'MEMBER_LOAD_MODEL_REQUIRED'):
            build_uniform_fire_bundle(c)


if __name__=="__main__":
    unittest.main()
