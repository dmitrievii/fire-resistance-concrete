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
    _stale |= not callable(getattr(_cached_model, "update_thermal_spec", None))
    _stale |= getattr(_cached_model, "R065_MODEL_RELEASE", None) != "r065-center-sections-load-transfer-20261107"
    _stale |= getattr(_cached_model, "R067_MODEL_RELEASE", None) != "r067-unified-preflight-member-20261107"
    _stale |= not _actual or Path(_actual).resolve() != _expected

for _suffix in _EXPECTED_MODULES:
    _loaded = sys.modules.get(_PACKAGE + "." + _suffix)
    if _loaded is None:
        continue
    _actual = getattr(_loaded, "__file__", None)
    _expected = (_ROOT / _PACKAGE / (_suffix + ".py")).resolve()
    _stale |= not _actual or Path(_actual).resolve() != _expected
    _stale |= getattr(_loaded, "R056_SP468_RELEASE", None) != _SP468_RELEASE

# R0.6.2 introduces a new thermal package and extends the project authoring
# contract. On a Streamlit Cloud hot reload, stale module objects must not
# survive even if the older R0.5.6 methods are still present.
_THERMAL_NAME = "rc_fire.thermal.normative"
_cached_thermal = sys.modules.get(_THERMAL_NAME)
if _cached_thermal is not None:
    _stale |= getattr(_cached_thermal,"VERSION",None) != "R0.6.2-annex-K-v1"

_MECHANICS_NAME = "rc_fire.mechanics.normative"
_cached_mechanics = sys.modules.get(_MECHANICS_NAME)
if _cached_mechanics is not None:
    _stale |= getattr(_cached_mechanics, "VERSION", None) != "R0.6.3C-source-adjudication-candidate"

# R064D_HOT_RELOAD_GUARD: prevent mixing old member/bridge modules.
for _name, _version in (("rc_fire.member.coupled", "R0.6.4C-member-uls-audited-diagnostic-v1"),
                        ("rc_fire.integration.r064d", "R0.6.4D-repository-integration-v1"),
                         ("rc_fire.integration.r067", "R0.6.7-uniform-longitudinal-thermal-member-diagnostic-v1")):
    _existing = sys.modules.get(_name)
    if _existing is not None:
        _stale |= getattr(_existing, "VERSION", None) != _version

if _stale:
    for _name in tuple(sys.modules):
        if (_name == "rc_fire.mechanics" or _name.startswith("rc_fire.mechanics.")
             or _name == "rc_fire.thermal" or _name.startswith("rc_fire.thermal.")
             or _name == "rc_fire.member" or _name.startswith("rc_fire.member.")
             or _name == "rc_fire.integration" or _name.startswith("rc_fire.integration.")):
            sys.modules.pop(_name,None)
    importlib.invalidate_caches()
    # Never mix a cached old UI/calculation facade with new material tables.
    for _name in tuple(sys.modules):
        if _name == _PACKAGE or _name.startswith(_PACKAGE + "."):
            sys.modules.pop(_name, None)
    importlib.invalidate_caches()

# run_module, not import_module: rerun the UI on every Streamlit interaction.
runpy.run_module("multicolumn_r05.app", run_name="__main__")
