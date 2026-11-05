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
# Release stamp guarantees dependent modules are from the same deployed
# source. This also detects old r056_ui.py after Streamlit Cloud hot reload.
_SP468_RELEASE = "r056-sp468-20261105-hotfix1"
_PACKAGE = "multicolumn_r05"
_EXPECTED_MODULES = ("r056_ui", "r056_engine", "sp468")
_stale = False

_cached_model = sys.modules.get(_PACKAGE + ".project_model")
if _cached_model is not None:
    _actual = getattr(_cached_model, "__file__", None)
    _expected = (_ROOT / _PACKAGE / "project_model.py").resolve()
    _stale |= not callable(getattr(_cached_model, "update_spalling", None))
    _stale |= not _actual or Path(_actual).resolve() != _expected

for _suffix in _EXPECTED_MODULES:
    _loaded = sys.modules.get(_PACKAGE + "." + _suffix)
    if _loaded is None:
        continue
    _actual = getattr(_loaded, "__file__", None)
    _expected = (_ROOT / _PACKAGE / (_suffix + ".py")).resolve()
    _stale |= not _actual or Path(_actual).resolve() != _expected
    _stale |= getattr(_loaded, "R056_SP468_RELEASE", None) != _SP468_RELEASE

if _stale:
    # Never mix a cached old UI/calculation facade with new material tables.
    for _name in tuple(sys.modules):
        if _name == _PACKAGE or _name.startswith(_PACKAGE + "."):
            sys.modules.pop(_name, None)
    importlib.invalidate_caches()

# run_module, not import_module: rerun the UI on every Streamlit interaction.
runpy.run_module("multicolumn_r05.app", run_name="__main__")
