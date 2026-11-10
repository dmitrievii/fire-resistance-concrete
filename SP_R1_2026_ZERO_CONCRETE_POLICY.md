# SP-R.1 — SP 2.02.05-2026 material law with user-defined hot concrete cutoff

**Design decision:** Calculate actual heated column first-failure time `t_R` by **СП 2.02.05-2026 §§8.2.16–8.2.23** and SP 5.03.01-2020. Do **not** use Table 3, 500°C critical-isotherm strength shortcuts, or Eurocode constitutive coefficients as if they were SP. Existing TKP FVM solver may supply only an explicitly unqualified numerical temperature field during this interim integration.

## User's high-temperature concrete assumption — implemented exactly

- At **T=800°C**, use the last actual row of **SP Table9**, not zero: heavy siliceous `k_c=0.10`, `beta_E=0.05`; heavy calcareous `k_c=0.15`, `beta_E=0.10`.
- At **T>800°C**, by **user engineering assumption**, set `k_c=0`, `beta_E=0`, concrete compressive/tensile stress=0, concrete stress tangent=0, concrete strength=0, concrete Young modulus=0. This state contributes no concrete section resistance, including concrete displaced by reinforcing bars.
- The discontinuity at **800°C+** is a **numerical-model choice**, not a coefficient provided by Table 9. Refined time-stepping and a separate transition-sensitivity test are mandatory before using the resulting failure time in a project report.
- Other SP5 normal-temperature properties still have to be confirmed for real concrete. A zeroed fibre is not equivalent to physical spalling or removing steel reinforcement.
- **Steel is not zeroed** above 800°C. SP Table10 ends there and the user has selected a zero-tail **only for concrete**. A bar >800°C blocks this mechanical scenario until a source-qualified steel policy is supplied.

## SP material constitutive sources

| Quantity | Source | Implemented |
|---|---|---|
| Ordinary concrete (k_c(T)), (eta_c(T)) | SP 2026 Table9 | yes, 20–800°C; user 0 tail at T>800°C |
| S240–S500 steel (k_s(T)), (eta_s(T)) | SP 2026 Table10 | yes, 200–800°C; 20–200°C ambient interpolation explicitly engineering-assumed |
| Parabolic-linear concrete (sigma_c-epsilon_c) | SP 5.03.01-2020 §6.1.5.4, Eq(6.17)/(6.18), Table6.1 | implemented in first-order sections with SP hot compressive strength |
| Bilinear steel with horizontal branch | SP 5.03.01-2020 §6.2.2.13 | implemented in first-order sections, no invented limiting steel strain |
| Concrete expansion/shrinkage coefficients | SP 2026 Tables11/12 | integrated as signed numerical coefficients, **irreversible history treatment not yet source-qualified** |
| Steel thermal expansion | SP 2026 Eq(6): (alpha_{st}=(0.005T+11.5)10^{-6}) | integrated analytically from 20°C |
| Source-specific SP modulus | SP 2026 Table9/10 | computed independently; tangent of SP5 parabolic fibre law is not forced to equal the specified (eta E_{cm}) |
| Full thermal solver conforming to SP §8.2.23 | SP thermophysical equations and qualified boundary | **pending SP-R.2**. Current preview explicitly consumes existing TKP FVM snapshots |
| Strain-compatible full-column (U(t)), (t_R), Rrequired PASS/FAIL | SP §§8.2.16, 8.2.20–8.2.23 | **pending SP-R.3–R.7**; still NULL and NOT_ESTABLISHED |

## API

- `rc_fire.materials.sp2026_fire.concrete_at_sp_fire`: SP material factors with explicit zero concrete tail.
- `steel_at_sp_fire`: SP steel table, fail-closed >800°C.
- `concrete_stress_sp`, `steel_stress_sp`: source-specific SP5 fibre stress and tangent.
- `concrete_free_thermal_strain_sp`, `steel_free_thermal_strain_sp`: source-traceable temperature expansion calculations.
- `rc_fire.mechanics.sp2026_section.prepare_sp2026_section`: map one saved FVM snapshot to actual SP heated fibre inventory for arbitrary specified reinforcement.
- `evaluate_sp2026_section_at_time`: first-order SP heated-section equilibrium for actual entered N/Mx/My, never a whole-column limit.
- `fire_assessment()['sp2026_stage1_at_required_time']`: explicit new SP preview, separately from older TKP diagnostic fields. Both still return R_t=None.

## Important physical/normative blockers

1. Source SP2026 thermal conductivity, cp, density and boundary calculation, flux convergence, temperature/bar coordinate uncertainty (SP-R.2).
2. SP5 ULS concrete characteristic versus design resistance safety factors and the compatibility of SP material modulus (eta E) with the chosen parabolic mechanical tangent; verify the intended section and member stiffness implementation (SP-R.3).
3. Irreversible concrete thermal shrinkage during non-uniform non-stationary heating; currently an **assumed signed coefficient integral**, not a qualified history law.
4. Whole-member support conditions, first/second-order N–Mx–My load distribution, initial imperfections, global stability and exact strain-compatible ultimate capacity (lambda_R(t)) (SP-R.4).
5. First physical t_R including 800°C+ discontinuous concrete cutoff time-refinement and loss-mode classification, not Newton divergence or an arbitrary fixed load scan (SP-R.5).
6. Spalling protection/Annex Л methodology and independent validation under applicable Belarus provisions; actual material certificates (SP-R.6/7).

**Result of SP-R.1:** real SP-specific heated concrete and steel **material response** and **first-order section equilibrium** connected to a time-stamped numerical 2D thermal field. **Not yet** actual column utilization `U(t)`, structural fire-resistance time `t_R`, nor validated R90 acceptance. A source-derived coefficient must never be confused with the user's T>800 engineering convention.
