# R0.6.9D1 — Belarus TKP EN 1992-1-2:2009 fire constitutive law

## Primary user-supplied sources

1. EN 1992-1-2:2004 English, with July 2008 corrigendum.
2. ТКП EN 1992-1-2-2009 (02250), Belarusian translation, identified as IDT with EN 1992-1-2:2004. The **Belarus National Annex IS INCLUDED IN THE END OF THE DOC FILE**. Do not ask for a separate copy.

Copyrighted full text and scanned pages are not redistributed in this repository.

## Explicit Belarus national choices (Table НП.1)

| Clause | Belarusian selection |
| --- | --- |
| 2.3(2)P | γM,fi = 1.0 for fire mechanical and thermal material properties |
| 3.2.3(5) | Class N Table 3.2a reinforcing steel; Class X only with experimental validation |
| 3.3.3(1) | Lower-bound normal-weight-concrete thermal conductivity |
| 4.1(1)P | Advanced models where other methods do not adequately reflect actual fire behavior |
| 4.5.1(2) | Spalling moisture threshold k = 3% by mass; not a universal no-spalling guarantee |

## Material laws implemented in independent source module

- §3.2.2.1, Table 3.1 and Figure 3.1: strength reduction, peak strain and ultimate strain of siliceous/calcareous normal-weight concrete, monotone rising stress curve, explicitly permitted linear descending branch. Ignore tensile resistance by default (§3.2.2.2).
- §3.2.3, Table 3.2a and Figure 3.3: Class N reinforcing steel: actual reduction of yield stress, proportional limit, elastic modulus, nonlinear rounded transition, plateau and ductility-dependent descending branch. Hot-rolled versus cold-worked is mandatory input, as is bar ductility class A/B/C. S500 or weldable-bar designation does not prove production route.
- §3.3.1 and §3.4: thermal free elongation of concrete/rebar. Thermo-mechanical coupling is NOT yet installed.
- Source fire material partial factor = 1.0.

### Table 3.1: a subtle constitutive domain gap

At 1200 °C Table 3.1 gives k_c=0, but the peak and ultimate concrete strains are recorded as **dashes**. At intermediate 1100<θ<1200 °C, k_c can be interpolated, but the absent 1200 strain endpoints cannot be linearly interpolated as source data. Consequently this module implements:
- Full concrete stress/strain to 1100 °C.
- Strength-reduction factor, **without** a complete stress/strain law, for 1100<θ<1200 °C (typed error for stress).
- Source-tabulated zero strength at exactly 1200 °C.
- No extrapolation above 1200 °C.

At K18 t=90 some boundary values exceed 1100 °C. No source-free assumption is inserted to conceal this.

## Not yet a fire resistance limit R(t)

This stage does not modify the SP 2.02.05-2026 production solver or combine Annex K heating with the independently defined EN thermal model. This avoids silently mixing methods or partial factors.

The follow-up integrated advanced model (§4.3) requires:
1. Thermal response based on Belarus lower thermal conductivity, consistent fire action and numerical convergence; benchmark against Annex K field.
2. Full fibre N–Mx–My material stress/strain with thermal eigenstrains, geometrical nonlinearity and defined handling of high-temperature concrete with incomplete strain parameters.
3. Actual member supports, imperfections and an action pattern; a single entered section moment cannot define distributed loads uniquely.
4. Time refinement and physical failure qualification independent of Newton numerical convergence.
5. Comparison with relevant fire test evidence, as required by TKP §4.3.4. Unit tests alone do not certify a fire resistance model.

The user already provides the fire-design N/M values; do not recombine these into another load combination.

## Acceptance

Targeted and full Python unittest discovery and both existing GitHub CI workflows must pass before merge. Do not merge without the user's explicit approval.
