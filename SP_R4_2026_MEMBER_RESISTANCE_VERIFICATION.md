# SP-R.4 — whole-column load-path resistance and fire-time evolution

**Status:** Draft numerical implementation. Not a certified Belarusian fire resistance design methodology. No automated merge.

## Priority and normative references

1. **СП 2.02.05-2026 §§8.2.16–8.2.23** — longitudinal member fire endurance is time to insufficient load-bearing capacity, based on a thermal field and corresponding temperature-dependent material behaviour.
2. **СП 2.02.05-2026 §8.2.18, Tables 9–10** — temperature-dependent concrete and steel strength/stiffness reduction.
3. **СП 5.03.01-2020 §8.1.2.1–8.1.2.4** — general compatible strain and axial/biaxial moment equilibrium, section stiffness, design strain criteria.
4. **СП 5.03.01-2020 §8.1.1.5** — for compression sections, minimum eccentricity e0=max(h/30,20 mm) in the corresponding bending plane.
5. **СП 5.03.01-2020 §8.1.6** — column slenderness, longitudinal buckling and second-order effects.

The numerical two-axis P–Δ formulation is provided by SP-R.3; no separate Eurocode or TKP concrete/steel law or tabular R90 lookup occurs.

## Governing model and evidence

At a **single stored time** t, take temperature snapshot SP-R.2, temperatures of actual reinforcement, SP-R.1 concrete and steel law (SP source), user-defined full-length exposure or individually supplied nodal and Gauss thermal fields, explicit supports in x/y, initial imperfections and all first-order member actions.

Compression-positive section compatibility is e_mech(x,y)=e0+kappa_x y+kappa_y x+eps_th(x,y). Section N/Mx/My are integrated over actual concrete fibres, displaced concrete at rebar, and actual steel bars. The full nonlinear beam-section tangent uses the axial Schur reduction and supplies a two-axis geometric-nonlinear Euler–Bernoulli beam-column FE formulation.

**SP-R.4 refinement:** at every section equilibrium, check not only interior fibre centres but also the *actual* 4 corners and 4 midpoints of faces using source-matched SP-R.2 surface temperatures. Boundary concrete at θ>800 °C has zero resistance **solely per the user's declared out-of-table assumption** (the SP tabulation still has nonzero strength at 800 °C). A finite sampling of eight boundary locations still cannot guarantee a continuous-section extremum; spatial refinement and additional maxima searches remain mandatory.

Let F_fi denote a complete, already combined **fire-design** load pattern (positive compression N, transverse q, member nodal forces). For a fixed thermal state, trial all mechanical actions on the same proportional ray:

    F(λ) = λ F_fi,   λ>=0.

Initial geometric imperfections are fixed; they are not multiplied by λ. Heat and member constraints are fixed at that fire time. Store complete evidence at all finite-element Gauss sections and both sides of every beam node.

### Classification (MUST NOT conflate)

| State | Required evidence | Permitted interpretation |
| --- | --- | --- |
| EQUILIBRATED_WITHIN_CHECKED_MODEL_LIMITS | converged two-axis FE branch; Gauss and both-sided nodal section check strains complete and within bounds | sampled state admitted **in this model**, not normative ULS |
| EQUILIBRATED_SAMPLED_STRAIN_LIMIT_EXCEEDED | converged equilibrium with local SP5 check-branch concrete or steel strain criterion exceeded | violation of **sampled model criterion**, not automatically physical global column failure |
| UNRESOLVED_MEMBER_STATE | Newton failure, singular / nonpositive tangent, unsupported temperatures, missing checked station, incomplete material | neither proof of survival nor proof of failure |

An interval is refined **only** if consecutive evaluated increasing load factors are explicitly WITHIN then EXCEEDED, and every refinement step remains resolved. Any unknown between them **invalidates** the bracket. Failures encountered before the first sampled λ do not become a first-limit estimate. Multiple nonlinear equilibrium branches/snap-back remain unqualified.

When a bracket [λ_L, λ_H] exists, the proportional model-only load utilisation index lies in the numerical interval

    1/λ_H <= U_model <= 1/λ_L.

It is **not** U_member(t) until the verified physical capacity on that action ray has been established, including global instability, post-peak constitutive behaviour and longitudinal continuity. Neither a strain ratio at the required load nor failure of a numerical iteration is U(t).

The source of a minimum eccentricity requirement, e0 >= max(h/30, 20 mm), is recorded with explicit N*e0 moments in each axis. These moments are **not automatically superimposed** on already precombined fire-design loads (which could double-count them). Reconciliation of initial/load eccentricity and of full longitudinal first-order moment diagrams is still a qualification blocker.

## Independent source-model axial stress-relaxed overbound

For each actual heated member Gauss and nodal section, compute a deliberately relaxed axial strength upper bound:

`N_upper,disc(t,z) = Σ_c A_c f_c,SP(T_c) + Σ_s A_s f_s,SP(T_s)` (MPa×m²×1000 gives kN).

This independently maximises each concrete/steel stress and does **not** enforce compatible strain, subtract displaced concrete, account for second-order effects or impose a strength interaction envelope. It therefore **overestimates** the axial resistance of the **discretised source model**. The upper bound for the member is the minimum of these station-wise overestimates; a necessary diagnostic condition for axial equilibrium is `N_fi <= min_z N_upper,disc`. This is not a mathematically certified upper bound for the entire continuous concrete body unless section discretisation and the material/thermal laws have been independently qualified.

The corresponding **lower bound on model-only axial utilisation**, `N_fi/min_z N_upper,disc`, is intentionally distinguished from the conditional two-axis inverse-load-factor interval. It is never represented as the true complete-column `U(t)`. If it exceeds 1, the source model's discretised axial stress envelope is exceeded even before compatibility/stability; a nonlinear solver failure is **not** needed to establish this restricted fact. Values are recorded at each requested fire time.

## Time-dependent evidence

`scan_sp2026_resistance_time_history(...)` repeats the **entire** independently prepared SP-R.2 → SP-R.1 → SP-R.3 → SP-R.4 capacity search at each requested *stored* fire time. It reports every evaluated time, nominal λ=1 state, optional conditional U_model interval and observed between-sample model strain-limit transitions. It does not generate synthetic temperature histories, smooth the user >800 °C concrete discontinuity, report first physical t_R or label unexamined intervals as safe.

The Streamlit UI offers an **explicitly confirmed restricted model**: pin–pin both axes, uniform q inferred from first-order midspan M=qL²/8 only when separately confirmed, prescribed uniform longitudinal fire and individually entered x/y initial imperfections. A separate checkbox opts into load scan; an additional independent checkbox opts into the three-time SP-R.4 history. Default form remains first-order no assumed member or resistance. The general programmatic API supports explicit different node and Gauss thermal fields and independent end supports.

## Outstanding normative and scientific P0 blockers

- **Material mechanics.** SP Table 9/10 reduced elastic modulus βE must be reconciled with SP5 complete nonlinear material stiffness and the §6.1.5.4 design-check parabola; the present hybrid operating boundary is not independently qualified. SP5 §8.1.2.1 check-branch steel tensile 10‰ is used, but full nonlinear ε_ud and hot steel buckling, concrete tension/stiffness reduction, creep and signed thermal shrinkage time histories are not fully resolved.
- **Global mechanics.** Finite-element small-rotation Euler–Bernoulli model is not a three-dimensional frame. End connections, axial restraint/thermal reaction, q/M reconciliation, actual eccentricity, shear/ torsion and global frame force redistribution are project-dependent. The user-confirmed pin–pin q model is only one option.
- **Physical failure.** Sampled strain exceedance is not proof of first physical collapse; an independent stability/postpeak criterion and mesh/time/continuation verification are required before `λ_R(t)`, `U(t)` and `t_R` are suitable for normative design.
- **Heat and local failure.** SP boundary radiation/convection, moisture transport, influence of steel on temperatures, concrete spalling (Annex Л), source-matched SP Annex Ж reference fields and test data remain unresolved.
- **Verification.** Compare slenderness and Euler–Bernoulli P–Δ stiffness with independent analytical limits and appropriate nonlinear FE; assess spatial mesh, load factor increments, temporal resolution, first physical failure time and published RC column fire tests (axial and biaxial, transient heating, restraint).

## Executable verification

`tests/test_sp_r4_resistance.py` includes pure bracketing tests (monotone known, unknown before/inside bracket, exceedance at first factor, invalid controls), actual SP thermal-to-hot-2D fibres-to-beam-FEM tests, minimum eccentricity values, boundary vs cell-centre extreme strain, true R0.7 full public facade, and multiple exact stored fire time calculations. Testing passing is necessary but not evidence of independent experimental qualification.

**API contract remains deliberately explicit:**

- `U_member_t=None`, `actual_U_member_t=None`, `R_t_minutes=None`, `t_R=None`, `regulatory_result="NOT_ESTABLISHED"`;
- temporary `observed_model_resistance_bracket`, `model_only_utilisation_interval` are diagnostic, with provenance and blockers.

### Stacked PR discipline

PR #26 (SP-R.1) → #27 (SP-R.2) → #28 (SP-R.3) → #29 (SP-R.4). All staged unmerged. Do not merge, release, claim R90 compliance or certify without explicit approval, independent mechanical/material/thermal qualification and green CI.
