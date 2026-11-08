"""Regression: deployed legacy Cloud entrypoint with stale pre-R0.6.8 modules.

The exact production incident was an ImportError for
`classify_fine_grained`: current Annex L imported an old cached
rc_fire.materials.normative object, even though the source file was correct.
Run in a subprocess so intentionally corrupted module caches cannot leak
into unrelated unit tests.
"""
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]

class CloudMaterialHotReloadRegression(unittest.TestCase):
    def _run_isolated(self, initial):
        body = ("import importlib\n"
                "from pathlib import Path\n"
                "from streamlit.testing.v1 import AppTest\n\n"
                + textwrap.dedent(initial).strip() + "\n\n"
                + textwrap.dedent("""
                    path = Path('K18_Streamlit_GitHub_MVP_R0.5') / 'streamlit_app.py'
                    app = AppTest.from_file(str(path), default_timeout=90).run()
                    assert not app.exception, 'Cloud startup failed: ' + repr([
                        x.message for x in app.exception])
                    assert not app.error, 'Cloud Streamlit error: ' + repr([
                        x.message for x in app.error])
                    materials = importlib.import_module('rc_fire.materials.normative')
                    assert callable(getattr(materials, 'classify_fine_grained', None))
                    ui = importlib.import_module('multicolumn_r05.r056_ui')
                    assert ui.R068_BELARUS_UI_RELEASE == 'r0681-belarus-only-ui'
                    print('CLOUD_STALE_IMPORT_RECOVERY_OK')
                """))
        result = subprocess.run(
            [sys.executable, '-c', body],
            cwd=str(ROOT), capture_output=True, text=True, timeout=150,
        )
        self.assertEqual(result.returncode, 0,
            "Cloud hot reload crashed.\nSTDOUT:\n" +
            result.stdout[-4000:] + "\nSTDERR:\n" + result.stderr[-6000:])
        self.assertIn('CLOUD_STALE_IMPORT_RECOVERY_OK', result.stdout)

    def test_cached_old_material_module_lacks_new_classifier(self):
        self._run_isolated("""
materials = importlib.import_module('rc_fire.materials.normative')
assert callable(materials.classify_fine_grained)
del materials.classify_fine_grained
assert not hasattr(materials, 'classify_fine_grained')
""")

    def test_cached_old_ui_has_old_belarus_screen(self):
        self._run_isolated("""
ui = importlib.import_module('multicolumn_r05.r056_ui')
assert hasattr(ui, 'R068_BELARUS_UI_RELEASE')
del ui.R068_BELARUS_UI_RELEASE
""")


if __name__ == '__main__':
    unittest.main()
