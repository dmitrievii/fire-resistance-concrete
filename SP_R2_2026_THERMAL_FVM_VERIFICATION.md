# SP-R.2 — heat-transfer equation and physical coupling

**Target: SP 2.02.05-2026 §§8.2.16–8.2.23, NOT the tabular fire-rating method.**

## Implementation
- New independent `rc_fire/thermal/sp2026_heat.py`: uses ONLY source СП 2.02.05-2026 Appendix **К.1**, Table К.1 heat-transfer parameters **A/B/D/E** for heavy siliceous/carbonate concrete. Temperature-dependent conductivity `lambda=A+B*T`, specific heat `C=D+E*T`, plus **effective humidity capacity `0.05 Wc`** per formula (К.1). Exact analytic enthalpy integration preserves energy balance. Fixed supplied dry density is explicit. The concrete high-temperature >800 °C **zero-strength rule remains in SP-R.1 mechanics**, not mistakenly applied to thermal conductivity/heat capacity.
- Conservative 2D transient implicit FVM with nonlinear convection/radiation on individually exposed faces, harmonic internal conduction, local surface flux balance, timestep-halving when nonlinear iteration is stiff, per-time cell and surface temperatures, individual actual rebar-centre temperatures.
- **External h=25 W/m²K, emissivity=.7 are not supplied by SP §8.2.23**; explicitly carried as a *comparison* assumption from TKP Annex A. SP §8.2.23 calls for temperature-dependent thermophysical properties and heat-mass transport, but this implementation uses Eq К.1's effective humidity approximation rather than a coupled water/vapour PDE; never certified silently.
- **SP-R.1 mechanics is coupled directly to the SP-R.2 temperature field at the exact fire time**, via `prepare_sp2026_section` and `evaluate_sp2026_section_at_time`. No relabelling a TKP field as SP. Legacy TKP calculations are separate comparison only.
- New public SP thermal history to `2×Rrequired` (5-min resolution, plus shared mechanical times, exact t=0) with same-source rod temperatures, energy ledger and actual 2D field. Streamlit temperature plots and section heatmap now prefer SP if available; legacy TKP shown only with a warning. Section heatmap has white background and correct SP provenance.
- `sp2026_verification.py`: 3-grid + 2-timestep temperature convergence report for EVERY rod and concrete centre/surface; independent selected point comparison to official **SP Appendix Ж Table Ж.7** (400×400, four sides, 90 min), no coefficient fitting or assumed exact same boundaries.

## Qualification
Passing source-equation and balance tests establishes **numerical implementation**, not sufficient normative thermal or whole-column qualification. External boundary h/eps, moisture transport, mesh/time tolerance propagation, SP5 mechanical stiffness/shrinkage history, true member second-order ULS and t_R still require validation. `regulatory_result=NOT_ESTABLISHED`, `R_t_minutes=None`.

## Dependencies/merge order
This is a **stacked PR based on SP-R.1 PR #26**, not independently mergeable to main before #26. Do NOT merge without explicit user instruction and green CI.

## Tests
New `tests/test_sp_r2_heat_and_coupling.py` covers exact SP Table K.1 material values/dimensions, analytical enthalpy, energy closure, four-face symmetry, adiabatic boundary, bar-temperature/steel coupling, correct source labels, plot background, SP Appendix Zh comparison and real 3mesh/2dt study.
## Executed independent SP-R.2 numerical campaign — 10 Nov 2026

### K1 600×600 mm, eight Ø20, four-sided fire, 90 minutes

SP Table К.1 siliceous concrete; user's dry density **2200 kg/m³**, mass moisture **1.5%**; external comparison boundary **h=25 W/(m²K), ε=0.7** (not assigned by SP §8.2.23). All actual rebar positions are sampled from the single solved 2D SP temperature field.

| Quantity | SP 2D FVM, 16×16 cells, dt=3 min |
|---|---:|
| Fire gas temperature | 1005.99°C (SP formula 3) |
| Maximum concrete boundary temperature | **989.41°C** |
| Concrete centre temperature | **22.20°C** |
| Corner steel bars S1/S3/S5/S7 | **698.17°C** |
| Middle-face bars S2/S4/S6/S8 | **483.76°C** |

Mesh/time differences in the **maximum steel-bar temperature**:

| Change | Difference |
|---|---:|
| Mesh 8×8 → 12×12 at dt=3 min | **64.33°C** |
| Mesh 12×12 → 16×16 at dt=3 min | **3.29°C** |
| Time step 3 → 1.5 min on 16×16 grid | **0.73°C** |

The last two differences are within the **provisional numerical** 15°C bar-temperature threshold. The 8×8 field is NOT mesh-converged at R90. Even the 12×12 vs 16×16 comparison is **not proof of physical material/heat-transfer validation**. No standard-defined acceptable numerical error or laboratory qualification has been asserted.

The section source case is already connected to SP-R.1: concrete fibres strictly above 800°C lose all compressive strength/stiffness by the **user's explicitly non-tabulated rule**; heated steel remains governed by SP Table 10 and blocks at T>800°C. No whole-column U(t), R(t), or fire-rating acceptance is inferred.

### Independent SP Appendix Ж, Table Ж.7, 400×400 mm column, four-sided R90

Eight selected official temperature matrix points were compared **without calibration**. With user K1 material/boundary parameters reused for a 400×400 source-shape comparison (not necessarily the undocumented physical assumptions behind the Annex Ж matrix):

- RMSE across eight points: **42.05°C**;
- maximum absolute deviation: **75.54°C**, at (40,200) mm, where SP Table Ж.7 gives 408°C and the source-based FVM gives 483.54°C;
- centre (200,200) mm: Table Ж.7 **38°C**, numerical **63.52°C**;
- outer corner (0,0) mm: Table Ж.7 **1002°C**, numerical **990.64°C**.

This benchmark is **NOT PASSED AS A PHYSICAL VALIDATION**. It does not prove a fault in the source formula implementation because the published table point comparison has not established equality of dry density, concrete moisture, exposed-face boundary convection/emissivity and other physical assumptions. All comparison inputs are retained in machine-readable evidence. Do not silently tune h, epsilon, rho or moisture merely to improve these numbers. Confirm matched reference conditions or obtain independent heated-column thermocouple data.

### Verification status

- Mathematically conservative energy ledger, all-face symmetry, actual steel positions, source heat material factors and SP5 coupling: **unit/integration tests pass**.
- K1 R90 high-resolution mesh/time **provisionally within selected numerical tolerances**.
- SP Appendix Ж.7 independent thermal temperature benchmark and boundary-condition qualification: **NOT QUALIFIED**.
- SP §8.2.23 explicit hygrothermal transport beyond the effective capacity approximation: **NOT QUALIFIED**.
- Full-member strength use and first loss time (t_R): **NOT ESTABLISHED**.

This evidence remains part of SP-R.2 and **does not assert a normative R90 PASS**.
