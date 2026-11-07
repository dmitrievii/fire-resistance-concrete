# R0.6.4D — Permanent source integration

R0.6.4D is committed as ordinary Python source files on this feature branch, not assembled dynamically from a ZIP. The temporary candidate archive and CI test-fixture adapter were removed.

Scope: R0.6.3A–C constitutive diagnostics, R0.6.4A–C heated beam-column and ULS diagnostics, R0.6.4D project integration, Streamlit UI, reporting and regression tests.

## Verification

Run from the repository root:

```bash
python -m pip install -r requirements.txt
python -m compileall -q streamlit_app.py multicolumn_r05 rc_fire tools
python -m unittest discover -s tests -v
python -m tools.validate_constitutive_r064d
```

Two GitHub Actions workflows run on PRs: the existing Python calculation and report contract, plus R0.6.4D full source integration acceptance. The latter also tests first-run Streamlit and Word report generation.

## Boundaries

- This release is **diagnostic only**, not qualification to claim R90.
- `normative_claim=False` and `fire_resistance_status=not_demonstrated` are retained.
- Heat-field data for each required longitudinal station must be provided explicitly.
- No automatic replacement of historical Mathcad outputs by the research beam-column solver.
- Fire material constitutive limitations and action combinations remain subject to independent normative validation.

Do not merge until the full direct-source CI run is green.
