"""R0.6.9 Streamlit end-to-end: explicit opt-in, no invented R certificate."""
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None


@unittest.skipUnless(AppTest is not None,"Streamlit testing framework unavailable")
class R069StreamlitTests(unittest.TestCase):
    def test_column_page_has_Rt_and_cached_scan_is_fail_closed(self):
        entry=Path(__file__).resolve().parents[1]/"streamlit_app.py"
        app=AppTest.from_file(str(entry),default_timeout=150).run()
        self.assertFalse(app.exception,list(app.exception))
        nav=next(x for x in app.radio if x.label=="Разделы")
        nav.set_value("c1").run()
        self.assertFalse(app.exception,list(app.exception))
        self.assertTrue(any("R0.6.9 — R(t)" in x.label for x in app.expander))
        self.assertTrue(any("Шаг по времени" in x.label for x in app.number_input))
        run=next(x for x in app.button if x.label=="Рассчитать историю R(t) (диагностически)")
        # With empty source values the calculation may run thermal only, but it
        # must never show a positive R certificate or silently fill N/M.
        run.click().run()
        self.assertFalse(app.exception,list(app.exception))
        cached=app.session_state["r069_result_c1"]
        r=cached["result"]
        self.assertGreater(r["sampled_time_count"],1)
        self.assertFalse(r["normative_claim"])
        self.assertIsNone(r["computed_exact_R_min"])
        self.assertIsNone(r["normative_class_approved"])
        self.assertEqual(r["fire_resistance_status"],"not_demonstrated")
        # Streamlit AppTest does not expose download_button in app.button.
        # Check the download handler statically instead of treating the
        # testing harness's unsupported widget as a missing UI control.
        import inspect
        from rc_fire.resistance.ui import render_resistance
        self.assertIn('st.download_button',inspect.getsource(render_resistance))


if __name__=="__main__":
    unittest.main()
