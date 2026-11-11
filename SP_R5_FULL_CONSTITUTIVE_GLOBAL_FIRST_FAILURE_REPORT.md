# SP-R.5 — nonlinear hot material law, global stability, first failure

**Normative hierarchy:** СП 2.02.05-2026 §§8.2.16–8.2.23 is the primary fire methodology. СП 5.03.01-2020 §§6.1.5.1–6.1.5.4, 6.2.2.13, 8.1.2 and 8.1.6 supplies the ambient reinforced-concrete mechanical model. No EC2 curve, TКП heat or tabular R substitute is silently introduced.

**Outcome:** an independent full SP5 constitutive research branch and an equilibrated-global-tangent stability auditor are implemented and regression tested. **The physically calibrated hot constitutive and first real global collapse model is not yet closed**. Therefore **no normative U(t), t_R or t_R≥Rrequired** can be issued. This is a scientific limitation visible in source data, not a software defect that should be concealed by changing formulas or marking test cases green.

## 1. Full uniaxial nonlinear concrete law (SP5 Eq. 6.13–6.16)

Implemented in `rc_fire/materials/sp2026_full_nonlinear.py`, with a distinct section entry point `prepare_sp2026_full_nonlinear_section` in `rc_fire/mechanics/sp2026_section.py`.

Compression-positive notation:
```text
eta = epsilon_mech / epsilon_c1
sigma_c = f_cm,theta * (k*eta - eta^2) / (1+(k-2)*eta)
k = 1.1 * E_cm,n,theta * epsilon_c1 / f_cm,theta
f_cm,theta = f_cm,20 * k_c(theta)
E_cm,n,theta = 22000*(f_cm,20/10)^0.3 * beta(theta) [MPa]
```
`epsilon_c1` is the ambient peak strain from SP5 Table 6.1; `epsilon_cu1` follows the figure in SP5 §6.1.5.1, and the derivative of the rational curve is implemented analytically. For each actual SP-R2 temperature, independently record `k_c(theta)`, `beta(theta)`, `f_cm`, `E_cm,n`, `epsilon_c1`, `epsilon_cu1`, and `k`. The SP2026 Table9 reduced ordinary Ecm and SP5 nonlinear `E_cm,n` are kept as **distinct source quantities**, not assumed identical.

**No physically sourced temperature-dependent `epsilon_c1(theta)` and `epsilon_cu1(theta)` are specified by the cited SP2026 §8.2.18 reduction tables.** Holding their ambient values under fire is an explicit provisional closure for testing; it must NOT be silently promoted to a validated material model.

### Material-domain contradiction demonstrated, not patched

For C30/37 with the Table 6.1 fcm=38 MPa and epsilon_c1=2.2‰, siliceous concrete and SP2026 Table 9, holding the ambient peak strain gives approximately the following derived `k`:

| Concrete °C | k_c | beta | Derived k |
| ---: | ---: | ---: | ---: |
| 20 | 1.00 | 1.00 | 2.091 |
| 100 | 0.99 | 0.85 | 1.795 |
| 200 | 0.98 | 0.70 | 1.494 |
| 300 | 0.95 | 0.50 | 1.101 |
| 400 | 0.85 | 0.40 | **0.984** |
| 500 | 0.80 | 0.30 | **0.784** |
| 600 | 0.60 | 0.20 | **0.697** |
| 700 | 0.20 | 0.10 | 1.046 |
| 800 | 0.10 | 0.05 | 1.046 |

When k≤1, the denominator `1+(k-2)*eta` vanishes for `eta=1/(2-k)` within the loading range, while the intended strain-at-peak formulation ceases to be physically admissible. **The exact source equations cannot be coupled this way to produce a regular hot stress–strain relation**. The implementation fails closed with actual T, beta, k_c and k instead of introducing arbitrary `epsilon_c1(theta)` or a fictitious plateau. No C30-class full hot stress law or t_R can be certified with this ambient-peak assumption. Other concrete classes/temperatures must be independently evaluated; the example is not a universal hot-temperature material fact.

At T>800°C, the user's **explicit convention** makes concrete strength and modulus zero; Table9 itself has nonzero values at exactly 800°C. Steel >800°C remains blocked. This is not a normative material extension.

## 2. Reinforcement law

SP5 §6.2.2.13 admits an idealised horizontal bilinear branch or a rising bilinear branch. The rising-branch *separate function* explicitly requires a measured/certified `k=f_tk/f_yk`, `epsilon_uk`, a design `gamma_s` and material provenance; `epsilon_ud=0.9*epsilon_uk` is used for the limited design branch. The temperature-dependent steel yield and E are reduced by SP2026 Table10 `k_s,` `beta`. Table10 does **not** provide a tested high-temperature reduction of steel `epsilon_uk` or fracture ductility. Numerical consistency of the branch therefore does not qualify a high-temperature rupture limit. No interpolation beyond declared `epsilon_ud` is made.

Crucially, the simplified-section tensile-steel **10‰** check is **not** allowed to substitute as a full nonlinear material failure criterion. In the full SP5 section option, that ratio is `null`, and checked complete member ULS remains `UNKNOWN` until an appropriate source-qualified hot `epsilon_ud` exists.

## 3. Global second-order equilibrium, stability, and first failure

Implemented in `rc_fire/member/sp2026_global_stability.py`:

```text
r(d,N) = F_internal(d,N) - N G (d+d_initial) + K_support*d - F_external
K_global_tangent = K_material(d,N) - N G + K_support.
```

The auditor reconstructs the actual FE displacement/rotation vector in both bending directions, actual complete load vector and two-axis supports, and explicitly checks the residual `||r_free||`. Only then are the eigenvalues of the **free-global-DOF** tangent matrix interpreted.

| Classification | Meaning |
| --- | --- |
| `EQUILIBRATED_STRICTLY_POSITIVE_GLOBAL_TANGENT` | strict positive local second variation of **that model equilibrium branch** |
| `EQUILIBRATED_NEGATIVE_GLOBAL_TANGENT_BRANCH` | an **equilibrated** mathematically unstable branch of the supplied FE model |
| `GLOBAL_TANGENT_NEAR_SINGULAR_UNRESOLVED` | numerical resolution around zero eigenvalue insufficient |
| `GLOBAL_STABILITY_UNRESOLVED` | equilibrium, material law, boundary or tangent not verified |

The ideal pinned perfect Euler column with **zero external transverse load** and zero imperfection is an independent analytical benchmark: `Ncrit=pi²EI/L²`. At `N/Ncrit=0.7`, the zero-deflection equilibrium has positive global tangent; at `1.2`, it remains an exact mathematical equilibrium but has a negative eigenvalue. A strict spectral bisection brackets the **first** ideal Euler instability without conflating iteration failure and physical instability.

For actual SP-R5 column `PreparedSP2026MemberResistance` can independently rerun the spectral check at any converged model trial (opt-in `global_stability_requested`). An uncertain or negative global tangent is **not** re-labelled as a certified fire failure; the load-trial classification becomes unresolved until first-path bifurcation and physical constitutive evidence are validated. Time-history output can record *sampled* stable→unstable equilibrated transition brackets, with the real first `t_R` deliberately null.

**Important:** signed eigenvalue on a single equilibrium is a local stability test. It does not prove that the equilibrium is the branch reached by the actual loading/thermal path, nor that a negative eigenvalue necessarily coincides with the first physically realized fire collapse. Arc-length/energy continuation, material history, imperfection calibration, and experimental validation remain necessary.

## 4. Mechanical integration and public diagnostics

- A **separate, explicitly selected** full SP5 concrete branch is available in `rc_fire.member.sp2026_member` and `rc_fire.member.sp2026_resistance`. It never overwrites the baseline §6.1.5.4 source branch. Inadmissible full-law material states block the trial with an actionable reason; they do not fall back to the simplified section law.
- Optional SP-R5 global spectral check reconstructs the equilibrium, so a negative eigenvalue is meaningful only where an actual solution exists.
- `r07_public.fire_assessment` and Streamlit report the full-law state, hot material blockers, and observed global eigen evidence. The input UI clearly marks these as research modes.
- Existing `U_model(t)` bounds and the independently relaxed axial `N_upper` remain separate; **no** full physical fire utilisation `U(t)` or `t_R` is invented.
- `tests/test_sp_r5_physical_and_global.py` independently checks (6.13) at ambient peak and derivative, hot k≤1 failure, steel rising-branch continuity/limiting strain, two distinct source concrete curves, perfect Euler stable/unstable global eigenvalues, first mathematical bifurcation bracket and non-equilibrium rejection, public full-law fail-close.

## 5. Non-waivable remaining physical admission evidence

| Gate | Unresolved requirement for normative `t_R` |
| --- | --- |
| M1 | Independently calibrated hot `epsilon_c1(theta)`, `epsilon_cu1(theta)` for the full concrete law, or a source-approved complete alternative constitutive method with SP2026 source priority |
| M2 | High-temperature steel `epsilon_ud(theta)`, verified material plastic/rupture behaviour and full SP5 ductility branch with actual mill tests |
| M3 | Irreversible concrete thermal shrinkage, transient strain, creep and stress history; temperature profile ≠ complete mechanical state for hysteretic material |
| M4 | Continuation of the actual stable global equilibrium branch until first verified physical load-bearing failure (including material softening, snap-back/bifurcation), longitudinal mesh/step convergence and both bending axes |
| M5 | Actual fire-design force and moment diagrams including normative minimal eccentricity, support stiffness, axial restraint and geometric imperfections; avoid double-counting |
| M6 | Temperature field material/boundary and spalling qualification under SP2026, including Annex Ж independent check; nonlinear stability cannot repair wrong temperatures |
| M7 | Independent uncalibrated experimental fire-column comparison under source-matched actual concrete/rebar properties, fire curve, restraints, load history and failure records |

**Conclusion:** `numerically_verified_global_spectral_criterion` for the tested ideal beam is supported; `SP2026_PHYSICAL_FIRE_MEMBER_FIRST_FAILURE_QUALIFIED = false`. Consequently `U_member_t = null`, `R_t_minutes = null`, `t_R = null`, `regulatory_result = NOT_ESTABLISHED`. The software is ready for targeted material tests and full unstable-branch numerical development, but a declared complete physical closure would currently be scientifically unsupported.

**Stacked PR sequence (NO MERGE):** #26 SP-R1 → #27 SP-R2 → #28 SP-R3 → #29 SP-R4 → #30 SP-R4Q → #31 SP-R5.
