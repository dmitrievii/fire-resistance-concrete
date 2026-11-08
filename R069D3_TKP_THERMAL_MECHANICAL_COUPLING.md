# R0.6.9D3 — unified transient heat transfer and TKP RC mechanics

## Normative sources and limits

Primary user-supplied: ТКП EN 1992-1-2-2009 (02250), with Belarus National Annex, §§3.3.2 (cp, density), 3.3.3 (conductivity), 4.3.2 (advanced thermal analysis), 4.3.3 (thermomechanics), and 4.3.4 (validation). In the Belarus NA the **lower bound** of the normal concrete conductivity is mandatory. The source allows ignoring explicit moisture migration (§4.3.2(3)) and the local influence of bars on concrete temperature (§4.3.2(4)).

Reference heat-transfer boundary, selected EXPLICITLY:
- **Standard fire gas** theta_g(t) = 20 + 345 log10(8t+1), from СП 2.02.05-2026 equation (3). EN 1991-1-2 was not supplied, so its additional fire-action/boundary provisions are not assumed fulfilled.
- **Convection 25 W/(m²·K)** and concrete **emissivity 0.7** from the reference conditions of Annex A of the user-supplied TKP. A different fire exposure must be independently declared and supported.
- Explicitly selected gravimetric water fraction for thermal cp, initial **1.5%** as in the published TKP Annex A reference temperature curves. The user's RH=44% is **not** automatically converted to a water fraction; Appendix L spalling moisture formula and thermal cp percentage are separate models.
- Concrete density is the user's actual 2200 kg/m³, not a tabular replacement. Unexposed surfaces are *explicitly adiabatic*, not fictitiously exposed.

### Governing energy equation

The cell-centred 2D solver integrates

\[
\frac{\partial H(T)}{\partial t}
=\nabla\cdot[\lambda(T)\nabla T],\qquad
H(T)=\int_{20}^{T}\rho(s)c_p(s)\,ds.
\]

The exterior surface enforces

\[
-\lambda\frac{\partial T}{\partial n}
=h_c(T_g-T_s)+\epsilon \sigma[(T_r+273.15)^4-(T_s+273.15)^4]
\]

with an implicit half-cell conduction resistance and a secant-linearized **exact radiative fourth-power difference**. Each interior neighbour face uses the harmonic conductivity in equal and opposite fluxes. Backward implicit time stepping uses the exact tabulated enthalpy difference per cell instead of a fixed ambient cp, and Picard iteration until the nonlinear solution and global energy budget agree; nonconvergent steps are reduced automatically, and still fail-closed if unresolved. The source properties remain bounded to 20–1200 °C.

The result includes true cell temperatures, calculated face-surface temperatures, four-face temperature extrema, total input heat per metre of column, stored enthalpy increase and their relative residual, number of steps and source parameters.

### Physical significance for user K1

At t=90 min the specified standard gas curve gives **1005.987666 °C**. A heating-only thermal model with no internal heat generation obeys the maximum principle: temperatures inside the section cannot exceed the maximum applied gas temperature. Thus this self-contained heat-transfer branch cannot produce the ~1132 °C corner predicted by the separate Annex K analytical field under these boundary conditions. That discrepancy is evidence of a need to adjudicate the thermal models; it is **not** an a priori proof of a bug in Appendix K or an experimental validation of the new FVM model.

Concrete strength/deformation relations in TKP Table 3.1 are fully specified for 20–1100 °C. Provided the computed K1 90-min boundary values remain below 1100 °C, the D1 concrete constitutive gap in 1100–1200 °C **does not apply to that particular modeled scenario**. This does not fix missing material information or validate the whole-column resistance.

### Exactly one field through mechanics

The D3 coupling computes one heat history, saves requested time-matched snapshots, and calls the D2 TKP nonlinear fibre law using **the native solved 2D temperature field**, not SP Annex K temperature_rectangle. Bar temperatures are obtained by bilinear interpolation from actual cell-centre and surface temperatures (TKP §4.3.2(4)). Actual individual steel bars are preserved and their temperature-dependent thermal free elongations and stresses are computed separately. Every time node uses its own stored state; no stale field is reused.

The optional second-order P–Δ beam is built from actual section laws at all nodes and three Gauss locations per element only after explicit N+q, end supports, node count and a *user-supported uniform along-length heating assumption*. This independent member action pattern is **not equivalent** to isolated user-entered Mx/My without proof.

### Numerical evidence and acceptance

- Source material/property nodes and Belarus Annex A boundary values.
- Energy audit: each step and cumulative relative balance below **3e-4**.
- Maximum principle: no heated point above the applied standard gas temperature, no nonphysical below-ambient result.
- All four-face section symmetries, and hotter edges than inner faces at early times.
- Actual K1 bar sample coordinates and same-time mechanical transfer.
- Non-exposed/adiabatic case stores zero net heat and stays at 20 °C.
- Optional reproducible **spatial grid and time step** sensitivity comparison (8×8 vs 12×12; original dt vs half dt).
- Global code base and Streamlit tests remain unmodified.

### Unresolved release blockers for a normative t_R

1. The full source EN 1991-1-2 boundary protocol and independently validated fire action; the explicit SP gas curve and TKP Annex A coefficients are a clearly identified reference scenario.
2. Thermal mesh/time convergence (code added, actual project thresholds to be assessed) and measured-temperature comparisons with appropriate fire tests.
3. Real gravimetric moisture measurement or justified value; the 1.5% Annex A baseline may not describe K1.
4. S500 steel manufacturing route (hot-rolled/cold-worked) and ductility (A/B/C); they cannot be inferred from the label alone.
5. Actual end restraints, supports, frame action diagram, initial geometric imperfections, thermal restraint along the column, and correspondence to the input N=50 kN and Mx=2 kNm.
6. Concrete spalling, transient creep and history-dependent/mechanical material stress-strain qualification; source §4.3.3 and §4.3.4.
7. Genuine first-loss-of-carrying-capacity detection, e.g. path following and dynamic instability/large deflection qualification; **nonconvergence is not collapse**.

**No numerical equilibrium, stable lambda=1, or thermodynamic energy closure by itself establishes R90.** This release returns R_t_minutes=null and normative_claim=false on every execution path.

## Dependency and rollout

D3 PR #17 is stacked on D2 PR #16 (and D1 PR #15). All three are currently separate from main; unrelated K18 audit PR #14 must be integrated only with its own approval. Merging #17 before #15/#16 will duplicate their changes into main; use a deliberate dependency order or rebase.

## Acceptance

\`\`\`bash
python -m compileall -q rc_fire multicolumn_r05 streamlit_app.py
python -m unittest discover -s tests -p 'test_r069d3_tkp_heat.py' -v
python -m unittest discover -s tests -v
\`\`\`

Two GitHub CI workflows must be green before merge. Licensed source PDFs/DOC never enter this public repository.
