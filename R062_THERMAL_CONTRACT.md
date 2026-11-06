# R0.6.2 — SP 2.02.05-2026 Annex K analytical thermal calculation

**Released component:** `rc_fire.thermal`, invoked from `multicolumn_r05/project_calculator.py`.  This release is a numerical implementation of selected Annex K thermal calculation methods.  **It does not certify R90, R(t), concrete mechanical resistance, stability, or explosive-spalling safety.**  R0.6.0 compliance remains fail-closed.

## Authoritative sources and precise scope

- **СП 2.02.05-2026**, Annex K, pp. 145–149 (PDF pp. 149–153), K.1–K.12, K.20–K.28, tables K.1 and K.2; §8.2.21 critical temperatures. Provided by the user.
- **СП 5.03.01-2020**, concrete classifications and mechanical material properties in the **R0.6.1** catalog. The heat-transfer module reads the selected aggregate family from that catalog if available; it does not conflate the concrete elastic modulus with thermal diffusivity.
- Mathcad K18: independent historical regression, *not* overriding current normative equations.

Only a standard-fire thermal-history approximation as prescribed by Annex K is calculated. No alternative exposure curve, convection/radiation boundary condition, transient moisture transport, or user-built material PDE is claimed.

## Implemented and unit-checked normative procedures

| Item | Implemented | Contract detail |
|---|---|---|
| Annex K.1, table K.1 | Yes | Concrete thermal families siliceous, calcareous, expanded clay; λ=A+Bθ, C=D+Eθ; default tabulated a_red or K.1 with θ=450 °C simplification |
| Annex K.2, table K.2 | Yes | φ1 and φ2 by actual dry density, exact tabulated nodes certified; intermediate density interpolation flagged as engineering interpolation, no extrapolation |
| K.4, K.5, K.11, K.12 | Yes | Equivalent distance, bar-diameter correction, r limited to 1, time min→hours |
| K.6–K.10 | Yes | One/two parallel/two adjacent/three/four exposed sides in any rectangular section |
| K.20–K.28 | Yes for **square, 4 sides** | Criterion 400/460/500/600 °C (with actual scope), heated-layer distances and remaining area by K.27 |
| Individual bars | Yes | Coordinates and diameters from the common project state; temperatures independently for every bar, without historic hard-coded 597/355 °C |
| Graph/UI/DOCX | Yes | Project-specific inputs; 2D field, bars, isotherm where resolved, limits and normative source |
| K.13 solid circular | No | Separate radial geometry API needed before enabling circular columns |
| K.14–K.19 / K.3 ring and centrifuged | No | Specialized K.3 coefficient table and wall/void geometry are *not* substituted with rectangular formulas |
| Annex Ж temperature matrices | No automatic route | Independent reference comparisons to be included with subsequent numerical qualification |
| Certified mechanical coupling | No | R0.6.3+ must integrate the actual temperature field, material curves, and sectional/member resistance |

## Critical implementation choices

**Time and diffusivity.** K.12 uses τ in hours: `l_m=sqrt(12*a_red_m2_h*t_minutes/60)`.

**Bar surface and centroid.** For K.5 the input `y_i` is interpreted as clear distance from heated surface to the bar *outer perimeter*; for a bar with center distance `y_center` and diameter `d`, effective K.5 distance is `y_center − d/2 + φ1 sqrt(a_red) + φ2 d`. This reproduces K18 when `d=25 mm`, `c_axis=50 mm`, `ρ=2400 kg/m³`. The PDF text does not explicitly say `y_i` is to bar centre, so this convention is declared in provenance and should be independently adjudicated during numerical qualification.

**Single-face limit.** K.6 is expressly stated for `x_i <= 0.7h`. This restriction is tracked per mesh point and per bar. Temperatures outside this limit are shown for visual continuity but flagged as outside a qualified complete-field interpretation; no unqualified R rating is inferred.

**Literal equations and unphysical results.** K.7/K.9/K.10 are evaluated without invented temperature clipping. If the approximation yields a temperature outside 20–1220 °C, the case is flagged rather than silently corrected.

**K.27 square area.** The exact Annex K correction ψ is used, even though it need not equal an integrated 2D mesh isotherm area. A numerical integration is not substituted for K.27 and rectangles other than squares have no claimed K.27 area.

**Critical temperature.** For heavy concrete classes through C50/60, §8.2.21 assigns 500 °C (siliceous) / 600 °C (calcareous); C55/67–C60/75 assigns 460 °C, C70/85–C80/95 assigns 400 °C. Unsupported classes/type return `None`, not a fabricated 500 °C.

**K.2 density.** The table's upper tabulated density is 2400 kg/m³. Input 2500 kg/m³ is not silently extrapolated. A user with verified 2500 kg/m³ can select a further method when its normative basis is provided or reviewed.

**Diagnostic bridge.** For verified four-sided input and without scope warnings, `to_engine_input` passes the resulting a_red, φ1, φ2 and critical θ to the older **diagnostic-only** fibre solver. That solver's mechanics is not changed or qualified. For a user-selected 1-, 2-, or 3-side fire, the old four-sided mechanical results are suppressed rather than misleadingly reused.

## Mandatory comparative benchmarks

At 600×600 mm, ρ0=2400 kg/m³, siliceous heavy concrete, R90, four faces, with 25-mm bars and axis depth 50 mm:

- Corner bar: **596.4654931806213 °C** (K18 raw result).
- Middle bar (x=250, y=50 mm): **354.99051555300593 °C**.

K.24: `r3 = 1−sqrt((1220w−1220+θcr)/(1200w))` (for `w=1, θcr=500`: `r3 ≈ 0.3545028`). Historic code used **1220w** in the denominator instead of **1200w**. That replay difference is intentional and tested, not masked by matching rounded K18 results.

## Missing normative dependencies / not a release blocker for thermal only

- СН 2.01.03-2019, §4.3: necessary for deriving fire *design-action combinations*, not for Annex K temperature at a specified standard-fire duration. The request for this source remains outstanding.
- The 2026 standard and 2020 RC standard are kept out of the public GitHub tree for copyright/licensing; source references, implementation and benchmark tests are public.

## Required R0.6.3 qualification

1. Compare Annex K predictions against multiple independent Annex Ж reference matrices at R30/R60/R90/R120 and grid points on their stated geometry, not just K18.
2. Resolve K.5 bar-distance interpretation with the standard and admissible test example(s).
3. Integrate theta_i into k_s(theta), beta_s(theta), k_c(theta), beta_c(theta) and ultimate strain limits. Do not extrapolate the table beyond its stated range.
4. Connect field and actual residual geometry to a normative N–Mx–My section-ULS solver; qualify R(t) and member stability before issuing R90.
5. Add dedicated K.13 and K.14–K.19 geometry backends to support circular/hollow columns.