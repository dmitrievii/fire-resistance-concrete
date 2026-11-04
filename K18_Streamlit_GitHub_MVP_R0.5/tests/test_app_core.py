import copy
import unittest
from app_core import (load_example, execute, summary_rows, parse_bars_table,
                      bars_table, with_variant_count, generate_docx)
from calculation_engine import ModelError

class CoreTests(unittest.TestCase):
    def test_reference_k18(self):
        r = execute(load_example('legacy'))
        self.assertAlmostEqual(r['variants']['v2']['axes']['x']['M_Rd_kNm'], 421.350648996, places=6)
        self.assertEqual(len(summary_rows(r)), 4)
    def test_parametric(self):
        r = execute(load_example('parametric'))
        self.assertEqual(r['engine'], 'k18-parametric-experimental')
        self.assertEqual(len(summary_rows(r)), 4)
    def test_reinforcement_table(self):
        p = load_example('parametric')
        reconstructed = parse_bars_table(bars_table(p, 0))
        self.assertEqual(len(reconstructed), len(p['variants'][0]['bars']))
        self.assertAlmostEqual(reconstructed[0]['x_m'], p['variants'][0]['bars'][0]['x_m'])
    def test_variant_count(self):
        a = load_example('parametric')
        b = with_variant_count(a, 4)
        self.assertEqual([v['id'] for v in b['variants']], ['v1','v2','v3','v4'])
        self.assertEqual(len(a['variants']),2)
    def test_deny_non_reference_template(self):
        p=load_example('parametric'); result=execute(p)
        with self.assertRaises(ModelError):
            generate_docx(p,result,b'not a Word template')
    def test_inconsistent_bars_rejected(self):
        data=load_example('parametric')
        data['variants'][0]['bars'][0]['x_m']=2
        with self.assertRaises(ModelError): execute(data)

if __name__=='__main__': unittest.main()
