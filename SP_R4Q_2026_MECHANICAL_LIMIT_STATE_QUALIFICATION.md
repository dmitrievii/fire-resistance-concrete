# SP-R.4Q — qualification of the mechanical fire ultimate limit state

**Final conclusion of the implemented qualification campaign:** the present
SP2026 whole-column FE mechanics passes selected independent numerical
benchmarks; the **mechanical fire ULS cannot yet be certified**. This is a
substantive engineering finding, not a CI failure. The report is fail-closed:
`U_member(t)`, `t_R` and `R>=Rrequired` remain null/NOT_ESTABLISHED.

## Governing source hierarchy

1. СП 2.02.05-2026 §§8.2.16–8.2.23, especially §8.2.18 (temperature-reduced design resistance and elastic modulus: concrete and reinforcement Table 9/10 coefficients).
2. СП 5.03.01-2020 §§6.1.5.2 (complete nonlinear concrete stress–strain), 6.1.5.4 (simplified parabolic-linear **section resistance** law), 6.2.2.13 (alternative reinforcing steel nonlinear bilinear curves), 8.1.2.1–8.1.2.4 (deformation compatibility, section force and moment equilibrium and current **secant** stiffness), 8.1.1.5 (minimum eccentricity) and 8.1.6 (compression member buckling / second order).
3. Experimental fire column validation from independent real tests, not tabular R assignment and not copying reference paper's model.

### Important stiffness distinction

The **secant** stiffness matrix in SP5 §8.1.2.3 is the constitutive
equilibrium stiffness described in the standard. A **tangent** (Jacobian)
matrix used by Newton's method to solve the very same nonlinear equilibrium
is mathematically allowed as a *numerical iteration mechanism*; its use
alone does not violate a secant formulation. The real outstanding issue is
**constitutive equivalence**, not whether Newton differentiates the residual.

The present implementation takes the SP5 §6.1.5.4 simplified parabolic
section diagram and derives its initial tangent
`E_parab,0(theta)=n * f_c(theta)/epsilon_c2`. Independently SP2026
§8.2.18 demands `E_c(theta)=beta_c(theta)*E_c0`. These are in general
**not equal** and should not be silently equated, interpolated into an
unreferenced stress law or relabelled as a fully normative member stiffness.
The complete nonlinear SP5 §6.1.5.2 material law and temperature-dependent
peak strain/creep path must be sourced and calibrated for the desired
fire constitutive branch, with no arbitrary choice of hot curve shape.

The current steel §6.2.2.13 horizontal upper branch is allowed as an
idealization, but a finite 10‰ tensile strain **section-check** criterion
cannot silently substitute for a full nonlinear §8.1.2.1 `epsilon_ud`
ductility/failure limit. Neither temperature extrapolation of steel above
800°C nor automatic zero strength for steel is permitted by the current
user concrete-only out-of-range policy.

## Independent numerical verification — executable and source separate

The module `rc_fire/member/sp2026_mechanical_qualification.py` implements:

| ID | Source / verification | Numerical gate |
|---|---|---|
| FE_EULER_BUCKLING | analytic exact Euler `Ncr=pi²*EI/(mu*L)²` at ideal pin-pin and fix-fix ends, x and y independently, with mesh refinement | abs error below 0.5% |
| FE_COUPLED_BIAXIAL_EULER | independent principal-stiffness eigenvalue benchmark with nonzero Dxy, pin-pin and full two-axis coupling | abs error below 0.5% for both first global bending modes |
| FE_PDELTA_DEFLECTION | exact solution of `EI w''''+N w''=q` for pinned ends under uniform q at 0.1/0.4/0.7 of Ncr | below 0.5% midspan error; no cross-axis leakage |
| SP_HOT_FIBRE_JACOBIAN | central finite differences of complete actual SP-R1 heated N–Mx–My resultant `F(e0,gx,gy)` vs analytical implemented J | global-scale Jacobian discrepancy below 0.1% away from nonsmooth material kinks |
| SP_HOT_CONDENSED_MEMBER_TANGENT | independent differences of actual hot member `M(kappa_x,kappa_y,Nfixed)`, re-solving axial equilibrium at every perturbation vs Schur 2×2 member tangent | below 0.1% discrepancy and near-symmetry |

These tests qualify the named numerical operations only. They do **not**
validate physical constitutive behavior, time-dependent creep or global
failure; passing all tests must NEVER set `normative_mechanical_uls_qualified`
to true.

At the actual public call, stage R4Q runs the independent analytic
benchmarks plus SP hot fibre/Schur tests at the exact saved SP-R2 time,
publishing a per-gate decision record in the API and Streamlit. If any
benchmark fails/throws, stage R4Q fails closed and leaves the normative
result unknown. It does not delay the regular first-order diagnostic
calculation when the full member model was not requested.

## Normative mechanical blockers — individually non-waivable

**B1.** Thermally modified nonlinear constitutive model: demonstrate
SP2026 Table 9/10 `k_c,k_s,beta_c,beta_s` and SP5 nonlinear stress–strain
consistency with source-proven temperature-specific plastic strain, peak
strain and modulus; distinguish full nonlinear from simplified section
check. No numeric claim may be based on a hybrid curve selected only to
pass a benchmark.

**B2.** The correct SP5 §8.1.2.1 limit states: `epsilon_cu,epsilon_ud`
for nonlinear member model or corresponding independently qualified
section verification `epsilon_cu2`, 10‰ for checking resistance.
The current branch mixes a simplified section law into whole-member
nonlinear computation. That is an exploratory model, **not** the final
normative global collapse criterion.

**B3.** Thermal free strain, signed concrete thermal shrinkage, transient
strain and steel/concrete creep/recovery histories under progressive fire:
the present integral of coefficients is an assumption, not a qualified
path-dependent constitutive model. Steel θ>800°C is blocked, while
concrete θ>800°C is assigned zero strength *only by the user's conservative
model convention*, not by a tabulated SP coefficient.

**B4.** The full physically consistent action and end-restraint contract:
source-proven eccentricity `e_min=max(h/30,20mm)` in relevant plane,
applied N, first/second order Mx/My distribution, initial sway/rotational
imperfections, connection stiffness and possible thermal axial restraint.
User-precombined fire actions are **not** combined a second time. The
current opt-in Streamlit pin–pin uniform-q/half-sine model is only one
special explicit case, not a whole building frame.

**B5.** Global first load-bearing limit: prove *first* loss of a stable
equilibrium path by displacement/arc-length continuation or another
independently justified method that resolves bifurcation, postpeak,
multiple roots and imperfections. Positive-definite sampled tangent is a
local stability check, while nonpositive tangent or a failed Newton
iteration is UNKNOWN, **not** proven collapse. Local strain-limit
exceedance at discrete Gauss points is not a globally demonstrated
structural limit state. Perform x/y coupling and mesh/step/continuation
convergence.

**B6.** Appropriate thermal physics and section deterioration: surface
heat transfer, moisture and steel perturbations, spalling by Annex Л
where applicable, and longitudinal heating at every FE node/Gauss point.
The SP-R2 8×/12×/16× mesh comparison for one column does not globally
qualify other geometric/exposure cases.

**B7.** Independent real RC-column fire experiments with matched geometry,
reinforcement centre/stirrup cover, measured fire curve, load, eccentricity,
end fixity, steel/concrete constitutive properties and observed failure.
Specify acceptance errors and holdout cases *before* calibrating.
Passing analytic **linear** Euler tests is not experimental fire validation.

### External reference test catalog — no false benchmark pass

`validation/sp_r4q_fire_column_reference_cases.json` transcribes **only**
the observed experimental test data for three RC columns, I3/T3/II10, as
reported in Kodur, Dwaikat and Raut, *Macroscopic FE model for tracing
the fire response of reinforced concrete structures*, Engineering
Structures **31** (2009), 2368–2379, Table 1, DOI
`10.1016/j.engstruct.2009.05.018`.

| Column | Geometry mm | Bars | L m | End supports | N kN | Experimental R min |
|---|---|---|---|---|---|---|
| I3 | 305×305 | 4×Ø25 | 3.8 | fixed–fixed | 800 | 218 |
| T3 | 305×305 | 4×Ø25 | 3.8 | pinned–pinned | 1022 | 221 |
| II10 | 407×407 | 4×Ø36 | 3.8 | fixed–fixed | 2418 | 262 |

These three cases are **NOT EXECUTED** as SP-R4Q validation. The published
steel actual f_y=444 MPa is not our S500 input catalog; the paper's f'_c
cannot be silently recast as a Belarus SP5 concrete class; ASTM E119 is
not identical to SP2026 standard fire without a documented boundary
comparison. Original specimen drawings, bar centres, concrete moisture,
actual end restraint, eccentricity, creep and thermal history must be
reconciled before calculating prediction error. Neither tuning to measured
R nor calling the published FEM's predicted values our model output is
allowed.

## Acceptance states and release

- **VERIFIED_NUMERICAL_KERNEL (scoped):** independent FE Euler/P–Δ
  and SP fibre/Schur algebra benchmarks PASS in the tested conditions.
- **BLOCKED_NORMATIVE_MECHANICAL_ULS:** one or more of B1–B7 unresolved.
  This is currently the correct result regardless of green CI.
- **FULL_NORMATIVE_MECHANICAL_ULS:** unavailable until a separate
  implementation implements B1–B7 and obtains matched independent
  acceptance evidence. No user checkbox, PR approval or CI status may
  override those physics requirements.
- The calculated `U_model` intervals and axial relaxed `N_upper` remain
  clearly labelled research diagnostics. Only after B1–B7 do any
  `U_member(t)`, `t_R` and `R>=Rrequired` become eligible to report.

Stacking: PR #26 (R1) → #27 (R2) → #28 (R3) → #29 (R4) → #30 (R4Q).
All remain unmerged, and PR #30 remains Draft until explicit review.
