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
    _stale |= getattr(_cached_model, "R068_MODEL_RELEASE", None) != "r068-belarus-annex-l-unified-20261108"
    _stale |= not _actual or Path(_actual).resolve() != _expected

for _suffix in _EXPECTED_MODULES:
    _loaded = sys.modules.get(_PACKAGE + "." + _suffix)
    if _loaded is None:
        continue
    _actual = getattr(_loaded, "__file__", None)
    _expected = (_ROOT / _PACKAGE / (_suffix + ".py")).resolve()
    _stale |= not _actual or Path(_actual).resolve() != _expected
    _stale |= getattr(_loaded, "R056_SP468_RELEASE", None) != _SP468_RELEASE
    if _suffix == "r056_ui":
        # The legacy SP468 stamp was accidentally retained in the new
        # Belarus-only R0.6.8 UI, so it cannot detect a stale Cloud UI.
        _stale |= getattr(_loaded, "R068_BELARUS_UI_RELEASE", None) != (
            "r0681-belarus-only-ui")

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
    _stale |= getattr(_cached_mechanics, "RESOLVED_MATERIAL_COUPLING", None) != (
        "R0.6.8.2-central-material-resolution-v1")

# R064D_HOT_RELOAD_GUARD: prevent mixing old member/bridge modules.
for _name, _version in (("rc_fire.member.coupled", "R0.6.4C-member-uls-audited-diagnostic-v1"),
                        ("rc_fire.integration.r064d", "R0.6.4D-repository-integration-v1"),
                         ("rc_fire.integration.r067", "R0.6.7-uniform-longitudinal-thermal-member-diagnostic-v1")):
    _existing = sys.modules.get(_name)
    if _existing is not None:
        _stale |= getattr(_existing, "VERSION", None) != _version

# R0.6.8.3: a cached normative/member module predating the project-wide
# fire-design-action convention must not survive Streamlit Cloud hot reload.
for _name in ("rc_fire.normative.preflight",
              "rc_fire.integration.r064d",
              "rc_fire.integration.r067",
              "rc_fire.member.uls"):
    _loaded=sys.modules.get(_name)
    if _loaded is not None:
        _stale |= getattr(_loaded, "ACTION_INPUT_CONTRACT", None) != (
            "R0.6.8.3-user-supplied-fire-design-actions-v1")

# The Belarus Annex L input form changed from the old Russian numeric
# range tooltips. Invalidate cached UI objects after the range-help release.
_old_annex_ui=sys.modules.get("rc_fire.spalling.ui")
if _old_annex_ui is not None:
    _stale |= getattr(_old_annex_ui, "RANGE_HINTS_RELEASE", None) != (
        "r0682-belarus-input-range-tooltips-v1")

_old_annex=sys.modules.get("rc_fire.spalling.annex_l")
if _old_annex is not None:
    _stale |= getattr(_old_annex,"VERSION",None) != "R0.6.8-BY-annex-L-source-first-v1"
    _stale |= getattr(_old_annex,"DEFAULT_SAND_POLICY",None) != (
        "R0.6.8.2-traceable-positive-default-v1")

# R0.6.8 introduced classify_fine_grained in the existing normative.py,
# but did NOT change the old R0.6.1 VERSION stamp. Streamlit Cloud can keep
# the old imported module in sys.modules while loading the new Annex L.
# The resulting import fails before a single calculation is performed.
# Detect the actual API and on-disk origin rather than relying only on VERSION.
_MATERIALS_MODULES = (
    ("rc_fire.materials", _ROOT / "rc_fire" / "materials" / "__init__.py"),
    ("rc_fire.materials.normative",
     _ROOT / "rc_fire" / "materials" / "normative.py"),
)
for _name, _expected in _MATERIALS_MODULES:
    _cached = sys.modules.get(_name)
    if _cached is not None:
        _file = getattr(_cached, "__file__", None)
        _stale |= not _file or Path(_file).resolve() != _expected.resolve()
        if _name.endswith(".normative"):
            _stale |= not callable(getattr(_cached, "classify_fine_grained", None))
            _stale |= not callable(getattr(_cached, "resolve_materials", None))
        else:
            _stale |= not callable(getattr(_cached, "resolve_materials", None))

if _stale:
    for _name in tuple(sys.modules):
        if (_name == "rc_fire.normative" or _name.startswith("rc_fire.normative.")
             or _name == "rc_fire.materials" or _name.startswith("rc_fire.materials.")
             or _name == "rc_fire.mechanics" or _name.startswith("rc_fire.mechanics.")
             or _name == "rc_fire.thermal" or _name.startswith("rc_fire.thermal.")
             or _name == "rc_fire.member" or _name.startswith("rc_fire.member.")
             or _name == "rc_fire.integration" or _name.startswith("rc_fire.integration.")
             or _name == "rc_fire.spalling" or _name.startswith("rc_fire.spalling.")):
            sys.modules.pop(_name,None)
    importlib.invalidate_caches()
    # Never mix a cached old UI/calculation facade with new material tables.
    for _name in tuple(sys.modules):
        if _name == _PACKAGE or _name.startswith(_PACKAGE + "."):
            sys.modules.pop(_name, None)
    importlib.invalidate_caches()

# Public R0.7 source must not combine an older cached UI adapter with a
# newer fire result engine after Streamlit Cloud redeployment.
for _name, _release in (
    ("rc_fire.integration.r07_inputs","R0.7-simple-physical-column-inputs-v1"),
    ("rc_fire.integration.r07_public","R0.7-public-fire-workflow-v4")):
    _loaded=sys.modules.get(_name)
    if _loaded is not None:
        _cached_path=getattr(_loaded,"__file__",None)
        _expected_path=(_ROOT / "rc_fire" / "integration" /
                        (_name.rsplit(".",1)[-1]+".py")).resolve()
        _stale_public=(not _cached_path or
            Path(_cached_path).resolve()!=_expected_path or
            getattr(_loaded,"VERSION",None)!=_release)
        if _stale_public:
            sys.modules.pop(_name,None)
            # The previous public facade can hold an older R0.6.9D3
            # coupling implementation without bars_C, even after the
            # Streamlit script itself was redeployed. Refresh its exact
            # dependent calculation modules at the same time.
            if _name=="rc_fire.integration.r07_public":
                for _dependency in (
                    "rc_fire.integration.r069d3",
                    "rc_fire.integration.r072_strength_evidence",
                    "rc_fire.integration.r073_plot_contract"):
                    sys.modules.pop(_dependency,None)
            importlib.invalidate_caches()

# run_module, not import_module: rerun the UI on every Streamlit interaction.
runpy.run_module("multicolumn_r05.simple_app", run_name="__main__")
