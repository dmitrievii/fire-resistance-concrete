"""Compatibility entrypoint for the original Streamlit Cloud file path.

All UI, state, calculation and reports live in the repository root application.
There is only one user-facing calculator.
"""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
runpy.run_path(str(ROOT / "streamlit_app.py"), run_name="__main__")
