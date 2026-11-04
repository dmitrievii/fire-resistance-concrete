"""Executed on GitHub CI where Streamlit is installed; verifies first browser session."""
from pathlib import Path
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None


@unittest.skipUnless(AppTest is not None,'Streamlit testing framework unavailable in offline build')
class StreamlitAppTests(unittest.TestCase):
    def test_default_session_presents_reference_without_mode_selector(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        self.assertFalse(app.exception, f'Streamlit crashed: {list(app.exception)}')
        self.assertFalse(app.error, f'Streamlit error: {list(app.error)}')
        # The original two-mode radio must not reappear.
        radio_labels=[getattr(item,'label','') for item in app.radio]
        self.assertNotIn('Calculation model',radio_labels)
        self.assertTrue(any('Calculated results' in x.value for x in app.subheader))

    def test_perimeter_ui_resizes_bars_with_section(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        self.assertFalse(app.exception, f'Streamlit crashed: {list(app.exception)}')
        labels=[item.label for item in app.number_input]
        self.assertIn('Bars along x (nx)',labels)
        self.assertIn('Bars along y (ny)',labels)
        self.assertIn('Bar diameter Ø [mm]',labels)
        self.assertIn('Left edge → bar centre [mm]',labels)
        width=next(item for item in app.number_input if item.label=='Width b [mm]')
        width.set_value(400.0).run()
        self.assertFalse(app.exception, f'Streamlit crashed on resizing: {list(app.exception)}')
        self.assertFalse(app.error, f'Streamlit UI error: {list(app.error)}')
        data=app.session_state['draft_input']
        self.assertEqual(data['geometry']['b_m'],.4)
        for variant in data['variants']:
            self.assertEqual(len(variant['bars']),8)
            self.assertAlmostEqual(max(bar['x_m'] for bar in variant['bars']),.35)
            self.assertEqual(variant['reinforcement']['spacing_x_mm'],150)
