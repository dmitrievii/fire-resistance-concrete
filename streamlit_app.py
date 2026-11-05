"""R0.5 Multi-Column RC Fire Resistance Calculator — Streamlit Cloud entrypoint.

Run the UI script on *every* Streamlit rerun, not just the first Python import.
The historic single-column version remains in legacy_single_column.py.
"""
import runpy
runpy.run_module('multicolumn_r05.app', run_name='__main__')