# R0.5 multi-column live deployment

`streamlit_app.py` now opens the multi-column Overview by default. The previous one-column calculator is kept unchanged in `legacy_single_column.py` and is accessible as a Streamlit page.

- The multi-column solver is diagnostic. It does not certify R90.
- Uses the public, sanitized template `templates/RC_Fire_Report_Master.docx`; no client originals or licensed standards are included.
- Export creates a ZIP of per-column and combined DOCX and, if LibreOffice is installed, PDFs.
- Tests: `python -m unittest discover -s tests -v` and syntax compile.