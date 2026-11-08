# R0.6.8 — Belarus Annex L and single-source concrete properties

**Active normative sources:** СП 2.02.05-2026 and СП 5.03.01-2020. No Russian concrete spalling index, lookup table, interpolation or threshold is used in the active calculator.

## Removed duplication

Concrete class, fire aggregate family, density, Ecm, thermal expansion and conductivity are resolved from the existing `material_spec` and `thermal_spec`. **Fine-grained status is calculated** from documented coarse aggregate content, never a manual Boolean. A positive coarse fraction or explicitly named gravel/granite coarse aggregate gives *not fine-grained*; a documented zero coarse fraction gives *fine-grained*, unless it conflicts with the named aggregate. Without composition the status is *unknown* and Ecm remains unresolved. SP 5.03.01-2020 §6.1.2.1 requires identification of fine-grained groups A/B in construction documentation. Annex L stores only extra measured/mix properties that these sources do not contain:

- Whether natural sand is actually present;
- Coarse aggregate volume fraction (0–100% for composition; Annex L.1 is valid only at 35–50%);
- Maximum aggregate size;
- Cement consumption (kg/m3);
- Water/cement ratio;
- RH and/or a separately documented measured mass moisture Wc.

The old `spalling` dictionary is kept as **archived input only**. Compatible, explicitly entered *physical* values may be imported on first save. Historical F, Russian coefficients and classifications are never reused. All new F results come from Annex L.

## Calculation traceability

- Formula Л.1: F = αF αbt β Ec ρ0 Wэ / (K1c λк np);
- Constant αF, β from Л.2;
- K1c from Table Л.1 at 35/50% coarse aggregate, with **explicitly permitted linear interpolation** in 35–50% and 1.14 multiplier above 10 mm;
- Porosity np from Л.2/Л.3 according to W/C;
- Wэ from Л.4, moisture: exact Table Л.2 nodes are preferred; otherwise formula Л.5 uses the given cement quantity and independently supplied W/C to calculate water consumption. Its numeric output requires an explicit percent-to-kg/kg interpretation, flagged as unqualified. An optional exploratory bilinear interpolation of Л.2 is labelled *not prescribed by the standard*;
- αbt from Table 11 and λк from Annex K;
- Ec from СП 5.03.01-2020, Table 6.3;
- Results sampled at 200, 250, 300°C, showing the maximum F over this discrete evaluation. This three-point envelope does not certify the true continuous maximum without further analysis.

Criterion: F≤4 no spalling predicted; 4<F≤6 potentially dangerous; F>6 spalling predicted; protection is required when F>4 (Л.6). A favorable F is **not** an R90 certificate.

## Deliberate scope restrictions

1. **Annex L formula Л.5 unit ambiguity:** the literal empirical expression using cement Ц and water В in kg/m3 produces numerics of the order of percentages while its variable definition specifies Wc in kg/kg. The current *automatic diagnostic* route uses exact Table Л.2 values when available, otherwise Л.5 with **explicitly declared** /100 conversion and a `moisture_method_qualified=false` warning propagated to the normative preflight and Word report. An opt-in bilinear interpolation of Л.2 is labelled experimental, not prescribed by the text. Neither route silently counts as normative approval. For Ц=500 kg/m3, В/Ц=.4 and RH=55%, Л.5 gives 0.024619 kg/kg while linear Л.2 interpolation gives 0.0292 kg/kg: methods are not interchangeable.
2. No use of Table Л.1 for incompatible *fine-grained* concrete with 35–50% coarse aggregate.
3. Expanded-clay mix requires separate porosity and mechanical-property qualification.
4. Intermediate density from Annex K may still have its own normative interpolation uncertainty.
5. The old R0.5.6 numerical mechanics remains diagnostic and cannot approve R90.
6. Russian SP468 remains solely in an archived comparison module and its tests; it is not used in main calculation, any report, or the current user-facing interface.

## Acceptance

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_r068_by_annex_l -v
```
