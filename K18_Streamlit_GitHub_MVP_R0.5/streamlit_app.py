"""Compatibility entrypoint for the historic Streamlit Cloud main file path.

The app itself lives at the repository root. Streamlit Cloud may place this
legacy entrypoint's directory before the project root on sys.path, and can
retain imported Python modules across script reruns. Explicitly prefer root
modules and refresh a stale pre-R0.8 app_core before executing the new UI.

For new deployments, configure the main file as `streamlit_app.py` instead.
"""
from pathlib import Path
import importlib
import runpy
import sys

ROOT = Path(__file__).resolve().parent.parent
root_path = str(ROOT)

# Never rely on 'if root_path not in sys.path': if it is already present at
# index > 0, an obsolete module on an earlier search path can shadow it.
sys.path[:] = [root_path] + [p for p in sys.path if p != root_path]
importlib.invalidate_caches()

# R0.8 introduced default_template_bytes. If Cloud has a cached R0.7
# app_core object from a hot reload, importing that symbol in the root UI
# raises ImportError even though the current source file is correct.
loaded = sys.modules.get("app_core")
if loaded is not None:
    source = getattr(loaded, "__file__", None)
    if not source or Path(source).resolve() != (ROOT / "app_core.py"):
        sys.modules.pop("app_core", None)
    elif not callable(getattr(loaded, "default_template_bytes", None)):
        importlib.reload(loaded)

runpy.run_path(str(ROOT / "legacy_single_column.py"), run_name="__main__")
