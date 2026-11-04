import copy
import unittest
from app_core import (load_example, execute, summary_rows, parse_bars_table,
                      bars_table, with_variant_count, generate_docx, default_template_bytes, CLEAN_MASTER_SHA256)
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
    def test_bundled_master_is_clean_and_reference_report_generates(self):
        from hashlib import sha256
        from io import BytesIO
        from zipfile import ZipFile
        data = default_template_bytes()
        self.assertEqual(sha256(data).hexdigest(),CLEAN_MASTER_SHA256)
        with ZipFile(BytesIO(data)) as z:
            text=' '.join(z.read(name).decode('utf-8',errors='ignore') for name in z.namelist() if name.endswith('.xml'))
            for private in ['ГродноПроектСтрой','Современные бетонные конструкции','42-XXV','42–XXV','05-2025-1215','Сергей Жамойдик']:
                self.assertNotIn(private,text)
            self.assertIn('RC-DEMO',text)
            self.assertEqual(sum('embeddings/oleObject' in name for name in z.namelist()),34)
        payload=load_example('k18')
        result=execute(payload)
        generated,audit=generate_docx(payload,result)
        self.assertEqual(generated,data)
        self.assertEqual(audit['template_source'],'bundled-sanitized-master')

    def test_bundled_master_parametric_report(self):
        payload=load_example('parametric')
        result=execute(payload)
        generated,audit=generate_docx(payload,result)
        self.assertTrue(generated.startswith(b'PK'))
        self.assertEqual(audit['template_source'],'bundled-sanitized-master')
        self.assertFalse(audit['certifies_fire_resistance'])

    def test_deny_non_reference_template(self):
        p=load_example('parametric'); result=execute(p)
        with self.assertRaises(ModelError):
            generate_docx(p,result,b'not a Word template')
    def test_inconsistent_bars_rejected(self):
        data=load_example('parametric')
        data['variants'][0]['bars'][0]['x_m']=2
        with self.assertRaises(ModelError): execute(data)

if __name__=='__main__': unittest.main()
