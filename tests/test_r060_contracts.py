"""Source, scope, provenance and fail-closed acceptance for R0.6.0."""
import json
import unittest
from pathlib import Path
from rc_fire.normative import (
    validate_contract_registry, frozen_contract_manifest, contract_sha256,
    methods_for_route, audit_column, select_critical_isotherm,
    evaluate_tabular_column_scope, prevent_normative_claim,
    NormativeQualificationError, LEGACY_INVENTORY, STRUCTURE_CAPABILITIES,
    validate_normative_result_provenance,
)

ROOT = Path(__file__).resolve().parents[1]

def column():
    return {
        "id": "c1", "name": "К1", "concrete":"C30/37",
        "b_mm":600., "h_mm":600., "length_m":3.,
        "mu_x":1.,"mu_y":1.,
        "bars":[{"diameter_mm":20} for _ in range(8)],
        "spalling":{"method":"sp468"},
        "sections":[{"id":"bottom","N_kN":500,"Mx_kNm":10,"My_kNm":4},
                    {"id":"top","N_kN":510,"Mx_kNm":12,"My_kNm":5}],
    }

class R060ContractTests(unittest.TestCase):
    def test_contract_version_source_and_lock(self):
        validate_contract_registry()
        manifest = frozen_contract_manifest()
        lock = json.loads((ROOT/"R060_CONTRACT_LOCK.json").read_text())
        self.assertEqual(lock["contract_sha256"],contract_sha256())
        self.assertEqual(lock["contract_version"],manifest["contract_version"])
        self.assertEqual(manifest["qualification"],"NOT_QUALIFIED_CONTRACTS_ONLY")
        sources={s["id"]:s for s in manifest["sources"]}
        self.assertEqual(sources["BY_SP_FIRE_2026"]["effective_from"],"2026-11-01")
        self.assertEqual(sources["BY_TKP_FIRE_2008"]["superseded_by"],"BY_SP_FIRE_2026")
        self.assertEqual(sources["RU_SP468"]["role"],"comparison_only")
        self.assertFalse(sources["BY_SN_LOADS_2019"]["supplied"])
        for m in manifest["methods"]:
            self.assertEqual(m["implementation"],"contract_only")
            self.assertNotIn(m["primary_source"],("RU_SP468","XMCD_K18","BY_TKP_FIRE_2008"))

    def test_legacy_inventory_and_structure_architecture(self):
        self.assertEqual(len(LEGACY_INVENTORY), 17)
        ids={x.id for x in LEGACY_INVENTORY}
        self.assertIn("XMCD-13",ids)
        self.assertIn("XMCD-17",ids)
        self.assertTrue(all(x.target_method for x in LEGACY_INVENTORY))
        caps={x.id:x for x in STRUCTURE_CAPABILITIES}
        self.assertEqual(caps["column_rectangular"].stage,"DIAGNOSTIC_ONLY")
        self.assertTrue(all(x.stage=="PLANNED" for x in STRUCTURE_CAPABILITIES
                            if x.id != "column_rectangular"))

    def test_provenance_requires_executable_method_and_correct_owner(self):
        record=dict(source_id="BY_SP_RC_2020",source_clause="8.1.2",
                    method_id="SECTION_ULS",backend_version="R0.6.0",
                    input_sha256="0"*64,applicability="NOT_QUALIFIED",
                    qualification="CONTRACT_ONLY",units="SI")
        validate_normative_result_provenance(record)
        with self.assertRaises(ValueError):
            validate_normative_result_provenance({**record,"source_id":"RU_SP468"})
        with self.assertRaises(ValueError):
            validate_normative_result_provenance({**record,"qualification":"CERTIFIED"})
        with self.assertRaises(ValueError):
            validate_normative_result_provenance({**record,"units":""})

    def test_contract_paths_have_single_owners(self):
        general={m.id for m in methods_for_route("general_member")}
        tabular={m.id for m in methods_for_route("table_3_column")}
        self.assertIn("SECTION_ULS",general)
        self.assertNotIn("SECTION_ULS",tabular)
        self.assertIn("COLUMN_TABLE_3",tabular)
        self.assertNotIn("COLUMN_TABLE_3",general)
        self.assertIn("SPALLING_ANNEX_L",general & tabular)
        self.assertNotIn("CRITICAL_ISOTHERM",general) # optional, not universally valid
        with self.assertRaises(ValueError): methods_for_route("legacy_k18")

    def test_no_unsupported_critical_temperature_default(self):
        self.assertIsNone(select_critical_isotherm("C30/37",None)["temperature_C"])
        for klass,agg,expected in [("C30/37","siliceous",500),("C30/37","calcareous",600),
                                   ("C55/67","siliceous",460),("C60/75","calcareous",460),
                                   ("C70/85","siliceous",400),("C80/95","calcareous",400)]:
            r=select_critical_isotherm(klass,agg,"heavy")
            self.assertEqual(r["temperature_C"],expected,(klass,agg))
            self.assertEqual(r["status"],"MATERIAL_CRITERION_ONLY")
        self.assertIsNone(select_critical_isotherm("C90/105","calcareous","heavy")["temperature_C"])
        self.assertIsNone(select_critical_isotherm("C30/37","calcareous","lightweight")["temperature_C"])

    def test_table_three_scope_is_strict(self):
        c=column()
        s=evaluate_tabular_column_scope(c)
        self.assertEqual(s["status"],"INCOMPLETE")
        self.assertFalse(s["normative_approval"])
        c["length_m"]=3.01
        self.assertIn("effective length exceeds 3 m",evaluate_tabular_column_scope(c)["failures"])
        c["length_m"]=3.0
        c["sections"][0]["Mx_kNm"]=100 # 100/500 = .20 > .15*.6
        self.assertTrue(any("eccentricity" in x for x in evaluate_tabular_column_scope(c)["failures"]))
        c["sections"][0]["Mx_kNm"]=10
        c["bars"]=[{"diameter_mm":40} for _ in range(12)]
        self.assertTrue(any("4%" in x for x in evaluate_tabular_column_scope(c)["failures"]))

    def test_default_column_never_certifies_and_exposes_missing_sources(self):
        c=column()
        a=audit_column(c)
        codes={i["code"] for i in a["issues"]}
        self.assertEqual(a["status"],"NOT_QUALIFIED")
        self.assertFalse(a["normative_claim"])
        self.assertNotIn("NO_FIRE_LOAD_SOURCE",codes)
        self.assertNotIn("FIRE_ACTION_COMBINATION_NOT_QUALIFIED",codes)
        self.assertTrue(a["resolved_inputs"]["fire_actions_are_design_values"])
        self.assertIn("ANNEX_L_NOT_EVALUATED",codes)
        self.assertIn("E_CM_NOT_PROVEN",codes)
        self.assertIn("ASSUMED_FOUR_SIDES",codes)
        self.assertIn("MATERIAL_THERMAL_SCOPE_MISSING",codes)
        self.assertIsNone(a["scope_check"]["temperature_C"])
        with self.assertRaises(NormativeQualificationError): prevent_normative_claim(a,"R90")
        with self.assertRaises(NormativeQualificationError): prevent_normative_claim({**a,"normative_claim":True})

    def test_documented_user_inputs_do_not_imply_qualified_model(self):
        c=column()
        c.update(concrete_aggregate="calcareous",concrete_density_type="heavy",
                 concrete_consistency_class="S3",tested_Ecm_source="lab",
                 fire_action_provenance="structural load combination supplied",
                 exposed_faces=["left","right","top","bottom"],
                 member_support_model="external verified model")
        c["spalling"]={"method":"by2026_annex_l"}
        a=audit_column(c)
        self.assertEqual(a["scope_check"]["temperature_C"],600)
        self.assertEqual(a["status"],"NOT_QUALIFIED")
        with self.assertRaises(NormativeQualificationError): prevent_normative_claim(a)

    def test_preflight_is_json_stable(self):
        a=audit_column(column(),"table_3_column")
        b=json.loads(json.dumps(a,ensure_ascii=False))
        self.assertEqual(a,b)
        self.assertEqual(a["contract_sha256"],contract_sha256())

if __name__=="__main__":unittest.main()