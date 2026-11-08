# Fire Resistance Concrete — Unified Rectangular Section R0.6

**One Streamlit workspace; one parametric input schema.** The app starts immediately with the original K18 (600 × 600 mm, 13.7 m, two reinforcement variants Ø20 / Ø25, four-sided R90) and **shows calculated reference results without pressing Calculate**.

[Live Streamlit app](https://fire-resistance-concrete.streamlit.app/) · [GitHub](https://github.com/dmitrievii/fire-resistance-concrete)

## What the engineer sees

- Editable dimensions, length, materials, fire duration, effective-length factors, `N`, `Mx`, `My` and individual reinforcement bars.
- **Live interactive Plotly section** with true-scale bar circles, overall dimensions, optional spacing chains, per-bar `x / y / Ø` labels, clear face cover and temperature on hover (after calculation).
- Immediate **K18 numerical baseline**, with both variants displayed in the same results table. On changes, an explicit Calculate action updates the result and exported reports; the drawing updates live even before recalculation.
- A printable, self-contained HTML report with section diagrams, loads, reinforcement schedule and computed results: open the file in a browser and select **Print / Save as PDF**.
- Downloadable calculation JSON and editable input JSON.
- Optional original-layout Word report, when the exact original `Пример.docx` is uploaded in the session. K18 geometry + supported actions produce the 32-page original layout; changed reinforcement/geometry produces a clearly marked *diagnostic* report with the original frame and stamp.

## Why calculations may differ from the old K18 report

There is **one interface**, but an internal applicability gate protects the original report:

1. **Exact K18 pattern** (geometry, 8 bar locations per variant, Ø20/Ø25, material, 90-minute fire and original effective lengths) uses the independent Mathcad-reproducing Python solver. Its v2 is compared with the provided `.xmcd`, and v1 follows the supplied reference report. Load changes are recalculated with the same method if the fixed report can represent them.
2. **Modified dimensions, bar positions/diameters or material/fire conditions** trigger an **experimental numerical fiber-section solver**. Results are not the original Mathcad calculation, and the single-axis checks **do not certify** biaxial fire-resistance or R90.

Never substitute experimental results into the original 32-page normative prose without explicitly updating that prose. The original client template and Mathcad file are not committed to the public repository.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

On Streamlit Community Cloud use repository `dmitrievii/fire-resistance-concrete`, branch `main`, main file `streamlit_app.py`.

## Tests

```bash
python -m unittest discover -s tests -v
```

The CI suite checks K18 numerical continuity, automatic solver switching, dimension/diameter drawing data, printed summaries, runtime input normalization, and the Streamlit first-run session. With the approved template present locally, it also checks byte-exact reproduction of the reference Word master.

## Security and limits

The client’s `Пример.docx`, Mathcad `.xmcd`, licensed standards and sensitive data **must not** be committed to the public repository. Uploaded Word templates are retained only in temporary session/processing memory and deleted after report generation; public Community Cloud is not a confidential file vault. The general model remains experimental; there is no verified full biaxial N–Mx–My interaction, spalling or normative certification.


## R0.7 — engineering reinforcement definition

Under **3 · Reinforcement layout**, every reinforcement variant can use:

- **Perimeter layout** (default for K18): bar diameter Ø [mm], counts along both horizontal faces `nx` and vertical faces `ny`, and either *edge-to-bar-centre offsets* or *centre-to-centre spacing*. Corner bars are counted once: `n = 2nx + 2ny − 4` (up to 64 bars).
- **Symmetric edge distances**: one horizontal and one vertical offset automatically apply to opposite edges. Disable this to specify left/right/bottom/top independently.
- **Spacing-driven definition**: choose `sx` and `sy`. For symmetric layouts, edge distances are calculated; for asymmetric layouts, specify the first bar's left and bottom offsets and the far-side distances are calculated.
- **Custom coordinates**: advanced per-bar ID, x, y, Ø editor for nonuniform and irregular reinforcement.

All distances are in millimetres. **Edge-to-bar-centre is not concrete clear cover**: clear cover = edge-to-centre − Ø/2. The UI shows both, as well as total steel area and true-scale dimensions. Changing the section size regenerates valid perimeter bars immediately. Invalid cover, overlap, spacing or bar counts are blocked rather than silently clamped. Both the printable HTML and the experimental DOCX diagnostic now include the engineering reinforcement definition. The unchanged K18 case still exports the identical 32-page reference DOCX when the approved master is uploaded.


## R0.8 — Default sanitized engineering report

The public repository includes `templates/RC_Fire_Report_Master.docx` (sanitized copy of `Пример.docx`). Its engineering frame, stamp structure, tables, equation objects, reinforcement drawings, and 32-page format are preserved. Client/contract identifiers, project-specific drawing reference and author metadata have been removed, with neutral `RC-DEMO` stamp code. This demo master is intended as a template, **not** an issued client-certified engineering report. The specific K18 engineering example remains visible in the body.

Under **5 · Word report**, select **Generate Word report** without uploading anything; the app loads the bundled master. The advanced override accepts only the SHA-256-verified sanitized or original K18 document. Missing or modified templates fail closed. K18 calculation reproduction and experimental parametric report generation remain separate calculation provenance internally.

The sanitized master SHA-256 is `12b2a9b290ea8ef6652a048c3aab09f6685b44fb955ad2985a8538fad15bcb5a`.

## R0.6.9 — Time-dependent member checks

Column pages now include an on-demand fire-time calculation from t=0 with
fresh Annex K/member solves, refinement of the first observed limit, and
separate handling of strain events, equilibrated instability, model-domain
stops and unresolved numerical solutions. Results and source inputs export
to JSON/CSV and the Word/ZIP reports. Source edits invalidate old histories.
The inherited material/member model remains diagnostic; a temperature-domain
stop or Newton failure is not reported as fire failure. See
[R069_TIME_HISTORY.md](R069_TIME_HISTORY.md) for scope and verification.
