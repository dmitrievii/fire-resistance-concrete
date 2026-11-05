"""Streamlit Cloud entrypoint for the R0.5 multi-column RC calculator.

On hot reload, Streamlit can retain modules imported by a previous release.
The nested historical Cloud entrypoint runs this file too. Keep all R0.5
modules from one release rather than mixing cached and new model code.
"""
from pathlib import Path
import importlib
import runpy
import sys

_ROOT = Path(__file__).resolve().parent
_MODEL_NAME = "multicolumn_r05.project_model"
_CACHED_MODEL = sys.modules.get(_MODEL_NAME)
if _CACHED_MODEL is not None:
    _actual = getattr(_CACHED_MODEL, "__file__", None)
    _expected = (_ROOT / "multicolumn_r05" / "project_model.py").resolve()
    _missing_r056 = not callable(getattr(_CACHED_MODEL, "update_spalling", None))
    _wrong_path = not _actual or Path(_actual).resolve() != _expected
    if _missing_r056 or _wrong_path:
        # Reload the *whole* internal package: its modules share references
        # to model types/functions and must not be mixed across releases.
        for _name in list(sys.modules):
            if _name == "multicolumn_r05" or _name.startswith("multicolumn_r05."):
                sys.modules.pop(_name, None)
        importlib.invalidate_caches()

# run_module, not import_module: rerun the UI on every Streamlit interaction.
runpy.run_module("multicolumn_r05.app", run_name="__main__")
