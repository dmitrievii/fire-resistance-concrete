# RC fire calculator — K18 R0.4 Streamlit prototype

A **web UI for the already implemented Python K18 calculation engines**. This is not a new fire design standard.

## Modes

- **Reference K18:** reproduces the known two-variant calculations from the supplied Mathcad worksheet; provides the **original 32-page K18 Word report** only for compatible inputs. Reference geometry and wording are intentionally fixed.
- **Parametric RC:** supports rectangular cross sections, 4–64 bars per variant, 1–12 variants, fire exposure on all four sides, temperature and approximate one-axis mechanical diagnostics. It outputs a **separate experimental DOCX** with the original frame and stamp. It does **not** certify R90, does not verify biaxial N–Mx–My interaction, and has not undergone normative model validation.

## Quick start

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Enter geometry and materials in the first tab, axial force and bending moments in the second, and individual bar coordinates and diameters in the third. Press **Calculate**. JSON can be downloaded immediately. For DOCX upload the exact original `Пример.docx` from the R0.4 package; this file is never part of this clean source distribution.

## Deploy on Streamlit Community Cloud

1. Create **a separate repository** (suggested: `rc-fire-report-generator`, preferably private during development). Do not use the existing steel `fire-resistance-calculator` repository.
2. Upload the **contents of this folder**. Do not commit `master.docx`, `source_k18.xmcd`, reports, client/project records, or licensed standards.
3. Open [share.streamlit.io](https://share.streamlit.io) and connect GitHub, permitting private-repository access if needed.
4. Choose the new repository, branch `main`, entrypoint **`streamlit_app.py`**, Python 3.12.
5. Deploy. Community Cloud installs Python dependencies from `requirements.txt`. The app exports DOCX and JSON; PDF can be converted locally in a trusted Word installation.

## Verification

```bash
python -m unittest discover -s tests -v
```

Runtime generation requires an exact SHA-256 match to the original reference template, checked at runtime. Generated DOCX files are held only in temporary directories, returned as bytes, and destroyed when generation finishes. Streamlit may retain results in per-session memory until the user disconnects. No backend upload, file persistence or user authentication is implemented in this MVP; **do not treat Streamlit Community Cloud as a confidential engineering file vault**.

## Structure

- `streamlit_app.py` — presentation and user input
- `app_core.py` — pure input validation, calculation routing, report generation
- `calculation_engine.py` — original Mathcad K18 reproduction
- `parametric_engine.py` — experimental rectangular fiber solver
- `report_adapter.py`, `word_patch.py`, `parametric_report.py` — Word report internals
- `examples/` — technical input examples in JSON only
- `tests/` — smoke/regression tests

Original formulas, field applicability, and compliance limitations are the same as the source R0.4 package.
