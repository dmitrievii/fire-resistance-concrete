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