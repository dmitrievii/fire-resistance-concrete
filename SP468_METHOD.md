# SP 468.1325800.2019, amendment 1 (2023): spalling F reference implementation

## Status

`multicolumn_r05/sp468.py` implements a **separate Russian SP 468 reference calculation** for concrete explosive spalling, using §9.7 and Tables 9.1–9.7 (porosity/water content equations 9.2–9.6). This does **not** replace the Belarusian TKP 45-2.02-110 Annex K or certify R90. The original manual K18 input mode remains available.

Normative text used: https://internet-law.ru/documents/prod/pravila/0/sp_39284.html (amendment 1, 2023). The module stores the source and each table's provenance with results.

## Equation and units

`F = a * alpha_bt * E_bt * rho * W_e / (K1_prime * lambda * porosity)`

- `a = 1.16e-2` W m^(5/2)/kg (SP468 equation 9.1)
- `alpha_bt` [1/°C], Table 9.1, interpolation at coarse aggregate contents 40–60%; heat-moisture treated ×1.1.
- `E_bt` [MPa], Table 9.2 for the separately specified concrete class **B**, heavy concrete or tabulated 1400/1800/2200 kg/m3 lightweight concrete; steam ×0.9, autoclave ×0.77.
- `rho` dry concrete density [kg/m3], **user input**.
- `K1_prime` [MN·m^(-3/2)], Table 9.5, with linear interpolation 20–50% coarse aggregate, correction ×1.14 when maximum particle size >10 mm, divide by 1.4 for heat-moisture treatment.
- `lambda` [W/(m·°C)], Table 9.3, interpolate at aggregate content 40–60%; never extrapolate. **First power**, not squared.
- `porosity` [m3/m3], equations (9.2)–(9.4) from cement content, W/C ratio, and optional porous aggregate information. Never supply percentage 10 as fraction 0.1.
- `W_e` [m3/m3], Table 9.6 mass moisture, equation (9.5) using the dry concrete density, and optional porous aggregate correction equation (9.6) with Table 9.7.

## User input; no guessed mix from C30/37

Aggregate type, content 40–60%, Russian B class, curing process, dry concrete density, cement content 200–700 kg/m3, W/C 0.3–0.7, design ambient RH 15–75%, and maximum aggregate size. Porous aggregate also needs its porosity and volume fraction. **No automatic mapping from C30/37 to B30**: the classes belong to distinct classifications and are not interchangeable without material documentation.

When the material combination has no Table 9.5 `K1_prime` (e.g. limestone sand and limestone crushed stone), no value is fabricated: F is `not_evaluated`. Unspecified fields remain unspecified, not zero. Invalid/out-of-table inputs fail closed. The UI is per column; input JSON contains the selected method and concrete mix for reproducibility.

## Outcome ranges (SP468 §9.7)

- `F ≤ 4`: `index_at_or_below_threshold` (SP468 index screening).
- `4 < F < 6`: `requires_structural_check` (further check by SP468 §9.9; not a PASS).
- `F ≥ 6`: `protection_required` (mitigation per SP468).

Note: a conclusion on the overall fire-resistance R90 is always `not_demonstrated`, regardless of the F result. Evaluation under the Belarusian TKP remains a separate, explicitly labelled mode.

## Backward-compatible K18 manual mode

`manual_k18` still accepts nine parameters, using corrected first-power λ and converting the existing UI `n_p_percent` into a fraction (`n_p_percent/100`). Previously stored numeric-only dictionaries without `method` are interpreted as manual, not SP468. Existing exported projects with missing `spalling` or an empty object are interpreted as pending SP468. Results are *not* silently certified by prior F results because formula and units were corrected.

## Acceptance

`python -m unittest discover -s tests -v` includes independent table lookups, numeric result and unit checks, interpolation, all 3 thresholds, out-of-range failure, curing modifiers, missing-tabulated-K1 failure, isolated per-column state, JSON roundtrip, and manual mode backward compatibility.