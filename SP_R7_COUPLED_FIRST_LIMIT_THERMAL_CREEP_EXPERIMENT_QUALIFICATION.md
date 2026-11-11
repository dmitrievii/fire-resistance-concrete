# SP-R.7 — coupled hot RC section stiffness, nominal stability, first model limit, and independent qualification evidence

**Status:** source-based numerical implementation and verification campaign, stacked Draft PR #33 on PR #32. Do not interpret the results as certification of an arbitrary RC column fire-resistance time.

**Binding hierarchy:** СП 2.02.05-2026 §§8.2.16–8.2.23 is the fire methodology, with material Tables 9–12 and actual 2D heat. СП 5.03.01-2020 §§4.2.5.3,6.1.2,6.1.5,6.2.2,8.1.1.5,8.1.2 and 8.1.6 governs structural section and nominal-stiffness methods. No EN1992 fire stress curve and no tabular R90 surrogate are introduced.

## 1. Full coupled 3×3 source section matrix

SP5 §8.1.2.3 Eq(8.1–8.3) supplies the three generalized unknowns: axial strain and curvature in both principal-section bending directions. Eq(8.2) includes:

- `K_NN = Σ E'_i A_i`;
- `K_NMx, K_NMy = Σ E'_i A_i y_i, Σ E'_i A_i x_i` (signs depend on work-conjugate curvature/force convention);
- `K_MxMx, K_MyMy = Σ E'_i (I_local + A_i y_i²), Σ E'_i (I_local + A_i x_i²)`;
- `K_MxMy = Σ E'_i A_i x_i y_i`.

The actual section implementation uses `q=[epsilon0, kappax, kappay]` and `epsilon=epsilon0+kappax*(y−h/2)+kappay*(x−b/2)`, and positive moment `M=Σ sigma A(y,x)`. This change of curvature sign relative to SP5 Eq(8.3) makes the physical 3×3 matrix work-conjugate and symmetric, not a normative change. Steel rods replace displaced concrete for the actual secant Eq(8.2) material section, and the gross-concrete convention is separately retained for literal §8.1.6 Eq(8.56) comparison; no invisible double counting.

Crucially, SP5 Eq(8.2) requires the **current SECANT** `E'_i=sigma_i/epsilon_i` from the actual source 6.17/6.18 stress diagram at a solved equilibrium. The model produces this `SP5_8_1_2_SOURCE_SECANT_AT_EQUILIBRIUM` matrix separately, with explicit thermal eigenstrain and ultimate-strain disclaimers. SP2026 Table9/10 **ELASTIC MODULUS** `beta(T) E` is another, independently calculated source quantity `HOT_BETA_SOURCE_ELASTIC`; these shall not be equated or converted silently.

Full axial–bending coupling is condensed at fixed axial action by Schur complement:

```text
  K = [ K_NN    K_NM ]
      [ K_MN    K_MM ]

  D = K_MM - K_MN inv(K_NN) K_NM
```

Both symmetric eigenvalues, the stiffness-weighted neutral-axis offset and off-diagonal bending coupling are audited. When T(x,y) is not symmetric, suppressing K_NMx, K_NMy or K_MxMy is no longer permissible.

## 2. Explicit mathematical extension of §8.1.6

The scalar nominal law `Bnom=kc,nom Ecd Ic + Es Is` is implemented literally in SP-R.6 for uniform symmetry. For a 2D unsymmetrically heated cross-section, the standard does not explicitly prescribe a tensorial scalar-to-matrix map; **SP-R.7 implements one explicit, testable *research hypothesis*:**

```text
  S = diag(1, sqrt(kc_nom,x), sqrt(kc_nom,y))
  K_nom = S K_concrete(beta E, T) S + K_steel(beta Es, T)
  D_nom = Schur(K_nom, axial DOF)
```

Here `kc_nom,axis = k1a k2a,axis/(1+phi_eff,axis)`; `k1a=sqrt(fck/20)`, `k2a=min(0.20,n*lambda_axis/170)`; `n=N/(Ac fcd_eq)`. `fcd_eq=Σ Ac_i fcd(T_i)/Ac` is a non-normative homogenization. `kc_nom` is **not** fire strength coefficient `kc,fire(T)`.

The square-root symmetrization is one mathematically compatible way to maintain a symmetric nominal matrix, **not unique, mandatory, or explicitly specified in §8.1.6**; nor is it a complete hysteretic constitutive law. The concrete gross area contribution is retained for direct §8.1.6 agreement; steel contribution remains separate.

The real pin–pin column under confirmed uniform longitudinal thermal exposure and source-compatible constant transverse load uses principal-axis buckling, not two disconnected nominal amplifications:

```text
  D_nom = V diag(d1,d2) V^T
  Ncrit,j = pi²*d_j / L²
  A(N) = V diag(1/(1-N/Ncrit,j)) V^T
  [M2x,M2y]^T = A(N) [M0x,M0y]^T
```

The 3×3 source design section is independently re-solved at `N,M2x,M2y` for limits `epsilon_cu2` and tensile steel 10‰ under the §8.1.2 *section-check* branch. The minimum eccentricity §8.1.1.5 is a floor applied once to first-order action eccentricity; no SP-R3 finite-element P–Δ moment is applied again.

A source-internal bug was identified and fixed at this stage: the SP-R.6 `SP5_6_1_5_4_DESIGN_SECTION_AT_FIRE` tag did not activate the same §8.1.2.1 steel 10‰ / concrete `epsilon_cu2` check as the `SP5_6_1_5_4_SECTION_CHECK` tag, despite sharing the §6.1.5.4 source design law. Both section-check variants now perform that check. The distinct full nonlinear §6.1.5.2 branch still MUST NOT use this verification-only 10‰ as an artificial hot `epsilon_ud` limit.

## 3. Independent global FE spectral benchmark

SP-R.7 checks the first coupled principal Euler load with a second, independent full-column Hermite beam FE generalized eigenproblem. The FE assembly builds physical K and geometric G and reports the first positive generalized critical load at 9 and 17 beam nodes. The exact reference `pi² eig_min(Dnom)/L²` is derived from the principal stiffness eigenvalues and is unaffected by higher-mode ordering. The numerical goal is <0.5% relative difference on both meshes, **not** a SP-prescribed tolerance or experimental validation.

A negative global second variation or an observed loss of source section strain feasibility is **model-only evidence**. First actual physical failure requires tracking the stable loading/thermal branch, actual material creep/shrinkage history, end actions, possible spalling and post-peak nonlinear effects; eigenvalues alone cannot replace this.

## 4. First observed model limit and optional exact-time refinement

`scan_coupled_first_model_limit` walks only explicitly stored, time-matched SP-R2 FVM snapshots. It records whether a model reaches the section-check deformation criterion, the first nominal Euler threshold, or an unresolved state. It reports a **last known within → first known model limit** interval only when no earlier sample is unknown. Sampling starts after t=0, so it cannot prove global first physical collapse.

`refine_first_coupled_model_limit_with_new_sp_heat` can then bisect a STRICT known model bracket. At *each* midpoint the program solves a **fresh SP2026 2D FVM heat problem** with the **same source boundary conditions and heat grid**, evaluates actual new temperatures, reassembles the coupled 3×3 mechanical model, and checks the new state. It does not interpolate old temperature snapshots. An unknown intermediate model state terminates the refined bracket rather than classifying Newton failure as collapse.

The interval is named `strict_refined_model_event_interval_min`, and **`actual_t_R_minutes=None` remains mandatory**.

## 5. Independent heat, creep, spalling and experiment acceptance

- **Thermal mesh/time:** `audit_sp2026_heat_mesh_and_time` carries out three independently solved source SP2026 FVM runs: coarse grid/coarse dt, fine grid/coarse dt, fine grid/fine dt. At identical physical points, including actual bar centers, it reports independent mesh/time sensitivity, energy residuals and source boundary. A user-given numerical tolerance does not validate the prescribed value of h/epsilon or coupled moisture transport. SP2026 Annex Ж pointwise validation and approved heat-transfer boundary data are still required.
- **Creep:** `audit_effective_creep_source` implements §8.1.6.5 Eq(8.64) separately for x and y from externally supplied `phi(infty,t0)`, `M0Eqp`, `M0Ed`, and source. Nonzero opposite-sign design/quasi-permanent moments or zero denominator fail closed. `phi_eff,x` and `phi_eff,y` enter separate nominal concrete bending coefficients; the mixed bending block is symmetrically combined. Neither Eq(8.64) nor the ambient §6.1.4.3 law proves hot **transient** creep or irreversible thermal strain history.
- **Spalling:** the original СП Annex Л method evidence, moisture/source status and protection-requirement flags are brought to the SP-R.7 release ledger; they are NOT overridden by a numerically converged stiffness matrix.
- **Experiments:** the source-cited Lie/Woolerton I3,T3,II10 values retained in `validation/sp_r4q_fire_column_reference_cases.json` are used **only for admissibility auditing**. The present catalog reports measured failure times 218,221,262 min from a secondary 2009 paper; this calculator has NOT reproduced those experiments. Actual `fy=444 MPa` is not silently replaced by SP5 S500; ASTM E119 furnace is not declared equivalent to СП standard fire; actual bar centres/cover, moisture, high-temperature laws and support stiffness still need primary-source validation. No fitted or fabricated error metric is output.

## 6. Explicit release gates and numerical test plan

Source & code:
- `rc_fire/mechanics/sp2026_coupled_rigidity.py`
- `rc_fire/mechanics/sp2026_coupled_first_limit.py`
- `rc_fire/verification/sp2026_r7_qualification.py`
- `rc_fire/mechanics/sp2026_section.py` (section-check tag correction)
- `rc_fire/integration/r067.py`, `r07_public.py`, `multicolumn_r05/simple_app.py`
- `tests/test_sp_r7_coupled_qualification.py`

Numerical evidence groups:
1. An isothermal symmetric rectangular source section reduces EXACTLY to the SP5 §8.1.6 closed-form scalar B for x and y.
2. Perturbing one physically populated concrete cell introduces the correct axial–bending and bending–bending cross-terms; D remains symmetric positive.
3. The two-axis inverse moment-amplification matrix agrees with direct mathematical inversion and principal eigenvalues.
4. Independent full-column beam FE 9/17-node first eigenvalue agrees with analytic first principal Euler mode at user-selected 0.5% numerical tolerance.
5. With actual SP2026 two-face heat, the model returns a real nonzero off-diagonal coupled D rather than a false scalar-axis certification.
6. The §8.1.2 **secant** 3×3 state and the Table9 βE 3×3 state are separately evaluated, not equated.
7. Model-only first observed transition, previously unknown time, and fresh-SP-heat midpoint bisection are tested.
8. Three independent thermal solves, creep Eq8.64 two axes and experimental catalog admissibility run with provenance.
9. Public API/Streamlit complete SP-R.7 opt-in and published release gates regress against accidental promotion of U(t) or t_R.

**Normative acceptance gates NOT YET CLOSED**:
```text
HOT_SP5_8_1_2_SOURCE_SECANT_ULTIMATE_HISTORY   UNQUALIFIED
HOT_8_1_6_COUPLED_NOMINAL_SCALING             NON_SOURCE_ENGINEERING_EXTENSION
SP2026_THERMAL_BOUNDARY_H_EPS_MOISTURE         COMPARISON_ONLY
SP2026_ANNEX_L_SPALLING_AND_CRACKING           NOT_VALIDATED
HOT_TRANSIENT_CREEP_AND_IRREVERSIBLE_STRAINS   NOT_VALIDATED
FIRST_GLOBAL_PHYSICAL_FAILURE_BRANCH          NOT_VALIDATED
PRIMARY_EXPERIMENTS_SOURCE_MATCHED             0 / 3
ACTUAL U(t), t_R AND R_PASS                    NOT_ESTABLISHED
```

Tests passing, even 100%, do not resolve absent constitutive or experimental inputs. **Do not merge PR #33 or stacked PRs #26–#32 without explicit user approval.** Use the conditional model outputs as research evidence and engineering diagnostic, not as regulatory fire-resistance certificates.
