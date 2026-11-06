import unittest
from docx import Document
from tools.integrate_r064d import (patch_facade, patch_streamlit,patch_reports,patch_entrypoint,IntegrateError)
from rc_fire.integration.report import add_member_evidence_note

class R064DHooks(unittest.TestCase):
    def test_facade_calls_are_not_eagerly_rewritten(self):
        source=('def evaluate_column(c,grid=48):\n'
                '    return {"normative_claim":False,"results":{"old":1}}\n\n'
                'def evaluate_project(project,grid=48):\n'
                '    return {c["id"]:evaluate_column(c,grid) for c in project["columns"]}\n')
        updated=patch_facade(source)
        env={}
        exec(updated,env)
        data=env['evaluate_project']({'columns':[{'id':'c1'}]})['c1']
        self.assertEqual(data['results'],{'old':1})
        self.assertEqual(data['member_r064d']['status'],'NOT_EVALUATED')
        self.assertFalse(data['normative_claim'])
        with self.assertRaises(IntegrateError):patch_facade(updated)

    def test_streamlit_insertion_unique(self):
        s=("    render_mechanics_results(st,c,calculation)\n"
           "if selected=='Обзор проекта':show_overview()\n")
        a=patch_streamlit(s)
        self.assertIn('render_member_evidence(st,c,calculation)',a)
        with self.assertRaises(IntegrateError):patch_streamlit(a)

    def test_report_insertion_no_eager_extra_pages(self):
        s=('    add_text(doc,\'Параметрический диагностический расчёт. Не является нормативным подтверждением R90.\',bold=True)\n'
           '        add_r056_diagnostics(doc,c,calc)\n'
           '        finish(doc,target,template)\n')
        updated=patch_reports(s)
        self.assertIn('not in (None, "NOT_EVALUATED")',updated)
        self.assertIn("not in (None, 'NOT_EVALUATED')",updated)

    def test_cloud_entrypoint_updates_hot_reload_guard(self):
        source=('expected = "R0.6.3-section-mechanics-v1"\n'
            'if _stale:\n'
            '    if (_name == "rc_fire.mechanics" or _name.startswith("rc_fire.mechanics.")\n'
            '             or _name == "rc_fire.thermal" or _name.startswith("rc_fire.thermal.")):\n'
            '        pass\n')
        updated=patch_entrypoint(source)
        compile(updated,'<R064D entrypoint smoke>','exec')
        self.assertIn('R0.6.3C-source-adjudication-candidate',updated)
        self.assertIn('rc_fire.member',updated)
        self.assertIn('rc_fire.integration',updated)
        with self.assertRaises(IntegrateError):patch_entrypoint(updated)

    def test_word_note_explicit_noncertification(self):
        doc=Document()
        add_member_evidence_note(doc,{'member_r064d':{'status':'INSUFFICIENT_ULS_EVIDENCE'}})
        joined=' '.join(p.text for p in doc.paragraphs)
        self.assertIn('R90',joined)
        self.assertIn('НЕ подтверждается',joined)

if __name__=='__main__':unittest.main()
