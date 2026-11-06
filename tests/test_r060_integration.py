"""R0.6.0 in R0.5.6: compatibility and locked fail-closed compliance."""
import unittest
from rc_fire.normative import contract_sha256
from multicolumn_r05.project_model import new_project, update_section
from multicolumn_r05.project_calculator import evaluate_column, evaluate_project

class R060IntegrationTests(unittest.TestCase):
    def test_default_project_returns_normative_preflight_without_fake_R90(self):
        p=new_project(2)
        results=evaluate_project(p)
        self.assertEqual(set(results),{"c1","c2"})
        for r in results.values():
            c=r["normative_preflight"]
            self.assertEqual(c["contract_sha256"],contract_sha256())
            self.assertEqual(c["status"],"NOT_QUALIFIED")
            self.assertFalse(c["normative_claim"])
            self.assertFalse(r["normative_claim"])
            self.assertEqual(r["fire_resistance_status"],"not_demonstrated")
            self.assertIn("NO_FIRE_LOAD_SOURCE", {x["code"] for x in c["issues"]})

    def test_loaded_reference_remains_diagnostic(self):
        p=new_project()
        update_section(p,"c1","bottom",{"N_kN":500,"Mx_kNm":10,"My_kNm":5})
        update_section(p,"c1","top",{"N_kN":510,"Mx_kNm":12,"My_kNm":7})
        r=evaluate_column(p["columns"][0])
        self.assertEqual(r["status"],"calculated",r["issues"])
        self.assertEqual(r["normative_preflight"]["status"],"NOT_QUALIFIED")
        self.assertFalse(r["normative_claim"])
        self.assertEqual(r["fire_resistance_status"],"not_demonstrated")
        self.assertTrue(r["raw_results"])

if __name__=="__main__":unittest.main()