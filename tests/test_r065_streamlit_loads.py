"""End-to-end Streamlit data-editor load synchronization, R0.6.5."""
import unittest
from pathlib import Path
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None


@unittest.skipUnless(AppTest is not None,"Streamlit test framework unavailable")
class R065StreamlitLoadTransferTests(unittest.TestCase):
    def test_overview_load_editor_reaches_column_page_and_engine(self):
        root=Path(__file__).resolve().parents[1]/"streamlit_legacy_app.py"
        app=AppTest.from_file(str(root),default_timeout=120).run()
        self.assertFalse(app.exception,list(app.exception))
        project=app.session_state["project"]
        self.assertEqual(len(project['columns'][0]['sections']),1)
        self.assertEqual(project['columns'][0]['sections'][0]['id'],'center')
        # Streamlit AppTest doesn't support direct data_editor.set_value.
        # Assigning the editor's serialized edit delta before run is the
        # documented way to exercise the real widget-to-model path.
        key=f"overview_loads_v{project['revision']}"
        app.session_state[key]={
            'edited_rows':{'0':{'N, кН':50.,'Mx, кН·м':3.,'My, кН·м':2.}},
            'added_rows':[],'deleted_rows':[]}
        app.run()
        self.assertFalse(app.exception,list(app.exception))
        state=app.session_state['project']
        s=state['columns'][0]['sections'][0]
        self.assertEqual((s['N_kN'],s['Mx_kNm'],s['My_kNm']),(50.,3.,2.))
        selection=next(r for r in app.radio if r.label=='Разделы')
        selection.set_value('c1').run()
        self.assertFalse(app.exception,list(app.exception))
        self.assertTrue(any('Усилия переданы' in str(x.value) for x in app.info))
        # The per-column and overview editors use the same canonical state.
        self.assertEqual(app.session_state['project']['columns'][0]['sections'][0]['N_kN'],50.)


    def test_explicit_new_project_resets_old_end_sections_safely(self):
        root=Path(__file__).resolve().parents[1]/"streamlit_legacy_app.py"
        app=AppTest.from_file(str(root),default_timeout=120).run()
        self.assertFalse(app.exception,list(app.exception))
        old=app.session_state['project']['columns'][0]
        old['sections']=[
            {'id':'bottom','name':'Низ','z_m':0.,'N_kN':50.,'Mx_kNm':3.,'My_kNm':2.},
            {'id':'top','name':'Верх','z_m':3.,'N_kN':None,'Mx_kNm':None,'My_kNm':None}]
        app.run()
        self.assertEqual(len(app.session_state['project']['columns'][0]['sections']),2)
        app.button(key='r065_new_project').click().run()
        self.assertFalse(app.exception,list(app.exception))
        new=app.session_state['project']['columns'][0]['sections']
        self.assertEqual(len(new),1)
        self.assertEqual(new[0]['id'],'center')
        self.assertIsNone(new[0]['N_kN'])


if __name__=='__main__':
    unittest.main()
