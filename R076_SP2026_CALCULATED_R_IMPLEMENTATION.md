# R0.7.6B — Only SP 2.02.05-2026 calculated R(t): authoritative design target

**User's definitive method selection, 10 November 2026:** no tabular fire ratings. The only requested production method is the **calculation of actual first load-bearing failure time t_R under SP 2.02.05-2026 §§8.2.16–8.2.23**, with SP 5.03.01-2020 as the normal-temperature reinforced-concrete mechanics source. The TKP EN 1992-1-2 branch may remain as an independently identified research comparator / explicit alternative under §8.1.11, but **cannot silently provide SP material coefficients or a normative SP rating**. Table 3, the §8.2.21 500°C critical-isotherm simplified resistance approach, and other look-up rating methods are **not implementation acceptance paths**.

This document supersedes any recommendation in the earlier R0.7.6 general audit to implement SP Table 3 first. That suggestion was rejected by the user. Original requirements still apply: arbitrary physically valid rectangular section and bar arrangement, all exposed sides, actual N/Mx/My and all relevant locations, multiple columns, real R(t) versus Rrequired, a clean Streamlit UI, and a traceable Belarus report.

## 1. Normative clause × required computation × status

| Source | Actual method requirement | Existing code | Missing for a defensible SP R(t) |
|---|---|---|---|
| SP §8.2.16 | Determine time since standard-fire onset until actual load-bearing capacity is inadequate for applied load; compute the cross-section temperature history followed by heated structural resistance; refer to SP 5.03.01 on failure | TKP 2D FVM heating, heated fibre N–Mx–My equilibrium, stress-envelope LP and sampled times; public R_t=None | **SP-consistent thermal/mechanical source**, full structural ultimate-limit criterion, member failure-time search and proof of physical (not solver) loss |
| SP §8.2.17 | Account for fire load magnitude and applicable SN 2.01.03 §4.3 | User gives already fire-design N/Mx/My; the code passes them literally | Complete load *distribution and support scenario*; source provenance for load route. Do **not** recombine an already supplied fire-design action vector |
| SP §8.2.18, Table 9 | Heated normative concrete resistance R_b(theta)=R_b,n k_c(theta) and E_b(theta)=E_b,0 beta_c(theta), selected aggregate/type | Existing SP material data/catalog and TKP temperature-dependent strengths are separate | Implement a **strict SP Table 9 source-specific nonlinear material adapter**, source ranges, interpolation policy and correct ambient resistance; no unlabelled TKP 3.1 coefficients |
| SP §8.2.18, Table 10 | Heated S240–S500 steel R_s(theta)=R_s,n k_s(theta), modulus E_s(theta)=E_s,0 beta_s(theta), correct steel type | TKP steel curves implemented, SP tables exist in earlier branches | **Explicit SP Table 10** in the actual fibre section, with steel grade/type and temperature dependent tangent; never use TKP k_sy=0.78 at 500°C as SP k_s=0.60 |
| SP §8.2.19, Tables 11–12 and equation (6) | Concrete thermal expansion and irreversible thermal shrinkage; steel thermal deformation | TKP eigenstrain embedded in source-fibre model | Replace with **SP alpha_bt / alpha_cs** and **SP alpha_st(theta)**, integrate incremental eigenstrains consistently across temperature histories; respect units, sign and path |
| SP §8.2.20 + SP 5.03.01 | Acceptable parabolic-linear concrete compression diagrams and reinforcing-steel sigma–epsilon diagrams, with heated parameters | Some SP normal-temperature reference and TKP constitutive curves | Make explicitly **SP-selected full stress–strain and tangent curves** for all fibres at temperature; source-valid strain bounds and mechanical limit states; test against hand calculations |
| SP §8.2.21 | Simplified critical-temperature isotherm only in stated simple symmetry/reinforcement/one-plane scope | Earlier SP isotherm and visualization exist | **Not selected.** Do not determine capacity from displayed 500°C contour; continue full-temperature fibre method |
| SP §8.2.22 | In indeterminate flexural members, account for thermal/mechanical force redistribution and check plastic hinge sections | Optional P–Delta research solver exists | Compatible **whole-member two-plane second-order equilibrium**, restraint reactions, thermal curvature/extension, distributed loads, member imperfections, hinge/stability/strength criterion |
| SP §8.2.23 | Transient heat conduction with nonlinear boundary conditions, coupled thermophysical properties, and heat/moisture transfer; FD or FEM allowed | TKP transient FVM 2D heat field, gas curve, faces, temperatures and energy balance | Verify heat coefficients/boundaries **against SP**, moisture treatment, thermal mesh/time convergence, interfacial bar temperatures, section/longitudinal thermal consistency; Annex K only cross-check |
| SP §8.2.24 / Appendix L | No unaccounted heat-induced concrete spalling changing the section or exposing steel | Appendix L F-index computed conditionally; hidden default natural sand assumed | Verify composition/moisture/unit interpretation; if spalling possible, qualify physical loss/protective measures or withhold normative claim. Do not silently ignore |
| SP §8.1.11 | Permits an explicitly selected EN/TKP route | TKP route is today's public numerical engine | SP route must be independent and unambiguous; TKP is **not default and is not labelled SP** |

**Source-domain issue:** SP Table 9 and Table 10 strength/modulus reduction points end at **800°C**, although concrete near the exposed surface of the sample K1 at 90 minutes was roughly **990°C**. Unlike a 500°C isotherm simplification, the full heated-fibre method must not silently extrapolate strength past tabulated temperatures or automatically invent a 0-strength cutoff. Research a defensible source-qualified extension or fail closed with an explicit material-domain blocker. Concrete expansion/shrinkage tables cover higher temperatures; they do not supply missing resistance curves.

## 2. The actual calculation required

### 2.1 Thermal problem

For each requested fire minute t and location z, solve the SP-consistent transient cross-sectional temperature field theta_c(x,y,z,t) and each actual reinforcement theta_si(z,t). Use material properties k(theta), rho(theta), c(theta) and heat/moisture transfer subject to the SP fire boundary; output surface, interior and rebar temperatures plus energy/convergence evidence. Reuse the **generic FVM numerical infrastructure** only after SP property/boundary qualification; do not reuse TKP material laws simply because they already run.

### 2.2 Heated constitutive response

At each fibre, use SP5 ambient resistance, SP Table 9 or 10 strength/modulus reduction, Tables 11–12 concrete thermal strain and eq (6) steel expansion; ensure stress–strain law, tangent stiffness and ultimate strains are from a consistent allowed source. Record source table, temperature and interpolation/domain status for each material. Include thermal eigenstrains and *their historical dependence* where the stated physics requires it.

### 2.3 Actual section and whole-member ULS

For every section z and time t, integrate real fibre stresses N_int, Mx_int, My_int and compatible strain/curvature. Determine the **strain-compatible** resistance boundary for a specified positive proportional fire load factor lambda rather than stopping at the artificial lambda<=2 scan. Solve the complete member equilibrium under:
- physical end translations/rotations along x and y; sway or non-sway, eccentricity and initial imperfections;
- N(z), Mx(z), My(z) or equivalent mechanically compatible nodal/transverse loads;
- real heated length, section evolution, and second-order P–Delta or bifurcation as required;
- axial/combined flexural failure, concrete crushing, steel limit strain, strength, instability and other applicable modes.

Correctly classify a physical ultimate limit point or loss of stable equilibrium; **Newton non-convergence is UNKNOWN** until separately verified. At a converged state, beta and k based on SP must be used, not TKP beta/k.

### 2.4 Physical first-failure time t_R

Let lambda_R,member(t) be the verified maximum proportional member load from a *compatible* continuation/ULS analysis at fire time t for the imposed action profile. The target utilization is U_member(t)=1/lambda_R,member(t). The first failure time is the earliest fire time whose established member resistance does not support lambda=1, incorporating all applicable failure modes. Refine the time bracket and numerical mesh until the user-defined/engineering-qualified t_R tolerance is demonstrated. If the model or source data are incomplete, output **NOT_ESTABLISHED**; if no first failure occurs within a verified horizon, output only a lower bound t_R>t_last (not a fabricated exact time).

An upper strength envelope / LP lower utilization bound U_lower(t) is a valuable **necessary test** and can prove impossible loads, but can **never replace** lambda_R,member or be described as actual U_member(t). Equally, a single successful equilibrium at R90 is not proof of all-time member stability.

## 3. Focused implementation campaign and gates

| Phase | Change | Minimum independent acceptance |
|---|---|---|
| SP-R.1 | Source-controlled SP material factors and ambient SP5 resistances | Hand-check every Table 9/10 factor, beta, 11/12 alpha and eq (6); temperature-domain edge tests; no TKP coefficient leakage |
| SP-R.2 | SP-consistent nonlinear transient thermal model | 2D source / boundary benchmark, 3+ grid levels, >=2 time steps, steel corner/side temperatures and integrated heat balance; documented errors |
| SP-R.3 | SP nonlinear compatible heated fibre sections | Closed-form ambient axial/bending references; N–Mx–My equilibrium/tangent and load-capacity boundary benchmarks; independent numerical solver cross-check |
| SP-R.4 | Coupled full-column stability and thermal restraint | Pinned/fixed/free and sway/non-sway benchmarks, N(z)/Mx(z)/My(z) and calibrated imperfections; force/energy/deflection convergence |
| SP-R.5 | R(t) first-failure search | Synthetic known failure times, stable/unstable branches, time-bracket proof, monotonic and nonmonotonic cases, unknown-safe handling |
| SP-R.6 | Spalling / material-source closure | Appendix L input and unit audit, source evidence; thermal/mechanical protection or fail-closed |
| SP-R.7 | Independent validation and report | Representative loaded fire column datasets / independent normative references for temperature/deflection/failure, applicability envelope, verified U(t), t_R and SP clause trace in final report |

**Priority:** SP-R.1 -> SP-R.2 -> SP-R.3 -> SP-R.4 -> SP-R.5 -> SP-R.6/7 validation (with spalling/source status checked throughout). Do not postpone SP-specific mechanics until after interface polishing. Do not promise an exact t_R until method/data qualification is complete.

## 4. Missing user-supplied physical information

The source K1 example contains 600x600mm, L3m, 8Ø20, concrete class, nominal cover and one midspan N=50kN, Mx=2kNm, My=0kNm, mu=1. It **does not fully define** end fixity (translations and rotations in two planes), axial/transverse load application, actual longitudinal moment/force distribution, initial imperfection, heated column length/temperature variation, bar manufacturing route/quality or verified concrete moisture/spalling assumption.

Implement explicit support and load-profile input or an openly chosen structural idealization. Do **not** assume the current one midspan section and effective-length factors define the true physical frame. Use supplied actions as already fire-design values; do not introduce a second load combination unless specifically requested.

## 5. Final validation and reporting contract

**Only a truly completed, code-scope and physically qualified analysis can display:** t_R=... minutes; U_member(t) with governing z and failure mode; Rrequired; complies/does not comply; supported tolerance/uncertainty; source method SP2026_CALCULATED_R; full source inputs, spalling, material range, thermal grid convergence and mechanical benchmarks.

Otherwise give exact status **NOT_ESTABLISHED** with the specific missing source/input/qualification reasons. Never print a normatively positive PASS based on a diagnostic section strain ratio, artificial test-load scan, LP lower utilization bound, section-isotherm graphic or table rating.

**Explicit exclusions:** Table 3 fire-rating lookup; any other normative tabular shortcut; SP §8.2.21 simplified 500°C isotherm *resistance* method; implicit fallback to TKP constitutive factors. Existing visual 500°C contours may remain strictly as graphics.

**Normative closure remains pending.** Green CI only means regression performance; SP-compliant R(t) needs the above code, evidence, and design-specific input.
