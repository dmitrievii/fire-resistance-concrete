"""Independent integration safeguards for R0.6.4D."""
import copy
import unittest

from rc_fire.integration.r064d import (
  pending_member_evidence,sample_station_bundle,
  evaluate_explicit_member_bundle,attach_member_evidence,MemberEvidenceInputError)
from rc_fire.thermal import evaluate_rectangular_column
from tests.test_r063_mechanics import sample_column


class R064DRepositoryIntegration(unittest.TestCase):
    def setUp(self):
        self.c=sample_column()
        self.c['id']='column_r064d'
        self.c['length_m']=3.0
        self.c['fire_minutes']=0.0

    def test_nonmutating_facade_does_not_remove_legacy_results(self):
        legacy={'id':'c1','status':'calculated','results':{'legacy':'retained'},
                'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
        before=copy.deepcopy(legacy)
        merged=attach_member_evidence(legacy,expected_column=self.c)
        self.assertEqual(legacy,before)
        self.assertEqual(merged['results'],before['results'])
        self.assertEqual(merged['member_r064d']['status'],'NOT_EVALUATED')
        self.assertFalse(merged['normative_claim'])

    def test_preexisting_positive_claim_rejected_not_masked(self):
        with self.assertRaises(MemberEvidenceInputError):
            attach_member_evidence({'normative_claim':True})

    def test_incomplete_template_is_not_an_automatically_valid_fire_case(self):
        b=sample_station_bundle(self.c,node_count=3)
        self.assertEqual(len(b['gauss_stations']),2)
        self.assertEqual(len(b['gauss_stations'][0]),3)
        self.assertEqual(len(b['node_stations']),3)
        self.assertIsNone(b['gauss_stations'][0][0]['thermal'])
        with self.assertRaisesRegex(MemberEvidenceInputError,'explicit column'):
            evaluate_explicit_member_bundle(b,expected_column=self.c)

    def test_requires_temperature_at_every_gauss_and_node(self):
        b=sample_station_bundle(self.c,node_count=2)
        th=evaluate_rectangular_column(self.c,grid=12)
        self.assertIn(th['status'],('evaluated','evaluated_with_scope_warnings'))
        for row in b['gauss_stations']:
            for e in row:e['thermal']=th
        # Nodal data deliberately absent. No interpolation from Gauss stations.
        b['N_kN']=100
        with self.assertRaisesRegex(MemberEvidenceInputError,'explicit column'):
            evaluate_explicit_member_bundle(b,expected_column=self.c)

    def test_mixed_column_geometry_cannot_be_evaluated(self):
        b=self._valid()
        b['gauss_stations'][0][1]['column']=copy.deepcopy(self.c)
        b['gauss_stations'][0][1]['column']['b_mm']=800
        with self.assertRaisesRegex(MemberEvidenceInputError,'geometry/material'):
            evaluate_explicit_member_bundle(b,expected_column=self.c)

    def test_nonuniform_fire_times_cannot_be_smuggled_into_one_case(self):
        b=self._valid()
        b['node_stations'][1]['column']=copy.deepcopy(self.c)
        b['node_stations'][1]['column']['fire_minutes']=10.
        with self.assertRaisesRegex(MemberEvidenceInputError,'same fire-exposure time'):
            evaluate_explicit_member_bundle(b,expected_column=self.c)

    def test_actions_cannot_be_fabricated_as_zero(self):
        b=self._valid()
        b['N_kN']=None
        with self.assertRaisesRegex(MemberEvidenceInputError,'N_kN'):
            evaluate_explicit_member_bundle(b,expected_column=self.c)

    def test_length_and_nonfinite_rejected(self):
        b=self._valid()
        b['z_m']=[0.,float('nan')]
        with self.assertRaises(MemberEvidenceInputError):
            evaluate_explicit_member_bundle(b,expected_column=self.c)
        b['z_m']=[0.,2.0]
        with self.assertRaisesRegex(MemberEvidenceInputError,'length'):
            evaluate_explicit_member_bundle(b,expected_column=self.c)

    def test_conflicting_section_axial_load_is_rejected(self):
        b=self._valid()
        self.c['sections'][0]['N_kN']=150.
        for row in b['gauss_stations']:
            for e in row:e['column']['sections'][0]['N_kN']=150.
        for e in b['node_stations']:e['column']['sections'][0]['N_kN']=150.
        with self.assertRaisesRegex(MemberEvidenceInputError,'section axial loads'):
            evaluate_explicit_member_bundle(b,expected_column=self.c)

    def test_invalid_support_kind_is_rejected(self):
        b=self._valid();b['left_support']={'kind':'spring'}
        with self.assertRaises(MemberEvidenceInputError):
            evaluate_explicit_member_bundle(b,expected_column=self.c)

    def test_actual_complete_ambient_pipeline_never_reports_r90(self):
        b=self._valid()
        r=evaluate_explicit_member_bundle(b,expected_column=self.c)
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')
        self.assertEqual(r['integration_status'],'DIAGNOSTIC_ONLY')
        self.assertIn('status',r)
        self.assertNotEqual(r['status'],'PASS')
        self.assertTrue(r.get('material_audit',{}).get('blockers'))

    def test_heated_10min_pipeline_remains_diagnostic(self):
        self.c['fire_minutes']=10.0
        b=self._valid()
        r=evaluate_explicit_member_bundle(b,expected_column=self.c)
        self.assertFalse(r['normative_claim'])
        self.assertEqual(r['fire_resistance_status'],'not_demonstrated')
        self.assertEqual(r['integration_status'],'DIAGNOSTIC_ONLY')
        self.assertIn('HOT_CONCRETE_ULTIMATE_STRAIN_NOT_QUALIFIED',
                      r.get('material_audit',{}).get('blockers',[]))

    def test_heated_90min_blocks_800C_table_exceedance(self):
        self.c['fire_minutes']=90.0
        b=self._valid()
        r=evaluate_explicit_member_bundle(b,expected_column=self.c)
        self.assertEqual(r['status'],'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT')
        self.assertFalse(r['normative_claim'])

    def test_every_material_station_has_provenance_and_blockers(self):
        b=self._valid()
        r=evaluate_explicit_member_bundle(b,expected_column=self.c)
        self.assertEqual(r['thermal_station_count'],5)
        self.assertGreaterEqual(len(r['material_audit']['stations']),5)
        self.assertIn('SECTION_CONSTITUTIVE_LAW_NOT_NORMATIVELY_QUALIFIED',
                      r['material_audit']['blockers'])

    def _valid(self):
        for sec in self.c.get('sections',[]):sec['N_kN']=100.
        b=sample_station_bundle(self.c,node_count=2)
        th=evaluate_rectangular_column(self.c,grid=12)
        self.assertIn(th['status'],('evaluated','evaluated_with_scope_warnings'))
        for row in b['gauss_stations']:
            for e in row:e['thermal']=th
        for e in b['node_stations']:e['thermal']=th
        b['N_kN']=100.
        b['fire_actions_source']='externally given test action (NOT verified fire combination)'
        b['grid']=12
        return b


if __name__=='__main__':unittest.main()
