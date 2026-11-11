# SP-R.6 — directly permitted SP5 section method + SP5 §8.1.6 nominal rigidity

**Draft.** SP 2.02.05-2026 §§8.2.16–8.2.23 have priority. Method is
non-tabular. SP 5.03.01-2020 provides the section-check and slender column
equations. No Eurocode law or TKP result is silently substituted for a source.

## Governing provisions, all explicitly matched

| Source | Implemented equation or criterion |
|---|---|
| SP5 §4.2.5.3 Table 4.6 | For special/accidental design, γc=1.20, γs=1.00 |
| SP5 §6.1.2.11 Eq (6.4–6.5) | fcd,20 = αcc ktc fck / γc; αcc=min[1,(40/fck)^(1/3)]; recommended ktc=1 |
| SP5 §6.2.2.12 Eq (6.28) | fyd,20=fyk/γs |
| SP2026 §8.2.18 Tables 9–10 | fcd(θ)=fcd,20 kc,fire(θ), fyd(θ)=fyd,20 ks(θ), Ecd(θ)=βc(θ)Ecm,20/1.2, Es(θ)=βs(θ)Es,20 |
| SP5 §6.1.5.4 Eqs (6.17–6.18) | Actual design parabolic–linear **SECTION resistance** curve, εc2/εcu2 from Table 6.1 and n for actual concrete class |
| SP5 §6.2.2.13 + §8.1.2.1 | Permitted steel design bilinear upper horizontal branch; section-check 10‰ tensile strain limit (not full nonlinear εud) |
| SP5 §8.1.1.5 | e0 >= max(h/30,20 mm) in the governing bending plane |
| SP5 §8.1.6.2 Eq (8.54–8.55) | ηa = 1/(1 − NEd/Ncrit), Ncrit=π²Bnom/l0² |
| SP5 §8.1.6.3 Eq (8.56–8.57) | Bnom=kc,nom Ecd Ic+Es Is; Ecd=Ecm/1.2; ks,nom=1 |
| SP5 §8.1.6.4 Eq (8.58–8.63) | kc,nom=k1a k2a/(1+φef), k1a=√(fck/20), k2a=min(0.20,nλa/170), n=NEd/(Ac fcd), λa=l0/i, i=√(Ic/Ac) |
| SP5 §8.1.6.5 Eq (8.64) | Effective φef = φ(∞,t0) * M0Eqp/M0Ed. This quantity is an input with independent project provenance; it is NOT silently assumed from the user's already combined fire load. A user-selected value zero is an explicit numerical scenario, not automatic permission from the standard. |
| SP5 §8.1.6.6 | l0=μl for identified restraint; first integrated UI case is explicitly pin–pin (μx=μy=1). |

The symbols `kc,nom` (a nominal rigidity factor, Eq8.58) and
`kc,fire(θ)` (SP2026 temperature-dependent concrete strength reduction)
are physically and numerically **different**. Code uses separate names.

## Two fire material scopes: source-literal vs engineered 2D extension

1. **ISOTHERMAL_LITERAL_UNIFORM_SECTION:** pure function
   `exact_sp5_nominal_axis` implements the listed formulas without any
   temperature spatial averaging. Independent exact analytical references
   validate Ecd Ic, Es Is, n, k1/k2/kc, l0, Ncrit and η. It is the first
   benchmark and cannot be confused with the real fire model.
2. **ISOTHERMAL_NUMERIC_QUADRATURE:** for synthetic uniform temperature
   the fibre sum `Σ Ecd(T) A[(y−yc)²+Δy²/12]` exactly reproduces
   rectangular `Ecd Ic`, and actual bars give Es Is. This is tested
   against the standalone closed form for both independent bending axes.
3. **NONUNIFORM_NUMERICAL_EXTENSION_NOT_PRESCRIBED:** for the actual
   SP-R2 2D heat field, concrete/steel have varying k(θ), β(θ).
   The model evaluates `Σ Ecd(θ) [ΔIc]` and
   `Σ Es(θ) As (y−yc)²` and defines an area-average
   `fcd,eq=Σ fcd(θ) Ac,cell / Ac` for the scalar `n`.
   **The SP5 Eq8.56/8.61 text does not explicitly prescribe this
   nonuniform homogenisation**. It is labelled as an engineering research
   extension, never a normative fire R qualification.
4. **CROSS-AXIS COUPLING CHECK:** if the stiffness-weighted axial centroid
   is not coincident with the concrete centroid or a nonzero bending EIxy
   is observed beyond strictly numerical tolerance, the two independent
   scalar ηa factors are **BLOCKED**. The source method cannot silently
   ignore a two-axis bending matrix for asymmetrically heated sections.
   A full coupled eigenstiffness / general member derivation is then
   necessary, independently of whether SP-R3 FE returns equilibrium.
5. Concrete above 800°C retains user-selected **zero strength and
   modulus** assumption, distinct from SP Table9 strength at exactly
   800°C. Steel above 800°C is rejected unless a source-supported
   temperature range or user-approved, independently labelled material
   policy is provided.

## Explicit section input and physically consistent load path

`prepare_sp2026_design_section` samples the real source-matched SP
thermal field (concrete cells, displaced concrete where bars sit, bar
centre temperatures and eight real concrete boundary points). It
overrides only the design stress laws of a separate `SPPreparedSection`,
not the legacy SP-R3 or SP-R5 constitutive branches.

`assess_sp5_nominal_column_at_fire` currently requires a
**confirmed pin–pin, constant transverse q, actual two-axis initial bow,
uniform full-length fire** schematic with exactly 3 z stations
[0,L/2,L] and zero other nodal actions. At each actual sampled fire
time, it obtains *source-derived nominal* ηx,ηy. Midspan first-order
moments are formed once as M0x=qx L²/8+N ex and
M0y=qy L²/8+N ey (ex,ey the entered bow amplitudes), and the
SP5 §8.1.1.5 minimum eccentricity is enforced by taking the
corresponding larger magnitude **rather than adding another fictitious
minimum imperfection**. Only then do M2x=ηx M0x and M2y=ηy M0y enter
the actual coupled three-DOF section equilibrium.

This is an *explicit conservative model closure* for the declared
scheme, not permission to infer unknown actual frame end moments,
restraint stiffness, eccentricity history or fire actions. In
particular, it must NOT be combined with SP-R3's pre-amplified
geometric nonlinear P–Δ displacement calculation, because that would
double-count second-order action effects. The existing SP-R3 FE model
is separately available for critical comparison only.

At N>=Ncrit, ηa is *undefined*: output
`N_AT_OR_ABOVE_NOMINAL_NCR_UNRESOLVED_MEMBER_CAPACITY`,
not an arbitrarily huge η or an independently proven real column
failure. If no valid equilibrium is found, the result is UNKNOWN,
not structural collapse.

## Explicit creep and numerical discretisation qualification tools

The source-literal helper
`effective_creep_coefficient_sp5(phi_infty,M0Eqp_kNm,M0Ed_kNm)`
evaluates Eq8.64 with independent finite-domain checks. It rejects a
zero denominator and an opposite-sign quasi-permanent moment rather
than silently assigning `phi_eff=0`. The fire input may also declare
`phi_eff` directly with an audit trail. Neither is a replacement for
project-specific identification of long-term loads and temperature-
dependent concrete creep.

The research tool `verify_sp5_nominal_grid_convergence` evaluates
exactly the same SP-R2 source thermal field using 8×8, 12×12 and
16×16 *mechanical* fibre quadratures. It compares axis-specific nominal
`Ncrit` values and produces pairwise relative changes, using a
user-designated numerical tolerance. Passing this study demonstrates
only numerical stability of section integration **for that specific
fixed temperature field**, not convergence of the SP-R2 heat mesh or
time, validation of exposure coefficients, physical material strength,
or ultimate fire endurance. Public API/UI exposes an independent
optional study with all three grid results and a separate visible
`normative_member_qualification=false` status.

SP5 Eq8.56 applies scalar flexural stiffness about a prescribed axis.
A 2D heated section can have significant `EIxy` and/or an
E-weighted axial stiffness centre shifted from the concrete centroid.
Before permitting scalar `eta_x` and `eta_y`, this implementation
computes both couplings and rejects states beyond a **strict numerical
decoupling** tolerance 10⁻⁶. That threshold is an algorithmic
preflight, **not** a SP-prescribed permitted eccentricity or a proof
that the remaining nonuniform EI homogenization is normative.

## Load-factor search on the SP5 nominal route itself

The optional
`scan_sp5_nominal_member_load_path(column,snapshot,member_spec,...)`
**does not borrow** a capacity or geometric stiffness from SP-R3/R4
hot FE. It scales the complete confirmed first-order action pattern
`F(λ)=λ{N,qx,qy,F_nodes}` while retaining the **same physical initial
imperfection**. Every independent trial re-evaluates:

1. The effective hot strength `fcd,eq(θ)` and
   `n(λ)=N(λ)/(Ac fcd,eq)`.
2. `k2a(λ)=min(0.20,n(λ) λa /170)`,
   `kc,nom(λ)=k1a k2a(λ)/(1+φef)`.
3. Hot `Bnom(λ)`, `Ncrit(λ)`, and therefore
   `ηa(λ)=1/(1−N(λ)/Ncrit(λ))`.
4. Source-compatible first-order moment and minimum eccentricity,
   their second-order magnification, and actual 3×3 SP5
   `N–Mx–My` design section equilibrium/limit strains.

Neither `ηa` nor `Ncrit` at λ=1 may be held fixed while scaling
N for a load-capacity calculation. The first known WITHIN and
known EXCEEDED sample are refined by explicit recalculation; a
singular `η`, lack of Newton convergence, cross-axis bending
coupling or invalid hot material stays **UNKNOWN** and invalidates
any alleged complete failure bracket.

Outputs:
`observed_conditional_SP5_section_factor_bracket`,
`model_only_utilisation_interval` where a valid bracket is found,
and the actual `at_reference_design_load_factor` state. These are
**sampled conditional model-only indices**, never the normative
load-bearing `U(t)`, and they do not determine first fire
`t_R` until physical/thermal source applicability and longitudinal
member stability are fully qualified. Public UI has a separate
opt-in SP-R6 capacity-scan switch.

## Numerical evidence and integration

- `tests/test_sp_r6_nominal_member.py`:
  Table4.6 γ, Eq6.4/6.5/6.28 strengths, exact SP5 equations
  8.54–8.64 (including k2 cap, φ and Ncrit),
  explicit invalid N>=Ncrit, numerical fibre/closed-form equality
  for isothermal cases, real SP2D hot section design vs fck-only
  stresses, 2D source nonuniformity and axis coupling, actual
  whole-public-workflow and saved-fire-time series.
- `r07_public.fire_assessment` includes explicit SP-R6
  opt-in `member_spec.nominal_sp5_requested`. `phi_eff` and its
  provenance must both exist; optional history uses *only exact
  stored SP-R2 temperature times*, no interpolation or synthetic
  temperatures. The default no-SP-R6 scenario remains unchanged.
- Streamlit provides a separate named SP-R6 calculation with
  editable φef, a time-series opt-in, material design values and
  separated axis Ncrit/ηa. R0.7 default dashboard still does
  **not** display a fabricated fire R.

## Remaining gates to certified physical t_R

1. Demonstrate or normatively qualify the general 2D nonuniform
   temperature stiffness method, especially variable fcd, skew EI,
   thermal neutral axis and cross-axis eccentricity. Eq8.56 is
   uniform-material; users must not receive an unlabeled extension
   as a literal code requirement.
2. Qualify φef=φ(∞,t0) M0Eqp/M0Ed under the actual special fire
   load history and temperature; the current UI's explicit 0
   is a *calculation assumption*, not normative evidence.
3. Prove actual first physical section-limit and global member failure
   rather than inferring them from a sampled strain at one section,
   nominal Ncr crossing, spectral tangent sign, solver nonconvergence
   or coarse fire time interval. Establish load/time/spatial
   convergence on a real heated column.
4. Validate SP2026 §8.2.23 thermal h/ε, moisture, steel thermal effects
   and Annex Л spalling as appropriate, against SP Annex Ж and
   independent fire column experiments (with real materials/restraints).
5. Qualify all actual prescribed/support/imperfection action diagrams,
   including section-specific N, Mx, My along the length. The
   pin–pin uniform q benchmark must not be silently applied to
   general frames, fixed ends or variable thermal exposure.

### Release discipline

This new source-based mechanical route is **calculating genuine
design-section and member nominal quantities** rather than a
tabular R90 rating. However, the asserted `U_model` and η values
are *conditional on the explicitly declared methods and assumptions*,
not an experimentally and normatively qualified structural-fire
utilisation `U(t)`.

`U_member_t=None`, `t_R=None`, `R_t_minutes=None`,
`regulatory_result=NOT_ESTABLISHED`.

Stacked PRs: #26 SP-R1 → #27 SP-R2 → #28 SP-R3 → #29 SP-R4 →
#30 SP-R4Q → #31 SP-R5 → **#32 SP-R6**.
All are Draft/unmerged unless the user expressly approves.
