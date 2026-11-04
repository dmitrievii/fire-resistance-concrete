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
