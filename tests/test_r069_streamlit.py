"""Exercise the actual time-history button and source invalidation on reruns."""
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest
from test_r069_time_history import configured_column


class HistoryStreamlitTests(unittest.TestCase):
    def test_compute_show_in_overview_and_invalidate_after_load_edit(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] /
                                  'streamlit_app.py'), default_timeout=120).run()
        self.assertFalse(app.exception, list(app.exception))
        p = configured_column()
        p['columns'][0]['fire_minutes'] = 1.
        app.session_state['project'] = p
        app.run()
        next(x for x in app.radio if x.label == 'Разделы').set_value('c1').run()
        self.assertFalse(app.exception, list(app.exception))
        next(x for x in app.button if x.label == 'Рассчитать R(t)').click().run()
        self.assertFalse(app.exception, list(app.exception))
        r = app.session_state['r069_result_c1']
        self.assertEqual(r['status'], 'SAMPLED_INTERVAL_WITHIN_DIAGNOSTIC_LIMITS')
        self.assertEqual(r['controls']['end_minutes'], 1.)
        self.assertFalse(r['normative_claim'])
        self.assertIsNone(app.session_state['exports'])
        next(x for x in app.radio if x.label == 'Разделы').set_value('Обзор проекта').run()
        self.assertFalse(app.exception, list(app.exception))
        self.assertTrue(any('Временной расчёт' in x.value.columns for x in app.dataframe))
        p = app.session_state['project']
        p['columns'][0]['sections'][0]['N_kN'] = 200.
        app.session_state['project'] = p
        app.run()
        self.assertFalse(app.exception, list(app.exception))
        self.assertNotIn('r069_result_c1', app.session_state)
        self.assertFalse(any('Временной расчёт' in x.value.columns for x in app.dataframe))


if __name__ == '__main__':
    unittest.main()
