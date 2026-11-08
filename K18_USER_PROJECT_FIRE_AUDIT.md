# R0.6.9C: K18 source-project audit and blocker adjudication

## Sources and scope

This source audit was executed against the numerical inputs extracted from the user-supplied K18_project.json and inspected the 1-page Streamlit PDF. Normative references were cross-checked with the user-provided licensed copies of СП 2.02.05-2026 (paragraphs 8.2.16–8.2.23, Tables 9–12, Annexes K/L) and СП 5.03.01-2020 (Table 6.3). The licensed PDFs and the original user's JSON are not published in this repository. Tests reconstruct the minimal case.

The screenshot only shows the top input-editor page, not a diagnostic trace; error causes were established by source review and reproducible tests.

## K1 inputs

600 × 600 mm, L = 3 m, concrete C30/37, consistency V3_V4, siliceous heavy concrete dry density 2200 kg/m³, S500, 8 Ø20 at x,y = (40/300/560 mm positions in an eight-bar perimeter layout), cover 20 mm to Ø10 stirrup, 90 min, four-face exposure. Entered section at z = 1.5 m: N = 50 kN, Mx = 2 kNm, My = 0. These are **already fire-design actions**.

Annex L: user explicitly confirms natural sand, 40% coarse aggregate, max aggregate size 30 mm, RH 44%, cement 500 kg/m³ and W/C = 0.45.

## Reproduced computation

| Quantity | Value | Qualification |
|---|---:|---|
| Concrete ambient Ecm | 41 GPa | SP 5.03.01-2020, Table 6.3, specified consistency and aggregate |
| Water content by Annex L.5 | about 0.02146 kg/kg | Formula result interpreted as percent then divided by 100; normative unit ambiguity explicitly tracked |
| Brittle spalling criterion F | **3.26208** | Maximum over evaluation temperatures 200–300 °C; below F=4, **conditional** on the L.5 unit convention |
| Dry-density K.2 coefficients at 2200 kg/m³ | phi1=0.62; phi2=0.5 | Unprescribed numerical interpolation between published density nodes 2000 and 2400 kg/m³; sensitivity reported independently |
| Heated 600 × 600 mm K.27 analytical remaining area | about 0.2000 m² | About 44.4% below original area; geometry only |
| Exposed corner concrete temperature at 90 min | about 1132 °C | Exceeds 800 °C end of published strength tables |
| Corner reinforcement temperature Ø20 at (40,40) | about 720 °C | **Within** published reinforcing-steel temperature range |
| Middle-of-face bar temperature Ø20 at (300,40) | about 445 °C | Within steel table range |
| Strict full-fibre heated section analysis | Blocked | Actual exposed-boundary concrete temperature exceeds 800 °C; not an observed failure |
| Optional zero-strength-hot-zone model | Numerical research only; physical state UNKNOWN | No invented post-800 material strength, but conservative numerical zero approximation is not a published constitutive law |
| Critical isotherm §8.2.21 admission | Blocked for mechanical capacity | Perimeter8 contains third bar-centre layer on the neutral-axis sides, while implemented conservative method requires two extreme-face layers |
| Spatial nonlinear P–Δ member | Optional, not configured | No continuous transverse loads/supports or confirmed uniform longitudinal heating in user JSON; does not block independent section check |
| Normative R(t) | **Not established** | No positive R90 verdict |

The independently checked F value is **3.26208**, not the initial hand estimate of approximately 3.45. At 200 °C the code interpolates the siliceous-concrete thermal-expansion coefficient between 100 and 300 °C, rather than using the 100 °C endpoint. Regression tests assert the corrected value.

## Actual code corrections

1. Project signature now includes the complete Annex L physical mix data, legacy physical mixture and bar layout details. Changing relative humidity or W/C now invalidates results and prevents a stale saved member/section state.
2. At t=90, strict section mechanics remains fail-closed because the source tables terminate at 800 °C for concrete. An **explicitly opt-in** high-temperature zero-strength numerical model is now separately available. Its raw equilibrium classification may be within/exceeded/unknown under the assumed model, but its physically qualified design-state classification is always UNKNOWN; it cannot create positive R90 evidence.
3. Boundary temperature is separately evaluated at the actual exposed corners rather than presenting cell-centre temperatures as a boundary maximum. All actual bar temperatures are reported.
4. A front-of-column one-click audit panel enumerates missing inputs, normative gaps and optional calculations separately, with JSON export and K.2 density-neighbour numerical sensitivity.
5. K18 regression tests reproduce the source geometry, actual mix, standard-fire input, loaded section and no-conclusion physical admissibility.

## Remaining restrictions

- 800 °C table limit for real full-section material law.
- No normative approval of the K.2 density interpolation at 2200 kg/m³ established in the published Annex K.2 text.
- Annex L.5 presents mass moisture Wc as kg/kg although direct numerical substitution gives percent-sized values; interpretation must be acknowledged/independently verified.
- §8.2.21 does not automatically qualify a perimeter-eight-bar arrangement, even when the K.27 analytical area is evaluated.
- Input N, Mx and My at a single station cannot uniquely determine a continuous member-end/support/transverse load path. No fictitious actions/supports are generated.
- Heated whole-member global ULS and first-loss-time R(t) require a separate fully qualified method. This stage cannot be described as calculated R90.

## Acceptance

Run the project tests and both GitHub Actions workflows. All new results remain normative_claim=false and R_t_minutes=None. Never merge before checks are green and the user explicitly requests it.
