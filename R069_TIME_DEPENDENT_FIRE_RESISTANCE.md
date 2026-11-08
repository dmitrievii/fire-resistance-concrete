# R0.6.9 — Belarus RC fire-resistance history and scoped Table 3 R classes

## Purpose

Compute the entire **time-resolved evidence** available from the existing
Normative Annex K heat profile and R0.6.3 heated-section solver, and separate it
from **qualified fire resistance**. A solver-reported first failure, absence of
convergence, or the 800 °C table cutoff MUST NOT be mislabeled as a normative R time.

Inputs N, Mx and My are already fire-design actions by the R0.6.8.3 contract.

## Route A: SP 2.02.05-2026 §8.2.11 / Table 3

Exact table grid: rows η=0.3, 0.5, 0.7; columns R30, R60, R90, R120,
R180; each cell has one or two allowed (b,c) pairs, **not** an independent b
threshold separated from c. For intermediate η, use the next greater tabular
row conservatively, without inventing interpolated values.

- η = max(N_Sd,fi) / N_Rd, where the denominator is **independently established
  normal-temperature axial cross-section resistance**; do not use the legacy
  R0.5.6 utilization and do not invent N_Rd from 50 kN or a nominal table.
- Width is min(b,h) for a conservative rectangular comparison; c is the
  **minimum measured center distance** of all longitudinal bars to any face.
- Existing preflight verifies effective length <=3 m, reinforcement <=4%
  and signed eccentricities <=0.15h/0.15b. Inputs are already fire actions.
- The current code flags two simultaneous bending moment components for
  engineering confirmation: an assessment of each separate signed
  eccentricity does not independently verify full biaxial applicability.
- Required verification of actual support model, exposure and correct ambient
  N_Rd is displayed separately. A conditional table row is not a PASS.

For K1 (600 x 600 mm, c=40 mm), conditional **η<=0.3** width/c tables have
R120 geometry but not R180 (c=45 mm). This is a *candidate* given a verified
η and all application conditions. R120 from Table 3 is a discrete normative
classification, **not a computed exact physical failure at t=120 min**.

## Route B: Time-dependent Annex K and R0.6.3

Given the user-selected fire duration and time step (max 61 stations, section grid 12–48), build
a temporary copy of the *same column* for t=0..fire duration. Evaluate
Annex K temperature at t and pass the unmodified original N/M fire actions to
the heated N–Mx–My section solver at that t.

At each station preserve:
- time, maximum concrete and bar temperatures;
- Annex K critical isotherm area, with its scope status;
- complete section equilibrium and strain-limit status for **every**
  authored section, including reasons for unresolved numerical solutions;
- optional R0.6.7 full-member diagnostic, when the user explicitly supplied
  longitudinal uniformity, supports and a valid member loading model.

Status distinction:
- SAMPLED_SECTION_EQUILIBRIUM_DIAGNOSTIC;
- SAMPLED_STRAIN_LIMIT_EXCEEDED_DIAGNOSTIC;
- UNRESOLVED_NUMERICAL_EVIDENCE;
- OUTSIDE_MATERIAL_OR_THERMAL_SCOPE;
- INCOMPLETE_INPUT.

The optional R0.6.7 FE/member ULS history has a **separate** bracket, based on sampled Gauss/node strain-limit states. A bracket in the member is independent from section strain failure and never a certified R. An explicitly selected high-temperature zero-strength *research* mode can also bracket sampled diagnostic exceedances, but reports `RESEARCH_LIMIT_BRACKETED` and never upgrades normative status.\n\nA diagnostic strain exceedance can only be *bracketed* if the immediately
preceding temporal sample was a solved admissible state, and no unresolved/
out-of-scope state lies within this bracket. Optional bisection remains
**diagnostic**. Do not interpolate across gaps. A non-converged Newton
iteration is **not** proof of collapse.

**Above 800°C:** SP 2.02.05-2026 Tables 9/10 do not provide coefficients,
so a time station crossing the material-table boundary is an **evidence
censoring point, NOT fire failure**. Research-mode assumed zero strength
over 800°C can be evaluated separately but not merged into normative evidence.

## Scope still open for a qualified exact t_R

1. Independent constitutive verification beyond 800°C, or a fully qualified
   replacement calculation route such as the explicitly limited critical
   isotherm/Eurocode 2 method; cannot extrapolate SP 9/10.
2. Full section ULS and member second-order validation for the applicable
   supports, nonuniform heating and true bending action distributions.
3. Annex L spalling and treatment of actual damage/time progression; a
   diagnostic F is not a complete physical spalling history.
4. Continuous time-adaptive location of first physical limit state with
   verification of numerical convergence, accuracy and stability.
5. Full Table 3 application evidence including normal-temperature N_Rd.

Until these are done:
`computed_exact_R_min = null`,
`normative_class_approved = null`,
`normative_claim = false`,
`fire_resistance_status = not_demonstrated`.

## Presentation\n\nThe Streamlit column page contains an opt-in time sweep with grid and time-step controls, a history table, temperature plot, explicit research-only mode and JSON download. The project overview summarizes history status per column. Cached histories are invalidated when ANY column input changes. Word reports include sampled histories without a false positive R verdict; no scan runs implicitly when the user edits a field.\n\n## Acceptance

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_r069_time_resistance -v
```
